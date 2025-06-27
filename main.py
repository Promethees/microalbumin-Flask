from flask import Flask, render_template, request, jsonify
import os
import sys
import webbrowser
import argparse
import threading
import time
import socket
import signal 
import platform
import subprocess
import atexit
import csv
import pandas as pd
import json
from typing import List, Dict, Union, Any

from log_hid_data import get_next_filename, parse_arguments
sys.path.append('src')
from file_path import get_directory, browse_directory, get_parent_directory, get_child_directories
from range import get_range_input
from mode import get_mode_input
from measure import get_dynamic_data
from quantity import get_quantity_input
from file import get_file_list

app = Flask(__name__)
process = None
log_file = "log/script_logs.txt"
con_col = 1
blankT_col_kin = 8
blankT_col_pnt = 6
time_point_col = 4

os_name = platform.system().lower()
if "window" in os_name:
    delimiter = "\\"
else:
    delimiter = "/"

json_root_path = os.path.join(os.getcwd(), "json")

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()  # Convert datetime to string
        return super().default(obj)

@app.route('/clear_logs', methods=['POST'])
def clear_logs():
    global log_file
    try:
        with open(log_file, 'w') as f:
            f.write("")  # Clear the file
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

def cleanup():
    global process
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

atexit.register(cleanup)

@app.route('/')
def index():
    directory = get_directory()
    range_input = get_range_input()
    mode_input = get_mode_input()
    quantity_input = get_quantity_input()
    file_list = get_file_list(directory)
    cal_json_list = get_file_list(os.path.join(json_root_path, "kinetics"), "*.json")
    print("reading default cal_json_list from ", os.path.join(os.getcwd(), "kinetics"))
    print(cal_json_list)
    return render_template('index.html', 
                         title="Easy Sensor Kit",
                         directory=directory,
                         range_input=range_input,
                         mode_input=mode_input,
                         quantity_input=quantity_input,
                         file_list=file_list,
                         cal_json_list=cal_json_list)

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

@app.route('/run_script', methods=['POST'])
def run_script():
    os_name = platform.system().lower()
    global process
    if process and process.poll() is None:
        return jsonify({'status': 'failure', 'message': 'A script is already running'})
    if not request.is_json:
        return jsonify({'status': 'failure', 'message': 'Request must be JSON'}), 400
    data = request.get_json()
    base_dir = data.get('base_dir', 'data')
    base_name = data.get('base_name', 'colorimeter_data')
    if "window" in os_name:
        cmd = ['python', 'log_hid_data.py', '--base-dir', base_dir, '--base-name', base_name]
    else:
        cmd = ['sudo', 'python3', 'log_hid_data.py', '--base-dir', base_dir, '--base-name', base_name]
    with open(log_file, 'a') as f:
        process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True, start_new_session=True)

    args = parse_arguments()
    return jsonify({'status': 'success', 'directory': args.base_dir})

@app.route('/terminate_script', methods=['POST'])
def terminate_script():
    global process
    if process is None or process.poll() is not None:
        return jsonify({'status': 'failure', 'message': 'No process running'})
    # Use pgid to terminate the entire process group
    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    try:
        process.wait(timeout=5)
        process = None
        return jsonify({'status': 'success'})
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        process = None
        return jsonify({'status': 'success'})

@app.route('/get_logs', methods=['GET'])
def get_logs():
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            logs = f.read()
        return jsonify({'status': 'success', 'logs': logs})
    return jsonify({'status': 'success', 'logs': 'No logs available'})

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

