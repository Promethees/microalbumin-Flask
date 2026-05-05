from flask import Blueprint, jsonify, request
from http import HTTPStatus
import os
import json
import csv
import re
from datetime import datetime
from pathlib import Path
from filelock import FileLock, Timeout
import shutil

import state
from file_path import get_directory, is_multi_value_timeseries_csv_header
from file import get_dynamic_data, replace_empty, merge_csv_files
from file_operations import remove_csv_columns
from measure import sort_csv_file
from get_next_filename import get_next_filename
from export_cal_json import processJSONCoef, extractAnalysisCoefficients, CustomEncoder
from export_data import is_metadata_consistent, write_metadata, write_headers, extract_single_entry
from validators import validate_json

file_bp = Blueprint('file', __name__)

@file_bp.route('/get_calibration_json_list', methods=['GET'])
def get_calibration_json_list():
    """
    Lists calibrated JSON coefficient files stored under /json/<mode>.
    mode: "kinetics" or "point"
    """
    mode = request.args.get('mode', '').strip().lower()
    if mode not in ('kinetics', 'point'):
        return jsonify({'status': 'error', 'message': 'Invalid mode. Expected kinetics or point.'}), 400

    try:
        json_dir = os.path.join(state.json_root_path, mode)
        if not os.path.exists(json_dir):
            return jsonify({'status': 'success', 'items': []})

        items = [
            f for f in os.listdir(json_dir)
            if f.lower().endswith('.json') and not f.lower().endswith('.meta.json')
        ]
        items.sort()
        return jsonify({'status': 'success', 'items': items})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@file_bp.route('/get_json_content', methods=['GET'])
def get_json_content():
    selected_json = request.args.get('json_name')
    mode = request.args.get('mode')
    json_path = os.path.join(os.path.join(state.json_root_path, mode), selected_json)
    print("print the json path ", json_path)
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            data = json.load(f)
        print("print the json data", data)
        return jsonify({'status': 'success', 'json': data, 'path': json_path})
    return jsonify({'status': 'error', 'message': 'Error in reading the json file'})

