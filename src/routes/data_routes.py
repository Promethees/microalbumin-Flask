from flask import Blueprint, request, jsonify
import pandas as pd
from io import StringIO
import json
import csv
from user_data import get_user_data, get_user_id
from export_cal_json import processJSONCoef, extractAnalysisCoefficients, CustomEncoder
from export_data import (
    parse_metadata, is_metadata_consistent, write_metadata, write_headers,
    extract_single_entry, sort_csv_content, get_user_lock
)
from file_path import (DEFAULT_CONCEN_UNIT, build_csv_identity_from_store,
                       build_json_identity_from_store, timeseries_x_column)
from get_next_filename import get_next_filename

data_bp = Blueprint('data', __name__)

@data_bp.route('/get_csv', methods=['GET'])
def get_csv():
    user_data = get_user_data()
    file_list = list(user_data['csv'].keys())
    # Per-file identity (Measurement/Unit/ConcenUnit) for the identity badge and
    # the CSV↔JSON pairing match. Read-time only — no back-fill of stored content.
    files_identity = build_csv_identity_from_store(user_data['csv'])
    return jsonify({'status': 'success', 'files': file_list,
                    'files_identity': files_identity})

@data_bp.route('/get_json_cal', methods=['GET'])
def get_json_cal():
    mode = request.args.get('mode')
    user_data = get_user_data()
    if mode not in user_data['json']:
        user_data['json'][mode] = {}
    json_files = list(user_data['json'][mode].keys())
    files_identity = build_json_identity_from_store(user_data['json'][mode])
    return jsonify({'status': 'success', 'files': json_files,
                    'files_identity': files_identity})

@data_bp.route('/get_json_content', methods=['GET'])
def get_json_content():
    selected_json = request.args.get('json_name', '').strip()
    mode = request.args.get('mode', '').strip().lower()
    if mode not in ('kinetics', 'point'):
        return jsonify({'status': 'error', 'message': 'Invalid mode'}), 400
    if not selected_json:
        return jsonify({'status': 'error', 'message': 'json_name is required'}), 400
    user_data = get_user_data()
    content = user_data['json'].get(mode, {}).get(selected_json, None)
    if content:
        try:
            data = json.loads(content)
            return jsonify({'status': 'success', 'json': data})
        except json.JSONDecodeError:
            return jsonify({'status': 'error', 'message': 'Error in reading the json file'})
    return jsonify({'status': 'error', 'message': 'Error in reading the json file'})

@data_bp.route('/get_headers', methods=['GET'])
def get_csv_headers():
    read_file = request.args.get('file')
    content = get_user_data()['csv'].get(read_file, None)
    if not content:
        return jsonify({'headers': [], 'error': 'File does not exist'}), 404
    try:
        df = pd.read_csv(StringIO(content), nrows=0, comment='#')
        headers = df.columns.tolist()
        return jsonify({'headers': headers})
    except pd.errors.EmptyDataError:
        return jsonify({'headers': [], 'error': 'CSV file is empty'}), 200
    except Exception as e:
        return jsonify({'headers': [], 'error': f'Error reading CSV: {str(e)}'}), 200

from user_data import get_file_metadata

@data_bp.route('/get_num_sources', methods=['GET'])
def get_num_sources():
    csv_data = get_user_data()['csv']
    num_sources = set()
    for filename in csv_data:
        meta = get_file_metadata(filename)
        if meta and 'num_sources' in meta:
            num_sources.add(meta['num_sources'])
    return jsonify({'num_sources': sorted(num_sources)})

