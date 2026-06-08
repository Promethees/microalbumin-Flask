"""Tests for src/update_service.py request auth headers.

_auth_headers() applies the hardware lock to the update path (not just the
activation gate): /api/version and /api/download carry both the bearer license
token AND this machine's fingerprint, so the server can reject a token presented
from a machine other than the one it was bound to. The non-obvious behaviour
here is that X-Machine-Id is sent UNCONDITIONALLY — only the Authorization
header is gated on a token being present.
"""

import update_service


def test_auth_headers_includes_bearer_and_machine_id(monkeypatch):
    monkeypatch.setattr(update_service.activation_mod, 'get_hwid', lambda: 'HW-DIGEST')
    headers = update_service._auth_headers('tok-abc')
    assert headers['Authorization'] == 'Bearer tok-abc'
    assert headers['X-Machine-Id'] == 'HW-DIGEST'


def test_auth_headers_omits_authorization_when_token_is_none(monkeypatch):
    monkeypatch.setattr(update_service.activation_mod, 'get_hwid', lambda: 'HW-DIGEST')
    headers = update_service._auth_headers(None)
    assert 'Authorization' not in headers
    # the fingerprint is still sent so an unauthenticated version check is attributable
    assert headers['X-Machine-Id'] == 'HW-DIGEST'


def test_auth_headers_omits_authorization_for_empty_token(monkeypatch):
    monkeypatch.setattr(update_service.activation_mod, 'get_hwid', lambda: 'HW-DIGEST')
    headers = update_service._auth_headers('')
    assert 'Authorization' not in headers
    assert headers['X-Machine-Id'] == 'HW-DIGEST'
