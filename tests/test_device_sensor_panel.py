"""The Sensor settings row must notice a gain turned on the device.

The keyed settings (`SENSCFG?`) cost a serial round trip, so the panel caches
them — and the first version cached BOTH halves of the comparison. The running
half then went stale the moment the operator turned the gain on the device: the
row kept showing the values it had read once, they still matched the file, and
Save stayed greyed out however many times the gain was changed.

The other panels do not have this failure because they cache only the *saved*
half and read the running half from the 1.5 s poll. STATE carries `gains`,
`itimes` and `chans` on every poll, so the change is already on the wire; this
checks it is used as the signal to re-read, and that idle polls do not.

Runs the real device-control.js in a Node VM with the DOM stubbed, so the thing
under test is the shipped file rather than a description of it.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / 'static' / 'script' / 'device-control.js'

HARNESS = r"""
const fs = require('fs'), vm = require('vm');
const els = {};
const el = id => els[id] || (els[id] = {
    id, disabled: null, textContent: '',
    classList: { add() {}, remove() {}, toggle() {} },
    setAttribute() {}, addEventListener() {}, appendChild() {}, innerHTML: '',
});

const plan = JSON.parse(process.env.EOK_PLAN);
let running = plan.running.shift();
let fetches = 0;

const ctx = {
    document: { addEventListener() {}, getElementById: el, querySelectorAll: () => [] },
    window: { addEventListener() {} },
    console, Map, Object, JSON, Promise, RegExp,
    setTimeout, clearTimeout, setInterval, clearInterval,
    t: (key, fallback) => fallback,
    fetch: async () => {
        fetches++;
        return { status: 200, json: async () => ({
            status: 'success', drive: '/Volumes/CIRCUITPY',
            saved: plan.saved, settings: running }) };
    },
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.env.EOK_SCRIPT, 'utf8'), ctx);

const seen = {};
vm.runInContext(`
  $disabled = (id, v) => { __seen.disabled = v; };
  $text = (id, v) => { __seen.text = v; };
  drawSavedNote = (id, u) => { __seen.unsaved = u; };
`, Object.assign(ctx, { __seen: seen }));

(async () => {
    const results = [];
    for (const step of plan.steps) {
        if (step.running !== undefined) running = step.running;
        const state = { mode: 'MEASURE', caps: ['senscfg'], chans: step.chans,
                        gains: step.gains, itimes: step.itimes };
        ctx.deviceState = state;
        const before = fetches;
        ctx.renderDeviceSensorConfig(state);
        await new Promise(r => setTimeout(r, 5));
        results.push({ disabled: seen.disabled, unsaved: seen.unsaved,
                       text: seen.text, fetched: fetches - before });
    }
    process.stdout.write(JSON.stringify(results));
})();
"""

MAX = {'gain_sensor_0': 'max', 'gain_sensor_1': 'max',
       'itime_sensor_0': '500ms', 'itime_sensor_1': '500ms'}
LOW = {'gain_sensor_0': 'low', 'gain_sensor_1': 'low',
       'itime_sensor_0': '500ms', 'itime_sensor_1': '500ms'}


def _run(plan):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    out = subprocess.run(
        [node, '-e', HARNESS],
        env={**os.environ, 'EOK_SCRIPT': str(SCRIPT), 'EOK_PLAN': json.dumps(plan)},
        capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def test_save_lights_up_when_the_gain_is_turned_on_the_device():
    """The bug, exactly as reported: the file says max, the operator turns the
    gain down to low, and Save has to become available."""
    steps = _run({
        'saved': MAX,
        'running': [MAX],
        'steps': [
            # Settled on the saved values: nothing to save.
            {'chans': [0, 1], 'gains': ['max', 'max'], 'itimes': ['500ms', '500ms']},
            {'chans': [0, 1], 'gains': ['max', 'max'], 'itimes': ['500ms', '500ms']},
            # The operator turns the gain down. STATE says so on this very poll.
            {'chans': [0, 1], 'gains': ['low', 'low'], 'itimes': ['500ms', '500ms'],
             'running': LOW},
            # …and the re-read has landed by the next one.
            {'chans': [0, 1], 'gains': ['low', 'low'], 'itimes': ['500ms', '500ms']},
        ],
    })
    first, settled, turning, turned = steps

    # First sight draws nothing: the read is in flight and there is no cache to
    # show yet. It is the tick after that has to be right.
    assert first == {'fetched': 1}
    assert settled['disabled'] is True, 'nothing to save yet'
    assert settled['unsaved'] is False

    # The tick the change arrives on still draws the OLD values rather than
    # blanking the row, so only the tick after it is asserted on.
    assert turning['fetched'] == 1, 'a change in STATE must trigger the re-read'
    assert turning['disabled'] is True, 'the stale row is drawn, not blanked'

    assert turned['unsaved'] is True
    assert turned['disabled'] is False, 'Save must be available after a gain change'
    assert 'low' in turned['text']


def test_idle_polls_do_not_re_read_the_settings():
    """The re-read is a serial round trip. It has to cost nothing while the
    operator is not touching anything — the poll comes round every 1.5 s."""
    steps = _run({
        'saved': MAX,
        'running': [MAX],
        'steps': [{'chans': [0, 1], 'gains': ['max', 'max'],
                   'itimes': ['500ms', '500ms']} for _ in range(5)],
    })
    assert steps[0]['fetched'] == 1, 'the first sight reads once'
    assert sum(step['fetched'] for step in steps[1:]) == 0, \
        'an unchanged device must not be re-read'


def test_a_channel_change_also_re_reads():
    """`chans` moving reorders which sensors are reported at all, so the keyed
    settings it was holding describe a different set."""
    steps = _run({
        'saved': MAX,
        'running': [MAX],
        'steps': [
            {'chans': [0, 1], 'gains': ['max', 'max'], 'itimes': ['500ms', '500ms']},
            {'chans': [0], 'gains': ['max'], 'itimes': ['500ms']},
        ],
    })
    assert steps[1]['fetched'] == 1
