from flask import Flask, render_template, request, jsonify
import os
import sys
import webbrowser
import argparse
import threading
import time
import socket
sys.path.append('src')
from file_path import get_directory, browse_directory, get_parent_directory, get_child_directories
from range import get_range_input
from measure import get_dynamic_data
from file import get_file_list

app = Flask(__name__)

@app.route('/')
def index():
    directory = get_directory()
    range_input = get_range_input()
    file_list = get_file_list(directory)
    return render_template('index.html', 
                         title="Easy Sensor Kit",
                         directory=directory,
                         range_input=range_input,
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