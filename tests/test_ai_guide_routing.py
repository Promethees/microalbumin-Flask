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

    # ── Only visible once the harness stopped using mode="unknown" ──────────
    # `concentration_calc_generic` carries no conditions, so it was queried in a
    # context no session emits — the ONE context where no mode-specific variant
    # outranks it. In every producible mode a variant wins: kinetics/point have
    # their own guide, calibrate/report get `concentration_calc_wrong_mode`.
    # The generic guide is therefore unreachable in practice; that is a real
    # finding about the corpus, recorded rather than hidden.
    # See test_concentration_calc_generic_is_unreachable_in_every_real_mode.
    ("concentration_calc_generic", "calculate concentration"):
        "loses to concentration_calc_kinetics (4.6): the mode variant takes the +2 mode boost",
    ("concentration_calc_generic", "get concentration"):
        "loses to concentration_calc_kinetics (3.0): same mode-variant boost",
    ("concentration_calc_generic", "derive concentration"):
        "loses to concentration_calc_kinetics (4.6): same mode-variant boost",
    ("concentration_calc_generic", "measure concentration"):
        "loses to concentration_calc_kinetics (4.6): same mode-variant boost",
    ("concentration_calc_generic", "find concentration"):
        "loses to concentration_calc_kinetics (3.0): same mode-variant boost",
    ("concentration_calc_generic", "how to get concentration"):
        "loses to concentration_calc_kinetics (3.0): same mode-variant boost",
    ("concentration_calc_generic", "concentration from sample"):
        "loses to concentration_calc_kinetics (4.6): same mode-variant boost",
    ("concentration_calc_generic", "apply standard curve"):
        "loses to concentration_calc_kinetics (4.6): same mode-variant boost",
    ("concentration_calc_generic", "calibration calculation"):
        "loses to concentration_calc_kinetics (3.8): same mode-variant boost",
    ("concentration_calc_generic", "what is the concentration"):
        "loses to concentration_calc_kinetics (3.0): same mode-variant boost",
    ("concentration_calc_generic", "show concentration"):
        "loses to concentration_calc_kinetics (3.0): same mode-variant boost",
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

    Simulates a machine where the user thumbed the measurement guide up: both
    guides have a baseline keyword hit for the query,
    and the learned coefficient carries measurement_guide past stop_device.
    Without the module fixture this is what a developer's own
    ai_guide_weights.json could do to these tests.
    """
    monkeypatch.setattr(ai_feedback, "is_enabled", lambda: True)
    monkeypatch.setattr(ai_feedback, "learned_terms", lambda gid: [])
    monkeypatch.setattr(ai_feedback, "learned_bonus", lambda gid: 0.0)
    # Neither guide has a keyword that IS the whole query (an exact keyword
    # outranks any weight), so the learned coefficient decides.
    assert _route("measurement stop button") == "stop_device"
    monkeypatch.setattr(ai_feedback, "learned_bonus",
                        lambda gid: 2.0 if gid == "measurement_guide" else 0.0)
    assert _route("measurement stop button") == "measurement_guide"


def test_learned_terms_cannot_create_a_baseline(monkeypatch):
    """B4: learned vocabulary alone never lifts a guide the query does not
    mention — a 👍 on 'stop measuring' for the app tour cannot hijack it."""
    monkeypatch.setattr(ai_feedback, "is_enabled", lambda: True)
    monkeypatch.setattr(ai_feedback, "learned_terms",
                        lambda gid: ["stop measuring"] if gid == "app_introduction" else [])
    monkeypatch.setattr(ai_feedback, "learned_bonus",
                        lambda gid: 3.0 if gid == "app_introduction" else 0.0)
    assert _route("stop measuring") == "stop_device"


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


# ── B3: statements and look-alike words must not launch a guide ──────────────
# (query, context, allowed guide ids — empty means "no launch").

KIN_DATA = {"mode": "kinetics", "data_loaded": True, "app_started": True}
REPORT_CTX = {"mode": "report", "data_loaded": False, "app_started": True}

NEGATIVE_PROBES = [
    ("my concentration results look too high", KIN_DATA, set()),
    ("concentration is negative for source 2", KIN_DATA, set()),
    ("my chart is empty", KIN_DATA, set()),
    ("how to unmerge files", KIN_DATA, set()),
    ("how to un-merge files", KIN_DATA, set()),
    ("how to unexport data", KIN_DATA, set()),
    ("how do I change the concentration unit", KIN_DATA, {"app_settings"}),
    ("how do I delete a report subject", KIN_DATA, {"report_subject_management"}),
]


@pytest.mark.parametrize("query, ctx, allowed", NEGATIVE_PROBES,
                         ids=[p[0] for p in NEGATIVE_PROBES])
def test_negative_probes_do_not_launch_the_wrong_guide(query, ctx, allowed):
    gid, _steps = ai_assistant.resolve_guide(query, ctx, "en")
    assert gid is None or gid in allowed, f"{query!r} launched {gid!r}"


def test_delete_report_subject_in_report_mode_reaches_its_guide():
    gid, _ = ai_assistant.resolve_guide("how do I delete a report subject", REPORT_CTX, "en")
    assert gid == "report_subject_management"


@pytest.mark.parametrize("query", ["how to calibrate", "how do I export?", "switch to point mode", "app settings"])
def test_positive_probes_still_launch(query):
    assert ai_assistant.resolve_guide(query, KIN_DATA, "en")[0]


# ── Launch level, not just match (fix round: H1 / H2 / M1) ──────────────────
# The corpus sweep above asserts the MATCH. These assert the LAUNCH — what the
# user actually sees — so a gate or threshold change can no longer silently
# stop guides from opening while every match test stays green.

def _ctx(mode):
    return {"mode": mode, "data_loaded": True, "app_started": True, "pending": ""}


LAUNCH_PROBES = [
    # H1: English terms written next to CJK / kana (no spaces).
    ("zh", "point", "切换到kinetics模式", "nav_kinetics_mode"),
    ("zh", "point", "进入kinetics", "nav_kinetics_mode"),
    ("zh", "kinetics", "切换到point模式", "nav_point_mode"),
    ("ja", "point", "kineticsモードに切り替え", "nav_kinetics_mode"),
    ("ja", "kinetics", "pointモードに切り替える方法", "nav_point_mode"),
    ("ja", "kinetics", "calibrateモードへ移動", "nav_calibrate_mode"),
    ("ja", "kinetics", "chartを表示する方法", "view_chart"),
    ("zh", "kinetics", "如何查看chart", "view_chart"),
    # H2: bare CJK phrases that are a guide's own keyword; nav phrasings.
    ("zh", "kinetics", "导出数据", "export_data"),
    ("ja", "kinetics", "データをエクスポート", "export_data"),
    ("zh", "kinetics", "合并csv", "merge_files"),
    ("ja", "kinetics", "CSVをマージ", "merge_files"),
    ("zh", "kinetics", "打开用户指南", "open_user_guide"),
    ("en", "kinetics", "how do i combine csv files", "merge_files"),
    ("en", "kinetics", "how do i join csv files", "merge_files"),
    ("ru", "kinetics", "выбрать файл", "select_file"),
    ("vi", "kinetics", "chọn tệp", "select_file"),
    # M1: bare commands; English mode names typed by non-English users.
    ("en", "kinetics", "see chart", "view_chart"),
    ("en", "kinetics", "show graph", "view_chart"),
    ("vi", "point", "kinetics", "nav_kinetics_mode"),
    ("fr", "kinetics", "calibrate", "nav_calibrate_mode"),
    ("ru", "kinetics", "point", "nav_point_mode"),
    # Representative multilingual nav phrasings.
    ("fr", "kinetics", "comment exporter les données", "export_data"),
    ("vi", "kinetics", "cách xuất dữ liệu", "export_data"),
    ("ru", "kinetics", "как экспортировать данные", "export_data"),
    ("en", "kinetics", "how to calibrate", "nav_calibrate_mode"),
    ("en", "kinetics", "how do I export?", "export_data"),
]


@pytest.mark.parametrize("lang, mode, query, expected", LAUNCH_PROBES,
                         ids=[f"{p[0]}-{p[2]}" for p in LAUNCH_PROBES])
def test_launch_probes(lang, mode, query, expected):
    gid, steps = ai_assistant.resolve_guide(query, _ctx(mode), lang)
    assert gid == expected and steps, f"{lang} {query!r} launched {gid!r}"


@pytest.mark.parametrize("query", [
    "explain the Km coefficient please",
    "what is a source?",
    "why is my export failing?",
    "my concentration results look too high",
    "my chart is empty",
])
def test_explanations_and_statements_still_go_to_the_llm(query):
    assert ai_assistant.resolve_guide(query, _ctx("kinetics"), "en")[0] is None


def test_own_query_launch_rate():
    """Every guide's own example queries (EN + all six overlays), typed as-is in
    a context the guide accepts, must mostly LAUNCH that guide. The floor sits a
    few points under today's rate so a gate change that kills launches fails."""
    import json as _json
    total = launched = 0
    for lang in ("en", "vi", "zh", "fr", "ja", "ru", "ko"):
        if lang == "en":
            own = {e["id"]: e["queries"] for e in GUIDES}
        else:
            path = os.path.join(os.path.dirname(__file__), "..", "guide_translations", f"{lang}.json")
            with open(path, encoding="utf-8") as f:
                own = {e["id"]: e.get("queries", []) for e in _json.load(f)}
        for ex in GUIDES:
            for q in own.get(ex["id"], []):
                total += 1
                gid, _ = ai_assistant.resolve_guide(q, context_for(ex), lang)
                launched += gid == ex["id"]
    assert total > 1000
    assert launched / total >= LAUNCH_RATE_FLOOR, f"{launched}/{total}"


