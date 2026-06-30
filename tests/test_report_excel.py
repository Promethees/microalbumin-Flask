"""Tests for the native calibration chart in /export_report_excel.

The chart is a category-axis LineChart with both series markers-only: the
standards as blue diamonds, the fitted curve as red X-marks. The category axis
is labelled ONLY on the standard rows (their concentration) — the fit rows are
blank — so the X-axis shows the concentration-table values and never the fit's
generated Xs. These tests guard:
  * string standards points coerced to real numbers (plottable, locale-aware);
  * the X labels = the standard concentrations only (no fit Xs);
  * two distinct markers (diamond / X-mark), no native trendline.
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

# Helper layout: AA(27)=conc (label — standards only), AB(28)=std_y, AC(29)=fit_y.
CAT, STD_Y, FIT_Y = 27, 28, 29


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _helper_sheet(wb):
    for ws in wb.worksheets:
        if ws.cell(1, CAT).value == 'conc':
            return ws
    return None


def _rows(ws):
    """(conc, std_y, fit_y) helper rows until a fully-empty row ends the data."""
    out, r = [], 2
    while any(ws.cell(r, c).value is not None for c in (CAT, STD_Y, FIT_Y)):
        out.append((ws.cell(r, CAT).value, ws.cell(r, STD_Y).value, ws.cell(r, FIT_Y).value))
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
    assert ws is not None, "category helper header not found"
    rows = _rows(ws)

    # The label column carries ONLY the standard concentrations (string→float).
    labels = sorted(c for (c, ys, yf) in rows if c is not None)
    assert labels == pytest.approx([5.0, 50.0, 500.0])
    # Standards' Y survive as numbers, paired with their concentration label.
    std = sorted(ys for (c, ys, yf) in rows if ys is not None)
    assert std == pytest.approx([0.00738, 0.01884, 0.085])
    # Each row is either a standard (conc + std_y) or a fit point (fit_y) — not both.
    for c, ys, yf in rows:
        if yf is not None:
            assert c is None and ys is None, "fit row carries a label/std_y"
        else:
            assert c is not None and ys is not None, "standard row missing label/std_y"


def test_fit_rows_per_interval_are_value_proportional(client):
    # Concentrations 0, 100, 300 → intervals span 100 and 200 (ratio 1:2). On the
    # equal-slot category axis, the fit-row count between consecutive labels must be
    # PROPORTIONAL to the value span, so the labels keep their true value distances
    # (100 sits ~1/3 of the way to 300, not halfway).
    item = _calibrate_item(
        points=[{'x': '0', 'y': '0.0'}, {'x': '100', 'y': '0.02'},
                {'x': '300', 'y': '0.06'}],
        fit=_fit_grid(0, 300, 60),
    )
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert rv.status_code == 200

    ws = _helper_sheet(load_workbook(io.BytesIO(rv.data)))
    rows = _rows(ws)

    # Count fit rows (fit_y set, no label) between consecutive concentration labels.
    runs, run = [], None
    for c, ys, yf in rows:
        if c is not None:               # a concentration label row
            if run is not None:
                runs.append(run)
            run = 0
        elif yf is not None and run is not None:
            run += 1
    # (fit rows only ever sit BETWEEN labels, so there's no trailing run to flush.)
    # Two gaps (0→100, 100→300); the second spans 2× the value, so ~2× the fit rows.
    assert len(runs) == 2
    assert runs[0] > 0 and runs[1] > 0
    assert runs[1] / runs[0] == pytest.approx(2.0, abs=0.4)


def test_non_numeric_points_are_skipped(client):
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.1'}, {'x': 'NONE', 'y': '0.2'}],
        fit=[],
    )
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert rv.status_code == 200

    ws = _helper_sheet(load_workbook(io.BytesIO(rv.data)))
    rows = _rows(ws)
    assert len(rows) == 1                      # only the valid standard
    assert rows[0][0] == pytest.approx(5.0)    # conc label
    assert rows[0][1] == pytest.approx(0.1)    # std_y


# ── Chart structure ──────────────────────────────────────────────────────────

def _chart_xml(xlsx_bytes):
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        names = sorted(n for n in z.namelist() if n.startswith('xl/charts/chart'))
        assert names, "no chart embedded in the workbook"
        return z.read(names[0]).decode('utf-8')


def test_line_chart_labels_standards_only_with_xmark_fit(client):
    item = _calibrate_item(
        points=[{'x': '5', 'y': '0.00738'}, {'x': '50', 'y': '0.01884'},
                {'x': '500', 'y': '0.085'}],
        fit=_fit_grid(0, 500),
    )
    rv = client.post('/export_report_excel', json={'items': [item]})
    assert rv.status_code == 200
    xml = _chart_xml(rv.data)

    # Category-axis line chart (lets us supply the X labels ourselves).
    assert '<lineChart>' in xml and '<scatterChart>' not in xml
    assert xml.count('<catAx>') == 1 and xml.count('<valAx>') == 1
    assert xml.count('<ser>') == 2
    # The category labels are the STANDARD concentrations only — no fit Xs.
    cat = re.findall(r'<cat>.*?</cat>', xml, re.S)[0]
    cat_vals = sorted(float(v) for v in re.findall(r'<pt idx="\d+"><v>([^<]+)</v>', cat))
    assert cat_vals == pytest.approx([5.0, 50.0, 500.0])
    # Two distinct markers — standards diamonds, fit X-marks — neither with a line.
    assert xml.count('<symbol val="diamond"') == 1
    assert xml.count('<symbol val="x"') == 1
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
