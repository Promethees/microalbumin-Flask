from flask import Blueprint, jsonify, make_response, render_template, request
import os
import time
import signal
import threading
import state
import user_settings as _user_settings
import event_logger
from file_path import DATA_ROOT, get_data_subfolders
from range import get_range_input
from mode import get_mode_input
from quantity import get_quantity_input
from file import get_file_list

core_bp = Blueprint('core', __name__)

@core_bp.route('/ping')
def ping():
    return jsonify({'status': 'success'})

@core_bp.route('/clear_logs', methods=['POST'])
def clear_logs():
    try:
        with open(state.log_file, 'w', encoding='utf-8') as f:
            f.write("")
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

@core_bp.route('/clear_cache', methods=['POST'])
def clear_cache():
    try:
        response = make_response(jsonify({
            'status': 'success',
            'message': 'Clearing client-side cache',
            'action': 'clear_storage'
        }))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

@core_bp.route('/')
def index():
    range_input = get_range_input()
    mode_input = get_mode_input()
    quantity_input = get_quantity_input()
    file_list = get_file_list(DATA_ROOT)
    cal_json_list = get_file_list(os.path.join(state.json_root_path, "kinetics"), "*.json")

    try:
        with open(state.log_file, 'w', encoding='utf-8') as f:
            f.write("")
    except:
        pass

    event_logger.cleanup_old_logs()
    event_logger.append('session', 'start')
    user_settings = _user_settings.load()
    response = make_response(render_template('index.html',
                         title="Easy OKAPI",
                         data_root=DATA_ROOT,
                         report_root=state.report_root_path,
                         json_root=state.json_root_path,
                         range_input=range_input,
                         mode_input=mode_input,
                         quantity_input=quantity_input,
                         file_list=file_list,
                         cal_json_list=cal_json_list,
                         delimiter=state.delimiter,
                         production_mode=state.PRODUCTION_MODE,
                         app_version=state.APP_VERSION,
                         user_settings=user_settings))
    return response

def delayed_termination():
    time.sleep(5) 
    # Use SIGTERM for all platforms and modes. The server in main.py has signal handlers
    # to gracefully detect SIGTERM and execute atexit hooks natively, protecting parent wrapper scripts.
    os.kill(os.getpid(), signal.SIGTERM)

@core_bp.route('/shutdown', methods=['POST'])
def shutdown():
    threading.Thread(target=delayed_termination).start()
    data = request.get_json()
    mode = data.get('mode', 'light') if data else 'light'
    return render_template('goodbye.html', production_mode=state.PRODUCTION_MODE, mode=mode)

@core_bp.route('/browse', methods=['POST'])
def browse():
    new_path = request.form.get('path')
    if not new_path:
        return jsonify({'status': 'error', 'message': 'Path is required'}), 400
    abs_path = os.path.abspath(new_path)
    data_root = state.data_root_path
    report_root = state.report_root_path
    in_data = abs_path == data_root or abs_path.startswith(data_root + os.sep)
    in_report = abs_path == report_root or abs_path.startswith(report_root + os.sep)
    if not (in_data or in_report):
        return jsonify({'status': 'error', 'message': 'Invalid directory'})
    if not os.path.isdir(abs_path):
        return jsonify({'status': 'error', 'message': 'Directory not found'})
    file_list = get_file_list(abs_path)
    return jsonify({'status': 'success', 'path': abs_path, 'files': file_list})

@core_bp.route('/get_data_folders', methods=['GET'])
def get_data_folders():
    folders = get_data_subfolders()
    return jsonify({'status': 'success', 'folders': folders})

@core_bp.route('/browse_export', methods=['GET'])
def browse_export():
    path = request.args.get('path')
    if not path:
        return jsonify({'exists': False, 'error': 'No path provided'}), 400
    exists = os.path.exists(path)
    return jsonify({'exists': exists})

@core_bp.route('/get_json_cal', methods=['GET'])
def get_json_cal():
    mode = request.args.get('mode', '').strip().lower()
    if mode not in ('kinetics', 'point'):
        return jsonify({'status': 'success', 'files': []})
    json_path = os.path.join(state.json_root_path, mode)
    os.makedirs(json_path, exist_ok=True)
    json_files = get_file_list(json_path, "*.json")
    return jsonify({'status': 'success', 'files': json_files})

@core_bp.route('/settings', methods=['GET'])
def get_settings():
    return jsonify({'status': 'success', 'settings': _user_settings.load()})


@core_bp.route('/settings', methods=['POST'])
def post_settings():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'No JSON data'}), 400
    if _user_settings.save(data):
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Could not save settings'}), 500


@core_bp.route('/event_log', methods=['GET'])
def get_event_log():
    return jsonify({'status': 'success', 'events': event_logger.read_all()})


@core_bp.route('/event_log', methods=['POST'])
def post_event_log():
    data = request.get_json(silent=True) or {}
    event_type = str(data.get('type', '')).strip()
    action = str(data.get('action', '')).strip()
    if not event_type or not action:
        return jsonify({'status': 'error', 'message': 'type and action are required'}), 400
    event_logger.append(event_type, action, data.get('details'))
    return jsonify({'status': 'success'})


@core_bp.route('/get_report_subjects', methods=['GET'])
def get_report_subjects():
    report_path = state.report_root_path
    if os.path.exists(report_path):
        # List only directories
        subjects = [d for d in os.listdir(report_path) if os.path.isdir(os.path.join(report_path, d))]
        subjects.sort()
        return jsonify({'status': 'success', 'subjects': subjects})
    return jsonify({'status': 'error', 'message': "Report directory not found"})
