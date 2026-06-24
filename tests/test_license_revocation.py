"""Client-side admin-revocation enforcement (src/activation.py).

A permanent activation token verifies offline, so the client polls the server
(POST /api/license/check) and caches the verdict in license_status.json. These
tests exercise the cache + the license_state() decision table without any
network or real frozen build:

  * dev / un-activated builds are always 'active' (revocation never interferes);
  * a frozen+activated build is gated by the cached verdict + grace window;
  * a 'revoked' verdict is sticky and survives offline;
  * check_revocation() maps server replies to cache writes, and never flips a
    working install to blocked on a network/`offline` result.
"""
import json
import os
import time

import pytest

import activation


@pytest.fixture
def status_file(tmp_path, monkeypatch):
    path = str(tmp_path / 'license_status.json')
    monkeypatch.setattr(activation, '_STATUS_PATH', path)
    return path


@pytest.fixture
def frozen_activated(monkeypatch):
    """Simulate a frozen build with a cryptographically valid (activated) token."""
    monkeypatch.setattr(activation.state, '_is_frozen', lambda: True)
    monkeypatch.setattr(activation, 'is_activated', lambda: True)
    monkeypatch.setattr(activation, 'get_license_token', lambda: 'tok')
    monkeypatch.setattr(activation, 'get_hwid', lambda: 'a' * 64)


def _write(path, status, age_seconds=0):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'status': status, 'checked_at': time.time() - age_seconds}, f)


# ── license_state() decision table ────────────────────────────────────────────

def test_dev_build_always_active(status_file, monkeypatch):
    monkeypatch.setattr(activation.state, '_is_frozen', lambda: False)
    _write(status_file, 'revoked')  # even a revoked cache is ignored in dev
    assert activation.license_state() == 'active'


def test_unactivated_build_is_active(status_file, monkeypatch):
    monkeypatch.setattr(activation.state, '_is_frozen', lambda: True)
    monkeypatch.setattr(activation, 'is_activated', lambda: False)
    assert activation.license_state() == 'active'


def test_recent_active_passes(status_file, frozen_activated):
    _write(status_file, 'active', age_seconds=60)
    assert activation.license_state() == 'active'


def test_stale_active_needs_recheck(status_file, frozen_activated):
    _write(status_file, 'active', age_seconds=activation._grace_seconds() + 100)
    assert activation.license_state() == 'needs_recheck'


def test_no_cache_needs_recheck(status_file, frozen_activated):
    assert activation.license_state() == 'needs_recheck'


def test_revoked_is_sticky(status_file, frozen_activated):
    _write(status_file, 'revoked', age_seconds=999999)  # stale, still blocks
    assert activation.license_state() == 'revoked'
    assert activation.license_blocked() is True


def test_grace_env_override(status_file, frozen_activated, monkeypatch):
    monkeypatch.setenv('LICENSE_GRACE_SECONDS', '3600')
    _write(status_file, 'active', age_seconds=7200)  # older than 1h override
    assert activation.license_state() == 'needs_recheck'


# ── check_revocation() network mapping ────────────────────────────────────────

class _Resp:
    def __init__(self, code, payload):
        self.status_code = code
        self._payload = payload
    def json(self):
        return self._payload


def _patch_post(monkeypatch, resp=None, raise_exc=False):
    def fake_post(url, **kw):
        if raise_exc:
            raise RuntimeError('no network')
        return resp
    import requests
    monkeypatch.setattr(requests, 'post', fake_post)


def test_check_revocation_active_writes_cache(status_file, frozen_activated, monkeypatch):
    _patch_post(monkeypatch, _Resp(200, {'status': 'active'}))
    assert activation.check_revocation() == 'active'
    assert json.load(open(status_file))['status'] == 'active'


def test_check_revocation_revoked_writes_cache(status_file, frozen_activated, monkeypatch):
    _patch_post(monkeypatch, _Resp(200, {'status': 'revoked'}))
    assert activation.check_revocation() == 'revoked'
    assert json.load(open(status_file))['status'] == 'revoked'


def test_check_revocation_offline_leaves_cache_untouched(status_file, frozen_activated, monkeypatch):
    _write(status_file, 'active', age_seconds=60)
    _patch_post(monkeypatch, raise_exc=True)
    assert activation.check_revocation() == 'offline'
    assert json.load(open(status_file))['status'] == 'active'  # unchanged


def test_check_revocation_non200_is_offline(status_file, frozen_activated, monkeypatch):
    _patch_post(monkeypatch, _Resp(401, {'status': 'error'}))
    assert activation.check_revocation() == 'offline'
    assert not os.path.exists(status_file)  # nothing written


# ── account ban (distinct from per-machine revocation) ────────────────────────

def test_banned_is_sticky(status_file, frozen_activated):
    _write(status_file, 'banned', age_seconds=999999)  # stale, still blocks
    assert activation.license_state() == 'banned'
    assert activation.license_blocked() is True


def test_check_revocation_banned_writes_cache(status_file, frozen_activated, monkeypatch):
    # Server reports a ban as status 'revoked' + code 'account_banned'.
    _patch_post(monkeypatch, _Resp(200, {'status': 'revoked', 'code': 'account_banned'}))
    assert activation.check_revocation() == 'banned'
    assert json.load(open(status_file))['status'] == 'banned'


def test_check_revocation_revoked_without_ban_code_stays_revoked(status_file, frozen_activated, monkeypatch):
    # A plain seat revocation (other code, or none) must NOT be cached as banned.
    _patch_post(monkeypatch, _Resp(200, {'status': 'revoked', 'code': 'machine_mismatch'}))
    assert activation.check_revocation() == 'revoked'
    assert json.load(open(status_file))['status'] == 'revoked'
