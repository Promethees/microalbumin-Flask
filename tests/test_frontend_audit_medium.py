"""Regression tests for the medium-severity frontend audit findings (2026-09-30).

Same approach as test_frontend_audit_fixes.py: behavioural checks run the real
static scripts (or single functions cut out of them by `_fn`) under `node` in a
vm context with the few browser globals they touch stubbed. Where a fix is
about markup or *where* a call sits, the test reads the source.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
JS = REPO / 'static' / 'script'


def _node(harness, **env):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    out = subprocess.run(
        [node, '-e', harness],
        env={**os.environ, 'EOK_JS': str(JS), **{k: json.dumps(v) for k, v in env.items()}},
        capture_output=True, text=True, timeout=60)
    if out.returncode:
        pytest.fail('node harness failed:\n' + out.stderr[-2000:], pytrace=False)
    return json.loads(out.stdout)


def _src(name):
    return (JS / name).read_text(encoding='utf-8')


# Harness prelude: FN(file, name) returns the source of one top-level function
# (brace-matched, string/template/comment aware enough for this codebase).
PRELUDE = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
function FN(file, name) {
    const src = fs.readFileSync(path.join(process.env.EOK_JS, file), 'utf8');
    const re = new RegExp('^[ \\t]*(async\\s+)?function\\s+' + name + '\\s*\\(', 'm');
    const m = re.exec(src);
    if (!m) throw new Error('no function ' + name + ' in ' + file);
    let i = src.indexOf('{', m.index + m[0].length - 1);
    // skip the parameter list (may hold default-value braces)
    let depthP = 0, j = m.index + m[0].length - 1;
    for (; j < src.length; j++) {
        if (src[j] === '(') depthP++;
        else if (src[j] === ')') { depthP--; if (!depthP) break; }
    }
    i = src.indexOf('{', j);
    let depth = 0, k = i, q = null;
    for (; k < src.length; k++) {
        const c = src[k];
        if (q) {
            if (c === '\\') { k++; continue; }
            if (c === q) q = null;
            continue;
        }
        if (c === '/' && src[k + 1] === '/') { k = src.indexOf('\n', k); continue; }
        if (c === '/' && src[k + 1] === '*') { k = src.indexOf('*/', k) + 1; continue; }
        if (c === '"' || c === "'" || c === '`') { q = c; continue; }
        if (c === '{') depth++;
        else if (c === '}') { depth--; if (!depth) break; }
    }
    return src.slice(m.index, k + 1);
}
function LOAD(ctx, file) {
    vm.runInContext(fs.readFileSync(path.join(process.env.EOK_JS, file), 'utf8'), ctx);
}
function OUT(o) { process.stdout.write(JSON.stringify(o)); }
// The real escape helpers (_escHtml / _esc / _attr) from navigation.js.
const HELPERS = fs.readFileSync(path.join(process.env.EOK_JS, 'navigation.js'), 'utf8')
    .split('\n').filter(l => /^const _(escHtml|esc|attr) = /.test(l)).join('\n');
"""


# ---------------------------------------------------------------------------
# index.js:453 — once the SSE stream closed mid-run, the /get_data fallback
# never redrew: the carrying branch had already set prevFile = currentFile.
# ---------------------------------------------------------------------------

FALLBACK_TICK = PRELUDE + r"""
let draws = 0, carrying = true;
const ctx = {
    AppState: { currentFile: 'run.csv', prevFile: null, scriptRunning: true },
    liveStreamCarrying: () => carrying,
    drawMeasurementChart: () => { draws++; },
};
vm.createContext(ctx);
vm.runInContext(FN('index.js', 'chartFallbackTick'), ctx);
ctx.chartFallbackTick(); ctx.chartFallbackTick();      // stream carrying: no timer redraws
const whileCarrying = draws;
carrying = false;                                        // stream closed for good
ctx.chartFallbackTick(); ctx.chartFallbackTick();
const afterClose = draws - whileCarrying;
ctx.AppState.scriptRunning = false;                      // run over: stop redrawing
ctx.chartFallbackTick(); ctx.chartFallbackTick();
OUT({ whileCarrying, afterClose, idle: draws - whileCarrying - afterClose });
"""


def test_chart_falls_back_to_polling_when_the_stream_closes_mid_run():
    r = _node(FALLBACK_TICK)
    assert r == {'whileCarrying': 0, 'afterClose': 2, 'idle': 0}


# ---------------------------------------------------------------------------
# data-handling.js:147 — calibration JSON keys/values reached tr.innerHTML
# unescaped, and a non-string fit_type threw inside getFormula.
# ---------------------------------------------------------------------------

CAL_JSON_TABLE = PRELUDE + r"""
const src = fs.readFileSync(path.join(process.env.EOK_JS, 'data-handling.js'), 'utf8');
const a = src.indexOf('const fitType = JSON_content.fit_type');
const b = src.indexOf('buildInfoTable(infoData);', a) + 'buildInfoTable(infoData);'.length;
const body = src.slice(a, b);
const html = [];
function el() {
    const e = { children: [], style: {}, appendChild(c) { this.children.push(c); } };
    Object.defineProperty(e, 'innerHTML', { set(v) { html.push(v); }, get() { return ''; } });
    return e;
}
const ctx = {
    AppState: { currentMeasurementMode: process.env.EOK_MODE ? JSON.parse(process.env.EOK_MODE) : 'point' },
    document: { createElement: el },
    _escHtml: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'),
};
vm.createContext(ctx);
let error = null;
try {
    vm.runInContext('(function (JSON_content, display) {' + body + '})', ctx)(JSON.parse(process.env.EOK_CAL), el());
} catch (e) { error = String(e); }
OUT({ error, html: html.join('\n') });
"""

EVIL = '<img src=x onerror=alert(1)>'


@pytest.mark.parametrize('mode', ['point', 'kinetics'])
def test_calibration_json_table_escapes_file_values(mode):
    cal = {
        'fit_type': 3,  # not a string: used to throw in getFormula
        'for_meas': EVIL, 'meas_unit': EVIL, 'concen_unit': EVIL,
        'fit_coef': {EVIL: EVIL},
        EVIL: EVIL if mode == 'point' else {'fit_coef': {EVIL: EVIL}},
    }
    r = _node(CAL_JSON_TABLE, EOK_CAL=cal, EOK_MODE=mode)
    assert r['error'] is None
    assert '<img' not in r['html']
    assert '&lt;img' in r['html']


# ---------------------------------------------------------------------------
# data-handling.js:1059 — a subject named `Batch "7"` came back from the edit
# dialog as `Batch`, and Save renamed the folder the user never touched. Item
# cards and the merge <option>s had the same unescaped pattern.
# ---------------------------------------------------------------------------

SUBJECT_EDIT = PRELUDE + r"""
const unhtml = s => s.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const subject = JSON.parse(process.env.EOK_SUBJECT);
let opts = null;
const fetched = [];
const ctx = {
    document: { body: { classList: { contains: () => false } } },
    Swal: { fire: async (o) => { opts = o; return { value: undefined }; } },
    fetch: async (u, o) => { fetched.push(u); return { json: async () => ({ status: 'success' }) }; },
    AppState: {},
};
vm.createContext(ctx);
vm.runInContext(HELPERS + FN('data-handling.js', 'editReportSubject') + FN('data-handling.js', 'loadEditSwalItems'), ctx);
(async () => {
    await vm.runInContext('editReportSubject', ctx)(subject, null);
    const val = /id="swal-rename-input"[^>]*value="([^"]*)"/.exec(opts.html)[1];
    // item cards
    const cards = [];
    const container = { innerHTML: '', appendChild(c) { cards.push(c); } };
    ctx.fetch = async () => ({ json: async () => ({ status: 'success', items: [{ filename: subject + '.csv', metadata: { mode: subject } }] }) });
    ctx.document.createElement = () => ({ style: {}, dataset: {} });
    await vm.runInContext('loadEditSwalItems', ctx)(subject, container);
    OUT({ value: unhtml(val), titleHtml: opts.title || null, titleText: opts.titleText || null, card: cards[0].innerHTML });
})();
"""


