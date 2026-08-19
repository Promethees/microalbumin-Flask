"""Same-origin request guard (src/security.py).

The guard is a single before_request that rejects state-changing requests whose
browser-supplied Origin isn't ours — defense-in-depth behind
SESSION_COOKIE_SAMESITE='Lax'. Exercised against the REAL init_request_guard on
a minimal app with one all-methods route.

The load-bearing behaviours, and why each is pinned here:

  * Safe methods are never guarded — a GET must not 403 on a foreign Origin.
  * Unsafe methods from a foreign Origin are refused (the actual CSRF gate).
  * An ABSENT Origin is allowed. This is the desktop-client path: the installed
    app calls the token-authenticated endpoints server-to-server with no Origin,
    so a guard that blocked them would silently cut off every install.
  * The Host header is NOT trusted for the allowlist — an attacker can spoof it,
    so a spoofed Host must not talk its way past the guard.
  * A trailing slash in APP_BASE_URL is tolerated. The Socket.IO allowlist was
    broken by exactly that (it matched the raw string); the guard parses to a
    hostname instead, and this pins that it stays that way.
"""
import os
import sys

import pytest
from flask import Flask, jsonify

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from security import _hostname, _allowed_hostnames, init_request_guard

_APP_HOST = 'app.example.com'
_APP_BASE = 'https://app.example.com'
_EVIL = 'https://evil.example'

_UNSAFE = ['POST', 'PUT', 'PATCH', 'DELETE']
_SAFE = ['GET', 'HEAD', 'OPTIONS']


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('APP_BASE_URL', _APP_BASE)
    monkeypatch.delenv('EXTRA_ALLOWED_ORIGINS', raising=False)
    monkeypatch.delenv('APP_FALLBACK_URLS', raising=False)
    monkeypatch.delenv('HEROKU_APP_DEFAULT_DOMAIN', raising=False)

    app = Flask(__name__)
    app.config['TESTING'] = True
    init_request_guard(app)

    @app.route('/thing', methods=_SAFE + _UNSAFE)
    def thing():
        return jsonify({'ok': True})

    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _send(client, method, **kwargs):
    return getattr(client, method.lower())('/thing', **kwargs)


# ── _hostname ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw, expected', [
    ('https://app.example.com', 'app.example.com'),
    ('https://app.example.com/', 'app.example.com'),        # trailing slash
    ('https://app.example.com/some/path', 'app.example.com'),
    ('https://APP.Example.COM', 'app.example.com'),          # case-folded
    ('https://app.example.com:8443', 'app.example.com'),     # port dropped
    ('app.example.com', 'app.example.com'),                  # bare host
    ('app.example.com:5003', 'app.example.com'),             # bare host:port
    ('http://127.0.0.1:5099', '127.0.0.1'),
    ('', None),
    (None, None),
])
def test_hostname_parsing(raw, expected):
    assert _hostname(raw) == expected


# ── _allowed_hostnames ────────────────────────────────────────────────────────

def test_allowed_includes_app_base_url(monkeypatch):
    monkeypatch.setenv('APP_BASE_URL', _APP_BASE)
    monkeypatch.delenv('EXTRA_ALLOWED_ORIGINS', raising=False)
    assert _APP_HOST in _allowed_hostnames()


def test_allowed_tolerates_trailing_slash_in_app_base_url(monkeypatch):
    """A base URL written with a trailing slash is ordinary; it must still work."""
    monkeypatch.setenv('APP_BASE_URL', 'https://app.example.com/')
    monkeypatch.delenv('EXTRA_ALLOWED_ORIGINS', raising=False)
    assert _APP_HOST in _allowed_hostnames()


def test_allowed_always_includes_dev_hosts(monkeypatch):
    monkeypatch.setenv('APP_BASE_URL', _APP_BASE)
    allowed = _allowed_hostnames()
    assert {'localhost', '127.0.0.1', '::1'} <= allowed


def test_extra_allowed_origins_are_added(monkeypatch):
    """Comma-separated extras — how the apex domain gets allowlisted alongside www."""
    monkeypatch.setenv('APP_BASE_URL', 'https://www.example.com')
    monkeypatch.setenv('EXTRA_ALLOWED_ORIGINS',
                       'https://example.com, https://alt.example.com/')
    allowed = _allowed_hostnames()
    assert {'www.example.com', 'example.com', 'alt.example.com'} <= allowed


def test_blank_extra_allowed_origins_is_harmless(monkeypatch):
    monkeypatch.setenv('APP_BASE_URL', _APP_BASE)
    monkeypatch.setenv('EXTRA_ALLOWED_ORIGINS', '')
    assert _APP_HOST in _allowed_hostnames()


# ── safe methods are never guarded ────────────────────────────────────────────

@pytest.mark.parametrize('method', _SAFE)
def test_safe_methods_pass_even_from_hostile_origin(client, method):
    r = _send(client, method, headers={'Origin': _EVIL})
    assert r.status_code == 200


# ── the CSRF gate ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('method', _UNSAFE)
def test_unsafe_methods_blocked_from_hostile_origin(client, method):
    r = _send(client, method, headers={'Origin': _EVIL})
    assert r.status_code == 403
    assert r.get_json()['code'] == 'forbidden_origin'


@pytest.mark.parametrize('method', _UNSAFE)
def test_unsafe_methods_pass_from_own_origin(client, method):
    assert _send(client, method, headers={'Origin': _APP_BASE}).status_code == 200


