"""Admin seat removal (POST /api/admin/machines/remove).

Every other way to free a seat needs the machine itself — the uninstaller's
POST /api/license/release, or the user signing in and deactivating. When the
machine is gone (dead disk, reformat, or an uninstall by a build predating the
seat release) the user is locked out of their own license by a machine that no
longer exists, and only an admin can free it.

  * Removing by hwid frees exactly that seat; all=true frees every seat.
  * Removal puts the account back under the cap, so a new machine can activate —
    the whole point of the endpoint.
  * A REVOKED seat is refused (409) unless force=true: deleting the row would let
    that machine re-activate into a fresh unrevoked seat and escape the
    kill-switch. A banned account needs no such guard (/api/activate refuses it).
  * Guarded by the shared admin key, like every other /api/admin/* route.
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from account import db, User, LicenseMachine
import routes.account_routes as ar
from routes.account_routes import account_bp, _bind_machine
from rate_limit import limiter

_ADMIN_KEY = 'test-admin-key'
_HWID_A = 'a' * 64
_HWID_B = 'b' * 64
_HWID_NEW = 'c' * 64


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', _ADMIN_KEY)
    # _MAX_MACHINES is resolved from the env at IMPORT time, so setting the env var
    # here would be too late — patch the module attribute. Two seats lets the
    # capacity test show a removal actually dropping the account back under the cap.
    monkeypatch.setattr(ar, '_MAX_MACHINES', 2)
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
        db.session.add(LicenseMachine(user_id=u.id, hwid=_HWID_A))
        db.session.add(LicenseMachine(user_id=u.id, hwid=_HWID_B))
        db.session.commit()
        app.config['_UID'] = u.id
    return app


@pytest.fixture
def client(app):
    with app.app_context():
        limiter.reset()
    return app.test_client()


def _hdr():
    return {'X-Admin-Key': _ADMIN_KEY}


def _post(client, **body):
    return client.post('/api/admin/machines/remove', json=body, headers=_hdr())


def _hwids(app):
    with app.app_context():
        return sorted(m.hwid for m in
                      LicenseMachine.query.filter_by(user_id=app.config['_UID']).all())


# ── removing seats ───────────────────────────────────────────────────────────

def test_remove_one_seat_by_hwid(app, client):
    r = _post(client, email='user@example.com', hwid=_HWID_A)
    assert r.status_code == 200
    body = r.get_json()
    assert body['removed'] == 1
    assert body['machine_count'] == 1
    assert _hwids(app) == [_HWID_B]          # the other seat is untouched


def test_remove_all_seats(app, client):
    r = _post(client, email='user@example.com', all=True)
    assert r.status_code == 200
    assert r.get_json()['removed'] == 2
    assert _hwids(app) == []


def test_remove_is_idempotent(app, client):
    _post(client, email='user@example.com', hwid=_HWID_A)
    again = _post(client, email='user@example.com', hwid=_HWID_A)
    assert again.status_code == 200
    assert again.get_json()['removed'] == 0   # already gone, not an error


def test_removal_frees_capacity_for_a_new_machine(app, client):
    # The reason the endpoint exists: the user is at the cap because of a machine
    # that no longer exists, and must be able to activate a replacement.
    with app.app_context():
        ok, _ = _bind_machine(User.query.get(app.config['_UID']), _HWID_NEW)
        assert ok is False                    # at the cap (2 seats, max 2)
    _post(client, email='user@example.com', hwid=_HWID_A)
    with app.app_context():
        ok, _ = _bind_machine(User.query.get(app.config['_UID']), _HWID_NEW)
        assert ok is True


def test_response_reports_the_remaining_seats(app, client):
    body = _post(client, email='user@example.com', hwid=_HWID_A).get_json()
    assert [m['hwid'] for m in body['machines']] == [_HWID_B]
    assert body['max_machines'] == 2


# ── the kill-switch must not be undone by accident ───────────────────────────

def test_revoked_seat_is_refused_without_force(app, client):
    with app.app_context():
        LicenseMachine.query.filter_by(hwid=_HWID_A).first().revoked = True
        db.session.commit()
    r = _post(client, email='user@example.com', hwid=_HWID_A)
    assert r.status_code == 409
    assert r.get_json()['code'] == 'seat_revoked'
    assert _hwids(app) == [_HWID_A, _HWID_B]   # nothing removed


def test_revoked_seat_removed_with_force(app, client):
    with app.app_context():
        LicenseMachine.query.filter_by(hwid=_HWID_A).first().revoked = True
        db.session.commit()
    r = _post(client, email='user@example.com', hwid=_HWID_A, force=True)
    assert r.status_code == 200
    assert _hwids(app) == [_HWID_B]


def test_all_is_refused_when_any_seat_is_revoked(app, client):
    # An all=true sweep must not quietly take a revoked seat with it.
    with app.app_context():
        LicenseMachine.query.filter_by(hwid=_HWID_B).first().revoked = True
        db.session.commit()
    r = _post(client, email='user@example.com', all=True)
    assert r.status_code == 409
    assert _hwids(app) == [_HWID_A, _HWID_B]   # all-or-nothing, none removed


def test_banned_account_seats_can_be_removed(app, client):
    # No guard needed: /api/activate refuses a banned user, so the seats cannot
    # come back and removing them cannot escape the ban.
    with app.app_context():
        User.query.get(app.config['_UID']).banned = True
        db.session.commit()
    r = _post(client, email='user@example.com', all=True)
    assert r.status_code == 200
    assert _hwids(app) == []


# ── auth + input ─────────────────────────────────────────────────────────────

def test_requires_the_admin_key(app, client):
    r = client.post('/api/admin/machines/remove',
                    json={'email': 'user@example.com', 'all': True})
    assert r.status_code == 401
    assert _hwids(app) == [_HWID_A, _HWID_B]


def test_wrong_admin_key_refused(app, client):
    r = client.post('/api/admin/machines/remove',
                    json={'email': 'user@example.com', 'all': True},
                    headers={'X-Admin-Key': 'nope'})
    assert r.status_code == 401


def test_503_when_admin_key_not_configured(app, client, monkeypatch):
    monkeypatch.delenv('ADMIN_API_KEY', raising=False)
    r = _post(client, email='user@example.com', all=True)
    assert r.status_code == 503


def test_unknown_account_404(client):
    r = _post(client, email='nobody@example.com', all=True)
    assert r.status_code == 404


def test_email_required(client):
    assert _post(client, hwid=_HWID_A).status_code == 400


def test_hwid_or_all_required(client):
    r = _post(client, email='user@example.com')
    assert r.status_code == 400
    assert 'hwid is required' in r.get_json()['message']


def test_unknown_hwid_removes_nothing(app, client):
    r = _post(client, email='user@example.com', hwid=_HWID_NEW)
    assert r.status_code == 200
    assert r.get_json()['removed'] == 0
    assert _hwids(app) == [_HWID_A, _HWID_B]
