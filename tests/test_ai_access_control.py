"""Access control + rate limiting for the AI endpoints (src/routes/ai_routes.py).

Two protections are exercised against the REAL ai_bp blueprint:

  * #1 — /ai/chat (which spends the server's Groq key) requires a logged-in
    session. Without it the endpoint would be an open door to the paid key.
  * #3 — both /ai/chat and /ai/proxy/chat are rate limited (Flask-Limiter), so a
    single client cannot drain the Groq quota / DoS the key.

The blueprint is registered on a minimal app (not main.py, which pulls in
SocketIO/Firebase/eventlet). Limits are read from the rate_limit constants so the
tests do not hard-code the numbers.
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from routes.ai_routes import ai_bp
from rate_limit import limiter, AI_CHAT_LIMIT, AI_PROXY_LIMIT


def _count(limit_str):
    """'30 per minute' -> 30."""
    return int(limit_str.split()[0])


@pytest.fixture(scope='module')
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    limiter.init_app(app)
    app.register_blueprint(ai_bp)
    return app


@pytest.fixture
def client(app):
    # Clear the (shared, in-memory) limiter counters before each test so the
    # per-route limits start fresh and tests do not leak into one another.
    with app.app_context():
        limiter.reset()
    return app.test_client()


# ── #1: /ai/chat requires login ───────────────────────────────────────────────

def test_chat_requires_login(client):
    r = client.post('/ai/chat', json={'messages': [{'role': 'user', 'content': 'hi'}]})
    assert r.status_code == 401
    assert r.get_json()['code'] == 'auth_required'


def test_chat_passes_gate_when_logged_in(client, monkeypatch):
    # With a session the auth gate is cleared. Pin GROQ_API_KEY empty so the view
    # deterministically takes the no-key 503 path: a 503 (not 401) proves the gate
    # let the request through rather than blocking it. (Pinned because Config reads
    # the key once at import, so the ambient env must not decide the outcome.)
    from config import Config
    monkeypatch.setattr(Config, 'GROQ_API_KEY', '')
    with client.session_transaction() as sess:
        sess['account_user_id'] = 7
    r = client.post('/ai/chat', json={'messages': [{'role': 'user', 'content': 'hi'}]})
    assert r.status_code == 503


# ── #3: rate limiting on the AI endpoints ─────────────────────────────────────

def test_chat_is_rate_limited(client):
    limit = _count(AI_CHAT_LIMIT)
    codes = [client.post('/ai/chat', json={}).status_code for _ in range(limit + 1)]
    assert codes[-1] == 429                       # the (limit+1)-th request is throttled
    assert all(c == 401 for c in codes[:limit])   # earlier ones hit the auth gate, not the limiter


def test_proxy_chat_is_rate_limited(client):
    limit = _count(AI_PROXY_LIMIT)
    codes = [client.post('/ai/proxy/chat', json={}).status_code for _ in range(limit + 1)]
    assert codes[-1] == 429
    assert all(c == 401 for c in codes[:limit])   # missing license_token → 401 before the limiter trips


# ── #4: the model is the server's choice, not the caller's ────────────────────
# A desktop build sends whatever model id was current when it was frozen, and a
# binary cannot be edited afterwards — installed copies kept asking Groq for
# `llama-3.1-8b-instant` after it was retired and 404'd every chat. The proxy
# therefore ignores data['model'] so one Heroku config var moves every client,
# shipped or not, onto a live model. See Rule.md §2.13.

def test_proxy_chat_ignores_a_client_supplied_model(client, monkeypatch):
    from config import Config
    import routes.ai_routes as ai_routes
    import routes.account_routes as account_routes

    monkeypatch.setattr(Config, 'GROQ_API_KEY', 'test-key')
    monkeypatch.setattr(Config, 'AI_MODEL', 'server/model')
    monkeypatch.setattr(ai_routes, 'validate_activation_token', lambda t: {'sub': '7'})
    monkeypatch.setattr(ai_routes, 'get_user_data', lambda user_id=None: {})
    monkeypatch.setattr(account_routes, '_machine_is_licensed', lambda *a, **k: True)

    # Swap the model itself: patching User.query on the real SQLAlchemy model
    # still reaches the session and needs an app context.
    class _User:
        is_verified = True
        id = 7

    class _FakeUserModel:
        query = type('Q', (), {'get': staticmethod(lambda _id: _User())})()

    monkeypatch.setattr(ai_routes, 'User', _FakeUserModel)

    used = {}

    def fake_stream(messages, language, api_key, model, *args, **kwargs):
        used['model'] = model
        return iter([])

    monkeypatch.setattr(ai_routes.ai_assistant, 'chat_stream', fake_stream)

    r = client.post('/ai/proxy/chat', json={
        'messages': [{'role': 'user', 'content': 'hi'}],
        'license_token': 'tok',
        'model': 'llama-3.1-8b-instant',   # a retired id from an old frozen build
    })
    assert r.status_code == 200
    r.get_data()                            # drain the stream so the generator runs
    assert used['model'] == 'server/model'
