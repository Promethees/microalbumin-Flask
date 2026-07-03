"""Tests for the activation HTTP routes (src/routes/ai_routes.py).

The token-exchange logic in activation.ensure_permanent_token() is unit-tested,
but the /ai/activate *route* a fresh DMG/tarball user actually posts to is a
second, parallel copy of that exchange with its own HTTP error mapping — and it
had no coverage. This file pins every exit code: the 400 input guard, the 502
unreachable-server arm, the upstream non-200 pass-through (JSON and non-JSON
bodies), the empty-token 502s, the save-failure 500, and the happy path.

requests.post is patched in every test so nothing hits the network.
"""

import pytest
import requests

import activation
import routes.ai_routes as ai_routes
import state
from main import app

_HWID = 'a' * 64


@pytest.fixture
def client(monkeypatch):
    app.config['TESTING'] = True
    # Dev build → the gate is off, so requests reach the route under test.
    monkeypatch.setattr(activation, 'needs_activation', lambda: False)
    # Pin the fingerprint the route sends so we can assert on it.
    monkeypatch.setattr(activation, 'get_hwid', lambda: _HWID)
    with app.test_client() as c:
        yield c


class _FakeResp:
    """Minimal stand-in for a requests Response; json() can raise ValueError."""

    def __init__(self, status_code=200, payload=None, bad_json=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError('no JSON body')
        return self._payload


def _post(client, body):
    return client.post('/ai/activate', json=body)


# ── 400: input guard ──────────────────────────────────────────────────────────

def test_missing_token_is_400(client, monkeypatch):
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: pytest.fail('must not call the server without a token'))
    rv = _post(client, {})
    assert rv.status_code == 400
    assert rv.get_json()['message'] == 'Token is required'


def test_blank_token_is_400(client, monkeypatch):
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: pytest.fail('must not call the server for a blank token'))
    rv = _post(client, {'token': '   '})
    assert rv.status_code == 400


# ── 502: activation server unreachable ────────────────────────────────────────

def test_network_error_is_502(client, monkeypatch):
    def boom(*_a, **_k):
        raise requests.RequestException('connection refused')

    monkeypatch.setattr('requests.post', boom)
    rv = _post(client, {'token': 'dl-token'})
    assert rv.status_code == 502
    assert 'Could not reach activation server' in rv.get_json()['message']


# ── upstream non-200 is echoed ────────────────────────────────────────────────

def test_upstream_non_200_echoes_status_and_message(client, monkeypatch):
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: _FakeResp(403, {'message': 'token expired'}))
    rv = _post(client, {'token': 'dl-token'})
    assert rv.status_code == 403
    assert rv.get_json()['message'] == 'token expired'


def test_upstream_non_200_with_non_json_body_uses_default_message(client, monkeypatch):
    # resp.json() raising ValueError must fall back to the default message, not 500.
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: _FakeResp(500, bad_json=True))
    rv = _post(client, {'token': 'dl-token'})
    assert rv.status_code == 500
    assert 'Activation failed' in rv.get_json()['message']


# ── 502: server returned no usable token ──────────────────────────────────────

def test_empty_license_token_is_502(client, monkeypatch):
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: _FakeResp(200, {'license_token': ''}))
    monkeypatch.setattr(activation, 'save',
                        lambda t: pytest.fail('must not save an empty token'))
    rv = _post(client, {'token': 'dl-token'})
    assert rv.status_code == 502
    assert 'did not return a license token' in rv.get_json()['message']


def test_success_body_with_bad_json_is_502(client, monkeypatch):
    # A 200 whose body will not parse → license_token '' → 502, not a crash.
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: _FakeResp(200, bad_json=True))
    rv = _post(client, {'token': 'dl-token'})
    assert rv.status_code == 502


# ── 500: persistence failed ───────────────────────────────────────────────────

