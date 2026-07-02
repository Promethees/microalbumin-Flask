"""Unit tests for the request-origin guard (src/security.py).

Built on a minimal Flask app with a dummy POST/GET route so the guard is
exercised in isolation — no dependence on the real app's routes or its slow
import. state.args is left unset here, so the alias defaults to easyokapi.com.
"""
import pytest
from flask import Flask, jsonify

from security import init_request_guard


@pytest.fixture
def client():
    app = Flask(__name__)
    init_request_guard(app)

    @app.route('/x', methods=['POST'])
    def _x():
        return jsonify(ok=True)

    @app.route('/r', methods=['GET'])
    def _r():
        return jsonify(ok=True)

    return app.test_client()


def test_same_origin_post_allowed(client):
    # Test client sends Host: localhost and no Origin — a same-origin request.
    rv = client.post('/x')
    assert rv.status_code == 200


def test_cross_origin_post_blocked(client):
    rv = client.post('/x', headers={'Origin': 'http://evil.example'})
    assert rv.status_code == 403
    assert rv.get_json()['code'] == 'forbidden_origin'


def test_loopback_origin_allowed(client):
    rv = client.post('/x', headers={'Origin': 'http://127.0.0.1:5099'})
    assert rv.status_code == 200


def test_alias_origin_allowed(client):
    rv = client.post('/x', headers={'Origin': 'http://easyokapi.com:5099'})
    assert rv.status_code == 200


def test_foreign_host_blocked_dns_rebinding(client):
    # A rebound request arrives with the attacker's Host (and matching Origin).
    rv = client.post('/x', headers={'Host': 'attacker.example',
                                    'Origin': 'http://attacker.example'})
    assert rv.status_code == 403
    assert rv.get_json()['code'] == 'forbidden_host'


def test_cross_origin_referer_blocked(client):
    rv = client.post('/x', headers={'Referer': 'http://evil.example/page'})
    assert rv.status_code == 403
    assert rv.get_json()['code'] == 'forbidden_referer'


def test_same_origin_referer_allowed(client):
    rv = client.post('/x', headers={'Referer': 'http://localhost:5099/'})
    assert rv.status_code == 200


def test_null_origin_blocked(client):
    rv = client.post('/x', headers={'Origin': 'null'})
    assert rv.status_code == 403


def test_safe_method_not_guarded(client):
    # GET is a read; a cross-origin Origin on it is not blocked.
    rv = client.get('/r', headers={'Origin': 'http://evil.example'})
    assert rv.status_code == 200
