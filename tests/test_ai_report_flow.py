"""Tests for the report quick/full clarification flow and streamed chat loop.

Guards:
  * the clarification question is asked AND its answer understood in every UI
    language, not English only (the old substring check silently broke for
    vi/zh/fr/ja/ru);
  * chat_stream relays streamed content deltas live and still reassembles tool
    calls from their streamed argument fragments.
"""
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import ai_assistant  # noqa: E402


# ── Report clarification (multilingual) ──────────────────────────────────────

@pytest.mark.parametrize("lang,report_q,quick_a,full_a", [
    ("en", "how do I make a report", "quick one please", "the full one"),
    ("vi", "làm báo cáo thế nào", "nhanh thôi", "đầy đủ nhé"),
    ("zh", "怎么生成报告", "快速", "完整"),
    ("fr", "comment créer un rapport", "rapide", "complet"),
    ("ja", "レポートの作り方", "クイック", "フル"),
    ("ru", "как сделать отчёт", "быстро", "полный"),
])
def test_report_clarification_roundtrip_all_languages(lang, report_q, quick_a, full_a):
    # 1) A bare report ask (no quick/full hint) triggers the clarification.
    assert ai_assistant._needs_report_clarification(report_q, [{"role": "user", "content": report_q}])

    clarify = ai_assistant._REPORT_CLARIFY_PROMPTS[lang]

    # 2) With the clarify prompt as the prior assistant turn, the user's answer resolves.
    quick_msgs = [
        {"role": "user", "content": report_q},
        {"role": "assistant", "content": clarify},
        {"role": "user", "content": quick_a},
    ]
    assert ai_assistant._get_pending_report_type(quick_msgs) == "quick"

    full_msgs = [
        {"role": "user", "content": report_q},
        {"role": "assistant", "content": clarify},
        {"role": "user", "content": full_a},
    ]
    assert ai_assistant._get_pending_report_type(full_msgs) == "full"


def test_no_reask_after_clarify_prompt():
    msgs = [
        {"role": "user", "content": "make a report"},
        {"role": "assistant", "content": ai_assistant._REPORT_CLARIFY_PROMPTS["en"]},
        {"role": "user", "content": "make a report"},
    ]
    assert ai_assistant._needs_report_clarification("make a report", msgs) is False


def test_specific_report_kind_skips_clarification():
    assert ai_assistant._needs_report_clarification("create a quick report", []) is False
    assert ai_assistant._needs_report_clarification("export data to report", []) is False


def test_non_report_query_no_clarification():
    assert ai_assistant._needs_report_clarification("what is R squared", []) is False


# ── Streamed chat loop ───────────────────────────────────────────────────────

def _fake_stream(events):
    """Build a _groq_chat_stream stand-in yielding the given (kind, payload)s."""
    def _gen(api_key, model, messages, tools):
        for e in events:
            yield e
    return _gen


def test_chat_stream_relays_content_deltas(monkeypatch):
    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", _fake_stream([
        ("chunk", "Hel"),
        ("chunk", "lo"),
        ("result", {"role": "assistant", "content": "Hello"}),
    ]))
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "explain R squared please"}], "en", "k", "m", {}))
    chunks = [e["content"] for e in events if e.get("type") == "chunk"]
    assert chunks == ["Hel", "lo"]
    assert all(e.get("type") != "error" for e in events)


def test_chat_stream_surfaces_error(monkeypatch):
    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", _fake_stream([
        ("result", {"role": "assistant", "content": "", "error": "rate_limit"}),
    ]))
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "explain R squared please"}], "en", "k", "m", {}))
    assert any(e.get("type") == "error" and e.get("error") == "rate_limit" for e in events)


# ── Invalid-tool-call recovery ───────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "Failed to call a function. Please adjust your prompt. See 'failed_generation' for more details.",
    "tool call validation failed: parameters for tool get_help_topic did not match schema",
    "Error code: 400 - {'code': 'tool_use_failed'}",
])
def test_map_groq_error_detects_tool_failure(raw):
    assert ai_assistant._map_groq_error(raw) == "tool_call_failed"


def test_chat_stream_recovers_from_tool_call_failure(monkeypatch):
    # First call (tools enabled) → Groq rejects the invalid tool call; the loop
    # must retry the same turn with tools disabled and stream the plain answer.
    calls = []

    def fake(api_key, model, messages, tools):
        calls.append(tools)
        if tools:
            yield ("result", {"role": "assistant", "content": "", "error": "tool_call_failed"})
        else:
            yield ("chunk", "This is a colorimeter data app.")
            yield ("result", {"role": "assistant", "content": "This is a colorimeter data app."})

    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", fake)
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "what is this software about"}], "en", "k", "m", {}))

    assert all(e.get("type") != "error" for e in events)
    text = "".join(e["content"] for e in events if e.get("type") == "chunk")
    assert "colorimeter" in text
    assert calls == [ai_assistant.TOOLS, None]  # retried once with tools off


def test_chat_stream_persistent_tool_failure_surfaces_code(monkeypatch):
    # If it keeps failing even without tools, surface the stable code (the
    # frontend renders it as a friendly message) — and don't loop forever.
    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", _fake_stream([
        ("result", {"role": "assistant", "content": "", "error": "tool_call_failed"}),
    ]))
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "what is this software about"}], "en", "k", "m", {}))
    assert any(e.get("type") == "error" and e.get("error") == "tool_call_failed" for e in events)
