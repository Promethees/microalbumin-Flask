"""Guide matcher behaviour on the web chat (src/ai_assistant.py).

Work-list items A6 (scoring + gate), A7 (stop-word overlay keywords), A14
(out-of-scope word boundaries), A16 (structural mode-switch steps).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import ai_assistant  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
KIN = {"mode": "kinetics", "data_loaded": True, "app_started": True}


def fires(query, ctx=KIN, lang="en"):
    return ai_assistant.resolve_guide(query, ctx, lang)[0]


# ── A6 / B3 negative probes ──────────────────────────────────────────────────

NEGATIVE_PROBES = [
    # (query, allowed guide ids — empty means "no launch")
    ("my concentration results look too high", set()),
    ("concentration is negative for source 2", set()),
    ("my chart is empty", set()),
    ("how to unmerge files", set()),
    ("how to un-merge files", set()),
    ("how to unexport data", set()),
    ("how do I change the concentration unit", set()),
    ("how do I delete a report subject", {"report_subject_management"}),
]


@pytest.mark.parametrize("query, allowed", NEGATIVE_PROBES)
def test_negative_probes(query, allowed):
    got = fires(query)
    assert got is None or got in allowed, f"{query!r} launched {got!r}"


def test_same_content_keywords_count_once():
    q = "concentration please"
    qc = ai_assistant._content_words(q)
    one = ai_assistant._score_guide_keywords(["get concentration"], q, qc)[0]
    many = ai_assistant._score_guide_keywords(
        ["get concentration", "find concentration", "show concentration", "how to get concentration"], q, qc)[0]
    assert one == many > 0


def test_mode_bonus_needs_a_baseline_hit():
    # A kinetics-only guide whose keyword only fuzzily grazes the query must
    # not be lifted over the nav threshold by its +2 mode bonus.
    best, score, _ = ai_assistant._match_guide_detail("how do I change the concentration unit", KIN, "en")
    assert score < ai_assistant._NAV_LAUNCH_SCORE


@pytest.mark.parametrize("kw, query, hit", [
    ("merge", "how to merge files", True),
    ("merge", "how to unmerge files", False),
    ("merge", "how to un-merge files", False),
    ("export", "re-export data", False),
    ("select", "deselect the file", False),
    ("calibrat", "calibration mode", True),      # long stems may continue
    ("mode", "model fitting", False),           # short keywords end on a boundary
    ("校准", "如何校准", True),                      # CJK: substring
])
def test_phrase_hit_boundaries(kw, query, hit):
    assert ai_assistant._phrase_hit(kw, query) is hit


# ── A7: overlay keywords ─────────────────────────────────────────────────────

@pytest.mark.parametrize("lang, query", [
    ("fr", "Qu'est-ce que le coefficient Km de Michaelis-Menten ?"),
    ("fr", "Pourquoi mon R² est bas ?"),
    ("fr", "rapide"),
    ("vi", "Tại sao R² của tôi thấp?"),
    ("ru", "Почему мой R² низкий?"),
])
def test_overlay_stop_words_do_not_launch(lang, query):
    assert fires(query, KIN, lang) is None


@pytest.mark.parametrize("lang, query, expected", [
    ("fr", "comment exporter les données", "export_data"),
    ("vi", "cách xuất dữ liệu", "export_data"),
    ("ru", "как экспортировать данные", "export_data"),
])
def test_overlay_nav_queries_still_launch(lang, query, expected):
    assert fires(query, KIN, lang) == expected


@pytest.mark.parametrize("lang", ["vi", "zh", "fr", "ja", "ru", "ko"])
def test_no_overlay_query_is_short_or_a_stop_word(lang):
    with open(os.path.join(ROOT, "guide_translations", f"{lang}.json"), encoding="utf-8") as f:
        overlay = json.load(f)
    bad = []
    for item in overlay:
        for q in item.get("queries", []):
            s = q.strip().lower()
            if ai_assistant._is_cjk(s):
                continue
            if len(s) < 4 or s in ai_assistant._STOPWORDS:
                bad.append((item["id"], q))
    assert not bad, bad


# ── A14: out-of-scope filter ─────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "Where is the time point selection?",
    "stock solution dilution",
    "how do I select a source",
])
def test_app_questions_are_not_refused(query):
    assert ai_assistant._is_out_of_scope(query) is False


@pytest.mark.parametrize("query", [
    "what is the stock price of apple",
    "tell me a joke",
    "recommend a movie",
    "play some music",          # online has no music feature
])
def test_off_topic_is_still_refused(query):
    assert ai_assistant._is_out_of_scope(query) is True


# ── A16: structural mode-switch steps ────────────────────────────────────────

@pytest.mark.parametrize("mode", ["kinetics", "point", "calibrate", "report"])
def test_app_introduction_keeps_step_one_in_every_mode(mode):
    ex = ai_assistant._guide_example_by_id("app_introduction", "en")
    steps = ai_assistant._format_fewshot_hint(ex, {"mode": mode, "data_loaded": True}, "en", steps_only=True)
    assert steps[0]["target"] == ex["steps"][0]["target"]
    assert len(steps) == len(ex["steps"])


@pytest.mark.parametrize("mode", ["kinetics", "point", "calibrate", "report"])
def test_export_excel_nav_same_sequence_in_en_and_vi(mode):
    ctx = {"mode": mode, "data_loaded": True}
    en = ai_assistant._format_fewshot_hint(
        ai_assistant._guide_example_by_id("export_excel_nav", "en"), ctx, "en", steps_only=True)
    vi = ai_assistant._format_fewshot_hint(
        ai_assistant._guide_example_by_id("export_excel_nav", "vi"), ctx, "vi", steps_only=True)
    assert [s["target"] for s in en] == [s["target"] for s in vi]


def test_requires_mode_prepends_localized_switch_step():
    ex = {"id": "x", "queries": [], "requires_mode": "calibrate",
          "steps": [{"target": "#export-coef", "title": "t", "description": "d"}]}
    steps = ai_assistant._format_fewshot_hint(ex, {"mode": "kinetics"}, "vi", steps_only=True)
    assert steps[0]["target"] == "#meas-mode-section"
    assert "calibrate" in steps[0]["description"]
    assert "{mode}" not in steps[0]["description"]
    same = ai_assistant._format_fewshot_hint(ex, {"mode": "calibrate"}, "vi", steps_only=True)
    assert [s["target"] for s in same] == ["#export-coef"]


def test_mode_switch_step_covers_every_language():
    import ai_settings
    langs = set(ai_assistant._MODE_SWITCH_STEP["descriptions"]) | {"en"}
    assert langs == set(ai_settings.SUPPORTED_LANGUAGES)
