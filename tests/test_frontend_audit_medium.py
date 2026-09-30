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
        capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def _src(name):
    return (JS / name).read_text(encoding='utf-8')


# Harness prelude: FN(file, name) returns the source of one top-level function
# (brace-matched, string/template/comment aware enough for this codebase).
PRELUDE = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
function FN(file, name) {
    const src = fs.readFileSync(path.join(process.env.EOK_JS, file), 'utf8');
    const re = new RegExp('^(async\\s+)?function\\s+' + name + '\\s*\\(', 'm');
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
