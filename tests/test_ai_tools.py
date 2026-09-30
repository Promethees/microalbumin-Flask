"""Tool execution, help docs and language handling in src/ai_assistant.py."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import ai_assistant  # noqa: E402
import ai_settings  # noqa: E402


# ── A17: language validation ─────────────────────────────────────────────────

def test_valid_langs_is_the_settings_registry():
    assert ai_assistant.VALID_LANGS == frozenset(ai_settings.SUPPORTED_LANGUAGES)


def test_unknown_language_falls_back_to_en_and_cache_stays_bounded():
    ai_assistant._GUIDE_CACHE.clear()
    en = ai_assistant._load_guide_examples("en")
    for junk in ["xx", "../etc", "EN", "", "zz" * 50] + [f"l{i}" for i in range(100)]:
        assert ai_assistant._load_guide_examples(junk) == en
    assert set(ai_assistant._GUIDE_CACHE) <= set(ai_settings.SUPPORTED_LANGUAGES)


# ── A10: trigger_custom_steps / trigger_guide results ────────────────────────

KIN = {"mode": "kinetics", "data_loaded": True, "app_started": True, "pending": ""}


def _call(name, args):
    return {"role": "assistant", "content": "", "finish_reason": "tool_calls",
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


class _Model:
    def __init__(self, first):
        self.first, self.calls = first, []

    def __call__(self, api_key, model, messages, tools):
        self.calls.append([dict(m) for m in messages])
        if len(self.calls) == 1:
            return self.first
        return {"role": "assistant", "content": "Use the Export button.", "finish_reason": "stop"}


def _stream(model, grounded=False):
    kw = {}
    if grounded:
        kw = dict(system_prompt_override="DESKTOP", tools_override=ai_assistant.TOOLS, proxy_request=True)
    return list(ai_assistant.chat_stream(
        [{"role": "user", "content": "xyzzy plugh"}], "en", "k", "m", KIN, {}, **kw))


def test_invalid_target_is_never_a_launched_guide(monkeypatch):
    model = _Model(_call("trigger_custom_steps", {"steps": [
        {"target": "export-btn", "title": "Export", "description": "d"}]}))
    monkeypatch.setattr(ai_assistant, "_groq_chat", model)
    events = _stream(model)
    text = "".join(e.get("content", "") for e in events if e["type"] == "chunk")
    assert not any(e["type"] == "guide" for e in events)
    assert ai_assistant._GUIDE_LAUNCHED["en"] not in text
    tool_msgs = [m for m in model.calls[1] if m.get("role") == "tool"]
    assert json.loads(tool_msgs[0]["content"])["error"] == "no_valid_steps"
    assert text == "Use the Export button."


def test_web_whitelist_drops_invented_ids():
    out = json.loads(ai_assistant._run_tool("trigger_custom_steps", {"steps": [
        {"target": "#export-button", "title": "x", "description": "y"},
        {"target": "#export-analysis", "title": "Export", "description": "Click"},
    ]}))
    assert [s["target"] for s in out["custom_steps"]] == ["#export-analysis"]


def test_grounded_request_keeps_desktop_ids(monkeypatch):
    model = _Model(_call("trigger_custom_steps", {"steps": [
        {"target": "#run-script-btn", "title": "Run", "description": "Start"}]}))
    monkeypatch.setattr(ai_assistant, "_groq_chat", model)
    events = _stream(model, grounded=True)
    guide = next(e for e in events if e["type"] == "guide")
    assert guide["guide_action"]["custom_steps"][0]["target"] == "#run-script-btn"


def test_steps_are_capped_and_coerced():
    raw = [{"target": "#export-analysis", "title": 5, "description": {"x": 1}}] * 10
    out = json.loads(ai_assistant._run_tool("trigger_custom_steps", {"steps": raw}))
    assert len(out["custom_steps"]) == ai_assistant._MAX_CUSTOM_STEPS
    assert out["custom_steps"][0]["title"] == "5"
    assert isinstance(out["custom_steps"][0]["description"], str)


@pytest.mark.parametrize("bad", [None, "x", [None, 3, {"target": None}], [{"target": "#1-bad"}]])
def test_malformed_steps_are_an_error(bad):
    out = json.loads(ai_assistant._run_tool("trigger_custom_steps", {"steps": bad}))
    assert out.get("error") == "no_valid_steps"


def test_unknown_workflow_is_an_error_not_general():
    out = json.loads(ai_assistant._run_tool("trigger_guide", {"workflow": "export_everything"}))
    assert out["error"] == "unknown_workflow"
    assert "general" in out["valid"]
    ok = json.loads(ai_assistant._run_tool("trigger_guide", {"workflow": "report"}))
    assert ok == {"guide_workflow": "report"}


def test_unknown_workflow_reaches_the_model(monkeypatch):
    model = _Model(_call("trigger_guide", {"workflow": "nope"}))
    monkeypatch.setattr(ai_assistant, "_groq_chat", model)
    events = _stream(model)
    assert not any(e["type"] == "guide" for e in events)
    assert len(model.calls) == 2


# ── Help docs match the app (A11 / B10) ──────────────────────────────────────
# Each formula the help text states is pinned to the function math_ops.py
# actually fits, evaluated numerically — so the doc and the fit cannot drift.
import math  # noqa: E402

import math_ops  # noqa: E402

_X, _A, _B, _C = 2.0, 3.0, 0.5, 1.5
PINNED_FORMS = [
    ("y = a·x + b", math_ops.linear_func(_X, _A, _B), _A * _X + _B),
    ("y = a·x² + b·x + c", math_ops.poly_func(_X, _A, _B, _C), _A * _X ** 2 + _B * _X + _C),
    ("y = a·ln(x + b) + c", math_ops.log_func(_X, _A, _B, _C), _A * math.log(_X + _B) + _C),
    ("y = a·e^(b·x) + c", math_ops.exp_func(_X, _A, _B, _C), _A * math.exp(_B * _X) + _C),
    # mm_func(x, vmax, km)
    ("y = (Km·x) / (Vmax − x)", math_ops.mm_func(_X, 5.0, 4.0), (4.0 * _X) / (5.0 - _X)),
]


@pytest.mark.parametrize("form, fitted, stated", PINNED_FORMS, ids=[p[0] for p in PINNED_FORMS])
def test_regression_help_states_the_fitted_forms(form, fitted, stated):
    assert form in ai_assistant._HELP_DOCS["regression"]
    assert fitted == pytest.approx(stated)


def test_help_docs_have_no_stale_claims():
    joined = "\n".join(ai_assistant._HELP_DOCS.values())
    assert "3 measurement modes" not in joined
    assert "degree 2-6" not in joined
    assert "Vmax·x / (Km + x)" not in joined
    assert "4 modes" in ai_assistant._HELP_DOCS["measurement_modes"]
    assert "Turn" in ai_assistant._HELP_DOCS["csv_format"]
    assert "#cal-json-sel-section" in ai_assistant._HELP_DOCS["calibration"]


def test_get_help_topic_returns_the_regression_doc():
    out = json.loads(ai_assistant._run_tool("get_help_topic", {"topic": "regression"}))
    assert out["content"] == ai_assistant._HELP_DOCS["regression"]
