import os
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
from get_next_filename import get_next_filename

data_bp = Blueprint('data', __name__)

@data_bp.route('/get_csv', methods=['GET'])
def get_csv():
    user_data = get_user_data()
    file_list = list(user_data['csv'].keys())
    return jsonify({'status': 'success', 'files': file_list})

@data_bp.route('/get_json_cal', methods=['GET'])
def get_json_cal():
    mode = request.args.get('mode')
    user_data = get_user_data()
    if mode not in user_data['json']:
        user_data['json'][mode] = {}
    json_files = list(user_data['json'][mode].keys())
    return jsonify({'status': 'success', 'files': json_files})

@data_bp.route('/get_json_content', methods=['GET'])
def get_json_content():
    selected_json = request.args.get('json_name')
    mode = request.args.get('mode')
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

from user_data import get_user_data, get_file_metadata

@data_bp.route('/get_num_sources', methods=['GET'])
def get_num_sources():
    csv_data = get_user_data()['csv']
    num_sources = set()
    for filename in csv_data.keys():
        meta = get_file_metadata(filename)
        if meta and 'num_sources' in meta:
            num_sources.add(meta['num_sources'])
    return jsonify({'num_sources': sorted(list(num_sources))})

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
            if data_lines:
                df = pd.read_csv(StringIO("\n".join(data_lines)))
                df = df.astype(object).where(pd.notnull(df), None)
                data = df.to_dict('records')
            else:
                data = []
            unit = "NONE"
            for possible_name in ['Unit', 'MeasUnit']:
                if possible_name in metadata:
                    unit = metadata[possible_name]
                    break
            return jsonify({
                'data': data, 'unit': unit, 'error': None, 'metadata': metadata,
                'num_sources': len([col for col in df.columns if col.startswith('Value:')]) if data_lines else 1
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
    entries = data.get('entries')
    is_batch = bool(entries)
    user_data = get_user_data()
    file_name = data.get('save_file', 'result')
    measurement = data.get('meas', 'NONE')
    meas_unit = data.get('measUnit', 'NONE')
    meas_mode = data.get('measMode')
    newFile = data.get('newFile', True)
    time_unit = "minute" if meas_mode == "point" else "minutes"
    full_name = f"{file_name}_{meas_mode}.csv"
    try:
        with get_user_lock(get_user_id()):
            content = user_data['csv'].get(full_name)
            file_exists = content is not None
            if file_exists:
                meta_dict = parse_metadata(content)
                if not is_metadata_consistent(meta_dict, measurement, meas_unit, time_unit, meas_mode):
                    return jsonify({"status": "error", "message": "Metadata inconsistency"})
            output = StringIO()
            writer = csv.writer(output)
            if not file_exists and newFile:
                write_metadata(output, measurement, meas_unit, time_unit, meas_mode)
                write_headers(writer, meas_mode)
            elif file_exists:
                output.write(content.rstrip('\n') + '\n')
            entries_to_write = [extract_single_entry(entry, meas_mode) for entry in entries] if is_batch else [extract_single_entry(data, meas_mode)]
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
    coef_content = data.get('coef_content')
    time = data.get('time')
    time_unit = "minute"
    file_name = data.get('file_name', 'calibrate')
    cal_mode = data.get('cal_mode', "kinetics")
    cal_params = data.get('cal_params')
    thres_val = float(data.get('threshold_val', 0))
    regress_algo = data.get('regress_algo', 'linear')
    try: 
        user_data = get_user_data()
        if cal_mode not in user_data['json']:
            user_data['json'][cal_mode] = {}
        full_name = get_next_filename(".json", list(user_data['json'][cal_mode].keys()), file_name)
        json_content = processJSONCoef(cal_params, extractAnalysisCoefficients(coef_content, thres_val, regress_algo), regress_algo)
        json_content.update({"fit_type": fit_type, "for_meas": for_meas})
        if cal_mode == "point":
            json_content.update({"time": time, "time-unit": time_unit})
        user_data['json'][cal_mode][full_name] = json.dumps(json_content, cls=CustomEncoder, indent=4)
        from user_data import save_user_data
        save_user_data(user_data)
        return jsonify({"status": "success", "message": f"Data exported to {full_name}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
