from flask import Blueprint, request, jsonify, session
from http import HTTPStatus
import os
import re
import json
from pathlib import Path
from werkzeug.utils import secure_filename
from user_data import get_user_data, get_user_id, save_user_data, user_data_session, update_file_metadata
from export_data import get_user_lock
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
                    except (ValueError, IndexError, TypeError):
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
        if not filename:
            return jsonify({'status': 'error', 'message': 'Invalid filename'}), HTTPStatus.BAD_REQUEST
        ext = os.path.splitext(filename)[1].lower()
        if tabletype == '#json-table' and ext != '.json':
            return jsonify({'status': 'error', 'message': 'Only .json files are allowed'}), HTTPStatus.BAD_REQUEST
        if tabletype != '#json-table' and ext != '.csv':
            return jsonify({'status': 'error', 'message': 'Only .csv files are allowed'}), HTTPStatus.BAD_REQUEST
        try:
            content = uploaded_file.read().decode('utf-8')
        except UnicodeDecodeError:
            return jsonify({'status': 'error', 'message': 'File must be UTF-8 encoded text'}), HTTPStatus.BAD_REQUEST
        uid = get_user_id()
        message_suffix = ''

        with get_user_lock(uid):
            user_data = get_user_data()
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
                save_user_data(user_data)
                socketio.emit('update_json', {'mode': mode})
            else:
                store = user_data['csv']
                if filename in store:
                    base, ext = os.path.splitext(filename)
                    filename = get_next_filename(ext, list(store.keys()), base)
                    message_suffix = f' (auto-renamed to avoid overwrite). New name is {filename}'
                store[filename] = content
                update_file_metadata(filename, content)
                save_user_data(user_data)
                socketio.emit('update_csv')

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
            save_user_data(user_data)
            return jsonify({'status': 'success', 'message': f'Files merged successfully into {output_name}'}), HTTPStatus.OK
        else:
            return jsonify({'status': 'error', 'message': result}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'An unexpected error occurred while merging the files: {str(e)}'}), 500


# ── Report helpers ─────────────────────────────────────────────────────────────

def _safe_subject_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("Subject name is required")
    if any(x in name for x in ("..", "/", "\\", "\x00")):
        raise ValueError("Invalid subject name")
    return name

def _get_report_store(user_data: dict) -> dict:
    if 'report' not in user_data:
        user_data['report'] = {}
    return user_data['report']

# ── Report Routes ──────────────────────────────────────────────────────────────

@file_bp.route('/get_report_subjects', methods=['GET'])
def get_report_subjects():
    user_data = get_user_data()
    store = _get_report_store(user_data)
    subjects = sorted(store.keys())
    return jsonify({'status': 'success', 'subjects': subjects})


@file_bp.route('/get_report_items', methods=['GET'])
def get_report_items():
    subject = request.args.get('subject')
    if not subject:
        return jsonify({'status': 'error', 'message': 'No subject provided'}), 400
    try:
        subject = _safe_subject_name(subject)
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

    user_data = get_user_data()
    store = _get_report_store(user_data)
    if subject not in store:
        return jsonify({'status': 'error', 'message': 'Subject not found'}), 404

    subject_data = store[subject]
    items_store = subject_data.get('items', {})
    saved_order = subject_data.get('order', [])

    items = []
    for fname, entry in items_store.items():
        items.append({
            'filename': fname,
            'metadata': entry.get('metadata', {}),
            'path': fname
        })

    if saved_order:
        order_map = {name: i for i, name in enumerate(saved_order)}
        items.sort(key=lambda x: order_map.get(x['filename'], len(saved_order)))
    else:
        items.sort(key=lambda x: x.get('metadata', {}).get('timestamp', x['filename']))

    return jsonify({'status': 'success', 'items': items})


@file_bp.route('/get_calibration_json_list', methods=['GET'])
def get_calibration_json_list():
    mode = request.args.get('mode', '').strip().lower()
    if mode not in ('kinetics', 'point'):
        return jsonify({'status': 'error', 'message': 'Invalid mode'}), 400
    user_data = get_user_data()
    items = sorted(user_data.get('json', {}).get(mode, {}).keys())
    return jsonify({'status': 'success', 'items': items})


@file_bp.route('/export_to_report', methods=['POST'])
def export_to_report():
    data = request.get_json(silent=True) or {}
    subject = data.get('subject', '').strip()
    filename = data.get('file_path', '').strip()
    metadata = data.get('metadata', {})

    if not subject or not filename:
        return jsonify({'status': 'error', 'message': 'subject and file_path are required'}), 400
    try:
        subject = _safe_subject_name(subject)
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

    user_data = get_user_data()
    content = user_data['csv'].get(filename)
    if content is None:
        return jsonify({'status': 'error', 'message': f"File '{filename}' not found"}), 404

    with user_data_session() as ud:
        store = _get_report_store(ud)
        if subject not in store:
            store[subject] = {'items': {}, 'order': []}

        items_store = store[subject]['items']
        # Prevent overwrite — generate unique dest filename
        dest = filename
        base, ext = Path(filename).stem, Path(filename).suffix
        counter = 1
        while dest in items_store:
            dest = f"{base}_{counter}{ext}"
            counter += 1

        items_store[dest] = {'content': content, 'metadata': metadata}
        order = store[subject].get('order', [])
        if dest not in order:
            order.append(dest)
        store[subject]['order'] = order

    return jsonify({'status': 'success', 'message': f"Exported '{filename}' to subject '{subject}' as '{dest}'"})


