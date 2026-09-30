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
