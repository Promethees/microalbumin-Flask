import sys
import os
import json
import unittest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Stub heavy external dependencies before any project module is imported.
#
# These stubs MUST be undone as soon as file_routes is imported. pytest imports
# every test module during collection, so anything left in sys.modules here is
# inherited by every test module collected after this one (test_license_check,
# test_register, …). Those modules then bound `account.db` to a MagicMock
# instead of the real SQLAlchemy instance and failed with "The current Flask app
# is not registered with this 'SQLAlchemy' instance" — a failure that pointed at
# the victim rather than here, and vanished whenever the file was run alone.
_STUBBED = ('config', 'firebase_admin', 'firebase_service', 'flask_socketio',
            'eventlet', 'account', 'flask_sqlalchemy', 'sqlalchemy')
_saved_modules = {_m: sys.modules.get(_m) for _m in _STUBBED}
for _mod in _STUBBED:
    sys.modules[_mod] = MagicMock()
sys.modules['config'].Config.REDIS_URL = None
sys.modules['config'].Config.SECRET_KEY = 'test-secret'

import flask as _flask
_flask.session = {}

from flask import Flask
from routes.file_routes import file_bp

# file_routes now holds the mock-backed references it needs, so put sys.modules
# back: restore what was really there, and drop the stub entirely for anything
# that had not been imported yet so a later import loads the real package.
for _mod, _orig in _saved_modules.items():
    if _orig is None:
        sys.modules.pop(_mod, None)
    else:
        sys.modules[_mod] = _orig

# ---------------------------------------------------------------------------
# Shared sample CSV content strings
# ---------------------------------------------------------------------------

_KINETICS_CAL = (
    "# Measurement: ABS\n"
    "# MeasUnit: AU\n"
    "# TimeUnit: minutes\n"
    "# MeasMode: kinetics\n"
    "Concentration,maxRate,Slope,Sat,Time To Sat\n"
    "1,0.5,0.1,1.0,20\n"
)

_POINT_CAL = (
    "# Measurement: ABS\n"
    "# MeasUnit: AU\n"
    "# TimeUnit: minute\n"
    "# MeasMode: point\n"
    "Concentration,Value,TimePoint\n"
    "1,0.5,2.0\n"
)

_TIMESERIES = (
    "# Measurement: ABS\n"
    "# Unit: AU\n"
    "# Concentration: 10\n"
    "Timestamp,Value:1\n"
    "0,0.5\n"
    "1,0.6\n"
)


def _make_user_data(csv: dict = None, json_store: dict = None) -> dict:
    """Return a minimal user_data dict pre-populated with files."""
    return {
        'csv': dict(csv or {}),
        'json': {'kinetics': dict(json_store or {}), 'point': {}},
        'metadata_cache': {},
    }


