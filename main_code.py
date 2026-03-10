from flask import Flask, render_template, request, jsonify, make_response
import os
import sys
import argparse
import threading
import time
import signal  
import platform
import subprocess
import atexit
import csv
import pandas as pd
import json
from http import HTTPStatus
from datetime import datetime
import re
from filelock import FileLock, Timeout
import shutil
from pathlib import Path

sys.path.append('code\src')
from file_path import get_directory, browse_directory, get_parent_directory, get_child_directories, is_multi_value_timeseries_csv_header
from range import get_range_input
from mode import get_mode_input
from measure import sort_csv_file
from quantity import get_quantity_input
from file import get_file_list, get_dynamic_data, replace_empty, merge_csv_files
from file_operations import remove_csv_columns
from get_next_filename import get_next_filename
from script_monitor import check_log_for_errors
from export_cal_json import processJSONCoef, extractAnalysisCoefficients, CustomEncoder
from export_data import is_metadata_consistent, write_metadata, write_headers, extract_single_entry
from browser_mgt import open_browser, cleanup, ensure_host_mapping
from send_command import connect_to_device, send_command_and_wait_ack

app = Flask(__name__, static_folder='static')
process = None
monitor_thread = None
script_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(script_dir, "log", "script_logs.txt")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
args = None

os_name = platform.system().lower()
if "window" in os_name:
    delimiter = "\\\\";
else:
    delimiter = "/";

json_root_path = os.path.join(script_dir, "json")
# Configuration - Set this to False for development, True for production
PRODUCTION_MODE = True  # Change this based on your environment

# Region 1: USED by index.js
@app.route('/ping')
def ping():
    return jsonify({'status': 'success'})

@app.route('/clear_logs', methods=['POST'])
def clear_logs():
    global log_file
    try:
        with open(log_file, 'w') as f:
            f.write("")  # Clear the file
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

@app.route('/clear_cache', methods=['POST'])
def clear_cache():
    try:
        # Create response with cache-control headers to prevent caching
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

@app.route('/')
def index():
    directory = get_directory()
    range_input = get_range_input()
    mode_input = get_mode_input()
    quantity_input = get_quantity_input()
    file_list = get_file_list(directory)
    # cal_json_list = get_file_list(os.path.join(json_root_path, "single_sensor", "kinetics"), "*.json")
    cal_json_list = get_file_list(os.path.join(json_root_path, "kinetics"), "*.json")
    clear_logs()
    response = make_response(render_template('index.html', 
                         title="Easy OKAPI",
                         directory= os.path.abspath(directory),
                         range_input=range_input,
                         mode_input=mode_input,
                         quantity_input=quantity_input,
                         file_list=file_list,
                         cal_json_list=cal_json_list,
                         delimiter=delimiter,
                         production_mode= PRODUCTION_MODE))
    # response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

def delayed_termination():
    """Wait a moment before terminating to allow the response to complete"""
    time.sleep(5)  # Give the browser time to load the goodbye page
    if PRODUCTION_MODE:
        # In production, we need to kill the entire process group
        if platform.system() == 'Windows':
            os.kill(os.getpid(), signal.SIGTERM)
        else:
            os.killpg(os.getpgid(os.getpid()), signal.SIGTERM)
    else:
        # In development, use the Werkzeug shutdown mechanism
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()

@app.route('/shutdown', methods=['POST'])
def shutdown():
    # Start termination after a short delay
    threading.Thread(target=delayed_termination).start()
    data = request.get_json()
    mode = data.get('mode', 'light')
    # Redirect to goodbye page immediately
    return render_template('goodbye.html', production_mode=PRODUCTION_MODE, mode=mode)

# @app.route('/goodbye')
# def goodbye():
#     return render_template('goodbye.html', production_mode=PRODUCTION_MODE)

@app.route('/browse', methods=['POST'])
def browse():
    new_path = request.form['path']
    if browse_directory(new_path):
        file_list = get_file_list(get_directory())
        return jsonify({'status': 'success', 'path': new_path, 'files': file_list})
    return jsonify({'status': 'error', 'message': 'Invalid directory'})

@app.route('/browse_export', methods=['GET'])
def browse_export():
    # Get the path from the query parameter
    path = request.args.get('path')
    if not path:
        return jsonify({'exists': False, 'error': 'No path provided'}), 400
    # Check if the path exists on the server
    exists = os.path.exists(path)
    return jsonify({'exists': exists})

