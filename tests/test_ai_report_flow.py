"""Report quick/full clarification on the web chat (work-list A8, A13).

Ported from main's tests/test_ai_report_flow.py: the explicit pending marker,
seven-language vocabulary, the "don't ask" rule shared with main B5, and the
report walkthroughs loaded from guide_training.json by id.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import ai_assistant  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
CTX = {"mode": "kinetics", "data_loaded": True, "app_started": True, "pending": ""}
ARMED = {**CTX, "pending": ai_assistant.PENDING_REPORT_TYPE}
REPORT_CTX = {"mode": "report", "data_loaded": False, "app_started": True, "pending": ""}


def _events(text, ctx=CTX, lang="en", history=None):
    msgs = (history or []) + [{"role": "user", "content": text}]
    return list(ai_assistant.chat_stream(msgs, lang, "k", "m", ctx, {}))


def _no_model(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the model must not be called")
    monkeypatch.setattr(ai_assistant, "_groq_chat", boom)


LANGUAGE_VOCAB = [
    ("en", "how do I make a report", ["quick", "a quick report"], ["full", "the full report"]),
    ("vi", "tạo báo cáo", ["nhanh", "báo cáo nhanh"], ["đầy đủ", "báo cáo đầy đủ"]),
    ("zh", "怎么生成报告", ["快速", "快速报告"], ["完整", "完整报告"]),
    ("fr", "créer un rapport", ["rapide", "rapport rapide"], ["complet", "rapport complète"]),
    ("ja", "レポートの作り方", ["クイック", "クイックレポート"], ["フル", "フルレポート"]),
    ("ru", "как сделать отчёт", ["быстро", "быстрый отчёт"], ["полный", "полная версия"]),
    ("ko", "보고서 만들기", ["빠른", "빠른 보고서"], ["전체", "전체 보고서"]),
]


@pytest.mark.parametrize("lang,ask,quick_answers,full_answers", LANGUAGE_VOCAB,
                         ids=[v[0] for v in LANGUAGE_VOCAB])
def test_every_language_can_ask_and_answer(monkeypatch, lang, ask, quick_answers, full_answers):
    _no_model(monkeypatch)
    ev = _events(ask, CTX, lang)
    assert ev[0]["content"] == ai_assistant._REPORT_CLARIFY_PROMPTS[lang]
    assert {"type": "pending", "pending": ai_assistant.PENDING_REPORT_TYPE} in ev
    for a in quick_answers:
        assert ai_assistant._get_pending_report_type([{"role": "user", "content": a}], ARMED) == "quick"
    for a in full_answers:
        assert ai_assistant._get_pending_report_type([{"role": "user", "content": a}], ARMED) == "full"


def test_french_quick_answer_launches_quick_walkthrough(monkeypatch):
    _no_model(monkeypatch)
    ask = _events("créer un rapport", CTX, "fr")
    assert ask[-1]["type"] == "pending"
    history = [{"role": "user", "content": "créer un rapport"},
               {"role": "assistant", "content": ask[0]["content"]}]
    ev = _events("rapide", ARMED, "fr", history)
    guide = next(e for e in ev if e["type"] == "guide")
    expected = ai_assistant._guide_example_by_id("report_quick", "fr")
    targets = [s["target"] for s in guide["guide_action"]["custom_steps"]]
    assert targets[-1] == expected["steps"][-1]["target"]


@pytest.mark.parametrize("query, ctx", [
    ("what is a report subject", REPORT_CTX),
    ("reporting issue with the chart", CTX),
    ("the chart was reported wrong", CTX),
    ("how do I delete a report subject", REPORT_CTX),
    ("change the report layout watermark", REPORT_CTX),
    ("qu'est-ce qu'un sujet de rapport", REPORT_CTX),
])
def test_report_topic_questions_are_not_asked_quick_or_full(query, ctx):
    assert ai_assistant._needs_report_clarification(query, [{"role": "user", "content": query}], ctx) is False


def test_marker_absent_falls_back_to_prose():
    # A cached (pre-marker) web client: no "pending" key; the previous
    # assistant turn is the clarification prompt verbatim.
    old_ctx = {"mode": "kinetics", "data_loaded": True}
    msgs = [{"role": "user", "content": "make a report"},
            {"role": "assistant", "content": ai_assistant._REPORT_CLARIFY_PROMPTS["en"]},
            {"role": "user", "content": "quick"}]
    assert ai_assistant._get_pending_report_type(msgs, old_ctx) == "quick"
    assert ai_assistant._get_pending_report_type(msgs, CTX) is None


# ── A13: walkthroughs come from guide_training.json ──────────────────────────

def _guide(gid):
    with open(os.path.join(ROOT, "guide_training.json"), encoding="utf-8") as f:
        return next(e for e in json.load(f)["examples"] if e["id"] == gid)


@pytest.mark.parametrize("ctx, gid", [
    ({**ARMED, "mode": "kinetics"}, "report_full_from_data"),
    ({**ARMED, "mode": "report"}, "report_full_in_report"),
])
def test_full_report_steps_equal_the_guide(monkeypatch, ctx, gid):
    _no_model(monkeypatch)
    ev = _events("full", ctx)
    steps = next(e for e in ev if e["type"] == "guide")["guide_action"]["custom_steps"]
    assert [s["target"] for s in steps] == [s["target"] for s in _guide(gid)["steps"]]


def test_subject_step_comes_before_the_console():
    targets = [s["target"] for s in _guide("report_full_from_data")["steps"]]
    assert targets.index("#file-selection") < targets.index("#report-console-section")
    assert targets.index('#measurement-mode button[data-mode="report"]') < targets.index("#file-selection")
    excel = [s["target"] for s in _guide("export_excel_nav")["steps"]]
    assert excel.index("#file-selection") < excel.index('button[onclick="finalizeReportExcel()"]')


def test_quick_report_uses_the_same_guide_ids_as_the_slash_command():
    js = open(os.path.join(ROOT, "static", "script", "ai-chat.js"), encoding="utf-8").read()
    for mode in ("kinetics", "report"):
        assert f"'{ai_assistant._quick_report_guide_id(mode)}'" in js
        assert f"'{ai_assistant._full_report_guide_id(mode)}'" in js


def test_no_step_constants_left():
    for name in ("_QUICK_REPORT_STEPS", "_QUICK_REPORT_STEPS_NO_DATA",
                 "_FULL_REPORT_STEPS_FROM_DATA", "_FULL_REPORT_STEPS_IN_REPORT"):
        assert not hasattr(ai_assistant, name)


@pytest.mark.parametrize("lang", ["vi", "zh", "fr", "ja", "ru", "ko"])
def test_subject_step_is_translated(lang):
    ex = ai_assistant._guide_example_by_id("report_full_from_data", lang)
    en = ai_assistant._guide_example_by_id("report_full_from_data", "en")
    i = [s["target"] for s in en["steps"]].index("#file-selection")
    assert ex["steps"][i]["description"] != en["steps"][i]["description"]


def test_ai_chat_js_sends_the_pending_key():
    js = open(os.path.join(ROOT, "static", "script", "ai-chat.js"), encoding="utf-8").read()
    assert "pending: pending || ''" in js
    assert "event.type === 'pending'" in js
    assert "_getUiContext(pending)" in js


# ── L1: "add to report" / report settings in every language ──────────────────

@pytest.mark.parametrize("query", [
    "thêm vào báo cáo", "ajouter au rapport", "добавить в отчёт", "添加到报告",
    "レポートに追加", "보고서에 추가", "настройки отчёта", "报告格式设置", "paramètres de rapport",
    "report settings",
])
def test_add_to_report_and_report_settings_are_not_asked(query):
    assert ai_assistant._needs_report_clarification(query, [{"role": "user", "content": query}], REPORT_CTX) is False