class TestEditFile(unittest.TestCase):
    """Route-level tests for POST /edit_file on the online branch.

    The online edit_file stores files in user_data dicts (no filesystem).
    Two main-branch tests are omitted here because they have no equivalent:
      - process_running_locked  (no hardware-process guard in online)
      - path_traversal_rejected (no filesystem, no path traversal check)
    """

    def setUp(self):
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        app.register_blueprint(file_bp)
        self.app = app
        self.client = app.test_client()

    # ------------------------------------------------------------------
    # Helper: run a request with get_user_data / save_user_data / socketio
    # mocked so no real storage is touched.
    # ------------------------------------------------------------------
    def _post(self, data: dict, user_data: dict = None):
        """POST /edit_file with mocked user_data layer.

        Returns (response, user_data, mock_socketio).
        The route mutates user_data in-place before calling save_user_data, so
        callers can inspect user_data directly to verify stored content.
        save_user_data is patched at its source module to catch the inline
        re-import the route uses inside the function body.
        """
        if user_data is None:
            user_data = _make_user_data()

        with patch('routes.file_routes.get_user_data', return_value=user_data), \
             patch('user_data.save_user_data'), \
             patch('routes.file_routes.update_file_metadata'), \
             patch('routes.file_routes.socketio') as mock_sock:
            rv = self.client.post('/edit_file', data=data)
            return rv, user_data, mock_sock

    # ------------------------------------------------------------------
    # Required field validation
    # ------------------------------------------------------------------

    def test_missing_filename_returns_400(self):
        rv, *_ = self._post({'content': _KINETICS_CAL})
        self.assertEqual(rv.status_code, 400)
        self.assertEqual(rv.get_json()['status'], 'error')

    def test_missing_content_returns_400(self):
        rv, *_ = self._post({'filename': 'test.csv'})
        self.assertEqual(rv.status_code, 400)
        self.assertEqual(rv.get_json()['status'], 'error')

    # ------------------------------------------------------------------
    # Extension validation
    # ------------------------------------------------------------------

    def test_invalid_extension_returns_400(self):
        ud = _make_user_data(csv={'test.txt': 'data'})
        rv, *_ = self._post(
            {'filename': 'test.txt', 'new_filename': 'test.txt', 'content': 'data'},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 400)
        self.assertIn('must end with', rv.get_json()['message'])

    # ------------------------------------------------------------------
    # File existence
    # ------------------------------------------------------------------

    def test_file_not_found_returns_404(self):
        rv, *_ = self._post(
            {'filename': 'nonexistent.csv', 'content': _KINETICS_CAL},
            user_data=_make_user_data(),
        )
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(rv.get_json()['status'], 'error')

    # ------------------------------------------------------------------
    # Rename conflict
    # ------------------------------------------------------------------

    def test_rename_conflict_returns_409(self):
        ud = _make_user_data(csv={'original.csv': _KINETICS_CAL, 'existing.csv': _KINETICS_CAL})
        rv, *_ = self._post(
            {'filename': 'original.csv', 'new_filename': 'existing.csv',
             'content': _KINETICS_CAL},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 409)
        self.assertEqual(rv.get_json()['status'], 'error')

    # ------------------------------------------------------------------
    # JSON validation
    # ------------------------------------------------------------------

    def test_invalid_json_content_returns_400(self):
        ud = _make_user_data(json_store={'cal.json': '{"key": "value"}'})
        rv, *_ = self._post(
            {'filename': 'cal.json', 'new_filename': 'cal.json',
             'type': 'json', 'mode': 'kinetics',
             'content': '{not valid json}'},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 400)
        self.assertIn('Invalid JSON', rv.get_json()['message'])

    def test_json_success_saves_updated_content(self):
        ud = _make_user_data(json_store={'cal.json': '{"key": "old"}'})
        rv, ud, _ = self._post(
            {'filename': 'cal.json', 'new_filename': 'cal.json',
             'type': 'json', 'mode': 'kinetics',
             'content': '{"key": "updated"}'},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.get_json()['status'], 'success')
        saved_content = ud['json']['kinetics']['cal.json']
        self.assertEqual(json.loads(saved_content)['key'], 'updated')

    # ------------------------------------------------------------------
    # CSV validation
    # ------------------------------------------------------------------

    def test_csv_no_data_lines_returns_400(self):
        ud = _make_user_data(csv={'test.csv': _KINETICS_CAL})
        rv, *_ = self._post(
            {'filename': 'test.csv', 'content': '# Measurement: ABS\n# MeasUnit: AU\n'},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 400)
        self.assertIn('header row', rv.get_json()['message'])

    def test_csv_unknown_schema_returns_400(self):
        ud = _make_user_data(csv={'test.csv': _KINETICS_CAL})
        rv, *_ = self._post(
            {'filename': 'test.csv',
             'content': '# Measurement: ABS\nUnknownCol1,UnknownCol2\n1,2\n'},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 400)
        self.assertIn('Invalid CSV header', rv.get_json()['message'])

    def test_csv_missing_metadata_fields_returns_400(self):
        # kinetics_cal header present but MeasUnit/TimeUnit/MeasMode absent
        ud = _make_user_data(csv={'test.csv': _KINETICS_CAL})
        rv, *_ = self._post(
            {'filename': 'test.csv',
             'content': (
                 "# Measurement: ABS\n"
                 "Concentration,maxRate,Slope,Sat,Time To Sat\n"
                 "1,0.5,0.1,1.0,20\n"
             )},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 400)

    def test_csv_invalid_data_row_returns_400(self):
        ud = _make_user_data(csv={'test.csv': _KINETICS_CAL})
        rv, *_ = self._post(
            {'filename': 'test.csv',
             'content': (
                 "# Measurement: ABS\n# MeasUnit: AU\n# TimeUnit: minutes\n# MeasMode: kinetics\n"
                 "Concentration,maxRate,Slope,Sat,Time To Sat\n"
                 "not_a_number,bad,data,row,here\n"
             )},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 400)
        self.assertIn('Invalid data in row', rv.get_json()['message'])

    # ------------------------------------------------------------------
    # CSV happy paths — all three schemas
    # ------------------------------------------------------------------

    def test_csv_kinetics_cal_success(self):
        ud = _make_user_data(csv={'test.csv': _KINETICS_CAL})
        new_content = (
            "# Measurement: ABS\n# MeasUnit: AU\n# TimeUnit: minutes\n# MeasMode: kinetics\n"
            "Concentration,maxRate,Slope,Sat,Time To Sat\n"
            "2,0.8,0.2,2.0,30\n"
        )
        rv, ud, _ = self._post(
            {'filename': 'test.csv', 'content': new_content},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.get_json()['status'], 'success')
        self.assertIn('2,0.8,0.2,2.0,30', ud['csv']['test.csv'])

    def test_csv_point_cal_success(self):
        ud = _make_user_data(csv={'test.csv': _POINT_CAL})
        rv, *_ = self._post({'filename': 'test.csv', 'content': _POINT_CAL}, user_data=ud)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.get_json()['status'], 'success')

    def test_csv_timeseries_success(self):
        ud = _make_user_data(csv={'test.csv': _TIMESERIES})
        rv, *_ = self._post({'filename': 'test.csv', 'content': _TIMESERIES}, user_data=ud)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.get_json()['status'], 'success')

    # ------------------------------------------------------------------
    # calibrate_mode — rows sorted by concentration in-memory
    # ------------------------------------------------------------------

    def test_calibrate_mode_sorts_rows(self):
        ud = _make_user_data(csv={'test.csv': _KINETICS_CAL})
        out_of_order = (
            "# Measurement: ABS\n# MeasUnit: AU\n# TimeUnit: minutes\n# MeasMode: kinetics\n"
            "Concentration,maxRate,Slope,Sat,Time To Sat\n"
            "5,0.8,0.2,2.0,30\n"
            "1,0.5,0.1,1.0,20\n"
        )
        rv, ud, _ = self._post(
            {'filename': 'test.csv', 'content': out_of_order, 'calibrate_mode': 'kinetics'},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 200)
        saved = ud['csv']['test.csv']
        data_lines = [l for l in saved.splitlines() if l and not l.startswith('#')]
        self.assertTrue(data_lines[1].startswith('1'), "concentration 1 should sort before 5")
        self.assertTrue(data_lines[2].startswith('5'))

    # ------------------------------------------------------------------
    # Rename success
    # ------------------------------------------------------------------

    def test_rename_success(self):
        ud = _make_user_data(csv={'original.csv': _KINETICS_CAL})
        rv, ud, _ = self._post(
            {'filename': 'original.csv', 'new_filename': 'renamed.csv',
             'content': _KINETICS_CAL},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.get_json()['status'], 'success')
        self.assertNotIn('original.csv', ud['csv'])
        self.assertIn('renamed.csv', ud['csv'])

    # ------------------------------------------------------------------
    # socketio.emit is called on success
    # ------------------------------------------------------------------

    def test_csv_success_emits_update_csv(self):
        ud = _make_user_data(csv={'test.csv': _KINETICS_CAL})
        rv, _, mock_sock = self._post(
            {'filename': 'test.csv', 'content': _KINETICS_CAL},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 200)
        mock_sock.emit.assert_called_with('update_csv')

    def test_json_success_emits_update_json(self):
        ud = _make_user_data(json_store={'cal.json': '{"key": "value"}'})
        rv, _, mock_sock = self._post(
            {'filename': 'cal.json', 'new_filename': 'cal.json',
             'type': 'json', 'mode': 'kinetics',
             'content': '{"key": "value"}'},
            user_data=ud,
        )
        self.assertEqual(rv.status_code, 200)
        mock_sock.emit.assert_called_with('update_json', {'mode': 'kinetics'})


if __name__ == '__main__':
    unittest.main()