@pytest.mark.parametrize('subject', ['Batch "7"', 'a<b>&c'])
def test_edit_subject_dialog_keeps_the_exact_name(subject):
    r = _node(SUBJECT_EDIT, EOK_SUBJECT=subject)
    assert r['value'] == subject
    assert r['titleHtml'] is None and subject in r['titleText']
    assert '<b>' not in r['card'] and 'data-filename="' + subject.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;') + '.csv"' in r['card']


def test_merge_subject_options_are_escaped():
    src = _src('data-handling.js')
    assert 'subjects.map(s => `<option value="${_attr(s)}">${_escHtml(s)}</option>`)' in src


# ---------------------------------------------------------------------------
# data-handling.js:896 — getEstimatedValue(...).toFixed(4) threw when a source
# had no valid reading near the reference point, aborting the mode update.
# ---------------------------------------------------------------------------

POINT_NULL_EST = PRELUDE + r"""
const els = {};
const el = id => (els[id] = els[id] || { id, textContent: '', innerHTML: '' });
const ctx = {
    AppState: { xAxis: 'time', refCalPoint: 99999, responseData: [{ Timestamp: 0, 'Value:1': '0.5' }, { Timestamp: 10, 'Value:1': '0.6' }],
                metaData: {}, globalAnalysis: { meas: 'Abs' } },
    $hidden: () => {}, getTimeUnitMultiplier: () => 1, getTimeUnitValue: () => 'seconds',
    measNumber: v => (isFinite(parseFloat(v)) ? parseFloat(v) : null),
    document: { getElementById: el },
    t: (k, f) => f, _escHtml: s => String(s), computeFit: v => v,
};
vm.createContext(ctx);
LOAD(ctx, 'calculate.js');
vm.runInContext(FN('data-handling.js', 'processPointMode'), ctx);
const con = { id: 'der-con-source-0', innerHTML: '', textContent: '' };
let error = null;
try { ctx.processPointMode({ fit_type: 'linear', fit_coef: {} }, con); } catch (e) { error = String(e); }
OUT({ error, msg: el('est-value-msg-source-0').textContent, con: con.textContent });
"""


def test_point_mode_survives_a_source_with_no_reading_at_the_reference():
    r = _node(POINT_NULL_EST)
    assert r['error'] is None
    assert 'source-1' in r['msg']
    assert r['con'] == '—'


# ---------------------------------------------------------------------------
# data-handling.js:1968 / init.js:291 — one source's estimate being null (the
# others fine) made Export throw on .toFixed and the estimate line fail.
# ---------------------------------------------------------------------------

PARTIAL_NULL_EST = PRELUDE + r"""
const swals = [];
const els = {};
const el = id => (els[id] = els[id] || { id, innerHTML: '' });
const ctx = {
    AppState: { globalEstimatedValue: [0.5, null], numSources: 2, responseData: [], plotColors: ['a', 'b'],
                globalAnalysis: { meas: 'Abs', meas_unit: 'AU' } },
    Swal: { fire: o => swals.push(o) },
    getValFloat: () => 30, getExpTimeUnit: () => 'seconds', getTimeUnitMultiplier: () => 1,
    getSelectedExportSources: () => [1, 2],
    getEstimatedValue: (d, tp, i) => (i === 1 ? 0.5 : null),
    document: { getElementById: el },
    t: (k, f) => f, _escHtml: s => String(s),
};
vm.createContext(ctx);
vm.runInContext(FN('init.js', 'isNullOrArrayOfNull') + FN('init.js', 'updatePointEstimate') + FN('data-handling.js', 'generatePointData'), ctx);
const errors = [];
let data;
try { data = ctx.generatePointData(); } catch (e) { errors.push('export: ' + e); }
try { ctx.updatePointEstimate(); } catch (e) { errors.push('estimate: ' + e); }
OUT({ errors, data, swal: swals.map(s => s.text), line: el('est-val-exp').innerHTML });
"""


def test_export_and_estimate_line_survive_one_null_source():
    r = _node(PARTIAL_NULL_EST)
    assert r['errors'] == []
    assert r['data'] is None
    assert len(r['swal']) == 1 and 'source: 2' in r['swal'][0]
    assert '0.5000' in r['line'] and '[#S2] —' in r['line']


# ---------------------------------------------------------------------------
# data-handling.js:2071 (also 937) — isVal only rejected 'NONE', so OVFL / INF
# / inf were exported as a Turn standard's Value, and the file then failed
# CSV_SCHEMA_POINT_CAL_TURN on the editor's Save.
# ---------------------------------------------------------------------------

TURN_EXPORT = PRELUDE + r"""
const posted = [];
const rows = [
    { Timestamp: 1, 'Value:1': '0.1' }, { Timestamp: 2, 'Value:1': 'OVFL' }, { Timestamp: 3, 'Value:1': '0.3' },
    { Timestamp: 4, 'Value:1': 'INF' }, { Timestamp: 5, 'Value:1': 'inf' }, { Timestamp: 6, 'Value:1': 'NONE' },
];
const ctx = {
    console, window: {}, AppState: { responseData: rows, globalAnalysis: { meas: 'Abs', meas_unit: 'AU' }, metaData: {} },
    document: { querySelectorAll: () => rows.map(r => ({ getAttribute: () => String(r.Timestamp), value: '5' })) },
    getSelectedExportSources: () => [1],
    Swal: { fire: () => {} }, t: (k, f) => f,
    $: { ajax: o => { posted.push(JSON.parse(o.data)); return { then: () => Promise.resolve({ src: 1, resp: { status: 'success' } }) }; } },
    exportFolderLabel: p => p,
};
vm.createContext(ctx);
LOAD(ctx, 'short-hands.js');
vm.runInContext(FN('data-handling.js', 'exportTurnCal'), ctx);
ctx.exportTurnCal('/data', 'cal');
// processTurnDerive: a sentinel is a dash, not an "err" cell.
const container = { innerHTML: '', classList: { toggle() {}, add() {}, remove() {} } };
Object.assign(ctx, { $hidden: () => {}, computeFit: v => { if (!isFinite(v)) throw new Error('bad'); return v * 2; },
                     document: { getElementById: () => container }, _escHtml: s => String(s) });
ctx.AppState.numSources = 1;
vm.runInContext(FN('data-handling.js', 'processTurnDerive'), ctx);
ctx.processTurnDerive({ fit_type: 'linear', fit_coef: {} });
OUT({ entries: posted.map(p => p.entries), derive: container.innerHTML });
"""


def test_turn_export_skips_sentinel_values():
    from routes.file_routes import _SCHEMA_VALIDATORS
    from file_path import CSV_SCHEMA_POINT_CAL_TURN
    r = _node(TURN_EXPORT)
    assert len(r['entries']) == 1
    entries = r['entries'][0]
    assert [e['estValue'] for e in entries] == ['0.1', '0.3']
    pattern = re.compile(_SCHEMA_VALIDATORS[CSV_SCHEMA_POINT_CAL_TURN]['data'])
    assert all(pattern.match(f"{e['con']},{e['estValue']}") for e in entries)
    assert 'err' not in r['derive']


