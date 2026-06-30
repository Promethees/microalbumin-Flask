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

    # The two standards sit on the first rows: shared X in AA, std_y in AB; both
    # must be real numbers (not text) so Excel plots them and Sheets honours them.
    for row in (2, 3):
        assert isinstance(ws.cell(row, X_COL).value, (int, float)), \
            f"x row {row} is {ws.cell(row, X_COL).value!r} (text → unplottable)"
        assert isinstance(ws.cell(row, STD_Y).value, (int, float)), \
            f"std_y row {row} is {ws.cell(row, STD_Y).value!r}"
    assert ws.cell(2, X_COL).value == 5.0
    assert ws.cell(2, STD_Y).value == pytest.approx(0.00738)
    # std_y is blank on the standards' rows' fit column, and vice-versa.
    assert ws.cell(2, FIT_Y).value is None
    # The fit curve follows on the next rows (shared X in AA, fit_y in AC).
    fit_row = 2 + 2  # after the two standards
    assert isinstance(ws.cell(fit_row, X_COL).value, (int, float))
    assert isinstance(ws.cell(fit_row, FIT_Y).value, (int, float))
    assert ws.cell(fit_row, STD_Y).value is None


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
    # Google Sheets drops a marker-less line series on a scatter, so the fit
    # curve must carry markers to render there (the standards already do).
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.00738'}, {'x': '50', 'y': '0.01884'}],
        fit=[{'x': 1.5, 'y': 0.002}, {'x': 2.5, 'y': 0.004}],
    )
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert rv.status_code == 200
    xml = _chart_xml(rv.data)

    assert '<scatterChart>' in xml
    assert xml.count('<ser>') == 2          # standards + fit
    # Both series must reference the SAME X column — Google Sheets' scatter model
    # allows only one X column per chart and drops series with a different X.
    xrefs = re.findall(r'<xVal><numRef><f>([^<]+)</f>', xml)
    assert len(xrefs) == 2 and xrefs[0] == xrefs[1], f"series do not share an X column: {xrefs}"
    # ...while the Y columns differ (standards vs fit).
    yrefs = re.findall(r'<yVal><numRef><f>([^<]+)</f>', xml)
    assert len(yrefs) == 2 and yrefs[0] != yrefs[1]
    # Every series carries a real marker; none uses a marker-less symbol "none"
    # (the line-only series that Google Sheets won't draw on a scatter).
    assert '<symbol val="none"' not in xml, "a series still has marker symbol 'none'"
    assert xml.count('<symbol val="circle"') == 2
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