@app.route('/get_parents', methods=['GET'])
def get_parents():
    current_dir = get_directory()
    parent_dir = get_parent_directory(current_dir)
    return jsonify({'parent': parent_dir})

@app.route('/get_children', methods=['GET'])
def get_children():
    current_dir = get_directory()
    child_dirs = get_child_directories(current_dir)
    return jsonify({'children': child_dirs})

@app.route('/get_json_cal', methods=['GET'])
def get_json_cal():
    mode = request.args.get('mode')
    is_multi_sources = request.args.get('isMultiSource', 'false').lower() == 'true'
    num_sources = int(request.args.get('numSources', 1))
    # if is_multi_sources:
    #     json_path = os.path.join(json_root_path, f"{num_sources}_sensors", mode)
    # else:
    # json_path = os.path.join(json_root_path, 'single_sensor', mode)
    json_path = os.path.join(json_root_path, mode)
    # print("The json path is ", json_path)
    if os.path.exists(json_path):
        json_files = get_file_list(json_path, "*.json")
        print("The json files are ", json_files)

        return jsonify({'status': 'success', 'files': json_files})
    return jsonify({'status': 'error', 'message': "Invalid directory"})

# Region 2: USED by navigation.js
@app.route('/get_json_content', methods=['GET'])
def get_json_content():
    selected_json = request.args.get('json_name')
    mode = request.args.get('mode')
    is_multi_source = request.args.get('isMultiSource', 'false').lower() == 'true'
    num_sources = int(request.args.get('numSources', 1))
    # if is_multi_source:
    #     json_path = os.path.join(os.path.join(json_root_path, f"{num_sources}_sensors"), mode, selected_json)
    # else:
    json_path = os.path.join(os.path.join(json_root_path, mode), selected_json)
    print("print the json path ", json_path)
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            data = json.load(f)
        print("print the json data", data)
        return jsonify({'status': 'success', 'json': data, 'path': json_path})
    return jsonify({'status': 'error', 'message': 'Error in reading the json file'})

@app.route('/get_headers', methods=['GET'])
def get_csv_headers():
    read_file = request.args.get('file')
    
    # Basic validation
    if not read_file:
        return jsonify({'headers': [], 'error': 'No file path provided'}), 400
    
    if not os.path.exists(read_file):
        return jsonify({'headers': [], 'error': 'File not found'}), 404
    
    if not os.path.isfile(read_file):
        return jsonify({'headers': [], 'error': 'Path is not a file'}), 400

    try:
        # Attempt to read only headers, skip comment lines starting with #
        df = pd.read_csv(read_file, nrows=0, comment='#')
        headers = df.columns.tolist()
        return jsonify({'headers': headers})
    
    except pd.errors.EmptyDataError:
        return jsonify({'headers': [], 'error': 'CSV file is empty'}), 200
    
    except pd.errors.ParserError as e:
        return jsonify({'headers': [], 'error': f'Invalid CSV format: {str(e)}'}), 200
    
    except PermissionError:
        return jsonify({'headers': [], 'error': 'Permission denied: Cannot read the file'}), 403
    
    except OSError as e:
        return jsonify({'headers': [], 'error': f'File system error: {str(e)}'}), 500
    
    except Exception as e:
        # Catch any unexpected errors (log this in production)
        return jsonify({'headers': [], 'error': 'An unexpected error occurred while reading the file'}), 500

