"""Routing regression harness for the web guide matcher (src/ai_assistant.py).

Ported from main's tests/test_ai_guide_routing.py (work-list A6). Every
(guide, example query) pair in guide_training.json is asserted to resolve to its
own guide; pairs that do not today are strict xfails in KNOWN_MISROUTES with the
guide that wins instead, so fixing one for real turns the case red until it is
removed from the table. The launch gate is pinned separately.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import ai_assistant  # noqa: E402

DEFAULT_MODE = "kinetics"
ALL_MODES = ("kinetics", "point", "calibrate", "report")
GUIDES = ai_assistant._load_guide_examples("en")


def context_for(example: dict) -> dict:
    conditions = example.get("conditions") or {}
    if conditions.get("mode"):
        mode = conditions["mode"]
    elif conditions.get("mode_in"):
        mode = conditions["mode_in"][0]
    elif conditions.get("mode_not"):
        mode = next(m for m in ALL_MODES if m != conditions["mode_not"])
    elif conditions.get("mode_not_in"):
        mode = next(m for m in ALL_MODES if m not in conditions["mode_not_in"])
    else:
        mode = DEFAULT_MODE
    return {"mode": mode, "data_loaded": True, "app_started": True}


_GENERIC = ("unreachable in every real mode: the mode-specific concentration_calc_kinetics/"
            "_point (hard conditions.mode + bonus) outrank the unconstrained generic guide")
KNOWN_MISROUTES = {
    ("create_calibration_curve_workflow", "build calibration from kinetics"):
        "loses to calibrate_kinetics_workflow (2.6): 'kinetics' + 'calibration' is that guide's phrase",
    ("concentration_calc_generic", "calculate concentration"): _GENERIC,
    ("concentration_calc_generic", "get concentration"): _GENERIC,
    ("concentration_calc_generic", "derive concentration"): _GENERIC,
    ("concentration_calc_generic", "measure concentration"): _GENERIC,
    ("concentration_calc_generic", "find concentration"): _GENERIC,
    ("concentration_calc_generic", "how to get concentration"): _GENERIC,
    ("concentration_calc_generic", "concentration from sample"): _GENERIC,
    ("concentration_calc_generic", "apply standard curve"): _GENERIC,
    ("concentration_calc_generic", "calibration calculation"): _GENERIC,
    ("concentration_calc_generic", "what is the concentration"): _GENERIC,
    ("concentration_calc_generic", "show concentration"): _GENERIC,
    ("set_analysis_range", "end time"):
        "loses to select_quantity (3.0) in kinetics: 'time' hits its 'time to sat' keyword plus the kinetics bonus",
    ("expand_collapse_analyses", "show all charts"):
        "loses to view_chart (1.0): 'charts' is view_chart's own noun",
    ("upload_file", "add file"):
        "loses to delete_file (1.0): 'file' ties and delete_file is listed first",
    ("upload_calibration_json", "add calibration file"):
        "loses to load_calibration_json (1.8): 'calibration file' is that guide's phrase",
}


def _pairs():
    for example in GUIDES:
        guide_id = example["id"]
        for query in example.get("queries", []):
            marks = []
            reason = KNOWN_MISROUTES.get((guide_id, query))
            if reason:
                marks.append(pytest.mark.xfail(strict=True, reason=reason))
            yield pytest.param(guide_id, query, marks=marks, id=f"{guide_id}::{query}")


PAIRS = list(_pairs())


def test_corpus_is_present():
    assert len(GUIDES) >= 40
    assert len(PAIRS) >= 300


@pytest.mark.parametrize("guide_id, query", PAIRS)
def test_example_query_routes_to_its_own_guide(guide_id, query):
    example = next(e for e in GUIDES if e["id"] == guide_id)
    best, score = ai_assistant._match_guide_example(query, context_for(example), "en")
    matched = best["id"] if best else None
    assert matched == guide_id, (
        f"{query!r} routed to {matched!r} (score {score:.2f}), expected {guide_id!r}"
    )


def test_known_misroutes_table_is_live():
    corpus = {(e["id"], q) for e in GUIDES for q in e.get("queries", [])}
    stale = sorted(pair for pair in KNOWN_MISROUTES if pair not in corpus)
    assert not stale, f"KNOWN_MISROUTES entries no longer in guide_training.json: {stale}"


# ── Launch gate (A6) ─────────────────────────────────────────────────────────

NAV_CTX = {"mode": "kinetics", "data_loaded": True, "app_started": True}


def _fires(query, ctx=NAV_CTX, lang="en"):
    gid, _steps = ai_assistant.resolve_guide(query, ctx, lang)
    return gid


@pytest.mark.parametrize("query", [
    "how do I export?",
    "how to calibrate",
    "how to export data to report",
    "show me how to select a file",
    "take me to calibrate mode",
    "how to merge two csv files",
    "where can i see the chart",
    "walk me through the whole app",
])
def test_navigation_queries_launch_a_guide(query):
    assert _fires(query), f"{query!r} should short-circuit to a guide"


@pytest.mark.parametrize("query", [
    "explain the Km coefficient please",
    "what is a source?",
    "why is my export failing?",
    "my concentration results look too high",
    "what is a calibration curve",
    "why is my r2 low",
    "explain michaelis menten kinetics",
    "what is the concentration unit for",
])
def test_conceptual_and_statement_queries_defer_to_the_llm(query):
    assert _fires(query) is None, f"{query!r} should be answered by the LLM, not a guide"


def test_gate_thresholds():
    nav = "how do i export data"
    assert ai_assistant._has_nav_intent(nav)
    assert ai_assistant._should_launch_guide(nav, ai_assistant._NAV_LAUNCH_SCORE) is True
    assert ai_assistant._should_launch_guide(nav, ai_assistant._NAV_LAUNCH_SCORE - 0.1) is False

    imperative = "switch to point mode"
    assert not ai_assistant._has_nav_intent(imperative)
    assert ai_assistant._should_launch_guide(imperative, ai_assistant._STRONG_MATCH_SCORE) is True
    assert ai_assistant._should_launch_guide(imperative, ai_assistant._STRONG_MATCH_SCORE - 0.1) is False
    # A strong score resting only on single generic words does not launch.
    assert ai_assistant._should_launch_guide(imperative, 9.0, strong_hit=False) is False

    tour = "walk me through the whole app"
    assert ai_assistant._should_launch_guide(tour, 0.7) is True
    assert ai_assistant._should_launch_guide(tour, 0.6) is False

    assert ai_assistant._should_launch_guide("what is a calibration curve", 99.0) is False


def test_web_chat_uses_the_gate(monkeypatch):
    """chat_stream must not launch a guide for a conceptual question: it reaches the model."""
    called = []

    def fake(api_key, model, messages, tools):
        called.append(1)
        return {"role": "assistant", "content": "Km is ...", "finish_reason": "stop"}

    monkeypatch.setattr(ai_assistant, "_groq_chat", fake)
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "explain the Km coefficient please"}], "en", "k", "m", NAV_CTX, {}))
    assert called
    assert not any(e.get("type") == "guide" for e in events)
