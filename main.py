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
abs_col = 0
blankT_col = 6

os_name = platform.system().lower()
if "window" in os_name:
    delimiter = "\\"
else:
    delimiter = "/"

json_root_path = os.path.join(os.getcwd(), "json")

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
    return jsonify({'status': 'success'})

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

@app.route('/export_data', methods=['POST'])
def export_data(mode="kinetics"):
    default_path = os.path.join(os.getcwd(), "export_data")
    data = request.get_json()
    print(f"data is {data}")
    file_name = data.get('save_file', 'result')
    export_path = data.get('save_dir' != "", default_path)
    measurement = data.get('meas')
    vmax = data.get('vmax', 'NONE')
    slope = data.get('slope', '0.0000')
    sat = data.get('sat', 'NONE')
    concentration = data.get('con')
    time_to_sat = data.get('timeSat')
    meas_unit = data.get('measUnit')

    blankT = data.get('blanked')
    time_unit = data.get('timeUnit')
    
    newFile = data.get('newFile')
    try:
        
        # Check if the provided path is an environment variable
        export_path = os.getenv(export_path, export_path)

        # Ensure the directory path is absolute and normalized
        export_path = os.path.abspath(os.path.expanduser(export_path))
        print(f"export path is {export_path}")
        # Ensure directory exists
        os.makedirs(export_path, exist_ok=True)
        
        full_path = os.path.join(export_path, file_name + ".csv")

        # Check if file exists and has headers
        file_exists = os.path.isfile(full_path)
        message = None
        status = None
        if not newFile:
            time.sleep(1)
        with open(full_path, "a", newline='') as f:
            writer = csv.writer(f)
            if not file_exists and newFile:
                writer.writerow(['Measurement', 'Concentration', 'Vmax', 'Slope', 'Saturation', 'Time To Sat', 'MeasUnit','TimeUnit', 'BlankType'])  # Write header if new file
                # writer.writerow(['Concentration', 'Value', 'Unit', 'Time', 'TimeUnit', 'BlankType'])
            # writer.writerow([vmax, slope, sat])  # Append data
            if check_row_exist(full_path, concentration, blankT):
                message = f"Error: This {concentration} nM/l concentration value with this blank Type \"{blankT}\" already exist in {full_path}"
                status = "error"
            else: 
                writer.writerow([measurement.lower(), concentration,vmax,slope,sat,time_to_sat,meas_unit,time_unit,blankT.lower()])

                # writer.writerow([concentration,value,unit.time,timeunit,blankT])
                message = f"Data exported at {full_path}"
                status = "success" 
            f.close()

        return jsonify({"status": status, "message": message})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

def check_row_exist(full_path, absorbance, blankT):
    with open(full_path, mode='r', newline='') as f:
        reader = csv.reader(f)

        for row in reader:
            if row[abs_col] == absorbance and row[blankT_col] == blankT:
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