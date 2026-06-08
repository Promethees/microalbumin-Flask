"""Tests for hardware-locked token verification (src/activation.py).

These exercise the client-side gate that makes a copied activation.json useless on
another machine: verify_token() must accept only a correctly-signed token whose
'hwid' claim matches this machine.
"""

import os
import time

import jwt
import pytest

import activation

_KEY_DIR = os.path.join(os.path.dirname(__file__), '..', 'keys')
_PRIV_PATH = os.path.join(_KEY_DIR, 'activation_private.pem')

# The committed public key (src/activation_pubkey.py) must pair with this private
# key for the suite to be meaningful; skip cleanly if the private half is absent
# (e.g. a checkout that never generated/keeps it locally).
pytestmark = pytest.mark.skipif(
    not os.path.exists(_PRIV_PATH),
    reason='keys/activation_private.pem not present in this checkout',
)

_THIS_MACHINE = 'a' * 64
_OTHER_MACHINE = 'b' * 64


@pytest.fixture(autouse=True)
def fixed_hwid(monkeypatch):
    """Pin this machine's fingerprint so tests are host-independent."""
    monkeypatch.setattr(activation, 'get_hwid', lambda: _THIS_MACHINE)


def _priv():
    with open(_PRIV_PATH, 'rb') as f:
        return f.read()


def _rs256(claims):
    return jwt.encode(claims, _priv(), algorithm='RS256')


def _hs256(claims, secret='server-secret'):
    return jwt.encode(claims, secret, algorithm='HS256')


def test_valid_token_for_this_machine_is_accepted():
    token = _rs256({'sub': '4', 'purpose': 'app_download', 'hwid': _THIS_MACHINE})
    assert activation.verify_token(token) is not None


def test_token_bound_to_another_machine_is_rejected():
    token = _rs256({'sub': '4', 'purpose': 'app_download', 'hwid': _OTHER_MACHINE})
    assert activation.verify_token(token) is None


def test_forged_signature_is_rejected():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    fake = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    fake_pem = fake.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    token = jwt.encode({'sub': '4', 'purpose': 'app_download', 'hwid': _THIS_MACHINE},
                       fake_pem, algorithm='RS256')
    assert activation.verify_token(token) is None


def test_legacy_hs256_without_hwid_is_grandfathered():
    token = _hs256({'sub': '4', 'purpose': 'app_download'})
    assert activation.verify_token(token) is not None


def test_hs256_claiming_hwid_is_rejected():
    # An unverifiable token that fakes an hwid claim is tampering, not legacy.
    token = _hs256({'sub': '4', 'purpose': 'app_download', 'hwid': _THIS_MACHINE})
    assert activation.verify_token(token) is None


def test_wrong_purpose_is_rejected():
    token = _hs256({'sub': '4', 'purpose': 'password_reset'})
    assert activation.verify_token(token) is None


def test_expired_token_is_rejected():
    token = _rs256({'sub': '4', 'purpose': 'app_download', 'hwid': _THIS_MACHINE,
                    'exp': int(time.time()) - 10})
    assert activation.verify_token(token) is None


def test_garbage_and_empty_are_rejected():
    assert activation.verify_token('not.a.jwt') is None
    assert activation.verify_token('') is None
    assert activation.verify_token(None) is None


def test_is_activated_reflects_verify(monkeypatch):
    good = _rs256({'sub': '4', 'purpose': 'app_download', 'hwid': _THIS_MACHINE})
    monkeypatch.setattr(activation, 'get_license_token', lambda: good)
    assert activation.is_activated() is True

    bad = _rs256({'sub': '4', 'purpose': 'app_download', 'hwid': _OTHER_MACHINE})
    monkeypatch.setattr(activation, 'get_license_token', lambda: bad)
    assert activation.is_activated() is False


# ── ensure_permanent_token() — download → permanent token exchange ─────────────
#
# Every installer persists the user's 30-minute *download* token. ensure_permanent_token
# exchanges that, while still fresh, for a permanent (no-exp) token via /api/activate,
# sending this machine's hwid so the server binds it. These cover the no-op short
# circuits, the happy exchange, and each failure mode that must leave the stored
# token untouched (return False) so a later run can retry.

class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def _expiring():
    return _rs256({'sub': '4', 'purpose': 'app_download', 'hwid': _THIS_MACHINE,
                   'exp': int(time.time()) + 1800})


def _permanent():
    return _rs256({'sub': '4', 'purpose': 'app_download', 'hwid': _THIS_MACHINE})


def _no_network(*_a, **_k):
    raise AssertionError('ensure_permanent_token must not hit the network here')


def test_ensure_noop_when_no_token(monkeypatch):
    monkeypatch.setattr(activation, 'get_license_token', lambda: None)
    monkeypatch.setattr('requests.post', _no_network)
    assert activation.ensure_permanent_token() is False


def test_ensure_noop_when_token_already_permanent(monkeypatch):
    monkeypatch.setattr(activation, 'get_license_token', _permanent)
    monkeypatch.setattr('requests.post', _no_network)
    assert activation.ensure_permanent_token() is False


def test_ensure_exchanges_expiring_token_and_saves(monkeypatch):
    perm = _permanent()
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent['url'] = url
        sent['json'] = json
        return _FakeResp(200, {'license_token': perm})

    saved = {}

    def fake_save(token):
        saved['token'] = token
        return True

    monkeypatch.setattr(activation, 'get_license_token', _expiring)
    monkeypatch.setattr('requests.post', fake_post)
    monkeypatch.setattr(activation, 'save', fake_save)

    assert activation.ensure_permanent_token() is True
    assert saved['token'] == perm
    # the exchange must carry this machine's fingerprint so the server can bind it
    assert sent['json']['hwid'] == _THIS_MACHINE
    assert sent['url'].endswith('/api/activate')


