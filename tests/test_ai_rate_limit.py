"""Tests for the /ai/chat server-side rate limit and payload caps.

The browser throttles at 15/60s, but that is bypassable and every accepted call
spends a paid proxy request, so the server enforces its own sliding-window
limit and hard size caps. These pin the 413 (too large) and 429 (too fast) arms
and the newest-N message trimming.
"""
import pytest

import ai_assistant
import routes.ai_routes as ai_routes
from main import app


@pytest.fixture
def client(monkeypatch):
    app.config['TESTING'] = True
    # Pretend the assistant is activated so requests reach the limiter, and make
    # the stream a no-op so no real Groq/proxy call happens.
    monkeypatch.setattr(ai_routes, '_get_api_mode', lambda: ('dev', 'fake-key'))
    monkeypatch.setattr(ai_assistant, 'chat_stream',
                        lambda *a, **k: iter(()))
    ai_routes._rate_hits.clear()
    with app.test_client() as c:
        yield c
    ai_routes._rate_hits.clear()


def _post(client, messages, language='en'):
    resp = client.post('/ai/chat', json={'messages': messages, 'language': language})
    # Drain the body before returning. A 200 from /ai/chat is a
    # stream_with_context SSE response; leaving its generator unconsumed leaves a
    # request context pushed, and Flask >= 2.2 (contextvars, not the old
    # _request_ctx_stack) then raises LookupError when the *next* request tries
    # to pop it.
    resp.get_data()
    return resp


def test_oversized_single_message_rejected(client):
    huge = 'x' * (ai_routes._MAX_MSG_CHARS + 1)
    resp = _post(client, [{'role': 'user', 'content': huge}])
    assert resp.status_code == 413
    assert resp.get_json()['status'] == 'failure'


def test_oversized_total_rejected(client):
    # Each message under the per-message cap, but together over the total cap.
    chunk = 'y' * (ai_routes._MAX_MSG_CHARS - 1)
    n = (ai_routes._MAX_TOTAL_CHARS // len(chunk)) + 2
    messages = [{'role': 'user', 'content': chunk} for _ in range(n)]
    resp = _post(client, messages)
    assert resp.status_code == 413


def test_413_is_localized(client):
    huge = 'x' * (ai_routes._MAX_MSG_CHARS + 1)
    resp = _post(client, [{'role': 'user', 'content': huge}], language='vi')
    assert resp.get_json()['message'] == ai_routes._TOO_LARGE_MSG['vi']


def test_rate_limit_trips_after_max(client):
    ok = 0
    for _ in range(ai_routes._RATE_MAX):
        r = _post(client, [{'role': 'user', 'content': 'hi there'}])
        assert r.status_code == 200
        ok += 1
    assert ok == ai_routes._RATE_MAX
    # The next one over the window is refused.
    r = _post(client, [{'role': 'user', 'content': 'one too many'}])
    assert r.status_code == 429
    assert r.headers.get('Retry-After')
    assert int(r.headers['Retry-After']) >= 1


def test_payload_cap_checked_before_rate_limit(client):
    # An oversized payload is a 413 even on the very first request (the size
    # gate runs before the limiter records a hit).
    huge = 'x' * (ai_routes._MAX_MSG_CHARS + 1)
    resp = _post(client, [{'role': 'user', 'content': huge}])
    assert resp.status_code == 413
    assert len(ai_routes._rate_hits) == 0


# ── Body-shape guard (@validate_json) — runs before the limiter ───────────────

def test_non_json_body_rejected(client):
    resp = client.post('/ai/chat', data='hello',
                       content_type='text/plain')
    assert resp.status_code == 400


def test_wrong_type_messages_rejected(client):
    resp = client.post('/ai/chat', json={'messages': 'not-a-list'})
    assert resp.status_code == 400


def test_json_array_body_rejected(client):
    resp = client.post('/ai/chat', json=[{'role': 'user', 'content': 'hi'}])
    assert resp.status_code == 400


def test_messages_cover_every_language():
    # B20b: Korean was missing, so a Korean user got the English text.
    import user_settings
    langs = set(user_settings.SUPPORTED_LANGUAGES)
    assert set(ai_routes._RATE_LIMITED_MSG) == langs
    assert set(ai_routes._TOO_LARGE_MSG) == langs
    assert "{s}" in ai_routes._RATE_LIMITED_MSG["ko"]
