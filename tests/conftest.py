import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from flask import Flask, jsonify
from routes.math_routes import math_bp
from validators import validate_json

# ---------------------------------------------------------------------------
# Build a minimal test-only Flask app.
#
# We intentionally do NOT import from main.py: the online branch's main.py
# pulls in flask_socketio, firebase, and other heavy deps that are not
# installed in the test venv.  math_bp + our stub routes are sufficient to
# exercise every branch of the validate_json decorator.
# ---------------------------------------------------------------------------

_app = Flask(__name__)
_app.config['TESTING'] = True
_app.config['SECRET_KEY'] = 'test-secret'
_app.register_blueprint(math_bp)

# Test-only routes — one per type that is NOT already reachable through math_bp.
# Flask raises AssertionError on duplicate endpoint names, so guard with a flag.
_test_routes_registered = False


def _register_test_routes():
    global _test_routes_registered
    if _test_routes_registered:
        return

    @_app.route('/test_bool_route', methods=['POST'])
    @validate_json({'flag': (bool, False, True)})
    def _bool_route(validated_data):
        return jsonify({'flag': validated_data['flag']})

    @_app.route('/test_float_route', methods=['POST'])
    @validate_json({'timeout': (float, None, True)})
    def _float_route(validated_data):
        return jsonify({'timeout': validated_data['timeout']})

    @_app.route('/test_str_route', methods=['POST'])
    @validate_json({'name': str})          # plain-type (non-tuple) schema
    def _str_route(validated_data):
        return jsonify({'name': validated_data['name']})

    _test_routes_registered = True


@pytest.fixture
def client():
    """Minimal Flask test client with math_bp + test-only type-coercion routes."""
    _register_test_routes()
    with _app.test_client() as c:
        yield c