# ---------------------------------------------------------------------------
# data-handling.js:45 — the clear* helpers looped to the previous
# AppState.numSources (1 after load), so sources 2..N of the next file kept
# the last file's concentrations, labels and colours.
# ---------------------------------------------------------------------------

CLEAR_PER_SOURCE = PRELUDE + r"""
const store = new Map();
const localStorage = {
    get length() { return store.size; },
    key: i => [...store.keys()][i] ?? null,
    getItem: k => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: k => store.delete(k),
};
for (let i = 0; i < 4; i++) {
    localStorage.setItem(`con-value-read-source-${i}`, '5');
    localStorage.setItem(`custom-line-label-source-${i}`, 'L');
    localStorage.setItem(`custom-source-color-${i}`, '#000');
}
localStorage.setItem('theme', 'dark');
const ctx = { localStorage, AppState: { numSources: 1 } };
vm.createContext(ctx);
const src = fs.readFileSync(path.join(process.env.EOK_JS, 'data-display.js'), 'utf8');
const helper = /^function _clearLocalByPrefix/m.test(src) ? FN('data-display.js', '_clearLocalByPrefix') : '';
vm.runInContext(helper + FN('data-display.js', 'clearConcentrationValues') + FN('data-display.js', 'clearCustomLabels')
    + FN('data-display.js', 'clearCustomColors'), ctx);
ctx.clearConcentrationValues(); ctx.clearCustomLabels(); ctx.clearCustomColors();
OUT({ left: [...store.keys()] });
"""


def test_new_file_clears_every_source_not_just_the_previous_count():
    assert _node(CLEAR_PER_SOURCE)['left'] == ['theme']


# ---------------------------------------------------------------------------
# edit-file.js:439 / :1017 — text mode put the raw file into <textarea> via
# innerHTML (RCDATA: `</textarea>` escaped it, `&amp;` was decoded and saved
# back as `&`); the filename input and the title were unescaped, and a mode
# toggle re-rendered without restoring the name, so `std "A".csv` was saved
# as `std .csv`. (renderContent is a closure inside editFile, so these are
# source checks.)
# ---------------------------------------------------------------------------

def test_editor_never_puts_raw_content_or_filename_into_markup():
    src = _src('edit-file.js')
    assert '${content.content}</textarea>' not in src
    assert 'value="${fileName}"' not in src
    assert src.count('value="${_attr(fileName)}"') == 3
    assert 'title: `Edit ${nameToShow}`' not in src
    assert 'titleText: `Edit ${nameToShow}`' in src


def test_editor_mode_toggle_restores_name_and_text_as_dom_values():
    src = _src('edit-file.js')
    toggle = src[src.index("toggleButton.addEventListener('click'"):]
    toggle = toggle[:toggle.index('preConfirm')]
    render = toggle.index('renderContent({ content: originalContent })')
    fill = toggle.index('fillRawFields(originalContent, nameToShow)')
    assert fill > render
    body = src[src.index('function fillRawFields'):]
    body = body[:body.index('\n            }\n')]
    assert "nameInput.value = name" in body and "textArea.value = content" in body


# ---------------------------------------------------------------------------
# A tiny fake DOM for widget-building code: enough of createElement /
# appendChild / attributes / listeners / querySelector(All) by class, id and
# [data-*] to drive a render and a key press.
# ---------------------------------------------------------------------------

FAKE_DOM = r"""
class El {
    constructor(tag) {
        this.tagName = tag.toUpperCase(); this.children = []; this.parentElement = null;
        this.attrs = {}; this.dataset = {}; this.style = {}; this.listeners = {};
        this.className = ''; this.textContent = ''; this.id = ''; this.disabled = false; this.hidden = false;
        const self = this;
        this.classList = {
            add: (...c) => { const s = new Set(self.className.split(/\s+/).filter(Boolean)); c.forEach(x => s.add(x)); self.className = [...s].join(' '); },
            remove: (...c) => { self.className = self.className.split(/\s+/).filter(x => x && !c.includes(x)).join(' '); },
            contains: c => self.className.split(/\s+/).includes(c),
            toggle: (c, on) => { const has = self.classList.contains(c); const want = on === undefined ? !has : !!on; if (want) self.classList.add(c); else self.classList.remove(c); return want; },
        };
    }
    set innerHTML(v) { this.children = []; this._html = v; }
    get innerHTML() { return this._html || ''; }
    set tabIndex(v) { this.attrs.tabindex = String(v); }
    get tabIndex() { return this.attrs.tabindex === undefined ? -1 : Number(this.attrs.tabindex); }
    setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'id') this.id = String(v); if (k === 'class') this.className = String(v); }
    getAttribute(k) { return k === 'id' ? this.id : (k in this.attrs ? this.attrs[k] : null); }
    hasAttribute(k) { return k in this.attrs; }
    removeAttribute(k) { delete this.attrs[k]; }
    appendChild(c) { if (c.parentElement) c.parentElement.removeChild(c); c.parentElement = this; this.children.push(c); return c; }
    append(...cs) { cs.forEach(c => (typeof c === 'string' ? this.appendChild(Object.assign(new El('#text'), { textContent: c })) : this.appendChild(c))); }
    insertBefore(c, ref) { c.parentElement = this; const i = this.children.indexOf(ref); this.children.splice(i < 0 ? this.children.length : i, 0, c); return c; }
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentElement = null; return c; }
    remove() { if (this.parentElement) this.parentElement.removeChild(this); }
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
    removeEventListener(t, f) { this.listeners[t] = (this.listeners[t] || []).filter(x => x !== f); }
    fire(t, ev = {}) { const e = Object.assign({ type: t, target: this, preventDefault() { this.defaultPrevented = true; }, stopPropagation() {} }, ev); (this.listeners[t] || []).slice().forEach(f => f(e)); return e; }
    click() { this.fire('click'); }
    focus() { DOC.activeElement = this; }
    getBoundingClientRect() { return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
    closest(sel) { let e = this; while (e) { if (MATCH(e, sel)) return e; e = e.parentElement; } return null; }
    contains(o) { while (o) { if (o === this) return true; o = o.parentElement; } return false; }
    *walk() { for (const c of this.children) { yield c; yield* c.walk(); } }
    querySelectorAll(sel) {
        const parts = sel.trim().split(/\s+/);
        return [...this.walk()].filter(e => {
            if (!MATCH(e, parts[parts.length - 1])) return false;
            let p = e.parentElement, i = parts.length - 2;
            while (i >= 0 && p) { if (MATCH(p, parts[i])) i--; p = p.parentElement; }
            return i < 0;
        });
    }
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
function MATCH(e, sel) {
    const m = /^([a-z]+)?((?:[.#][\w-]+)*)((?:\[[^\]]+\])*)$/i.exec(sel);
    if (!m) throw new Error('fake DOM selector: ' + sel);
    if (m[1] && e.tagName !== m[1].toUpperCase()) return false;
    for (const t of (m[2].match(/[.#][\w-]+/g) || [])) {
        if (t[0] === '.' && !e.classList.contains(t.slice(1))) return false;
        if (t[0] === '#' && e.id !== t.slice(1)) return false;
    }
    for (const a of (m[3].match(/\[[^\]]+\]/g) || [])) {
        const [, k, v] = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(a);
        let val;
        if (k.startsWith('data-')) { const dk = k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase()); val = e.dataset[dk]; }
        else val = e.getAttribute(k);
        if (val === undefined || val === null) return false;
        if (v !== undefined && String(val) !== v) return false;
    }
    return true;
}
const DOC = {
    activeElement: null, body: new El('body'), head: new El('head'), listeners: {},
    createElement: t => new El(t),
    getElementById: id => (DOC.body.id === id ? DOC.body : [...DOC.body.walk()].find(e => e.id === id) || null),
    querySelector: s => DOC.body.querySelector(s), querySelectorAll: s => DOC.body.querySelectorAll(s),
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
    removeEventListener() {},
};
"""


