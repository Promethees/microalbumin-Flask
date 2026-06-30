"""Tests for the native calibration chart in /export_report_excel.

The chart is a category-axis LineChart (markers only) whose X labels are the
measured standard concentrations only. These tests guard:
  * string standards points coerced to real numbers (plottable, locale-aware);
  * the category column carrying ONLY the standard concentrations (the 150 fit
    points stay unlabelled);
  * two distinct markers, no connecting lines, no native trendline.
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

# Helper layout: AA(27)=conc (category label — standards only), AB(28)=std_y,
# AC(29)=fit_y. Rows are the standards + fit points merged and sorted by conc.
CAT, STD_Y, FIT_Y = 27, 28, 29


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _helper_sheet(wb):
    """The worksheet whose row-1 header at column AA is the category 'conc'."""
    for ws in wb.worksheets:
        if ws.cell(1, CAT).value == 'conc':
            return ws
    return None


def _read_helper_rows(ws):
    """Read (conc, std_y, fit_y) rows until a fully-empty row ends the data."""
    rows, r = [], 2
    while any(ws.cell(r, c).value is not None for c in (CAT, STD_Y, FIT_Y)):
        rows.append((ws.cell(r, CAT).value,
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
    assert ws is not None, "category helper header not found"
    rows = _read_helper_rows(ws)

    # Rows are sorted by concentration; a row is either a standard (conc + std_y)
    # or a fit point (fit_y only) — never both.
    for conc, ys, yf in rows:
        if yf is not None:
            assert ys is None and conc is None, "fit row must have no label/std_y"
        else:
            assert ys is not None and conc is not None, "standard row must be labelled"
    # The category column carries ONLY the standard concentrations, as real
    # numbers, so the X axis is labelled just at the standards.
    std = {conc: ys for (conc, ys, yf) in rows if ys is not None}
    assert set(std) == {5.0, 50.0}
    assert std[5.0] == pytest.approx(0.00738)
    assert std[50.0] == pytest.approx(0.01884)
    assert all(isinstance(v, (int, float)) for v in std.values())
    # Both fit points survive as numbers (positioned by row order, not labelled).
    fit_vals = [yf for (conc, ys, yf) in rows if yf is not None]
    assert len(fit_vals) == 2
    assert all(isinstance(v, (int, float)) for v in fit_vals)


def test_non_numeric_points_are_skipped(client):
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.1'}, {'x': 'NONE', 'y': '0.2'}],
        fit=[],
    )
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert rv.status_code == 200

    ws = _helper_sheet(load_workbook(io.BytesIO(rv.data)))
    # Only the valid standard is written; the 'NONE' x is dropped (not text).
    assert ws.cell(2, CAT).value == 5.0
    assert ws.cell(2, STD_Y).value == pytest.approx(0.1)
    assert ws.cell(3, CAT).value is None


def _chart_xml(xlsx_bytes):
    """The first embedded chart's XML (openpyxl can't read charts back)."""
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        names = sorted(n for n in z.namelist() if n.startswith('xl/charts/chart'))
        assert names, "no chart embedded in the workbook"
        return z.read(names[0]).decode('utf-8')


def test_category_line_chart_with_custom_concentration_labels(client):
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.00738'}, {'x': '50', 'y': '0.01884'}],
        fit=[{'x': 1.5, 'y': 0.002}, {'x': 2.5, 'y': 0.004}],
    )
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert rv.status_code == 200
    xml = _chart_xml(rv.data)

    # A category-axis LINE chart (not a scatter) — that's what lets us relabel X.
    assert '<lineChart>' in xml and '<scatterChart>' not in xml
    assert xml.count('<catAx>') == 1 and xml.count('<valAx>') == 1
    assert xml.count('<ser>') == 2          # standards + fit
    # Both series share ONE category axis; values are cached numbers.
    assert xml.count('<cat>') == 2 and xml.count('<val>') == 2
    assert xml.count('<numCache>') == 4     # cat + val × 2 series
    # The category labels are the STANDARD concentrations only — not the fit Xs.
    cat_blocks = re.findall(r'<cat>.*?</cat>', xml, re.S)
    assert cat_blocks, "no category data on the series"
    cat_vals = re.findall(r'<pt idx="\d+"><v>([^<]+)</v>', cat_blocks[0])
    assert sorted(float(v) for v in cat_vals) == [5.0, 50.0]
    # Every slot's label renders (so all standards show, not just the few Sheets
    # would auto-pick from the ~157 mostly-blank category slots), kept horizontal.
    assert '<tickLblSkip val="1"' in xml
    assert 'rot="0"' in xml
    # Two DISTINCT marker shapes, neither with a connecting line (both <a:noFill/>).
    assert '<symbol val="none"' not in xml
    assert xml.count('<symbol val="diamond"') == 1  # standards
    assert xml.count('<symbol val="dot"') == 1      # fit — smallest marker
    assert xml.count('<a:noFill') == 2, "a series carries a connecting line"
    # No native trendline (it would draw the wrong inverted curve here).
    assert 'trendline' not in xml.lower()


def test_no_native_trendline_for_michaelis_menten(client):
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.00738'}, {'x': '50', 'y': '0.01884'}],
        fit=[{'x': 1.5, 'y': 0.002}, {'x': 2.5, 'y': 0.004}],
    )  # _calibrate_item already uses algo 'Michaelis-Menten'
    rv = client.post('/export_report_excel', json={'items': [item]})
    xml = _chart_xml(rv.data)
    assert 'trendline' not in xml.lower()
