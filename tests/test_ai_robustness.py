"""Robustness + dev/proxy-consistency tests for the AI chat path.

Guards the hardening work:
  * `deterministic_events` is the single source of the no-LLM turns (greeting,
    out-of-scope refusal, report quick/full clarification) shared by BOTH the
    dev and proxy paths, so an activated user gets the same behaviour as a
    source run;
  * /ai/chat short-circuits those turns before dispatching to either backend
    (no upstream call spent);
  * a length-truncated answer is flagged with a continuable notice instead of
    cutting off silently;
  * an empty model reply is retried once (tools off) rather than dead-ending.
"""
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import ai_assistant  # noqa: E402
import routes.ai_routes as ai_routes  # noqa: E402
from main import app  # noqa: E402


KIN_DATA = {"mode": "kinetics", "data_loaded": True, "app_started": True}
KIN_NODATA = {"mode": "kinetics", "data_loaded": False, "app_started": True}


# ── deterministic_events: the shared no-LLM layer ────────────────────────────

def _last_chunk_text(events):
    return "".join(e.get("content", "") for e in (events or []) if e.get("type") == "chunk")


@pytest.mark.parametrize("lang", ["en", "vi", "zh", "fr", "ja", "ru"])
def test_greeting_resolved_locally(lang):
    events = ai_assistant.deterministic_events(
        [{"role": "user", "content": "hello"}], lang, KIN_DATA)
    assert events is not None
    assert _last_chunk_text(events) == ai_assistant._GREETING_RESPONSE[lang]


def test_out_of_scope_resolved_locally():
    events = ai_assistant.deterministic_events(
        [{"role": "user", "content": "write me a poem about the weather"}], "en", KIN_DATA)
    assert events is not None
    assert _last_chunk_text(events) == ai_assistant._OUT_OF_SCOPE["en"]


def test_report_clarification_asked_locally():
    events = ai_assistant.deterministic_events(
        [{"role": "user", "content": "how do I make a report"}], "en", KIN_DATA)
    assert events is not None
    assert _last_chunk_text(events) == ai_assistant._REPORT_CLARIFY_PROMPTS["en"]


def test_pending_report_quick_emits_guide():
    msgs = [
        {"role": "user", "content": "make a report"},
        {"role": "assistant", "content": ai_assistant._REPORT_CLARIFY_PROMPTS["en"]},
        {"role": "user", "content": "quick please"},
    ]
    events = ai_assistant.deterministic_events(msgs, "en", KIN_DATA)
    assert events is not None
    assert any(e.get("type") == "guide" for e in events)


def test_normal_question_returns_none():
    # A real question must fall through to the model (None), not be short-circuited.
    events = ai_assistant.deterministic_events(
        [{"role": "user", "content": "explain what R squared means"}], "en", KIN_DATA)
    assert events is None


def test_chat_stream_delegates_to_deterministic(monkeypatch):
    # chat_stream must not call the model for a greeting.
    def _boom(*a, **k):
        raise AssertionError("model was called for a greeting")
        yield  # pragma: no cover
    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", _boom)
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "hi there"}], "en", "k", "m", KIN_DATA))
    assert _last_chunk_text(events) == ai_assistant._GREETING_RESPONSE["en"]


# ── Truncation notice ────────────────────────────────────────────────────────

def _fake_stream(events):
    def _gen(api_key, model, messages, tools):
        for e in events:
            yield e
    return _gen


def test_truncated_answer_gets_notice(monkeypatch):
    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", _fake_stream([
        ("chunk", "The coefficient a is the sensitivity"),
        ("result", {"role": "assistant",
                    "content": "The coefficient a is the sensitivity",
                    "finish_reason": "length"}),
    ]))
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "explain the linear coefficients"}], "en", "k", "m", KIN_DATA))
    text = _last_chunk_text(events)
    assert ai_assistant._TRUNCATION_NOTICE["en"] in text


def test_finish_reason_not_sent_back_to_groq(monkeypatch):
    # Regression: finish_reason is our own out-of-band signal, not a valid chat
    # message field. When a tool turn's assistant message is appended to the
    # history and re-sent, it must NOT carry finish_reason, or Groq 400s with
    # "property 'finish_reason' is unsupported".
    seen_messages = []

    def fake(api_key, model, messages, tools):
        seen_messages.append([dict(m) for m in messages])
        if len(seen_messages) == 1:
            # First turn: a tool call (finish_reason == "tool_calls").
            yield ("result", {
                "role": "assistant", "content": "", "finish_reason": "tool_calls",
                "tool_calls": [{"id": "c1", "type": "function",
                                "function": {"name": "get_app_context", "arguments": "{}"}}],
            })
        else:
            yield ("chunk", "You have 3 folders.")
            yield ("result", {"role": "assistant", "content": "You have 3 folders.",
                              "finish_reason": "stop"})

    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", fake)
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "how many folders do I have"}], "en", "k", "m", KIN_DATA))
    assert "You have 3 folders." in _last_chunk_text(events)
    # The second call's message history includes the prior assistant turn — none
    # of the messages sent upstream may carry a finish_reason.
    assert len(seen_messages) >= 2
    for msg in seen_messages[1]:
        assert "finish_reason" not in msg


