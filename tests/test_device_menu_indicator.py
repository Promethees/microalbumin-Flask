"""The Device Controller's menu bar must mark the open entry on every firmware.

`deviceMenuOpenName()` in static/script/device-control.js answers the one
question the bar exists for — "which screen is the device on?" — and it has to
answer it for four firmware branches whose modes and entry names differ. It has
been wrong twice: CALIBRATION was missing from the mapping outright, so the bar
went blank the moment an operator opened Cal Factor, and the calibration screen
is named differently on the multi-channel build, so a fixed string would mark
nothing there.

That is a matrix, and a matrix rots. This runs the real function — the file is
evaluated in a Node VM with the DOM stubbed, not reimplemented here — against
every mode each branch can report. The expectations below are the firmware's:
keep them in step with each `_extend_menu_items()` / `_handle_menu_mode()` pair
the way Rule.md §2.35 requires of the button table.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / 'static' / 'script' / 'device-control.js'

# What each firmware branch puts in its menu (colorimeter._extend_menu_items)
# and announces in `caps` (serial_manager.CAPABILITIES).
BRANCHES = {
    'main': {
        'menu': ['Absorbance', 'Transmittance', 'Raw Sensor',
                 'Concentration', 'Cal Factor', 'About', 'Settings'],
        'caps': ['btn', 'state', 'inftoken', 'menu', 'conc', 'timing', 'calib'],
    },
    'open-plus': {
        'menu': ['Absorbance', 'Transmittance', 'Raw Sensor', 'Raw Count',
                 'Irradiance', 'Relative Unit', 'Concentration', 'Cal Factor',
                 'About', 'Settings'],
        'caps': ['btn', 'state', 'selsensor', 'inftoken', 'menu', 'conc',
                 'timing', 'calib'],
    },
    'open-extra': {
        'menu': ['Absorbance', 'Transmittance', 'Raw Sensor', 'Raw Count',
                 'Irradiance', 'Concentration', 'Sensor Cal', 'About', 'Settings'],
        'caps': ['btn', 'state', 'channels', 'selsensor', 'inftoken', 'menu',
                 'conc', 'timing', 'calib', 'calauto'],
    },
    'open-uv': {
        # No SETTINGS mode — the timing values live in configuration.json.
        'menu': ['Absorbance', 'Transmittance', 'Raw Sensor',
                 'Concentration', 'Cal Factor', 'About'],
        'caps': ['btn', 'state', 'uvchannel', 'uvchanset', 'inftoken', 'menu',
                 'conc', 'timing', 'calib'],
    },
}

# (branch, mode, msg, meas) -> the entry that mode IS, or None for "mark nothing".
# MENU is None on purpose: browsing is not having something open, and the keypad
# cursor (`menupos`) is the mark that applies there.
CASES = [
    ('main', 'MEASURE', '', 'Absorbance', 'Absorbance'),
    ('main', 'MENU', '', '', None),
    ('main', 'SETTINGS', '', '', 'Settings'),
    ('main', 'CONCENTRATION', '', '', 'Concentration'),
    ('main', 'CALIBRATION', '', '', 'Cal Factor'),
    ('main', 'MESSAGE', 'About', '', 'About'),
    ('main', 'MESSAGE', 'Error', '', None),
    ('main', 'ABORT', 'Abort', '', None),

    ('open-plus', 'MEASURE', '', 'Relative Unit', 'Relative Unit'),
    ('open-plus', 'MENU', '', '', None),
    ('open-plus', 'SETTINGS', '', '', 'Settings'),
    ('open-plus', 'CONCENTRATION', '', '', 'Concentration'),
    ('open-plus', 'CALIBRATION', '', '', 'Cal Factor'),
    ('open-plus', 'MESSAGE', 'About', '', 'About'),
    ('open-plus', 'MESSAGE', 'Error', '', None),
    ('open-plus', 'ABORT', 'Abort', '', None),

    ('open-extra', 'MEASURE', '', 'Irradiance', 'Irradiance'),
    ('open-extra', 'MENU', '', '', None),
    ('open-extra', 'SETTINGS', '', '', 'Settings'),
    ('open-extra', 'CONCENTRATION', '', '', 'Concentration'),
    # The one that cannot be a fixed string: this build calls it Sensor Cal.
    ('open-extra', 'CALIBRATION', '', '', 'Sensor Cal'),
    ('open-extra', 'MESSAGE', 'About', '', 'About'),
    ('open-extra', 'MESSAGE', 'Error', '', None),
    ('open-extra', 'ABORT', 'Abort', '', None),

    ('open-uv', 'MEASURE', '', 'Absorbance', 'Absorbance'),
    ('open-uv', 'MENU', '', '', None),
    ('open-uv', 'CONCENTRATION', '', '', 'Concentration'),
    ('open-uv', 'CALIBRATION', '', '', 'Cal Factor'),
    ('open-uv', 'MESSAGE', 'About', '', 'About'),
    ('open-uv', 'MESSAGE', 'Error', '', None),
    ('open-uv', 'ABORT', 'Abort', '', None),
]

# `deviceMenuItems` is a top-level `let`, so it lives in the script's lexical
# scope rather than on the context object and has to be assigned from inside the
# VM. Getting that wrong makes every non-MEASURE case look broken.
HARNESS = r"""
const fs = require('fs'), vm = require('vm');
const ctx = {
    document: { addEventListener() {}, getElementById: () => null,
                querySelectorAll: () => [] },
    window: { addEventListener() {} },
    t: (key, fallback) => fallback,
    console,
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.env.EOK_SCRIPT, 'utf8'), ctx);

