from flask import Blueprint, request, jsonify, session
from http import HTTPStatus
import os
import re
import json
from werkzeug.utils import secure_filename
from user_data import get_user_data, update_file_metadata
from get_next_filename import get_next_filename
from export_cal_json import replace_empty
from file_merge import merge_csv_contents
from extensions import socketio
from validators import validate_csv_content, validate_json_content

file_bp = Blueprint('file', __name__)

@file_bp.route('/edit_file', methods=['POST'])
def edit_file():
    try:
        # Extract request data
        file_name = request.form.get('filename')
        new_file_name = request.form.get('new_filename', file_name)
        type = request.form.get('type')
        content = request.form.get('content')
        calibrate_mode = request.form.get('calibrate_mode')

        # Input validation
        if not file_name or not content:
            return jsonify({'status': 'error', 'message': 'Filename and content are required'}), HTTPStatus.BAD_REQUEST

        if not (new_file_name.endswith('.csv') or new_file_name.endswith('.json')):
            return jsonify({'status': 'error', 'message': 'New file name must end with .csv or .json'}), HTTPStatus.BAD_REQUEST

        is_json = new_file_name.endswith('.json')

        if is_json:
            success, result = validate_json_content(content)
            if not success:
                return jsonify({'status': 'error', 'message': result}), HTTPStatus.BAD_REQUEST
        else:  # CSV validation
            success, result = validate_csv_content(content)
            if not success:
                return jsonify({'status': 'error', 'message': result}), HTTPStatus.BAD_REQUEST

        user_data = get_user_data()
        if type == "json":
            mode = request.form.get('mode')
            if mode not in user_data['json']:
                user_data['json'][mode] = {}
            store = user_data['json'][mode]
        else:
            store = user_data['csv']

        if file_name not in store:
            return jsonify({'status': 'error', 'message': f'File {file_name} not found'}), HTTPStatus.NOT_FOUND

        if file_name != new_file_name and new_file_name in store:
            return jsonify({'status': 'error', 'message': f'File {new_file_name} already exists'}), HTTPStatus.CONFLICT

        if is_json:
            parsed_json = json.loads(content)
            cleaned_json = replace_empty(parsed_json)
            store[new_file_name] = json.dumps(cleaned_json, indent=2)
        else:
            store[new_file_name] = content

        if file_name != new_file_name:
            del store[file_name]
            # Update cache: remove old name
            if 'metadata_cache' in user_data and file_name in user_data['metadata_cache']:
                del user_data['metadata_cache'][file_name]
        
        # Update cache for new/updated content
        if not is_json:
            update_file_metadata(new_file_name, store[new_file_name])
        
        message = f'File {file_name} updated successfully' + (f' and renamed to {new_file_name}' if file_name != new_file_name else '')

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
                # Update cache again after sorting
                update_file_metadata(new_file_name, new_content)

        if type == "json":
            socketio.emit('update_json', {'mode': mode})
        else:
            socketio.emit('update_csv')

        from user_data import save_user_data
        save_user_data(user_data)

        return jsonify({'status': 'success', 'message': message}), HTTPStatus.OK
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred while saving the file'}), 500

@file_bp.route('/delete_file', methods=['POST'])
def delete_file():
    try:
        file_name = request.form.get('filename')
        tabletype = request.form.get('tabletype')
        mode = request.form.get('mode')

        if not file_name or not tabletype:
            return jsonify({'status': 'error', 'message': 'Filename and tabletype are required'}), HTTPStatus.BAD_REQUEST

        user_data = get_user_data()

        if tabletype == '#json-table':
            if not mode:
                return jsonify({'status': 'error', 'message': 'Mode is required for JSON table type'}), HTTPStatus.BAD_REQUEST
            if mode in user_data['json'] and file_name in user_data['json'][mode]:
                del user_data['json'][mode][file_name]
                socketio.emit('update_json', {'mode': mode})
                from user_data import save_user_data
                save_user_data(user_data)
                return jsonify({'status': 'success', 'message': f'File {file_name} deleted successfully'}), HTTPStatus.OK
            else:
                return jsonify({'status': 'error', 'message': f'File {file_name} not found'}), HTTPStatus.NOT_FOUND
        else:
            if file_name in user_data['csv']:
                del user_data['csv'][file_name]
                # Delete cache
                if 'metadata_cache' in user_data and file_name in user_data['metadata_cache']:
                    del user_data['metadata_cache'][file_name]
                socketio.emit('update_csv')
                from user_data import save_user_data
                save_user_data(user_data)
                return jsonify({'status': 'success', 'message': f'File {file_name} deleted successfully'}), HTTPStatus.OK
            else:
                return jsonify({'status': 'error', 'message': f'File {file_name} not found'}), HTTPStatus.NOT_FOUND
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred while deleting the file'}), 500

