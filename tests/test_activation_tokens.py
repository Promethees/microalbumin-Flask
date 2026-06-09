"""Tests for hardware-locked activation tokens (src/download_service.py).

Covers the RS256 issue/validate path and its 'hwid' binding, plus the legacy
HS256 fallback when no signing key is configured.
"""

import os
import sys

import jwt
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import download_service as ds


def _ephemeral_private_pem():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def signing_key(monkeypatch):
    pem = _ephemeral_private_pem()
    monkeypatch.setenv('ACTIVATION_PRIVATE_KEY', pem)
    ds._pubkey_cache.update(pem=None, derived=False)  # force re-derive for this key
    yield pem
    ds._pubkey_cache.update(pem=None, derived=False)


_HWID = 'c' * 64
_PAYLOAD = {'sub': '7', 'email': 'a@b.c', 'purpose': 'app_download', 'exp': 9999999999}


def test_rs256_token_is_hwid_bound_and_validates(signing_key):
    token = ds.issue_activation_token(_PAYLOAD, _HWID)
    assert jwt.get_unverified_header(token)['alg'] == 'RS256'
    payload = ds.validate_activation_token(token)
    assert payload['hwid'] == _HWID
    assert payload['sub'] == '7'
    assert 'exp' not in payload  # permanent token


def test_rs256_token_rejects_tampered_hwid(signing_key):
    token = ds.issue_activation_token(_PAYLOAD, _HWID)
    # Tamper the payload (re-sign with a different key) -> signature fails.
    other = _ephemeral_private_pem()
    forged = jwt.encode({'sub': '7', 'purpose': 'app_download', 'hwid': 'd' * 64},
                        other, algorithm='RS256')
    with pytest.raises(jwt.InvalidTokenError):
        ds.validate_activation_token(forged)


def test_wrong_purpose_rejected(signing_key):
    # issue_activation_token now stamps the canonical 'activation' purpose, so a
    # bad purpose can only arrive via a forged/hand-built token. Sign one with the
    # configured key and confirm validate still enforces the purpose allowlist.
    forged = jwt.encode({'sub': '7', 'purpose': 'something_else'}, signing_key, algorithm='RS256')
    with pytest.raises(jwt.InvalidTokenError):
        ds.validate_activation_token(forged)


def test_rs256_token_carries_activation_purpose(signing_key):
    # New permanent tokens are stamped 'activation' (distinct from the short-lived
    # download token's 'app_download') and still validate.
    token = ds.issue_activation_token(_PAYLOAD, _HWID)
    assert jwt.decode(token, options={'verify_signature': False})['purpose'] == 'activation'
    assert ds.validate_activation_token(token)['purpose'] == 'activation'


def test_validate_accepts_legacy_rs256_app_download_purpose(signing_key):
    # Permanent tokens minted before the split were RS256 with the inherited
    # 'app_download' purpose and no exp — they must keep validating (in-app upgrade
    # continuity for already-activated machines).
    legacy = jwt.encode({'sub': '7', 'purpose': 'app_download', 'hwid': _HWID},
                        signing_key, algorithm='RS256')
    assert ds.validate_activation_token(legacy)['sub'] == '7'


def test_live_download_token_rejected_as_activation(monkeypatch):
    # A live (HS256, exp-bearing) download token shares the 'app_download' purpose
    # but must NOT pass as a permanent activation credential — that was the hole.
    monkeypatch.delenv('ACTIVATION_PRIVATE_KEY', raising=False)
    ds._pubkey_cache.update(pem=None, derived=False)
    monkeypatch.setenv('SECRET_KEY', 'unit-secret')
    dl = ds.generate_download_token(7, 'a@b.c')
    with pytest.raises(jwt.InvalidTokenError):
        ds.validate_activation_token(dl)


def test_expired_download_token_rejected_as_activation(monkeypatch):
    # The old validator skipped exp, so an EXPIRED download token would have been
    # accepted as a permanent license forever. The exp-presence check rejects it.
    monkeypatch.delenv('ACTIVATION_PRIVATE_KEY', raising=False)
    ds._pubkey_cache.update(pem=None, derived=False)
    monkeypatch.setenv('SECRET_KEY', 'unit-secret')
    expired = jwt.encode({'sub': '7', 'purpose': 'app_download', 'exp': 1},
                         'unit-secret', algorithm='HS256')
    with pytest.raises(jwt.InvalidTokenError):
        ds.validate_activation_token(expired)


def test_legacy_hs256_fallback_when_no_key(monkeypatch):
    monkeypatch.delenv('ACTIVATION_PRIVATE_KEY', raising=False)
    ds._pubkey_cache.update(pem=None, derived=False)
    monkeypatch.setenv('SECRET_KEY', 'unit-secret')
    token = ds.issue_activation_token(_PAYLOAD, _HWID)
    assert jwt.get_unverified_header(token)['alg'] == 'HS256'
    payload = jwt.decode(token, options={'verify_signature': False})
    assert 'hwid' not in payload          # never bind on an unverifiable token
    assert ds.validate_activation_token(token)['sub'] == '7'


def test_validate_accepts_legacy_token_even_when_key_configured(signing_key, monkeypatch):
    # A token signed earlier with HS256 (SECRET_KEY) must still validate after the
    # server gains an RS256 key, so existing installs are not locked out.
    monkeypatch.setenv('SECRET_KEY', 'legacy-secret')
    legacy = jwt.encode({'sub': '7', 'purpose': 'app_download'}, 'legacy-secret', algorithm='HS256')
    assert ds.validate_activation_token(legacy)['sub'] == '7'
