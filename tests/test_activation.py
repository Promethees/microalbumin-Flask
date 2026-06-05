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
