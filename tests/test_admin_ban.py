"""Admin account ban (src/routes/account_routes.py).

A ban is the kill-switch's bigger hammer than a per-seat revoke: it sets
User.banned, which blocks the WHOLE account — web sign-in, download, activation,
and software usage on every machine (even an account with zero seats).

Exercises the shared-secret admin surface against the REAL account_bp on a
minimal app backed by in-memory SQLite:

  * /api/admin/ban refuses callers without the right X-Admin-Key, and 503 when
    ADMIN_API_KEY is unset.
  * Banning by email sets User.banned, mirrors the flag onto every seat, and is
    idempotent; unbanning clears both.
  * A banned account fails the server-side machine check (_machine_is_licensed)
    even for a legacy unbound token, so AI proxy + auto-update + the license
    check stop working immediately.
  * Login / activate / token are refused for a banned account.
  * lookup + users surface the banned flag.

The ban email is monkeypatched out — mail delivery is not under test here.
"""
import os
import sys
import time

import jwt
import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from account import db, User, LicenseMachine
import routes.account_routes as ar
from routes.account_routes import account_bp, _machine_is_licensed
from rate_limit import limiter

_ADMIN_KEY = 'test-admin-key'
_SECRET = 'test-secret'
_HWID = 'a' * 64


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', _ADMIN_KEY)
    monkeypatch.setenv('SECRET_KEY', _SECRET)
    # Don't actually send mail during the test.
    monkeypatch.setattr(ar, 'send_account_banned_email', lambda *a, **k: None)
    monkeypatch.setattr(ar, 'send_license_revoked_email', lambda *a, **k: None)
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = _SECRET
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(account_bp)
    with app.app_context():
        db.create_all()
        u = User(email='user@example.com', name='Test User', is_verified=True)
        u.set_password('password123')
        db.session.add(u)
        db.session.flush()
        db.session.add(LicenseMachine(user_id=u.id, hwid=_HWID))
        # A second account with NO machines — a ban must still block it.
        a = User(email='alice@example.com', name='Alice Smith', is_verified=True)
        a.set_password('password123')
        db.session.add(a)
        db.session.commit()
    return app


@pytest.fixture
def client(app):
    with app.app_context():
        limiter.reset()
    return app.test_client()


def _hdr(key=_ADMIN_KEY):
    return {'X-Admin-Key': key}


def _ban(client, email='user@example.com', banned=True):
    return client.post('/api/admin/ban', json={'email': email, 'banned': banned},
                       headers=_hdr())


# ── auth gate ─────────────────────────────────────────────────────────────────

def test_ban_rejects_missing_key(client):
    assert client.post('/api/admin/ban', json={'email': 'user@example.com'}).status_code == 401


def test_ban_rejects_wrong_key(client):
    r = client.post('/api/admin/ban', json={'email': 'user@example.com'}, headers=_hdr('nope'))
    assert r.status_code == 401


def test_ban_503_when_unconfigured(client, monkeypatch):
    monkeypatch.delenv('ADMIN_API_KEY', raising=False)
    assert _ban(client).status_code == 503


def test_ban_unknown_email_404(client):
    assert _ban(client, email='ghost@example.com').status_code == 404


# ── ban / unban ────────────────────────────────────────────────────────────────

def test_ban_sets_flag_and_mirrors_seats(client):
    r = _ban(client)
    body = r.get_json()
    assert r.status_code == 200
    assert body['banned'] is True
    assert body['changed'] is True
    assert body['user']['banned'] is True
    assert all(m['revoked'] for m in body['machines'])

    # Idempotent: a second ban changes nothing.
    assert _ban(client).get_json()['changed'] is False


def test_ban_account_with_no_seats(client):
    body = _ban(client, email='alice@example.com').get_json()
    assert body['banned'] is True
    assert body['machine_count'] == 0
    assert body['user']['banned'] is True


def test_unban_clears_flag_and_seats(client):
    _ban(client)
    body = _ban(client, banned=False).get_json()
    assert body['banned'] is False
    assert body['user']['banned'] is False
    assert not any(m['revoked'] for m in body['machines'])


# ── ban actually disables every surface ───────────────────────────────────────

def test_banned_fails_machine_check_even_legacy_token(app):
    """A banned account is refused even for a legacy (unbound, no-hwid) token."""
    client = app.test_client()
    client.post('/api/admin/ban', json={'email': 'user@example.com'}, headers=_hdr())
    with app.app_context():
        user = User.query.filter_by(email='user@example.com').first()
        # Legacy token (no 'hwid') would normally be grandfathered → True.
        assert _machine_is_licensed(user, {'sub': str(user.id)}, None) is False
        # Bound token also blocked.
        assert _machine_is_licensed(user, {'sub': str(user.id), 'hwid': _HWID}, _HWID) is False


def test_banned_login_refused(client):
    _ban(client)
    r = client.post('/api/account/login',
                    json={'email': 'user@example.com', 'password': 'password123'})
    assert r.status_code == 403
    assert r.get_json()['code'] == 'account_banned'


def test_banned_license_check_reports_revoked(client):
    _ban(client)
    token = jwt.encode({'sub': '1', 'purpose': 'activation', 'hwid': _HWID},
                       _SECRET, algorithm='HS256')
    r = client.post('/api/license/check', json={'license_token': token, 'hwid': _HWID})
    body = r.get_json()
    assert r.status_code == 200
    assert body['status'] == 'revoked'
    assert body['code'] == 'account_banned'


def test_banned_activate_refused(client):
    _ban(client)
    dl = jwt.encode({'sub': '1', 'email': 'user@example.com', 'purpose': 'app_download',
                     'exp': int(time.time()) + 600}, _SECRET, algorithm='HS256')
    r = client.post('/api/activate', json={'token': dl, 'hwid': _HWID})
    assert r.status_code == 403
    assert r.get_json()['code'] == 'account_banned'


# ── ban surfaced in admin views ───────────────────────────────────────────────

def test_lookup_reports_banned(client):
    _ban(client)
    body = client.get('/api/admin/lookup?email=user@example.com', headers=_hdr()).get_json()
    assert body['user']['banned'] is True


def test_users_banned_flag_reflected(client):
    _ban(client)
    body = client.get('/api/admin/users?q=user@example.com', headers=_hdr()).get_json()
    assert body['users'][0]['banned'] is True
