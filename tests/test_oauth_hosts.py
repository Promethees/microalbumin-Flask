"""Which host each OAuth provider is told to come back to (src/routes/oauth_routes.py).

The deployment answers on a branded custom domain and on the platform's own
hostname, and the branded one can be down while the app is fine. Sign-in has to
behave sensibly on both, and the two providers are deliberately NOT symmetric:

  * **Google** registers several redirect URIs, so its redirect_uri follows the
    host the user is actually on (allowlisted — see test_security.py).
  * **GitHub**'s OAuth app holds a single authorisation callback URL, so its
    redirect_uri stays pinned to the branded domain.

The pinning has a consequence worth pinning down here: a GitHub flow started
from any other host cannot succeed *even when every host is up*, because
`oauth_state` lives in a host-scoped session cookie and the callback would land
on the branded host with a different cookie jar. So the flow is refused up front
and the button is not rendered, rather than sending someone through GitHub to a
guaranteed "Invalid state parameter".
"""
import os
import sys
from urllib.parse import urlsplit, parse_qs, unquote_plus

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from routes.oauth_routes import (oauth_bp, _base_url, _github_base_url,
                                 github_signin_available)

_BRANDED = 'https://www.easyokapi.cbbiotec.vn'
_BRANDED_HOST = 'www.easyokapi.cbbiotec.vn'
_FALLBACK = 'https://easysensor-kit-ea7db935ce81.herokuapp.com'
_FALLBACK_HOST = 'easysensor-kit-ea7db935ce81.herokuapp.com'


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('APP_BASE_URL', _BRANDED)
    monkeypatch.setenv('APP_FALLBACK_URLS', _FALLBACK)
    monkeypatch.delenv('GITHUB_OAUTH_BASE_URL', raising=False)
    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_ID', 'test-google')
    monkeypatch.setenv('GITHUB_OAUTH_CLIENT_ID', 'test-github')

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    app.register_blueprint(oauth_bp)
    return app


def _start(app, host, provider):
    """Follow the sign-in entry point; return the Location it redirects to."""
    with app.test_client() as c:
        return c.get(f'/auth/oauth/{provider}',
                     base_url=f'https://{host}').headers.get('Location', '')


def _redirect_uri(location):
    return (parse_qs(urlsplit(location).query).get('redirect_uri') or [None])[0]


def _oauth_error(location):
    raw = (parse_qs(urlsplit(location).query).get('oauth_error') or [''])[0]
    return unquote_plus(raw)


# ── Google follows the host ───────────────────────────────────────────────────

def test_google_comes_back_to_the_branded_host(app):
    loc = _start(app, _BRANDED_HOST, 'google')
    assert _redirect_uri(loc) == _BRANDED + '/auth/oauth/google/callback'


def test_google_comes_back_to_the_fallback_host(app):
    loc = _start(app, _FALLBACK_HOST, 'google')
    assert _redirect_uri(loc) == _FALLBACK + '/auth/oauth/google/callback'


def test_google_ignores_an_unserved_host(app):
    loc = _start(app, 'attacker.example', 'google')
    assert _redirect_uri(loc) == _BRANDED + '/auth/oauth/google/callback'


# ── GitHub stays pinned ───────────────────────────────────────────────────────

def test_github_uses_the_branded_host_when_on_it(app):
    loc = _start(app, _BRANDED_HOST, 'github')
    assert _redirect_uri(loc) == _BRANDED + '/auth/oauth/github/callback'


def test_github_base_never_follows_the_request(app):
    with app.test_request_context('/', base_url=f'https://{_FALLBACK_HOST}'):
        assert _github_base_url() == _BRANDED
        assert _base_url() == _FALLBACK      # Google would follow; GitHub does not


def test_github_base_is_overridable(app, monkeypatch):
    monkeypatch.setenv('GITHUB_OAUTH_BASE_URL', 'https://other.example/')
    with app.test_request_context('/', base_url=f'https://{_BRANDED_HOST}'):
        assert _github_base_url() == 'https://other.example'


# ── GitHub is refused where it cannot finish ──────────────────────────────────

def test_github_is_refused_from_the_fallback_host(app):
    loc = _start(app, _FALLBACK_HOST, 'github')
    # Never hand the user to GitHub for a round trip that must fail the state
    # check when it comes back to a host whose cookie jar it never touched.
    assert 'github.com' not in loc
    assert '/account/login' in loc


def test_the_refusal_names_the_host_that_works(app):
    err = _oauth_error(_start(app, _FALLBACK_HOST, 'github'))
    assert _BRANDED in err
    assert 'Google' in err or 'e-mail' in err   # offers a way forward, not a dead end


def test_github_sets_no_oauth_state_when_refused(app):
    # A refused start must not leave a half-begun flow in the session.
    with app.test_client() as c:
        c.get('/auth/oauth/github', base_url=f'https://{_FALLBACK_HOST}')
        with c.session_transaction() as sess:
            assert 'oauth_state' not in sess


def test_availability_flag_tracks_the_host(app):
    with app.test_request_context('/', base_url=f'https://{_BRANDED_HOST}'):
        assert github_signin_available() is True
    with app.test_request_context('/', base_url=f'https://{_FALLBACK_HOST}'):
        assert github_signin_available() is False