@app.route("/api/current_output", methods=["GET"])
def api_current_output():
    try:
        # adjust this to the actual location of the "log" folder if needed
        marker_path = os.path.join(script_dir, "log", "current_output.txt")

        if not os.path.isfile(marker_path):
            return jsonify({"exists": False, "message": "marker not found"}), 404

        with open(marker_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            return jsonify({"exists": False, "message": "marker empty"}), 204

        # normalize path (handles Windows backslashes and POSIX slashes)
        full_path = os.path.normpath(content)
        dirpath, filename = os.path.split(full_path)

        # include a directory string that ends with the OS-specific separator
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

# Region 3: USED by hid-logging.js
@app.route('/run_script', methods=['POST'])
def run_script():
    global process, monitor_thread
    
    os_name = platform.system().lower()
    
    if process and process.poll() is None:
        return jsonify({'status': 'failure', 'message': 'A script is already running'})
    
    if not request.is_json:
        return jsonify({'status': 'failure', 'message': 'Request must be JSON'}), 400
    
    data = request.get_json()
    base_dir = data.get('base_dir', 'data')
    base_name = data.get('base_name', 'colorimeter_data')
    timeout_sec = data.get('timeout_sec')
    interval_sec = data.get('interval_sec')
    print("Interval seconds is ", interval_sec)
    try:
        pybadge = connect_to_device()
        print(f"Connected to PyBadge at {pybadge.port}")
        
        # Prepare commands and their respective acks
        commands = [
            "1\n",
            f"TIMEOUT:{float(timeout_sec) if timeout_sec is not None else -1}\n",
            f"INTERVAL:{float(interval_sec) if interval_sec is not None else -1}\n"
        ]
        expected_acks = ["ACK_START", "ACK_TIMEOUT", "ACK_INTERVAL"]
        error_acks = ["ERR_START", "ERR_TIMEOUT", "ERR_INTERVAL"]
        
        # Send all commands and wait for acks
        success, error_msg = send_command_and_wait_ack(pybadge, commands, expected_acks, error_acks)
        if not success:
            pybadge.close()
            return jsonify({'status': 'failure', 'message': error_msg})
        
        if "window" in os_name:
            venv_python = os.path.join(script_dir, 'venv', 'Scripts', 'python.exe')
            script_path = os.path.join(script_dir, 'log_hid_data_pyusb.py')
            cmd = [venv_python, script_path, '--base-dir', base_dir, '--base-name', base_name]
        else:
            script_path = os.path.join(script_dir, 'log_hid_data.py')
            cmd = ['sudo', 'python3', script_path, '--base-dir', base_dir, '--base-name', base_name]
        
        with open(log_file, 'a') as f:
            process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True, start_new_session=True)    
            try:
                process.wait(timeout=1)
                error = check_log_for_errors(log_file)
                if error:
                    process = None
                    clear_logs()
                    if error == "device_not_found":
                        print("Device not found in log, returning error")
                        return jsonify({'status': 'device_not_found', 'message': 'PyBadge device not connected. Please connect the device and try again.'})
                    elif error == "input_endpoint_error":
                        return jsonify({'status': 'failure', 'message': 'Failed to find input endpoint. Please check the device connection.'})
                return jsonify({'status': 'success', 'message': 'Script is still running'})
            except subprocess.TimeoutExpired:
                return jsonify({'status': 'success', 'message': 'Script is still running'})
                
    except Exception as e:
        process = None
        if 'pybadge' in locals():
            pybadge.close()
        return jsonify({'status': 'failure', 'message': f'Failed to start script: {str(e)}'})

@app.route('/check_status', methods=['GET'])
def check_status():
    """Endpoint to check process status and detect runtime errors"""
    global process
    
    if process is None:
        return jsonify({'status': 'not_running', 'message': 'No process running'})
    
    # First check for errors in log
    error = check_log_for_errors(log_file)
    if error:
        process = None
        clear_logs()
        if error == "device_not_found":
            return jsonify({'status': 'device_not_found', 'message': 'PyBadge device not connected during runtime.'})
        elif error == "input_endpoint_error":
            return jsonify({'status': 'failure', 'message': 'Input endpoint error detected during runtime.'})
    
    # Then check process status
    if process.poll() is None:
        return jsonify({'status': 'running', 'message': 'Script is running'})
    else:
        # Process has finished - check one final time for errors
        error = check_log_for_errors(log_file)
        process = None
        if error:
            if error == "device_not_found":
                return jsonify({'status': 'device_not_found', 'message': 'PyBadge device was not found.'})
            elif error == "input_endpoint_error":
                return jsonify({'status': 'failure', 'message': 'Failed to find input endpoint.'})
        return jsonify({'status': 'success', 'message': 'Script still running, waiting for device to send next report'})
    
@app.route('/terminate_script', methods=['POST'])
def terminate_script():
    global process
    
    if process is None or process.poll() is not None:
        return jsonify({'status': 'failure', 'message': 'No process running'})

    try:
        pybadge = connect_to_device()
        print(f"Connected to PyBadge at {pybadge.port}")

        # Send stop command using helper function
        success, error_msg = send_command_and_wait_ack(pybadge, ["0\n"], ["ACK_STOP"], ["ERR_STOP"])
        pybadge.close()  # Close serial connection after sending stop command
        if not success:
            return jsonify({'status': 'failure', 'message': error_msg})
        
        # Terminate the running process
        os_name = platform.system().lower()
        if "window" in os_name:
            process.terminate()
            try:
                process.wait(timeout=3)
                process = None
                return jsonify({'status': 'success'})
            except subprocess.TimeoutExpired:
                process.kill()
                process = None
                return jsonify({'status': 'success'})
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=3)
                process = None
                return jsonify({'status': 'success'})
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process = None
                return jsonify({'status': 'success'})
                
    except Exception as e:
        if 'pybadge' in locals():
            pybadge.close()
        return jsonify({'status': 'failure', 'message': f'Error terminating process: {str(e)}'})

