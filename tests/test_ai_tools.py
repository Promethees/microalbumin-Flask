"""Tests for the AI assistant's tool executor (src/ai_assistant._run_tool).

Focus: the LLM-supplied filename/mode of `read_calibration_file` must stay
confined to the `json/` root — a crafted `..` must not read sibling files in
the data root (e.g. activation.json, .env).
"""
import json
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import ai_assistant  # noqa: E402
import state  # noqa: E402


@pytest.fixture
def json_root(tmp_path, monkeypatch):
    """Redirect json_root_path to an isolated tree with kinetics/point subdirs.

    _run_tool and validate_in_json_root both read state.json_root_path at call
    time, so monkeypatching it here is sufficient.
    """
    root = tmp_path / "json"
    (root / "kinetics").mkdir(parents=True)
    (root / "point").mkdir(parents=True)
    monkeypatch.setattr(state, 'json_root_path', str(root))
    # A legitimate calibration file inside json/kinetics/.
    (root / "kinetics" / "curve.json").write_text(
        json.dumps({"algo": "linear", "coef": [1, 0]}), encoding="utf-8")
    # A secret sibling in the data root, one level above json/.
    (tmp_path / "activation.json").write_text(
        json.dumps({"license_token": "SECRET"}), encoding="utf-8")
    return tmp_path


def _read_cal(filename, mode):
    return json.loads(ai_assistant._run_tool(
        "read_calibration_file", {"filename": filename, "mode": mode}))


def test_reads_legitimate_calibration_file(json_root):
    out = _read_cal("curve.json", "kinetics")
    assert out.get("algo") == "linear"


def test_filename_traversal_is_blocked(json_root):
    out = _read_cal("../activation.json", "kinetics")
    assert "error" in out
    assert "SECRET" not in json.dumps(out)


def test_mode_traversal_is_blocked(json_root):
    # mode="..", filename="activation.json" would resolve to json/../activation.json.
    out = _read_cal("activation.json", "..")
    assert "error" in out
    assert "SECRET" not in json.dumps(out)


def test_absolute_path_filename_is_blocked(json_root):
    secret = str(json_root / "activation.json")
    out = _read_cal(secret, "kinetics")
    assert "error" in out
    assert "SECRET" not in json.dumps(out)


def test_unknown_mode_rejected(json_root):
    out = _read_cal("curve.json", "kinetics/../../..")
    assert "error" in out


# ── Tool schemas carry no hard enum (Groq rejects out-of-enum args) ───────────

def _tool(name):
    return next(t["function"] for t in ai_assistant.TOOLS if t["function"]["name"] == name)


def test_tool_schemas_have_no_enum_constraints():
    # An `enum` in a tool schema makes Groq 400 (tool_use_failed) when the model
    # picks any other value; we validate permissively in _run_tool instead.
    import json as _json
    assert '"enum"' not in _json.dumps(ai_assistant.TOOLS)


# ── get_help_topic degrades gracefully instead of erroring ───────────────────

def _help(topic):
    return json.loads(ai_assistant._run_tool("get_help_topic", {"topic": topic}))


def test_help_known_topic():
    assert "modes" in _help("measurement_modes")["content"].lower()


def test_help_unknown_topic_falls_back_to_overview():
    out = _help("about")   # not a known key — the exact screenshot-2 failure
    assert out["topic"] == "overview"
    assert "Easy OKAPI" in out["content"]


def test_help_topic_normalized_and_fuzzy_matched():
    # "Standard Curve" → standard_curve (case/space normalized).
    assert _help("Standard Curve")["topic"] == "standard_curve"


# ── trigger_custom_steps normalizes an out-of-range position ─────────────────

def test_custom_steps_bad_position_defaults_to_bottom():
    out = json.loads(ai_assistant._run_tool("trigger_custom_steps", {
        "steps": [{"target": "#settingsBtn", "title": "x", "description": "y",
                   "position": "center"}]}))
    assert out["custom_steps"][0]["position"] == "bottom"


def test_trigger_guide_bad_workflow_defaults_to_general():
    out = json.loads(ai_assistant._run_tool("trigger_guide", {"workflow": "nonsense"}))
    assert out["guide_workflow"] == "general"
