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
import shutil
from pathlib import Path
from werkzeug.utils import secure_filename

sys.path.append('src')
from file_path import get_directory, browse_directory, get_parent_directory, get_child_directories
from range import get_range_input
from mode import get_mode_input
from measure import sort_csv_file
from quantity import get_quantity_input
from file import get_file_list, get_dynamic_data
from get_next_filename import get_next_filename
from script_monitor import check_log_for_errors
from export_data import check_row_exist, check_metadata_consistency
from export_cal_json import processJSONCoef, extractAnalysisCoefficients, CustomEncoder
from browser_mgt import open_browser, cleanup, ensure_host_mapping
from send_command import connect_to_device, send_command_and_wait_ack
from config import Config

app = Flask(__name__, static_folder='static')
app.config.from_object(Config)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

os_name = platform.system().lower()
if "window" in os_name:
    delimiter = "\\\\";
else:
    delimiter = "/";

json_root_path = os.path.join(os.getcwd(), "json")
csv_path = os.path.join(os.getcwd(), "csv")
# Configuration - Set this to False for development, True for production
PRODUCTION_MODE = True  # Change this based on your environment

# Region 1: USED by index.js
@app.route('/ping')
def ping():
    return jsonify({'status': 'success'})

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
    range_input = get_range_input()
    mode_input = get_mode_input()
    quantity_input = get_quantity_input()
    file_list = get_file_list(csv_path)
    cal_json_list = get_file_list(os.path.join(json_root_path, "kinetics"), "*.json")
    response = make_response(render_template('index.html', 
                         title="Easy Sensor Kit",
                         directory= os.path.abspath(os.getcwd()),
                         csv_path = csv_path,
                         range_input=range_input,
                         mode_input=mode_input,
                         quantity_input=quantity_input,
                         file_list=file_list,
                         cal_json_list=cal_json_list,
                         delimiter=delimiter,
                         production_mode= PRODUCTION_MODE))
    return response

@app.route('/browse', methods=['POST'])
def browse():
    new_path = request.form['path']
    if browse_directory(new_path):
        file_list = get_file_list(get_directory())
        return jsonify({'status': 'success', 'path': new_path, 'files': file_list})
    return jsonify({'status': 'error', 'message': 'Invalid directory'})

@app.route('/get_json_cal', methods=['GET'])
def get_json_cal():
    mode = request.args.get('mode')
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
        df = pd.read_csv(read_file, nrows=0, comment = "#")  # Read only the header row, ignore comment lines
        return jsonify({'headers': df.columns.tolist()}) 
    return jsonify({'headers': [], 'error': "Invalid csv file or file path is wrong"})

@app.route("/api/current_output", methods=["GET"])
def api_current_output():
    try:
        # adjust this to the actual location of the "log" folder if needed
        marker_path = os.path.join(os.getcwd(), "log", "current_output.txt")

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

# Region 3: USED by edit_file.js
@app.route('/edit_file', methods=['POST'])
def edit_file():
    global process
    try:
        # Extract request data
        file_name = request.form.get('filename')
        new_file_name = request.form.get('new_filename', file_name)  # Default to original name if not provided
        path = request.form.get('path') if request.form.get('path') else get_directory()
        content = request.form.get('content')
        calibrate_mode = request.form.get('calibrate_mode')
        multi_source = request.form.get('multi_source', 'false').lower() == 'true'

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
                    'header': r"^Timestamp,Value,Type,Blanked$",
                    'data': r"^\d+\.{0,1}\d{0,2},(\-{0,1}\d+\.{0,1}\d{0,3}|OVFL),[A-Za-z]+,(TRUE|FALSE)$",
                    'meta': ["Measurement", "Unit", "Concentration"],
                    'error': 'Invalid format (Colorimeter data). Header must be: Timestamp,Measurement,Value,Type,Blanked. Metadata must include Measurement, Unit, and Concentration.'
                },
                {
                    'header': r"^Concentration,maxRate,Slope,Sat,TimeToSat,BlankType$",
                    'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+\.\d+),(NONE|\d+|\d+\.\d*),(MIXED|BLANKED|NON-BLANKED)$",
                    'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
                    'error': 'Invalid format (Kinetics calibration). Header must be: Concentration,maxRate,Slope,Sat,Time To Sat,BlankType. Metadata must include Measurement, MeasUnit, TimeUnit, and MeasMode.'
                },
                {
                    'header': r"^Concentration,Value,TimePoint,BlankType$",
                    'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d*),(MIXED|BLANKED|NON-BLANKED)$",
                    'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
                    'error': 'Invalid format (Point calibration). Header must be: Concentration,Value,TimePoint,BlankType. Metadata must include Measurement, MeasUnit, TimeUnit and MeasMode.'
                },
                {
                    'header': r'^\s*Timestamp\s*,\s*Value:\d+(?:\s*,\s*Value:\d+)*\s*$',
                    'data': r'^\s*\d+(?:\.\d{1,2})?\s*(?:,\s*(?:-?\d+(?:\.\d{1,3})?|OVFL))*\s*$',
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
                if re.match(pattern['header'], header_line):
                    matched_pattern = pattern
                    break

            if not matched_pattern:
                valid_headers = " OR ".join(p['error'].split('Header must be: ')[1] for p in pattern_sets)
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid CSV header. Must match one of: {valid_headers}'
                }), HTTPStatus.BAD_REQUEST

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
            if new_file_name.endswith('.json'):
                # Pretty print JSON with indentation
                parsed_json = json.loads(content)
                with open(new_file_path, 'w') as f:
                    json.dump(parsed_json, f, indent=2)
            else:
                with open(new_file_path, 'w') as f:
                    f.write(content)
                if calibrate_mode:
                    sort_csv_file(new_file_path, calibrate_mode, multi_source)
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
    
