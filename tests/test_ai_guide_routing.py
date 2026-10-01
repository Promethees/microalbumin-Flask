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


LAUNCH_RATE_FLOOR = 0.88   # 93.6 % at fix round 2 (1584 / 1692)


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
    assert ai_assistant._should_launch_guide("how do i not export", 2.0, 0) is True
    assert ai_assistant._should_launch_guide("not export", 9.0, ai_assistant._HIT_EXACT) is False


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


def test_exact_keyword_guide_outranks_a_mode_bonus():
    # fr "charger la calibration" IS a load_calibration_json keyword; the word
    # "calibration" also hits nav_calibrate_mode, whose mode_not bonus (+1)
    # gives it the higher raw score. Exact-first ranking must pick the former.
    ctx = {"mode": "kinetics", "data_loaded": True, "app_started": True, "pending": ""}
    assert ai_assistant.resolve_guide("charger la calibration", ctx, "fr")[0] == "load_calibration_json"
