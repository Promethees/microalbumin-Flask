"""Machine-initiated seat release (POST /api/license/release).

Uninstalling the software must free its seat, otherwise a user who reinstalls
elsewhere hits the seat cap against a machine that no longer exists. There is no
web session at uninstall time, so the machine's own permanent token is the
credential: its 'hwid' claim names the one seat it may free.

  * A bound machine frees its own seat, and the call is idempotent.
  * A token can only free the seat it is bound to (body hwid must agree).
  * A revoked seat / banned account CANNOT be freed — that would let the user
    re-activate into a fresh unrevoked seat and escape the kill-switch.
  * Freeing a seat puts the user back under the cap so a new machine can bind.

Backed by in-memory SQLite + an ephemeral RS256 signing key so real
hardware-locked tokens can be issued and validated.
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from account import db, User, LicenseMachine
from routes.account_routes import account_bp
import download_service as ds
from rate_limit import limiter

_HWID = 'd' * 64
_OTHER_HWID = 'e' * 64


def _ephemeral_private_pem():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('ACTIVATION_PRIVATE_KEY', _ephemeral_private_pem())
    ds._pubkey_cache.update(pem=None, derived=False)  # re-derive for this key
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
        db.session.commit()
        app.config['_UID'] = u.id
    yield app
    ds._pubkey_cache.update(pem=None, derived=False)


@pytest.fixture
def client(app):
    with app.app_context():
        limiter.reset()
    return app.test_client()


def _token(app, hwid=_HWID):
    payload = {'sub': str(app.config['_UID']), 'email': 'user@example.com',
               'purpose': 'app_download'}
    return ds.issue_activation_token(payload, hwid)


def _seat_count(app):
    with app.app_context():
        return LicenseMachine.query.filter_by(user_id=app.config['_UID']).count()


# ── the happy path: uninstall frees the seat ─────────────────────────────────

def test_release_deletes_the_bound_seat(app, client):
    r = client.post('/api/license/release',
                    json={'license_token': _token(app), 'hwid': _HWID})
    assert r.status_code == 200
    assert r.get_json()['status'] == 'success'
    assert r.get_json()['code'] == 'released'
    assert _seat_count(app) == 0


def test_release_is_idempotent(app, client):
    body = {'license_token': _token(app), 'hwid': _HWID}
    assert client.post('/api/license/release', json=body).get_json()['code'] == 'released'
    # An uninstaller that retries (or a second uninstall) must not error out.
    again = client.post('/api/license/release', json=body)
    assert again.status_code == 200
    assert again.get_json()['status'] == 'success'
    assert again.get_json()['code'] == 'not_bound'


def test_release_works_without_a_body_hwid(app, client):
    # The seat to free is named by the token's own claim; hwid is optional.
    r = client.post('/api/license/release', json={'license_token': _token(app)})
    assert r.get_json()['code'] == 'released'
    assert _seat_count(app) == 0


def test_released_seat_frees_capacity_for_a_new_machine(app, client):
    # The whole point: after uninstalling, the next machine can activate.
    client.post('/api/license/release', json={'license_token': _token(app)})
    with app.app_context():
        from routes.account_routes import _bind_machine
        ok, _ = _bind_machine(User.query.get(app.config['_UID']), _OTHER_HWID)
        assert ok is True


# ── a token may only free its own seat ───────────────────────────────────────

def test_body_hwid_must_match_the_token_claim(app, client):
    r = client.post('/api/license/release',
                    json={'license_token': _token(app), 'hwid': _OTHER_HWID})
    assert r.status_code == 403
    assert r.get_json()['code'] == 'machine_mismatch'
    assert _seat_count(app) == 1


def test_token_cannot_free_another_machines_seat(app, client):
    # Two seats bound; a token for _OTHER_HWID must leave _HWID's seat alone.
    with app.app_context():
        db.session.add(LicenseMachine(user_id=app.config['_UID'], hwid=_OTHER_HWID))
        db.session.commit()
    client.post('/api/license/release', json={'license_token': _token(app, _OTHER_HWID)})
    with app.app_context():
        assert LicenseMachine.query.filter_by(hwid=_HWID).first() is not None
        assert LicenseMachine.query.filter_by(hwid=_OTHER_HWID).first() is None


def test_legacy_unbound_token_frees_nothing(app, client):
    # No 'hwid' claim: it never took a seat, and must not be able to name one.
    legacy = ds.issue_activation_token(
        {'sub': str(app.config['_UID']), 'email': 'user@example.com',
         'purpose': 'app_download'}, None)
    r = client.post('/api/license/release',
                    json={'license_token': legacy, 'hwid': _HWID})
    assert r.status_code == 200
    assert r.get_json()['code'] == 'not_bound'
    assert _seat_count(app) == 1  # the real seat survives


# ── the kill-switch must not be escapable via release ────────────────────────

def test_revoked_seat_cannot_be_released(app, client):
    with app.app_context():
        LicenseMachine.query.filter_by(hwid=_HWID).first().revoked = True
        db.session.commit()
    r = client.post('/api/license/release',
                    json={'license_token': _token(app), 'hwid': _HWID})
    assert r.status_code == 403
    assert r.get_json()['code'] == 'seat_revoked'
    assert _seat_count(app) == 1  # seat stays → re-activation still refused


def test_banned_account_cannot_release(app, client):
    with app.app_context():
        User.query.get(app.config['_UID']).banned = True
        db.session.commit()
    r = client.post('/api/license/release',
                    json={'license_token': _token(app), 'hwid': _HWID})
    assert r.status_code == 403
    assert r.get_json()['code'] == 'account_banned'
    assert _seat_count(app) == 1


# ── malformed input ──────────────────────────────────────────────────────────

def test_missing_token_400(client):
    r = client.post('/api/license/release', json={'hwid': _HWID})
    assert r.status_code == 400


def test_garbage_token_401(client):
    r = client.post('/api/license/release',
                    json={'license_token': 'not.a.jwt', 'hwid': _HWID})
    assert r.status_code == 401


def test_deleted_account_reports_success(app, client):
    token = _token(app)
    with app.app_context():
        LicenseMachine.query.filter_by(hwid=_HWID).delete()
        db.session.delete(User.query.get(app.config['_UID']))
        db.session.commit()
    r = client.post('/api/license/release', json={'license_token': token})
    assert r.status_code == 200
    assert r.get_json()['code'] == 'account_invalid'