@app.route('/copy_file', methods=['POST'])
def copy_file():
    try:
        file_name = request.form.get('filename')
        mode = request.form.get('mode')
        tabletype = request.form.get('tabletype')
        path = request.form.get('path') if request.form.get('path') else get_directory()

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

@app.route('/upload_file', methods=['POST'])
def upload_file():
    try:
        uploaded_file = request.files.get('file')
        mode = request.form.get('mode')
        tabletype = request.form.get('tabletype')

        if not uploaded_file or not tabletype:
            return jsonify({
                'status': 'error',
                'message': 'File and tabletype are required'
            }), HTTPStatus.BAD_REQUEST

        filename = secure_filename(uploaded_file.filename)

        # Determine destination directory
        if tabletype == '#json-table':
            if not mode:
                return jsonify({
                    'status': 'error',
                    'message': 'Mode is required for JSON uploads'
                }), HTTPStatus.BAD_REQUEST
            dst_dir = os.path.join(json_root_path, mode)
        else:
            dst_dir = csv_path

        os.makedirs(dst_dir, exist_ok=True)

        dst_path = os.path.join(dst_dir, filename)

        # === ✅ Duplicate filename check ===
        if os.path.exists(dst_path):
            # Automatically rename
            base, ext = os.path.splitext(filename)
            dst_path = get_next_filename(ext, dst_dir, base)
            message_suffix = f' (auto-renamed to avoid overwrite). New name is {filename}'
        else:
            message_suffix = ''

        # Save file
        uploaded_file.save(dst_path)

        return jsonify({
            'status': 'success',
            'message': f'File "{filename}" uploaded successfully{message_suffix}.',
            'filename': os.path.basename(dst_path)
        }), HTTPStatus.OK

    except PermissionError as e:
        return jsonify({
            'status': 'error',
            'message': f'Permission denied: {str(e)}'
        }), HTTPStatus.FORBIDDEN

    except Exception as e:
        print(f"Unexpected error in upload_file: {e}")
        return jsonify({
            'status': 'error',
            'message': 'An unexpected error occurred while uploading the file.'
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
    newFile = data.get('newFile')
    meas_mode = data.get('measMode')
    time_unit = "minute" if meas_mode == "point" else "minutes"
    value = data.get('estValue', 'NONE')
    time_point = data.get('timePoint')

    try:
        export_path = os.path.abspath(os.path.expanduser(save_dir))
        os.makedirs(export_path, exist_ok=True)
        full_path = os.path.join(export_path, file_name + "_" + meas_mode + ".csv")

        file_exists = os.path.isfile(full_path)

        # ✅ Check metadata consistency if file already exists
        if file_exists:
            check_metadata_consistency(full_path, measurement, meas_unit, time_unit, meas_mode)

        if not newFile:
            time.sleep(1)

        with open(full_path, "a", newline='') as f:
            writer = csv.writer(f)

            if not file_exists and newFile:
                # Write metadata
                f.write(f"# Measurement: {measurement}\n")
                f.write(f"# MeasUnit: {meas_unit}\n")
                f.write(f"# TimeUnit: {time_unit}\n")
                f.write(f"# MeasMode: {meas_mode}\n") 

                # Write headers
                if meas_mode == "kinetics":
                    writer.writerow(['Concentration', 'maxRate', 'Slope', 'Sat', 'Time To Sat', 'BlankType'])
                else:
                    writer.writerow(['Concentration', 'Value', 'TimePoint', 'BlankType'])

            # Write data
            if meas_mode == "kinetics":
                writer.writerow([concentration, maxrate, slope, sat, time_to_sat, blankT])
            else:
                writer.writerow([concentration, value, time_point, blankT])

        sort_csv_file(full_path, meas_mode)

        return jsonify({"status": "success", "message": f"Data exported at {full_path}"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/export_cal_coefs', methods=['POST'])
def export_cal_coefs():
    data = request.get_json()
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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the Flask app with a specified port and alias.')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the Flask app on (default: 5099)')
    parser.add_argument('--alias', type=str, default='easysensor-kit.com', help='Optional domain alias (e.g., mydomain.com)')
    args = parser.parse_args()

    host = '127.0.0.1'
    port = args.port
    alias = args.alias or host

    # Launch browser with alias
    browser_thread = threading.Thread(target=open_browser, args=(alias, port), daemon=True)
    browser_thread.start()

    try:
        app.run(debug=True, host=host, port=port)
    except Exception as e:
        print(f"Failed to start Flask server: {e}")
        sys.exit(1)