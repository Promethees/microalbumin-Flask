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


# ===========================================================================
# Regression batch for the four routing defects found by the query harness.
# ===========================================================================

# ---------------------------------------------------------------------------
# #1 — Prefix-only token matching.
# A base word embedded as a *suffix* of a negation/derivation form must not
# cross-match ('select' ⊂ 'deselect'/'unselect'), while genuine stem variants
# ('record'/'recorded', 'file'/'files') still do.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("a, b, expected", [
    ("file", "files", True),
    ("record", "recorded", True),
    ("source", "sources", True),
    ("select", "deselect", False),
    ("select", "unselect", False),
    ("load", "unload", False),
])
def test_token_match_is_prefix_only(a, b, expected):
    assert ai_assistant._token_match(a, b) is expected
    assert ai_assistant._token_match(b, a) is expected  # symmetric


def test_select_file_not_hijacked_by_deselect():
    """'select a file' must reach select_file, not the antonym deselect_file."""
    matched, score = route("where do I select a file", KIN_DATA)
    assert matched == "select_file", f"routed to {matched!r} ({score:.2f})"
    assert fires("where do I select a file", KIN_DATA)


def test_genuine_deselect_still_reaches_deselect_file():
    """Inverse guard: real deselect phrasing still routes to deselect_file."""
    matched, _ = route("how do I deselect a file", KIN_DATA)
    assert matched == "deselect_file"


# ---------------------------------------------------------------------------
# #2 / #3 — Specificity-weighted exact matches.
# One long, specific exact phrase must outrank a pile of short generic or
# near-duplicate fuzzy keywords summed from a less-relevant example.
# ---------------------------------------------------------------------------
def test_export_to_report_beats_generic_export():
    """'export data to report' is the report-subject guide, not plain export."""
    matched, score = route("export data to report", KIN_DATA)
    assert matched == "export_to_report_subject", f"routed to {matched!r} ({score:.2f})"
    assert fires("export data to report", KIN_DATA)


def test_record_data_reaches_measurement_guide_not_live_view():
    """'record data' reaches the measurement guide, not live_view_inactive, whose
    several near-duplicate '...recorded data' keywords previously out-summed it."""
    matched, score = route("how do I record data", KIN_DATA)
    assert matched == "measurement_guide", f"routed to {matched!r} ({score:.2f})"


def test_specificity_weight_orders_exact_matches():
    """A longer exact phrase scores strictly higher than a one-word exact match."""
    qc = ai_assistant._content_words("export data to report")
    long_phrase = ai_assistant._score_keyword("export data to report", "export data to report", qc)
    one_word = ai_assistant._score_keyword("export", "export data to report", qc)
    assert long_phrase > one_word


# ---------------------------------------------------------------------------
# #4 — A single incidental fuzzy hit (0.8) on an out-of-context word must not
# hijack into an unrelated guide. The right guide still fires in its own mode.
# ---------------------------------------------------------------------------
def test_regression_query_wrong_mode_defers_to_llm():
    """'select a regression algorithm' in kinetics must NOT open the file guide
    (its only hit there is the incidental word 'select')."""
    matched, score = route("how do I select a regression algorithm", KIN_NODATA)
    assert not fires("how do I select a regression algorithm", KIN_NODATA), \
        f"weak fuzzy match {matched!r} ({score:.2f}) should defer to the LLM"


def test_regression_query_fires_in_calibrate_mode():
    """The same query in the correct mode reaches the regression-algorithm guide."""
    matched, _ = route("how do I select a regression algorithm", CAL_DATA)
    assert matched == "select_regression"
    assert fires("how do I select a regression algorithm", CAL_DATA)


def test_nav_launch_requires_a_solid_hit():
    """The nav/how-to path needs >= _NAV_LAUNCH_SCORE; a lone 0.8 fuzzy is not enough."""
    assert ai_assistant._NAV_LAUNCH_SCORE >= 1.0


# ---------------------------------------------------------------------------
# Firing gate: explicit full-tour requests launch even on a weak keyword score.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query", [
    "walk me through the whole app",
    "guide me through everything",
    "give me a step by step walkthrough",
])
def test_full_tour_requests_fire_app_introduction(query):
    matched, score = route(query, KIN_NODATA)
    assert matched == "app_introduction", f"{query!r} routed to {matched!r}"
    assert fires(query, KIN_NODATA), f"{query!r} (score {score:.2f}) should launch the tour"


# ===========================================================================
# Semantic-intent layer: spell-correction (typos / phrasing) + local resolver.
# ===========================================================================

# ---------------------------------------------------------------------------
# Query words are spell-corrected to the guide vocabulary BEFORE scoring, so
# misspellings still reach the right guide. Guards keep genuine out-of-domain
# words and antonyms from being mis-corrected.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("typo, canonical", [
    ("measurment", "measurement"),
    ("mesure", "measure"),
    ("calibrte", "calibrate"),
    ("kinetcs", "kinetics"),
    ("colorimiter", "colorimeter"),
])
def test_nearest_keyword_word_fixes_typos(typo, canonical):
    vocab = ai_assistant._guide_vocabulary(ai_assistant._load_guide_examples("en"))
    assert canonical in vocab, f"test premise: {canonical!r} should be in the guide vocabulary"
    assert ai_assistant._nearest_keyword_word(typo, vocab) == canonical