# ---------------------------------------------------------------------------
# generate-chart.js:504 — the legend's show/hide toggle was a click on plain
# spans (no role, no tabindex, no keys); the pencil was an unnamed "✎".
# ---------------------------------------------------------------------------

LEGEND = PRELUDE + FAKE_DOM + r"""
const wrap = new El('div'); DOC.body.appendChild(wrap);
const canvas = new El('canvas'); canvas.id = 'c1'; wrap.appendChild(canvas);
const hidden = { 0: false, 1: false };
const chart = { data: { datasets: [{}, {}] }, setDatasetVisibility: (i, v) => { hidden[i] = !v; }, update() {} };
const ctx = {
    document: DOC, t: (k, f) => f,
    Chart: { defaults: { plugins: { legend: { labels: { generateLabels: () => [0, 1].map(i => ({ text: 'Source ' + (i + 1), datasetIndex: i, hidden: hidden[i], strokeStyle: '#000' })) } } } } },
};
vm.createContext(ctx);
vm.runInContext(FN('generate-chart.js', 'renderHtmlLegend'), ctx);
ctx.renderHtmlLegend(chart, 'c1', null);
const legend = DOC.getElementById('html-legend-c1');
const labels = () => legend.querySelectorAll('.legend-label');
const before = labels().map(l => ({ role: l.getAttribute('role'), tab: l.getAttribute('tabindex'), pressed: l.getAttribute('aria-pressed') }));
const pencils = legend.querySelectorAll('.legend-pencil').map(p => p.getAttribute('aria-label'));
const first = labels()[0];
first.focus();
const ev = first.fire('keydown', { key: 'Enter' });
const after = labels()[0];
OUT({ before, pencils, hidden0: hidden[0], prevented: !!ev.defaultPrevented, pressedAfter: after.getAttribute('aria-pressed'),
      focusKept: DOC.activeElement === after && after !== first });
"""


def test_legend_series_toggle_works_from_the_keyboard():
    r = _node(LEGEND)
    assert r['before'] == [{'role': 'button', 'tab': '0', 'pressed': 'true'}] * 2
    assert r['pencils'] == ['Edit label and color: Source 1', 'Edit label and color: Source 2']
    assert r['hidden0'] is True and r['prevented'] is True
    assert r['pressedAfter'] == 'false'
    assert r['focusKept'] is True


# ---------------------------------------------------------------------------
# init.js:1085 — saving App Settings merged the controller settings into
# USER_SETTINGS but never applied them: unticking "Connect to the device" kept
# the poll (and the port) going until a reload, and /settings did not echo
# the values it had actually kept.
# ---------------------------------------------------------------------------

DEVICE_SETTINGS = PRELUDE + FAKE_DOM + r"""
const section = new El('div'); section.id = 'device-control-section'; DOC.body.appendChild(section);
const box = new El('input'); box.id = 'devctl-link-toggle'; box.checked = true; section.appendChild(box);
const collapse = new El('div'); collapse.id = 'device-control-collapse'; section.appendChild(collapse);
const status = new El('div'); status.id = 'devctl-status'; section.appendChild(status);
const fetched = [], timers = [];
let nextId = 1;
const ctx = {
    document: DOC, window: { addEventListener() {} }, t: (k, f) => f, console,
    USER_SETTINGS: { device_control_enabled: true, device_link_enabled: true, device_state_poll_ms: 1500 },
    fetch: async (u) => { fetched.push(u); return { status: 200, json: async () => ({ status: 'offline' }) }; },
    setInterval: (f, ms) => { const id = nextId++; timers.push({ id, ms, live: true }); return id; },
    clearInterval: id => { const tm = timers.find(x => x.id === id); if (tm) tm.live = false; },
    setTimeout: () => 0, clearTimeout: () => {},
    requestAnimationFrame: () => 0, ResizeObserver: class { observe() {} disconnect() {} },
};
vm.createContext(ctx);
LOAD(ctx, 'device-control.js');
vm.runInContext('setDeviceControlStatus = () => {}; applyDeviceState = () => {};', ctx);
vm.runInContext('startDevicePolling()', ctx);                         // panel open, polling at 1500
const live = () => timers.filter(x => x.live).map(x => x.ms);
const r = { start: live() };
ctx.USER_SETTINGS.device_state_poll_ms = 3000;
vm.runInContext('applyDeviceControlSettings()', ctx);
r.newInterval = live();
ctx.USER_SETTINGS.device_link_enabled = false;
vm.runInContext('applyDeviceControlSettings()', ctx);
r.afterOff = live(); r.boxChecked = box.checked; r.released = fetched.includes('/device/disconnect');
ctx.USER_SETTINGS.device_control_enabled = false;
vm.runInContext('applyDeviceControlSettings()', ctx);
r.sectionHidden = section.classList.contains('hidden');
OUT(r);
"""


def test_saved_device_settings_apply_without_a_reload():
    r = _node(DEVICE_SETTINGS)
    assert r['start'] == [1500]
    assert r['newInterval'] == [3000]
    assert r['afterOff'] == [] and r['boxChecked'] is False and r['released'] is True
    assert r['sectionHidden'] is True


def test_settings_save_applies_controller_and_strip_settings():
    src = _src('init.js')
    save = src[src.index("fetch('/settings', {\n        method: 'POST'"):]
    save = save[:save.index("Swal.fire(t('settings.saved_title'")]
    assert 'saved.settings' in save
    assert 'applyDeviceControlSettings()' in save
    assert 'applySessionStripSetting()' in save


def test_post_settings_echoes_what_was_stored(tmp_path, monkeypatch):
    import state
    from main import app
    monkeypatch.setattr(state, 'script_dir', str(tmp_path))
    app.config['TESTING'] = True
    with app.test_client() as c:
        rv = c.post('/settings', json={'device_state_poll_ms': 100, 'device_link_enabled': False})
    body = rv.get_json()
    assert body['status'] == 'success'
    # 100 ms is below the floor, so the stored (default) value comes back.
    assert body['settings']['device_state_poll_ms'] == 1500
    assert body['settings']['device_link_enabled'] is False


# ---------------------------------------------------------------------------
# cdc-logging.js:247 — the session strip drew AppState.responseData: another
# open CSV's trace under "Recording", or (live file open) one row behind, so a
# manual Turn just taken was missing. With the stream carrying the run it now
# draws the session's own pushed rows.
# ---------------------------------------------------------------------------

STRIP_SOURCE = PRELUDE + FAKE_DOM + r"""
for (const id of ['strip-traces', 'strip-scale', 'strip-latest', 'strip-latest-label']) {
    const e = new El('div'); e.id = id; DOC.body.appendChild(e);
}
const other = Array.from({ length: 10 }, (_, i) => ({ Timestamp: i, 'Value:1': '9', 'Value:2': '9' }));
const ctx = {
    document: DOC, window: {}, t: (k, f) => f, sourceRamp: n => Array(n).fill('#000'),
    AppState: { responseData: other, numSources: 2, xAxis: 'time' },
    STRIP_W: 900, STRIP_H: 64,
};
vm.createContext(ctx);
LOAD(ctx, 'short-hands.js');
const src = FN('cdc-logging.js', 'drawSessionStrip');
vm.runInContext('const STRIP_W = 900, STRIP_H = 64;' + src, ctx);
const hasLive = /function liveStripSource/.test(fs.readFileSync(path.join(process.env.EOK_JS, 'live-stream.js'), 'utf8'));
if (hasLive) {
    vm.runInContext('let _liveStreamCarrying = true, _liveMeta = { num_sources: 1, x_axis: "turn" }, _liveRows = [' +
        '{ Timestamp: 1, "Value:1": "0.1" }, { Timestamp: 2, "Value:1": "0.2" }, { Timestamp: 3, "Value:1": "0.3" }];' +
        FN('live-stream.js', 'liveStripSource'), ctx);
}
ctx.drawSessionStrip();
OUT({ scale: DOC.getElementById('strip-scale').textContent, latest: DOC.getElementById('strip-latest').textContent });
"""