@file_bp.route('/get_headers', methods=['GET'])
def get_csv_headers():
    read_file = request.args.get('file')
    
    if not read_file:
        return jsonify({'headers': [], 'error': 'No file path provided'}), 400
    if not os.path.exists(read_file):
        return jsonify({'headers': [], 'error': 'File not found'}), 404
    if not os.path.isfile(read_file):
        return jsonify({'headers': [], 'error': 'Path is not a file'}), 400

    try:
        with open(read_file, 'r', encoding='utf-8') as f:
            for line in f:
                stripped_line = line.strip()
                if not stripped_line or stripped_line.startswith('#'):
                    continue
                
                # Use csv.reader on a single line to get the headers
                reader = csv.reader([line])
                headers = [h.strip() for h in next(reader)]
                return jsonify({'headers': headers})
            
            return jsonify({'headers': [], 'error': 'CSV file is empty'}), 200
    except StopIteration:
        return jsonify({'headers': [], 'error': 'CSV file is empty'}), 200
    except (csv.Error, UnicodeDecodeError) as e:
        return jsonify({'headers': [], 'error': f'Invalid CSV format: {str(e)}'}), 200
    except PermissionError:
        return jsonify({'headers': [], 'error': 'Permission denied: Cannot read the file'}), 403
    except OSError as e:
        return jsonify({'headers': [], 'error': f'File system error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'headers': [], 'error': 'An unexpected error occurred while reading the file'}), 500

@file_bp.route("/api/current_output", methods=["GET"])
def api_current_output():
    try:
        marker_path = os.path.join(state.script_dir, "log", "current_output.txt")
        if not os.path.isfile(marker_path):
            return jsonify({"exists": False, "message": "marker not found"}), 404
        with open(marker_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return jsonify({"exists": False, "message": "marker empty"}), 204
        full_path = os.path.normpath(content)
        dirpath, filename = os.path.split(full_path)
        dir_with_sep = dirpath + (os.sep if dirpath else "")
        return jsonify({
            "exists": True,
            "full_path": full_path,
            "dir": dirpath,
            "dir_with_sep": dir_with_sep,
            "filename": filename
        }), 200
    except Exception as e:
        return jsonify({"exists": False, "message": str(e)}), 500

@file_bp.route('/edit_file', methods=['POST'])
def edit_file():
    try:
        if state.process and state.process.poll() is None:
            return jsonify({'status': 'error', 'message': 'Cannot edit files while the data collection process is running'}), HTTPStatus.LOCKED

        file_name = request.form.get('filename')
        new_file_name = request.form.get('new_filename', file_name)
        path = request.form.get('path') if request.form.get('path') else get_directory()
        content = request.form.get('content')
        calibrate_mode = request.form.get('calibrate_mode')

        if not file_name or not content:
            return jsonify({'status': 'error', 'message': 'Filename and content are required'}), HTTPStatus.BAD_REQUEST

        if not (new_file_name.endswith('.csv') or new_file_name.endswith('.json')):
            return jsonify({'status': 'error', 'message': 'New file name must end with .csv or .json'}), HTTPStatus.BAD_REQUEST

        file_path = os.path.join(path, file_name)
        new_file_path = os.path.join(path, new_file_name)
        print(f"Editing file: {file_path} to {new_file_path} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S %z')}")

        if '..' in os.path.normpath(file_path) or '..' in os.path.normpath(new_file_path):
            return jsonify({'status': 'error', 'message': 'Invalid file path'}), HTTPStatus.BAD_REQUEST

        if not os.path.exists(file_path):
            return jsonify({'status': 'error', 'message': f'File {file_name} not found'}), HTTPStatus.NOT_FOUND

        if file_name != new_file_name and os.path.exists(new_file_path):
            return jsonify({'status': 'error', 'message': f'File {new_file_name} already exists'}), HTTPStatus.CONFLICT

        if new_file_name.endswith('.json'):
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                return jsonify({'status': 'error', 'message': f'Invalid JSON format: {str(e)}'}), HTTPStatus.BAD_REQUEST
        else:
            pattern_sets = [
                {
                    'header': r"^Concentration,maxRate,Slope,Sat,TimeToSat$",
                    'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+\.\d+),(NONE|\d+|\d+\.\d*)$",
                    'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
                    'error': 'Invalid format (Kinetics calibration).'
                },
                {
                    'header': r"^Concentration,Value,TimePoint$",
                    'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d*)$",
                    'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
                    'error': 'Invalid format (Point calibration).'
                },
                {
                    'header_test': is_multi_value_timeseries_csv_header,
                    'data': r'^\s*\d+(?:\.\d{1,2})?\s*(?:(?:,\s*)?(?:-?\d+(?:\.\d{1,3})?|OVFL|NONE)?\s*)*$',
                    'meta': ["Measurement", "Unit", "Concentration"],
                    'error': 'Invalid format (Pattern 4).'
                }
            ]

            lines = content.strip().split('\n')
            if not lines:
                return jsonify({'status': 'error', 'message': 'Content cannot be empty'}), HTTPStatus.BAD_REQUEST

            metadata_lines = [line.strip() for line in lines if line.strip().startswith('#')]
            data_lines = [line.strip() for line in lines if not line.strip().startswith('#')]

            if not data_lines:
                return jsonify({'status': 'error', 'message': 'CSV must contain at least a header row after metadata'}), HTTPStatus.BAD_REQUEST

            header_line = data_lines[0].replace(" ", "")
            matched_pattern = None
            for pattern in pattern_sets:
                if 'header_test' in pattern:
                    if pattern['header_test'](header_line):
                        matched_pattern = pattern
                        break
                if 'header' in pattern and re.match(pattern['header'], header_line):
                    matched_pattern = pattern
                    break

            if not matched_pattern:
                return jsonify({'status': 'error', 'message': 'Invalid CSV header.'}), 400

            required_meta = matched_pattern.get("meta", [])
            if required_meta:
                meta_dict = {}
                for line in metadata_lines:
                    if ":" in line:
                        key, value = line.lstrip("#").split(":", 1)
                        meta_dict[key.strip()] = value.strip()
                missing_meta = [m for m in required_meta if m not in meta_dict]
                if missing_meta:
                    return jsonify({'status': 'error', 'message': f'Missing metadata fields: {", ".join(missing_meta)}'}), HTTPStatus.BAD_REQUEST

            for i, line in enumerate(data_lines[1:], 2):
                if not re.match(matched_pattern['data'], line):
                    return jsonify({'status': 'error', 'message': f'Invalid data in row {i}'}), HTTPStatus.BAD_REQUEST

        try:
            lock_path = new_file_path + '.lock'
            lock = FileLock(lock_path, timeout=0)

            try:
                lock.acquire()
                try:
                    if new_file_name.endswith('.json'):
                        parsed_json = json.loads(content)
                        cleaned_json = replace_empty(parsed_json)
                        with open(new_file_path, 'w', encoding='utf-8') as f:
                            json.dump(cleaned_json, f, indent=2, ensure_ascii=False)
                    else:
                        with open(new_file_path, 'w') as f:
                            f.write(content)
                        if calibrate_mode:
                            sort_csv_file(new_file_path, calibrate_mode)
                finally:
                    if os.path.exists(lock_path):
                        try:
                            os.unlink(lock_path)
                        except:
                            pass
            except Timeout:
                    return jsonify({'status': 'error', 'message': 'Another save is in progress or previous save crashed'}), 423
            finally:
                lock.release()
                
            if file_name != new_file_name:
                os.remove(file_path)
            return jsonify({'status': 'success', 'message': f'File {file_name} updated successfully' + (f' and renamed to {new_file_name}' if file_name != new_file_name else '')}), HTTPStatus.OK
        except PermissionError as e:
            return jsonify({'status': 'error', 'message': f'Permission denied while writing {new_file_name}: {str(e)}'}), HTTPStatus.FORBIDDEN
        except OSError as e:
            text = 'in use' if e.errno == 16 else 'Failed'
            return jsonify({'status': 'error', 'message': f'Err {text}: {str(e)}'}), HTTPStatus.LOCKED if e.errno == 16 else HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), HTTPStatus.INTERNAL_SERVER_ERROR

@file_bp.route('/delete_file', methods=['POST'])
def delete_file():
    try:
        if state.process and state.process.poll() is None:
            return jsonify({'status': 'error', 'message': 'Cannot delete files while the data collection process is running'}), HTTPStatus.LOCKED

        file_name = request.form.get('filename')
        tabletype = request.form.get('tabletype')
        mode = request.form.get('mode')
        path = request.form.get('path') if request.form.get('path') else get_directory()

        if not file_name or not tabletype:
            return jsonify({'status': 'error', 'message': 'Filename and tabletype are required'}), HTTPStatus.BAD_REQUEST

        if tabletype == '#json-table':
            if not mode:
                return jsonify({'status': 'error', 'message': 'Mode is required for JSON table type'}), HTTPStatus.BAD_REQUEST
            json_path = os.path.join(state.json_root_path, mode)
            file_path = os.path.join(json_path, file_name)
        else:
            file_path = os.path.join(path, file_name)

        if '..' in os.path.normpath(file_path):
            return jsonify({'status': 'error', 'message': 'Invalid file path'}), HTTPStatus.BAD_REQUEST

        if not os.path.exists(file_path):
            return jsonify({'status': 'error', 'message': f'File {file_name} not found'}), HTTPStatus.NOT_FOUND

        try:
            os.remove(file_path)
            return jsonify({'status': 'success', 'message': f'File {file_name} deleted successfully'}), HTTPStatus.OK
        except PermissionError as e:
            return jsonify({'status': 'error', 'message': f'Permission denied: {str(e)}'}), HTTPStatus.FORBIDDEN
        except OSError as e:
            return jsonify({'status': 'error', 'message': f'Err: {str(e)}'}), HTTPStatus.LOCKED if e.errno == 16 else HTTPStatus.INTERNAL_SERVER_ERROR

    except Exception as e:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), HTTPStatus.INTERNAL_SERVER_ERROR

@file_bp.route('/copy_file', methods=['POST'])
def copy_file():
    try:
        if state.process and state.process.poll() is None:
            return jsonify({'status': 'error', 'message': 'Cannot copy files while the data collection process is running'}), HTTPStatus.LOCKED

        file_name = request.form.get('filename')
        mode = request.form.get('mode')
        tabletype = request.form.get('tabletype')
        path = request.form.get('path') if request.form.get('path') else get_directory()

        if not file_name or not tabletype:
            return jsonify({'status': 'error', 'message': 'Filename and tabletype are required'}), HTTPStatus.BAD_REQUEST

        if tabletype == '#json-table':
            if not mode:
                return jsonify({'status': 'error', 'message': 'Mode is required for JSON table type'}), HTTPStatus.BAD_REQUEST
            src_dir = os.path.join(state.json_root_path, mode)
        else:
            src_dir = path

        src_path = os.path.join(src_dir, file_name)

        if '..' in os.path.normpath(src_path):
            return jsonify({'status': 'error', 'message': 'Invalid file path'}), HTTPStatus.BAD_REQUEST

        if not os.path.exists(src_path):
            return jsonify({'status': 'error', 'message': 'Source file not found'}), HTTPStatus.NOT_FOUND

        dst_path = get_next_filename(".json", src_dir, Path(file_name).stem) if tabletype == '#json-table' else get_next_filename(".csv", src_dir, Path(file_name).stem)

        try:
            shutil.copy2(src_path, dst_path)
            return jsonify({'status': 'success', 'message': f'File copied to {dst_path}', 'new_filename': dst_path}), HTTPStatus.OK
        except PermissionError as e:
            return jsonify({'status': 'error', 'message': f'Permission denied: {str(e)}'}), HTTPStatus.FORBIDDEN
        except OSError as e:
            return jsonify({'status': 'error', 'message': f'Failed: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR

    except Exception as e:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), HTTPStatus.INTERNAL_SERVER_ERROR

@file_bp.route('/merge_csv', methods=['POST'])
def merge_csv():
    try:
        if state.process and state.process.poll() is None:
            return jsonify({'status': 'error', 'message': 'Cannot merge files while the data collection process is running'}), HTTPStatus.LOCKED

        file1 = request.form.get('file1')
        file2 = request.form.get('file2')
        output_name = request.form.get('output_name')
        path = request.form.get('path') if request.form.get('path') else get_directory()

        if not file1 or not file2 or not output_name:
            return jsonify({'status': 'error', 'message': 'Both files and output name are required'}), HTTPStatus.BAD_REQUEST

        if not output_name.endswith('.csv'):
            output_name += '.csv'

        file1_path = os.path.join(path, file1)
        file2_path = os.path.join(path, file2)
        output_path = os.path.join(path, output_name)

        if '..' in os.path.normpath(file1_path) or '..' in os.path.normpath(file2_path) or '..' in os.path.normpath(output_path):
            return jsonify({'status': 'error', 'message': 'Invalid file path'}), HTTPStatus.BAD_REQUEST

        success, result = merge_csv_files(file1_path, file2_path, output_path)
        if success:
            return jsonify({'status': 'success', 'message': f'Files merged successfully into {result}'}), HTTPStatus.OK
        else:
            return jsonify({'status': 'error', 'message': result}), HTTPStatus.INTERNAL_SERVER_ERROR

    except Exception as e:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), HTTPStatus.INTERNAL_SERVER_ERROR

@file_bp.route('/remove_columns', methods=['POST'])
@validate_json({
    'filename': str,
    'path': str,
    'columns': (list, [], False)
})
def remove_columns(validated_data):
    try:
        filename = validated_data['filename']
        path = validated_data['path']
        columns = validated_data['columns']
        
        if not filename or not path:
            return jsonify({'status': 'failure', 'message': 'Filename and path are required'}), 400
            
        file_path = os.path.join(path, filename)
        
        if '..' in os.path.normpath(file_path):
             return jsonify({'status': 'failure', 'message': 'Invalid file path'}), 400
             
        success, message = remove_csv_columns(file_path, columns)
        if success:
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'failure', 'message': message}), 400
            
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

