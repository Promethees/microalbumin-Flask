"""Route-level tests for the point-mode Turn axis (online branch).

Covers the three places the Turn axis crosses an HTTP boundary:
  * GET  /get_data                  — Turn column renamed to Timestamp + x_axis flag
  * POST /export_data               — turn-based calibration table + mixing guard
  * POST /convert_timestamp_to_turn — one-way Timestamp → Turn relabel

The heavy online dependencies (socketio, firebase, SQLAlchemy, config) are
stubbed the same way tests/test_edit_file.py does, and restored immediately
after the blueprints are imported so later-collected modules see the real ones.
"""

import sys
import os
import json
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

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
from routes.data_routes import data_bp

for _mod, _orig in _saved_modules.items():
    if _orig is None:
        sys.modules.pop(_mod, None)
    else:
        sys.modules[_mod] = _orig


_TURN_SERIES = (
    "# Measurement: ABS\n"
    "# Unit: AU\n"
    "# Concentration: 10\n"
    "Turn,Value:1,Value:2\n"
    "1,0.5,0.6\n"
    "2,0.7,0.8\n"
)

_TIMESERIES = (
    "# Measurement: ABS\n"
    "# Unit: AU\n"
    "# Concentration: 10\n"
    "Timestamp,Value:1\n"
    "0.00,0.5\n"
    "1.50,0.6\n"
    "3.00,0.7\n"
)

_POINT_CAL_TIME = (
    "# Measurement: ABS\n"
    "# MeasUnit: AU\n"
    "# TimeUnit: minute\n"
    "# MeasMode: point\n"
    "# ConcenUnit: ng/µL\n"
    "Concentration,Value,TimePoint\n"
    "1,0.5,2.0\n"
)

_POINT_CAL_TURN = (
    "# Measurement: ABS\n"
    "# MeasUnit: AU\n"
    "# TimeUnit: minute\n"
    "# MeasMode: point\n"
    "# ConcenUnit: ng/µL\n"
    "Concentration,Value\n"
    "1,0.5\n"
)


def _make_user_data(csv=None, json_store=None):
    return {
        'csv': dict(csv or {}),
        'json': {'kinetics': dict(json_store or {}), 'point': {}},
        'metadata_cache': {},
    }