LAUNCH_RATE_FLOOR = 0.92   # 95.2 % at fix round 2 (2344 / 2463)


@pytest.mark.parametrize("query, expected", [
    ("set timeout", "set_timeout"), ("set interval", "set_interval"),
    ("timeout", "set_timeout"), ("settings", "app_settings"),
])
def test_bare_commands_launch(query, expected):
    assert ai_assistant.resolve_guide(query, _ctx("kinetics"), "en")[0] == expected


# ── Fix round 2 (N1/N4): negations, pronouns and vague keywords never launch ──
# The exact-keyword launch compares tokens with only a small filler list
# removed (negations and pronouns are kept), refuses a negated query, and
# ignores keywords that are one generic word or shared by 3+ guides.

NEGATIVE_PROBES_EXACT = [
    ("en", q) for q in (
        "not export", "do not export", "so export", "then export", "could export",
        "no merge", "we merge", "not calibrate", "not the chart", "no chart", "my chart",
        "my concentration", "is it my concentration?", "my source", "it is the source",
        "no timeout", "my settings", "data", "my data", "all data", "data please",
        "r2", "source", "log", "don't export the data",
    )
] + [
    ("ko", "데이터"), ("vi", "đường chuẩn"), ("zh", "模式"),
    ("zh", "不要导出数据"), ("zh", "别合并csv"), ("ja", "データをエクスポートしない"),
    ("ru", "не экспортировать данные"), ("fr", "ne pas exporter les données"),
    ("vi", "không xuất dữ liệu"), ("ko", "데이터 내보내기 안 해요"),
]


