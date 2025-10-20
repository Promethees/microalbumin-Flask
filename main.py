from flask import Flask, render_template, request, jsonify, make_response, session
import os
import sys
import argparse
import threading
import time
import csv
import pandas as pd
from io import StringIO
import json
from http import HTTPStatus
from datetime import datetime
import re
from werkzeug.utils import secure_filename
import uuid
from flask_socketio import SocketIO
import eventlet

sys.path.append('src')
from range import get_range_input
from mode import get_mode_input
from quantity import get_quantity_input
from get_next_filename import get_next_filename
from export_cal_json import processJSONCoef, extractAnalysisCoefficients, CustomEncoder
from export_data import parse_metadata, is_metadata_consistent, write_metadata, write_headers, extract_single_entry, sort_csv_content, user_csv_lock
from browser_mgt import open_browser
from config import Config

app = Flask(__name__, static_folder='static')
app.config.from_object(Config)
app.secret_key = 'easy-sensor-kit'  # Required for session to work
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', engineio_logger=True, logger=True)

# Global in-memory storage for user data
USER_DATA = {}

def get_user_id():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

def get_user_data():
    uid = get_user_id()
    if uid not in USER_DATA:
        USER_DATA[uid] = {'csv': {}, 'json': {}}
    return USER_DATA[uid]

delimiter = "/";

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
    user_data = get_user_data()
    file_list = list(user_data['csv'].keys())
    cal_json_list = list(user_data['json'].get('kinetics', {}).keys())
    response = make_response(render_template('index.html', 
                         title="Easy Sensor Kit",
                         directory= '/',
                         csv_path = '/csv',
                         range_input=range_input,
                         mode_input=mode_input,
                         quantity_input=quantity_input,
                         file_list=file_list,
                         cal_json_list=cal_json_list,
                         delimiter=delimiter,
                         production_mode= PRODUCTION_MODE))
    return response

@app.route('/get_csv', methods=['GET'])
def get_csv():
    user_data = get_user_data()
    # Virtual directory, return csv files
    file_list = list(user_data['csv'].keys())
    return jsonify({'status': 'success', 'files': file_list})

@app.route('/get_json_cal', methods=['GET'])
def get_json_cal():
    mode = request.args.get('mode')
    user_data = get_user_data()
    if mode not in user_data['json']:
        user_data['json'][mode] = {}
    json_files = list(user_data['json'][mode].keys())
    return jsonify({'status': 'success', 'files': json_files})

# Region 2: USED by navigation.js
@app.route('/get_json_content', methods=['GET'])
def get_json_content():
    selected_json = request.args.get('json_name')
    mode = request.args.get('mode')
    user_data = get_user_data()
    content = user_data['json'].get(mode, {}).get(selected_json, None)
    if content:
        try:
            data = json.loads(content)
            return jsonify({'status': 'success', 'json': data})
        except json.JSONDecodeError:
            return jsonify({'status': 'error', 'message': 'Error in reading the json file'})
    return jsonify({'status': 'error', 'message': 'Error in reading the json file'})

@app.route('/get_headers', methods=['GET'])
def get_csv_headers():
    read_file = request.args.get('file')
    content = get_user_data()['csv'].get(read_file, None)
    if content:
        df = pd.read_csv(StringIO(content), nrows=0, comment = "#")  # Read only the header row, ignore comment lines
        return jsonify({'headers': df.columns.tolist()}) 
    return jsonify({'headers': [], 'error': "Invalid csv file or file path is wrong"})

@app.route("/api/current_output", methods=["GET"])
def api_current_output():
    return jsonify({"exists": False, "message": "Not supported in multiuser mode"}), 404

