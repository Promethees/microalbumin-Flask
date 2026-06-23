"""Desktop revocation poll endpoint (POST /api/license/check).

The client posts its permanent activation token + hwid; the server answers
'active' or 'revoked' so the client can enforce admin revocation locally (a
permanent token verifies offline and cannot otherwise tell it was revoked).

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


def test_active_for_bound_machine(app, client):
    r = client.post('/api/license/check',
                    json={'license_token': _token(app), 'hwid': _HWID})
    assert r.status_code == 200
    assert r.get_json()['status'] == 'active'


def test_revoked_when_seat_revoked(app, client):
    with app.app_context():
        m = LicenseMachine.query.filter_by(hwid=_HWID).first()
        m.revoked = True
        db.session.commit()
    r = client.post('/api/license/check',
                    json={'license_token': _token(app), 'hwid': _HWID})
    assert r.status_code == 200
    assert r.get_json()['status'] == 'revoked'


def test_revoked_when_seat_missing(app, client):
    with app.app_context():
        LicenseMachine.query.filter_by(hwid=_HWID).delete()
        db.session.commit()
    r = client.post('/api/license/check',
                    json={'license_token': _token(app), 'hwid': _HWID})
    assert r.get_json()['status'] == 'revoked'


def test_revoked_on_wrong_machine(app, client):
    # Token bound to _HWID, but presented from a different machine.
    r = client.post('/api/license/check',
                    json={'license_token': _token(app), 'hwid': 'e' * 64})
    assert r.get_json()['status'] == 'revoked'


def test_missing_token_400(client):
    r = client.post('/api/license/check', json={'hwid': _HWID})
    assert r.status_code == 400


def test_garbage_token_401_not_a_verdict(client):
    r = client.post('/api/license/check',
                    json={'license_token': 'not.a.jwt', 'hwid': _HWID})
    assert r.status_code == 401  # client treats this as "no change", never blocks
