"""
Regression tests for AI assistant guide routing (src/ai_assistant.py).

Covers the matcher (`_match_guide_example`) and the firing gate
(`_should_launch_guide`) against realistic user phrasings. Guards the fixes for:
  * recording/measurement questions routing to the device-console guide instead
    of the generic app tour (commits ab49712, 6a4c36b);
  * imperative commands firing without an explicit "how to" marker;
  * conceptual questions ("what is R²") still deferring to the LLM;
  * "how do i ..." nav phrasing taking precedence over the "how do" conceptual
    marker;
  * greedy single-shared-word keywords no longer hijacking unrelated queries.
"""
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import ai_assistant  # noqa: E402

# UI contexts the matcher receives from the frontend.
KIN_NODATA = {"mode": "kinetics", "data_loaded": False, "app_started": True}
KIN_DATA = {"mode": "kinetics", "data_loaded": True, "app_started": True}
CAL_DATA = {"mode": "calibrate", "data_loaded": True, "app_started": True}


def route(query, ctx=KIN_NODATA):
    """Return (matched_id_or_None, score) for a query."""
    best, score = ai_assistant._match_guide_example(query, ctx, "en")
    return (best["id"] if best else None), score


def fires(query, ctx=KIN_NODATA):
    """Return True if the query would short-circuit to a guide (vs. the LLM)."""
    best, score = ai_assistant._match_guide_example(query, ctx, "en")
    return bool(best and ai_assistant._should_launch_guide(query, score))


# ---------------------------------------------------------------------------
# Routing: recording-domain questions reach the right guide
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query, expected, ctx", [
    # The originally reported bug: a recording question must reach the device
    # console guide, NOT the generic app-introduction tour.
    ("how to start a colorimetric recording", "measurement_guide", KIN_NODATA),
    ("how do I record data from the colorimeter", "measurement_guide", KIN_NODATA),
    ("how do I start a measurement", "measurement_guide", KIN_NODATA),
    ("how to take colorimeter readings", "measurement_guide", KIN_NODATA),
    ("record a kinetics measurement", "measurement_guide", KIN_NODATA),
    ("start the device", "start_device", KIN_NODATA),
    ("how do I stop the recording", "stop_device", KIN_NODATA),
    ("stop the measurement", "stop_device", KIN_NODATA),
    ("halt the colorimeter", "stop_device", KIN_NODATA),
    ("where do I set the timeout", "set_timeout", KIN_NODATA),
    ("set recording duration", "set_timeout", KIN_NODATA),
    ("change measurement interval", "set_interval", KIN_NODATA),
    ("how to name my recording file", "base_name_input", KIN_NODATA),
    ("where is the recording log", "view_log", KIN_NODATA),
    ("where is my recorded data", "live_view_inactive", KIN_NODATA),
])
def test_recording_queries_route_correctly(query, expected, ctx):
    matched, score = route(query, ctx)
    assert matched == expected, f"{query!r} routed to {matched!r} ({score:.2f}), expected {expected!r}"


def test_recording_query_not_app_introduction():
    """The exact reported regression: must not fall into the 17-step app tour."""
    matched, _ = route("how to start a colorimetric recording", KIN_NODATA)
    assert matched != "app_introduction"
    assert fires("how to start a colorimetric recording", KIN_NODATA)


# ---------------------------------------------------------------------------
# Regression guard: greedy shared-word keywords must not hijack
# ("recording" / "colorimeter" must not pull start/log queries into stop_device)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query", [
    "how to start the sensor recording",
    "how do I begin recording",
    "where is the recording log",
])
def test_recording_queries_not_hijacked_by_stop_device(query):
    matched, _ = route(query, KIN_NODATA)
    assert matched != "stop_device", f"{query!r} wrongly hijacked to stop_device"


# ---------------------------------------------------------------------------
# Firing gate: conceptual questions defer to the LLM
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query", [
    "what is R squared",
    "what is maxRate",
    "explain Michaelis-Menten",
    "why is my R2 low",
    "what does Vmax mean",
    "what is the difference between slope and maxRate",
])
def test_conceptual_questions_do_not_fire_guide(query):
    assert not fires(query, KIN_DATA), f"conceptual query {query!r} should defer to the LLM"


# ---------------------------------------------------------------------------
# Firing gate: nav and imperative phrasings fire
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query, ctx", [
    # "how do i ..." must win over the broader "how do" conceptual marker.
    ("how do I delete a file", KIN_DATA),
    ("how do I stop the recording", KIN_NODATA),
    ("how do I calculate concentration", KIN_DATA),
    # Imperative commands with no nav marker fire on a strong match.
    ("switch to point mode", KIN_NODATA),
    ("change the interval", KIN_NODATA),
    ("merge two csv files", KIN_NODATA),
])
def test_actionable_queries_fire_guide(query, ctx):
    assert fires(query, ctx), f"{query!r} should launch a guide"


# ---------------------------------------------------------------------------
# Helper-level guards
# ---------------------------------------------------------------------------
def test_nav_intent_precedes_conceptual_marker():
    # Contains both "how do i" (nav) and "how do" (conceptual); nav must win.
    assert ai_assistant._has_nav_intent("how do i delete a file") is True


def test_is_conceptual_detects_explanatory_phrasing():
    assert ai_assistant._is_conceptual("what is r squared") is True
    assert ai_assistant._is_conceptual("how to start a recording") is False


def test_weak_match_without_nav_defers_to_llm():
    # A correct but weak (single-keyword) match with no nav marker should fall
    # through to the LLM rather than firing a low-confidence guide.
    matched, score = route("normalize my data", KIN_DATA)
    assert matched == "normalize_data"
    assert score < ai_assistant._STRONG_MATCH_SCORE
    assert not fires("normalize my data", KIN_DATA)