const setMenu = value => {
    ctx.__menu = value;
    vm.runInContext('deviceMenuItems = __menu;', ctx);
};

const results = [];
for (const probe of JSON.parse(process.env.EOK_PROBES)) {
    setMenu(probe.menu);
    results.push(ctx.deviceMenuOpenName(probe.state));
}
process.stdout.write(JSON.stringify(results));
"""


def _run(probes):
    """Ask the real deviceMenuOpenName() what it would mark, for each probe.

    Passed through the environment and `node -e` rather than a temp file: this
    is a check on a source file, and it has no business leaving anything behind
    in the tree it is checking.
    """
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    out = subprocess.run(
        [node, '-e', HARNESS],
        env={**os.environ, 'EOK_SCRIPT': str(SCRIPT), 'EOK_PROBES': json.dumps(probes)},
        capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def test_open_entry_is_marked_on_every_firmware():
    probes = [
        {'menu': BRANCHES[branch]['menu'],
         'state': {'mode': mode, 'msg': msg, 'meas': meas,
                   'caps': BRANCHES[branch]['caps']}}
        for branch, mode, msg, meas, _ in CASES
    ]
    got = _run(probes)
    wrong = [
        f'{branch}/{mode}{"/" + msg if msg else ""}: want {want!r}, got {actual!r}'
        for (branch, mode, msg, _meas, want), actual in zip(CASES, got)
        if actual != want
    ]
    assert not wrong, 'menu bar marks the wrong entry:\n  ' + '\n  '.join(wrong)


def test_firmware_without_the_msg_field_marks_nothing_on_a_message():
    """Older builds send no `msg`. About is unknowable then, and a bar that
    guessed would mark About over an error screen — worse than marking nothing.
    """
    probe = {'menu': BRANCHES['open-uv']['menu'],
             'state': {'mode': 'MESSAGE', 'meas': '',
                       'caps': BRANCHES['open-uv']['caps']}}
    assert _run([probe]) == [None]


def test_nothing_is_marked_before_the_menu_has_been_fetched():
    """The list arrives on its own request, one per connection. Until it does
    there is nothing to match against, and a name matched against nothing must
    not become a mark on a chip that is not there yet."""
    probes = [{'menu': None,
               'state': {'mode': mode, 'msg': 'About', 'meas': 'Absorbance',
                         'caps': BRANCHES['open-uv']['caps']}}
              for mode in ('CALIBRATION', 'CONCENTRATION', 'SETTINGS', 'MESSAGE')]
    assert _run(probes) == [None, None, None, None]


# ── the panel's buttons have to survive the cascade, not just be written ────
# deviceMenuOpenName() was returning the right entry and the class was going on
# the right chip — and the bar still showed nothing, because every property the
# marks set (border, color, font-weight, box-shadow) is also set by the blanket
# `button:not(...)` rule, which out-specifies them. `:not(.x)` carries its
# argument's specificity and there are ten of them, so that rule is (0,10,1) —
# not the (0,3,1) the stylesheet's comments claimed in two places. A correct
# mapping into an invisible mark is the same bug to an operator.
#
# The keypad was losing the same argument: its idle-key rule is written to keep a
# no-effect key looking like part of the keypad, and the blanket :disabled rule
# (0,11,1) painted #eef1f2 on #8a959b over it — light-theme literals, in dark
# mode. So this checks the whole panel, not just the two marks.

STYLE = REPO / 'static' / 'style.css'
BLANKET_PREFIX = 'button:not(.swal2-confirm)'

# Subjects that are actually <button> elements. `devctl-btn-glyph` /
# `devctl-btn-fn` / `devctl-btn-fn-track` are spans INSIDE a key, which
# `button:not(...)` never matches — hence `--modifier` only, not any suffix.
BUTTON_SUBJECT = re.compile(
    r'^[.#][\w-]*(devctl-btn|devctl-menu-item)(--[\w-]+)?(:[\w-]+)*$')

# What the blanket button rule and its :disabled sibling declare between them.
BLANKET_PROPS = {
    'padding', 'font-family', 'font-weight', 'font-size', 'border-radius',
    'border', 'border-color', 'cursor', 'transition', 'display', 'align-items',
    'justify-content', 'gap', 'box-shadow', 'background', 'background-color',
    'color', 'white-space', 'overflow', 'text-overflow', 'opacity',
}


def _specificity(selector):
    """(ids, classes) for one selector — enough to compare against the blanket.

    `:not(...)` contributes its argument's specificity rather than one of its
    own, which is the whole reason that rule is as heavy as it is.
    """
    selector = re.sub(r'::[a-z-]+', '', selector)
    ids = len(re.findall(r'#[\w-]+', selector))
    classes = (len(re.findall(r'\.[\w-]+', selector))
               + len(re.findall(r':(?!not\()[a-z-]+', selector)))
    return ids, classes


def _rules():
    css = STYLE.read_text(encoding='utf-8')
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    for match in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        head = match.group(1).strip()
        if not head or head.startswith('@'):
            continue
        props = {p.split(':')[0].strip() for p in match.group(2).split(';') if ':' in p}
        for selector in (s.strip() for s in head.split(',')):
            if selector:
                yield selector, props


def test_the_blanket_button_rule_is_still_as_heavy_as_we_think():
    """If someone trims those :not()s, the rules below are over-scoped, not
    broken — but the reasoning in this file and in style.css would be stale."""
    blanket = [_specificity(sel) for sel, _ in _rules()
               if sel.startswith(BLANKET_PREFIX)]
    assert blanket, 'the blanket button rule moved — this check needs updating'
    assert max(blanket)[1] >= 10, (
        f'the blanket button rule is lighter than (0,10,1) now: {max(blanket)}')


def test_every_panel_button_rule_out_specifies_the_blanket_rule():
    blanket = [(_specificity(sel), props) for sel, props in _rules()
               if sel.startswith(BLANKET_PREFIX)]
    heaviest = max(spec for spec, _ in blanket)

    checked = 0
    problems = []
    for selector, props in _rules():
        subject = selector.split()[-1]
        if not BUTTON_SUBJECT.match(subject):
            continue
        shadowed = props & BLANKET_PROPS
        if not shadowed:
            continue
        checked += 1
        spec = _specificity(selector)
        if spec <= heaviest:
            problems.append(
                f'{selector} is {spec} against the blanket rule {heaviest}; '
                f'it would lose {", ".join(sorted(shadowed))}')

    assert checked, 'no panel button rules found — the selectors moved'
    assert not problems, ('written but never seen:\n  ' + '\n  '.join(problems))