@data_bp.route('/get_data', methods=['GET'])
def get_data():
    selected_file = request.args.get('file')
    subject = request.args.get('subject')
    user_data = get_user_data()

    # If a report subject is specified, look up content from report store first
    content = None
    if subject:
        content = user_data.get('report', {}).get(subject, {}).get('items', {}).get(selected_file, {}).get('content')
    if content is None:
        content = user_data['csv'].get(selected_file)

    if not content:
        return jsonify({'data': [], 'error': 'File not found', 'unit': "NONE", 'metadata': {}})
    try:
        if selected_file.lower().endswith('.csv'):
            metadata = {}
            lines = content.splitlines()
            data_lines = []
            for line in lines:
                if line.strip().startswith("#"):
                    if ":" in line:
                        key, value = line[1:].split(":", 1)
                        metadata[key.strip()] = value.strip()
                elif line.strip():
                    data_lines.append(line)
            # Point-mode Turn files carry a "Turn" X column (1,2,3…) instead of
            # "Timestamp". Rather than teach the whole timeseries pipeline (plot,
            # value-at-point, reports — all keyed on "Timestamp") a second X name,
            # rename the key to "Timestamp" on read and flag x_axis="turn" so the
            # client relabels the axis / reference input. The stored file keeps
            # its "Turn" header (a Turn file never has a Timestamp column).
            x_axis = 'time'
            if data_lines:
                df = pd.read_csv(StringIO("\n".join(data_lines)))
                df = df.astype(object).where(pd.notnull(df), None)
                data = df.to_dict('records')
                if timeseries_x_column(data_lines[0]) == 'Turn':
                    x_axis = 'turn'
                    data = [
                        {('Timestamp' if k == 'Turn' else k): v for k, v in row.items()}
                        for row in data
                    ]
            else:
                data = []
            unit = "NONE"
            for possible_name in ['Unit', 'MeasUnit']:
                if possible_name in metadata:
                    unit = metadata[possible_name]
                    break
            return jsonify({
                'data': data, 'unit': unit, 'error': None, 'metadata': metadata,
                'num_sources': len([col for col in df.columns if col.startswith('Value:')]) if data_lines else 1,
                'x_axis': x_axis
            })
        elif selected_file.lower().endswith('.json'):
            json_data = json.loads(content)
            data = json_data if isinstance(json_data, list) else [json_data]
            unit = "NONE"
            if data and isinstance(data[0], dict):
                for possible_name in ['Unit', 'MeasUnit', 'unit', 'measUnit']:
                    if possible_name in data[0]:
                        unit = data[0][possible_name]
                        break
            return jsonify({'data': data, 'unit': unit, 'error': None, 'metadata': {}})
        return jsonify({'data': [], 'error': 'Unsupported file type', 'unit': "NONE", 'metadata': {}})
    except Exception as e:
        return jsonify({'data': [], 'error': f'Error processing file: {str(e)}', 'unit': "NONE", 'metadata': {}})

@data_bp.route('/get_file_content', methods=['GET'])
def get_file_content():
    file_name = request.args.get('file')
    type = request.args.get('type') 
    if not file_name:
        return jsonify({'status': 'error', 'message': 'Filename is required'}), 400
    user_data = get_user_data()
    if type == 'json':
        mode = request.args.get('mode')
        content = user_data[type][mode].get(file_name)
    else:
        content = user_data[type].get(file_name)
    if content is None:
        return jsonify({'status': 'error', 'message': 'File not found'}), 404
    return jsonify({'status': 'success', 'content': content})

