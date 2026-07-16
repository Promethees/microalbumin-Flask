"""Socket.IO CORS wiring (src/extensions.py).

Two things are under test, both of which have already gone wrong once:

  * The vulnerability. `cors_allowed_origins="*"` with cookie auth let any site
    open an authenticated socket as a visiting victim and receive their
    `update_csv`/`update_json` pushes. The allowlist must never be a wildcard.

  * The outage. The fix passed APP_BASE_URL straight through, and engine.io
    matches the browser's Origin against that list by EXACT STRING comparison
    (`origin not in allowed_origins`, engineio/server.py). An Origin header
    never carries a path or a trailing slash, so a perfectly ordinary
    APP_BASE_URL of "https://app.example.com/" matched nothing and would have
    refused every socket in production with "Not an accepted origin". These
    values come from operator-set config vars where a trailing slash is
    invisible, so _normalize_origin exists to absorb that.

The engine.io contract is asserted directly (`origin in allowed`) rather than
described, so if that library ever starts normalizing — or stops — this notices.

Unlike security.py's guard, which matches on hostname only, these entries keep
scheme and port: engine.io compares whole origins.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# extensions.py imports flask_socketio (which pulls eventlet). Both are real
# project dependencies — the Procfile runs `gunicorn -k eventlet` — but
# conftest.py notes the test venv has historically gone without them. Skip this
# module rather than error the whole collection when they are absent.
pytest.importorskip('flask_socketio',
                    reason='flask_socketio/eventlet not installed in this test env')

import extensions
from extensions import _normalize_origin, _cors_origins

# The real production value at the time of writing — trailing slash and all.
_PROD_BASE = 'https://www.easyokapi.cbbiotec.vn/'
_PROD_ORIGIN = 'https://www.easyokapi.cbbiotec.vn'
_PROD_APEX = 'https://easyokapi.cbbiotec.vn'

_ENV_KEYS = ('SOCKETIO_CORS_ORIGINS', 'APP_BASE_URL', 'DYNO', 'PORT', 'HEROKU_APP_NAME')


@pytest.fixture
def clean_env(monkeypatch):
    """Start from a known-empty config so a stray real env var can't mask a bug."""
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


@pytest.fixture
def reimport():
    """Reload extensions so its import-time wiring re-evaluates under a given env.

    `socketio` and `_VERBOSE` are computed at import, so a reload is the only way
    to exercise them. The finalizer restores the real environment and reloads
    once more, leaving this module exactly as it was found — test_edit_file.py
    leaked global state this way and silently failed *other* files.
    """
    saved = dict(os.environ)

    def _reimport(**env):
        for k in _ENV_KEYS:
            os.environ.pop(k, None)
        os.environ.update({k: v for k, v in env.items() if v is not None})
        return importlib.reload(extensions)

    yield _reimport
    os.environ.clear()
    os.environ.update(saved)
    importlib.reload(extensions)


# ── _normalize_origin ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw, expected', [
    # The regression: a trailing slash must not survive into the allowlist.
    ('https://app.example.com/', 'https://app.example.com'),
    (_PROD_BASE, _PROD_ORIGIN),
    ('https://app.example.com', 'https://app.example.com'),
    ('https://app.example.com/some/path', 'https://app.example.com'),
    ('  https://app.example.com/  ', 'https://app.example.com'),      # trimmed
    ('https://APP.Example.COM/', 'https://app.example.com'),          # case-folded
    ('http://localhost:5003/', 'http://localhost:5003'),              # port kept
    ('https://app.example.com:8443/x', 'https://app.example.com:8443'),
    ('app.example.com', 'https://app.example.com'),                   # bare host
    ('app.example.com:8443', 'https://app.example.com:8443'),
    ('http://app.example.com/', 'http://app.example.com'),            # scheme kept
])
def test_normalize_origin(raw, expected):
    assert _normalize_origin(raw) == expected


@pytest.mark.parametrize('raw', ['', '   ', None, '///', 'not a url', 'https://'])
def test_normalize_origin_rejects_unusable(raw):
    """Junk is dropped rather than admitted as an entry that can never match."""
    assert _normalize_origin(raw) is None


def test_normalize_origin_preserves_port_unlike_the_request_guard():
    """engine.io compares whole origins, so the port is significant here."""
    assert _normalize_origin('https://app.example.com:8443') != 'https://app.example.com'


# ── _cors_origins ─────────────────────────────────────────────────────────────

def test_uses_app_base_url(clean_env):
    clean_env.setenv('APP_BASE_URL', 'https://app.example.com')
    assert _cors_origins() == ['https://app.example.com']


def test_app_base_url_trailing_slash_is_normalized(clean_env):
    """The exact production shape that would have refused every socket."""
    clean_env.setenv('APP_BASE_URL', _PROD_BASE)
    assert _cors_origins() == [_PROD_ORIGIN]


def test_socketio_cors_origins_overrides_app_base_url(clean_env):
    clean_env.setenv('APP_BASE_URL', 'https://ignored.example.com')
    clean_env.setenv('SOCKETIO_CORS_ORIGINS', 'https://app.example.com')
    assert _cors_origins() == ['https://app.example.com']


