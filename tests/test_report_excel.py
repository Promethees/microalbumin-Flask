"""Tests for the native calibration chart in /export_report_excel.

The chart is a value-axis ScatterChart with a single SHARED, sorted X column
(both series reference it) — which Google Sheets renders as a proportional
value axis — plus a "nice numbers" major-unit so the X ticks are round
(0, 100, …, 500). These tests guard:
  * string standards points coerced to real numbers (plottable, locale-aware);
  * one shared X column with numeric caches (independent X makes Sheets drop a
    series / fall to a category axis);
  * the value axis clamped to round nice-number ticks;
  * two distinct markers, no native trendline.
"""
import io
import os
import re
import sys
import zipfile

import pytest
from openpyxl import load_workbook

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import app  # noqa: E402
from routes.file_routes import _nice_axis_ticks  # noqa: E402

# Shared-X helper layout: AA(27)=x (shared), AB(28)=std_y, AC(29)=fit_y.
X, STD_Y, FIT_Y = 27, 28, 29


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _helper_sheet(wb):
    for ws in wb.worksheets:
        if ws.cell(1, X).value == 'x':
            return ws
    return None


def _rows(ws):
    """(x, std_y, fit_y) helper rows until the shared X column runs out."""
    out, r = [], 2
    while ws.cell(r, X).value is not None:
        out.append((ws.cell(r, X).value, ws.cell(r, STD_Y).value, ws.cell(r, FIT_Y).value))
        r += 1
    return out


def _fit_grid(lo, hi, n=24):
    step = (hi - lo) / (n - 1)
    return [{'x': lo + i * step, 'y': 0.1 * ((lo + i * step) / (300 + lo + i * step))}
            for i in range(n)]


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


# ── Nice-numbers tick algorithm ──────────────────────────────────────────────

def test_nice_axis_ticks_round_and_evenly_spaced():
    assert _nice_axis_ticks(5, 500) == [0, 100, 200, 300, 400, 500]
    assert _nice_axis_ticks(5, 50) == [0, 10, 20, 30, 40, 50]
    assert _nice_axis_ticks(100, 560) == [100, 200, 300, 400, 500, 600]
    ticks = _nice_axis_ticks(0.2, 2.1)
    steps = {round(b - a, 10) for a, b in zip(ticks, ticks[1:])}
    assert len(steps) == 1, f"ticks not evenly spaced: {ticks}"


# ── Cell writing ─────────────────────────────────────────────────────────────

def test_string_points_written_as_numbers(client):
    # The standards arrive as strings (as they do from the CSV-parsed client).
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.00738'}, {'x': '50', 'y': '0.01884'},
                {'x': '500', 'y': '0.085'}],
        fit=_fit_grid(0, 500),
    )
    rv = client.post('/export_report_excel', json={'items': [item], 'subject': 'T'})
    assert rv.status_code == 200

    ws = _helper_sheet(load_workbook(io.BytesIO(rv.data)))
    assert ws is not None, "shared-x helper header not found"
    rows = _rows(ws)

    xs = [x for (x, _, _) in rows]
    assert all(isinstance(x, (int, float)) for x in xs), f"non-numeric X: {xs}"
    assert xs == sorted(xs), "shared X column is not sorted"
    # Standards survive as real numbers (string→float), blank-separated from the fit.
    std = sorted(ys for (x, ys, yf) in rows if ys is not None)
    assert std == pytest.approx([0.00738, 0.01884, 0.085])
    assert all((ys is None) != (yf is None) for (x, ys, yf) in rows)  # exactly one Y/row


def test_non_numeric_points_are_skipped(client):
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.1'}, {'x': 'NONE', 'y': '0.2'}],
        fit=[],
    )
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert rv.status_code == 200

    ws = _helper_sheet(load_workbook(io.BytesIO(rv.data)))
    rows = _rows(ws)
    assert len(rows) == 1                     # only the valid standard
    assert rows[0][0] == pytest.approx(5.0)   # x
    assert rows[0][1] == pytest.approx(0.1)   # std_y


# ── Chart structure ──────────────────────────────────────────────────────────

def _chart_xml(xlsx_bytes):
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        names = sorted(n for n in z.namelist() if n.startswith('xl/charts/chart'))
        assert names, "no chart embedded in the workbook"
        return z.read(names[0]).decode('utf-8')


def test_shared_x_value_scatter_with_round_ticks(client):
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.00738'}, {'x': '50', 'y': '0.01884'},
                {'x': '500', 'y': '0.085'}],
        fit=_fit_grid(0, 500),
    )
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert rv.status_code == 200
    xml = _chart_xml(rv.data)

    # A value-axis scatter (two value axes, no category) — proportional X.
    assert '<scatterChart>' in xml and '<lineChart>' not in xml
    assert xml.count('<valAx>') == 2 and '<catAx>' not in xml
    assert xml.count('<ser>') == 2
    # Both series reference the SAME (shared) X column — that is what keeps Sheets
    # on a proportional value axis (independent X drops a series / goes category).
    xrefs = re.findall(r'<xVal><numRef><f>([^<]+)</f>', xml)
    assert len(xrefs) == 2 and xrefs[0] == xrefs[1], f"series do not share X: {xrefs}"
    assert xml.count('<numCache>') == 4
    # X axis clamped to round nice-numbers ticks (0..500 by 100).
    assert '<max val="500"' in xml and '<min val="0"' in xml
    assert '<majorUnit val="100"' in xml
    # Two distinct markers, neither joined by a line (both <a:noFill/>).
    assert xml.count('<symbol val="diamond"') == 1   # standards
    assert xml.count('<symbol val="dot"') == 1       # fit — finest marker
    assert '<symbol val="none"' not in xml
    assert xml.count('<a:noFill') == 2, "a series carries a connecting line"
    assert 'trendline' not in xml.lower()


def test_no_native_trendline_for_michaelis_menten(client):
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.00738'}, {'x': '50', 'y': '0.01884'}],
        fit=_fit_grid(0, 200, 12),
    )  # _calibrate_item already uses algo 'Michaelis-Menten'
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert 'trendline' not in _chart_xml(rv.data).lower()