def test_own_origin_with_port_is_allowed(client):
    """Matching is hostname-only, so a port on our own host still passes."""
    assert _send(client, 'POST',
                 headers={'Origin': 'https://app.example.com:8443'}).status_code == 200


def test_lookalike_origin_is_blocked(client):
    """A suffix attack — app.example.com.evil.example is a different hostname."""
    r = _send(client, 'POST', headers={'Origin': 'https://app.example.com.evil.example'})
    assert r.status_code == 403


# ── the desktop-client path ───────────────────────────────────────────────────

@pytest.mark.parametrize('method', _UNSAFE)
def test_absent_origin_is_allowed(client, method):
    """No Origin and no Referer = a server-to-server client, not a browser.

    The installed desktop app calls /api/activate, /api/license/check,
    /ai/proxy/chat and /api/download this way. Blocking these would break every
    install, so this is the regression that matters most in this file.
    """
    assert _send(client, method).status_code == 200


# ── Referer fallback (only consulted when Origin is absent) ───────────────────

def test_hostile_referer_blocked_when_origin_absent(client):
    r = _send(client, 'POST', headers={'Referer': _EVIL + '/page'})
    assert r.status_code == 403
    assert r.get_json()['code'] == 'forbidden_referer'


def test_own_referer_allowed_when_origin_absent(client):
    assert _send(client, 'POST',
                 headers={'Referer': _APP_BASE + '/dashboard'}).status_code == 200


def test_origin_wins_over_referer(client):
    """A present Origin decides; a friendly Referer must not rescue a bad Origin."""
    r = _send(client, 'POST', headers={'Origin': _EVIL, 'Referer': _APP_BASE + '/x'})
    assert r.status_code == 403
    assert r.get_json()['code'] == 'forbidden_origin'


def test_good_origin_survives_hostile_referer(client):
    r = _send(client, 'POST', headers={'Origin': _APP_BASE, 'Referer': _EVIL + '/x'})
    assert r.status_code == 200


# ── the Host header is not an allowlist input ─────────────────────────────────

def test_spoofed_host_header_does_not_authorize(client):
    """An attacker controls Host, so it must not widen the allowlist."""
    r = _send(client, 'POST', headers={'Origin': _EVIL, 'Host': 'evil.example'})
    assert r.status_code == 403


def test_spoofed_host_cannot_rescue_a_foreign_origin(client):
    r = _send(client, 'POST', headers={'Origin': _EVIL, 'Host': _APP_HOST})
    assert r.status_code == 403


# ── config changes take effect per-request (no cached allowlist) ──────────────

def test_allowlist_is_not_cached_across_requests(client, monkeypatch):
    assert _send(client, 'POST', headers={'Origin': _EVIL}).status_code == 403
    monkeypatch.setenv('EXTRA_ALLOWED_ORIGINS', _EVIL)
    assert _send(client, 'POST', headers={'Origin': _EVIL}).status_code == 200


# ── the platform fallback host is a first-class origin ────────────────────────
# APP_BASE_URL is a branded custom domain: DNS + CDN + TLS in front of this dyno,
# all of which can break while the app is fine. The platform hostname serves the
# same app and is where users are sent when that happens — so it has to be able
# to do more than render. Without it on the allowlist a visitor can load the page
# and then have every sign-in POST rejected by this guard.

_FALLBACK = 'https://myapp-1234.herokuapp.com'


def test_fallback_origin_is_allowed(client, monkeypatch):
    monkeypatch.setenv('APP_FALLBACK_URLS', _FALLBACK)
    assert _send(client, 'POST', headers={'Origin': _FALLBACK}).status_code == 200


def test_fallback_origin_is_rejected_when_not_configured(client):
    # It is an allowlist entry, not a blanket herokuapp.com exemption.
    assert _send(client, 'POST', headers={'Origin': _FALLBACK}).status_code == 403


def test_several_fallbacks_are_accepted(client, monkeypatch):
    other = 'https://myapp-staging.herokuapp.com'
    monkeypatch.setenv('APP_FALLBACK_URLS', f'{_FALLBACK}, {other}')
    for origin in (_FALLBACK, other):
        assert _send(client, 'POST', headers={'Origin': origin}).status_code == 200


def test_branded_origin_still_works_alongside_fallbacks(client, monkeypatch):
    monkeypatch.setenv('APP_FALLBACK_URLS', _FALLBACK)
    assert _send(client, 'POST', headers={'Origin': _APP_BASE}).status_code == 200


def test_fallbacks_do_not_widen_the_list_to_anyone_else(client, monkeypatch):
    monkeypatch.setenv('APP_FALLBACK_URLS', _FALLBACK)
    assert _send(client, 'POST', headers={'Origin': _EVIL}).status_code == 403


def test_heroku_metadata_domain_is_trusted(client, monkeypatch):
    # Set by the platform for THIS app, so unlike Host it cannot be spoofed by a
    # caller — and it keeps working if the app is renamed.
    monkeypatch.setenv('HEROKU_APP_DEFAULT_DOMAIN', 'myapp-1234.herokuapp.com')
    assert _send(client, 'POST', headers={'Origin': _FALLBACK}).status_code == 200


def test_blank_fallback_config_contributes_nothing(client, monkeypatch):
    monkeypatch.setenv('APP_FALLBACK_URLS', ' , ,')
    assert _send(client, 'POST', headers={'Origin': _EVIL}).status_code == 403
    assert _send(client, 'POST', headers={'Origin': _APP_BASE}).status_code == 200
