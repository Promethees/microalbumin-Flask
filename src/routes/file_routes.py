from flask import Blueprint, jsonify, request
from http import HTTPStatus
import os
import json
import csv
import re
import time
import threading
import secrets
from datetime import datetime
from pathlib import Path
from filelock import FileLock, Timeout
import shutil

import state
from file_path import (DATA_ROOT, validate_in_data_root, validate_in_allowed_roots,
                       is_reserved_data_folder_name, RESERVED_ARCHIVE_FOLDER,
                       parse_csv_metadata, detect_csv_schema,
                       CSV_SCHEMA_TIMESERIES, CSV_SCHEMA_KINETICS_CAL, CSV_SCHEMA_POINT_CAL,
                       DEFAULT_CONCEN_UNIT)
from file import get_dynamic_data, replace_empty, merge_csv_files
from file_operations import remove_csv_columns
from measure import sort_csv_file
from get_next_filename import get_next_filename
from export_cal_json import processJSONCoef, extractAnalysisCoefficients, CustomEncoder
from excel_formula import formulas_from_content
from export_data import metadata_mismatches, write_metadata, write_headers, extract_single_entry
from validators import validate_json

file_bp = Blueprint('file', __name__)

# ── Cross-tab edit-session locks ──────────────────────────────────────────────
# A file open in the editor of one browser tab must not be editable from another
# tab at the same time. Because every tab talks to this one Flask process, an
# in-memory registry (guarded by a lock for the threaded dev server) is enough:
# it maps a file's absolute path to the holder's opaque token and a last-seen
# timestamp. The holding tab heartbeats to keep the lock fresh; a tab that closes
# or crashes without releasing lets the lock go stale after _EDIT_LOCK_TTL so the
# file is never wedged permanently. This is distinct from the per-write FileLock
# in edit_file(), which only guards the atomicity of a single save.
_EDIT_LOCK_TTL = 120.0   # seconds a lock survives without a heartbeat
_edit_locks = {}          # abs_path -> {'token': str, 'ts': float (monotonic)}
_edit_locks_guard = threading.Lock()


def _edit_lock_key(path, filename):
    """Absolute-path registry key for a file, or None when filename is missing."""
    if not filename:
        return None
    return os.path.normcase(os.path.abspath(os.path.join(path or DATA_ROOT, filename)))


def _edit_lock_holder(key, now):
    """Live holder token for ``key``, pruning the entry when it is stale/expired.

    Must be called while holding ``_edit_locks_guard`` — it mutates the registry.
    """
    entry = _edit_locks.get(key)
    if not entry:
        return None
    if now - entry['ts'] > _EDIT_LOCK_TTL:
        _edit_locks.pop(key, None)
        return None
    return entry['token']