def test_save_failure_is_500(client, monkeypatch):
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: _FakeResp(200, {'license_token': 'perm-token'}))
    monkeypatch.setattr(activation, 'save', lambda t: False)
    rv = _post(client, {'token': 'dl-token'})
    assert rv.status_code == 500
    assert 'Could not save activation token' in rv.get_json()['message']


# ── 200: happy path ───────────────────────────────────────────────────────────

def test_happy_path_saves_permanent_token_and_sends_hwid(client, monkeypatch):
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent['url'] = url
        sent['json'] = json
        return _FakeResp(200, {'license_token': 'perm-token'})

    saved = {}
    monkeypatch.setattr('requests.post', fake_post)
    monkeypatch.setattr(activation, 'save', lambda t: saved.setdefault('token', t) or True)

    rv = _post(client, {'token': '  dl-token  '})  # surrounding whitespace is stripped
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    # the permanent token from the server is what gets persisted
    assert saved['token'] == 'perm-token'
    # the exchange carries the stripped download token AND this machine's fingerprint
    assert sent['url'].endswith('/api/activate')
    assert sent['json'] == {'token': 'dl-token', 'hwid': _HWID}


# ── /ai/status — _get_api_mode() reporting (proxy / dev / none) ────────────────
#
# The three (api_ready, activated, dev_mode) flags drive the activation UI, and
# each comes from a distinct _get_api_mode() branch: a stored licence token
# (proxy), a dev GROQ_API_KEY with no token (dev), or neither (none).

def test_status_reports_proxy_when_token_is_valid(client, monkeypatch):
    # Proxy mode requires a token that passes the hardware lock (is_activated),
    # not mere presence — so pin is_activated() True, as a verified token would.
    monkeypatch.setattr(activation, 'get_license_token', lambda: 'a-licence-token')
    monkeypatch.setattr(activation, 'is_activated', lambda: True)
    body = client.get('/ai/status').get_json()
    assert body['api_ready'] is True
    assert body['activated'] is True


def test_status_reports_not_activated_for_invalid_token(client, monkeypatch):
    # A stored-but-invalid token (expired / forged / copied from another machine —
    # the hardware-lock scenario) must NOT report activated, even though a token
    # string is present. Keying off presence alone would mislabel it "AI ready"
    # while the gate simultaneously redirects every page to /activate.
    monkeypatch.setattr(activation, 'get_license_token', lambda: 'expired-or-other-machine')
    monkeypatch.setattr(activation, 'is_activated', lambda: False)
    monkeypatch.setattr(ai_routes, '_DEV_GROQ_KEY', '')
    body = client.get('/ai/status').get_json()
    assert body['api_ready'] is False
    assert body['activated'] is False
    assert body['dev_mode'] is False
    assert body['dev_mode'] is False


def test_status_reports_dev_when_only_dev_key_present(client, monkeypatch):
    monkeypatch.setattr(activation, 'get_license_token', lambda: None)
    monkeypatch.setattr(ai_routes, '_DEV_GROQ_KEY', 'gsk-dev')
    body = client.get('/ai/status').get_json()
    assert body['api_ready'] is True
    assert body['activated'] is False
    assert body['dev_mode'] is True


def test_status_reports_none_when_unconfigured(client, monkeypatch):
    monkeypatch.setattr(activation, 'get_license_token', lambda: None)
    monkeypatch.setattr(ai_routes, '_DEV_GROQ_KEY', '')
    body = client.get('/ai/status').get_json()
    assert body['api_ready'] is False
    assert body['activated'] is False
    assert body['dev_mode'] is False


# ── Frozen (installed) build vs source run — AI entitlement split ──────────────
#
# The .env GROQ_API_KEY dev bypass lets a SOURCE run use the chatbot with no
# token, but an INSTALLED build (state.IS_FROZEN) must require a real activation
# token — dropping a .env beside the binary must not unlock the AI. _dev_key()
# enforces that, so both mode selection and the proxy fallback obey it.