def test_session_strip_draws_the_live_session_not_the_open_file():
    r = _node(STRIP_SOURCE)
    assert r['scale'].startswith('3 rows') and 'turns' in r['scale']
    assert r['latest'] == '0.300'


# ---------------------------------------------------------------------------
# cdc-logging.js:64 — stopping a paused run left #strip-state at "Paused";
# resetRunControls() set readingPaused = false directly, so the next run's
# applyPausedState(false) returned early and the strip said "Paused" all run.
# ---------------------------------------------------------------------------

STRIP_PAUSE_RESET = PRELUDE + FAKE_DOM + r"""
for (const id of ['session-strip', 'strip-state', 'strip-traces', 'strip-elapsed', 'strip-latest', 'strip-next',
                  'strip-next-field', 'strip-scale', 'pause-reading-btn', 'reading-control-fab', 'reading-fab-pause',
                  'measure-point-btn', 'measure-point-fab', 'measure-fab-btn']) {
    const e = new El('div'); e.id = id; DOC.body.appendChild(e);
}
const ctx = { document: DOC, t: (k, f) => f, AppState: {}, console };
vm.createContext(ctx);
const names = ['applyStripPausedState', 'hideSessionStrip', 'resetRunControls'];
vm.runInContext('let readingPaused = true, _pausedAt = 1, manualSession = false;' +
    'function endStartupWatch() {} function applyPauseControlsUI() {} function stopControlObserver() {} function stopMeasureObserver() {}' +
    names.map(n => FN('cdc-logging.js', n)).join('\n'), ctx);
const state = DOC.getElementById('strip-state'), strip = DOC.getElementById('session-strip');
const r = {};
ctx.applyStripPausedState(true);
ctx.hideSessionStrip();
r.afterHide = [state.textContent, strip.classList.contains('is-paused')];
ctx.applyStripPausedState(true);
ctx.resetRunControls();
r.afterReset = [state.textContent, strip.classList.contains('is-paused')];
OUT(r);
"""


def test_strip_state_is_reset_after_a_paused_run_ends():
    r = _node(STRIP_PAUSE_RESET)
    assert r['afterHide'] == ['Recording', False]
    assert r['afterReset'] == ['Recording', False]


# ---------------------------------------------------------------------------
# cdc-logging.js:621 — Pause is offered as soon as /run_script succeeds, but
# the start-up watch kept counting while paused and tore a healthy session
# down as "The device did not respond".
# ---------------------------------------------------------------------------

STARTUP_PAUSE = PRELUDE + r"""
let now = 0, failed = false;
const ctx = {
    Date: { now: () => now }, document: { getElementById: () => null },
    startupTimeoutSec: () => 60, setInterval: () => 1, clearInterval: () => {},
};
vm.createContext(ctx);
vm.runInContext('let readingPaused = false, _pausedAt = null, _startupWatching = true, _startupStartedAt = 0,' +
    ' sessionStartTime = null, lastDataPointTime = null, sessionTimerHandle = null;' +
    'function _startupEl() { return null; } function applyPauseControlsUI() {} function applyStripPausedState() {}' +
    'function syncReadingFab() {} function tickSessionTimer() {}' +
    'function failStartupWatch() { globalThis.__failed = true; }' +
    FN('cdc-logging.js', 'tickStartupWatch') + FN('cdc-logging.js', 'applyPausedState'), ctx);
now = 5000; ctx.applyPausedState(true);
now = 120000; ctx.tickStartupWatch();          // paused for 115 s
const failedWhilePaused = !!ctx.__failed;
ctx.applyPausedState(false);
now = 130000; ctx.tickStartupWatch();          // 15 s of un-paused waiting in all
const failedAfterResume = !!ctx.__failed;
now = 5000 + 115000 + 61000; ctx.tickStartupWatch();
OUT({ failedWhilePaused, failedAfterResume, failedPastLimit: !!ctx.__failed });
"""


def test_startup_watch_holds_while_paused():
    r = _node(STARTUP_PAUSE)
    assert r == {'failedWhilePaused': False, 'failedAfterResume': False, 'failedPastLimit': True}


# ---------------------------------------------------------------------------
# cdc-logging.js:1002 — a pushed SESSION TIMEOUT / STOPPED log frame called
# terminateScript() (SIGINT into a logger already exiting) and announced its
# own reason, racing /check_status, which owns why a session ended (§2.31).
# ---------------------------------------------------------------------------

END_SENTINEL = PRELUDE + r"""
const calls = [];
const ctx = { AppState: { scriptRunning: true }, t: (k, f) => f, Swal: { fire: () => calls.push('swal') } };
vm.createContext(ctx);
vm.runInContext('let _terminationNoticeFired = false, _endSentinelSeen = false;' +
    'function terminateScript() { globalThis.__calls.push("terminate"); }' +
    'function checkScriptStatus() { globalThis.__calls.push("check"); return Promise.resolve(true); }' +
    'function stopSessionTimer() {} function updateStartupProgress() {} function onNewDataPoint() {}' +
    'function fireDoneNotification(m) { globalThis.__calls.push("done:" + m); }' +
    FN('cdc-logging.js', 'showTerminationNotice') + FN('cdc-logging.js', 'applyLogText'), ctx);
ctx.__calls = calls;
ctx.applyLogText('Received: Turn: 1\nSESSION TIMEOUT\n');
ctx.applyLogText('Received: Turn: 1\nSESSION TIMEOUT\nbye\n');   // a later frame
OUT({ calls, running: ctx.AppState.scriptRunning });
"""


def test_device_end_sentinel_defers_to_check_status():
    r = _node(END_SENTINEL)
    assert r['calls'] == ['check']
    assert r['running'] is True  # left for /check_status to decide


# ---------------------------------------------------------------------------
# cdc-logging.js:930 — terminateScript() had no in-flight guard while the
# route can block ~6 s, so a double-click on Stop sent a second SIGINT.
# ---------------------------------------------------------------------------

TERMINATE_GUARD = PRELUDE + FAKE_DOM + r"""
for (const id of ['terminate-script-btn', 'reading-fab-stop', 'measure-fab-stop']) {
    const b = new El('button'); b.id = id; DOC.body.appendChild(b);
}
let posts = 0, release;
const ctx = {
    document: DOC, console,
    fetch: (u) => { if (u === '/terminate_script') posts++; return new Promise(r => { release = () => r({ json: async () => ({ status: 'success' }) }); }); },
};
vm.createContext(ctx);
const src = fs.readFileSync(path.join(process.env.EOK_JS, 'cdc-logging.js'), 'utf8');
const guarded = /^async function _terminateScript/m.test(src);
const decl = (src.match(/^const STOP_BUTTON_IDS = .*$/m) || [''])[0] + (src.match(/^let _terminateInFlight = null;$/m) || [''])[0];
vm.runInContext(decl + 'function logEvent() {} function handleScriptTermination() {} async function clearLogs() {} function clearStatusCheck() {}' +
    FN('cdc-logging.js', 'terminateScript') + (guarded ? FN('cdc-logging.js', '_terminateScript') : ''), ctx);
(async () => {
    const p1 = ctx.terminateScript();
    const p2 = ctx.terminateScript();
    await new Promise(r => setImmediate(r));
    const during = ['terminate-script-btn', 'reading-fab-stop', 'measure-fab-stop'].map(id => DOC.getElementById(id).disabled);
    const postsDuring = posts;
    release();
    await p1; await p2;
    OUT({ postsDuring, during, fabAfter: DOC.getElementById('reading-fab-stop').disabled, again: (ctx.terminateScript(), posts) });
})();
"""


