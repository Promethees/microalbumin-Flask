import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import app as _app
import state

# Register test-only routes exactly once per process.
# Flask raises AssertionError on duplicate endpoint registration, so guard it.
_test_routes_registered = False


def _register_test_routes():
    global _test_routes_registered
    if _test_routes_registered:
        return
    from validators import validate_json
    from flask import jsonify

    @_app.route('/test_bool_route', methods=['POST'])
    @validate_json({'flag': (bool, False, True)})
    def _bool_route(validated_data):
        return jsonify({'flag': validated_data['flag']})

    @_app.route('/test_float_route', methods=['POST'])
    @validate_json({'timeout': (float, None, True)})
    def _float_route(validated_data):
        return jsonify({'timeout': validated_data['timeout']})

    _test_routes_registered = True


@pytest.fixture
def client():
    """Shared Flask test client. Registers test-only routes on first use.

    test_app.py defines its own local `client` fixture; pytest resolves the
    local one for tests in that file, so there is no collision.
    """
    _register_test_routes()
    _app.config['TESTING'] = True
    state.process = None
    with _app.test_client() as c:
        yield c
