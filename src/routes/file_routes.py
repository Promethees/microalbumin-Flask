from flask import Blueprint, jsonify, request, send_file
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
from file_path import (DATA_ROOT, validate_in_data_root,
                       is_reserved_data_folder_name, RESERVED_ARCHIVE_FOLDER,
                       parse_csv_metadata, detect_csv_schema,
                       CSV_SCHEMA_TIMESERIES, CSV_SCHEMA_KINETICS_CAL, CSV_SCHEMA_POINT_CAL,
                       DEFAULT_CONCEN_UNIT)
from file import get_dynamic_data, replace_empty, merge_csv_files
from file_operations import remove_csv_columns
from measure import sort_csv_file
from get_next_filename import get_next_filename
from export_cal_json import processJSONCoef, extractAnalysisCoefficients, CustomEncoder
from export_data import is_metadata_consistent, write_metadata, write_headers, extract_single_entry
from validators import validate_json

file_bp = Blueprint('file', __name__)


def _nice_num(x, round_it):
    """Heckbert's 'nice number' — round x to a 1/2/5 × 10^k figure.

    `round_it` rounds to the nearest nice number; otherwise rounds up (used to
    size the overall range so it comfortably covers the data).
    """
    import math
    if x <= 0:
        return 1.0
    exp = math.floor(math.log10(x))
    frac = x / (10 ** exp)
    if round_it:
        nice = 1 if frac < 1.5 else 2 if frac < 3 else 5 if frac < 7 else 10
    else:
        nice = 1 if frac <= 1 else 2 if frac <= 2 else 5 if frac <= 5 else 10
    return nice * (10 ** exp)


def _nice_axis_ticks(lo, hi, target=6):
    """A 'reasonably looking' tick series spanning [lo, hi] (e.g. 0,100,…,500).

    Returns evenly-spaced round values (1/2/5 × 10^k step) — the classic axis
    algorithm — covering the data range with about `target` ticks.
    """
    import math
    if hi <= lo:
        return [lo]
    rng = _nice_num(hi - lo, False)
    step = _nice_num(rng / max(1, target - 1), True)
    start = math.floor(lo / step) * step
    end = math.ceil(hi / step) * step
    ticks, t, n = [], start, 0
    while t <= end + 0.5 * step and n < 1000:
        ticks.append(round(t, 10))
        t += step
        n += 1
    return ticks

_SCHEMA_VALIDATORS = {
    CSV_SCHEMA_KINETICS_CAL: {
        'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+\.\d+),(NONE|\d+|\d+\.\d*)$",
        'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
        'error': 'Invalid format (Kinetics calibration).'
    },
    CSV_SCHEMA_POINT_CAL: {
        'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d*)$",
        'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
        'error': 'Invalid format (Point calibration).'
    },
    CSV_SCHEMA_TIMESERIES: {
        'data': r'^\s*\d+(?:\.\d{1,2})?\s*(?:(?:,\s*)?(?:-?\d+(?:\.\d{1,3})?|OVFL|NONE)?\s*)*$',
        'meta': ["Measurement", "Unit", "Concentration"],
        'error': 'Invalid format (Pattern 4).'
    },
}

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
    selected_json = request.args.get('json_name', '').strip()
    mode = request.args.get('mode', '').strip().lower()
    if mode not in ('kinetics', 'point'):
        return jsonify({'status': 'error', 'message': 'Invalid mode'}), 400
    if not selected_json or any(c in selected_json for c in ('..', '/', '\\')):
        return jsonify({'status': 'error', 'message': 'Invalid filename'}), 400
    json_path = os.path.join(state.json_root_path, mode, selected_json)
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({'status': 'success', 'json': data, 'path': json_path})
    return jsonify({'status': 'error', 'message': 'Error in reading the json file'})