# Region 3: USED by edit_file.js
@app.route('/edit_file', methods=['POST'])
def edit_file():
    try:
        # Extract request data
        file_name = request.form.get('filename')
        new_file_name = request.form.get('new_filename', file_name)  # Default to original name if not provided
        type = request.form.get('type')
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
        print(f"Editing file: {file_name} to {new_file_name} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S %z')}")

        is_json = new_file_name.endswith('.json')

        # Validate content based on file extension
        if is_json:
            try:
                # Validate JSON format
                parsed_json = json.loads(content)
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

        # Write the new content in memory
        user_data = get_user_data()
        if type == "json":
            mode = request.form.get('mode')
            if mode not in user_data['json']:
                user_data['json'][mode] = {}
            store = user_data['json'][mode]
        else:
            store = user_data['csv']

        if file_name not in store:
            return jsonify({
                'status': 'error',
                'message': f'File {file_name} not found'
            }), HTTPStatus.NOT_FOUND

        if file_name != new_file_name and new_file_name in store:
            return jsonify({
                'status': 'error',
                'message': f'File {new_file_name} already exists'
            }), HTTPStatus.CONFLICT

        try:
            if is_json:
                # Pretty print JSON with indentation
                parsed_json = json.loads(content)
                store[new_file_name] = json.dumps(parsed_json, indent=2)
            else:
                store[new_file_name] = content
            if file_name != new_file_name:
                del store[file_name]
            message = f'File {file_name} updated successfully' + (f' and renamed to {new_file_name}' if file_name != new_file_name else '')

            # Handle sorting if applicable
            if calibrate_mode and not is_json:
                content = store[new_file_name]
                lines = content.split('\n')
                metadata = [l for l in lines if l.startswith('#')]
                data_lines = [l for l in lines if not l.startswith('#') and l.strip()]
                if data_lines:
                    header = data_lines[0]
                    rows = data_lines[1:]
                    parsed_rows = [r.split(',') for r in rows if r]
                    def key_func(row):
                        try:
                            return float(row[0]) if row[0] != 'NONE' else float('inf')
                        except:
                            return float('inf')
                    parsed_rows.sort(key=key_func)
                    new_rows = [','.join(r) for r in parsed_rows]
                    new_content = '\n'.join(metadata + [header] + new_rows) + '\n'
                    store[new_file_name] = new_content

            # Emit update after changes
            if type == "json":
                socketio.emit('update_json', {'mode': mode})
            else:
                socketio.emit('update_csv')

            return jsonify({
                'status': 'success',
                'message': message
            }), HTTPStatus.OK
        except Exception as e:
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

        # Input validation
        if not file_name or not tabletype:
            return jsonify({
                'status': 'error',
                'message': 'Filename and tabletype are required'
            }), HTTPStatus.BAD_REQUEST

        user_data = get_user_data()

        if tabletype == '#json-table':
            if not mode:
                return jsonify({
                    'status': 'error',
                    'message': 'Mode is required for JSON table type'
                }), HTTPStatus.BAD_REQUEST
            if mode in user_data['json'] and file_name in user_data['json'][mode]:
                del user_data['json'][mode][file_name]
                socketio.emit('update_json', {'mode': mode})
                return jsonify({
                    'status': 'success',
                    'message': f'File {file_name} deleted successfully'
                }), HTTPStatus.OK
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'File {file_name} not found'
                }), HTTPStatus.NOT_FOUND
        else:
            if file_name in user_data['csv']:
                del user_data['csv'][file_name]
                socketio.emit('update_csv')
                return jsonify({
                    'status': 'success',
                    'message': f'File {file_name} deleted successfully'
                }), HTTPStatus.OK
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'File {file_name} not found'
                }), HTTPStatus.NOT_FOUND

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

        # Input validation
        if not file_name or not tabletype:
            return jsonify({
                'status': 'error',
                'message': 'Filename and tabletype are required'
            }), HTTPStatus.BAD_REQUEST

        user_data = get_user_data()

        if tabletype == '#json-table':
            if not mode:
                return jsonify({
                    'status': 'error',
                    'message': 'Mode is required for JSON table type'
                }), HTTPStatus.BAD_REQUEST

            content = user_data['json'].get(mode, {}).get(file_name, None)
            if content is None:
                return jsonify({
                    'status': 'error',
                    'message': f'Source file {file_name} not found'
                }), HTTPStatus.NOT_FOUND

            base, ext = os.path.splitext(file_name)
            files = list(user_data['json'].get(mode, {}).keys())
            dst_name = get_next_filename(ext, files, base)
            user_data['json'][mode][dst_name] = content
            socketio.emit('update_json', {'mode': mode})
            return jsonify({
                'status': 'success',
                'message': f'File copied to {dst_name}',
                'new_filename': dst_name
            }), HTTPStatus.OK
        else:
            content = user_data['csv'].get(file_name, None)
            if content is None:
                return jsonify({
                    'status': 'error',
                    'message': f'Source file {file_name} not found'
                }), HTTPStatus.NOT_FOUND

            base, ext = os.path.splitext(file_name)
            files = list(user_data['csv'].keys())
            dst_name = get_next_filename(ext, files, base)
            user_data['csv'][dst_name] = content
            socketio.emit('update_csv')
            return jsonify({
                'status': 'success',
                'message': f'File copied to {dst_name}',
                'new_filename': dst_name
            }), HTTPStatus.OK

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
        content = uploaded_file.read().decode('utf-8')

        user_data = get_user_data()
        message_suffix = ''

        if tabletype == '#json-table':
            if not mode:
                return jsonify({
                    'status': 'error',
                    'message': 'Mode is required for JSON uploads'
                }), HTTPStatus.BAD_REQUEST
            if mode not in user_data['json']:
                user_data['json'][mode] = {}
            store = user_data['json'][mode]
            if filename in store:
                base, ext = os.path.splitext(filename)
                files = list(store.keys())
                filename = get_next_filename(ext, files, base)
                message_suffix = f' (auto-renamed to avoid overwrite). New name is {filename}'
            store[filename] = content
            socketio.emit('update_json', {'mode': mode})
        else:
            store = user_data['csv']
            if filename in store:
                base, ext = os.path.splitext(filename)
                files = list(store.keys())
                filename = get_next_filename(ext, files, base)
                message_suffix = f' (auto-renamed to avoid overwrite). New name is {filename}'
            store[filename] = content
            socketio.emit('update_csv')

        return jsonify({
            'status': 'success',
            'message': f'File "{filename}" uploaded successfully{message_suffix}.',
            'filename': filename
        }), HTTPStatus.OK

    except Exception as e:
        print(f"Unexpected error in upload_file: {e}")
        return jsonify({
            'status': 'error',
            'message': 'An unexpected error occurred while uploading the file.'
        }), HTTPStatus.INTERNAL_SERVER_ERROR
       