@data_bp.route('/export_data', methods=['POST'])
def export_data():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON body"}), 400
    entries = data.get('entries')
    is_batch = bool(entries)
    user_data = get_user_data()
    file_name = data.get('save_file', 'result')
    measurement = data.get('meas', 'NONE')
    meas_unit = data.get('measUnit', 'NONE')
    concen_unit = data.get('concenUnit') or DEFAULT_CONCEN_UNIT
    meas_mode = data.get('measMode')
    if meas_mode not in ('kinetics', 'point'):
        return jsonify({"status": "error", "message": "Invalid measMode"}), 400
    newFile = data.get('newFile', True)
    # 'turn' marks a point-mode Turn calibration (each Turn is a standard) — the
    # written table drops the TimePoint column.
    x_axis = 'turn' if str(data.get('xAxis', 'time')).strip().lower() == 'turn' else 'time'
    time_unit = "minute" if meas_mode == "point" else "minutes"
    full_name = f"{file_name}_{meas_mode}.csv"
    try:
        with get_user_lock(get_user_id()):
            content = user_data['csv'].get(full_name)
            file_exists = content is not None
            if file_exists:
                meta_dict = parse_metadata(content)
                if not is_metadata_consistent(meta_dict, measurement, meas_unit, time_unit, meas_mode, concen_unit):
                    # Surface a concentration-unit clash explicitly — the most
                    # likely (and otherwise opaque) cause of an inconsistency.
                    existing_unit = meta_dict.get('ConcenUnit', DEFAULT_CONCEN_UNIT)
                    if existing_unit != concen_unit:
                        return jsonify({"status": "error", "message": (
                            f"Concentration unit mismatch: this file records {existing_unit}, "
                            f"but the export is in {concen_unit}. Pick a different file or unit.")})
                    return jsonify({"status": "error", "message": "Metadata inconsistency"})
                # Appending to an existing point calibration file must not mix a
                # turn-based table (Concentration,Value) with a time-based one
                # (Concentration,Value,TimePoint) — the column counts differ.
                if meas_mode == "point":
                    existing_header = next(
                        (l.strip() for l in content.splitlines()
                         if l.strip() and not l.strip().startswith('#')), '')
                    if existing_header:
                        existing_is_turn = 'TimePoint' not in existing_header
                        if existing_is_turn != (x_axis == 'turn'):
                            return jsonify({"status": "error", "message": (
                                'Cannot append to "{name}": it is a {existing} point '
                                'calibration table but this export is {incoming}. Use a '
                                'different file name.').format(
                                    name=full_name,
                                    existing="turn-based" if existing_is_turn else "time-based",
                                    incoming="turn-based" if x_axis == 'turn' else "time-based")})
            output = StringIO()
            writer = csv.writer(output)
            if not file_exists and newFile:
                write_metadata(output, measurement, meas_unit, time_unit, meas_mode, concen_unit)
                write_headers(writer, meas_mode, x_axis)
            elif file_exists:
                output.write(content.rstrip('\n') + '\n')
            entries_to_write = [extract_single_entry(entry, meas_mode, x_axis) for entry in entries] if is_batch else [extract_single_entry(data, meas_mode, x_axis)]
            for entry in entries_to_write:
                writer.writerow(entry)
            new_content = sort_csv_content(output.getvalue())
            user_data['csv'][full_name] = new_content
            from user_data import save_user_data
            save_user_data(user_data)
        return jsonify({"status": "success", "message": f"Data exported at {full_name}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@data_bp.route('/export_cal_coefs', methods=['POST'])
def export_cal_coefs():
    data = request.get_json()
    fit_type = data.get('fit_type')
    for_meas = data.get('for_meas')
    meas_unit = data.get('measUnit', 'NONE')
    concen_unit = data.get('concenUnit') or DEFAULT_CONCEN_UNIT
    coef_content = data.get('coef_content')
    time = data.get('time')
    # 'turn' → a turn-based point calibration curve (each standard is a Turn);
    # the JSON omits the time/time-unit reference.
    x_axis = 'turn' if str(data.get('x_axis', 'time')).strip().lower() == 'turn' else 'time'
    time_unit = "minute"
    file_name = data.get('file_name', 'calibrate')
    cal_mode = data.get('cal_mode', "kinetics")
    cal_params = data.get('cal_params')
    try:
        thres_val = float(data.get('threshold_val', 0))
        if not (0 <= thres_val <= 1):
            thres_val = 0.0
    except (TypeError, ValueError):
        thres_val = 0.0
    regress_algo = data.get('regress_algo', 'linear')
    try: 
        user_data = get_user_data()
        if cal_mode not in user_data['json']:
            user_data['json'][cal_mode] = {}
        full_name = get_next_filename(".json", list(user_data['json'][cal_mode].keys()), file_name)
        json_content = processJSONCoef(cal_params, extractAnalysisCoefficients(coef_content, thres_val, regress_algo), regress_algo)
        # Identity recorded with the curve so a measurement CSV can be matched
        # against it: Measurement (for_meas), measurement Unit, ConcenUnit.
        json_content.update({"fit_type": fit_type, "for_meas": for_meas,
                             "meas_unit": meas_unit, "concen_unit": concen_unit})
        # A turn-based point curve has no time reference — each Turn is already a
        # discrete standard, so the concentration is derived from the raw value
        # with no time lookup. Record x_axis so a reader can tell.
        if cal_mode == "point" and x_axis == 'turn':
            json_content.update({"x_axis": "turn"})
        elif cal_mode == "point":
            json_content.update({"time": time, "time-unit": time_unit})
        user_data['json'][cal_mode][full_name] = json.dumps(json_content, cls=CustomEncoder, indent=4)
        from user_data import save_user_data
        save_user_data(user_data)
        return jsonify({"status": "success", "message": f"Data exported to {full_name}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