def processJSONCoef(cal_params: List[str], coefficients: Union[List[float], List[List[float]]]) -> Dict[str, Any]:
    """
    Process analysis parameters and coefficients into a structured JSON object.
    
    Args:
        cal_params: List of parameter names (e.g., ["Vmax", "slope", "sat", "Time To Sat"])
        coefficients: Either:
            - A 1D array [v, v] → Returns {"fit_coef": [v, v]}
            - A 2D array [[v, v], [v, v], ...] → Returns {param1: {"fit_coef": [v, v]}, ...}
    
    Returns:
        A JSON-compatible dictionary with "NONE" replacing None values.
    
    Raises:
        Exception: If inputs are invalid.
    """
    # Validate inputs
    if not isinstance(cal_params, list):
        raise Exception("cal_params must be a list")
    if not isinstance(coefficients, list):
        raise Exception("coefficients must be a list")

    def sanitize_value(v: Any) -> Union[float, str]:
        """Replace None with 'NONE' to avoid JSON issues."""
        return v if v is not None else "NONE"

    # Case 1: coefficients is 1D (e.g., [v, v])
    if all(not isinstance(x, list) for x in coefficients):
        if len(coefficients) < 2:
            raise Exception("1D coefficients must have at least 2 values")
        
        sanitized_coef = [sanitize_value(v) for v in coefficients]
        return {"fit_coef": sanitized_coef}

    # Case 2: coefficients is 2D (e.g., [[v, v], [v, v], ...])
    elif all(isinstance(x, list) for x in coefficients):
        if len(cal_params) != len(coefficients):
            raise Exception("For 2D coefficients, cal_params and coefficients must have the same length")
        
        result = {}
        for param, coef in zip(cal_params, coefficients):
            if len(coef) < 2:
                raise Exception(f"Each coefficient must be a list of at least 2 values (got {len(coef)})")
            
            processed_key = param.lower().replace(" ", "_")
            sanitized_coef = [sanitize_value(v) for v in coef]
            result[processed_key] = {"fit_coef": sanitized_coef}
        return result

    else:
        raise Exception("coefficients must be either [v, v] or [[v, v], [v, v], ...]")

def extractAnalysisCoefficients(
    data: Union[List[Dict[str, Any]], Dict[str, Any]], 
    threshold: float = 0.0  # Default threshold (adjust as needed)
) -> Union[List[Any], List[List[Any]]]:
    """
    Extracts coefficients, setting them to null if rSquared < threshold.
    
    Args:
        data: Single slope object or array of slope objects.
        threshold: Minimum rSquared value to keep coefficients.
    
    Returns:
        - Single object: Coefficients array (with null if filtered).
        - Array: List of coefficients arrays (with null if filtered).
    """
    def process_entry(entry: Dict[str, Any]) -> List[Any]:
        """Process one slope entry: return coefficients or nulls based on rSquared."""
        r_squared = entry.get("rSquared")
        # Convert rSquared to float if it's a string
        if isinstance(r_squared, str):
            try:
                r_squared = float(r_squared)
            except ValueError:
                r_squared = None  # Treat invalid strings as None
        if r_squared is None or (isinstance(r_squared, (float, int)) and r_squared < threshold):
            return [None] * len(entry.get("coefficients", []))
        return entry["coefficients"]
    
    # Case 1: Single object
    if isinstance(data, dict):
        return process_entry(data)
    
    # Case 2: Array of objects
    elif isinstance(data, list):
        return [process_entry(entry) for entry in data]
    
    else:
        raise Exception("Input must be a slope object or array of slope objects")