@app.route('/get_data', methods=['GET'])
def get_data():
    selected_file = request.args.get('file')
    user_data = get_user_data()
    content = user_data['csv'].get(selected_file, None)
    if not content:
        return jsonify({'data': [], 'error': 'File not found', 'unit': "NONE", 'metadata': {}})

    try:
        if selected_file.lower().endswith('.csv'):
            metadata = {}
            data = []

            # Split content into lines
            lines = content.splitlines()

            # Separate metadata and CSV data
            data_lines = []
            for line in lines:
                if line.strip().startswith("#"):
                    if ":" in line:
                        key, value = line[1:].split(":", 1)
                        metadata[key.strip()] = value.strip()
                elif line.strip():
                    data_lines.append(line)

            # Parse the CSV part into a DataFrame
            if data_lines:
                df = pd.read_csv(StringIO("\n".join(data_lines)))
                data = df.to_dict('records')
            else:
                data = []

            # Unit resolution priority: check metadata keys
            unit = "NONE"
            for possible_name in ['Unit', 'MeasUnit']:
                if possible_name in metadata:
                    unit = metadata[possible_name]
                    break

            return jsonify({
                'data': data,
                'unit': unit,
                'error': None,
                'metadata': metadata
            })

        elif selected_file.lower().endswith('.json'):
            json_data = json.loads(content)
            
            data = json_data if isinstance(json_data, list) else [json_data]
            
            # Attempt to find a unit field in JSON data
            unit = "NONE"
            if data and isinstance(data[0], dict):
                for possible_name in ['Unit', 'MeasUnit', 'unit', 'measUnit']:
                    if possible_name in data[0]:
                        unit = data[0][possible_name]
                        break

            return jsonify({
                'data': data,
                'unit': unit,
                'error': None,
                'metadata': {}  # JSON files don't have metadata in this context
            })
        else:
            return jsonify({'data': [], 'error': 'Unsupported file type', 'unit': "NONE", 'metadata': {}})

    except json.JSONDecodeError as e:
        return jsonify({'data': [], 'error': f'Invalid JSON format: {str(e)}', 'unit': "NONE", 'metadata': {}})
    except Exception as e:
        return jsonify({'data': [], 'error': f'Error processing file: {str(e)}', 'unit': "NONE", 'metadata': {}})