def test_stop_sends_one_terminate_while_one_is_in_flight():
    r = _node(TERMINATE_GUARD)
    assert r['postsDuring'] == 1
    assert r['during'] == [True, True, True]
    assert r['fabAfter'] is False
    assert r['again'] == 2  # a later, separate Stop still goes through


# ---------------------------------------------------------------------------
# device-control.js:1175 (and 885) — the menu and UV-channel chips were torn
# down and rebuilt on every state poll, so a focused chip lost focus to
# <body> within 1.5 s.
# ---------------------------------------------------------------------------

DEVICE_CHIPS = PRELUDE + FAKE_DOM + r"""
for (const id of ['devctl-menu-items', 'devctl-uvchannel-boxes']) { const e = new El('div'); e.id = id; DOC.body.appendChild(e); }
const ctx = {
    document: DOC, window: { addEventListener() {} }, t: (k, f) => f, console,
    setInterval: () => 1, clearInterval: () => {}, setTimeout: () => 0, clearTimeout: () => {},
    fetch: async () => ({ status: 200, json: async () => ({}) }),
    requestAnimationFrame: () => 0, ResizeObserver: class { observe() {} disconnect() {} },
};
vm.createContext(ctx);
LOAD(ctx, 'device-control.js');
vm.runInContext('deviceMenuItems = ["Absorbance", "Settings", "About"]; deviceUvChannels = ["UVA", "UVB"];', ctx);
const menu = DOC.getElementById('devctl-menu-items'), uv = DOC.getElementById('devctl-uvchannel-boxes');
vm.runInContext('drawDeviceMenuItems({ mode: "MEASURE", meas: "Absorbance", menupos: 0 }); drawDeviceUvChannels("UVA");', ctx);
const m1 = menu.children[1], u1 = uv.children[1];
m1.focus();
vm.runInContext('drawDeviceMenuItems({ mode: "SETTINGS", menupos: 1 }); drawDeviceUvChannels("UVB");', ctx);
const r = {
    menuKept: menu.children[1] === m1, uvKept: uv.children[1] === u1, focusKept: DOC.activeElement === m1,
    openMoved: [menu.children[0].classList.contains('devctl-menu-item--open'), m1.classList.contains('devctl-menu-item--open')],
    cursor: m1.classList.contains('devctl-menu-item--cursor'), uvOpen: u1.classList.contains('devctl-menu-item--open'),
};
vm.runInContext('deviceMenuItems = ["Absorbance", "Settings"]; drawDeviceMenuItems({ mode: "MEASURE", meas: "Absorbance", menupos: 0 });', ctx);
r.rebuiltOnNewList = menu.children.length === 2 && menu.children[1] !== m1;
OUT(r);
"""


def test_device_chips_are_updated_in_place_across_polls():
    r = _node(DEVICE_CHIPS)
    assert r['menuKept'] and r['uvKept'] and r['focusKept']
    assert r['openMoved'] == [False, True] and r['cursor'] and r['uvOpen']
    assert r['rebuiltOnNewList']


# ---------------------------------------------------------------------------
# report.js:1461 — the report console card put item.filename, item.path and
# metadata.mode into innerHTML, attributes and inline handlers unescaped; and
# refreshPreviewNormalization built [data-filename="…"] without CSS.escape.
# ---------------------------------------------------------------------------

REPORT_CARD = PRELUDE + FAKE_DOM + r"""
const container = new El('div'); container.id = 'report-items-container'; DOC.body.appendChild(container);
const name = JSON.parse(process.env.EOK_NAME);
const items = [
    { filename: name + '.csv', path: '/r/' + name + '.csv', metadata: { mode: 'kinetics' } },
    { filename: 'p' + name + '.csv', path: '/r/p' + name + '.csv', metadata: { mode: 'calibrate' } },
];
const ctx = {
    document: DOC, window: {}, console, CSS: { escape: s => String(s).replace(/["\\]/g, '\\$&') },
    fetch: async (u) => ({ json: async () => (u.startsWith('/get_report_items')
        ? { status: 'success', items } : { status: 'success', items: [name + '.json'] }) }),
    $: { get: (u, q) => Promise.resolve(q.file.startsWith('/r/p')
        ? { data: [{ Concentration: '1', Value: '2', TimePoint: name }] } : { data: [{ Timestamp: 0, 'Value:1': 1 }] }) },
    initItemPreview: () => {},
};
vm.createContext(ctx);
const src = fs.readFileSync(path.join(process.env.EOK_JS, 'report.js'), 'utf8');
const algo = src.match(/^const REPORT_ALGO_CHOICES = \[[\s\S]*?\n\];/m)[0];
const lifecycle = /^function destroyReportCharts/m.test(src)
    ? FN('report.js', 'destroyReportCharts') + '\nlet _reportLoadSeq = 0;\n' : '';
vm.runInContext(HELPERS + '\n' + algo + lifecycle + FN('report.js', '_fullPointTpEntryHtml') + FN('report.js', 'loadReportItems'), ctx);
(async () => {
    await ctx.loadReportItems('subj');
    const html = container.children.map(c => c.innerHTML).join('\n');
    const unhtml = s => s.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
    const attrs = [...html.matchAll(/data-(?:filename|item|path)="([^"]*)"/g)].map(m => unhtml(m[1]));
    // Run every inline handler that names a function taking the filename.
    const calls = [];
    const hctx = { calls };
    for (const fn of ['addPointTimePoint', 'updateReportWindowSize', 'updateReportDerivedQuantity', 'updatePointPreview', 'removePointTimePoint', 'toggleItemCardOpacity', 'deleteReportItem', 'toggleMetricDisplayArea'])
        hctx[fn] = (...a) => calls.push([fn, ...a.filter(x => typeof x === 'string')]);
    vm.createContext(hctx);
    let handlerErrors = 0;
    for (const m of html.matchAll(/on(?:click|change)="([^"]*)"/g)) {
        try { vm.runInContext(`(function(){ ${unhtml(m[1])} }).call({ value: '5', checked: true })`, hctx); }
        catch (e) { if (!/moveCard/.test(String(e))) { handlerErrors++; console.error(String(e), m[1]); } }
    }
    OUT({ html, attrs, calls, handlerErrors });
})();
"""


@pytest.mark.parametrize('name', ['<img src=x onerror=alert(1)>', 'std "A"', "O'Neil\\x"])
def test_report_console_card_escapes_file_names(name):
    r = _node(REPORT_CARD, EOK_NAME=name)
    assert '<img' not in r['html']
    for a in r['attrs']:
        assert name in a
    assert r['handlerErrors'] == 0
    named = [c for c in r['calls'] if c[0] not in ('toggleItemCardOpacity', 'deleteReportItem', 'toggleMetricDisplayArea')]
    assert named and all(name in c[1] for c in named)