class _TurnRouteTestCase(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        app.register_blueprint(file_bp)
        app.register_blueprint(data_bp)
        self.client = app.test_client()

    @staticmethod
    @contextmanager
    def _session_stub(user_data):
        """Stand in for user_data_session(): hands back the same dict."""
        yield user_data


class TestGetDataTurnAxis(_TurnRouteTestCase):
    def _get(self, user_data, file_name):
        with patch('routes.data_routes.get_user_data', return_value=user_data):
            return self.client.get('/get_data?file=' + file_name)

    def test_turn_column_is_renamed_to_timestamp(self):
        # The whole client pipeline is keyed on "Timestamp"; a Turn file is
        # renamed on read so nothing downstream needs a second X-column name.
        ud = _make_user_data({'turn.csv': _TURN_SERIES})
        body = self._get(ud, 'turn.csv').get_json()
        assert body['x_axis'] == 'turn'
        assert body['data'][0] == {'Timestamp': 1, 'Value:1': 0.5, 'Value:2': 0.6}
        assert 'Turn' not in body['data'][0]
        assert body['num_sources'] == 2

    def test_timeseries_file_reports_time_axis(self):
        ud = _make_user_data({'ts.csv': _TIMESERIES})
        body = self._get(ud, 'ts.csv').get_json()
        assert body['x_axis'] == 'time'
        assert body['data'][0]['Timestamp'] == 0.0

    def test_stored_content_is_not_rewritten_by_a_read(self):
        ud = _make_user_data({'turn.csv': _TURN_SERIES})
        self._get(ud, 'turn.csv')
        assert ud['csv']['turn.csv'] == _TURN_SERIES


class TestExportDataTurnAxis(_TurnRouteTestCase):
    def _post(self, payload, user_data):
        with patch('routes.data_routes.get_user_data', return_value=user_data), \
             patch('routes.data_routes.get_user_id', return_value='uid'), \
             patch('user_data.save_user_data'):
            return self.client.post('/export_data', json=payload)

    @staticmethod
    def _payload(**over):
        base = {
            'save_file': 'results',
            'measMode': 'point',
            'meas': 'ABS',
            'measUnit': 'AU',
            'concenUnit': 'ng/µL',
            'newFile': True,
            'entries': [{'con': '1', 'estValue': '0.5'},
                        {'con': '2', 'estValue': '0.9'}],
        }
        base.update(over)
        return base

    def test_turn_export_writes_two_column_table(self):
        ud = _make_user_data()
        rv = self._post(self._payload(xAxis='turn'), ud)
        assert rv.get_json()['status'] == 'success'
        content = ud['csv']['results_point.csv']
        rows = [l for l in content.splitlines() if l and not l.startswith('#')]
        assert rows[0] == 'Concentration,Value'
        assert rows[1:] == ['1,0.5', '2,0.9']

    def test_time_export_keeps_timepoint_column(self):
        ud = _make_user_data()
        rv = self._post(self._payload(), ud)
        assert rv.get_json()['status'] == 'success'
        header = [l for l in ud['csv']['results_point.csv'].splitlines()
                  if l and not l.startswith('#')][0]
        assert header == 'Concentration,Value,TimePoint'

    def test_appending_turn_rows_to_a_time_table_is_refused(self):
        # Column counts differ — the two tables cannot share a file.
        ud = _make_user_data({'results_point.csv': _POINT_CAL_TIME})
        body = self._post(self._payload(xAxis='turn'), ud).get_json()
        assert body['status'] == 'error'
        assert 'time-based' in body['message']
        assert ud['csv']['results_point.csv'] == _POINT_CAL_TIME  # untouched

    def test_appending_time_rows_to_a_turn_table_is_refused(self):
        ud = _make_user_data({'results_point.csv': _POINT_CAL_TURN})
        body = self._post(self._payload(), ud).get_json()
        assert body['status'] == 'error'
        assert 'turn-based' in body['message']

    def test_appending_turn_rows_to_a_turn_table_succeeds(self):
        ud = _make_user_data({'results_point.csv': _POINT_CAL_TURN})
        body = self._post(self._payload(xAxis='turn'), ud).get_json()
        assert body['status'] == 'success', body
        rows = [l for l in ud['csv']['results_point.csv'].splitlines()
                if l and not l.startswith('#')]
        assert rows[0] == 'Concentration,Value'
        assert rows[1:] == ['1,0.5', '1,0.5', '2,0.9']


class TestExportCalCoefsTurnAxis(_TurnRouteTestCase):
    def _post(self, payload, user_data):
        with patch('routes.data_routes.get_user_data', return_value=user_data), \
             patch('user_data.save_user_data'):
            return self.client.post('/export_cal_coefs', json=payload)

    @staticmethod
    def _payload(**over):
        base = {
            'fit_type': 'linear',
            'for_meas': 'ABS',
            'measUnit': 'AU',
            'concenUnit': 'ng/µL',
            'coef_content': {'coefficients': [1.0, 2.0], 'rSquared': 0.99},
            'time': 2.0,
            'file_name': 'curve',
            'cal_mode': 'point',
            'cal_params': [],
            'threshold_val': 0,
            'regress_algo': 'linear',
        }
        base.update(over)
        return base

    def test_turn_curve_records_x_axis_and_omits_time(self):
        ud = _make_user_data()
        rv = self._post(self._payload(x_axis='turn'), ud)
        assert rv.get_json()['status'] == 'success'
        curve = json.loads(list(ud['json']['point'].values())[0])
        assert curve['x_axis'] == 'turn'
        assert 'time' not in curve and 'time-unit' not in curve

    def test_time_curve_records_time_and_omits_x_axis(self):
        ud = _make_user_data()
        rv = self._post(self._payload(), ud)
        assert rv.get_json()['status'] == 'success'
        curve = json.loads(list(ud['json']['point'].values())[0])
        assert curve['time'] == 2.0 and curve['time-unit'] == 'minute'
        assert 'x_axis' not in curve


class TestConvertTimestampToTurn(_TurnRouteTestCase):
    def _post(self, filename, user_data):
        with patch('routes.file_routes.get_user_data', return_value=user_data), \
             patch('routes.file_routes.user_data_session',
                   lambda *a, **k: self._session_stub(user_data)), \
             patch('routes.file_routes.update_file_metadata'), \
             patch('routes.file_routes.socketio'):
            return self.client.post('/convert_timestamp_to_turn',
                                    json={'filename': filename})

    def test_converts_header_and_reindexes_rows(self):
        ud = _make_user_data({'ts.csv': _TIMESERIES})
        body = self._post('ts.csv', ud).get_json()
        assert body['status'] == 'success'
        assert body['count'] == 3
        lines = ud['csv']['ts.csv'].splitlines()
        # Metadata survives verbatim; the X column is relabelled and reindexed.
        assert lines[0] == '# Measurement: ABS'
        data = [l for l in lines if l and not l.startswith('#')]
        assert data == ['Turn,Value:1', '1,0.5', '2,0.6', '3,0.7']

    def test_already_turn_file_is_rejected(self):
        ud = _make_user_data({'turn.csv': _TURN_SERIES})
        rv = self._post('turn.csv', ud)
        assert rv.status_code == 400
        assert ud['csv']['turn.csv'] == _TURN_SERIES

    def test_calibration_file_is_rejected(self):
        ud = _make_user_data({'cal.csv': _POINT_CAL_TIME})
        rv = self._post('cal.csv', ud)
        assert rv.status_code == 400
        assert ud['csv']['cal.csv'] == _POINT_CAL_TIME

    def test_missing_file_returns_404(self):
        rv = self._post('nope.csv', _make_user_data())
        assert rv.status_code == 404

    def test_non_csv_is_rejected(self):
        rv = self._post('curve.json', _make_user_data())
        assert rv.status_code == 400


if __name__ == '__main__':
    unittest.main()