@app.route('/get_logs', methods=['GET'])
def get_logs():
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            logs = f.read()
        return jsonify({'status': 'success', 'logs': logs})
    return jsonify({'status': 'success', 'logs': 'No logs available'})

# Region 4: USED by data_handling.js
@app.route('/edit_file', methods=['POST'])
def edit_file():
    global process
    try:
        # Check if script is running
        if process and process.poll() is None:
            return jsonify({
                'status': 'error',
                'message': 'Cannot edit files while the data collection process is running'
            }), HTTPStatus.LOCKED

        # Extract request data
        file_name = request.form.get('filename')
        new_file_name = request.form.get('new_filename', file_name)  # Default to original name if not provided
        path = request.form.get('path') if request.form.get('path') else get_directory()
        content = request.form.get('content')
        calibrate_mode = request.form.get('calibrate_mode')

        # Input validation
        if not file_name or not content:
            return jsonify({
                'status': 'error',
                'message': 'Filename and content are required'
            }), HTTPStatus.BAD_REQUEST

        # Validate file extension
        if not (new_file_name.endswith('.csv') or new_file_name.endswith('.json')):
            return jsonify({
                'status': 'error',
                'message': 'New file name must end with .csv or .json'
            }), HTTPStatus.BAD_REQUEST

        # Construct file paths
        file_path = os.path.join(path, file_name)
        new_file_path = os.path.join(path, new_file_name)
        print(f"Editing file: {file_path} to {new_file_path} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S %z')}")

        # Validate file path to prevent directory traversal
        if '..' in os.path.normpath(file_path) or '..' in os.path.normpath(new_file_path):
            return jsonify({
                'status': 'error',
                'message': 'Invalid file path'
            }), HTTPStatus.BAD_REQUEST

        # Check if original file exists
        if not os.path.exists(file_path):
            return jsonify({
                'status': 'error',
                'message': f'File {file_name} not found'
            }), HTTPStatus.NOT_FOUND

        # Check if new file name already exists (unless it's the same file)
        if file_name != new_file_name and os.path.exists(new_file_path):
            return jsonify({
                'status': 'error',
                'message': f'File {new_file_name} already exists'
            }), HTTPStatus.CONFLICT

        # Validate content based on file extension
        if new_file_name.endswith('.json'):
            try:
                # Validate JSON format
                json.loads(content)
            except json.JSONDecodeError as e:
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid JSON format: {str(e)}'
                }), HTTPStatus.BAD_REQUEST
        else:  # CSV validation
            pattern_sets = [
                {
                    'header': r"^Concentration,maxRate,Slope,Sat,TimeToSat$",
                    'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+\.\d+),(NONE|\d+|\d+\.\d*)$",
                    'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
                    'error': 'Invalid format (Kinetics calibration). Header must be: Concentration,maxRate,Slope,Sat,Time To Sat. Metadata must include Measurement, MeasUnit, TimeUnit, and MeasMode.'
                },
                {
                    'header': r"^Concentration,Value,TimePoint$",
                    'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d*)$",
                    'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
                    'error': 'Invalid format (Point calibration). Header must be: Concentration,Value,TimePoint. Metadata must include Measurement, MeasUnit, TimeUnit and MeasMode.'
                },
                {
                    'header_test': is_multi_value_timeseries_csv_header,
                    'data': r'^\s*\d+(?:\.\d{1,2})?\s*(?:(?:,\s*)?(?:-?\d+(?:\.\d{1,3})?|OVFL|NONE)?\s*)*$',
                    'meta': ["Measurement", "Unit", "Concentration"],
                    'error': 'Invalid format (Pattern 4). Header must be: Timestamp,Value:1,Value:2,... Metadata must include Measurement, Unit, and Concentration.'
                }
            ]

            lines = content.strip().split('\n')
            if not lines:
                return jsonify({
                    'status': 'error',
                    'message': 'Content cannot be empty'
                }), HTTPStatus.BAD_REQUEST

            # --- Separate metadata and data lines ---
            metadata_lines = [line.strip() for line in lines if line.strip().startswith('#')]
            data_lines = [line.strip() for line in lines if not line.strip().startswith('#')]

            if not data_lines:
                return jsonify({
                    'status': 'error',
                    'message': 'CSV must contain at least a header row after metadata'
                }), HTTPStatus.BAD_REQUEST

            # --- Detect header pattern ---
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
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid CSV header. Supported formats:\n'
                            '1. Concentration,maxRate,Slope,Sat,TimeToSat\n'
                            '2. Concentration,Value,TimePoint\n'
                            '3. Timestamp,Value:1,Value:2,...\n'
                }), 400

            # --- Validate metadata for this pattern ---
            required_meta = matched_pattern.get("meta", [])
            if required_meta:
                meta_dict = {}
                for line in metadata_lines:
                    if ":" in line:
                        key, value = line.lstrip("#").split(":", 1)
                        meta_dict[key.strip()] = value.strip()

                missing_meta = [m for m in required_meta if m not in meta_dict]
                if missing_meta:
                    return jsonify({
                        'status': 'error',
                        'message': f'Missing metadata fields: {", ".join(missing_meta)}'
                    }), HTTPStatus.BAD_REQUEST

            # --- Validate data rows ---
            for i, line in enumerate(data_lines[1:], 2):
                if not re.match(matched_pattern['data'], line):
                    return jsonify({
                        'status': 'error',
                        'message': f'Invalid data in row {i} for the detected format.'
                    }), HTTPStatus.BAD_REQUEST

        # Write the new content
        try:
            lock_path = new_file_path + '.lock'
            lock = FileLock(lock_path, timeout=0)

            try:
                lock.acquire()
                try:
                    if new_file_name.endswith('.json'):
                        # Load the original content
                        parsed_json = json.loads(content)

                        # Replace all empty values with "NONE"
                        cleaned_json = replace_empty(parsed_json)

                        # Pretty-print to the new file
                        with open(new_file_path, 'w', encoding='utf-8') as f:
                            json.dump(cleaned_json, f, indent=2, ensure_ascii=False)
                    else:
                        with open(new_file_path, 'w') as f:
                            f.write(content)
                        if calibrate_mode:
                            sort_csv_file(new_file_path, calibrate_mode)
                    f.close()
                finally:
                    # Force cleanup even if exception
                    if os.path.exists(lock_path):
                        try:
                            os.unlink(lock_path)
                        except:
                            pass
            except Timeout:
                    return jsonify({
                        'status': 'error',
                        'message': 'Another save is in progress or previous save crashed'
                    }), 423   # 423 = Locked
            finally:
                lock.release()
                
            if file_name != new_file_name:
                os.remove(file_path)  # Remove old file if renamed
            return jsonify({
                'status': 'success',
                'message': f'File {file_name} updated successfully' + (f' and renamed to {new_file_name}' if file_name != new_file_name else '')
            }), HTTPStatus.OK
        except PermissionError as e:
            return jsonify({
                'status': 'error',
                'message': f'Permission denied while writing {new_file_name}: {str(e)}'
            }), HTTPStatus.FORBIDDEN
        except OSError as e:
            if e.errno == 16:  # EBUSY: Resource busy
                return jsonify({
                    'status': 'error',
                    'message': f'File {new_file_name} is currently in use by another process'
                }), HTTPStatus.LOCKED
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Failed to write {new_file_name}: {str(e)}'
                }), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        print(f"Unexpected error in edit_file: {str(e)} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S %z')}")
        return jsonify({
            'status': 'error',
            'message': 'An unexpected error occurred while saving the file'
        }), HTTPStatus.INTERNAL_SERVER_ERROR
          