def test_preview_normalization_selector_uses_css_escape():
    src = _src('report.js')
    fn = src[src.index('function refreshPreviewNormalization'):]
    fn = fn[:fn.index('\n}\n')]
    assert 'data-filename="${CSS.escape(filename)}"' in fn


# ---------------------------------------------------------------------------
# report.js:1256 — loadReportItems() / clearReportSubject() reset
# ReportItemConfig without destroying its Chart.js instances (and the delete
# path skipped pointChart), and a slow subject load could append its cards
# into the subject picked after it.
# ---------------------------------------------------------------------------

REPORT_LIFECYCLE = PRELUDE + FAKE_DOM + r"""
const container = new El('div'); container.id = 'report-items-container'; DOC.body.appendChild(container);
const section = new El('div'); section.id = 'report-console-section'; DOC.body.appendChild(section);
const gates = {};
const ctx = {
    document: DOC, window: {}, console, CSS: { escape: s => s }, AppState: {},
    fetch: (u) => {
        const subj = (u.match(/subject=([^&]*)/) || [])[1];
        const body = subj ? { status: 'success', items: [{ filename: subj + '.csv', path: '/r/' + subj, metadata: { mode: 'kinetics' } }] }
                          : { status: 'success', items: [] };
        const p = new Promise(r => { const go = () => r({ json: async () => body }); if (subj) gates[subj] = go; else go(); });
        return p;
    },
    $: { get: () => Promise.resolve({ data: [{ Timestamp: 0 }] }) },
    initItemPreview: () => {},
};
vm.createContext(ctx);
const src = fs.readFileSync(path.join(process.env.EOK_JS, 'report.js'), 'utf8');
const algo = src.match(/^const REPORT_ALGO_CHOICES = \[[\s\S]*?\n\];/m)[0];
const extra = /^function destroyReportCharts/m.test(src)
    ? FN('report.js', 'destroyReportCharts') + '\nlet _reportLoadSeq = 0;\n' : '';
vm.runInContext(HELPERS + '\n' + algo + extra + FN('report.js', '_fullPointTpEntryHtml') + FN('report.js', 'loadReportItems')
    + FN('report.js', 'clearReportSubject'), ctx);
const tick = () => new Promise(r => setImmediate(r));
(async () => {
    // Charts left from a previous subject.
    let destroyed = 0;
    const chart = () => ({ destroy: () => destroyed++ });
    ctx.window.ReportItemConfig = { 'old.csv': { chart: chart(), charts: { Slope: chart() }, pointChart: chart() } };
    const a = ctx.loadReportItems('A');
    const destroyedOnLoad = destroyed;
    const b = ctx.loadReportItems('B');
    await tick(); gates.B(); await b; await tick();
    gates.A(); await a; await tick();
    const cards = container.children.map(c => c.dataset.filename);
    ctx.window.ReportItemConfig = { 'x.csv': { chart: chart(), pointChart: chart() } };
    destroyed = 0;
    ctx.clearReportSubject();
    OUT({ destroyedOnLoad, cards, destroyedOnClear: destroyed });
})();
"""


def test_report_subject_switch_frees_charts_and_ignores_stale_loads():
    r = _node(REPORT_LIFECYCLE)
    assert r['destroyedOnLoad'] == 3
    assert r['cards'] == ['B.csv']
    assert r['destroyedOnClear'] == 2


def test_report_item_delete_also_frees_the_point_chart():
    src = _src('report.js')
    fn = src[src.index('async function deleteReportItem'):]
    fn = fn[:fn.index('\n}\n')]
    assert 'config.pointChart.destroy()' in fn


# ---------------------------------------------------------------------------
# ai-chat.js:688 — the feedback opt-out read window.USER_SETTINGS, but
# index.html declares `const USER_SETTINGS` (a global binding, not a window
# property), so the thumbs were shown with ai_feedback_enabled = false.
# ---------------------------------------------------------------------------

AI_FEEDBACK_OPTOUT = PRELUDE + FAKE_DOM + r"""
const msgs = new El('div'); msgs.id = 'okapi-ai-messages'; DOC.body.appendChild(msgs);
const bubble = new El('div'); msgs.appendChild(bubble);
let inserted = 0;
bubble.insertAdjacentElement = () => { inserted++; };
const ctx = { document: DOC, window: {}, AI: { activeLang: 'en' }, _FB_UP_HINT: { en: 'up' }, _FB_DOWN_HINT: { en: 'down' },
              _esc: s => s };
vm.createContext(ctx);
// Exactly how index.html declares it: a top-level const in a classic script.
vm.runInContext('const USER_SETTINGS = { ai_feedback_enabled: false };', ctx);
vm.runInContext(FN('ai-chat.js', '_attachFeedback'), ctx);
let error = null;
try { ctx._attachFeedback(bubble, { source: 'llm' }); } catch (e) { error = String(e); }
OUT({ inserted, windowSees: ctx.window.USER_SETTINGS === undefined ? 'undefined' : 'object', error });
"""


def test_ai_feedback_opt_out_is_honoured():
    r = _node(AI_FEEDBACK_OPTOUT)
    assert r['windowSees'] == 'undefined'  # the premise of the bug
    assert r['inserted'] == 0


# ---------------------------------------------------------------------------
# ai-chat.js:489 + user-guide.js:1061 + bug-report.js:210 — widget chrome was
# English-only. The user guide and the bug-report dialogs now go through t();
# every key they use must exist in all seven catalogs with the same English.
# ---------------------------------------------------------------------------

LANGS = ['en', 'vi', 'zh', 'fr', 'ja', 'ru', 'ko']


def _catalog(lang):
    return json.loads((REPO / 'ui_translations' / f'{lang}.json').read_text(encoding='utf-8'))


def _wrapped_keys(src, fn):
    return re.findall(fn + r"\('([\w.]+)',\s*'((?:[^'\\]|\\.)*)'\)", src)


@pytest.mark.parametrize('name,fn', [('user-guide.js', '_guideT'), ('bug-report.js', '_t')])
def test_widget_chrome_keys_exist_in_every_catalog(name, fn):
    pairs = _wrapped_keys(_src(name), fn)
    assert len(pairs) >= 9
    cats = {lang: _catalog(lang) for lang in LANGS}
    for key, english in pairs:
        for lang in LANGS:
            assert key in cats[lang], (lang, key)
        assert cats['en'][key] == english.replace("\\'", "'"), key


def test_user_guide_and_bug_report_have_no_hardcoded_chrome():
    guide = _src('user-guide.js')
    for literal in ["? 'Next →' :", "textContent = 'Skip →'", "? 'Skip' : 'Finish'", "= 'Loading…'", '} of ${this.steps.length}',
                    "'' : ' Click or interact with", 'aria-label="Close guide"']:
        assert literal not in guide, literal
    bug = _src('bug-report.js')
    for literal in ["title: 'Report a Bug'", "confirmButtonText: 'Yes, choose files'", "denyButtonText: 'No, just email'",
                    "title: 'Choose log files'", "title: 'Name the log archive'", "title: 'Log archive downloaded'"]:
        assert literal not in bug, literal


# ---------------------------------------------------------------------------
# ai-chat.js:497 (also 1463) — the icon-only "+", "✕" and "➤"/"■" buttons
# had a data-hint but no accessible name; the inputs relied on placeholders.
# ---------------------------------------------------------------------------

