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

sys.path.append('src')
from file_path import get_directory, browse_directory, get_parent_directory, get_child_directories
from range import get_range_input
from method import get_method_input
from measure import get_dynamic_data
from quantity import get_quantity_input
from file import get_file_list

app = Flask(__name__)
process = None
log_file = "log/script_logs.txt"

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
    method_input = get_method_input()
    quantity_input = get_quantity_input()
    file_list = get_file_list(directory)
    return render_template('index.html', 
                         title="Easy Sensor Kit",
                         directory=directory,
                         range_input=range_input,
                         method_input=method_input,
                         quantity_input=quantity_input,
                         file_list=file_list)

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
    base_dir = data.get('base_dir', '')
    base_name = data.get('base_name', '')
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

@app.route('/get_data', methods=['GET'])
def get_data():
    selected_file = request.args.get('file')
    range_value = request.args.get('range')
    time_unit = request.args.get('unit')
    # print(f"Range value is: {range_value}")
    data = get_dynamic_data(selected_file, range_value, time_unit)
    # print(f"Data read is {data}")
    return jsonify(data)

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