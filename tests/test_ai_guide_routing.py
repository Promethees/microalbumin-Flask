"""Routing regression harness for the guide matcher (src/ai_assistant.py).

`guide_training.json` ships 62 guides carrying 576 example queries between them.
Those queries are the matcher's documented contract — they are what the keyword
lists were tuned against — but nothing asserted they still route to their own
guide, so a keyword addition or a threshold edit could silently re-route a guide
and only surface as a user complaint.

This module pins that contract:

  * every (guide, example query) pair is asserted to resolve to that guide via
    `_match_guide_example`, one parametrized case per pair so a failure names the
    exact offending phrase;
  * the launch gate (`_should_launch_guide`) is pinned separately — it decides
    whether a match is short-circuited to the UI or handed to the LLM;
  * learned 👍/👎 weights (`ai_feedback.ai_guide_weights.json`) are neutralized,
    so the developer's own feedback history cannot decide whether CI is green.

Pairs that do NOT route to their own guide today are marked `xfail(strict=True)`
in `KNOWN_MISROUTES` with the guide that wins instead. They are recorded, not
"fixed" by loosening the matcher: strict xfail means fixing one for real turns
the case red until it is removed from the table.

Companion file: test_ai_guide_matching.py (hand-written phrasings and the
originally reported regressions). This file is the exhaustive corpus sweep.
"""
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import ai_assistant  # noqa: E402
import ai_feedback  # noqa: E402


# ── Learned-weight isolation ─────────────────────────────────────────────────
# `_match_guide_example` folds `ai_feedback.learned_terms()` /
# `learned_bonus()` into every score whenever the feedback toggle is on, reading
# `ai_guide_weights.json` from the writable data root. That file is per-machine
# user data: a developer who thumbed a few answers up would get different
# baselines from CI. Everything below runs with the toggle forced off, which is
# exactly the branch `_match_guide_example` uses to skip the learned layer.

@pytest.fixture(autouse=True)
def neutral_learned_weights(monkeypatch):
    monkeypatch.setattr(ai_feedback, "is_enabled", lambda: False)


# ── UI context construction ──────────────────────────────────────────────────
# `_match_guide_example` filters on `conditions` (hard gates) and boosts on a
# mode hit, so every guide is queried in a context that actually satisfies its
# own conditions:
#   conditions.mode      → that mode (a hard gate; the guide is skipped elsewhere)
#   conditions.mode_in   → the first accepted mode
#   conditions.mode_not  → any other mode
#   requires_mode        → the mode the guide's own steps ask the user to switch
#                          to (soft; it does not gate matching)
# A guide with no mode constraint is queried in DEFAULT_MODE.
#
# THE CONTEXT RULE: this harness only ever builds a context the frontend can
# actually emit. `_getUiContext` (ai-chat.js) reads
# `AppState.currentMeasurementMode`, which `AppState.reset()` (index.js) mirrors
# from the #measurement-mode button and never leaves unset — so a started app
# always sends one of ALL_MODES. The literal `'unknown'` in `_getUiContext` is a
# dead fallback for an AppState that does not exist yet, and in that state
# `app_started` is false too.
#
# This file used to pin unconstrained guides in `mode="unknown"` together with
# `app_started: True` — a combination no session produces. It was green on 14
# pairs that are unreachable in every real mode, which is precisely the kind of
# comfortable number a routing harness must not report. They are now in
# KNOWN_MISROUTES with the guide that really wins.
#
# `kinetics` is the app's own default (`init.js` sets the mode button to
# kinetics on a restart-reset, else `USER_SETTINGS.default_mode`), so it is the
# single most representative producible context. It is one of four, and a few
# collisions below are kinetics-specific — see
# `test_unconstrained_guides_are_checked_in_a_producible_context` and
# `test_concentration_calc_generic_is_unreachable_in_every_real_mode`.
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
    else:
        requires = example.get("requires_mode")
        if isinstance(requires, str):
            mode = requires
        elif isinstance(requires, list) and requires:
            mode = requires[0]
        else:
            mode = DEFAULT_MODE
    return {
        "mode": mode,
        # requires_data_loaded is a soft prefix (a "select a file first" step),
        # not a match gate — a loaded file is the state these guides describe.
        "data_loaded": True,
        "app_started": True,
    }