@app.route('/delete_file', methods=['POST'])
def delete_file():
    try:
        # Check if script is running
        if process and process.poll() is None:
            return jsonify({
                'status': 'error',
                'message': 'Cannot delete files while the data collection process is running'
            }), HTTPStatus.LOCKED

        file_name = request.form.get('filename')
        tabletype = request.form.get('tabletype')
        mode = request.form.get('mode')
        path = request.form.get('path') if request.form.get('path') else get_directory()
        is_multi_source = request.form.get('isMultiSource', 'false').lower() == 'true'
        num_sources = int(request.form.get('numSources', 1))

        # Input validation
        if not file_name or not tabletype:
            return jsonify({
                'status': 'error',
                'message': 'Filename and tabletype are required'
            }), HTTPStatus.BAD_REQUEST

        # Construct file path based on tabletype
        if tabletype == '#json-table':
            if not mode:
                return jsonify({
                    'status': 'error',
                    'message': 'Mode is required for JSON table type'
                }), HTTPStatus.BAD_REQUEST
            # if is_multi_source:
            #     json_path = os.path.join(json_root_path, f"{num_sources}_sensors", mode)
            # else:
            #     json_path = os.path.join(json_root_path, "single_sensor", mode)
            json_path = os.path.join(json_root_path, mode)
            file_path = os.path.join(json_path, file_name)
            print(f"JSON file path is {file_path}")
        else:
            file_path = os.path.join(path, file_name)
            print(f"CSV file path is {file_path}")

        # Validate file path to prevent directory traversal
        if '..' in os.path.normpath(file_path):
            return jsonify({
                'status': 'error',
                'message': 'Invalid file path'
            }), HTTPStatus.BAD_REQUEST

        # Check if file exists
        if not os.path.exists(file_path):
            return jsonify({
                'status': 'error',
                'message': f'File {file_name} not found'
            }), HTTPStatus.NOT_FOUND

        # Attempt to delete the file
        try:
            os.remove(file_path)
            return jsonify({
                'status': 'success',
                'message': f'File {file_name} deleted successfully'
            }), HTTPStatus.OK
        except PermissionError as e:
            return jsonify({
                'status': 'error',
                'message': f'Permission denied while deleting {file_name}: {str(e)}'
            }), HTTPStatus.FORBIDDEN
        except OSError as e:
            if e.errno == 16:  # EBUSY: Resource busy
                return jsonify({
                    'status': 'error',
                    'message': f'File {file_name} is currently in use by another process'
                }), HTTPStatus.LOCKED
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Failed to delete {file_name}: {str(e)}'
                }), HTTPStatus.INTERNAL_SERVER_ERROR

    except Exception as e:
        print(f"Unexpected error in delete_file: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An unexpected error occurred while deleting the file'
        }), HTTPStatus.INTERNAL_SERVER_ERROR
    