def test_complete_answer_has_no_notice(monkeypatch):
    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", _fake_stream([
        ("chunk", "R squared measures goodness of fit."),
        ("result", {"role": "assistant",
                    "content": "R squared measures goodness of fit.",
                    "finish_reason": "stop"}),
    ]))
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "explain R squared"}], "en", "k", "m", KIN_DATA))
    assert ai_assistant._TRUNCATION_NOTICE["en"] not in _last_chunk_text(events)


# ── Empty-reply retry ────────────────────────────────────────────────────────

def test_empty_reply_retries_without_tools(monkeypatch):
    calls = []

    def fake(api_key, model, messages, tools):
        calls.append(tools)
        if tools is not None:
            # First attempt: nothing at all (no content, no tool call).
            yield ("result", {"role": "assistant", "content": "", "finish_reason": "stop"})
        else:
            yield ("chunk", "Here is the answer.")
            yield ("result", {"role": "assistant", "content": "Here is the answer.",
                              "finish_reason": "stop"})

    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", fake)
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "explain the kinetics mode coefficients"}],
        "en", "k", "m", KIN_DATA))
    assert "Here is the answer." in _last_chunk_text(events)
    assert calls == [ai_assistant.TOOLS, None]  # retried once with tools off
    assert all(e.get("type") != "error" for e in events)


def test_persistent_empty_reply_ends_cleanly(monkeypatch):
    # Empty even without tools → give up quietly (client shows its own fallback),
    # never loop forever or surface a raw error.
    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", _fake_stream([
        ("result", {"role": "assistant", "content": "", "finish_reason": "stop"}),
    ]))
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "explain the kinetics mode coefficients"}],
        "en", "k", "m", KIN_DATA))
    assert _last_chunk_text(events) == ""
    assert all(e.get("type") != "error" for e in events)


# ── Route-level: proxy path short-circuits deterministic turns ───────────────

@pytest.fixture
def proxy_client(monkeypatch):
    """A client in PROXY (activated) mode with the proxy stream stubbed to blow
    up — so any test that reaches the proxy fails loudly."""
    app.config['TESTING'] = True
    monkeypatch.setattr(ai_routes, '_get_api_mode', lambda: ('proxy', 'fake-token'))

    def _proxy_must_not_be_called(*a, **k):
        raise AssertionError("proxy was called for a deterministic turn")
        yield  # pragma: no cover
    monkeypatch.setattr(ai_assistant, 'proxy_chat_stream', _proxy_must_not_be_called)
    ai_routes._rate_hits.clear()
    with app.test_client() as c:
        yield c
    ai_routes._rate_hits.clear()


def _collect_sse(resp):
    return resp.get_data(as_text=True)


def test_proxy_greeting_short_circuits(proxy_client):
    resp = proxy_client.post('/ai/chat', json={
        'messages': [{'role': 'user', 'content': 'hello'}],
        'language': 'en',
    })
    assert resp.status_code == 200
    body = _collect_sse(resp)
    assert ai_assistant._GREETING_RESPONSE['en'] in body
    assert '[DONE]' in body


def test_proxy_report_clarify_short_circuits(proxy_client):
    resp = proxy_client.post('/ai/chat', json={
        'messages': [{'role': 'user', 'content': 'how do I make a report'}],
        'language': 'en',
        'ui_context': KIN_DATA,
    })
    assert resp.status_code == 200
    assert ai_assistant._REPORT_CLARIFY_PROMPTS['en'] in _collect_sse(resp)


def test_proxy_real_question_reaches_proxy(monkeypatch):
    # A genuine question is NOT short-circuited: it must dispatch to the proxy.
    app.config['TESTING'] = True
    monkeypatch.setattr(ai_routes, '_get_api_mode', lambda: ('proxy', 'fake-token'))
    reached = {'hit': False}

    def _proxy(*a, **k):
        reached['hit'] = True
        yield {'type': 'chunk', 'content': 'from proxy'}
    monkeypatch.setattr(ai_assistant, 'proxy_chat_stream', _proxy)
    ai_routes._rate_hits.clear()
    with app.test_client() as c:
        resp = c.post('/ai/chat', json={
            'messages': [{'role': 'user', 'content': 'explain what R squared means'}],
            'language': 'en',
            'ui_context': KIN_DATA,
        })
        assert resp.status_code == 200
        assert 'from proxy' in _collect_sse(resp)
    ai_routes._rate_hits.clear()
    assert reached['hit']