@app.route('/export_data', methods=['POST'])
def export_data(mode="kinetics"):
    default_path = os.path.join(os.getcwd(), "export_data")
    data = request.get_json()
    print(f"data is {data}")
    file_name = data.get('save_file', 'result')
    export_path = data.get('save_dir' != "", default_path)
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
    print("Measurmenet mode is ", meas_mode)
    try:
        
        # Check if the provided path is an environment variable
        export_path = os.getenv(export_path, export_path)

        # Ensure the directory path is absolute and normalized
        export_path = os.path.abspath(os.path.expanduser(export_path))
        print(f"export path is {export_path}")
        # Ensure directory exists
        os.makedirs(export_path, exist_ok=True)
        
        full_path = os.path.join(export_path, file_name + "_" + meas_mode +".csv")

        # Check if file exists and has headers
        file_exists = os.path.isfile(full_path)
        message = None
        status = None
        if not newFile:
            time.sleep(1)
        with open(full_path, "a", newline='') as f:
            writer = csv.writer(f)
            if not file_exists and newFile:
                if (meas_mode == "kinetics"):
                    writer.writerow(['Measurement', 'Concentration', 'Vmax', 'Slope', 'Sat', 'Time To Sat', 'MeasUnit','TimeUnit', 'BlankType', 'MeasMode'])  # Write header if new file
                else:
                    writer.writerow(['Measurement', 'Concentration', 'Value', 'MeasUnit', 'TimePoint', 'TimeUnit', 'BlankType', 'MeasMode'])
            # writer.writerow([vmax, slope, sat])  # Append data
            if check_row_exist(full_path, concentration, blankT, time_point, meas_mode):
                if (meas_mode == "kinetics"):
                    message = f"Error: This {concentration} nM/l concentration value with this blank Type \"{blankT}\" already exist in {full_path}"
                elif (meas_mode == "point"):
                    message = f"Error: This {concentration} nM/l concentration value with this blank Type \"{blankT}\" at this {time_point} already exist in {full_path}"
                status = "error"
            else: 
                if (meas_mode == "kinetics"):
                    writer.writerow([measurement,concentration,vmax,slope,sat,time_to_sat,meas_unit,time_unit,blankT,meas_mode])
                else:
                    writer.writerow([measurement,concentration,value,meas_unit,time_point,time_unit,blankT,meas_mode])
                message = f"Data exported at {full_path}"
                status = "success" 
            f.close()

        return jsonify({"status": status, "message": message})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

def check_row_exist(full_path, concentration, blankT, timePoint = None, measMode = "kinetics"):
    with open(full_path, mode='r', newline='') as f:
        reader = csv.reader(f)

        for row in reader:
            if (measMode == "kinetics"):
                if row[con_col] == concentration and row[blankT_col_kin] == blankT:
                    return True
            elif (measMode == "point"):
                if row[con_col] == concentration and row[blankT_col_pnt] == blankT and row[time_point_col] == timePoint:
                    return True
    return False

@app.route('/get_data', methods=['GET'])
def get_data():
    selected_file = request.args.get('file')
    data = get_dynamic_data(selected_file)
    return jsonify(data)

@app.route('/get_headers', methods=['GET'])
def get_csv_headers():
    read_file = request.args.get('file')
    if os.path.exists(read_file):
        df = pd.read_csv(read_file, nrows=0)
        return jsonify({'headers': df.columns.tolist()}) 
    return jsonify({'headers': [], 'error': "Invalid csv file or file path is wrong"})

@app.route('/get_json_cal', methods=['GET'])
def get_json_cal():
    mode = request.args.get('mode')
    json_path = os.path.join(json_root_path, mode)
    if os.path.exists(json_path):
        json_files = get_file_list(json_path, "*.json")

        return jsonify({'status': 'success', 'files': json_files})
    return jsonify({'status': 'error', 'message': "Invalid directory"})

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

def is_port_open(host, port):
    """Check if the specified port is open."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex((host, port))
    sock.close()
    return result == 0

def open_browser(host, port):
    """Open the browser after a short delay to ensure server is running."""
    # Only open browser in the main process, not the reloader
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        time.sleep(2)  # Wait for server to start
        if is_port_open(host, port):
            try:
                webbrowser.open(f'http://{host}:{port}')
                print(f"Opened browser at http://{host}:{port}")
            except Exception as e:
                print(f"Failed to open browser: {e}")
        else:
            print(f"Failed to verify server is running on port {port}. Please check if the port is in use or accessible.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the Flask app with a specified port.')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the Flask app on (default: 5000)')
    args = parser.parse_args()

    port = args.port
    host = '127.0.0.1'

    # Start browser opening in a separate thread
    browser_thread = threading.Thread(target=open_browser, args=(host, port), daemon=True)
    browser_thread.start()

    # Run Flask server in the main thread
    try:
        app.run(debug=True, host='127.0.0.1', port=port)
    except Exception as e:
        print(f"Failed to start Flask server: {e}")
        sys.exit(1)