_SCHEMA_VALIDATORS = {
    CSV_SCHEMA_KINETICS_CAL: {
        'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|-?\d+|-?\d+\.\d+),(NONE|\d+|\d+\.\d*)$",
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
    validated = validate_in_allowed_roots(read_file)
    if not validated:
        return jsonify({'headers': [], 'error': 'Invalid file path'}), 400
    read_file = validated
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

@file_bp.route('/acquire_edit_lock', methods=['POST'])
@validate_json({'filename': str, 'path': (str, '', False), 'token': (str, '', False)})
def acquire_edit_lock(validated_data):
    """Claim the edit-session lock for a file so other tabs can't edit it.

    Returns the opaque holder token on success; 423 when another tab already
    holds a live lock. Re-acquiring with the same token (a reopened editor)
    refreshes the lock instead of failing.
    """
    key = _edit_lock_key(validated_data.get('path'), validated_data['filename'])
    if not key:
        return jsonify({'status': 'error', 'message': 'Filename is required'}), HTTPStatus.BAD_REQUEST
    requester = (validated_data.get('token') or '').strip()
    now = time.monotonic()
    with _edit_locks_guard:
        holder = _edit_lock_holder(key, now)
        if holder and requester and holder == requester:
            _edit_locks[key] = {'token': holder, 'ts': now}
            return jsonify({'status': 'success', 'token': holder})
        if holder:
            return jsonify({'status': 'locked',
                            'message': 'This file is currently being edited in another tab.'}), HTTPStatus.LOCKED
        token = secrets.token_hex(16)
        _edit_locks[key] = {'token': token, 'ts': now}
    return jsonify({'status': 'success', 'token': token})


@file_bp.route('/refresh_edit_lock', methods=['POST'])
@validate_json({'filename': str, 'path': (str, '', False), 'token': str})
def refresh_edit_lock(validated_data):
    """Heartbeat: keep this tab's edit lock alive (or reclaim it if it lapsed)."""
    key = _edit_lock_key(validated_data.get('path'), validated_data['filename'])
    token = (validated_data.get('token') or '').strip()
    if not key or not token:
        return jsonify({'status': 'error', 'message': 'Filename and token are required'}), HTTPStatus.BAD_REQUEST
    now = time.monotonic()
    with _edit_locks_guard:
        holder = _edit_lock_holder(key, now)
        if holder and holder != token:
            return jsonify({'status': 'locked',
                            'message': 'Lock held by another tab.'}), HTTPStatus.LOCKED
        # Held by us, or expired and now free — (re)stamp it for this open editor.
        _edit_locks[key] = {'token': token, 'ts': now}
    return jsonify({'status': 'success', 'token': token})


@file_bp.route('/release_edit_lock', methods=['POST'])
@validate_json({'filename': str, 'path': (str, '', False), 'token': (str, '', False)})
def release_edit_lock(validated_data):
    """Release this tab's edit lock. No-op if the lock is gone or held by another tab."""
    key = _edit_lock_key(validated_data.get('path'), validated_data['filename'])
    token = (validated_data.get('token') or '').strip()
    if key:
        with _edit_locks_guard:
            entry = _edit_locks.get(key)
            if entry and (not token or entry['token'] == token):
                _edit_locks.pop(key, None)
    return jsonify({'status': 'success'})


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

        v_file = validate_in_allowed_roots(file_path)
        v_new = validate_in_allowed_roots(new_file_path)
        if not v_file or not v_new:
            return jsonify({'status': 'error', 'message': 'Invalid file path'}), HTTPStatus.BAD_REQUEST
        file_path, new_file_path = v_file, v_new

        if not os.path.exists(file_path):
            return jsonify({'status': 'error', 'message': f'File {file_name} not found'}), HTTPStatus.NOT_FOUND

        if file_name != new_file_name and os.path.exists(new_file_path):
            return jsonify({'status': 'error', 'message': f'File {new_file_name} already exists'}), HTTPStatus.CONFLICT

        # Cross-tab edit-session lock: reject a save when another tab currently
        # holds the editing lock for this file (see /acquire_edit_lock). The
        # editor sends its edit_token; a save from the lock holder is allowed, a
        # save from any other origin (or a stale/absent token) is refused.
        edit_token = (request.form.get('edit_token') or '').strip()
        lock_key = _edit_lock_key(path, file_name)
        with _edit_locks_guard:
            holder = _edit_lock_holder(lock_key, time.monotonic())
        if holder and holder != edit_token:
            return jsonify({'status': 'error', 'message': 'This file is being edited in another tab.'}), HTTPStatus.LOCKED

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
            # Per-write lock guarding the atomicity of THIS save. The context
            # manager releases it on every exit path; the .lock file is left on
            # disk (standard filelock behaviour) rather than unlinked while held,
            # which would let a concurrent writer create a fresh lock and race.
            lock_path = new_file_path + '.lock'
            try:
                with FileLock(lock_path, timeout=0):
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
            except Timeout:
                return jsonify({'status': 'error', 'message': 'Another save is in progress or previous save crashed'}), 423

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

def _resolve_form_file_target():
    """Parse and validate the {filename, tabletype, mode, path} form target
    shared by /delete_file and /copy_file: a json-table entry lives under
    json_root/<mode>, anything else under the supplied data path.

    Returns ((file_name, tabletype, src_dir, abs_path), None) on success or
    (None, (response, status)) with each guard's long-standing message.
    """
    file_name = request.form.get('filename')
    tabletype = request.form.get('tabletype')
    mode = request.form.get('mode')
    path = request.form.get('path') if request.form.get('path') else DATA_ROOT

    if not file_name or not tabletype:
        return None, (jsonify({'status': 'error', 'message': 'Filename and tabletype are required'}), HTTPStatus.BAD_REQUEST)

    if tabletype == '#json-table':
        if not mode:
            return None, (jsonify({'status': 'error', 'message': 'Mode is required for JSON table type'}), HTTPStatus.BAD_REQUEST)
        src_dir = os.path.join(state.json_root_path, mode)
    else:
        src_dir = path

    abs_path = validate_in_allowed_roots(os.path.join(src_dir, file_name))
    if not abs_path:
        return None, (jsonify({'status': 'error', 'message': 'Invalid file path'}), HTTPStatus.BAD_REQUEST)
    return (file_name, tabletype, src_dir, abs_path), None


@file_bp.route('/delete_file', methods=['POST'])
def delete_file():
    try:
        if state.process and state.process.poll() is None:
            return jsonify({'status': 'error', 'message': 'Cannot delete files while the data collection process is running'}), HTTPStatus.LOCKED

        target, err = _resolve_form_file_target()
        if err:
            return err
        file_name, _tabletype, _src_dir, file_path = target

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

@file_bp.route('/create_data_folder', methods=['POST'])
@validate_json({'name': str})
def create_data_folder(validated_data):
    """Create an empty data subfolder under DATA_ROOT without running a reading.

    Standalone counterpart to the folder auto-creation in /run_script: it lets a
    user organise data folders even when no colorimeter is connected. The name
    rules mirror /rename_data_folder — a bare, visible folder name (no
    separators, traversal, hidden ``.``/``_`` prefix, or the reserved archive
    name ``root``).
    """
    try:
        if state.process and state.process.poll() is None:
            return jsonify({'status': 'error', 'message': 'Cannot create folders while the data collection process is running'}), HTTPStatus.LOCKED

        name = (validated_data['name'] or '').strip()
        if not name:
            return jsonify({'status': 'error', 'message': 'Folder name is required'}), HTTPStatus.BAD_REQUEST
        if any(x in name for x in ('..', '/', '\\', '\x00')) or name.startswith('.') or name.startswith('_'):
            return jsonify({'status': 'error', 'message': 'Invalid folder name'}), HTTPStatus.BAD_REQUEST
        if is_reserved_data_folder_name(name):
            return jsonify({'status': 'error', 'message': f"'{RESERVED_ARCHIVE_FOLDER}' is a reserved folder name and cannot be used"}), HTTPStatus.BAD_REQUEST

        new_path = os.path.join(DATA_ROOT, name)
        # Defensive: confirm the joined path still resolves inside DATA_ROOT.
        if not validate_in_data_root(new_path):
            return jsonify({'status': 'error', 'message': 'Invalid folder path'}), HTTPStatus.BAD_REQUEST
        if os.path.exists(new_path):
            return jsonify({'status': 'error', 'message': 'A folder with that name already exists'}), HTTPStatus.CONFLICT

        os.makedirs(new_path)
        return jsonify({'status': 'success', 'message': f"Created folder '{name}'", 'path': new_path, 'name': name}), HTTPStatus.OK
    except PermissionError as e:
        return jsonify({'status': 'error', 'message': f'Permission denied: {str(e)}'}), HTTPStatus.FORBIDDEN
    except OSError as e:
        return jsonify({'status': 'error', 'message': f'Err: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), HTTPStatus.INTERNAL_SERVER_ERROR


@file_bp.route('/create_csv_file', methods=['POST'])
@validate_json({
    'mode': str,
    'cal_mode': (str, 'kinetics', False),
    'filename': str,
    'path': (str, '', False),
    'num_sources': (int, 1, False),
    'num_lines': (int, 0, False),
    'concenUnit': (str, DEFAULT_CONCEN_UNIT, False),
})
def create_csv_file(validated_data):
    """Create a new template CSV for a measurement mode — no reading run.

    ``kinetics``/``point`` → a raw timeseries file (``Timestamp,Value:1[..N]``).
    ``calibrate``          → a calibration table for ``cal_mode`` (kinetics/point).

    The file carries the mode's correct metadata block + header row and
    ``num_lines`` blank placeholder data rows (0 = header only), so it opens
    straight in the file editor for manual data entry. Placeholder rows are
    written editor-valid (timeseries: an incrementing Timestamp with empty value
    cells; calibration: all ``NONE``) so a later save doesn't fail validation. It
    never clobbers an existing file: a name clash is auto-incremented
    (``name_1.csv`` …).
    """
    try:
        if state.process and state.process.poll() is None:
            return jsonify({'status': 'error', 'message': 'Cannot create files while the data collection process is running'}), HTTPStatus.LOCKED

        mode = (validated_data['mode'] or '').strip().lower()
        if mode not in ('kinetics', 'point', 'calibrate'):
            return jsonify({'status': 'error', 'message': 'Invalid mode'}), HTTPStatus.BAD_REQUEST

        target_dir = validate_in_data_root(validated_data.get('path') or DATA_ROOT)
        if not target_dir:
            return jsonify({'status': 'error', 'message': 'Invalid folder path'}), HTTPStatus.BAD_REQUEST
        if not os.path.isdir(target_dir):
            return jsonify({'status': 'error', 'message': 'Folder not found'}), HTTPStatus.NOT_FOUND

        raw_name = (validated_data['filename'] or '').strip()
        if not raw_name:
            return jsonify({'status': 'error', 'message': 'File name is required'}), HTTPStatus.BAD_REQUEST
        if any(c in raw_name for c in ('/', '\\', '..', '\x00')):
            return jsonify({'status': 'error', 'message': 'Invalid file name'}), HTTPStatus.BAD_REQUEST
        # Accept an optional user-typed .csv suffix; the stem drives auto-naming.
        stem = raw_name[:-4] if raw_name.lower().endswith('.csv') else raw_name
        if not stem:
            return jsonify({'status': 'error', 'message': 'File name is required'}), HTTPStatus.BAD_REQUEST

        concen_unit = validated_data['concenUnit'] or DEFAULT_CONCEN_UNIT

        try:
            num_lines = int(validated_data['num_lines'])
        except (TypeError, ValueError):
            num_lines = 0
        num_lines = max(0, min(num_lines, 100000))

        cal_mode = None
        if mode == 'calibrate':
            cal_mode = (validated_data['cal_mode'] or 'kinetics').strip().lower()
            if cal_mode not in ('kinetics', 'point'):
                return jsonify({'status': 'error', 'message': 'Invalid calibration mode'}), HTTPStatus.BAD_REQUEST
            time_unit = 'minute' if cal_mode == 'point' else 'minutes'
        else:
            try:
                n_sources = int(validated_data['num_sources'])
            except (TypeError, ValueError):
                n_sources = 1
            n_sources = max(1, min(n_sources, 50))
            header = 'Timestamp,' + ','.join('Value:%d' % i for i in range(1, n_sources + 1))

        full_path = os.path.join(target_dir, stem + '.csv')
        if os.path.exists(full_path):
            full_path = get_next_filename('.csv', target_dir, stem)

        with open(full_path, 'w', newline='', encoding='utf-8') as f:
            if mode == 'calibrate':
                write_metadata(f, 'NONE', 'NONE', time_unit, cal_mode, concen_unit)
                writer = csv.writer(f)
                write_headers(writer, cal_mode)
                # Blank placeholder rows: all NONE (5 cols kinetics / 3 cols point).
                ncols = 5 if cal_mode == 'kinetics' else 3
                for _ in range(num_lines):
                    writer.writerow(['NONE'] * ncols)
            else:
                f.write("# Measurement: NONE\n")
                f.write("# Unit: NONE\n")
                f.write("# Concentration: NONE\n")
                f.write("# ConcenUnit: %s\n" % concen_unit)
                f.write(header + "\n")
                # Blank placeholder rows: incrementing Timestamp, empty value cells.
                for i in range(num_lines):
                    f.write("%d%s\n" % (i, "," * n_sources))

        return jsonify({
            'status': 'success',
            'message': f"Created {os.path.basename(full_path)}",
            'path': full_path,
            'filename': os.path.basename(full_path)
        }), HTTPStatus.OK
    except PermissionError as e:
        return jsonify({'status': 'error', 'message': f'Permission denied: {str(e)}'}), HTTPStatus.FORBIDDEN
    except OSError as e:
        return jsonify({'status': 'error', 'message': f'Err: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), HTTPStatus.INTERNAL_SERVER_ERROR


@file_bp.route('/copy_file', methods=['POST'])
def copy_file():
    try:
        if state.process and state.process.poll() is None:
            return jsonify({'status': 'error', 'message': 'Cannot copy files while the data collection process is running'}), HTTPStatus.LOCKED

        target, err = _resolve_form_file_target()
        if err:
            return err
        file_name, tabletype, src_dir, src_path = target

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

        validated = validate_in_allowed_roots(file_path)
        if not validated:
             return jsonify({'status': 'failure', 'message': 'Invalid file path'}), 400
        file_path = validated

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
    validated = validate_in_allowed_roots(selected_file)
    if not validated:
        return jsonify({'data': [], 'error': 'Invalid file path', 'unit': 'NONE'}), 400
    selected_file = validated
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
        validated = validate_in_allowed_roots(file_path)
        if not validated:
            return jsonify({'status': 'error', 'message': 'Invalid file path'}), HTTPStatus.BAD_REQUEST
        file_path = validated

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

    # The source is a managed file (confine to the app's roots); save_dir is a
    # user-chosen export destination, so only guard it against traversal.
    validated_source = validate_in_allowed_roots(source_file)
    if not validated_source or '..' in os.path.normpath(save_dir):
        return jsonify({'status': 'error', 'message': 'Invalid path'})
    source_file = validated_source
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
            meta_dict = get_dynamic_data(full_path).get('metadata', {})
            mismatches = metadata_mismatches(meta_dict, measurement, meas_unit, time_unit, meas_mode, concen_unit)
            if mismatches:
                # Name every clashing field with both sides' values, so it is
                # clear *why* the analysis can't be appended to this calibration
                # table (rather than the opaque "Metadata inconsistency").
                labels = {
                    'Measurement': 'measurement',
                    'MeasUnit': 'measurement unit',
                    'TimeUnit': 'time unit',
                    'MeasMode': 'mode',
                    'ConcenUnit': 'concentration unit',
                }
                details = "; ".join(
                    f"{labels.get(field, field)} (file: {existing or 'none'}, export: {incoming or 'none'})"
                    for field, existing, incoming in mismatches
                )
                plural = "s" if len(mismatches) > 1 else ""
                return jsonify({"status": "error", "message": (
                    f"Cannot append this analysis to \"{file_name}\": its "
                    f"metadata does not match the export. Mismatched field{plural}: "
                    f"{details}. Pick a different calibration table, or adjust the "
                    f"export to match.")})

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

# Excel cell reference like A1, Bved, $A$1 (letters + digits, optional $).
_CELL_RE = re.compile(r'^\$?[A-Za-z]{1,3}\$?[0-9]{1,7}$')

@file_bp.route('/export_cal_excel_formula', methods=['POST'])
@validate_json({
    'regress_algo': (str, 'linear', False),
    'coef_content': ((list, dict), None, False),
    'cal_params': (list, [], False),
    'threshold_val': (float, 0.0, False),
    'cell': (str, 'A1', False),
})
def export_cal_excel_formula(validated_data):
    """Build ready-to-paste Excel formulas from the fitted standard-curve coefficients.

    Reuses the exact coefficient pipeline of /export_cal_coefs
    (extractAnalysisCoefficients → processJSONCoef) so the formula math matches
    what the JSON export records and what the app applies internally. Returns one
    formula per source (labelled), each mapping the ``cell`` (a measured quantity)
    to the derived concentration. A source whose fit is missing / below threshold
    yields a null formula so the caller can flag it.
    """
    regress_algo = validated_data['regress_algo']
    coef_content = validated_data['coef_content']
    cal_params = validated_data['cal_params']
    thres_val = validated_data['threshold_val']
    cell = (validated_data['cell'] or 'A1').strip()
    if not _CELL_RE.match(cell):
        return jsonify({'status': 'error', 'message': 'Invalid cell reference (e.g. A1).'}), HTTPStatus.BAD_REQUEST

    try:
        content = processJSONCoef(
            cal_params,
            extractAnalysisCoefficients(coef_content, thres_val, regress_algo),
            regress_algo,
        )
        formulas = formulas_from_content(content, regress_algo, cell)
        if not formulas:
            return jsonify({'status': 'error', 'message': 'No coefficients available to build a formula.'}), HTTPStatus.BAD_REQUEST
        return jsonify({'status': 'success', 'cell': cell, 'algo': regress_algo, 'formulas': formulas})
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), HTTPStatus.INTERNAL_SERVER_ERROR

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
@validate_json({
    'file': (str, None, False),
    'save_name': (str, None, False),
    'save_dir': (str, None, False),
    'source_index': (int, None, False),
})
def save_normalized_csv(validated_data):
    """Save a normalized copy of a CSV file (subtract per-column minimum / blank removal) to a new CSV file.

    Body: {file, save_name, save_dir, source_index?}. When source_index is
    omitted/null, every Value column is normalized; otherwise only the column
    for that source is normalized. Fields stay schema-optional so
    _write_normalized_csv keeps its specific 404/400 messages.
    """
    try:
        return _write_normalized_csv(validated_data['file'], validated_data['save_name'],
                                     validated_data['save_dir'], validated_data['source_index'])
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