# ── Known misroutes ──────────────────────────────────────────────────────────
# (guide_id, query) → why it does not reach its own guide today. Each is a real
# routing finding, left as a strict xfail rather than papered over by editing
# keyword lists or thresholds. "loses to X" means X outscored the guide that
# lists the query; "loses to None" means nothing cleared the 0.1 baseline gate.
KNOWN_MISROUTES = {
    ("stop_device", "end measurement"):
        "loses to measurement_guide (1.6): 'measurement' is that guide's own keyword and 'end' is not a stop_device keyword",
    ("view_log", "log"):
        "loses to None (0.0): 'log' is 3 chars, under the 4-char content-word floor in _content_words",
    ("view_log", "measurement log"):
        "loses to measurement_guide (1.6): the 'measurement' half outweighs the 3-char 'log'",
    ("calibrate_kinetics_workflow", "calibrate kinetics"):
        "loses to nav_calibrate_mode (2.6): its mode_not:calibrate boost (+1) beats the workflow guide",
    ("calibrate_point_workflow", "calibrate point"):
        "loses to nav_calibrate_mode (2.6): same mode_not:calibrate boost",
    ("build_turn_calibration", "calibrate turns"):
        "loses to nav_calibrate_mode (2.6): same mode_not:calibrate boost",
    ("build_turn_calibration", "concentration per turn"):
        "loses to concentration_calc_generic (4.0): 'concentration' is that guide's core keyword",
    ("create_calibration_curve_workflow", "how to create calibrated curve"):
        "loses to nav_calibrate_mode (2.6): same mode_not:calibrate boost",
    ("create_calibration_curve_workflow", "how to calibrate from data"):
        "loses to nav_calibrate_mode (2.6): same mode_not:calibrate boost",
    ("measurement_guide", "start measuring data"):
        "loses to start_device (2.6): 'start' phrases are start_device's specialty",
    ("generate_report_dialog", "what to enter in the report window"):
        "loses to window_size (2.8): the incidental word 'window' matches the analysis-window guide",
    ("split_sources", "separate chart"):
        "loses to view_chart (1.8): 'chart' is view_chart's core keyword",
    ("set_analysis_range", "time window"):
        "loses to set_timeout (2.4): 'time' matches the recording-timeout guide",
    ("set_analysis_range", "start time"):
        "loses to set_timeout (2.4): same 'time' collision",
    ("set_analysis_range", "end time"):
        "loses to set_timeout (2.4): same 'time' collision",
    ("live_view_inactive", "browse data folder"):
        "loses to navigate_directory (2.6): 'folder'/'browse' are the directory guide's keywords",
    ("live_view_inactive", "open data folder"):
        "loses to navigate_directory (2.6): same folder-navigation collision",
    ("clear_logs", "delete log"):
        "loses to delete_file (1.6): 'delete' outweighs the 3-char 'log'",
    ("deselect_file", "unselect file"):
        "loses to select_file (1.8): _token_match deliberately refuses the 'un-' prefix, leaving only 'file'",
    ("deselect_file", "unload file"):
        "loses to select_file (1.8): same, only the generic 'file' scores",
    ("expand_collapse_analyses", "show all charts"):
        "loses to view_chart (1.8): 'charts' is view_chart's core keyword",
    ("app_settings", "default timeout setting"):
        "loses to set_timeout (4.4): the feature guide outranks the settings-panel guide for its own noun",
    ("app_settings", "default split sources"):
        "loses to split_sources (2.6): same feature-vs-settings collision",
    ("save_range_csv", "cut data to range"):
        "loses to set_analysis_range (1.8): 'cut data' is that guide's own keyword",

    # ── Only visible once the harness stopped using mode="unknown" ──────────
    # `concentration_calc_generic` carries no conditions, so it was queried in a
    # context no session emits — the ONE context where no mode-specific variant
    # outranks it. In every producible mode a variant wins: kinetics/point have
    # their own guide, calibrate/report get `concentration_calc_wrong_mode`.
    # The generic guide is therefore unreachable in practice; that is a real
    # finding about the corpus, recorded rather than hidden.
    # See test_concentration_calc_generic_is_unreachable_in_every_real_mode.
    ("concentration_calc_generic", "calculate concentration"):
        "loses to concentration_calc_kinetics (7.8): the mode variant takes the +2 mode boost",
    ("concentration_calc_generic", "get concentration"):
        "loses to concentration_calc_kinetics (6.2): same mode-variant boost",
    ("concentration_calc_generic", "derive concentration"):
        "loses to concentration_calc_kinetics (7.8): same mode-variant boost",
    ("concentration_calc_generic", "measure concentration"):
        "loses to concentration_calc_kinetics (7.8): same mode-variant boost",
    ("concentration_calc_generic", "find concentration"):
        "loses to concentration_calc_kinetics (6.2): same mode-variant boost",
    ("concentration_calc_generic", "how to get concentration"):
        "loses to concentration_calc_kinetics (6.4): same mode-variant boost",
    ("concentration_calc_generic", "concentration from sample"):
        "loses to concentration_calc_kinetics (7.8): same mode-variant boost",
    ("concentration_calc_generic", "apply standard curve"):
        "loses to concentration_calc_kinetics (4.6): same mode-variant boost",
    ("concentration_calc_generic", "calibration calculation"):
        "loses to concentration_calc_kinetics (3.8): same mode-variant boost",
    ("concentration_calc_generic", "what is the concentration"):
        "loses to concentration_calc_kinetics (6.2): same mode-variant boost",
    ("concentration_calc_generic", "show concentration"):
        "loses to concentration_calc_kinetics (6.2): same mode-variant boost",
    ("app_settings", "concentration unit setting"):
        "loses to concentration_calc_kinetics (6.0): 'concentration' is that guide's core keyword in every real mode",
    ("app_settings", "change window size default"):
        "loses to window_size (7.2) in kinetics: the feature guide outranks the settings panel for its own noun (app_settings wins at 3.4 in the other three modes)",
    ("save_range_csv", "save time window"):
        "loses to window_size (2.8) in kinetics: 'window' pulls to the analysis-window guide (save_range_csv wins at 2.6 in the other three modes)",
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
    """Guard the harness itself: an empty/renamed corpus must not pass silently."""
    assert len(GUIDES) >= 60
    assert len(PAIRS) >= 500


@pytest.mark.parametrize("guide_id, query", PAIRS)
def test_example_query_routes_to_its_own_guide(guide_id, query):
    example = next(e for e in GUIDES if e["id"] == guide_id)
    best, score = ai_assistant._match_guide_example(query, context_for(example), "en")
    matched = best["id"] if best else None
    assert matched == guide_id, (
        f"{query!r} routed to {matched!r} (score {score:.2f}), expected {guide_id!r}"
    )


def test_known_misroutes_table_is_live():
    """Every entry in KNOWN_MISROUTES must name a query that still exists.

    A stale entry would silently xpass-guard nothing after the corpus changes.
    """
    corpus = {(e["id"], q) for e in GUIDES for q in e.get("queries", [])}
    stale = sorted(pair for pair in KNOWN_MISROUTES if pair not in corpus)
    assert not stale, f"KNOWN_MISROUTES entries no longer in guide_training.json: {stale}"


# ── Launch gate ──────────────────────────────────────────────────────────────
# Routing decides WHICH guide; `_should_launch_guide` decides whether to launch
# it at all instead of letting the LLM answer. The thresholds it compares against
# (_STRONG_MATCH_SCORE, _NAV_LAUNCH_SCORE, the 0.7 tour cutoff) are pinned both
# directly and end-to-end.

NAV_CTX = {"mode": "kinetics", "data_loaded": True, "app_started": True}


def _fires(query, ctx=NAV_CTX):
    best, score = ai_assistant._match_guide_example(query, ctx, "en")
    return bool(best and ai_assistant._should_launch_guide(query, score))


@pytest.mark.parametrize("query", [
    "how do i start a measurement",
    "where is the recording log",
    "how to export data to report",
    "show me how to select a file",
    "how do i change the interval",
    "take me to calibrate mode",
    "how to merge two csv files",
    "how do i open settings",
    "where can i see the chart",
    # Explicit full-tour phrasing: fires on the lower 0.7 tour cutoff.
    "walk me through the whole app",
])
def test_navigation_queries_launch_a_guide(query):
    assert _fires(query), f"{query!r} should short-circuit to a guide"


@pytest.mark.parametrize("query", [
    "what is a calibration curve",
    "why is my r2 low",
    "what does maxrate mean",
    "explain michaelis menten kinetics",
    "difference between kinetics and point mode",
    "what is absorbance",
    "why does my regression fit badly",
    "what is R squared",
    "how does the colorimeter work",
    # Scores 6+ against concentration_calc_* and must STILL defer to the LLM.
    "what is the concentration unit for",
])
def test_conceptual_questions_defer_to_the_llm(query):
    assert not _fires(query), f"{query!r} should be answered by the LLM, not a guide"


def test_gate_thresholds():
    """The three launch paths, pinned at their exact cutoffs."""
    nav = "how do i export data"
    assert ai_assistant._has_nav_intent(nav)
    assert ai_assistant._should_launch_guide(nav, ai_assistant._NAV_LAUNCH_SCORE) is True
    assert ai_assistant._should_launch_guide(nav, ai_assistant._NAV_LAUNCH_SCORE - 0.1) is False

    imperative = "switch to point mode"          # no nav marker, no conceptual marker
    assert not ai_assistant._has_nav_intent(imperative)
    assert ai_assistant._should_launch_guide(imperative, ai_assistant._STRONG_MATCH_SCORE) is True
    assert ai_assistant._should_launch_guide(imperative, ai_assistant._STRONG_MATCH_SCORE - 0.1) is False

    tour = "walk me through the whole app"
    assert ai_assistant._is_tour_request(tour)
    assert ai_assistant._should_launch_guide(tour, 0.7) is True
    assert ai_assistant._should_launch_guide(tour, 0.6) is False

    # A conceptual question never launches, however strong the keyword match.
    assert ai_assistant._should_launch_guide("what is a calibration curve", 99.0) is False


# ── Learned weights must not decide the baseline ─────────────────────────────

def _route(query, ctx=NAV_CTX):
    best, _score = ai_assistant._match_guide_example(query, ctx, "en")
    return best["id"] if best else None


def test_learned_weights_can_re_route_when_enabled(monkeypatch):
    """The isolation fixture is load-bearing: prove feedback CAN move routing.

    Simulates a machine where the user thumbed 'stop measuring' up on the app
    tour: reinforced terms give app_introduction a baseline score and the learned
    coefficient carries it past the real guide. Without the module fixture this
    is what a developer's own ai_guide_weights.json could do to these tests.
    """
    monkeypatch.setattr(ai_feedback, "is_enabled", lambda: True)
    monkeypatch.setattr(ai_feedback, "learned_terms",
                        lambda gid: ["stop measuring"] if gid == "app_introduction" else [])
    monkeypatch.setattr(ai_feedback, "learned_bonus",
                        lambda gid: 3.0 if gid == "app_introduction" else 0.0)
    assert _route("stop measuring") == "app_introduction"


def test_routing_ignores_learned_weights(monkeypatch):
    """With the toggle off (the fixture's state) the same weights change nothing."""
    monkeypatch.setattr(ai_feedback, "learned_terms",
                        lambda gid: ["stop measuring"] if gid == "app_introduction" else [])
    monkeypatch.setattr(ai_feedback, "learned_bonus",
                        lambda gid: 3.0 if gid == "app_introduction" else 0.0)
    assert ai_feedback.is_enabled() is False   # the autouse fixture is in effect
    assert _route("stop measuring") == "stop_device"


def test_weights_file_is_never_read_during_routing(monkeypatch):
    """No on-disk weights file is touched while the toggle is off."""
    def _boom(*_a, **_k):
        raise AssertionError("routing must not read ai_guide_weights.json")

    monkeypatch.setattr(ai_feedback, "learned_terms", _boom)
    monkeypatch.setattr(ai_feedback, "learned_bonus", _boom)
    assert _route("stop measuring") == "stop_device"