@file_bp.route('/get_headers', methods=['GET'])
def get_csv_headers():
    read_file = request.args.get('file')

    if not read_file:
        return jsonify({'headers': [], 'error': 'No file path provided'}), 400
    if '..' in os.path.normpath(read_file):
        return jsonify({'headers': [], 'error': 'Invalid file path'}), 400
    if not read_file.lower().endswith('.csv'):
        return jsonify({'headers': [], 'error': 'Only CSV files are supported'}), 400
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
        path = request.form.get('path') if request.form.get('path') else DATA_ROOT
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
            lines = content.strip().split('\n')
            if not lines:
                return jsonify({'status': 'error', 'message': 'Content cannot be empty'}), HTTPStatus.BAD_REQUEST

            metadata_lines = [line.strip() for line in lines if line.strip().startswith('#')]
            data_lines = [line.strip() for line in lines if not line.strip().startswith('#')]

            if not data_lines:
                return jsonify({'status': 'error', 'message': 'CSV must contain at least a header row after metadata'}), HTTPStatus.BAD_REQUEST

            schema = detect_csv_schema(data_lines[0])
            matched_pattern = _SCHEMA_VALIDATORS.get(schema)
            if not matched_pattern:
                return jsonify({'status': 'error', 'message': 'Invalid CSV header.'}), 400

            required_meta = matched_pattern.get("meta", [])
            if required_meta:
                meta_dict = parse_csv_metadata(metadata_lines)
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
                        with open(new_file_path, 'w', encoding='utf-8') as f:
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
        path = request.form.get('path') if request.form.get('path') else DATA_ROOT

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

