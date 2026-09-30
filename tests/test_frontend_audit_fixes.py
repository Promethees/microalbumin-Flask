"""Regression tests for the high-severity frontend audit findings (2026-09-30).

Behavioural checks run the real static scripts under `node` in a vm context
with the few browser globals they touch stubbed out (same approach as
test_device_menu_indicator.py). Where a fix is about *where* a call sits —
e.g. Shutdown only stopping a run after the user confirms — the test reads
the source, because driving a confirm() dialog headless proves nothing more.
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


# ---------------------------------------------------------------------------
# Long multi-source runs crashed the chart: Math.min(...arr) past ~120k values
# throws RangeError. arrayMin/arrayMax loop instead.
# ---------------------------------------------------------------------------

MINMAX = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const ctx = { console, document: {}, window: {} };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(process.env.EOK_JS, 'short-hands.js'), 'utf8'), ctx);
const big = Array.from({ length: 200000 }, (_, i) => (i * 7919) % 100003 - 5);
let spreadThrows = false;
try { Math.min(...big); } catch (e) { spreadThrows = true; }
process.stdout.write(JSON.stringify({
    spreadThrows,
    bigMin: ctx.arrayMin(big), bigMax: ctx.arrayMax(big),
    small: [ctx.arrayMin([3, -2, '7']), ctx.arrayMax([3, -2, '7'])],
    empty: [String(ctx.arrayMin([])), String(ctx.arrayMax([]))],
    nan: [String(ctx.arrayMin([1, NaN])), String(ctx.arrayMax([1, NaN]))],
}));
"""


def test_array_min_max_survive_a_long_multi_source_run():
    r = _node(MINMAX)
    # The harness array is big enough to break a spread — otherwise this
    # test would not be testing the bug.
    assert r['spreadThrows'] is True
    assert r['bigMin'] == -5 and r['bigMax'] == 100002 - 5
    # Same results as Math.min/Math.max on the edge cases.
    assert r['small'] == [-2, 7]
    assert r['empty'] == ['Infinity', '-Infinity']
    assert r['nan'] == ['NaN', 'NaN']


@pytest.mark.parametrize('name', ['data-display.js', 'generate-chart.js', 'calculate.js', 'cdc-logging.js', 'report.js'])
def test_chart_paths_no_longer_spread_data_into_math_min_max(name):
    assert not re.search(r'Math\.(min|max)\(\.\.\.', _src(name))


# ---------------------------------------------------------------------------
# A folder named "Lan's samples" could not be opened, renamed or deleted:
# data-path used the JS-string escape, which left a literal backslash.
# ---------------------------------------------------------------------------

