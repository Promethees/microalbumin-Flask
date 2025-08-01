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
from filelock import FileLock
import serial.tools.list_ports

sys.path.append('src')
from file_path import get_directory, browse_directory, get_parent_directory, get_child_directories
from range import get_range_input
from mode import get_mode_input
from measure import get_dynamic_data, sort_csv_file
from quantity import get_quantity_input
from file import get_file_list
from get_next_filename import get_next_filename
from script_monitor import check_log_for_errors, monitor_process
from export_data import check_row_exist
from export_cal_json import processJSONCoef, extractAnalysisCoefficients, CustomEncoder
from browser_mgt import open_browser, close_port, is_port_open, cleanup

app = Flask(__name__)
process = None
monitor_thread = None
log_file = "log/script_logs.txt"

os_name = platform.system().lower()
if "window" in os_name:
    delimiter = "\\\\";
else:
    delimiter = "/";

json_root_path = os.path.join(os.getcwd(), "json")
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
    cal_json_list = get_file_list(os.path.join(json_root_path, "kinetics"), "*.json")
    clear_logs()
    response = make_response(render_template('index.html', 
                         title="Easy Sensor Kit",
                         directory= os.path.abspath(directory),
                         range_input=range_input,
                         mode_input=mode_input,
                         quantity_input=quantity_input,
                         file_list=file_list,
                         cal_json_list=cal_json_list,
                         delimiter=delimiter,
                         production_mode= PRODUCTION_MODE))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
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
    # Redirect to goodbye page immediately
    return render_template('goodbye.html', production_mode=PRODUCTION_MODE)

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
    json_path = os.path.join(json_root_path, mode)
    if os.path.exists(json_path):
        json_files = get_file_list(json_path, "*.json")

        return jsonify({'status': 'success', 'files': json_files})
    return jsonify({'status': 'error', 'message': "Invalid directory"})

# Region 2: USED by navigation.js
@app.route('/get_json_content', methods=['GET'])
def get_json_content():
    selected_json = request.args.get('json_name')
    mode = request.args.get('mode')
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
    if os.path.exists(read_file):
        df = pd.read_csv(read_file, nrows=0)
        return jsonify({'headers': df.columns.tolist()}) 
    return jsonify({'headers': [], 'error': "Invalid csv file or file path is wrong"})

# Region 3: USED by hid-logging.js
@app.route('/run_script', methods=['POST'])
def run_script():
    global process, monitor_thread
    
    os_name = platform.system().lower()
    
    # Check if process is already running
    if process and process.poll() is None:
        return jsonify({'status': 'failure', 'message': 'A script is already running'})
    
    if not request.is_json:
        return jsonify({'status': 'failure', 'message': 'Request must be JSON'}), 400
    
    data = request.get_json()
    base_dir = data.get('base_dir', 'data')
    base_name = data.get('base_name', 'colorimeter_data')
    
    try:
        # Connect to PyBadge and send start signal
        pybadge = connect_to_device()
        print(f"Connected to PyBadge at {pybadge.port}")
        
        # Send start signal with newline
        pybadge.write(b'1\n')
        
        # Read acknowledgment with timeout
        start_time = time.time()
        timeout = 5  # seconds
        ack_received = False
        
        while time.time() - start_time < timeout:
            if pybadge.in_waiting:
                response = pybadge.readline().decode('utf-8').strip()
                if response == "ACK_START":
                    ack_received = True
                    break
            time.sleep(0.1)
        
        if not ack_received:
            pybadge.close()
            return jsonify({'status': 'failure', 'message': 'No acknowledgment from PyBadge'})
        
        # Rest of the run_script code...
        if "window" in os_name:
            venv_python = os.path.join('venv', 'Scripts', 'python.exe')
            cmd = [venv_python, 'log_hid_data_pyusb.py', '--base-dir', base_dir, '--base-name', base_name]
        else:
            cmd = ['sudo', 'python3', 'log_hid_data.py', '--base-dir', base_dir, '--base-name', base_name]
        
        with open(log_file, 'a') as f:
            process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            
            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=lambda: monitor_process(process, log_file),
                daemon=True
            )
            monitor_thread.start()
            
            # Initial check
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
        # Send stop signal and wait for acknowledgment
        pybadge = connect_to_device()
        print(f"Connected to PyBadge at {pybadge.port}")

        # Send stop signal with newline
        pybadge.write(b'0\n')
        
        # Read acknowledgment with timeout
        start_time = time.time()
        timeout = 5  # seconds
        ack_received = False
        
        while time.time() - start_time < timeout:
            if pybadge.in_waiting:
                response = pybadge.readline().decode('utf-8').strip()
                if response == "ACK_STOP":
                    ack_received = True
                    break
            time.sleep(0.1)
        
        if not ack_received:
            pybadge.close()
            return jsonify({'status': 'failure', 'message': 'No acknowledgment from PyBadge'})
        
        # Rest of the terminate_script code...
        if "window" in os_name:
            process.terminate()
            try:
                process.wait(timeout=5)
                process = None
                return jsonify({'status': 'success'})
            except subprocess.TimeoutExpired:
                process.kill()
                process = None
                return jsonify({'status': 'success'})
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=5)
                process = None
                return jsonify({'status': 'success'})
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process = None
                return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': f'Error terminating process: {str(e)}'})
    