@file_bp.route('/delete_data_folder', methods=['POST'])
@validate_json({'path': str})
def delete_data_folder(validated_data):
    """Delete a data subfolder (and everything inside it).

    The path must resolve inside DATA_ROOT and may not be DATA_ROOT itself.
    """
    try:
        if state.process and state.process.poll() is None:
            return jsonify({'status': 'error', 'message': 'Cannot delete folders while the data collection process is running'}), HTTPStatus.LOCKED

        abs_path = validate_in_data_root(validated_data['path'])
        if not abs_path:
            return jsonify({'status': 'error', 'message': 'Invalid folder path'}), HTTPStatus.BAD_REQUEST
        if abs_path == DATA_ROOT:
            return jsonify({'status': 'error', 'message': 'Cannot delete the data root folder'}), HTTPStatus.BAD_REQUEST
        if not os.path.isdir(abs_path):
            return jsonify({'status': 'error', 'message': 'Folder not found'}), HTTPStatus.NOT_FOUND

        shutil.rmtree(abs_path)
        return jsonify({'status': 'success', 'message': f"Deleted folder '{os.path.basename(abs_path)}'"}), HTTPStatus.OK
    except PermissionError as e:
        return jsonify({'status': 'error', 'message': f'Permission denied: {str(e)}'}), HTTPStatus.FORBIDDEN
    except OSError as e:
        return jsonify({'status': 'error', 'message': f'Err: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), HTTPStatus.INTERNAL_SERVER_ERROR

@file_bp.route('/rename_data_folder', methods=['POST'])
@validate_json({'path': str, 'new_name': str})
def rename_data_folder(validated_data):
    """Rename a data subfolder.

    The source path must resolve inside DATA_ROOT and may not be DATA_ROOT
    itself. The new name must be a bare folder name (no separators, traversal,
    or hidden-folder prefix) so the renamed folder stays visible in the picker.
    Returns the new absolute path so the frontend can re-point the active
    directory if the renamed folder was selected.
    """
    try:
        if state.process and state.process.poll() is None:
            return jsonify({'status': 'error', 'message': 'Cannot rename folders while the data collection process is running'}), HTTPStatus.LOCKED

        abs_path = validate_in_data_root(validated_data['path'])
        if not abs_path:
            return jsonify({'status': 'error', 'message': 'Invalid folder path'}), HTTPStatus.BAD_REQUEST
        if abs_path == DATA_ROOT:
            return jsonify({'status': 'error', 'message': 'Cannot rename the data root folder'}), HTTPStatus.BAD_REQUEST
        if not os.path.isdir(abs_path):
            return jsonify({'status': 'error', 'message': 'Folder not found'}), HTTPStatus.NOT_FOUND

        new_name = (validated_data['new_name'] or '').strip()
        if not new_name:
            return jsonify({'status': 'error', 'message': 'New folder name is required'}), HTTPStatus.BAD_REQUEST
        if any(x in new_name for x in ('..', '/', '\\', '\x00')) or new_name.startswith('.') or new_name.startswith('_'):
            return jsonify({'status': 'error', 'message': 'Invalid folder name'}), HTTPStatus.BAD_REQUEST
        if is_reserved_data_folder_name(new_name):
            return jsonify({'status': 'error', 'message': f"'{RESERVED_ARCHIVE_FOLDER}' is a reserved folder name and cannot be used"}), HTTPStatus.BAD_REQUEST

        if os.path.basename(abs_path) == new_name:
            return jsonify({'status': 'success', 'message': 'Folder name unchanged', 'path': abs_path}), HTTPStatus.OK

        new_path = os.path.join(DATA_ROOT, new_name)
        if os.path.exists(new_path):
            return jsonify({'status': 'error', 'message': 'A folder with that name already exists'}), HTTPStatus.CONFLICT

        os.rename(abs_path, new_path)
        return jsonify({'status': 'success', 'message': f"Renamed folder to '{new_name}'", 'path': new_path}), HTTPStatus.OK
    except PermissionError as e:
        return jsonify({'status': 'error', 'message': f'Permission denied: {str(e)}'}), HTTPStatus.FORBIDDEN
    except OSError as e:
        return jsonify({'status': 'error', 'message': f'Err: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR
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
        path = request.form.get('path') if request.form.get('path') else DATA_ROOT

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

@file_bp.route('/move_file', methods=['POST'])
def move_file():
    """Move a CSV data file from one data subfolder to another.

    Both the source (``path``) and destination (``dest_path``) directories must
    validate inside DATA_ROOT. The destination filename is auto-incremented when
    a file of the same name already exists there, so a move never clobbers data.
    """
    try:
        if state.process and state.process.poll() is None:
            return jsonify({'status': 'error', 'message': 'Cannot move files while the data collection process is running'}), HTTPStatus.LOCKED

        file_name = request.form.get('filename')
        src_dir = request.form.get('path') or DATA_ROOT
        dest_dir = request.form.get('dest_path') or DATA_ROOT

        if not file_name:
            return jsonify({'status': 'error', 'message': 'Filename is required'}), HTTPStatus.BAD_REQUEST
        # Filename must be a bare name with no path traversal/separators.
        if any(c in file_name for c in ('/', '\\', '..')):
            return jsonify({'status': 'error', 'message': 'Invalid filename'}), HTTPStatus.BAD_REQUEST

        src_dir_v = validate_in_data_root(src_dir)
        dest_dir_v = validate_in_data_root(dest_dir)
        if not src_dir_v or not dest_dir_v:
            return jsonify({'status': 'error', 'message': 'Invalid folder path'}), HTTPStatus.BAD_REQUEST
        if not os.path.isdir(dest_dir_v):
            return jsonify({'status': 'error', 'message': 'Destination folder not found'}), HTTPStatus.NOT_FOUND

        if os.path.normpath(src_dir_v) == os.path.normpath(dest_dir_v):
            return jsonify({'status': 'error', 'message': 'Source and destination folders are the same'}), HTTPStatus.BAD_REQUEST

        src_path = os.path.join(src_dir_v, file_name)
        if not os.path.isfile(src_path):
            return jsonify({'status': 'error', 'message': 'Source file not found'}), HTTPStatus.NOT_FOUND

        # Auto-rename in the destination so a same-named file is never overwritten.
        dst_path = os.path.join(dest_dir_v, file_name)
        if os.path.exists(dst_path):
            dst_path = get_next_filename(Path(file_name).suffix or ".csv", dest_dir_v, Path(file_name).stem)

        try:
            shutil.move(src_path, dst_path)
            return jsonify({
                'status': 'success',
                'message': f"Moved '{file_name}' to {dest_dir_v}",
                'new_path': dst_path,
                'new_filename': os.path.basename(dst_path)
            }), HTTPStatus.OK
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

        folder_paths = request.form.getlist('folder_paths')
        file_names = request.form.getlist('file_names')
        output_name = request.form.get('output_name')
        output_dir = request.form.get('output_path') or DATA_ROOT

        if len(folder_paths) < 2 or len(folder_paths) != len(file_names) or not output_name:
            return jsonify({'status': 'error', 'message': 'At least two files and an output name are required'}), HTTPStatus.BAD_REQUEST

        if not output_name.endswith('.csv'):
            output_name += '.csv'

        file_paths = []
        for folder, fname in zip(folder_paths, file_names):
            if not fname:
                return jsonify({'status': 'error', 'message': 'Each slot must have a file selected'}), HTTPStatus.BAD_REQUEST
            validated = validate_in_data_root(os.path.join(folder, fname))
            if not validated:
                return jsonify({'status': 'error', 'message': 'Invalid file path'}), HTTPStatus.BAD_REQUEST
            file_paths.append(validated)

        validated_out_dir = validate_in_data_root(output_dir)
        if not validated_out_dir:
            return jsonify({'status': 'error', 'message': 'Invalid output path'}), HTTPStatus.BAD_REQUEST

        output_full = os.path.join(validated_out_dir, output_name)

        success, result = merge_csv_files(file_paths, output_full)
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
    directory = request.args.get('path') if request.args.get('path') else DATA_ROOT
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
                    if detect_csv_schema(line) == CSV_SCHEMA_TIMESERIES:
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
    if not selected_file:
        return jsonify({'data': [], 'error': 'No file path provided', 'unit': 'NONE'}), 400
    if '..' in os.path.normpath(selected_file):
        return jsonify({'data': [], 'error': 'Invalid file path', 'unit': 'NONE'}), 400
    if not selected_file.lower().endswith('.csv'):
        return jsonify({'data': [], 'error': 'Only CSV files are supported', 'unit': 'NONE'}), 400
    data = get_dynamic_data(selected_file)
    return jsonify(data)

@file_bp.route('/get_file_content', methods=['GET'])
def get_file_content():
    try:
        file_name = request.args.get('file')
        path = request.args.get('path') if request.args.get('path') else DATA_ROOT
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
            with open(file_path, 'r', encoding='utf-8') as f:
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

@file_bp.route('/save_range_csv', methods=['POST'])
@validate_json({
    'file': str,
    'range_start': (float, 0.0, False),
    'range_end': (float, None, False),
    'save_name': str,
    'save_dir': str
})
def save_range_csv(validated_data):
    source_file = validated_data['file']
    range_start = validated_data['range_start']
    range_end = validated_data['range_end']
    save_name = os.path.basename(validated_data['save_name'].strip())
    save_dir = validated_data['save_dir']

    if '..' in os.path.normpath(source_file) or '..' in os.path.normpath(save_dir):
        return jsonify({'status': 'error', 'message': 'Invalid path'})
    if not source_file.lower().endswith('.csv'):
        return jsonify({'status': 'error', 'message': 'Source must be a CSV file'})
    if not os.path.isfile(source_file):
        return jsonify({'status': 'error', 'message': 'Source file not found'})
    if not save_name:
        return jsonify({'status': 'error', 'message': 'Save name is required'})

    try:
        meta_lines = []
        data_lines = []

        with open(source_file, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith('#'):
                    meta_lines.append(line.rstrip('\n'))
                elif stripped:
                    data_lines.append(stripped)

        if not data_lines:
            return jsonify({'status': 'error', 'message': 'Source file has no data'})

        header_list = [h.strip() for h in next(csv.reader([data_lines[0]]))]
        if 'Timestamp' not in header_list:
            return jsonify({'status': 'error', 'message': 'Source file has no Timestamp column'})

        filtered_rows = []
        for line in data_lines[1:]:
            parsed = next(csv.reader([line]))
            row_dict = dict(zip(header_list, parsed))
            try:
                ts = float(row_dict['Timestamp'])
                if ts >= range_start and (range_end is None or ts <= range_end):
                    filtered_rows.append(parsed)
            except (ValueError, KeyError):
                pass

        save_dir_abs = os.path.abspath(os.path.expanduser(save_dir))
        os.makedirs(save_dir_abs, exist_ok=True)

        if not save_name.lower().endswith('.csv'):
            save_name += '.csv'
        out_path = os.path.join(save_dir_abs, save_name)

        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            for line in meta_lines:
                f.write(line + '\n')
            writer = csv.writer(f)
            writer.writerow(header_list)
            writer.writerows(filtered_rows)

        return jsonify({
            'status': 'success',
            'message': f'Saved {len(filtered_rows)} rows to {out_path}',
            'count': len(filtered_rows),
            'path': out_path
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@file_bp.route('/export_data', methods=['POST'])
@validate_json({
    'entries': (list, [], False),
    'save_file': (str, 'result', False),
    'save_dir': str,
    'meas': (str, 'NONE', False),
    'measUnit': (str, 'NONE', False),
    'concenUnit': (str, DEFAULT_CONCEN_UNIT, False),
    'measMode': str,
    'newFile': (bool, True, False),
    # Single-entry (one source) export sends the row's values at the top level
    # rather than in `entries`. Declare them so @validate_json keeps them in
    # validated_data — otherwise extract_single_entry() reads nothing and the row
    # is written as all NONE. Permissive type: each is a numeric value or "NONE".
    'maxrate': ((str, int, float), 'NONE', False),
    'slope': ((str, int, float), 'NONE', False),
    'sat': ((str, int, float), 'NONE', False),
    'timeSat': ((str, int, float), 'NONE', False),
    'con': ((str, int, float), 'NONE', False),
    'estValue': ((str, int, float), 'NONE', False),
    'timePoint': ((str, int, float), 'NONE', False),
})
def export_data(validated_data):
    entries = validated_data['entries']
    is_batch = bool(entries)

    file_name = validated_data['save_file']
    save_dir = validated_data['save_dir']
    measurement = validated_data['meas']
    meas_unit = validated_data['measUnit']
    concen_unit = validated_data['concenUnit'] or DEFAULT_CONCEN_UNIT
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
            if not is_metadata_consistent(meta_dict, measurement, meas_unit, time_unit, meas_mode, concen_unit):
                # Surface a concentration-unit clash explicitly — the most
                # likely (and otherwise opaque) cause of an inconsistency.
                existing_unit = meta_dict.get('ConcenUnit', DEFAULT_CONCEN_UNIT)
                if existing_unit != concen_unit:
                    return jsonify({"status": "error", "message": (
                        f"Concentration unit mismatch: this file records {existing_unit}, "
                        f"but the export is in {concen_unit}. Pick a different file or unit.")})
                return jsonify({"status": "error", "message": "Metadata inconsistency"})

        with open(full_path, "a", newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists and newFile:
                write_metadata(f, measurement, meas_unit, time_unit, meas_mode, concen_unit)
                write_headers(writer, meas_mode)

            if is_batch:
                entries = [extract_single_entry(entry, meas_mode) for entry in entries]
            else:
                entries = [extract_single_entry(validated_data, meas_mode)]
            
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
    'measUnit': (str, 'NONE', False),
    'concenUnit': (str, DEFAULT_CONCEN_UNIT, False),
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
    meas_unit = validated_data['measUnit']
    concen_unit = validated_data['concenUnit'] or DEFAULT_CONCEN_UNIT
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
        export_path = os.path.abspath(os.path.expanduser(export_path))
        os.makedirs(export_path, exist_ok=True)
        full_path = get_next_filename(".json", export_path, file_name)

        json_content = processJSONCoef(cal_params, extractAnalysisCoefficients(coef_content, thres_val, regress_algo), regress_algo)
        # Identity recorded with the calibration curve so a measurement CSV can be
        # matched against it: Measurement (for_meas), measurement Unit, ConcenUnit.
        json_content.update({"fit_type": fit_type, "for_meas": for_meas,
                             "meas_unit": meas_unit, "concen_unit": concen_unit})

        if (cal_mode == "point"):
            json_content.update({"time": time, "time-unit": time_unit})
        with open(full_path, "w", encoding='utf-8') as f:
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

@file_bp.route('/get_report_items', methods=['GET'])
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


@file_bp.route('/save_report_item_order', methods=['POST'])
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


@file_bp.route('/delete_report_item', methods=['POST'])
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


@file_bp.route('/export_report_excel', methods=['POST'])
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
    from openpyxl.chart import LineChart, ScatterChart, Reference, Series
    from openpyxl.chart.marker import Marker
    from openpyxl.chart.shapes import GraphicalProperties
    from openpyxl.chart.series import Series as XYSeries, SeriesLabel
    from openpyxl.chart.data_source import (
        NumRef, NumData, NumVal, NumDataSource, AxDataSource)
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

    def _add_native_scatter_chart(ws, s, anchor_row):
        """Render a calibration fit as a *native* (editable) value-axis ScatterChart.

        Two markers-only series — the standards (blue diamonds) and the fitted curve
        (fine red dots) — sharing one sorted X column (which Sheets renders as a
        proportional value axis), with the X axis clamped to round "nice numbers"
        ticks. Unlike an embedded PNG, the title/axis titles stay editable.

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

        # Merge both datasets onto a single, SORTED shared X column (col AA), with
        # each Y column blank on the other dataset's rows. Two requirements force
        # this shape:
        #   1. Google Sheets' scatter model permits only ONE X column per chart, so
        #      independent per-series X (valid in Excel's true XY model) makes Sheets
        #      silently drop the fit series — the curve never appears.
        #   2. That shared X must be MONOTONIC, or Sheets falls back to a *category*
        #      axis (points placed by row index, not value — standards crammed left,
        #      the fit splayed right). Sorting the merged rows keeps the axis numeric.
        # Values are written as floats (General format) so Excel plots them and shows
        # the decimals in the user's own locale — do not stringify or pin a format.
        merged = sorted(
            [(x, y, None) for (x, y) in points] + [(x, None, y) for (x, y) in fit],
            key=lambda r: r[0],
        )
        hc = getattr(ws, '_chart_helper_col', 27)  # first helper block at col AA
        x_col, ys_col, yf_col = hc, hc + 1, hc + 2
        _cell(ws, 1, x_col, 'x'); _cell(ws, 1, ys_col, 'std_y'); _cell(ws, 1, yf_col, 'fit_y')
        for i, (x, ys, yf) in enumerate(merged, start=2):
            ws.cell(i, x_col, value=x)
            if ys is not None:
                ws.cell(i, ys_col, value=ys)   # fit_y left blank → skipped
            if yf is not None:
                ws.cell(i, yf_col, value=yf)   # std_y left blank → skipped
        last = len(merged) + 1

        chart = ScatterChart()
        # scatterStyle is *required* by the OOXML schema. Omitting it yields a
        # technically-invalid chart that Excel silently "repairs" (dropping the
        # marker series) and that Google Sheets refuses to render at all. Both
        # series are markers-only (no lines), so 'marker' is the honest style and
        # keeps Google Sheets importing this as a scatter (value axis) rather than
        # a line chart (category axis that labels every concentration).
        chart.scatterStyle = 'marker'
        chart.title = s.get('title') or s.get('label') or 'Calibration Curve'
        chart.x_axis.title = s.get('xLabel') or 'Concentration'
        chart.y_axis.title = s.get('yLabel') or 'Value'
        # openpyxl defaults axes to delete=True, which hides the axis titles.
        chart.x_axis.delete = False
        chart.y_axis.delete = False
        # ScatterChart leaves both value axes at axPos='l'; the X axis belongs at
        # the bottom (some readers, incl. Google Sheets, mis-plot otherwise).
        chart.x_axis.axPos = 'b'
        chart.y_axis.axPos = 'l'
        # Round value-axis ticks: clamp the X axis to a "nice numbers" series
        # (`_nice_axis_ticks` → 0,100,…,500) via scaling bounds + majorUnit. Sheets
        # renders this shared-X scatter as a proportional VALUE axis (the numCache
        # makes X numeric), so a majorUnit gives clean evenly-spaced round ticks
        # instead of the raw standard values (e.g. 50, 200) it would otherwise pick;
        # the bounds also crop the fit's negative/over-range extrapolation tail.
        base_xs = [p[0] for p in (points if points else fit)]
        ticks = _nice_axis_ticks(min(base_xs), max(base_xs))
        if len(ticks) > 1:
            chart.x_axis.scaling.min = ticks[0]
            chart.x_axis.scaling.max = ticks[-1]
            chart.x_axis.majorUnit = ticks[1] - ticks[0]
        chart.style = 13
        chart.width = 18
        chart.height = 11
        # Each Y column is blank on the other series' rows; 'gap' just leaves those
        # cells empty (both series are markers-only, so there is no line to bridge).
        chart.display_blanks = 'gap'

        # Build the two series with explicit numeric CACHES. openpyxl writes bare
        # cell references with no cached values; Excel recomputes them on open, but
        # Google Sheets does not — without a numCache it treats the X refs as text
        # *categories* and prints every fitted point's concentration along the axis
        # (the cluttered, category-axis mis-render). Caching the numbers makes the X
        # an unambiguous value axis with clean, evenly-spaced ticks. Both series
        # reference the SAME (sorted) X column; blank Y rows are skipped.
        sheet_q = ws.title.replace("'", "''")

        def _ref(col_idx):
            c = get_column_letter(col_idx)
            return "'{s}'!${c}${lo}:${c}${hi}".format(s=sheet_q, c=c, lo=2, hi=last)

        def _cache(values):
            # 0-based idx within the range; blanks (None) are omitted so the
            # importer reads them as empty cells (the other series' rows).
            return NumData(pt=[NumVal(idx=i, v=v) for i, v in enumerate(values)
                               if v is not None])

        xs_all = [x for (x, ys, yf) in merged]

        def _cached_series(y_col, y_values, title):
            ser = XYSeries()
            ser.xVal = AxDataSource(numRef=NumRef(f=_ref(x_col), numCache=_cache(xs_all)))
            ser.yVal = NumDataSource(numRef=NumRef(f=_ref(y_col), numCache=_cache(y_values)))
            ser.tx = SeriesLabel(v=title)
            ser.graphicalProperties = GraphicalProperties()
            return ser

        if points:
            sp = _cached_series(ys_col, [ys for (x, ys, yf) in merged], 'Standards')
            # Big blue DIAMONDS for the measured standards — a deliberately distinct
            # shape from the fit's small round dots so the two are unmistakable.
            marker = Marker(symbol='diamond', size=8)
            marker.graphicalProperties = GraphicalProperties(solidFill='3498DB')
            sp.marker = marker
            line = LineProperties(); line.noFill = True  # markers only, no join line
            sp.graphicalProperties.line = line
            chart.series.append(sp)
        if fit:
            algo = s.get('algo')
            sf = _cached_series(yf_col, [yf for (x, ys, yf) in merged],
                                'Fit ({})'.format(algo) if algo else 'Fit')
            # The fit is a dense (150-pt) sampling of the *exact* fitted curve, drawn
            # as small markers with NO connecting line. Two reasons it must be
            # markers-only: (1) a line series makes Google Sheets import the whole
            # chart as a *line* chart — a category X axis that prints every point's
            # concentration along the bottom; markers-only keeps it a true scatter
            # (value axis, clean ticks); (2) the dense line rendered as a thick band.
            # 150 fine points read as a smooth curve in both apps. NOT a native
            # trendline: the chart plots metric-vs-concentration while the app fits
            # concentration-vs-metric and inverts it, so a native trendline would
            # recompute the *wrong* functional family (log<->exp swap) and has no
            # Michaelis-Menten type.
            # 'dot' is the smallest marker symbol — a fine point, smaller than a
            # 'circle' (whose size floors at 2 in OOXML). 150 fine dots read as a
            # thin smooth fit trace in Google Sheets (which draws the fit as points).
            fmarker = Marker(symbol='dot', size=2)
            fmarker.graphicalProperties = GraphicalProperties(solidFill='E74C3C')
            sf.marker = fmarker
            line = LineProperties(); line.noFill = True   # markers only — see above
            sf.graphicalProperties.line = line
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
                _cell(ws, r, 1, 'Raw Data', bold=True, size=11, fill=SECTION_FILL, color='2c3e50')
                if len(csv_columns) > 1:
                    ws.merge_cells(start_row=r, start_column=1,
                                   end_row=r, end_column=min(len(csv_columns), 8))
                r += 1
                for ci, col in enumerate(csv_columns, 1):
                    _cell(ws, r, ci, col, bold=True, color='FFFFFF',
                          fill=TABLE_HDR_FILL, align_h='center', border=CELL_BORDER)
                    ws.column_dimensions[get_column_letter(ci)].width = max(12, len(str(col)) + 2)
                r += 1
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
                r += 1  # blank row before charts

                # Prefer native (editable) ScatterCharts — points + fit line with
                # live, renameable axis titles. Falls back to embedded PNGs only
                # for older payloads that still send chart_images.
                if chart_series:
                    for s in chart_series:
                        label = s.get('label', '')
                        if label:
                            _cell(ws, r, 1, label, bold=True, size=11, color='555555')
                            r += 1
                        r = _add_native_scatter_chart(ws, s, r)
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


def _write_normalized_csv(file_path, save_name, save_dir, source_index=None):
    """Write a normalized copy of a CSV file to a new CSV file.

    Companion to _write_subset_csv for the Normalize extraction feature.
    Each targeted Value column has its own minimum subtracted from every
    value (per-column blank removal), so the lowest point becomes 0 and the
    measured baseline (blank) is removed. The Timestamp column and any
    non-targeted columns are copied unchanged.

    If source_index is None, every Value column is normalized (global button).
    Otherwise only the Value column for that source is normalized.
    Preserves all metadata (#) lines and the header row.
    """
    if not file_path or not os.path.isfile(file_path):
        return jsonify({'status': 'error', 'message': 'Source file not found.'}), 404

    if save_name is None or not str(save_name).strip():
        return jsonify({'status': 'error', 'message': 'Save name is required.'}), 400

    # Sanitize the save name -> strip any path components and .csv suffix
    save_name = os.path.basename(str(save_name).strip())
    if save_name.lower().endswith('.csv'):
        save_name = save_name[:-4]

    src_dir = os.path.dirname(file_path)
    save_dir = save_dir or src_dir
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir, exist_ok=True)

    out_path = os.path.join(save_dir, save_name + '.csv')

    metadata_lines = []
    header_line = None
    data_rows = []
    with open(file_path, 'r', newline='') as f:
        for raw in f:
            line = raw.rstrip('\n')
            if line.startswith('#'):
                metadata_lines.append(line)
            elif header_line is None:
                header_line = line
            else:
                data_rows.append(line)

    if header_line is None:
        return jsonify({'status': 'error', 'message': 'No header row found in source file.'}), 400

    header_cols = header_line.split(',')
    # Value columns: every column whose name starts with "Value" (col 0 is Timestamp).
    value_col_idx = [i for i, name in enumerate(header_cols)
                     if name.strip().lower().startswith('value')]
    if not value_col_idx:
        # Fallback: treat every column except the first (timestamp) as a value column.
        value_col_idx = list(range(1, len(header_cols)))

    if source_index is None:
        target_idx = list(value_col_idx)
    else:
        try:
            target_idx = [value_col_idx[int(source_index)]]
        except (IndexError, ValueError, TypeError):
            return jsonify({'status': 'error', 'message': 'Invalid source index.'}), 400

    # Parse non-blank rows into cells once.
    parsed = [row.split(',') for row in data_rows if row.strip()]

    # Compute per-column minimum over numeric cells.
    col_min = {}
    for ci in target_idx:
        mn = None
        for cells in parsed:
            if ci >= len(cells):
                continue
            try:
                v = float(cells[ci])
            except ValueError:
                continue
            if mn is None or v < mn:
                mn = v
        col_min[ci] = mn

    out_rows = []
    for cells in parsed:
        new_cells = list(cells)
        for ci in target_idx:
            mn = col_min.get(ci)
            if mn is None or ci >= len(cells):
                continue
            try:
                v = float(cells[ci])
            except ValueError:
                continue
            new_cells[ci] = '%.6g' % (v - mn)
        out_rows.append(','.join(new_cells))

    # Record the transformation in metadata for traceability.
    if source_index is None:
        metadata_lines.append('# Normalization: subtract per-column minimum / blank removal (all sources)')
    else:
        metadata_lines.append('# Normalization: subtract per-column minimum / blank removal (source %d)' % (int(source_index) + 1))

    with open(out_path, 'w', newline='') as f:
        for m in metadata_lines:
            f.write(m + '\n')
        f.write(header_line + '\n')
        for row in out_rows:
            f.write(row + '\n')

    rel_path = os.path.relpath(out_path, state.data_root_path) \
        if hasattr(state, 'data_root_path') and state.data_root_path else out_path

    return jsonify({
        'status': 'success',
        'count': len(out_rows),
        'path': rel_path,
        'file_name': save_name + '.csv'
    })


@file_bp.route('/save_normalized_csv', methods=['POST'])
@validate_json
def save_normalized_csv():
    """Save a normalized copy of a CSV file (subtract per-column minimum / blank removal) to a new CSV file.

    Body: {file, save_name, save_dir, source_index?}. When source_index is
    omitted/null, every Value column is normalized; otherwise only the column
    for that source is normalized.
    """
    try:
        data = request.get_json()
        file_path = data.get('file')
        save_name = data.get('save_name')
        save_dir = data.get('save_dir')
        source_index = data.get('source_index')
        return _write_normalized_csv(file_path, save_name, save_dir, source_index)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