@pytest.mark.parametrize("word", [
    "internal",   # real word, near 'interval' — must NOT be corrected
    "deselect",   # antonym of 'select' — must stay itself
    "report",     # already in vocabulary
])
def test_nearest_keyword_word_leaves_valid_words(word):
    vocab = ai_assistant._guide_vocabulary(ai_assistant._load_guide_examples("en"))
    assert ai_assistant._nearest_keyword_word(word, vocab) == word


@pytest.mark.parametrize("query, expected", [
    ("how to do measurment", "measurement_guide"),
    ("how to mesure kinetics", "measurement_guide"),
    ("how to start a colorimetic recording", "measurement_guide"),
    ("how do I calibrte", "nav_calibrate_mode"),
    ("swich to point mode", "nav_point_mode"),
    ("how do I delete a fle", "delete_file"),
])
def test_misspelled_queries_still_route(query, expected):
    matched, score = route(query, KIN_NODATA)
    assert matched == expected, f"{query!r} routed to {matched!r} ({score:.2f})"


def test_typo_does_not_break_antonym_guard():
    # 'deselct' (typo of deselect) must reach deselect_file, never select_file.
    matched, _ = route("how do I deselct a file", KIN_DATA)
    assert matched == "deselect_file"


# ---------------------------------------------------------------------------
# resolve_guide(): the local, no-LLM resolver used by the /ai/match endpoint.
# ---------------------------------------------------------------------------
def test_resolve_guide_returns_local_steps():
    guide_id, steps = ai_assistant.resolve_guide("how to do measurement", KIN_NODATA, "en")
    assert guide_id == "measurement_guide"
    assert steps and len(steps) == 7
    # Steps are real desktop targets, resolved locally (not the cloud's 2-step stub).
    assert steps[0]["target"] == "#measurement-mode"


def test_resolve_guide_defers_conceptual_and_greeting():
    assert ai_assistant.resolve_guide("what is R squared", KIN_DATA, "en") == (None, None)
    assert ai_assistant.resolve_guide("hello there", KIN_NODATA, "en") == (None, None)
    assert ai_assistant.resolve_guide("", KIN_NODATA, "en") == (None, None)


# ---------------------------------------------------------------------------
# /ai/match HTTP route — local guide resolution, no activation required.
# ---------------------------------------------------------------------------
def test_ai_match_route_fires_for_measurement(client):
    resp = client.post("/ai/match", json={
        "query": "how to do measurment",  # misspelled on purpose
        "language": "en",
        "ui_context": {"mode": "kinetics", "data_loaded": False, "app_started": True},
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["fires"] is True
    assert data["guide_id"] == "measurement_guide"
    assert len(data["steps"]) == 7


def test_ai_match_route_defers_conceptual(client):
    resp = client.post("/ai/match", json={
        "query": "what is maxRate",
        "language": "en",
        "ui_context": {"mode": "kinetics", "data_loaded": True, "app_started": True},
    })
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["fires"] is False
    assert data["guide_id"] is None
    assert data["steps"] == []


# ---------------------------------------------------------------------------
# save_linearity_range — soft mode gate + correct button selector.
# Regression for "how to save linearity range" launching a guide that pointed
# at #log-cdc-data: the hard conditions.mode==kinetics gate excluded the guide
# outside kinetics, so the query fell through to the LLM and landed on the CDC
# logging console. It is now a soft `requires_mode` that keeps the guide
# matchable everywhere and prepends a switch-to-kinetics step instead.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ctx", [
    {"mode": "kinetics", "data_loaded": True, "app_started": True},
    {"mode": "point", "data_loaded": True, "app_started": True},
    {"mode": "calibrate", "data_loaded": True, "app_started": True},
    {"mode": "unknown", "data_loaded": False, "app_started": True},
])
def test_save_linearity_range_fires_in_every_mode(ctx):
    gid, steps = ai_assistant.resolve_guide("how to save linearity range", ctx, "en")
    assert gid == "save_linearity_range"
    assert steps


def test_save_linearity_range_prepends_switch_mode_when_not_kinetics():
    gid, steps = ai_assistant.resolve_guide(
        "how to save linearity range",
        {"mode": "point", "data_loaded": True, "app_started": True}, "en")
    assert steps[0]["target"] == "#meas-mode-section"
    assert "kinetics" in steps[0]["description"]


def test_save_linearity_range_no_switch_mode_in_kinetics():
    gid, steps = ai_assistant.resolve_guide(
        "how to save linearity range",
        {"mode": "kinetics", "data_loaded": True, "app_started": True}, "en")
    assert steps[0]["target"] != "#meas-mode-section"


def test_save_linearity_range_button_uses_data_hint_selector():
    # The real button carries data-hint (native title= is stripped by tooltip.js),
    # so a button[title=...] target would spotlight nothing.
    _, steps = ai_assistant.resolve_guide(
        "how to save linearity range",
        {"mode": "kinetics", "data_loaded": True, "app_started": True}, "en")
    targets = [s["target"] for s in steps]
    assert any('data-hint="Save the linearity range' in t for t in targets)
    assert not any("[title=" in t for t in targets)


def test_soft_mode_gate_does_not_crossfire_other_guides():
    # Removing save_linearity_range's hard mode gate must not let mode-specific
    # guides bleed across modes: point-mode concentration still routes to the
    # point variant, not the kinetics one.
    assert route("how do I calculate concentration", CAL_DATA)  # sanity: resolves
    gid, _ = ai_assistant.resolve_guide(
        "how do I calculate concentration",
        {"mode": "point", "data_loaded": True, "app_started": True}, "en")
    assert gid == "concentration_calc_point"