FOLDERS = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const container = { innerHTML: '' };
const ctx = {
    console, AppState: { currentDirectory: '' },
    document: { getElementById: () => container },
    t: (k, fallback) => fallback,
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(process.env.EOK_JS, 'navigation.js'), 'utf8'), ctx);
const folders = JSON.parse(process.env.EOK_FOLDERS);
ctx._renderFolderList('x', folders);
const unhtml = s => s.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const paths = [...container.innerHTML.matchAll(/data-path="([^"]*)"/g)].map(m => unhtml(m[1]));
// The inline onclick handlers must still parse as JS once the HTML parser
// has decoded the attribute.
const handlers = [...container.innerHTML.matchAll(/onclick="([^"]*)"/g)].map(m => unhtml(m[1]));
const calls = [];
const hctx = {
    selectDataFolder: (n) => calls.push(n), renameDataFolder: (n) => calls.push(n),
    deleteDataFolder: (n) => calls.push(n),
    event: { stopPropagation() {} },
};
vm.createContext(hctx);
for (const h of handlers) {
    vm.runInContext(`(function(){ ${h} }).call({ dataset: {}, closest: () => ({ dataset: {} }) })`, hctx);
}
process.stdout.write(JSON.stringify({ paths, calls }));
"""


def test_folder_with_apostrophe_or_backslash_keeps_its_real_path():
    folders = [
        {'name': "Lan's samples", 'path': "/data/Lan's samples"},
        {'name': 'plain', 'path': 'C:\\Users\\Thông\\data\\plain'},
        {'name': 'a"b<c>&d', 'path': '/data/a"b<c>&d'},
    ]
    r = _node(FOLDERS, EOK_FOLDERS=folders)
    assert r['paths'] == [f['path'] for f in folders]
    # Each folder has select, rename and delete handlers; each receives the
    # real name back.
    assert r['calls'] == [f['name'] for f in folders for _ in range(3)]


# ---------------------------------------------------------------------------
# CSV metadata (# Concentration / # ConcenUnit / Measurement / Unit) went into
# innerHTML raw — a shared CSV could run script in the app origin.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('name, raw', [
    ('data-display.js', r'\$\{metaConcentration\}'),
    ('data-display.js', r'\$\{concenUnit\}'),
    ('data-display.js', r"'\$\{unit\}'"),
    ('data-handling.js', r'\$\{concenUnit\}'),
    ('data-handling.js', r'\$\{unitPrinted\}'),
    ('data-handling.js', r'\$\{AppState\.globalAnalysis\.meas\}'),
    ('init.js', r'\$\{AppState\.globalAnalysis\.meas_unit\}'),
    ('report.js', r'value="\$\{_concenAxisLabel'),
    # HTML sites only; derived_lines are plain text for the Excel export.
    ('report.js', r'\$\{_reportConcenUnit\([^)]*\)\}</strong>'),
])
def test_file_metadata_is_escaped_before_it_reaches_html(name, raw):
    assert not re.search(raw, _src(name)), f'{name} still interpolates {raw} unescaped'


# ---------------------------------------------------------------------------
# Shutdown → Cancel ended a live run: terminateScript() ran before confirm().
# ---------------------------------------------------------------------------

def test_shutdown_stops_a_run_only_after_the_user_confirms():
    src = _src('init.js')
    handler = src[src.index("getElementById('shutdown-btn')"):]
    handler = handler[:handler.index('\n});')]
    assert 'terminateScript' in handler
    assert handler.index('confirm(') < handler.index('terminateScript')


# ---------------------------------------------------------------------------
# Saving App Settings lit the default-mode button under the live layout and
# wrote a stale default_mode back.
# ---------------------------------------------------------------------------

def test_saving_settings_does_not_touch_the_mode_bar():
    src = _src('init.js')
    assert not re.search(r'formValues\.default_mode', src)


SAVE_SETTING = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const src = fs.readFileSync(path.join(process.env.EOK_JS, 'init.js'), 'utf8');
const fn = src.slice(src.indexOf('function saveUserSetting'), src.indexOf('\n}\n', src.indexOf('function saveUserSetting')) + 2);
const ctx = { USER_SETTINGS: { default_mode: 'kinetics' }, fetch: () => Promise.resolve() };
vm.createContext(ctx);
vm.runInContext(fn + "\nsaveUserSetting('default_mode', 'point');", ctx);
process.stdout.write(JSON.stringify(ctx.USER_SETTINGS));
"""


def test_save_user_setting_keeps_the_page_copy_current():
    assert _node(SAVE_SETTING) == {'default_mode': 'point'}


# ---------------------------------------------------------------------------
# Reloading mid-run left the page idle with Stop disabled.
# ---------------------------------------------------------------------------