@pytest.mark.parametrize("lang, query", NEGATIVE_PROBES_EXACT,
                         ids=[f"{p[0]}-{p[1]}" for p in NEGATIVE_PROBES_EXACT])
def test_negated_pronoun_and_vague_queries_do_not_launch(lang, query):
    ctx = {"mode": "kinetics", "data_loaded": True, "app_started": True, "pending": ""}
    assert ai_assistant.resolve_guide(query, ctx, lang)[0] is None


def test_nav_phrasing_still_launches_with_a_negation():
    # "how do I not show popups" is a request; the negation guard only covers
    # statements without how-to phrasing.
    ctx = {"mode": "kinetics", "data_loaded": True, "app_started": True, "pending": ""}
    assert ai_assistant.resolve_guide("how do i not show popups", ctx, "en")[0] == "disable_popups"
    # A keyword that is itself negated still launches ("no popup", "不要弹窗").
    assert ai_assistant.resolve_guide("no popup", ctx, "en")[0] == "disable_popups"


# ── Test gaps: CJK weighting and exact-first ranking are pinned ──────────────

@pytest.mark.parametrize("lang, query, expected", [
    # Launch ONLY through the CJK ~1-word-per-2-chars weighting: no nav marker,
    # the query is not itself a keyword (so no _HIT_EXACT), one CJK phrase hit.
    ("zh", "我要导出数据", "export_data"),
    ("ja", "今すぐデータをエクスポート", "export_data"),
])
def test_cjk_phrase_weighting_launches(lang, query, expected):
    ctx = {"mode": "kinetics", "data_loaded": True, "app_started": True, "pending": ""}
    _best, _score, evidence = ai_assistant._match_guide_detail(query, ctx, lang)
    assert evidence != ai_assistant._HIT_EXACT and not ai_assistant._has_nav_intent(query)
    assert ai_assistant.resolve_guide(query, ctx, lang)[0] == expected


def test_specificity_units_weights_cjk_runs():
    assert ai_assistant._specificity_units(frozenset({"导出数据"})) == 2
    assert ai_assistant._specificity_units(frozenset({"export", "data"})) == 2
    assert ai_assistant._specificity_units(frozenset({"图表"})) == 1
