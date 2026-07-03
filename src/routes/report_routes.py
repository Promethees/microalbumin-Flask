"""Report blueprint: subject/item CRUD under report/<subject>/ plus the
Excel report export. Split out of file_routes.py (routes and behavior
unchanged — same URL rules, same responses).
"""
from flask import Blueprint, jsonify, request, send_file
import os
import json
import re
import shutil
from pathlib import Path

import state
from file_path import DATA_ROOT, validate_in_data_root
from get_next_filename import get_next_filename
from validators import validate_json

report_bp = Blueprint('report', __name__)


@report_bp.route('/save_report', methods=['POST'])
@validate_json({
    'filename': (str, 'report', False),
    'html_content': str
})
def save_report(validated_data):
    filename = validated_data.get('filename', 'report')
    if not filename.endswith('.html'):
        filename += '.html'
        
    html_content = validated_data['html_content']
    
    try:
        # Avoid overriding by getting next available name if file exists
        full_path = get_next_filename(".html", state.report_root_path, Path(filename).stem)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        return jsonify({"status": "success", "message": f"Report saved at {full_path}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@report_bp.route('/export_to_report', methods=['POST'])
@validate_json({
    'subject': str,
    'file_path': str,  # The current relative or absolute path
    'metadata': (dict, {}, False)
})
def export_to_report(validated_data):
    subject = validated_data['subject']
    source_path = validated_data['file_path']
    metadata = validated_data.get('metadata', {})
    
    try:
        # The export copies a measurement file out of the data/ tree into a
        # report subject, so the source must live inside the data root — not the
        # report root. Relative paths resolve against the data root; absolute
        # paths are confined to it (path-traversal guard).
        if not os.path.isabs(source_path):
            source_path = os.path.join(DATA_ROOT, source_path)
        abs_source = validate_in_data_root(source_path)
        if abs_source is None:
            return jsonify({"status": "error", "message": "Source file is outside the data directory"}), 403
        source_path = abs_source

        if not os.path.exists(source_path):
            return jsonify({"status": "error", "message": f"Source file not found: {source_path}"}), 404
            
        # Create subject folder if it doesn't exist
        subject_path = os.path.join(state.report_root_path, subject)
        os.makedirs(subject_path, exist_ok=True)
        
        # Determine destination filename (prevent overwrite)
        base_name = os.path.basename(source_path)
        stem = Path(base_name).stem
        ext = Path(base_name).suffix
        
        dest_filename = base_name
        counter = 1
        while os.path.exists(os.path.join(subject_path, dest_filename)):
            dest_filename = f"{stem}_{counter}{ext}"
            counter += 1
            
        dest_path = os.path.join(subject_path, dest_filename)
        
        # Copy the file
        shutil.copy2(source_path, dest_path)

        # Also save metadata for this specific file if needed
        meta_filename = Path(dest_filename).stem + ".meta.json"
        meta_path = os.path.join(subject_path, meta_filename)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)
            
        return jsonify({"status": "success", "message": f"Copied '{base_name}' to report subject '{subject}'"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@report_bp.route('/get_report_items', methods=['GET'])
def get_report_items():
    subject = request.args.get('subject')
    if not subject:
        return jsonify({"status": "error", "message": "No subject provided"}), 400
        
    subject_path = os.path.join(state.report_root_path, subject)
    if not os.path.exists(subject_path):
        return jsonify({"status": "error", "message": "Subject not found"}), 404
        
    # List supported data files (CSV, JSON) — exclude order.json and meta files
    files = [
        f for f in os.listdir(subject_path)
        if f.endswith('.csv') or (
            f.endswith('.json')
            and not f.endswith('.meta.json')
            and f != 'order.json'
        )
    ]
    items = []
    for f in files:
        meta_f = Path(f).stem + ".meta.json"
        meta_p = os.path.join(subject_path, meta_f)
        meta = {}
        if os.path.exists(meta_p):
            with open(meta_p, 'r', encoding='utf-8') as meta_file:
                meta = json.load(meta_file)

        items.append({
            "filename": f,
            "metadata": meta,
            "path": os.path.join(subject_path, f)
        })

    # Apply saved order if present, otherwise fall back to timestamp/name sort
    order_path = os.path.join(subject_path, 'order.json')
    if os.path.exists(order_path):
        with open(order_path, 'r', encoding='utf-8') as of:
            saved_order = json.load(of)
        order_map = {name: i for i, name in enumerate(saved_order)}
        items.sort(key=lambda x: order_map.get(x['filename'], len(saved_order)))
    else:
        items.sort(key=lambda x: x.get('metadata', {}).get('timestamp', x['filename']))

    return jsonify({"status": "success", "items": items})


def _safe_subject_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("Subject name is required")
    # Basic hardening against traversal and odd separators
    if any(x in name for x in ("..", "/", "\\", "\x00")):
        raise ValueError("Invalid subject name")
    return name


@report_bp.route('/delete_report_subject', methods=['POST'])
@validate_json({
    'subject': str
})
def delete_report_subject(validated_data):
    try:
        subject = _safe_subject_name(validated_data['subject'])
        subject_path = os.path.join(state.report_root_path, subject)
        if not os.path.isdir(subject_path):
            return jsonify({'status': 'error', 'message': 'Subject not found'}), 404
        shutil.rmtree(subject_path)
        return jsonify({'status': 'success', 'message': f"Deleted subject '{subject}'"})
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@report_bp.route('/copy_report_subject', methods=['POST'])
@validate_json({
    'subject': str
})
def copy_report_subject(validated_data):
    try:
        subject = _safe_subject_name(validated_data['subject'])
        src = os.path.join(state.report_root_path, subject)
        if not os.path.isdir(src):
            return jsonify({'status': 'error', 'message': 'Subject not found'}), 404

        base = f"{subject}_copy"
        dst = os.path.join(state.report_root_path, base)
        counter = 1
        while os.path.exists(dst):
            dst = os.path.join(state.report_root_path, f"{base}_{counter}")
            counter += 1

        shutil.copytree(src, dst)
        return jsonify({'status': 'success', 'message': f"Copied subject '{subject}'", 'new_subject': os.path.basename(dst)})
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@report_bp.route('/rename_report_subject', methods=['POST'])
@validate_json({
    'old_subject': str,
    'new_subject': str
})
def rename_report_subject(validated_data):
    try:
        old_subject = _safe_subject_name(validated_data['old_subject'])
        new_subject = _safe_subject_name(validated_data['new_subject'])
        src = os.path.join(state.report_root_path, old_subject)
        dst = os.path.join(state.report_root_path, new_subject)
        if not os.path.isdir(src):
            return jsonify({'status': 'error', 'message': 'Subject not found'}), 404
        if os.path.exists(dst):
            return jsonify({'status': 'error', 'message': 'New subject name already exists'}), 409
        os.rename(src, dst)
        return jsonify({'status': 'success', 'message': f"Renamed subject '{old_subject}' to '{new_subject}'"})
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@report_bp.route('/merge_report_subjects', methods=['POST'])
@validate_json({
    'subjects': (list, [], False),
    'output_subject': str
})
def merge_report_subjects(validated_data):
    try:
        subjects = validated_data.get('subjects') or []
        if len(subjects) < 2:
            return jsonify({'status': 'error', 'message': 'Please select at least 2 subjects to merge'}), 400

        safe_subjects = [_safe_subject_name(s) for s in subjects]
        output_subject = _safe_subject_name(validated_data['output_subject'])

        out_path = os.path.join(state.report_root_path, output_subject)
        if os.path.exists(out_path):
            return jsonify({'status': 'error', 'message': 'Output subject already exists'}), 409
        os.makedirs(out_path, exist_ok=False)

        for sub in safe_subjects:
            src_dir = os.path.join(state.report_root_path, sub)
            if not os.path.isdir(src_dir):
                return jsonify({'status': 'error', 'message': f"Subject not found: {sub}"}), 404

            for fname in os.listdir(src_dir):
                # Skip order.json and meta files — meta files are handled alongside their CSV
                if fname == 'order.json' or fname.endswith('.meta.json'):
                    continue
                src_file = os.path.join(src_dir, fname)
                if not os.path.isfile(src_file):
                    continue

                # Resolve destination filename with conflict avoidance
                dst_fname = fname
                dst_file = os.path.join(out_path, dst_fname)
                base = Path(fname).stem
                ext = Path(fname).suffix
                counter = 1
                while os.path.exists(dst_file):
                    dst_fname = f"{base}_{sub}_{counter}{ext}"
                    dst_file = os.path.join(out_path, dst_fname)
                    counter += 1
                shutil.copy2(src_file, dst_file)

                # Copy paired meta file using the resolved destination name so the
                # pairing is preserved even when the CSV was renamed
                meta_src = os.path.join(src_dir, Path(fname).stem + '.meta.json')
                if os.path.isfile(meta_src):
                    shutil.copy2(meta_src, os.path.join(out_path, Path(dst_fname).stem + '.meta.json'))

        return jsonify({'status': 'success', 'message': f"Merged {len(safe_subjects)} subjects into '{output_subject}'"})
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@report_bp.route('/save_report_item_order', methods=['POST'])
@validate_json({'subject': str, 'order': list})
def save_report_item_order(validated_data):
    try:
        subject = _safe_subject_name(validated_data['subject'])
        order = validated_data['order']
        for fname in order:
            if any(x in str(fname) for x in ('..', '/', '\\', '\x00')):
                return jsonify({'status': 'error', 'message': f'Invalid filename: {fname}'}), 400
        subject_path = os.path.join(state.report_root_path, subject)
        if not os.path.isdir(subject_path):
            return jsonify({'status': 'error', 'message': 'Subject not found'}), 404
        order_path = os.path.join(subject_path, 'order.json')
        with open(order_path, 'w', encoding='utf-8') as f:
            json.dump(order, f)
        return jsonify({'status': 'success'})
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@report_bp.route('/delete_report_item', methods=['POST'])
@validate_json({'subject': str, 'filename': str})
def delete_report_item(validated_data):
    try:
        subject = _safe_subject_name(validated_data['subject'])
        filename = validated_data['filename']
        if any(x in filename for x in ('..', '/', '\\', '\x00')):
            return jsonify({'status': 'error', 'message': 'Invalid filename'}), 400
        subject_path = os.path.join(state.report_root_path, subject)
        target = os.path.join(subject_path, filename)
        if not os.path.isfile(target):
            return jsonify({'status': 'error', 'message': 'File not found'}), 404
        os.remove(target)
        meta_path = os.path.join(subject_path, Path(filename).stem + '.meta.json')
        if os.path.exists(meta_path):
            os.remove(meta_path)
        return jsonify({'status': 'success', 'message': f"Removed '{filename}' from '{subject}'"})
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@report_bp.route('/export_report_excel', methods=['POST'])
@validate_json({
    'title': (str, 'Analysis Report', False),
    'subject': (str, '', False),
    'split_sheets': (bool, True, False),
    'items': (list, [], False),
})
def export_report_excel(validated_data):
    import io
    import base64
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.chart import LineChart, Reference
    from openpyxl.chart.marker import Marker
    from openpyxl.chart.shapes import GraphicalProperties
    from openpyxl.chart.series import Series as XYSeries, SeriesLabel
    from openpyxl.chart.data_source import (
        NumRef, NumData, NumVal, NumDataSource, AxDataSource)
    from openpyxl.chart.text import RichText
    from openpyxl.drawing.text import (
        Paragraph, ParagraphProperties, CharacterProperties, RichTextProperties)
    from openpyxl.drawing.line import LineProperties
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.utils import get_column_letter
    from datetime import datetime as _dt

    title = validated_data.get('title', 'Analysis Report')
    subject = validated_data.get('subject', '')
    split_sheets = validated_data.get('split_sheets', True)
    items = validated_data.get('items', [])

    HEADER_FILL    = PatternFill(fill_type='solid', fgColor='2980b9')
    TABLE_HDR_FILL = PatternFill(fill_type='solid', fgColor='3498db')
    SECTION_FILL   = PatternFill(fill_type='solid', fgColor='ecf0f1')
    THIN           = Side(style='thin', color='b0b0b0')
    CELL_BORDER    = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

    CHART_ROW_RESERVE = 22  # rows reserved per native chart (~12 cm at default row height)
    IMAGE_W           = 640
    IMAGE_H           = 320
    IMAGE_ROW_RESERVE = 18

    def _cell(ws, row, col, value=None, bold=False, size=11, color='000000',
              fill=None, align_h='left', border=None):
        c = ws.cell(row=row, column=col, value=value)
        c.font = Font(bold=bold, size=size, color=color)
        if fill:
            c.fill = fill
        c.alignment = Alignment(horizontal=align_h, vertical='center', wrap_text=True)
        if border:
            c.border = border
        return c

    def _add_native_chart(ws, columns, hdr_row, data_start, data_end):
        num_cols = len(columns)
        if num_cols < 2 or data_end < data_start:
            return data_end + 2
        anchor = data_end + 2
        chart = LineChart()
        chart.title = 'Measurement Data'
        chart.x_axis.title = columns[0]
        chart.y_axis.title = 'Value'
        data_ref = Reference(ws, min_col=2, min_row=hdr_row,
                             max_col=num_cols, max_row=data_end)
        chart.add_data(data_ref, titles_from_data=True)
        cats = Reference(ws, min_col=1, min_row=data_start, max_row=data_end)
        chart.set_categories(cats)
        chart.style = 10
        chart.width = 20
        chart.height = 12
        ws.add_chart(chart, f'A{anchor}')
        return anchor + CHART_ROW_RESERVE

    def _add_native_scatter_chart(ws, s, anchor_row, conc_values=None):
        """Render a calibration fit as a *native* (editable) category LineChart.

        Two markers-only series — the standards (blue diamonds) and the fitted curve
        (red X-marks) — on a category axis labelled ONLY at the standard rows (their
        concentration), so the X-axis shows the concentration-table values and never
        the fit's generated Xs. The fitted curve is resampled so each concentration
        interval carries a number of fit rows PROPORTIONAL to its value span: on a
        category (equal-slot) axis that makes each concentration label land at a
        value-proportional row index, so 5 / 50 / 500 keep their true value distances
        (a small gap stays small, a wide gap stays wide). Title/axis titles stay
        editable. Total fit density is kept modest so the renderer (esp. Google
        Sheets, which thins dense category labels) has a better chance of showing
        every standard's label.

        `conc_values` is the exact Concentration column parsed from the data file
        (the Raw Data table) — the authoritative source for the axis tick labels;
        each standard's X is snapped to it so the ticks are the file's own values.

        The X/Y values are written to helper columns far to the right of the
        report content (so they don't clutter it but stay *visible* — Excel does
        not plot data in hidden cells). A per-sheet cursor (`_chart_helper_col`)
        keeps successive charts from overwriting each other.
        """
        def _num(v):
            """Coerce a chart value to float for a numeric Excel cell, else None.

            The standards points arrive from the client as *strings* (parsed out
            of the CSV), so writing them verbatim makes openpyxl emit text cells:
            Excel then refuses to plot them on the scatter (the green "number
            stored as text" marker) and ignores the user's locale decimal
            separator. Writing a real float fixes both — the point plots, and the
            cell is formatted per the user's regional settings (no forced format).
            """
            if v is None or isinstance(v, bool):
                return None
            if isinstance(v, (int, float)):
                return float(v)
            try:
                t = str(v).strip()
                return float(t) if t else None
            except (TypeError, ValueError):
                return None

        points, fit = [], []
        for p in (s.get('points') or []):
            x, y = _num(p.get('x')), _num(p.get('y'))
            if x is not None and y is not None:
                points.append((x, y))
        for p in (s.get('fit') or []):
            x, y = _num(p.get('x')), _num(p.get('y'))
            if x is not None and y is not None:
                fit.append((x, y))
        if not points and not fit:
            return anchor_row

        # The axis ticks are the EXACT Concentration values parsed from the data
        # file (`conc_values`, the Raw Data table's concentration column). Snap each
        # standard's X to its nearest parsed concentration so the tick label is the
        # file's own value (not a chart-payload approximation); fall back to the X.
        conc_ticks = sorted({round(float(c), 6) for c in (conc_values or [])})

        def _conc_label(x):
            if conc_ticks:
                near = min(conc_ticks, key=lambda c: abs(c - x))
                if abs(near - x) <= max(1e-6, 1e-3 * abs(near or 1.0)):
                    return near
            return x

        # Build the rows for a category LINE chart with both series MARKERS-ONLY.
        # The category axis is labelled ONLY on the standard rows (their snapped
        # concentration); the fit rows stay blank, so the axis shows the
        # concentration-TABLE values and never the fit's generated Xs. (A value-axis
        # scatter can't do this: Sheets drops a series or auto-picks round ticks.)
        #
        # The fitted curve is RESAMPLED so the number of fit rows between two
        # consecutive concentration labels is PROPORTIONAL to that interval's value
        # span. Because the axis is categorical (every row is one equal-width slot),
        # proportional fit-row counts place each label at a value-proportional row
        # index — so 5 / 50 / 500 keep their true value distances instead of being
        # squashed to equal spacing. Concretely each label j is pinned to an integer
        # slot `positions[j] ∝ (c_j - c_0)`, and the gap to the next label is filled
        # with that many fit rows. Values are floats (General format) so Excel/Sheets
        # render decimals per locale; never stringify (a text cell is unplottable).
        labelled = sorted({_conc_label(x) for (x, y) in points})
        std_by_tick = {_conc_label(x): y for (x, y) in points}

        fit_sorted = sorted(fit, key=lambda p: p[0])

        def _interp_fit(x):
            """Linear-interpolate the fitted y at concentration x (clamped to range)."""
            if not fit_sorted:
                return None
            if x <= fit_sorted[0][0]:
                return fit_sorted[0][1]
            if x >= fit_sorted[-1][0]:
                return fit_sorted[-1][1]
            lo, hi = 0, len(fit_sorted) - 1
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if fit_sorted[mid][0] <= x:
                    lo = mid
                else:
                    hi = mid
            x0, y0 = fit_sorted[lo]
            x1, y1 = fit_sorted[hi]
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)

        # Total fit rows spread across the whole axis (≈ category count). Kept
        # modest — denser axes make Google Sheets thin/skip category labels — while
        # still giving enough resolution to space uneven concentrations faithfully.
        PTS_TOTAL = 80

        merged = []  # (cat_label_or_None, std_y_or_None, fit_y_or_None)
        if len(labelled) >= 2 and fit_sorted:
            c0, cN = labelled[0], labelled[-1]
            total_span = cN - c0
            # Pin each label to a value-proportional integer slot (label 0 → slot 0,
            # last label → slot PTS_TOTAL). Degenerate (all-equal) spans fall back to
            # consecutive slots.
            if total_span > 0:
                positions = [round(PTS_TOTAL * (c - c0) / total_span) for c in labelled]
            else:
                positions = list(range(len(labelled)))
            # Keep ≥1 free slot between consecutive labels, so every interval gets at
            # least one fit point. That guarantees the fit_y column never has two
            # adjacent blanks (the label rows) — the fit line then only ever spans a
            # SINGLE blank between fit points, which keeps its segments connected.
            for j in range(1, len(positions)):
                if positions[j] <= positions[j - 1] + 1:
                    positions[j] = positions[j - 1] + 2
            for j, c in enumerate(labelled):
                # The label row carries the fit value TOO, so fit_y has no blanks at
                # the standards. That is the only way to keep the curve connected:
                # Google Sheets ignores display_blanks='span' and breaks a line at any
                # blank cell, so a blank fit_y at each standard would split the curve
                # into one segment per interval. (Unlike the reverted anchoring, this
                # adds NO extra rows and sits at the label's exact slot.)
                merged.append((c, std_by_tick.get(c), _interp_fit(c)))
                if j < len(labelled) - 1:
                    gap = positions[j + 1] - positions[j] - 1  # fit rows in interval
                    c_lo, c_hi = c, labelled[j + 1]
                    for k in range(1, gap + 1):
                        xk = c_lo + (c_hi - c_lo) * k / (gap + 1)
                        merged.append((None, None, _interp_fit(xk)))  # fit-only row
        else:
            # Too few labelled concentrations (or no fit) to define equal intervals:
            # keep the standards + raw fit points merged on a shared sorted axis.
            fallback = sorted(
                [(x, y, None) for (x, y) in points] + [(x, None, y) for (x, y) in fit],
                key=lambda r: r[0],
            )
            merged = [(_conc_label(x) if ys is not None else None, ys, yf)
                      for (x, ys, yf) in fallback]

        hc = getattr(ws, '_chart_helper_col', 27)  # first helper block at col AA
        cat_col, ys_col, yf_col = hc, hc + 1, hc + 2
        _cell(ws, 1, cat_col, 'conc'); _cell(ws, 1, ys_col, 'std_y'); _cell(ws, 1, yf_col, 'fit_y')
        for i, (cat, ys, yf) in enumerate(merged, start=2):
            if cat is not None:
                ws.cell(i, cat_col, value=cat)   # tick = file concentration
                ws.cell(i, ys_col, value=ys)
            if yf is not None:
                ws.cell(i, yf_col, value=yf)   # fit row: no axis label
        last = len(merged) + 1

        chart = LineChart()
        chart.title = s.get('title') or s.get('label') or 'Calibration Curve'
        chart.x_axis.title = s.get('xLabel') or 'Concentration'
        chart.y_axis.title = s.get('yLabel') or 'Value'
        # openpyxl defaults axes to delete=True, which hides the axis titles.
        chart.x_axis.delete = False
        chart.y_axis.delete = False
        chart.x_axis.axPos = 'b'
        chart.y_axis.axPos = 'l'
        # The category axis has many slots but only the standards carry a label.
        # Excel auto-skips labels on a dense axis (showing just a couple, rotated), so
        # force every slot's label to render — the blank fit rows show nothing, so all
        # the standard concentrations come through — and keep them horizontal.
        chart.x_axis.tickLblSkip = 1
        chart.x_axis.tickMarkSkip = 1
        chart.x_axis.txPr = RichText(
            bodyPr=RichTextProperties(rot=0, vert='horz'),
            p=[Paragraph(pPr=ParagraphProperties(defRPr=CharacterProperties()))],
        )
        chart.style = 13
        chart.width = 18
        chart.height = 11
        # The fit line must run CONTINUOUSLY through the standard rows (which carry
        # no fit_y), so blanks are SPANNED — the renderer bridges the gap, joining the
        # fit points on either side of each standard into one unbroken curve. The
        # standards series has no line (noFill), so spanning never joins its markers.
        chart.display_blanks = 'span'

        # Series carry explicit numeric CACHES — openpyxl writes bare refs, and
        # Google Sheets reads a cache-less ref as empty and drops the series.
        sheet_q = ws.title.replace("'", "''")

        def _ref(col_idx):
            c = get_column_letter(col_idx)
            return "'{s}'!${c}${lo}:${c}${hi}".format(s=sheet_q, c=c, lo=2, hi=last)

        def _cache(values):
            # blanks (None) omitted by 0-based idx → empty cells (fit rows carry no
            # label; standard rows carry no fit_y).
            return NumData(pt=[NumVal(idx=i, v=v) for i, v in enumerate(values)
                               if v is not None])

        # The shared category axis is labelled only on the standard rows.
        cat_values = [cat for (cat, ys, yf) in merged]

        def _series(y_col, y_values, title):
            ser = XYSeries()
            ser.val = NumDataSource(numRef=NumRef(f=_ref(y_col), numCache=_cache(y_values)))
            ser.cat = AxDataSource(numRef=NumRef(f=_ref(cat_col), numCache=_cache(cat_values)))
            ser.tx = SeriesLabel(v=title)
            ser.graphicalProperties = GraphicalProperties()
            return ser

        if points:
            sp = _series(ys_col, [ys for (cat, ys, yf) in merged], 'Standards')
            # Blue DIAMONDS for the measured standards, markers only (no line). The
            # standards are sparse and never on adjacent rows, so nothing joins them.
            marker = Marker(symbol='diamond', size=8)
            marker.graphicalProperties = GraphicalProperties(solidFill='3498DB')
            sp.marker = marker
            line = LineProperties(); line.noFill = True
            sp.graphicalProperties.line = line
            chart.series.append(sp)
        if fit:
            algo = s.get('algo')
            sf = _series(yf_col, [yf for (cat, ys, yf) in merged],
                         'Fit ({})'.format(algo) if algo else 'Fit')
            # Red fitted curve: the dense points are now JOINED by a smooth red line
            # (markers kept as small X's so the sampled points stay visible on the
            # curve). With display_blanks='span' the line is continuous across the
            # standard rows. NOT a native trendline: the chart plots
            # metric-vs-concentration while the app fits concentration-vs-metric and
            # inverts it (log<->exp swap; no MM type).
            fmarker = Marker(symbol='x', size=4)
            fmarker.graphicalProperties = GraphicalProperties(solidFill='E74C3C')
            sf.marker = fmarker
            line = LineProperties(solidFill='E74C3C')
            line.w = 19050  # ~1.5pt
            sf.graphicalProperties.line = line
            sf.smooth = True
            chart.series.append(sf)

        ws.add_chart(chart, 'A{}'.format(anchor_row))
        ws._chart_helper_col = hc + 4  # 3 cols + a 1-column gap between blocks
        return anchor_row + CHART_ROW_RESERVE

    def _embed_image(ws, b64_str, anchor_row):
        if b64_str.startswith('data:'):
            b64_str = b64_str.split(',', 1)[1]
        try:
            xl_img = XLImage(io.BytesIO(base64.b64decode(b64_str)))
            xl_img.width  = IMAGE_W
            xl_img.height = IMAGE_H
            ws.add_image(xl_img, f'A{anchor_row}')
        except Exception as e:
            ws.cell(anchor_row, 1, value=f'[Image error: {e}]')
            return anchor_row + 2
        return anchor_row + IMAGE_ROW_RESERVE + 1

    def _write_header(ws, title, subject, timestamp):
        ws.merge_cells('A1:J1')
        c = ws['A1']
        c.value = title
        c.font = Font(bold=True, size=18, color='FFFFFF')
        c.fill = HEADER_FILL
        c.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 36
        ws['A2'] = f'Subject: {subject}'
        ws['A2'].font = Font(bold=True, size=11)
        ws['F2'] = f'Generated: {timestamp}'
        ws.row_dimensions[2].height = 18

    def _write_table(ws, r, section_label, columns, rows):
        _cell(ws, r, 1, section_label, bold=True, size=11, fill=SECTION_FILL, color='2c3e50')
        if len(columns) > 1:
            ws.merge_cells(start_row=r, start_column=1,
                           end_row=r, end_column=min(len(columns), 8))
        r += 1
        for ci, col in enumerate(columns, 1):
            _cell(ws, r, ci, col, bold=True, color='FFFFFF',
                  fill=TABLE_HDR_FILL, align_h='center', border=CELL_BORDER)
            ws.column_dimensions[get_column_letter(ci)].width = max(12, len(str(col)) + 2)
        r += 1
        for row_data in rows:
            for ci, col in enumerate(columns, 1):
                val = row_data.get(col)
                if val is not None:
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        pass
                ws.cell(r, ci, value=val).border = CELL_BORDER
            r += 1
        return r + 1

    def _write_csv_table(ws, r, csv_columns, csv_rows):
        """'Raw Data' section: label, styled header row, one bordered cell per
        value (numeric strings coerced to float). Returns
        (next_row, header_row, first_data_row) for native-chart anchoring."""
        _cell(ws, r, 1, 'Raw Data', bold=True, size=11, fill=SECTION_FILL, color='2c3e50')
        if len(csv_columns) > 1:
            ws.merge_cells(start_row=r, start_column=1,
                           end_row=r, end_column=min(len(csv_columns), 8))
        r += 1
        hdr_row = r
        for ci, col in enumerate(csv_columns, 1):
            _cell(ws, r, ci, col, bold=True, color='FFFFFF',
                  fill=TABLE_HDR_FILL, align_h='center', border=CELL_BORDER)
            ws.column_dimensions[get_column_letter(ci)].width = max(12, len(str(col)) + 2)
        r += 1
        data_start = r
        for row_data in csv_rows:
            for ci, col in enumerate(csv_columns, 1):
                val = row_data.get(col)
                if val is not None:
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        pass
                ws.cell(r, ci, value=val).border = CELL_BORDER
            r += 1
        return r, hdr_row, data_start

    def _write_item_block(ws, item, start_row):
        r = start_row
        filename      = item.get('filename', 'Item')
        mode          = item.get('mode', 'N/A')
        chart_images  = item.get('chart_images', [])
        chart_series  = item.get('chart_series', [])
        csv_columns   = item.get('csv_columns', [])
        csv_rows      = item.get('csv_rows', [])
        analysis_rows = item.get('analysis_rows', [])
        coef_rows     = item.get('coef_rows', [])
        coef_tables   = item.get('coef_tables', [])
        derived_lines = item.get('derived_lines', [])

        _cell(ws, r, 1, filename, bold=True, size=13, color='2c3e50')
        ws.cell(r, 2, value=f'Mode: {mode}')
        ws.row_dimensions[r].height = 20
        r += 1

        if csv_columns and csv_rows:
            if mode == 'calibrate':
                # Write standards data table
                r, _hdr_row, _data_start = _write_csv_table(ws, r, csv_columns, csv_rows)
                r += 1  # blank row before charts

                # Prefer the native (editable) calibration chart — standards +
                # fitted curve with live, renameable axis titles. Falls back to
                # embedded PNGs only for older payloads that still send chart_images.
                if chart_series:
                    # Parse the exact Concentration values straight from the data
                    # table (the file's Raw Data) — the first CSV column is the X /
                    # concentration — so the chart's axis ticks are sourced from the
                    # file itself, not just whatever the chart payload carries.
                    conc_col = csv_columns[0] if csv_columns else 'Concentration'
                    conc_values = []
                    for rd in csv_rows:
                        v = rd.get(conc_col)
                        try:
                            if v not in (None, '', 'NONE'):
                                conc_values.append(float(v))
                        except (ValueError, TypeError):
                            pass
                    for s in chart_series:
                        label = s.get('label', '')
                        if label:
                            _cell(ws, r, 1, label, bold=True, size=11, color='555555')
                            r += 1
                        r = _add_native_scatter_chart(ws, s, r, conc_values)
                else:
                    for ci_info in chart_images:
                        label = ci_info.get('label', '')
                        b64   = ci_info.get('b64', '')
                        if not b64:
                            continue
                        if label:
                            _cell(ws, r, 1, label, bold=True, size=11, color='555555')
                            r += 1
                        r = _embed_image(ws, b64, r)
            else:
                r, hdr_row, data_start = _write_csv_table(ws, r, csv_columns, csv_rows)
                r = _add_native_chart(ws, csv_columns, hdr_row, data_start, r - 1)

        if analysis_rows:
            r = _write_table(ws, r, 'Kinetics Analysis',
                             list(analysis_rows[0].keys()), analysis_rows)

        # Per-algorithm coefficient tables (each with that fit's exact columns,
        # e.g. linear → a, b; Michaelis-Menten → Vmax, Km). Falls back to the
        # legacy flat coef_rows table when coef_tables isn't supplied.
        if coef_tables:
            for t in coef_tables:
                rows = t.get('rows') or []
                if not rows:
                    continue
                cols = t.get('columns') or list(rows[0].keys())
                r = _write_table(ws, r, t.get('title', 'Calibration Fit Coefficients'),
                                 cols, rows)
                # Concentration-formula legend (e.g. "where [S] = …; q = …; a = slope, …").
                note = t.get('note')
                if note:
                    _cell(ws, r, 1, note, size=9, color='666666')
                    if len(cols) > 1:
                        ws.merge_cells(start_row=r, start_column=1,
                                       end_row=r, end_column=min(len(cols), 8))
                    r += 2
        elif coef_rows:
            r = _write_table(ws, r, 'Calibration Fit Coefficients',
                             list(coef_rows[0].keys()), coef_rows)

        if derived_lines:
            _cell(ws, r, 1, 'Derived Concentration', bold=True, size=11,
                  fill=SECTION_FILL, color='2c3e50')
            r += 1
            for line in derived_lines:
                ws.cell(r, 1, value=line)
                r += 1

        return r + 2

    wb = Workbook()
    wb.remove(wb.active)
    timestamp = _dt.now().strftime('%Y-%m-%d %H:%M:%S')

    if split_sheets:
        used_names = {}
        for item in items:
            base = re.sub(r'[\\/*?:\[\]]', '_', Path(item.get('filename', 'Sheet')).stem)[:27]
            idx = used_names.get(base, 0)
            used_names[base] = idx + 1
            sheet_name = (base if idx == 0 else f'{base}_{idx}')[:31]
            ws = wb.create_sheet(title=sheet_name)
            _write_header(ws, title, subject, timestamp)
            _write_item_block(ws, item, start_row=4)
    else:
        ws = wb.create_sheet(title='Report')
        _write_header(ws, title, subject, timestamp)
        cur = 4
        for item in items:
            cur = _write_item_block(ws, item, cur)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_subject = re.sub(r'[^\w\-]', '_', subject) if subject else 'report'
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        attachment_filename=f'{safe_subject}_report.xlsx'
    )


