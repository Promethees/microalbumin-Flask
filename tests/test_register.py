"""Account signup (src/routes/account_routes.py register()).

Exercises the REAL account_bp on a minimal app backed by in-memory SQLite.
send_verification_email is monkeypatched into a recorder: mail delivery is not
under test, but *whether* a mail is sent is the whole point of several cases
below, so the calls are captured rather than discarded.

What this file pins, and why:

  * Enumeration: signing up with a known address must be byte-for-byte
    indistinguishable from a fresh one. The endpoint used to answer 409 for a
    known email, which turned it into an "does this person have an account?"
    oracle.
  * No takeover: a duplicate signup must never overwrite the existing account's
    password or name. The neutral reply says "Account created" even when nothing
    was created, so this is the assertion that keeps that lie harmless.
  * Mail on duplicates: an unverified account re-sends the verification link (so
    a legitimate re-signup still works), a verified one sends nothing.
  * Rate limit: that resend is a mail-sending side effect on an unauthenticated
    endpoint, so without a limit anyone could register an arbitrary address and
    replay the POST to flood the inbox and drain the mail quota. REGISTER_LIMIT
    is what stops that, and is read from the constant so the limit and this test
    can never drift apart.
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from account import db, User
import routes.account_routes as ar
from routes.account_routes import account_bp
from rate_limit import limiter, REGISTER_LIMIT

_SECRET = 'test-secret'
_NEW = {'email': 'new@example.com', 'name': 'New Person', 'password': 'password123'}

# The single neutral reply every non-validation path returns.
_NEUTRAL = 'Account created. Please check your email to verify your address before downloading.'


def _count(limit_str):
    """'5 per hour' -> 5."""
    return int(limit_str.split()[0])


@pytest.fixture
def sent(monkeypatch):
    """Capture verification emails instead of sending them."""
    calls = []
    monkeypatch.setattr(ar, 'send_verification_email',
                        lambda to, name, token, base: calls.append(
                            {'to': to, 'name': name, 'token': token}))
    return calls


@pytest.fixture
def app(monkeypatch, sent):
    monkeypatch.setenv('SECRET_KEY', _SECRET)
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
        verified = User(email='verified@example.com', name='Verified', is_verified=True)
        verified.set_password('original-password')
        db.session.add(verified)
        unverified = User(email='unverified@example.com', name='Unverified', is_verified=False)
        unverified.set_password('original-password')
        db.session.add(unverified)
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    with app.app_context():
        limiter.reset()
    return app.test_client()


def _register(client, **over):
    return client.post('/api/account/register', json={**_NEW, **over})


# ── validation ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('missing', ['email', 'name', 'password'])
def test_missing_field_is_400(client, missing):
    assert _register(client, **{missing: ''}).status_code == 400


def test_no_body_is_400(client):
    assert client.post('/api/account/register').status_code == 400


def test_short_password_is_400(client):
    r = _register(client, password='short1')
    assert r.status_code == 400
    assert 'at least 8' in r.get_json()['message']


def test_email_without_at_is_400(client):
    r = _register(client, email='not-an-email')
    assert r.status_code == 400
    assert r.get_json()['message'] == 'Invalid email address'


def test_validation_failure_sends_no_mail(client, sent):
    _register(client, email='not-an-email')
    assert sent == []


# ── happy path ────────────────────────────────────────────────────────────────

def test_new_signup_creates_user(app, client):
    assert _register(client).status_code == 201
    with app.app_context():
        assert User.query.filter_by(email='new@example.com').first() is not None


def test_new_signup_returns_neutral_message(client):
    assert _register(client).get_json() == {'status': 'success', 'message': _NEUTRAL}


def test_new_signup_sends_verification_mail(client, sent):
    _register(client)
    assert len(sent) == 1
    assert sent[0]['to'] == 'new@example.com'
    assert sent[0]['token']


def test_email_is_normalized(app, client):
    assert _register(client, email='  MiXeD@Example.COM  ').status_code == 201
    with app.app_context():
        assert User.query.filter_by(email='mixed@example.com').first() is not None


def test_password_is_hashed_not_stored_plain(app, client):
    _register(client)
    with app.app_context():
        u = User.query.filter_by(email='new@example.com').first()
        assert u.password_hash != _NEW['password']
        assert u.check_password(_NEW['password'])


def test_new_account_starts_unverified(app, client):
    _register(client)
    with app.app_context():
        assert User.query.filter_by(email='new@example.com').first().is_verified is False


def test_mail_failure_still_returns_201(client, monkeypatch):
    """A dead mail provider must not fail the signup — the account exists."""
    def _boom(*a, **k):
        raise RuntimeError('smtp down')
    monkeypatch.setattr(ar, 'send_verification_email', _boom)
    assert _register(client).status_code == 201


# ── enumeration: known and unknown addresses are indistinguishable ────────────

@pytest.mark.parametrize('email', ['verified@example.com', 'unverified@example.com'])
def test_duplicate_signup_looks_identical_to_a_new_one(client, email):
    fresh = _register(client)
    dupe = _register(client, email=email)
    assert dupe.status_code == fresh.status_code == 201
    assert dupe.get_json() == fresh.get_json() == {'status': 'success', 'message': _NEUTRAL}


def test_duplicate_signup_creates_no_second_user(app, client):
    _register(client, email='verified@example.com')
    with app.app_context():
        assert User.query.filter_by(email='verified@example.com').count() == 1


# ── no takeover via re-registration ───────────────────────────────────────────

@pytest.mark.parametrize('email', ['verified@example.com', 'unverified@example.com'])
def test_duplicate_signup_does_not_change_password(app, client, email):
    _register(client, email=email, password='attacker-password')
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        assert u.check_password('original-password')
        assert not u.check_password('attacker-password')


def test_duplicate_signup_does_not_change_name(app, client):
    _register(client, email='verified@example.com', name='Attacker')
    with app.app_context():
        assert User.query.filter_by(email='verified@example.com').first().name == 'Verified'


def test_duplicate_signup_cannot_verify_an_account(app, client):
    _register(client, email='unverified@example.com')
    with app.app_context():
        assert User.query.filter_by(email='unverified@example.com').first().is_verified is False


# ── mail behaviour on duplicates ──────────────────────────────────────────────

def test_duplicate_on_verified_account_sends_nothing(client, sent):
    """A verified owner must not get mail because someone guessed their address."""
    _register(client, email='verified@example.com')
    assert sent == []


def test_duplicate_on_unverified_account_resends_link(client, sent):
    """A legitimate re-signup before verifying still gets a fresh link."""
    _register(client, email='unverified@example.com')
    assert len(sent) == 1
    assert sent[0]['to'] == 'unverified@example.com'


def test_resend_failure_still_returns_neutral_201(client, monkeypatch):
    """A mail error must not leak that the account exists via a different reply."""
    def _boom(*a, **k):
        raise RuntimeError('smtp down')
    monkeypatch.setattr(ar, 'send_verification_email', _boom)
    r = _register(client, email='unverified@example.com')
    assert r.status_code == 201
    assert r.get_json()['message'] == _NEUTRAL


# ── rate limit ────────────────────────────────────────────────────────────────

def test_register_is_rate_limited(client):
    limit = _count(REGISTER_LIMIT)
    codes = [_register(client, email=f'user{i}@example.com').status_code
             for i in range(limit + 1)]
    assert codes[-1] == 429
    assert all(c == 201 for c in codes[:limit])


def test_rate_limit_counts_validation_failures_too(client):
    """The limiter runs before the view, so junk requests can't be used to
    sidestep the quota and keep hammering the endpoint."""
    limit = _count(REGISTER_LIMIT)
    for _ in range(limit):
        _register(client, email='not-an-email')
    assert _register(client).status_code == 429


def test_rate_limit_caps_the_resend_mail_bomb(client, sent):
    """The vector the limit exists for: replaying a duplicate signup against an
    unverified address to flood that inbox. Mails must stop at the limit."""
    limit = _count(REGISTER_LIMIT)
    for _ in range(limit + 5):
        _register(client, email='unverified@example.com')
    assert len(sent) == limit