RESYNC = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const src = fs.readFileSync(path.join(process.env.EOK_JS, 'cdc-logging.js'), 'utf8');
const grab = name => {
    const i = src.indexOf(name);
    return src.slice(i, src.indexOf('\n}\n', i) + 2);
};
const calls = [];
const status = JSON.parse(process.env.EOK_STATUS);
const ctx = {
    AppState: { scriptRunning: false },
    fetch: async () => ({ json: async () => status }),
    lockRunInputs: () => calls.push('lock'),
    enterRunningUI: (o) => calls.push(['enter', o]),
    $append: () => calls.push('log'),
    t: (k, f) => f,
    _terminationNoticeFired: true,
};
vm.createContext(ctx);
vm.runInContext('let _terminationNoticeFired = true;\n' + grab('async function resyncRunningSession'), ctx);
vm.runInContext('resyncRunningSession()', ctx).then(() => process.stdout.write(JSON.stringify(calls)));
"""


def test_reload_during_a_paused_timed_run_resyncs_the_controls():
    calls = _node(RESYNC, EOK_STATUS={'status': 'running', 'paused': True, 'manual': False})
    assert calls[0] == 'lock'
    assert calls[1] == ['enter', {'manual': False, 'intervalSec': None, 'paused': True, 'measureArmed': True}]


def test_reload_restores_the_session_interval():
    calls = _node(RESYNC, EOK_STATUS={'status': 'running', 'paused': False, 'manual': False, 'interval_sec': 30})
    assert calls[1][1]['intervalSec'] == 30


def test_reload_during_a_manual_run_restores_measure_now():
    calls = _node(RESYNC, EOK_STATUS={'status': 'running', 'paused': False, 'manual': True})
    assert calls[1][1]['manual'] is True


@pytest.mark.parametrize('status', ['not_running', 'ending', 'success', 'failure'])
def test_reload_with_no_run_going_changes_nothing(status):
    assert _node(RESYNC, EOK_STATUS={'status': status}) == []


def test_resync_is_wired_to_page_load_and_shares_the_start_path():
    src = _src('cdc-logging.js')
    # The load-time probe is read-only: it must not consume a finished run.
    assert "fetch('/check_status?peek=1')" in src
    assert "addEventListener('DOMContentLoaded', resyncRunningSession)" in src
    # A fresh start and a resync go through the same helper, so they can't drift.
    run = src[src.index('async function runScript'):]
    run = run[:run.index('\n}\n')]
    assert 'enterRunningUI(' in run
    assert 'setInterval(checkScriptStatus' not in run


# ---------------------------------------------------------------------------
# The 500 ms directory poll re-read every CSV header each tick and rewrote the
# file table, stealing keyboard focus.
# ---------------------------------------------------------------------------

POLL = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const tables = {};
const el = id => (tables[id] = tables[id] || { innerHTML: '', writes: 0 });
let fetches = 0;
const ctx = {
    console, window: {}, DELIMITER: '/', USER_SETTINGS: {},
    AppState: { currentDirectory: '/d', currentMeasurementMode: 'kinetics',
                fileMeta: { 'a.csv': { mtime: 1, display: '' }, 'b.csv': { mtime: 1, display: '' } },
                fileIdentity: {}, fileSortOrder: 'name-asc' },
    document: { getElementById: id => {
        const e = el(id);
        return new Proxy(e, { set(t, k, v) { if (k === 'innerHTML') t.writes++; t[k] = v; return true; } });
    } },
    fetch: async () => { fetches++; return { ok: true, json: async () => ({ headers: ['Timestamp', 'Value:1'] }) }; },
    t: (k, f) => f,
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(process.env.EOK_JS, 'short-hands.js'), 'utf8'), ctx);
vm.runInContext(fs.readFileSync(path.join(process.env.EOK_JS, 'navigation.js'), 'utf8'), ctx);
(async () => {
    const files = ['a.csv', 'b.csv'];
    await ctx.updateFileTable(files, false);
    const afterFirst = { fetches, writes: tables['file-table'].writes };
    await ctx.updateFileTable(files, false);   // idle poll tick: nothing changed
    const afterIdle = { fetches, writes: tables['file-table'].writes };
    ctx.AppState.fileMeta['b.csv'].mtime = 2;  // b.csv gained a row
    await ctx.updateFileTable(files, false);
    const afterChange = { fetches };
    process.stdout.write(JSON.stringify({ afterFirst, afterIdle, afterChange }));
})();
"""


def test_idle_directory_poll_neither_refetches_headers_nor_rewrites_the_table():
    r = _node(POLL)
    assert r['afterFirst']['fetches'] == 2
    assert r['afterFirst']['writes'] == 1
    # An idle tick costs no header requests and leaves the table (and the
    # keyboard focus inside it) alone.
    assert r['afterIdle'] == r['afterFirst']
    # Only the file whose mtime moved is read again.
    assert r['afterChange']['fetches'] == 3


def test_directory_poll_skips_a_hidden_tab():
    src = _src('index.js')
    assert 'if (!document.hidden) updateDirectory(AppState.currentDirectory, false);' in src
    assert "addEventListener('visibilitychange'" in src


def test_kinetics_analysis_table_escapes_the_unit():
    src = _src('data-display.js')
    body = src[src.index('function buildKineticsTableHtml'):]
    assert body.index('_escHtml(unitDisp)') < body.index('${unitDisp}')


INVALIDATE = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const table = { innerHTML: '' };
const ctx = { console, document: { getElementById: () => table }, t: (k, f) => f };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(process.env.EOK_JS, 'navigation.js'), 'utf8'), ctx);
const out = [];
out.push(ctx._setTableHtml('file-table', '<tr>a</tr>'));
out.push(ctx._setTableHtml('file-table', '<tr>a</tr>'));   // identical: skipped
table.innerHTML = '';                                       // a row removed by hand
ctx._invalidateTable('file-table');
out.push(ctx._setTableHtml('file-table', '<tr>a</tr>'));   // rewritten from state
process.stdout.write(JSON.stringify(out));
"""


def test_hand_edited_table_is_redrawn_after_invalidation():
    assert _node(INVALIDATE) == [True, False, True]


def test_failed_delete_and_rejected_select_invalidate_the_table():
    src = _src('data-handling.js')
    delete = src[src.index('const proceedDelete'):]
    delete = delete[:delete.index('};')]
    assert '_invalidateTable(' in delete
    select = src[src.index('async function selectFile'):]
    select = select[:select.index('\n}\n')]
    assert select.count('_invalidateTable(') == 2
