"""Regression tests for the follow-up decisions on the 2026-09-30 frontend audit.

1  a reload no longer stops a running reading (AppState.reset)
2  point / Turn calibration tables accept a negative Value
3  the preview's curve math uses the server's domain (math_ops.evaluate_curve)
4  AI chat chrome follows the UI language
5  confirm / destructive dialog buttons clear WCAG AA contrast
6  every source's kinetics analysis goes in one request
7  the file editor escapes metadata keys, column names and JSON paths
"""
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
JS = REPO / 'static' / 'script'
LANGS = ['en', 'vi', 'zh', 'fr', 'ja', 'ru', 'ko']


def _src(name):
    return (JS / name).read_text(encoding='utf-8')


def _node(harness, **env):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    out = subprocess.run(
        [node, '-e', harness],
        env={**os.environ, 'EOK_JS': str(JS), **{k: json.dumps(v) for k, v in env.items()}},
        capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


# ---------------------------------------------------------------------------
# 1. A page load must not stop a run it did not start.
# ---------------------------------------------------------------------------

RESET = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const src = fs.readFileSync(path.join(process.env.EOK_JS, 'index.js'), 'utf8');
const start = src.indexOf('reset: function () {');
let depth = 0, end = start;
for (let i = src.indexOf('{', start); i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
}
const body = src.slice(start + 'reset: '.length, end);
const out = [];
const ctx = { terminateScript: () => out.push('terminate'), DATA_ROOT: '/d', modeDiv: undefined };
vm.createContext(ctx);
vm.runInContext('var reset = ' + body + ';', ctx);
for (const running of JSON.parse(process.env.EOK_RUNNING)) {
    const state = { scriptRunning: running, chartInstances: {} };
    out.length = 0;
    ctx.reset.call(state);
    out.push(state.scriptRunning);
    process.stdout.write('');
    ctx.__r = (ctx.__r || []).concat([out.slice()]);
}
process.stdout.write(JSON.stringify(ctx.__r));
"""


def test_page_load_reset_leaves_a_running_logger_alone():
    idle, driving = _node(RESET, EOK_RUNNING=[False, True])
    # Page load: this tab is not driving a run, so nothing is stopped.
    assert idle == [False]
    # Server went down while this tab was driving a run: stop it, as before.
    assert driving == ['terminate', False]


# ---------------------------------------------------------------------------
# 2. Negative Value in the point / Turn calibration tables.
# ---------------------------------------------------------------------------

def test_point_calibration_validators_accept_a_negative_value():
    from routes.file_routes import _SCHEMA_VALIDATORS
    from file_path import CSV_SCHEMA_POINT_CAL, CSV_SCHEMA_POINT_CAL_TURN
    point = _SCHEMA_VALIDATORS[CSV_SCHEMA_POINT_CAL]['data']
    turn = _SCHEMA_VALIDATORS[CSV_SCHEMA_POINT_CAL_TURN]['data']
    assert re.match(point, '5,-0.2,30')
    assert re.match(turn, '5,-0.2')
    # Concentration and TimePoint stay non-negative.
    assert not re.match(point, '-5,0.2,30')
    assert not re.match(point, '5,0.2,-30')
    assert not re.match(turn, '-5,0.2')


def test_editor_point_calibration_patterns_accept_a_negative_value():
    src = _src('edit-file.js')
    pats = re.findall(r"data: (/\^\\s\*\(NONE\|\\d\+\|\\d\+\\\.\\d\+\)\\s\*,\\s\*\(NONE\|-\?.*?\$/),", src)
    assert len(pats) == 2, 'both point-cal editor patterns must allow -? in Value'


# ---------------------------------------------------------------------------
# 3. computeFit (client preview) matches math_ops.evaluate_curve.
# ---------------------------------------------------------------------------

FIT = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const ctx = { console, document: { getElementById: () => ({ value: 'maxRate' }) } };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(process.env.EOK_JS, 'calculate.js'), 'utf8'), ctx);
const out = [];
for (const [type, coef, x] of JSON.parse(process.env.EOK_CASES)) {
    try { out.push(ctx.computeFit(x, type, coef)); } catch (e) { out.push('ERR'); }
}
process.stdout.write(JSON.stringify(out));
"""


def test_preview_curve_domain_matches_the_server():
    from math_ops import evaluate_curve
    log = {'a': 2.0, 'b': 3.0, 'c': 1.0}
    mm = {'VMax': 1.0, 'Km': 0.5}
    cases = [('logarithmic', log, x) for x in (-4.0, -3.0, -2.5, -1.0, 0.0, 0.5, 5.0)]
    cases += [('michaelis-menten', mm, x) for x in (-0.5, 0.0, 0.5, 1.0, 1.5)]
    got = _node(FIT, EOK_CASES=cases)
    for (type_, coef, x), client in zip(cases, got):
        algo = 'Michaelis-Menten' if type_ == 'michaelis-menten' else type_
        try:
            server = evaluate_curve(algo, coef, x)
        except ValueError:
            server = 'ERR'
        if server == 'ERR' or client == 'ERR':
            assert client == server, f'{type_} x={x}: client {client!r}, server {server!r}'
        else:
            assert math.isclose(client, server, rel_tol=1e-12), f'{type_} x={x}'


# ---------------------------------------------------------------------------
# 4. AI chat chrome is translated; answers keep following AI.activeLang.
# ---------------------------------------------------------------------------

AI_CHROME_KEYS = ['ai.fab_label', 'ai.input_placeholder', 'ai.status_ready', 'ai.status_not_activated',
                  'ai.token_placeholder', 'ai.activate', 'ai.activating', 'ai.activation_failed', 'ai.get_token']


def test_ai_chat_chrome_keys_exist_in_every_catalog():
    cmds = re.findall(r"cmd: '/([a-z-]+)'", _src('ai-chat.js'))
    assert len(cmds) >= 20
    keys = AI_CHROME_KEYS + ['ai.cmd.' + c.replace('-', '_') for c in cmds]
    en = json.loads((REPO / 'ui_translations' / 'en.json').read_text(encoding='utf-8'))
    for lang in LANGS:
        cat = json.loads((REPO / 'ui_translations' / f'{lang}.json').read_text(encoding='utf-8'))
        missing = [k for k in keys if k not in cat]
        assert not missing, f'{lang} lacks {missing}'
        if lang != 'en':
            same = [k for k in keys if cat[k] == en[k]]
            assert not same, f'{lang} left untranslated: {same}'


def test_ai_chat_chrome_goes_through_t():
    src = _src('ai-chat.js')
    for literal in ['>AI Assistant</span>', 'placeholder="Ask anything', '&#10003; AI ready<',
                    '&#9888; Not activated<', 'placeholder="Paste Easy OKAPI token', '()">Activate</button>',
                    "textContent = 'Activating…'", "textContent = 'Activate'"]:
        assert literal not in src, literal
    assert "_esc(_cmdDesc(c))" in src


# ---------------------------------------------------------------------------
# 5. Dialog button contrast (WCAG 1.4.3, 4.5:1).
# ---------------------------------------------------------------------------

def _lum(hexcol):
    h = hexcol.lstrip('#')
    ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def _ratio(a, b):
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _tokens(block_selector):
    css = (REPO / 'static' / 'style.css').read_text(encoding='utf-8')
    start = css.index(block_selector + ' {')
    block = css[start:css.index('\n}', start)]
    return dict(re.findall(r'--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;', block))


@pytest.mark.parametrize('block', [':root', 'body.dark'])
def test_dialog_buttons_clear_aa_contrast(block):
    tok = _tokens(block)
    assert _ratio(tok['on-accent'], tok['accent']) >= 4.5
    assert _ratio('#ffffff', tok['danger-fill']) >= 4.5


def test_dialog_buttons_use_the_contrast_tokens_and_keep_their_fill_on_hover():
    css = (REPO / 'static' / 'style.css').read_text(encoding='utf-8')
    confirm = css[css.index('body:not(.ui-classic) .swal2-popup .swal2-styled.swal2-confirm {'):]
    assert 'color: var(--on-accent) !important;' in confirm[:300]
    hover = css[css.index('.swal2-styled.swal2-confirm:hover:enabled {'):]
    assert 'background: var(--accent) !important;' in hover[:300]
    assert 'filter: brightness(1.12)' not in css


# ---------------------------------------------------------------------------
# 6. One request for every source's kinetics analysis.
# ---------------------------------------------------------------------------

def test_batch_kinetics_route_matches_the_single_route(client):
    x = list(range(20))
    ys = [[0.1 + 0.01 * i for i in x], [0.2 + 0.02 * i for i in x]]
    batch = client.post('/calculate_kinetics_quantities_batch',
                        json={'XColumn': x, 'YColumns': ys, 'window_size': 4}).get_json()
    assert batch['status'] == 'success'
    for y, got in zip(ys, batch['results']):
        single = client.post('/calculate_kinetics_quantities',
                             json={'XColumn': x, 'YColumn': y, 'window_size': 4}).get_json()
        assert got == single['result']


def test_batch_kinetics_route_isolates_a_failing_source(client, monkeypatch):
    import routes.math_routes as mr
    real = mr.calculate_kinetics_quantities

    def flaky(x, y, w):
        if y and y[0] == 'boom':
            raise ValueError('bad column')
        return real(x, y, w)
    monkeypatch.setattr(mr, 'calculate_kinetics_quantities', flaky)
    x = list(range(20))
    body = client.post('/calculate_kinetics_quantities_batch',
                       json={'XColumn': x, 'YColumns': [[0.1] * 20, ['boom'] * 20], 'window_size': 4}).get_json()
    assert body['status'] == 'success'
    assert body['results'][0] is not None
    assert body['results'][1] is None


def test_chart_render_uses_one_request_for_every_source():
    src = _src('data-display.js')
    # No per-source loop of single requests remains; a single-source file
    # still uses the single route.
    assert not re.search(r'map\(\w+ => calculateKineticsQuantities\(', src)
    assert 'allGroups.allYColumn[i], getValInt' not in src
    assert src.count('calculateKineticsQuantitiesBatch(') == 3


# ---------------------------------------------------------------------------
# 7. The editor's table and JSON modes escape file-derived names.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('raw', [
    r'<td class="metadata-key">\$\{key\}</td>',
    r'data-meta-key="\$\{key\}"',
    r"moveColumn\('\$\{col\}'",
    r"removeColumn\('\$\{col\}'\)",
    r'data-col="\$\{columnName\}"',
    r'data-path="\$\{(fullPath|itemPath|pathPrefix)\}"',
    r'margin-top:6px;">\$\{label\}</label>',
])
def test_editor_escapes_file_derived_names(raw):
    assert not re.search(raw, _src('edit-file.js')), raw


def test_editor_escape_helper_covers_quotes():
    src = _src('edit-file.js')
    helper = src[src.index('function escapeHtml(text)'):]
    helper = helper[:helper.index('\n    }')]
    assert "&quot;" in helper and "&#39;" in helper
