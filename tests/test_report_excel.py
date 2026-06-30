"""Tests for the native ScatterChart export in /export_report_excel.

Guards the fix for calibration standards points arriving from the client as
strings: they must be written to the helper columns as real numbers, or Excel
refuses to plot them (the "number stored as text" marker) and ignores the user's
locale decimal separator.
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

# Shared-X helper layout: AA(27)=x (shared), AB(28)=std_y, AC(29)=fit_y.
# Standards occupy the first rows, the fit curve the rows after.
X_COL, STD_Y, FIT_Y = 27, 28, 29


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _helper_sheet(wb):
    """The worksheet whose row-1 header at column AA is the shared 'x'."""
    for ws in wb.worksheets:
        if ws.cell(1, X_COL).value == 'x':
            return ws
    return None


def _read_helper_rows(ws):
    """Read the (x, std_y, fit_y) helper rows until the shared X runs out."""
    rows, r = [], 2
    while ws.cell(r, X_COL).value is not None:
        rows.append((ws.cell(r, X_COL).value,
                     ws.cell(r, STD_Y).value,
                     ws.cell(r, FIT_Y).value))
        r += 1
    return rows


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
    assert ws is not None, "shared-x helper header not found"
    rows = _read_helper_rows(ws)

    xs = [x for (x, _, _) in rows]
    # Shared X must be all-numeric (not text) and MONOTONIC — non-monotonic X makes
    # Google Sheets fall back to a category axis (the "horrible" mis-render).
    assert all(isinstance(x, (int, float)) for x in xs), f"non-numeric X: {xs}"
    assert xs == sorted(xs), f"shared X column is not sorted: {xs}"
    # Every row carries exactly one series' Y (blank-separated datasets).
    for x, ys, yf in rows:
        assert (ys is None) != (yf is None), f"row x={x} has both/neither Y: {ys!r},{yf!r}"
    # Both standards survive as real numbers at their own X.
    std = {x: ys for (x, ys, yf) in rows if ys is not None}
    assert std[5.0] == pytest.approx(0.00738)
    assert std[50.0] == pytest.approx(0.01884)
    assert all(isinstance(v, (int, float)) for v in std.values())
    # Both fit points survive as numbers too.
    fit = {x: yf for (x, ys, yf) in rows if yf is not None}
    assert set(fit) == {1.5, 2.5}
    assert all(isinstance(v, (int, float)) for v in fit.values())


def test_non_numeric_points_are_skipped(client):
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.1'}, {'x': 'NONE', 'y': '0.2'}],
        fit=[],
    )
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert rv.status_code == 200

    ws = _helper_sheet(load_workbook(io.BytesIO(rv.data)))
    # Only the valid standard is written; the 'NONE' x is dropped (not text).
    assert ws.cell(2, X_COL).value == 5.0
    assert ws.cell(3, X_COL).value is None


def _chart_xml(xlsx_bytes):
    """The first embedded chart's XML (openpyxl can't read charts back)."""
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        names = sorted(n for n in z.namelist() if n.startswith('xl/charts/chart'))
        assert names, "no chart embedded in the workbook"
        return z.read(names[0]).decode('utf-8')


def test_fit_series_has_markers_for_google_sheets(client):
    # Both series are markers-only (no lines): a line series makes Google Sheets
    # import the chart as a *line* chart (category axis labelling every point),
    # and the fit must show as scatter points there anyway.
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.00738'}, {'x': '50', 'y': '0.01884'}],
        fit=[{'x': 1.5, 'y': 0.002}, {'x': 2.5, 'y': 0.004}],
    )
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert rv.status_code == 200
    xml = _chart_xml(rv.data)

    assert '<scatterChart>' in xml
    assert '<scatterStyle val="marker"' in xml      # markers-only style
    assert xml.count('<ser>') == 2          # standards + fit
    # Both series must reference the SAME X column — Google Sheets' scatter model
    # allows only one X column per chart and drops series with a different X.
    xrefs = re.findall(r'<xVal><numRef><f>([^<]+)</f>', xml)
    assert len(xrefs) == 2 and xrefs[0] == xrefs[1], f"series do not share an X column: {xrefs}"
    # ...while the Y columns differ (standards vs fit).
    yrefs = re.findall(r'<yVal><numRef><f>([^<]+)</f>', xml)
    assert len(yrefs) == 2 and yrefs[0] != yrefs[1]
    # Each series ref carries an explicit numeric cache (xVal + yVal × 2 series) so
    # importers read a value axis with clean ticks instead of labelling every point.
    assert xml.count('<numCache>') == 4
    assert xml.count('<valAx>') == 2 and '<catAx>' not in xml
    # Both series are markers; NEITHER carries a connecting line — both series
    # lines are <a:noFill/> (a real line would trigger Sheets' line-chart import).
    assert '<symbol val="none"' not in xml, "a series still has marker symbol 'none'"
    assert xml.count('<symbol val="circle"') == 2
    assert xml.count('<a:noFill') == 2, "a series carries a connecting line"
    # And we must NOT delegate to a native trendline (wrong curve for this chart).
    assert 'trendline' not in xml.lower()


def test_no_native_trendline_for_michaelis_menten(client):
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.00738'}, {'x': '50', 'y': '0.01884'}],
        fit=[{'x': 1.5, 'y': 0.002}, {'x': 2.5, 'y': 0.004}],
    )  # _calibrate_item already uses algo 'Michaelis-Menten'
    rv = client.post('/export_report_excel', json={'items': [item]})
    xml = _chart_xml(rv.data)
    assert 'trendline' not in xml.lower()
