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
import sys
import os

if os.name == "nt":  # Windows
    sys.path.append(r"code\src")
else:  # Linux, macOS, etc.
    sys.path.append("src")
    
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
import state
from routes.core_routes import core_bp
from routes.hardware_routes import hardware_bp
from routes.file_routes import file_bp
from routes.math_routes import math_bp

app = Flask(__name__, static_folder='static')
app.register_blueprint(core_bp)
app.register_blueprint(hardware_bp)
app.register_blueprint(file_bp)
app.register_blueprint(math_bp)

# Endpoints moved to their respective blueprints

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the Flask app with a specified port and alias.')
    parser.add_argument('--port', type=int, default=5099, help='Port to run the Flask app on (default: 5099)')
    parser.add_argument('--alias', type=str, default='easyokapi.com', help='Optional domain alias (e.g., mydomain.com)')
    
    # We assign to state args directly
    state.args = parser.parse_args()

    host = '127.0.0.1'
    port = state.args.port
    alias = state.args.alias or host

    if alias and alias != '127.0.0.1':
        ensure_host_mapping(alias)

    # Launch browser with alias
    browser_thread = threading.Thread(target=open_browser, args=(alias, port), daemon=True)
    browser_thread.start()

    atexit.register(cleanup, state.process, state.log_file, state.args)

    def _shutdown_handler(signum, frame):
        """Handle SIGTERM/SIGINT by triggering registered atexit handlers and exiting cleanly."""
        print(f"Received signal {signum}, shutting down gracefully...")
        sys.exit(0)  # triggers atexit.register(cleanup, ...)

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    try:
        # use_reloader=False prevents Werkzeug from spawning a child reloader process.
        # That child process is the main source of "leaked semaphore" warnings on shutdown.
        app.run(debug=True, host=host, port=port, use_reloader=False)
    except Exception as e:
        print(f"Failed to start Flask server: {e}")
        sys.exit(1)