@file_bp.route('/get_num_sources', methods=['GET'])
def get_num_sources():
    directory = request.args.get('path') if request.args.get('path') else get_directory()
    possible_counts = set()

    for filename in os.listdir(directory):
        if not filename.lower().endswith('.csv'):
            continue
        full_path = os.path.join(directory, filename)
        if not os.path.isfile(full_path):
            continue

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if is_multi_value_timeseries_csv_header(line):
                        columns = [c.strip() for c in line.split(',')]
                        value_count = sum(1 for c in columns[1:] if c.startswith('Value:'))
                        if value_count > 0:
                            possible_counts.add(value_count)
                    break
        except Exception:
            continue

    return jsonify({'status': 'success', 'num_sources': sorted(list(possible_counts))})

@file_bp.route('/get_data', methods=['GET'])
def get_data():
    selected_file = request.args.get('file')
    data = get_dynamic_data(selected_file)
    return jsonify(data)

@file_bp.route('/get_file_content', methods=['GET'])
def get_file_content():
    try:
        file_name = request.args.get('file')
        path = request.args.get('path') if request.args.get('path') else get_directory()
        if not file_name:
            return jsonify({'status': 'error', 'message': 'Filename is required'}), HTTPStatus.BAD_REQUEST

        file_path = os.path.join(path, file_name)
        if '..' in os.path.normpath(file_path):
            return jsonify({'status': 'error', 'message': 'Invalid file path'}), HTTPStatus.BAD_REQUEST

        result = get_dynamic_data(file_path)
        if 'error' in result and result['error']:
            return jsonify({'status': 'error', 'message': result['error']}), HTTPStatus.NOT_FOUND

        if state.process and state.process.poll() is None:
            if path.startswith(os.path.abspath(os.path.join(state.script_dir, 'data'))):
                return jsonify({'status': 'error', 'message': f'File {file_name} may be in use by the data collection process'}), HTTPStatus.LOCKED

        if not (file_name.lower().endswith('.csv') or file_name.lower().endswith('.json')):
            return jsonify({'status': 'error', 'message': 'Only CSV and JSON files are supported'}), HTTPStatus.BAD_REQUEST

        try:
            with open(file_path, 'r') as f:
                content = f.read()

            if file_name.lower().endswith('.json'):
                try:
                    json.loads(content)
                except json.JSONDecodeError as e:
                    return jsonify({'status': 'error', 'message': f'Invalid JSON file format: {str(e)}'}), HTTPStatus.BAD_REQUEST

            return jsonify({'status': 'success', 'content': content})
        except PermissionError as e:
            return jsonify({'status': 'error', 'message': f'Permission denied: {str(e)}'}), HTTPStatus.FORBIDDEN
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), HTTPStatus.INTERNAL_SERVER_ERROR