def connect_to_device(vid = 0x239A, pid = 0x8034):
    """Automatically find and connect to Device"""

    # Find the port
    port = None
    for p in serial.tools.list_ports.comports():
        if p.vid == vid and p.pid == pid:
            port = p.device
            break
    
    if not port:
        raise Exception("Device (Pybadge) not found. Is it connected?")
    
    # Configure and open serial connection
    ser = serial.Serial(
        port=port,
        baudrate=115200,
        timeout=1,
        write_timeout=1
    )
    
    # Wait for connection to establish
    time.sleep(2)
    return ser

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
                    'header': r"^Timestamp,Measurement,Value,Unit,Type,Blanked,Concentration$",
                    'data': r"^\d+\.\d{1,2},[A-Za-z]+,\d+\.\d{1,3},[A-Za-z]+,[A-Za-z]+,[A-Za-z]+,(NONE|\d+)$",
                    'error': 'Invalid format (Pattern 1). Header must be: Timestamp,Measurement,Value,Unit,Type,Blanked,Concentration'
                },
                {
                    'header': r"^Measurement,Concentration,maxRate,Slope,Sat,Time To Sat,MeasUnit,TimeUnit,BlankType,MeasMode$",
                    'data': r"^[A-Za-z]+,(NONE|\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+\.\d+),(NONE|\d+|\d+\.\d*),[A-Za-z]+,[A-Za-z]+,[A-Za-z]+,[A-Za-z]+$",
                    'error': 'Invalid format (Pattern 2). Header must be: Measurement,Concentration,maxRate,Slope,Sat,Time To Sat,MeasUnit,TimeUnit,BlankType,MeasMode'
                },
                {
                    'header': r"^Measurement,Concentration,Value,MeasUnit,TimePoint,TimeUnit,BlankType,MeasMode$",
                    'data': r"^[A-Za-z]+,(NONE|\d+),(NONE|\d+|\d+\.\d+),[A-Za-z]+,(NONE|\d+|\d+\.\d*),[A-Za-z]+,[A-Za-z]+,[A-Za-z]+$",
                    'error': 'Invalid format (Pattern 3). Header must be: Measurement,Concentration,Value,MeasUnit,TimePoint,TimeUnit,BlankType,MeasMode'
                }
            ]

            lines = content.strip().split('\n')
            if not lines:
                return jsonify({
                    'status': 'error',
                    'message': 'Content cannot be empty'
                }), HTTPStatus.BAD_REQUEST

            # Find matching pattern set
            matched_pattern = None
            for pattern in pattern_sets:
                if re.match(pattern['header'], lines[0]):
                    matched_pattern = pattern
                    break

            if not matched_pattern:
                valid_headers = " OR ".join(p['error'].split('Header must be: ')[1] for p in pattern_sets)
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid CSV header. Must match one of: {valid_headers}'
                }), HTTPStatus.BAD_REQUEST

            # Validate data rows with the matched pattern
            for i, line in enumerate(lines[1:], 2):
                if not re.match(matched_pattern['data'], line):
                    return jsonify({
                        'status': 'error',
                        'message': f'Invalid data in row {i} for the detected format.'
                    }), HTTPStatus.BAD_REQUEST

        # Write the new content
        try:
            lock_path = new_file_path + '.lock'
            with FileLock(lock_path):
                if new_file_name.endswith('.json'):
                    # Pretty print JSON with indentation
                    parsed_json = json.loads(content)
                    with open(new_file_path, 'w') as f:
                        json.dump(parsed_json, f, indent=2)
                else:
                    with open(new_file_path, 'w') as f:
                        f.write(content)
                    if calibrate_mode:
                        sort_csv_file(new_file_path, calibrate_mode)
                f.close()
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
            if path.startswith(os.path.abspath(os.path.join(os.getcwd(), 'data'))):
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
def export_data(mode="kinetics"):
    data = request.get_json()
    print(f"data is {data}")
    file_name = data.get('save_file', 'result')
    save_dir = data.get('save_dir')
    measurement = data.get('meas')
    maxrate = data.get('maxrate', 'NONE')
    slope = data.get('slope', 'NONE')
    sat = data.get('sat', 'NONE')
    concentration = data.get('con')
    time_to_sat = data.get('timeSat', 'NONE')
    meas_unit = data.get('measUnit', 'NONE')
    blankT = data.get('blanked')
    time_unit = data.get('timeUnit')
    newFile = data.get('newFile')
    meas_mode = data.get('measMode')
    value = data.get('estValue', 'NONE')
    time_point = data.get('timePoint')
    print("Measurement mode is ", meas_mode)
    try:
        # Ensure the directory path is absolute and normalized
        export_path = os.path.abspath(os.path.expanduser(save_dir))
        print(f"export path is {export_path}")
        # Ensure directory exists
        os.makedirs(export_path, exist_ok=True)
        
        full_path = os.path.join(export_path, file_name + "_" + meas_mode + ".csv")

        # Check if file exists and has headers
        file_exists = os.path.isfile(full_path)
        message = None
        status = None
        if not newFile:
            time.sleep(1)
        with open(full_path, "a", newline='') as f:
            writer = csv.writer(f)
            if not file_exists and newFile:
                if meas_mode == "kinetics":
                    writer.writerow(['Measurement', 'Concentration', 'maxRate', 'Slope', 'Sat', 'Time To Sat', 'MeasUnit', 'TimeUnit', 'BlankType', 'MeasMode'])
                else:
                    writer.writerow(['Measurement', 'Concentration', 'Value', 'MeasUnit', 'TimePoint', 'TimeUnit', 'BlankType', 'MeasMode'])
            if meas_mode == "kinetics":
                writer.writerow([measurement, concentration, maxrate, slope, sat, time_to_sat, meas_unit, 'minutes', blankT, meas_mode])
            else:
                writer.writerow([measurement, concentration, value, meas_unit, time_point, 'minutes', blankT, meas_mode])
            message = f"Data exported at {full_path}"
            status = "success" 
            # Add this line to sort the file after insertion
            f.close()
            sort_csv_file(full_path, meas_mode)

        return jsonify({"status": status, "message": message})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/export_cal_coefs', methods=['POST'])
