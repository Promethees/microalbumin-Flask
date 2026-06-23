"""Admin license kill-switch (src/routes/account_routes.py).

Exercises the shared-secret admin surface against the REAL account_bp on a
minimal app backed by in-memory SQLite:

  * /api/admin/revoke and /api/admin/lookup refuse callers without the right
    X-Admin-Key, and 503 when ADMIN_API_KEY is unset.
  * Revoking by email flips every one of the user's seats to revoked and reports
    the affected count; reinstating clears them. Idempotent.
  * A revoked seat fails the server-side machine check (_machine_is_licensed),
    so AI proxy + auto-update stop working immediately.

The revoke email is monkeypatched out — mail delivery is not under test here.
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from account import db, User, LicenseMachine
import routes.account_routes as ar
from routes.account_routes import account_bp, _machine_is_licensed
from rate_limit import limiter

_ADMIN_KEY = 'test-admin-key'
_HWID = 'a' * 64


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', _ADMIN_KEY)
    # Don't actually send mail during the test.
    monkeypatch.setattr(ar, 'send_license_revoked_email', lambda *a, **k: None)
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
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
        db.session.add(LicenseMachine(user_id=u.id, hwid='b' * 64))
        # A second account (no machines) for the user-listing / search tests.
        a = User(email='alice@example.com', name='Alice Smith', is_verified=False)
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


# ── auth gate ─────────────────────────────────────────────────────────────────

def test_revoke_rejects_missing_key(client):
    r = client.post('/api/admin/revoke', json={'email': 'user@example.com'})
    assert r.status_code == 401


def test_revoke_rejects_wrong_key(client):
    r = client.post('/api/admin/revoke', json={'email': 'user@example.com'},
                    headers=_hdr('nope'))
    assert r.status_code == 401


def test_admin_503_when_unconfigured(client, monkeypatch):
    monkeypatch.delenv('ADMIN_API_KEY', raising=False)
    r = client.get('/api/admin/lookup?email=user@example.com', headers=_hdr())
    assert r.status_code == 503


# ── revoke / reinstate ────────────────────────────────────────────────────────

def test_revoke_flips_all_seats_and_is_idempotent(client):
    r = client.post('/api/admin/revoke', json={'email': 'user@example.com'}, headers=_hdr())
    body = r.get_json()
    assert r.status_code == 200
    assert body['revoked'] is True
    assert body['affected'] == 2
    assert body['machine_count'] == 2
    assert all(m['revoked'] for m in body['machines'])

    # Idempotent: a second revoke changes nothing.
    again = client.post('/api/admin/revoke', json={'email': 'user@example.com'}, headers=_hdr())
    assert again.get_json()['affected'] == 0


def test_reinstate_clears_revocation(client):
    client.post('/api/admin/revoke', json={'email': 'user@example.com'}, headers=_hdr())
    r = client.post('/api/admin/revoke',
                    json={'email': 'user@example.com', 'revoked': False}, headers=_hdr())
    body = r.get_json()
    assert body['revoked'] is False
    assert body['affected'] == 2
    assert not any(m['revoked'] for m in body['machines'])


def test_revoke_unknown_email_404(client):
    r = client.post('/api/admin/revoke', json={'email': 'ghost@example.com'}, headers=_hdr())
    assert r.status_code == 404


def test_lookup_reports_machines(client):
    r = client.get('/api/admin/lookup?email=user@example.com', headers=_hdr())
    body = r.get_json()
    assert r.status_code == 200
    assert body['user']['email'] == 'user@example.com'
    assert len(body['machines']) == 2


# ── user listing + search ─────────────────────────────────────────────────────

def test_users_requires_key(client):
    assert client.get('/api/admin/users').status_code == 401


def test_users_lists_all(client):
    r = client.get('/api/admin/users', headers=_hdr())
    body = r.get_json()
    assert r.status_code == 200
    assert body['total'] == 2
    emails = {u['email'] for u in body['users']}
    assert emails == {'user@example.com', 'alice@example.com'}
    by_email = {u['email']: u for u in body['users']}
    assert by_email['user@example.com']['machine_count'] == 2
    assert by_email['alice@example.com']['machine_count'] == 0
    assert by_email['alice@example.com']['is_verified'] is False


def test_users_search_by_name(client):
    r = client.get('/api/admin/users?q=alice', headers=_hdr())
    body = r.get_json()
    assert body['count'] == 1
    assert body['users'][0]['email'] == 'alice@example.com'


def test_users_search_by_email_substring(client):
    r = client.get('/api/admin/users?q=USER@example', headers=_hdr())  # case-insensitive
    body = r.get_json()
    assert body['count'] == 1
    assert body['users'][0]['email'] == 'user@example.com'


def test_users_search_no_match(client):
    r = client.get('/api/admin/users?q=zzz-nobody', headers=_hdr())
    assert r.get_json()['count'] == 0


def test_users_revoked_flag_reflected(client):
    client.post('/api/admin/revoke', json={'email': 'user@example.com'}, headers=_hdr())
    r = client.get('/api/admin/users?q=user@example.com', headers=_hdr())
    assert r.get_json()['users'][0]['revoked'] is True


# ── revocation actually disables the seat ─────────────────────────────────────

def test_revoked_seat_fails_machine_check(app):
    payload = {'sub': None, 'hwid': _HWID}
    with app.app_context():
        user = User.query.filter_by(email='user@example.com').first()
        payload['sub'] = str(user.id)
        assert _machine_is_licensed(user, payload, _HWID) is True
    # Revoke, then the same token/hwid must be refused.
    client = app.test_client()
    client.post('/api/admin/revoke', json={'email': 'user@example.com'}, headers=_hdr())
    with app.app_context():
        user = User.query.filter_by(email='user@example.com').first()
        assert _machine_is_licensed(user, payload, _HWID) is False
