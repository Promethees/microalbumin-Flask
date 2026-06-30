"""Tests for the native ScatterChart export in /export_report_excel.

Guards the fix for calibration standards points arriving from the client as
strings: they must be written to the helper columns as real numbers, or Excel
refuses to plot them (the "number stored as text" marker) and ignores the user's
locale decimal separator.
"""
import io
import os
import sys

import pytest
from openpyxl import load_workbook

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import app  # noqa: E402

# Helper columns: AA(27)=pt_x, AB(28)=pt_y, AC(29)=fit_x, AD(30)=fit_y
PT_X, PT_Y, FIT_X, FIT_Y = 27, 28, 29, 30


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _helper_sheet(wb):
    """The worksheet whose row-1 header at column AA is 'pt_x'."""
    for ws in wb.worksheets:
        if ws.cell(1, PT_X).value == 'pt_x':
            return ws
    return None


def _calibrate_item(points, fit):
    return {
        'filename': 'cal.csv',
        'mode': 'calibrate',
        'csv_columns': ['Concentration', 'maxRate'],
        'csv_rows': [{'Concentration': '5', 'maxRate': '0.00738'}],
        'chart_series': [{
            'label': 'maxRate — Michaelis-Menten',
            'title': 'maxRate — Michaelis-Menten',
            'algo': 'Michaelis-Menten',
            'xLabel': 'Concentration (ng/µL)', 'yLabel': 'maxRate',
            'points': points,
            'fit': fit,
        }],
    }


def test_string_points_written_as_numbers(client):
    # The standards arrive as strings (as they do from the CSV-parsed client).
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.00738'}, {'x': '50', 'y': '0.01884'}],
        fit=[{'x': 1.5, 'y': 0.002}, {'x': 2.5, 'y': 0.004}],
    )
    rv = client.post('/export_report_excel', json={'items': [item], 'subject': 'T'})
    assert rv.status_code == 200

    wb = load_workbook(io.BytesIO(rv.data))
    ws = _helper_sheet(wb)
    assert ws is not None, "pt_x helper header not found"

    # Both standards must be real numbers (not text) in pt_x / pt_y.
    for row in (2, 3):
        assert isinstance(ws.cell(row, PT_X).value, (int, float)), \
            f"pt_x row {row} is {ws.cell(row, PT_X).value!r} (text → unplottable)"
        assert isinstance(ws.cell(row, PT_Y).value, (int, float)), \
            f"pt_y row {row} is {ws.cell(row, PT_Y).value!r}"
    assert ws.cell(2, PT_X).value == 5.0
    assert ws.cell(2, PT_Y).value == pytest.approx(0.00738)
    # Fit values stay numeric too.
    assert isinstance(ws.cell(2, FIT_X).value, (int, float))
    assert isinstance(ws.cell(2, FIT_Y).value, (int, float))


def test_non_numeric_points_are_skipped(client):
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.1'}, {'x': 'NONE', 'y': '0.2'}],
        fit=[],
    )
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert rv.status_code == 200

    ws = _helper_sheet(load_workbook(io.BytesIO(rv.data)))
    # Only the valid standard is written; the 'NONE' x is dropped (not text).
    assert ws.cell(2, PT_X).value == 5.0
    assert ws.cell(3, PT_X).value is None