@file_bp.route('/save_report_item_order', methods=['POST'])
def save_report_item_order():
    data = request.get_json(silent=True) or {}
    subject = data.get('subject', '').strip()
    order = data.get('order', [])
    if not subject:
        return jsonify({'status': 'error', 'message': 'subject is required'}), 400
    try:
        subject = _safe_subject_name(subject)
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

    with user_data_session() as ud:
        store = _get_report_store(ud)
        if subject not in store:
            return jsonify({'status': 'error', 'message': 'Subject not found'}), 404
        store[subject]['order'] = order

    return jsonify({'status': 'success'})


@file_bp.route('/delete_report_item', methods=['POST'])
def delete_report_item():
    data = request.get_json(silent=True) or {}
    subject = data.get('subject', '').strip()
    filename = data.get('filename', '').strip()
    if not subject or not filename:
        return jsonify({'status': 'error', 'message': 'subject and filename are required'}), 400
    try:
        subject = _safe_subject_name(subject)
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

    with user_data_session() as ud:
        store = _get_report_store(ud)
        if subject not in store:
            return jsonify({'status': 'error', 'message': 'Subject not found'}), 404
        items = store[subject].get('items', {})
        if filename not in items:
            return jsonify({'status': 'error', 'message': 'Item not found'}), 404
        del items[filename]
        order = store[subject].get('order', [])
        if filename in order:
            order.remove(filename)
        store[subject]['order'] = order

    return jsonify({'status': 'success', 'message': f"Removed '{filename}' from '{subject}'"})


@file_bp.route('/delete_report_subject', methods=['POST'])
def delete_report_subject():
    data = request.get_json(silent=True) or {}
    subject = data.get('subject', '').strip()
    try:
        subject = _safe_subject_name(subject)
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

    with user_data_session() as ud:
        store = _get_report_store(ud)
        if subject not in store:
            return jsonify({'status': 'error', 'message': 'Subject not found'}), 404
        del store[subject]

    return jsonify({'status': 'success', 'message': f"Deleted subject '{subject}'"})


@file_bp.route('/copy_report_subject', methods=['POST'])
def copy_report_subject():
    data = request.get_json(silent=True) or {}
    subject = data.get('subject', '').strip()
    try:
        subject = _safe_subject_name(subject)
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

    with user_data_session() as ud:
        store = _get_report_store(ud)
        if subject not in store:
            return jsonify({'status': 'error', 'message': 'Subject not found'}), 404
        base = f"{subject}_copy"
        new_name = base
        counter = 1
        while new_name in store:
            new_name = f"{base}_{counter}"
            counter += 1
        import copy
        store[new_name] = copy.deepcopy(store[subject])

    return jsonify({'status': 'success', 'message': f"Copied subject '{subject}'", 'new_subject': new_name})


@file_bp.route('/rename_report_subject', methods=['POST'])
def rename_report_subject():
    data = request.get_json(silent=True) or {}
    old_subject = data.get('old_subject', '').strip()
    new_subject = data.get('new_subject', '').strip()
    try:
        old_subject = _safe_subject_name(old_subject)
        new_subject = _safe_subject_name(new_subject)
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

    with user_data_session() as ud:
        store = _get_report_store(ud)
        if old_subject not in store:
            return jsonify({'status': 'error', 'message': 'Subject not found'}), 404
        if new_subject in store:
            return jsonify({'status': 'error', 'message': 'New subject name already exists'}), 409
        store[new_subject] = store.pop(old_subject)

    return jsonify({'status': 'success', 'message': f"Renamed '{old_subject}' to '{new_subject}'"})


@file_bp.route('/merge_report_subjects', methods=['POST'])
def merge_report_subjects():
    data = request.get_json(silent=True) or {}
    subjects = data.get('subjects', [])
    output_subject = data.get('output_subject', '').strip()

    if len(subjects) < 2:
        return jsonify({'status': 'error', 'message': 'Please select at least 2 subjects to merge'}), 400
    try:
        safe_subjects = [_safe_subject_name(s) for s in subjects]
        output_subject = _safe_subject_name(output_subject)
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

    with user_data_session() as ud:
        store = _get_report_store(ud)
        for sub in safe_subjects:
            if sub not in store:
                return jsonify({'status': 'error', 'message': f"Subject not found: {sub}"}), 404
        if output_subject in store:
            return jsonify({'status': 'error', 'message': 'Output subject already exists'}), 409

        merged_items = {}
        merged_order = []
        for sub in safe_subjects:
            sub_data = store[sub]
            sub_order = sub_data.get('order', list(sub_data.get('items', {}).keys()))
            for fname in sub_order:
                if fname not in sub_data.get('items', {}):
                    continue
                entry = sub_data['items'][fname]
                dest = fname
                base, ext = Path(fname).stem, Path(fname).suffix
                counter = 1
                while dest in merged_items:
                    dest = f"{base}_{sub}_{counter}{ext}"
                    counter += 1
                merged_items[dest] = entry
                merged_order.append(dest)

        store[output_subject] = {'items': merged_items, 'order': merged_order}

    return jsonify({'status': 'success', 'message': f"Merged {len(safe_subjects)} subjects into '{output_subject}'"})


@file_bp.route('/save_report', methods=['POST'])
def save_report():
    data = request.get_json(silent=True) or {}
    filename = data.get('filename', 'report')
    html_content = data.get('html_content', '')
    if not html_content:
        return jsonify({'status': 'error', 'message': 'html_content is required'}), 400
    if not filename.endswith('.html'):
        filename += '.html'
    with user_data_session() as ud:
        if 'reports' not in ud:
            ud['reports'] = {}
        base = Path(filename).stem
        dest = filename
        counter = 1
        while dest in ud['reports']:
            dest = f"{base}_{counter}.html"
            counter += 1
        ud['reports'][dest] = html_content
    return jsonify({'status': 'success', 'message': f"Report saved as '{dest}'"})