def test_ensure_returns_false_on_non_200(monkeypatch):
    monkeypatch.setattr(activation, 'get_license_token', _expiring)
    monkeypatch.setattr('requests.post', lambda *a, **k: _FakeResp(403, {}))
    monkeypatch.setattr(activation, 'save',
                        lambda t: pytest.fail('must not save on a non-200 response'))
    assert activation.ensure_permanent_token() is False


def test_ensure_returns_false_on_network_error(monkeypatch):
    import requests

    def boom(*_a, **_k):
        raise requests.RequestException('server unreachable')

    monkeypatch.setattr(activation, 'get_license_token', _expiring)
    monkeypatch.setattr('requests.post', boom)
    assert activation.ensure_permanent_token() is False


def test_ensure_returns_false_when_server_returns_no_token(monkeypatch):
    monkeypatch.setattr(activation, 'get_license_token', _expiring)
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: _FakeResp(200, {'license_token': ''}))
    monkeypatch.setattr(activation, 'save',
                        lambda t: pytest.fail('must not save an empty token'))
    assert activation.ensure_permanent_token() is False


def test_ensure_returns_false_when_returned_token_still_expires(monkeypatch):
    # A returned token that still carries 'exp' is the wrong kind — reject, do not save.
    monkeypatch.setattr(activation, 'get_license_token', _expiring)
    monkeypatch.setattr('requests.post',
                        lambda *a, **k: _FakeResp(200, {'license_token': _expiring()}))
    monkeypatch.setattr(activation, 'save',
                        lambda t: pytest.fail('must not save a still-expiring token'))
    assert activation.ensure_permanent_token() is False


# ── RS256 dev fallback (libs missing, not frozen) ─────────────────────────────
#
# When _verify_rs256 cannot verify (None), the meaning of None depends on the
# environment: a frozen build always ships the crypto libs, so None there means a
# bad signature → reject. On a dev box without the libs we cannot check the
# signature at all, so rather than block the developer we fall back to the
# unverified payload and apply ONLY the hwid claim check.

def test_rs256_dev_fallback_accepts_when_libs_unavailable(monkeypatch):
    token = _rs256({'sub': '4', 'hwid': _THIS_MACHINE})
    monkeypatch.setattr(activation, '_verify_rs256', lambda t: None)
    monkeypatch.setattr(activation, '_libs_available', lambda: False)
    monkeypatch.setattr(activation.state, '_is_frozen', lambda: False)
    assert activation.verify_token(token) is not None


def test_rs256_dev_fallback_still_enforces_hwid(monkeypatch):
    token = _rs256({'sub': '4', 'hwid': _OTHER_MACHINE})
    monkeypatch.setattr(activation, '_verify_rs256', lambda t: None)
    monkeypatch.setattr(activation, '_libs_available', lambda: False)
    monkeypatch.setattr(activation.state, '_is_frozen', lambda: False)
    assert activation.verify_token(token) is None


def test_rs256_unverifiable_rejected_when_libs_available(monkeypatch):
    # Libs present → None from _verify_rs256 means a bad signature, not a dev box.
    token = _rs256({'sub': '4', 'hwid': _THIS_MACHINE})
    monkeypatch.setattr(activation, '_verify_rs256', lambda t: None)
    monkeypatch.setattr(activation, '_libs_available', lambda: True)
    monkeypatch.setattr(activation.state, '_is_frozen', lambda: False)
    assert activation.verify_token(token) is None


def test_rs256_unverifiable_rejected_when_frozen(monkeypatch):
    # Frozen build ships the libs, so an unverifiable token is always a bad one.
    token = _rs256({'sub': '4', 'hwid': _THIS_MACHINE})
    monkeypatch.setattr(activation, '_verify_rs256', lambda t: None)
    monkeypatch.setattr(activation, '_libs_available', lambda: False)
    monkeypatch.setattr(activation.state, '_is_frozen', lambda: True)
    assert activation.verify_token(token) is None


# ── RS256 with no hwid claim — not machine-bound ──────────────────────────────

def test_rs256_without_hwid_claim_is_accepted_anywhere():
    # A validly-signed RS256 token carrying no hwid claim is not machine-bound, so
    # the binding check is skipped and it is accepted on any machine.
    assert activation.verify_token(_rs256({'sub': '4', 'purpose': 'app_download'})) is not None


# ── Legacy HS256 kill switch ──────────────────────────────────────────────────

def test_legacy_hs256_refused_when_flag_disabled(monkeypatch):
    # Flipping _ALLOW_LEGACY_HS256 off refuses even a genuine, well-formed legacy token.
    monkeypatch.setattr(activation, '_ALLOW_LEGACY_HS256', False)
    token = _hs256({'sub': '4', 'purpose': 'app_download'})
    assert activation.verify_token(token) is None


# ── needs_activation() gate ───────────────────────────────────────────────────

def test_needs_activation_only_gates_frozen_builds(monkeypatch):
    # Source/dev never gates, regardless of activation state.
    monkeypatch.setattr(activation.state, '_is_frozen', lambda: False)
    monkeypatch.setattr(activation, 'is_activated', lambda: False)
    assert activation.needs_activation() is False

    # Frozen + not activated → must show the gate.
    monkeypatch.setattr(activation.state, '_is_frozen', lambda: True)
    assert activation.needs_activation() is True

    # Frozen + activated → no gate.
    monkeypatch.setattr(activation, 'is_activated', lambda: True)
    assert activation.needs_activation() is False
