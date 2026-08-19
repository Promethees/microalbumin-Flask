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


# ── why an 'offline' verdict happened (reverify gate messaging) ───────────────
# "Check your connection" is the wrong advice when the connection is fine and our
# service is the thing that is down, so check_revocation_detailed() classifies the
# failure. The network probes are patched out here — these tests assert the
# decision table, not the machine's real connectivity.

def _patch_probes(monkeypatch, online=True, resolves=True):
    monkeypatch.setattr(activation, 'internet_reachable', lambda force=False: online)
    monkeypatch.setattr(activation, '_service_host_resolves', lambda: resolves)


def test_detailed_active_has_no_reason(status_file, frozen_activated, monkeypatch):
    _patch_post(monkeypatch, _Resp(200, {'status': 'active'}))
    assert activation.check_revocation_detailed() == ('active', None)


def test_detailed_no_token(status_file, monkeypatch):
    monkeypatch.setattr(activation, 'get_license_token', lambda: None)
    assert activation.check_revocation_detailed() == ('offline', 'no_token')


def test_detailed_no_internet(status_file, frozen_activated, monkeypatch):
    _patch_post(monkeypatch, raise_exc=True)
    _patch_probes(monkeypatch, online=False)
    assert activation.check_revocation_detailed() == ('offline', 'no_internet')


def test_detailed_dns_failure(status_file, frozen_activated, monkeypatch):
    _patch_post(monkeypatch, raise_exc=True)
    _patch_probes(monkeypatch, online=True, resolves=False)
    assert activation.check_revocation_detailed() == ('offline', 'dns_failure')


def test_detailed_service_down_on_connect_failure(status_file, frozen_activated, monkeypatch):
    # Machine is online and our name resolves — so the outage is ours.
    _patch_post(monkeypatch, raise_exc=True)
    _patch_probes(monkeypatch, online=True, resolves=True)
    assert activation.check_revocation_detailed() == ('offline', 'service_down')


@pytest.mark.parametrize('code', [401, 500, 502, 503])
def test_detailed_non200_is_service_down(status_file, frozen_activated, monkeypatch, code):
    # The host answered, so the network worked; a bad answer is our problem.
    _patch_post(monkeypatch, _Resp(code, {'status': 'error'}))
    assert activation.check_revocation_detailed() == ('offline', 'service_down')
    assert not os.path.exists(status_file)


def test_detailed_untrusted_200_is_service_down(status_file, frozen_activated, monkeypatch):
    _patch_post(monkeypatch, _Resp(200, {'status': 'who knows'}))
    assert activation.check_revocation_detailed() == ('offline', 'service_down')


def test_internet_probe_caches(monkeypatch):
    calls = []

    def fake_conn(addr, timeout=None):
        calls.append(addr)
        raise OSError('down')

    monkeypatch.setattr(activation.socket, 'create_connection', fake_conn)
    monkeypatch.setattr(activation, '_net_probe_cache', {'at': 0.0, 'online': False})
    assert activation.internet_reachable(force=True) is False
    assert len(calls) == len(activation._NET_PROBE_HOSTS)  # all tried, all dead
    assert activation.internet_reachable() is False        # served from cache
    assert len(calls) == len(activation._NET_PROBE_HOSTS)