@file_bp.route('/copy_file', methods=['POST'])
def copy_file():
    try:
        file_name = request.form.get('filename')
        mode = request.form.get('mode')
        tabletype = request.form.get('tabletype')

        if not file_name or not tabletype:
            return jsonify({'status': 'error', 'message': 'Filename and tabletype are required'}), HTTPStatus.BAD_REQUEST

        user_data = get_user_data()

        if tabletype == '#json-table':
            if not mode:
                return jsonify({'status': 'error', 'message': 'Mode is required for JSON table type'}), HTTPStatus.BAD_REQUEST
            content = user_data['json'].get(mode, {}).get(file_name, None)
            if content is None:
                return jsonify({'status': 'error', 'message': f'Source file {file_name} not found'}), HTTPStatus.NOT_FOUND
            base, ext = os.path.splitext(file_name)
            files = list(user_data['json'].get(mode, {}).keys())
            dst_name = get_next_filename(ext, files, base)
            user_data['json'][mode][dst_name] = content
            socketio.emit('update_json', {'mode': mode})
            from user_data import save_user_data
            save_user_data(user_data)
            return jsonify({'status': 'success', 'message': f'File copied to {dst_name}', 'new_filename': dst_name}), HTTPStatus.OK
        else:
            content = user_data['csv'].get(file_name, None)
            if content is None:
                return jsonify({'status': 'error', 'message': f'Source file {file_name} not found'}), HTTPStatus.NOT_FOUND
            base, ext = os.path.splitext(file_name)
            files = list(user_data['csv'].keys())
            dst_name = get_next_filename(ext, files, base)
            user_data['csv'][dst_name] = content
            # Update cache
            update_file_metadata(dst_name, content)
            socketio.emit('update_csv')
            from user_data import save_user_data
            save_user_data(user_data)
            return jsonify({'status': 'success', 'message': f'File copied to {dst_name}', 'new_filename': dst_name}), HTTPStatus.OK
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred while copying the file'}), 500

@file_bp.route('/upload_file', methods=['POST'])
def upload_file():
    try:
        uploaded_file = request.files.get('file')
        mode = request.form.get('mode')
        tabletype = request.form.get('tabletype')

        if not uploaded_file or not tabletype:
            return jsonify({'status': 'error', 'message': 'File and tabletype are required'}), HTTPStatus.BAD_REQUEST

        filename = secure_filename(uploaded_file.filename)
        content = uploaded_file.read().decode('utf-8')
        user_data = get_user_data()
        message_suffix = ''

        if tabletype == '#json-table':
            if not mode:
                return jsonify({'status': 'error', 'message': 'Mode is required for JSON uploads'}), HTTPStatus.BAD_REQUEST
            if mode not in user_data['json']:
                user_data['json'][mode] = {}
            store = user_data['json'][mode]
            if filename in store:
                base, ext = os.path.splitext(filename)
                filename = get_next_filename(ext, list(store.keys()), base)
                message_suffix = f' (auto-renamed to avoid overwrite). New name is {filename}'
            store[filename] = content
            socketio.emit('update_json', {'mode': mode})
            from user_data import save_user_data
            save_user_data(user_data)
        else:
            store = user_data['csv']
            if filename in store:
                base, ext = os.path.splitext(filename)
                filename = get_next_filename(ext, list(store.keys()), base)
                message_suffix = f' (auto-renamed to avoid overwrite). New name is {filename}'
            store[filename] = content
            # Update cache
            update_file_metadata(filename, content)
            socketio.emit('update_csv')
            from user_data import save_user_data
            save_user_data(user_data)

        return jsonify({'status': 'success', 'message': f'File "{filename}" uploaded successfully{message_suffix}.', 'filename': filename}), HTTPStatus.OK
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred while uploading the file.'}), 500

@file_bp.route('/merge_csv', methods=['POST'])
def merge_csv():
    try:
        file1 = request.form.get('file1')
        file2 = request.form.get('file2')
        output_name = request.form.get('output_name')

        if not file1 or not file2 or not output_name:
            return jsonify({'status': 'error', 'message': 'Both files and output name are required'}), HTTPStatus.BAD_REQUEST

        if not output_name.endswith('.csv'):
            output_name += '.csv'

        user_data = get_user_data()
        content1 = user_data['csv'].get(file1)
        content2 = user_data['csv'].get(file2)

        if not content1:
            return jsonify({'status': 'error', 'message': f'File {file1} not found'}), HTTPStatus.NOT_FOUND
        if not content2:
            return jsonify({'status': 'error', 'message': f'File {file2} not found'}), HTTPStatus.NOT_FOUND

        success, result = merge_csv_contents(content1, content2)
        if success:
            user_data['csv'][output_name] = result
            # Update cache
            update_file_metadata(output_name, result)
            socketio.emit('update_csv')
            from user_data import save_user_data
            save_user_data(user_data)
            return jsonify({'status': 'success', 'message': f'Files merged successfully into {output_name}'}), HTTPStatus.OK
        else:
            return jsonify({'status': 'error', 'message': result}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'An unexpected error occurred while merging the files: {str(e)}'}), 500