@app.route('/copy_file', methods=['POST'])
def copy_file():
    try:
        # Prevent copy during running process
        if process and process.poll() is None:
            return jsonify({
                'status': 'error',
                'message': 'Cannot copy files while the data collection process is running'
            }), HTTPStatus.LOCKED

        file_name = request.form.get('filename')
        mode = request.form.get('mode')
        tabletype = request.form.get('tabletype')
        path = request.form.get('path') if request.form.get('path') else get_directory()
        is_multi_source = request.form.get('isMultiSource', 'false').lower() == 'true'
        num_sources = int(request.form.get('numSources', 1))
        # Input validation
        if not file_name or not tabletype:
            return jsonify({
                'status': 'error',
                'message': 'Filename and tabletype are required'
            }), HTTPStatus.BAD_REQUEST

        # Construct source file path
        if tabletype == '#json-table':
            if not mode:
                return jsonify({
                    'status': 'error',
                    'message': 'Mode is required for JSON table type'
                }), HTTPStatus.BAD_REQUEST
            # if is_multi_source:
            #     src_dir = os.path.join(json_root_path, f"{num_sources}_sensors", mode)
            # else:
            #     src_dir = os.path.join(json_root_path, "single_sensor", mode)
            src_dir = os.path.join(json_root_path, mode)
        else:
            src_dir = path

        src_path = os.path.join(src_dir, file_name)

        # Validate file path
        if '..' in os.path.normpath(src_path):
            return jsonify({
                'status': 'error',
                'message': 'Invalid file path'
            }), HTTPStatus.BAD_REQUEST

        if not os.path.exists(src_path):
            return jsonify({
                'status': 'error',
                'message': f'Source file {file_name} not found'
            }), HTTPStatus.NOT_FOUND

        # Generate new filename using helper
        dst_path = get_next_filename(".json", src_dir, Path(file_name).stem) if tabletype == '#json-table' else get_next_filename(".csv", src_dir, Path(file_name).stem)

        try:
            shutil.copy2(src_path, dst_path)  # preserve metadata
            return jsonify({
                'status': 'success',
                'message': f'File copied to {dst_path}',
                'new_filename': dst_path
            }), HTTPStatus.OK
        except PermissionError as e:
            return jsonify({
                'status': 'error',
                'message': f'Permission denied while copying {file_name}: {str(e)}'
            }), HTTPStatus.FORBIDDEN
        except OSError as e:
            return jsonify({
                'status': 'error',
                'message': f'Failed to copy {file_name}: {str(e)}'
            }), HTTPStatus.INTERNAL_SERVER_ERROR

    except Exception as e:
        print(f"Unexpected error in copy_file: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An unexpected error occurred while copying the file'
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route('/merge_csv', methods=['POST'])
def merge_csv():
    try:
        # Prevent merge during running process
        if process and process.poll() is None:
            return jsonify({
                'status': 'error',
                'message': 'Cannot merge files while the data collection process is running'
            }), HTTPStatus.LOCKED

        file1 = request.form.get('file1')
        file2 = request.form.get('file2')
        output_name = request.form.get('output_name')
        path = request.form.get('path') if request.form.get('path') else get_directory()

        if not file1 or not file2 or not output_name:
            return jsonify({
                'status': 'error',
                'message': 'Both files and output name are required'
            }), HTTPStatus.BAD_REQUEST

        if not output_name.endswith('.csv'):
            output_name += '.csv'

        file1_path = os.path.join(path, file1)
        file2_path = os.path.join(path, file2)
        output_path = os.path.join(path, output_name)

        # Validate file path to prevent directory traversal
        if '..' in os.path.normpath(file1_path) or '..' in os.path.normpath(file2_path) or '..' in os.path.normpath(output_path):
            return jsonify({
                'status': 'error',
                'message': 'Invalid file path'
            }), HTTPStatus.BAD_REQUEST

        success, result = merge_csv_files(file1_path, file2_path, output_path)
        if success:
            return jsonify({
                'status': 'success',
                'message': f'Files merged successfully into {result}'
            }), HTTPStatus.OK
        else:
            return jsonify({
                'status': 'error',
                'message': result
            }), HTTPStatus.INTERNAL_SERVER_ERROR

    except Exception as e:
        print(f"Unexpected error in merge_csv: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An unexpected error occurred while merging the files'
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route('/remove_columns', methods=['POST'])
def remove_columns():
    try:
        data = request.json
        filename = data.get('filename')
        path = data.get('path')
        columns = data.get('columns', [])
        
        if not filename or not path:
            return jsonify({'status': 'failure', 'message': 'Filename and path are required'}), 400
            
        file_path = os.path.join(path, filename)
        
        # Security check
        if '..' in os.path.normpath(file_path):
             return jsonify({'status': 'failure', 'message': 'Invalid file path'}), 400
             
        success, message = remove_csv_columns(file_path, columns)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message
            })
        else:
            return jsonify({'status': 'failure', 'message': message}), 400
            
    except Exception as e:
        print(f"Error in remove_columns: {str(e)}")
        return jsonify({'status': 'failure', 'message': str(e)}), 500

