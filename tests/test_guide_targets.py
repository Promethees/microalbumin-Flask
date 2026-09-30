"""Every static guide target must exist in the app's markup (work-list A9 / B7).

A guide step whose selector matches nothing waits 3 s, then skips — or, on the
last step, used to leave the overlay up. Targets are collected from
guide_training.json and from the step dicts / ID lists in src/ai_assistant.py,
and each simple selector inside them (#id, .class, [attr="value"]) is looked up
in templates/*.html and static/script/*.js. Ids that only exist at runtime are
allow-listed by pattern.
"""
import glob
import json
import os
import re

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Elements that are created at runtime with a computed id/attribute, or
# rendered by a template loop, so the literal never appears in the source.
DYNAMIC_PATTERNS = [
    r"^#con-value-read-source-\d+$",
    r"^#plot-button-source-\d+$",
    r"^#swal-",                 # SweetAlert dialog fields built in JS strings
    r"^\.swal2-",               # SweetAlert's own classes
    r'^\[data-mode="(kinetics|point|calibrate|report)"\]$',   # mode buttons: {% for mode %}
]


def _corpus():
    parts = []
    for pattern in ("templates/*.html", "templates/**/*.html", "static/script/*.js"):
        for path in glob.glob(os.path.join(ROOT, pattern), recursive=True):
            with open(path, encoding="utf-8") as f:
                parts.append(f.read())
    return "\n".join(parts)


CORPUS = _corpus()


def _guide_targets():
    with open(os.path.join(ROOT, "guide_training.json"), encoding="utf-8") as f:
        data = json.load(f)
    for ex in data["examples"]:
        for st in ex.get("steps", []):
            yield ex["id"], st["target"]


def _code_targets():
    with open(os.path.join(ROOT, "src", "ai_assistant.py"), encoding="utf-8") as f:
        src = f.read()
    for m in re.finditer(r'"target"\s*:\s*"((?:[^"\\]|\\.)+)"', src):
        yield "ai_assistant.py", m.group(1).encode().decode("unicode_escape")
    # IDs advertised to the model (tool description + prompt examples).
    for m in re.finditer(r"(?<![\w#&])#([a-z][a-z0-9]*(?:-[a-z0-9]+)+)\b", src):
        yield "ai_assistant.py", "#" + m.group(1)


def _simple_selectors(selector):
    for compound in selector.split():
        for piece in re.findall(r'#[\w-]+|\.[\w-]+|\[[^\]]+\]', compound):
            yield piece


def _exists(piece):
    if any(re.search(p, piece) for p in DYNAMIC_PATTERNS):
        return True
    if piece.startswith("#"):
        name = re.escape(piece[1:])
        return re.search(r"""(\bid\s*[=:]\s*|\.id\s*=\s*|setAttribute\(\s*['"]id['"]\s*,\s*)\\?['"`]""" + name + r"""\\?['"`]""", CORPUS) is not None
    if piece.startswith("."):
        name = re.escape(piece[1:])
        return re.search(r"""class(Name)?\s*[=:]?\s*\\?['"`][^'"`]*\b""" + name + r"""\b|classList\.add\([^)]*['"]""" + name + r"""['"]""", CORPUS) is not None
    attr = re.match(r'\[([\w-]+)\s*=\s*"(.*)"\]$', piece)
    if attr:
        key, val = attr.group(1), attr.group(2)
        return (key + '="' + val + '"') in CORPUS or (key + "='" + val + "'") in CORPUS \
            or (key + '=\\"' + val + '\\"') in CORPUS
    return piece[1:-1] in CORPUS


# Placeholders in the tool schema's prose, not real targets.
NOT_TARGETS = {"#element-id"}

TARGETS = sorted((s, t) for s, t in set(_guide_targets()) | set(_code_targets()) if t not in NOT_TARGETS)


@pytest.mark.parametrize("piece", ["#save-dir-label", "#definitely-not-an-element", '[onclick="clearReportSubject()"]'])
def test_resolver_rejects_known_dead_targets(piece):
    assert not _exists(piece)


def test_targets_were_collected():
    assert len(TARGETS) > 30


@pytest.mark.parametrize("source, target", TARGETS, ids=[f"{s}::{t}" for s, t in TARGETS])
def test_guide_target_exists_in_markup(source, target):
    missing = [p for p in _simple_selectors(target) if not _exists(p)]
    assert not missing, f"{source}: {target!r} — not found in templates/JS: {missing}"
