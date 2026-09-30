"""Robustness of the server's chat loop (src/ai_assistant.py:chat_stream).

Ported from main's tests/test_ai_robustness.py (work-list item A1). The proxy
serves every activated desktop build, so these guard the behaviours that rescue
builds already in the field:

  * a botched tool call (Groq 400 tool_use_failed) is retried once with tools
    off, and the user gets the plain-text answer, not an error;
  * an empty reply is retried once with tools off;
  * a length-truncated answer is followed by a continuable notice;
  * an unknown upstream exception becomes the stable code `upstream_error` —
    the raw exception text never reaches any SSE event.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import ai_assistant  # noqa: E402

KIN_DATA = {"mode": "kinetics", "data_loaded": True, "app_started": True}
# A question no guide matches and no fast path catches, so it reaches the model.
QUESTION = [{"role": "user", "content": "xyzzy plugh"}]


def _text(events):
    return "".join(e.get("content", "") for e in events if e.get("type") == "chunk")


def _run(messages=QUESTION, **kw):
    return list(ai_assistant.chat_stream(messages, "en", "k", "m", KIN_DATA, {}, **kw))


def test_tool_use_failed_retries_without_tools(monkeypatch):
    calls = []

    def fake(api_key, model, messages, tools):
        calls.append(tools)
        if tools:
            return {"role": "assistant", "content": "", "error": "tool_call_failed"}
        return {"role": "assistant", "content": "Plain answer.", "finish_reason": "stop"}

    monkeypatch.setattr(ai_assistant, "_groq_chat", fake)
    events = _run()
    assert _text(events) == "Plain answer."
    assert not any(e.get("type") == "error" for e in events)
    assert calls[0] and calls[1] is None      # second call had tools off


def test_groq_tool_use_failed_exception_maps_to_retryable_code():
    raw = "Error code: 400 - {'error': {'code': 'tool_use_failed', 'message': 'x'}}"
    assert ai_assistant._map_groq_error(raw) == "tool_call_failed"


def test_truncated_reply_gets_notice(monkeypatch):
    monkeypatch.setattr(ai_assistant, "_groq_chat", lambda *a: {
        "role": "assistant", "content": "The slope a is", "finish_reason": "length"})
    events = _run()
    assert _text(events).endswith(ai_assistant._TRUNCATION_NOTICE["en"])


def test_complete_reply_has_no_notice(monkeypatch):
    monkeypatch.setattr(ai_assistant, "_groq_chat", lambda *a: {
        "role": "assistant", "content": "Done.", "finish_reason": "stop"})
    assert ai_assistant._TRUNCATION_NOTICE["en"] not in _text(_run())


def test_truncation_notice_covers_every_language():
    import ai_settings
    assert set(ai_assistant._TRUNCATION_NOTICE) == set(ai_settings.SUPPORTED_LANGUAGES)


def test_generic_exception_is_upstream_error_without_raw_text(monkeypatch):
    secret = "ConnectionError: host=internal-groq-7.example req_id=abc123 SECRET"

    class _Boom:
        def __init__(self, *a, **k):
            pass

        @property
        def chat(self):
            raise RuntimeError(secret)

    import types
    fake_mod = types.SimpleNamespace(Groq=_Boom)
    monkeypatch.setitem(sys.modules, "groq", fake_mod)
    events = _run()
    assert events == [{"type": "error", "error": "upstream_error"}]
    assert all("SECRET" not in json.dumps(e) for e in events)


def test_unmapped_error_code_is_never_forwarded(monkeypatch):
    # Even if a stub returns a raw string as the error, the loop only emits
    # stable codes.
    monkeypatch.setattr(ai_assistant, "_groq_chat", lambda *a: {
        "role": "assistant", "content": "", "error": "Traceback: secret"})
    events = _run()
    assert events == [{"type": "error", "error": "upstream_error"}]


def test_empty_reply_retries_once_without_tools(monkeypatch):
    calls = []

    def fake(api_key, model, messages, tools):
        calls.append(tools)
        if tools:
            return {"role": "assistant", "content": "", "finish_reason": "stop"}
        return {"role": "assistant", "content": "Here it is.", "finish_reason": "stop"}

    monkeypatch.setattr(ai_assistant, "_groq_chat", fake)
    events = _run()
    assert _text(events) == "Here it is."
    assert len(calls) == 2 and calls[1] is None


def test_persistent_empty_reply_ends_cleanly(monkeypatch):
    monkeypatch.setattr(ai_assistant, "_groq_chat", lambda *a: {
        "role": "assistant", "content": "", "finish_reason": "stop"})
    events = _run()
    assert _text(events) == ""
    assert not any(e.get("type") == "error" for e in events)


def test_finish_reason_never_sent_back_upstream(monkeypatch):
    seen = []

    def fake(api_key, model, messages, tools):
        seen.append([dict(m) for m in messages])
        if len(seen) == 1:
            return {"role": "assistant", "content": "", "finish_reason": "tool_calls",
                    "tool_calls": [{"id": "c1", "type": "function",
                                    "function": {"name": "get_help_topic",
                                                 "arguments": '{"topic": "regression"}'}}]}
        return {"role": "assistant", "content": "ok", "finish_reason": "stop"}

    monkeypatch.setattr(ai_assistant, "_groq_chat", fake)
    _run()
    assert len(seen) == 2
    assert all("finish_reason" not in m for m in seen[1])


@pytest.mark.parametrize("code", ["api_key_invalid", "rate_limit"])
def test_known_codes_pass_through(monkeypatch, code):
    monkeypatch.setattr(ai_assistant, "_groq_chat", lambda *a: {
        "role": "assistant", "content": "", "error": code})
    assert _run() == [{"type": "error", "error": code}]