def test_comma_separated_origins(clean_env):
    """How the apex is allowlisted alongside www in production."""
    clean_env.setenv('SOCKETIO_CORS_ORIGINS', f'{_PROD_BASE},{_PROD_APEX}/')
    assert _cors_origins() == [_PROD_ORIGIN, _PROD_APEX]


def test_duplicates_are_collapsed(clean_env):
    """Two spellings of one origin are one entry."""
    clean_env.setenv('SOCKETIO_CORS_ORIGINS',
                     'https://app.example.com,https://app.example.com/,https://APP.example.com')
    assert _cors_origins() == ['https://app.example.com']


def test_blank_and_junk_entries_are_dropped(clean_env):
    clean_env.setenv('SOCKETIO_CORS_ORIGINS', 'https://app.example.com, ,,not a url')
    assert _cors_origins() == ['https://app.example.com']


def test_falls_back_to_localhost_when_unset(clean_env):
    assert _cors_origins() == ['http://localhost:5003']


@pytest.mark.parametrize('value', ['', '   ', ',', ' , '])
def test_falls_back_to_localhost_when_config_is_empty(clean_env, value):
    """An empty config must not yield an empty allowlist."""
    clean_env.setenv('SOCKETIO_CORS_ORIGINS', value)
    assert _cors_origins() == ['http://localhost:5003']


def test_never_returns_a_wildcard(clean_env):
    """The original vulnerability: '*' plus cookie auth is a cross-site socket."""
    for value in ('*', 'https://app.example.com', _PROD_BASE, ''):
        clean_env.setenv('SOCKETIO_CORS_ORIGINS', value)
        assert '*' not in _cors_origins()


def test_wildcard_config_is_not_honoured_as_a_wildcard(clean_env):
    """Even if someone sets '*', it must not come back as engine.io's wildcard."""
    clean_env.setenv('SOCKETIO_CORS_ORIGINS', '*')
    assert _cors_origins() != ['*']
    assert _cors_origins() != '*'


def test_result_is_always_a_list(clean_env):
    """A bare string would make engine.io treat it as a single origin; keep the
    shape stable so callers and this test agree."""
    clean_env.setenv('SOCKETIO_CORS_ORIGINS', 'https://app.example.com')
    assert isinstance(_cors_origins(), list)


# ── the engine.io contract: exact string match against the Origin header ──────

@pytest.mark.parametrize('configured, origin, allowed', [
    (_PROD_BASE, _PROD_ORIGIN, True),        # trailing-slash config still matches
    (_PROD_ORIGIN, _PROD_ORIGIN, True),
    (_PROD_BASE, _PROD_APEX, False),         # apex is a different origin
    (_PROD_BASE, 'https://evil.example', False),
    (_PROD_BASE, 'http://www.easyokapi.cbbiotec.vn', False),   # scheme matters
])
def test_engineio_exact_match_semantics(clean_env, configured, origin, allowed):
    """engine.io does `origin not in allowed_origins` — a plain list membership
    test. Assert against that directly rather than trusting the docstring."""
    clean_env.setenv('SOCKETIO_CORS_ORIGINS', configured)
    assert (origin in _cors_origins()) is allowed


def test_both_production_hosts_match_when_configured(clean_env):
    clean_env.setenv('SOCKETIO_CORS_ORIGINS', f'{_PROD_BASE},{_PROD_APEX}')
    allowed = _cors_origins()
    assert _PROD_ORIGIN in allowed
    assert _PROD_APEX in allowed
    assert 'https://evil.example' not in allowed


# ── import-time wiring ────────────────────────────────────────────────────────

def test_socketio_is_built_with_normalized_origins(reimport):
    mod = reimport(APP_BASE_URL=_PROD_BASE)
    assert mod.socketio.server_options['cors_allowed_origins'] == [_PROD_ORIGIN]


def test_socketio_is_never_built_with_a_wildcard(reimport):
    mod = reimport(SOCKETIO_CORS_ORIGINS='*')
    assert mod.socketio.server_options['cors_allowed_origins'] != '*'
    assert '*' not in mod.socketio.server_options['cors_allowed_origins']


# ── _VERBOSE: chatty in dev, quiet under a server ─────────────────────────────

@pytest.mark.parametrize('marker', ['DYNO', 'PORT', 'HEROKU_APP_NAME'])
def test_logging_is_off_under_a_server_env(reimport, marker):
    """Verbose engine/socket logging would put request and session detail into
    production logs."""
    mod = reimport(APP_BASE_URL='https://app.example.com', **{marker: 'set'})
    assert mod._VERBOSE is False
    assert mod.socketio.server_options['logger'] is False
    assert mod.socketio.server_options['engineio_logger'] is False


def test_logging_is_on_for_local_development(reimport):
    mod = reimport(APP_BASE_URL='http://localhost:5003')
    assert mod._VERBOSE is True
    assert mod.socketio.server_options['logger'] is True


def test_empty_server_marker_does_not_count_as_production(reimport):
    """`any(os.environ.get(k))` is falsy for an empty string — pin that reading."""
    mod = reimport(APP_BASE_URL='http://localhost:5003', DYNO='')
    assert mod._VERBOSE is True