@file_bp.route('/export_data', methods=['POST'])
@validate_json({
    'entries': (list, [], False),
    'save_file': (str, 'result', False),
    'save_dir': str,
    'meas': (str, 'NONE', False),
    'measUnit': (str, 'NONE', False),
    'measMode': str,
    'newFile': (bool, True, False)
})
def export_data(validated_data):
    entries = validated_data['entries']
    is_batch = bool(entries)

    file_name = validated_data['save_file']
    save_dir = validated_data['save_dir']
    measurement = validated_data['meas']
    meas_unit = validated_data['measUnit']
    meas_mode = validated_data['measMode']
    newFile = validated_data['newFile']
    time_unit = "minute" if meas_mode == "point" else "minutes"

    try:
        export_path = os.path.abspath(os.path.expanduser(save_dir))
        os.makedirs(export_path, exist_ok=True)
        full_path = os.path.join(export_path, file_name + "_" + meas_mode + ".csv")
        file_exists = os.path.isfile(full_path)

        if file_exists:
            meta_dict = get_dynamic_data(full_path)['metadata']
            if not is_metadata_consistent(meta_dict, measurement, meas_unit, time_unit, meas_mode):
                return jsonify({"status": "error", "message": "Metadata inconsistency"})

        with open(full_path, "a", newline='') as f:
            writer = csv.writer(f)
            if not file_exists and newFile:
                write_metadata(f, measurement, meas_unit, time_unit, meas_mode)
                write_headers(writer, meas_mode)

            if is_batch:
                entries = [extract_single_entry(entry, meas_mode) for entry in entries]
            else:
                raw_data = request.get_json()
                entries = [extract_single_entry(raw_data, meas_mode)]
            
            for entry in entries:
                writer.writerow(entry)

        sort_csv_file(full_path, meas_mode)
        return jsonify({"status": "success", "message": f"Data exported at {full_path}"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@file_bp.route('/export_cal_coefs', methods=['POST'])
@validate_json({
    'fit_type': str,
    'for_meas': str,
    'coef_content': ((list, dict), None, False),
    'time': (float, None, False),
    'file_name': (str, 'calibrate', False),
    'cal_mode': (str, 'kinetics', False),
    'cal_params': (list, [], False),
    'threshold_val': (float, 0.0, False),
    'regress_algo': (str, 'linear', False)
})
def export_cal_coefs(validated_data):
    fit_type = validated_data['fit_type']
    for_meas = validated_data['for_meas']
    coef_content = validated_data['coef_content']
    time = validated_data['time']
    time_unit = "minute"
    file_name = validated_data['file_name']
    cal_mode = validated_data['cal_mode']
    cal_params = validated_data['cal_params']
    thres_val = validated_data['threshold_val']
    regress_algo = validated_data['regress_algo']
    export_path = os.path.join(state.json_root_path, cal_mode)
    
    try: 
        export_path = os.getenv(export_path, export_path)
        export_path = os.path.abspath(os.path.expanduser(export_path))
        os.makedirs(export_path, exist_ok=True)
        full_path = get_next_filename(".json", export_path, file_name)

        json_content = processJSONCoef(cal_params, extractAnalysisCoefficients(coef_content, thres_val, regress_algo), regress_algo)
        json_content.update({"fit_type": fit_type, "for_meas": for_meas})

        if (cal_mode == "point"):
            json_content.update({"time": time, "time-unit": time_unit})
        with open(full_path, "w") as f:
            json.dump(json_content, f, cls=CustomEncoder, indent=4)
        return jsonify({"status": "success", "message": f"Data exported to {full_path}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@file_bp.route('/save_report', methods=['POST'])
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
        report_path = os.path.join(state.report_root_path, filename)
        # Avoid overriding by getting next available name if file exists
        full_path = get_next_filename(".html", state.report_root_path, Path(filename).stem)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        return jsonify({"status": "success", "message": f"Report saved at {full_path}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@file_bp.route('/export_to_report', methods=['POST'])
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
        # Resolve source path
        if not os.path.isabs(source_path):
             source_path = os.path.abspath(os.path.join(state.script_dir, source_path))
        
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
        import shutil
        shutil.copy2(source_path, dest_path)
            
        # Also save metadata for this specific file if needed
        meta_filename = Path(dest_filename).stem + ".meta.json"
        meta_path = os.path.join(subject_path, meta_filename)
        import json
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)
            
        return jsonify({"status": "success", "message": f"Copied '{base_name}' to report subject '{subject}'"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@file_bp.route('/get_report_items', methods=['GET'])
def get_report_items():
    subject = request.args.get('subject')
    if not subject:
        return jsonify({"status": "error", "message": "No subject provided"}), 400
        
    subject_path = os.path.join(state.report_root_path, subject)
    if not os.path.exists(subject_path):
        return jsonify({"status": "error", "message": "Subject not found"}), 404
        
    # List supported data files (CSV, JSON)
    files = [f for f in os.listdir(subject_path) if f.endswith('.csv') or (f.endswith('.json') and not f.endswith('.meta.json'))]
    items = []
    for f in files:
        meta_f = Path(f).stem + ".meta.json"
        meta_p = os.path.join(subject_path, meta_f)
        meta = {}
        if os.path.exists(meta_p):
            with open(meta_p, 'r', encoding='utf-8') as meta_file:
                import json
                meta = json.load(meta_file)
        
        items.append({
            "filename": f,
            "metadata": meta,
            "path": os.path.join(subject_path, f)
        })
        
    # Sort items by filename or meta timestamp
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


@file_bp.route('/delete_report_subject', methods=['POST'])
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


@file_bp.route('/copy_report_subject', methods=['POST'])
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


@file_bp.route('/rename_report_subject', methods=['POST'])
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


@file_bp.route('/merge_report_subjects', methods=['POST'])
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
                src_file = os.path.join(src_dir, fname)
                if not os.path.isfile(src_file):
                    continue
                base = Path(fname).stem
                ext = Path(fname).suffix
                dst_file = os.path.join(out_path, fname)
                counter = 1
                while os.path.exists(dst_file):
                    dst_file = os.path.join(out_path, f"{base}_{sub}_{counter}{ext}")
                    counter += 1
                shutil.copy2(src_file, dst_file)

        return jsonify({'status': 'success', 'message': f"Merged {len(safe_subjects)} subjects into '{output_subject}'"})
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
