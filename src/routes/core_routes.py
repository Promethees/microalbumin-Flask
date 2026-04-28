from flask import Blueprint, jsonify, make_response, render_template, request
import os
import platform
import time
import signal
import threading
import state
from file_path import get_directory, browse_directory, get_parent_directory, get_child_directories
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
        with open(state.log_file, 'w') as f:
            f.write("")  # Clear the file
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
    directory = get_directory()
    range_input = get_range_input()
    mode_input = get_mode_input()
    quantity_input = get_quantity_input()
    file_list = get_file_list(directory)
    cal_json_list = get_file_list(os.path.join(state.json_root_path, "kinetics"), "*.json")
    
    # Can't use clear_logs() call like main.py did easily without importing it, but let's clear it here
    try:
        with open(state.log_file, 'w') as f:
            f.write("")
    except:
        pass

    response = make_response(render_template('index.html', 
                         title="Easy OKAPI",
                         directory= os.path.abspath(directory),
                         range_input=range_input,
                         mode_input=mode_input,
                         quantity_input=quantity_input,
                         file_list=file_list,
                         cal_json_list=cal_json_list,
                         delimiter=state.delimiter,
                         production_mode=state.PRODUCTION_MODE))
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
    new_path = request.form['path']
    if browse_directory(new_path):
        file_list = get_file_list(get_directory())
        return jsonify({'status': 'success', 'path': new_path, 'files': file_list})
    return jsonify({'status': 'error', 'message': 'Invalid directory'})

@core_bp.route('/browse_export', methods=['GET'])
def browse_export():
    path = request.args.get('path')
    if not path:
        return jsonify({'exists': False, 'error': 'No path provided'}), 400
    exists = os.path.exists(path)
    return jsonify({'exists': exists})

@core_bp.route('/get_parents', methods=['GET'])
def get_parents():
    current_dir = get_directory()
    parent_dir = get_parent_directory(current_dir)
    return jsonify({'parent': parent_dir})

@core_bp.route('/get_children', methods=['GET'])
def get_children():
    current_dir = get_directory()
    child_dirs = get_child_directories(current_dir)
    return jsonify({'children': child_dirs})

@core_bp.route('/get_json_cal', methods=['GET'])
def get_json_cal():
    mode = request.args.get('mode')
    json_path = os.path.join(state.json_root_path, mode)
    if os.path.exists(json_path):
        json_files = get_file_list(json_path, "*.json")
        return jsonify({'status': 'success', 'files': json_files})
    return jsonify({'status': 'error', 'message': "Invalid directory"})