@app.route('/get_num_sources', methods=['GET'])
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

                    # This is the first real data line → probably header
                    if is_multi_value_timeseries_csv_header(line):
                        columns = [c.strip() for c in line.split(',')]
                        value_count = sum(1 for c in columns[1:] if c.startswith('Value:'))
                        if value_count > 0:
                            possible_counts.add(value_count)
                    break  # We only care about the header

        except Exception:
            continue  # skip broken files silently

    return jsonify({
        'status': 'success',
        'num_sources': sorted(list(possible_counts))
    })

@app.route('/get_data', methods=['GET'])
def get_data():
    selected_file = request.args.get('file')
    data = get_dynamic_data(selected_file)
    return jsonify(data)

@app.route('/get_file_content', methods=['GET'])
def get_file_content():
    try:
        file_name = request.args.get('file')
        path = request.args.get('path') if request.args.get('path') else get_directory()
        if not file_name:
            return jsonify({
                'status': 'error',
                'message': 'Filename is required'
            }), HTTPStatus.BAD_REQUEST

        file_path = os.path.join(path, file_name)
        print(f"Fetching raw content for editing from file: {file_path} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S %z')}")

        # Validate file path to prevent directory traversal
        if '..' in os.path.normpath(file_path):
            return jsonify({
                'status': 'error',
                'message': 'Invalid file path'
            }), HTTPStatus.BAD_REQUEST

        # Check if file exists (reuse get_dynamic_data for existence check)
        result = get_dynamic_data(file_path)
        if 'error' in result and result['error']:
            return jsonify({
                'status': 'error',
                'message': result['error']
            }), HTTPStatus.NOT_FOUND

        # Check if the subprocess is running
        if process and process.poll() is None:
            if path.startswith(os.path.abspath(os.path.join(script_dir, 'data'))):
                return jsonify({
                    'status': 'error',
                    'message': f'File {file_name} may be in use by the data collection process'
                }), HTTPStatus.LOCKED

        # Ensure the file is either CSV or JSON
        if not (file_name.lower().endswith('.csv') or file_name.lower().endswith('.json')):
            return jsonify({
                'status': 'error',
                'message': 'Only CSV and JSON files are supported'
            }), HTTPStatus.BAD_REQUEST

        # Read raw content
        try:
            with open(file_path, 'r') as f:
                content = f.read()

            # For JSON files, validate the content
            if file_name.lower().endswith('.json'):
                try:
                    json.loads(content)
                except json.JSONDecodeError as e:
                    return jsonify({
                        'status': 'error',
                        'message': f'Invalid JSON file format: {str(e)}'
                    }), HTTPStatus.BAD_REQUEST

            return jsonify({
                'status': 'success',
                'content': content
            })
        except PermissionError as e:
            return jsonify({
                'status': 'error',
                'message': f'Permission denied while accessing {file_name}: {str(e)}'
            }), HTTPStatus.FORBIDDEN
    except Exception as e:
        print(f"Unexpected error in get_file_content: {str(e)} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S %z')}")
        return jsonify({
            'status': 'error',
            'message': 'An unexpected error occurred while fetching file content'
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route('/export_data', methods=['POST'])
def export_data():
    data = request.get_json()
    entries = data.get('entries')  # If present, batch mode
    is_batch = bool(entries)

    # Extract common fields
    file_name = data.get('save_file', 'result')
    save_dir = data.get('save_dir')
    measurement = data.get('meas', 'NONE')
    meas_unit = data.get('measUnit', 'NONE')
    meas_mode = data.get('measMode')
    newFile = data.get('newFile', True)
    time_unit = "minute" if meas_mode == "point" else "minutes"

    try:
        export_path = os.path.abspath(os.path.expanduser(save_dir))
        os.makedirs(export_path, exist_ok=True)
        full_path = os.path.join(export_path, file_name + "_" + meas_mode + ".csv")

        file_exists = os.path.isfile(full_path)

        # Check metadata consistency if file exists
        if file_exists:
            meta_dict = get_dynamic_data(full_path)['metadata']
            if not is_metadata_consistent(meta_dict, measurement, meas_unit, time_unit, meas_mode):
                return jsonify({"status": "error", "message": "Metadata inconsistency"})

        with open(full_path, "a", newline='') as f:
            writer = csv.writer(f)

            # Write metadata and headers if new file
            if not file_exists and newFile:
                write_metadata(f, measurement, meas_unit, time_unit, meas_mode)
                write_headers(writer, meas_mode)
            # elif file_exists:
            #     f.write(content.rstrip('\n') + '\n')

            # Prepare entries (handle single as list of one)
            if is_batch:
                entries = [extract_single_entry(entry, meas_mode) for entry in entries]
            else:
                entries = [extract_single_entry(data, meas_mode)]

            print("Entries are ", entries)
            # Append all entries
            for entry in entries:
                writer.writerow(entry)

        sort_csv_file(full_path, meas_mode)

        return jsonify({"status": "success", "message": f"Data exported at {full_path}"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/export_cal_coefs', methods=['POST'])
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
    # if is_multi_source:
    #     export_path = os.path.join(json_root_path, f"{num_sources}_sources", cal_mode)
    # else:
    #     export_path = os.path.join(json_root_path, "single_sensor", cal_mode)
    export_path = os.path.join(json_root_path, cal_mode)
    print("received coef_content:", coef_content)
    try: 
        export_path = os.getenv(export_path, export_path)
        export_path = os.path.abspath(os.path.expanduser(export_path))
        print(f"export path is {export_path}")
        # Ensure directory exists
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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the Flask app with a specified port and alias.')
    parser.add_argument('--port', type=int, default=5099, help='Port to run the Flask app on (default: 5099)')
    parser.add_argument('--alias', type=str, default='easyokapi.com', help='Optional domain alias (e.g., mydomain.com)')
    args = parser.parse_args()

    host = '127.0.0.1'
    port = args.port
    alias = args.alias or host

    if alias and alias != '127.0.0.1':
        ensure_host_mapping(alias)

    # Launch browser with alias
    browser_thread = threading.Thread(target=open_browser, args=(alias, port), daemon=True)
    browser_thread.start()

    atexit.register(cleanup, process, log_file, args)

    try:
        app.run(debug=True, host=host, port=port)
    except Exception as e:
        print(f"Failed to start Flask server: {e}")
        sys.exit(1)