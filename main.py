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

sys.path.append('src')
from file_path import get_directory, browse_directory, get_parent_directory, get_child_directories
from range import get_range_input
from mode import get_mode_input
from measure import get_dynamic_data
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
                         delimiter=delimiter))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.route('/browse', methods=['POST'])
def browse():
    new_path = request.form['path']
    if browse_directory(new_path):
        file_list = get_file_list(get_directory())
        return jsonify({'status': 'success', 'path': new_path, 'files': file_list})
    return jsonify({'status': 'error', 'message': 'Invalid directory'})

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
    
    if "window" in os_name:
        cmd = ['python', 'log_hid_data_pyusb.py', '--base-dir', base_dir, '--base-name', base_name]
    else:
        cmd = ['sudo', 'python3', 'log_hid_data.py', '--base-dir', base_dir, '--base-name', base_name]
    
    try:
        with open(log_file, 'a') as f:
            process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            
            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=lambda: monitor_process(process, log_file),
                daemon=True
            )
            monitor_thread.start()
            
            # Initial check (like your original code)
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
        if "window" in os_name:
            # On Windows, use terminate() or kill() for the process
            process.terminate()  # Try graceful termination
            try:
                process.wait(timeout=5)
                process = None
                return jsonify({'status': 'success'})
            except subprocess.TimeoutExpired:
                process.kill()  # Force kill if it doesn't terminate
                process = None
                return jsonify({'status': 'success'})
        else:
            # On Unix-like systems, use os.killpg for process group
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

@app.route('/get_logs', methods=['GET'])
def get_logs():
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            logs = f.read()
        return jsonify({'status': 'success', 'logs': logs})
    return jsonify({'status': 'success', 'logs': 'No logs available'})

# Region 4: USED by data_handling.js
@app.route('/get_data', methods=['GET'])
def get_data():
    selected_file = request.args.get('file')
    data = get_dynamic_data(selected_file)
    return jsonify(data)

@app.route('/export_data', methods=['POST'])
def export_data(mode="kinetics"):
    data = request.get_json()
    print(f"data is {data}")
    file_name = data.get('save_file', 'result')
    save_dir = data.get('save_dir')
    measurement = data.get('meas')
    vmax = data.get('vmax', 'NONE')
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
                    writer.writerow(['Measurement', 'Concentration', 'Vmax', 'Slope', 'Sat', 'Time To Sat', 'MeasUnit', 'TimeUnit', 'BlankType', 'MeasMode'])
                else:
                    writer.writerow(['Measurement', 'Concentration', 'Value', 'MeasUnit', 'TimePoint', 'TimeUnit', 'BlankType', 'MeasMode'])
            if check_row_exist(full_path, concentration, blankT, time_point, meas_mode):
                if meas_mode == "kinetics":
                    message = f"Error: This {concentration} nM/l concentration value with this blank Type \"{blankT}\" already exist in {full_path}"
                elif meas_mode == "point":
                    message = f"Error: This {concentration} nM/l concentration value with this blank Type \"{blankT}\" at this {time_point} already exist in {full_path}"
                status = "error"
            else: 
                if meas_mode == "kinetics":
                    writer.writerow([measurement, concentration, vmax, slope, sat, time_to_sat, meas_unit, time_unit, blankT, meas_mode])
                else:
                    writer.writerow([measurement, concentration, value, meas_unit, time_point, time_unit, blankT, meas_mode])
                message = f"Data exported at {full_path}"
                status = "success" 
            f.close()

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