def test_frozen_build_ignores_dev_key_so_token_is_mandatory(client, monkeypatch):
    # Installed build with a dev key present but no token → AI stays locked.
    monkeypatch.setattr(state, 'IS_FROZEN', True)
    monkeypatch.setattr(activation, 'get_license_token', lambda: None)
    monkeypatch.setattr(activation, 'is_activated', lambda: False)
    monkeypatch.setattr(ai_routes, '_DEV_GROQ_KEY', 'gsk-dev')
    body = client.get('/ai/status').get_json()
    assert body['api_ready'] is False
    assert body['dev_mode'] is False
    assert body['activated'] is False


def test_frozen_build_still_activates_with_valid_token(client, monkeypatch):
    # The hardware-locked proxy path is unaffected by the frozen flag.
    monkeypatch.setattr(state, 'IS_FROZEN', True)
    monkeypatch.setattr(activation, 'get_license_token', lambda: 'a-licence-token')
    monkeypatch.setattr(activation, 'is_activated', lambda: True)
    body = client.get('/ai/status').get_json()
    assert body['api_ready'] is True
    assert body['activated'] is True


def test_source_run_allows_dev_key_without_token(client, monkeypatch):
    # Mirror image: not frozen + dev key + no token → dev mode unlocks the AI.
    monkeypatch.setattr(state, 'IS_FROZEN', False)
    monkeypatch.setattr(activation, 'get_license_token', lambda: None)
    monkeypatch.setattr(activation, 'is_activated', lambda: False)
    monkeypatch.setattr(ai_routes, '_DEV_GROQ_KEY', 'gsk-dev')
    body = client.get('/ai/status').get_json()
    assert body['api_ready'] is True
    assert body['dev_mode'] is True
    assert body['activated'] is False


# ── _parse_env_value — dotenv value parsing (inline-comment footgun) ───────────
#
# A trailing ' # comment' on a KEY=value line must NOT become part of the value:
# left in, it corrupts e.g. `GROQ_API_KEY=gsk_… # note` so Groq 401s. Quoted
# values are taken verbatim so a literal '#' can still be kept by quoting.

def test_parse_env_value_strips_inline_comment():
    assert ai_routes._parse_env_value('gsk_realkey # my groq key!!!') == 'gsk_realkey'


def test_parse_env_value_plain_value_untouched():
    assert ai_routes._parse_env_value('  gsk_realkey  ') == 'gsk_realkey'


def test_parse_env_value_quoted_keeps_hash():
    assert ai_routes._parse_env_value('"pa#ss word"') == 'pa#ss word'
    assert ai_routes._parse_env_value("'tok#en'") == 'tok#en'


def test_parse_env_value_hash_without_space_is_kept():
    # No whitespace before '#': it is part of the value (standard dotenv rule).
    assert ai_routes._parse_env_value('abc#def') == 'abc#def'


# ── /update/apply — activation guard ──────────────────────────────────────────
#
# The update-apply SSE endpoint is the update-path twin of the gate: it refuses
# to start without a stored token. Only the negative is exercised here — the
# positive path would kick off the real download/apply machinery.

def test_update_apply_refuses_without_token(client, monkeypatch):
    monkeypatch.setattr(activation, 'get_license_token', lambda: None)
    rv = client.post('/update/apply', json={})
    assert rv.status_code == 403
    assert rv.get_json() == {'status': 'error', 'message': 'Not activated'}


# ── 400: body-shape guard (@validate_json) ────────────────────────────────────

def test_non_json_body_is_400(client, monkeypatch):
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: pytest.fail('must not call the server for a non-JSON body'))
    rv = client.post('/ai/activate', data='token=abc',
                     content_type='application/x-www-form-urlencoded')
    assert rv.status_code == 400


def test_json_array_body_is_400(client, monkeypatch):
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: pytest.fail('must not call the server for a non-object body'))
    rv = client.post('/ai/activate', json=['token'])
    assert rv.status_code == 400


def test_wrong_type_token_is_400(client, monkeypatch):
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: pytest.fail('must not call the server for a non-string token'))
    rv = client.post('/ai/activate', json={'token': 123})
    assert rv.status_code == 400