@app.route('/get_file_content', methods=['GET'])
def get_file_content():
    try:
        file_name = request.args.get('file')
        type = request.args.get('type') 
        if not file_name:
            return jsonify({
                'status': 'error',
                'message': 'Filename is required'
            }), HTTPStatus.BAD_REQUEST

        print(f"Fetching raw content for editing from file: {file_name} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S %z')}")

        # Ensure the file is either CSV or JSON
        if not (file_name.lower().endswith('.csv') or file_name.lower().endswith('.json')):
            return jsonify({
                'status': 'error',
                'message': 'Only CSV and JSON files are supported'
            }), HTTPStatus.BAD_REQUEST

        user_data = get_user_data()
        content = None
        if type == 'json':
            mode = request.args.get('mode')
            content = user_data[type][mode].get(file_name, None)
        else:
            content = user_data[type].get(file_name, None)

        if content is None:
            return jsonify({
                'status': 'error',
                'message': 'File not found'
            }), HTTPStatus.NOT_FOUND

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
    user_data = get_user_data()

    # Extract common fields
    file_name = data.get('save_file', 'result')
    measurement = data.get('meas', 'NONE')
    meas_unit = data.get('measUnit', 'NONE')
    meas_mode = data.get('measMode')
    newFile = data.get('newFile', True)
    time_unit = "minute" if meas_mode == "point" else "minutes"

    full_name = f"{file_name}_{meas_mode}.csv"

    try:
        with user_csv_lock:
            content = user_data['csv'].get(full_name, None)
            file_exists = content is not None

            # Check metadata consistency if file exists
            if file_exists:
                meta_dict = parse_metadata(content)
                if not is_metadata_consistent(meta_dict, measurement, meas_unit, time_unit, meas_mode):
                    return jsonify({"status": "error", "message": "Metadata inconsistency"})

            output = StringIO()
            writer = csv.writer(output)

            # Write metadata and headers if new file
            if not file_exists and newFile:
                write_metadata(output, measurement, meas_unit, time_unit, meas_mode)
                write_headers(writer, meas_mode)
            elif file_exists:
                output.write(content.rstrip('\n') + '\n')

            # Prepare entries (handle single as list of one)
            if is_batch:
                entries = [extract_single_entry(entry, meas_mode) for entry in entries]
            else:
                entries = [extract_single_entry(data, meas_mode)]

            print("Entries are ", entries)
            # Append all entries
            for entry in entries:
                writer.writerow(entry)

            new_content = output.getvalue()

            # Sort by Concentration
            new_content = sort_csv_content(new_content)

            user_data['csv'][full_name] = new_content

        return jsonify({"status": "success", "message": f"Data exported at {full_name}"})

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
    print("received coef_content:", coef_content)
    try: 
        user_data = get_user_data()
        if cal_mode not in user_data['json']:
            user_data['json'][cal_mode] = {}
        files = list(user_data['json'][cal_mode].keys())
        full_name = get_next_filename(".json", files, file_name)

        json_content = processJSONCoef(cal_params, extractAnalysisCoefficients(coef_content, thres_val))
        json_content.update({"fit_type": fit_type, "for_meas": for_meas, "for_blank_type": for_blank_type})

        if (cal_mode == "point"):
            json_content.update({"time": time, "time-unit": time_unit})
        content = json.dumps(json_content, cls=CustomEncoder, indent=4)
        user_data['json'][cal_mode][full_name] = content
        return jsonify({"status": "success", "message": f"Data exported to {full_name}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# if __name__ == '__main__':
#     import eventlet

#     parser = argparse.ArgumentParser(description='Run the Flask app with a specified port and alias.')
#     parser.add_argument('--port', type=int, default=5000, help='Port to run the Flask app on (default: 5099)')
#     parser.add_argument('--alias', type=str, default='easysensor-kit.com', help='Optional domain alias (e.g., mydomain.com)')
#     args = parser.parse_args()

#     host = '127.0.0.1'
#     port = args.port
#     alias = args.alias or host

#     # Launch browser with alias
#     browser_thread = threading.Thread(target=open_browser, args=(alias, port), daemon=True)
#     browser_thread.start()

#     try:
#         socketio.run(app, debug=True, host=host, port=port)
#     except Exception as e:
#         print(f"Failed to start Flask server: {e}")
#         sys.exit(1)
if __name__ == '__main__':
    import eventlet
    import os
    port = int(os.environ.get('PORT', 5000))  # Use Heroku's PORT or default to 5000
    host = '0.0.0.0'  # Listen on all interfaces
    try:
        socketio.run(app, debug=False, host=host, port=port)  # Disable debug for production
    except Exception as e:
        print(f"Failed to start Flask server: {e}")
        sys.exit(1)