def test_ai_chat_icon_buttons_and_inputs_have_accessible_names():
    src = _src('ai-chat.js')
    for elem_id, key in [('okapi-ai-new-btn', 'ai.new_chat'), ('okapi-ai-close-btn', 'ai.close'),
                         ('okapi-ai-send-btn', 'ai.send'), ('okapi-ai-input', 'ai.input_label'),
                         ('okapi-ai-token-input', 'ai.token_label')]:
        tag = re.search(r'<\w+ id="' + elem_id + r'"[^>]*>', src).group(0)
        assert f"aria-label=\"${{_esc(_tr('{key}'" in tag, elem_id
    # Stop mode renames the button, and the reset names it Send again.
    assert "sendBtn.setAttribute('aria-label', _tr('ai.stop', 'Stop generation'))" in src
    assert "sendBtn.setAttribute('aria-label', _tr('ai.send', 'Send message'))" in src
    assert "btn.setAttribute('aria-label', `${_tr('ai.change_language'" in src
    pairs = _wrapped_keys(src, '_tr')
    cats = {lang: _catalog(lang) for lang in LANGS}
    for key, english in pairs:
        for lang in LANGS:
            assert key in cats[lang], (lang, key)
        assert cats['en'][key] == english, key


# ---------------------------------------------------------------------------
# style.css:3854 — the closed AI panel was only faded out (opacity +
# pointer-events): its controls stayed in the Tab order and the a11y tree,
# the FAB had no aria-expanded, and Escape did not close it.
# ---------------------------------------------------------------------------

AI_PANEL = PRELUDE + FAKE_DOM + r"""
const fab = new El('button'); fab.id = 'okapi-ai-fab'; DOC.body.appendChild(fab);
const panel = new El('div'); panel.id = 'okapi-ai-panel'; DOC.body.appendChild(panel);
const ctx = { document: DOC };
vm.createContext(ctx);
vm.runInContext(FN('ai-chat.js', '_setPanelOpen'), ctx);
ctx._setPanelOpen(false);
const closed = { inert: panel.inert, hidden: panel.getAttribute('aria-hidden'), expanded: fab.getAttribute('aria-expanded') };
ctx._setPanelOpen(true);
const open = { inert: panel.inert, hidden: panel.getAttribute('aria-hidden'), expanded: fab.getAttribute('aria-expanded'),
               cls: panel.classList.contains('okapi-ai-panel-open') };
OUT({ closed, open });
"""


def test_closed_ai_panel_is_inert_and_the_fab_reports_it():
    r = _node(AI_PANEL)
    assert r['closed'] == {'inert': True, 'hidden': 'true', 'expanded': 'false'}
    assert r['open'] == {'inert': False, 'hidden': None, 'expanded': 'true', 'cls': True}


def test_ai_panel_open_close_and_escape_go_through_the_same_switch():
    src = _src('ai-chat.js')
    api = src[src.index('open_() {'):src.index('toggleLangMenu() {')]
    assert api.count('_setPanelOpen(') == 2
    assert "classList.add('okapi-ai-panel-open')" not in src
    inject = src[src.index('function _injectWidget'):]
    inject = inject[:inject.index('// Move lang menu')]
    assert '_setPanelOpen(false)' in inject
    assert "e.key === 'Escape' && !e.defaultPrevented" in inject


# ---------------------------------------------------------------------------
# music.js:264 — a queue entry played on a click of its <li> only (no
# tabindex/role/key handler, native title=); the ✕ and transport buttons were
# glyph-only; loop/shuffle had no aria-pressed.
# ---------------------------------------------------------------------------

MUSIC_QUEUE = PRELUDE + FAKE_DOM + r"""
const list = new El('ul'); list.id = 'okapi-music-queue'; DOC.body.appendChild(list);
const loop = new El('button'); loop.id = 'okapi-music-loop'; DOC.body.appendChild(loop);
const shuf = new El('button'); shuf.id = 'okapi-music-shuffle'; DOC.body.appendChild(shuf);
const ctx = { document: DOC };
vm.createContext(ctx);
vm.runInContext('let queue = [{ title: "Lo-fi <beats>", kind: "video" }, { title: "Jazz", kind: "playlist" }], queueIndex = 1,' +
    ' loopMode = "one", shuffle = true;' +
    'function _t(k, f) { return f; }' +
    // _escape as in music.js (FN cannot scan its /'/ regex literal).
    'function _escape(x) { return String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;")' +
    '.replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/\x27/g, "&#39;"); }' +
    FN('music.js', '_renderQueue') + FN('music.js', '_renderModes'), ctx);
ctx._renderQueue(); ctx._renderModes();
OUT({ html: list.innerHTML, loopPressed: loop.getAttribute('aria-pressed'), loopLabel: loop.getAttribute('aria-label'),
      shufPressed: shuf.getAttribute('aria-pressed') });
"""


def test_music_queue_entries_and_toggles_are_keyboard_and_sr_ready():
    r = _node(MUSIC_QUEUE)
    html = r['html']
    assert ' title="' not in html
    assert html.count('class="okapi-music-q-title" role="button" tabindex="0"') == 2
    assert 'aria-label="Remove: Lo-fi &lt;beats&gt;"' in html
    assert html.count('aria-current="true"') == 1
    assert r['loopPressed'] == 'true' and r['loopLabel'] == 'Repeat: this item'
    assert r['shufPressed'] == 'true'


def test_music_queue_title_plays_on_enter_and_transport_is_named():
    src = _src('music.js')
    assert "const title = e.target.closest('.okapi-music-q-title');" in src
    assert "e.key !== 'Enter' && e.key !== ' '" in src
    for hid in ['okapi-music-close', 'okapi-music-add-btn', 'okapi-music-prev', 'okapi-music-play',
                'okapi-music-next', 'okapi-music-loop', 'okapi-music-shuffle']:
        tag = src[src.index(f'id="{hid}"'):]
        tag = tag[:tag.index('>')]
        assert 'aria-label="${_escape(_t(' in tag, hid


# ---------------------------------------------------------------------------
# templates/index.html:532 (also 502, 519, 501, 510) — #notify-me,
# #inf-timeout and #cdc-axis-turn sat beside a <span> with no <label>, and the
# Timeout / Interval <label>s had no for=, so the text neither toggled nor
# named its control.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('control', ['notify-me', 'inf-timeout', 'cdc-axis-turn', 'timeout', 'interval'])
def test_reading_setup_controls_have_a_label(control):
    html = (REPO / 'templates' / 'index.html').read_text(encoding='utf-8')
    assert html.count(f'<label for="{control}"') == 1


# ---------------------------------------------------------------------------
# Gaps found by the correctness review of this branch.
# ---------------------------------------------------------------------------

def test_saved_report_escapes_the_applied_calibration_name():
    src = (REPO / 'static' / 'script' / 'report.js').read_text(encoding='utf-8')
    assert '[Applied Calibration: ${calFile}]' not in src
    assert '[Applied Calibration: ${_escHtml(calFile)}]' in src


def test_console_item_delete_also_frees_the_point_chart():
    src = (REPO / 'static' / 'script' / 'data-handling.js').read_text(encoding='utf-8')
    body = src[src.index('async function confirmSwalItemDelete'):]
    body = body[:body.index('\n}\n')]
    assert 'config.pointChart.destroy()' in body


def test_turn_cal_table_shows_sentinels_as_a_dash():
    src = (REPO / 'static' / 'script' / 'data-handling.js').read_text(encoding='utf-8')
    assert "v === 'NONE' || v === ''" not in src


def test_settings_save_overlays_only_the_saved_keys():
    """A debounced music-volume save must not be rolled back by App Settings."""
    src = (REPO / 'static' / 'script' / 'init.js').read_text(encoding='utf-8')
    assert 'Object.assign(USER_SETTINGS, formValues, (saved && saved.settings)' not in src
    assert 'Object.keys(formValues).forEach' in src