def export_cal_coefs():
    data = request.get_json()
    print(f"data is {data}")
    fit_type = data.get('fit_type')
    for_meas = data.get('for_meas')
    for_blank_type = data.get('for_blank_type')
    coef_content = data.get('coef_content')
    time = data.get('time')
    time_unit = "minute"
    file_name = data.get('file_name', 'calibrate')
    cal_mode = data.get('cal_mode', "kinetics")
    cal_params = data.get('cal_params')
    thres_val = float(data.get('threshold_val', 0))

    export_path = os.path.join(json_root_path, cal_mode)
    print("received coef_content:", coef_content)
    try: 
        export_path = os.getenv(export_path, export_path)
        export_path = os.path.abspath(os.path.expanduser(export_path))
        print(f"export path is {export_path}")
        # Ensure directory exists
        os.makedirs(export_path, exist_ok=True)

        full_path = get_next_filename(".json", export_path, file_name)

        json_content = processJSONCoef(cal_params, extractAnalysisCoefficients(coef_content, thres_val))
        json_content.update({"fit_type": fit_type, "for_meas": for_meas, "for_blank_type": for_blank_type})

        if (cal_mode == "point"):
            json_content.update({"time": time, "time-unit": time_unit})
        with open(full_path, "w") as f:
            json.dump(json_content, f, cls=CustomEncoder, indent=4)
        return jsonify({"status": "success", "message": f"Data exported to {full_path}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

atexit.register(cleanup)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the Flask app with a specified port.')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the Flask app on (default: 5000)')
    args = parser.parse_args()

    port = args.port
    host = '127.0.0.1'

    # Check if port is in use before starting
    # if is_port_open(host, port):
    #     print(f"Port {port} is in use, attempting to free it...")
    #     close_port(port)

    # Start browser opening in a separate thread
    browser_thread = threading.Thread(target=open_browser, args=(host, port), daemon=True)
    browser_thread.start()

    # Run Flask server in the main thread
    try:
        app.run(debug=True, host='127.0.0.1', port=port)
    except Exception as e:
        print(f"Failed to start Flask server: {e}")
        sys.exit(1)