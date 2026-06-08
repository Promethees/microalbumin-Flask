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
