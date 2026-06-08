"""Tests for the licence gate (main._enforce_activation, a before_request hook).

A frozen build is licence-gated: until a valid token is stored, every page is
redirected to /activate and every /api or /ai call returns 403. The pure
verifier (test_activation.py) and the lifecycle helpers are unit-tested, but the
Flask wiring that actually blocks requests is not — this file covers that seam.

The gate keys off activation.needs_activation(); we pin it per-test rather than
faking a frozen build, so the tests are host- and build-independent.
"""

import pytest

import activation
from main import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def gated(monkeypatch):
    """Force the gate ON (as on an unactivated frozen build)."""
    monkeypatch.setattr(activation, 'needs_activation', lambda: True)


def _is_redirect_to_activate(rv):
    return rv.status_code in (301, 302) and rv.headers.get('Location', '').endswith('/activate')


def _is_not_activated_403(rv):
    return rv.status_code == 403 and (rv.get_json() or {}).get('code') == 'not_activated'


# ── Gate ON: blocked requests ─────────────────────────────────────────────────

def test_api_path_returns_403_not_activated(client, gated):
    # The gate runs before routing, so a /api/ prefix is blocked even with no route.
    rv = client.get('/api/anything')
    assert _is_not_activated_403(rv)
    assert 'not activated' in rv.get_json()['message'].lower()


def test_ai_path_returns_403_not_activated(client, gated):
    rv = client.post('/ai/chat', json={'messages': []})
    assert _is_not_activated_403(rv)


def test_non_api_page_redirects_to_activate(client, gated):
    # A normal page (not /api or /ai) is redirected to the gate page, not 403'd.
    rv = client.get('/')
    assert _is_redirect_to_activate(rv)


def test_non_api_post_route_also_redirects(client, gated):
    # /run_script is neither /api nor /ai, so it falls through to the redirect arm.
    rv = client.post('/run_script', json={})
    assert _is_redirect_to_activate(rv)


# ── Gate ON: open paths pass through ──────────────────────────────────────────

def test_ping_is_open(client, gated):
    rv = client.get('/ping')
    assert rv.status_code == 200
    assert rv.get_json() == {'status': 'success'}


def test_ai_status_is_open(client, gated):
    rv = client.get('/ai/status')
    assert rv.status_code == 200
    assert not _is_not_activated_403(rv)


def test_ai_activate_endpoint_is_open(client, gated):
    # GET is the wrong method (405), which proves the gate let it reach routing
    # rather than short-circuiting with its own 403/redirect.
    rv = client.get('/ai/activate')
    assert rv.status_code == 405
    assert not _is_not_activated_403(rv)
    assert not _is_redirect_to_activate(rv)


def test_static_assets_are_open(client, gated):
    # Anything under /static/ bypasses the gate (theme/JS must load on the gate page).
    rv = client.get('/static/script/init.js')
    assert not _is_not_activated_403(rv)
    assert not _is_redirect_to_activate(rv)


# ── Gate OFF: dev/source builds are never gated ───────────────────────────────

def test_gate_off_lets_everything_through(client, monkeypatch):
    monkeypatch.setattr(activation, 'needs_activation', lambda: False)
    # With the gate off, an unknown /api path is a plain 404 — not the gate's 403.
    rv = client.get('/api/anything')
    assert rv.status_code == 404
    assert not _is_not_activated_403(rv)
