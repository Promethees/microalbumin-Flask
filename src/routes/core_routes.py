from flask import Blueprint, jsonify, make_response, render_template, request, send_file
import os
import io
import time
import signal
import threading
import zipfile
import state
import user_settings as _user_settings
import data_root as _data_root
import event_logger
import i18n as _i18n
from file_path import DATA_ROOT, get_data_subfolders, CONCEN_UNITS
from range import get_range_input
from mode import get_mode_input
from quantity import get_quantity_input
from file import (get_file_list, get_file_meta, build_meta, sort_file_names,
                  ensure_concen_unit_in_dir, ensure_cal_units_in_dir,
                  build_csv_identity, build_json_identity)

core_bp = Blueprint('core', __name__)

@core_bp.route('/ping')
def ping():
    return jsonify({'status': 'success'})

@core_bp.route('/clear_logs', methods=['POST'])
def clear_logs():
    try:
        with open(state.log_file, 'w', encoding='utf-8') as f:
            f.write("")
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

@core_bp.route('/clear_cache', methods=['POST'])
def clear_cache():
    try:
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

@core_bp.route('/')
def index():
    range_input = get_range_input()
    mode_input = get_mode_input()
    quantity_input = get_quantity_input()
    user_settings = _user_settings.load()
    file_sort_order = user_settings.get("file_sort_order", "date_desc")
    time_tag_format = user_settings.get("time_tag_format", "iso")
    ui_lang = _i18n.normalize_lang(user_settings.get("ui_language", "en"))
    ui_strings = _i18n.load_catalog(ui_lang)
    file_meta = get_file_meta(DATA_ROOT, time_format=time_tag_format)
    file_list = sort_file_names(get_file_list(DATA_ROOT), file_meta, file_sort_order)
    cal_json_dir = os.path.join(state.json_root_path, "kinetics")
    # NB: the on-disk back-fill runs in /get_json_cal (fired on mode/folder select),
    # not here — the index render stays read-only. build_json_identity still normalizes
    # legacy JSONs for the first-paint badge.
    cal_json_meta = get_file_meta(cal_json_dir, "*.json", time_format=time_tag_format)
    cal_json_list = sort_file_names(get_file_list(cal_json_dir, "*.json"), cal_json_meta, file_sort_order)
    file_identity = build_csv_identity(DATA_ROOT, file_list)
    cal_json_identity = build_json_identity(cal_json_dir, cal_json_list)

    try:
        with open(state.log_file, 'w', encoding='utf-8') as f:
            f.write("")
    except:
        pass

    event_logger.cleanup_old_logs()
    event_logger.append('session', 'start')
    response = make_response(render_template('index.html',
                         title="Easy OKAPI",
                         data_root=DATA_ROOT,
                         report_root=state.report_root_path,
                         json_root=state.json_root_path,
                         range_input=range_input,
                         mode_input=mode_input,
                         quantity_input=quantity_input,
                         file_list=file_list,
                         file_meta=file_meta,
                         file_identity=file_identity,
                         file_sort_order=file_sort_order,
                         cal_json_list=cal_json_list,
                         cal_json_meta=cal_json_meta,
                         cal_json_identity=cal_json_identity,
                         delimiter=state.delimiter,
                         production_mode=state.PRODUCTION_MODE,
                         app_version=state.APP_VERSION,
                         maintainer_email=state.MAINTAINER_EMAIL,
                         demo_prompt_pending=state.demo_prompt_pending(),
                         user_settings=user_settings,
                         concen_units=CONCEN_UNITS,
                         is_frozen=state.IS_FROZEN,
                         reset_display=state.consume_reset_display_pending(),
                         data_root_info=_data_root.get_info(),
                         ui_lang=ui_lang,
                         ui_strings=ui_strings))
    return response


@core_bp.route('/api/first-run/seed', methods=['POST'])
def first_run_seed():
    """Act on the first-run demo-content prompt.

    Body: {"load": true|false}. When true, seed the bundled default calibration
    curves and sample measurements into the user's writable data. Either way the
    choice is recorded so the prompt never reappears.
    """
    data = request.get_json(silent=True) or {}
    if data.get('load'):
        state.seed_demo_content()
    state.mark_demo_prompt_done()
    return jsonify({'status': 'success', 'loaded': bool(data.get('load'))})

def delayed_termination():
    time.sleep(5) 
    # Use SIGTERM for all platforms and modes. The server in main.py has signal handlers
    # to gracefully detect SIGTERM and execute atexit hooks natively, protecting parent wrapper scripts.
    os.kill(os.getpid(), signal.SIGTERM)

@core_bp.route('/shutdown', methods=['POST'])
def shutdown():
    threading.Thread(target=delayed_termination).start()
    data = request.get_json()
    mode = data.get('mode', 'light') if data else 'light'
    return render_template('goodbye.html', production_mode=state.PRODUCTION_MODE, mode=mode)

@core_bp.route('/browse', methods=['POST'])
def browse():
    new_path = request.form.get('path')
    if not new_path:
        return jsonify({'status': 'error', 'message': 'Path is required'}), 400
    abs_path = os.path.abspath(new_path)
    data_root = state.data_root_path
    report_root = state.report_root_path
    in_data = abs_path == data_root or abs_path.startswith(data_root + os.sep)
    in_report = abs_path == report_root or abs_path.startswith(report_root + os.sep)
    if not (in_data or in_report):
        return jsonify({'status': 'error', 'message': 'Invalid directory'})
    if not os.path.isdir(abs_path):
        return jsonify({'status': 'error', 'message': 'Directory not found'})
    # Backfill the ConcenUnit metadata line into legacy CSVs in this folder as it
    # is selected/parsed (idempotent, best-effort) before stat-ing for mtimes, so
    # the Modified column reflects any rewrite. Only for data-root folders.
    if in_data:
        ensure_concen_unit_in_dir(abs_path)
    file_list = get_file_list(abs_path)
    time_tag_format = _user_settings.load().get("time_tag_format", "iso")
    file_meta = get_file_meta(abs_path, time_format=time_tag_format)
    files_identity = build_csv_identity(abs_path, file_list) if in_data else {}
    return jsonify({'status': 'success', 'path': abs_path, 'files': file_list,
                    'files_meta': file_meta, 'files_identity': files_identity})

@core_bp.route('/get_data_folders', methods=['GET'])
def get_data_folders():
    folders = get_data_subfolders()
    return jsonify({'status': 'success', 'folders': folders})

@core_bp.route('/browse_export', methods=['GET'])
def browse_export():
    path = request.args.get('path')
    if not path:
        return jsonify({'exists': False, 'error': 'No path provided'}), 400
    exists = os.path.exists(path)
    return jsonify({'exists': exists})

@core_bp.route('/get_json_cal', methods=['GET'])
def get_json_cal():
    mode = request.args.get('mode', '').strip().lower()
    if mode not in ('kinetics', 'point'):
        return jsonify({'status': 'success', 'files': []})
    json_path = os.path.join(state.json_root_path, mode)
    os.makedirs(json_path, exist_ok=True)
    # Back-fill identity units into legacy calibration JSONs as the list is fetched
    # (idempotent, best-effort), mirroring the CSV back-fill on /browse.
    ensure_cal_units_in_dir(json_path)
    json_files = get_file_list(json_path, "*.json")
    time_tag_format = _user_settings.load().get("time_tag_format", "iso")
    files_meta = get_file_meta(json_path, "*.json", time_format=time_tag_format)
    files_identity = build_json_identity(json_path, json_files)
    return jsonify({'status': 'success', 'files': json_files,
                    'files_meta': files_meta, 'files_identity': files_identity})

@core_bp.route('/settings', methods=['GET'])
def get_settings():
    return jsonify({'status': 'success', 'settings': _user_settings.load()})


@core_bp.route('/settings', methods=['POST'])
def post_settings():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'No JSON data'}), 400
    if _user_settings.save(data):
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Could not save settings'}), 500


@core_bp.route('/data_root', methods=['GET'])
def get_data_root():
    return jsonify({'status': 'success', **_data_root.get_info()})


@core_bp.route('/data_root', methods=['POST'])
def post_data_root():
    """Validate a proposed data-folder change **without** moving anything (dry run).

    The actual copy/move is deferred to ``POST /data_root/restart`` so the user can
    confirm first and a cancel leaves the data exactly where it was (no revert
    needed). Returns the resolved target and whether committing would move or copy.
    Relocating only makes sense for an installed build — a source run always uses the
    project root (see src/data_root.py)."""
    if not state.IS_FROZEN:
        return jsonify({'status': 'error',
                        'message': 'The data folder can only be changed in an installed build.'}), 400
    # Don't move data out from under a running data-collection process.
    if state.process and state.process.poll() is None:
        return jsonify({'status': 'error',
                        'message': 'Cannot change the data folder while the data collection process is running'}), 423
    data = request.get_json(silent=True) or {}
    try:
        if data.get('reset'):
            new_path, moved = _data_root.preview_reset()
        elif 'path' in data:
            new_path, moved = _data_root.preview_data_root(data['path'])
        else:
            return jsonify({'status': 'error', 'message': 'No path provided'}), 400
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    return jsonify({'status': 'success', 'path': new_path,
                    'moved': moved, 'restart_required': True})


@core_bp.route('/data_root/restart', methods=['POST'])
def restart_for_data_root():
    """Commit the data-folder change, then relaunch the app in place to adopt it.

    This is where the move actually happens (the ``POST /data_root`` step is only a
    dry run), so the same body — ``{path}`` to relocate or ``{reset: true}`` — is
    re-sent here. After the copy/move we reuse the update path's relauncher
    (``update_service.restart_after_delay``): mac/linux exec the same image in place,
    Windows spawns a detached relauncher that waits for the port to free and starts a
    fresh hidden instance. The browser is handed ``restarting.html``, which polls
    ``/ping`` and reloads once the new instance is serving on the same port — so the
    tab refreshes itself into the new data location. The location is read from the
    pointer file at import time, which is why a restart is required at all.

    Frozen-only and ``@423 LOCKED`` while the data-collection process runs, matching
    ``POST /data_root`` (a source run never relocates; an in-flight capture must not
    be killed by a restart)."""
    if not state.IS_FROZEN:
        return jsonify({'status': 'error',
                        'message': 'The data folder can only be changed in an installed build.'}), 400
    if state.process and state.process.poll() is None:
        return jsonify({'status': 'error',
                        'message': 'Cannot change the data folder while the data collection process is running'}), 423
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'light')
    try:
        if data.get('reset'):
            new_path, moved = _data_root.reset_to_default()
        elif 'path' in data:
            new_path, moved = _data_root.set_data_root(data['path'])
        else:
            return jsonify({'status': 'error', 'message': 'No path provided'}), 400
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Could not move data folder: {e}'}), 500
    event_logger.append('settings', 'data_root', {'path': new_path, 'moved': moved})
    state.mark_reset_display_pending()
    import update_service
    update_service.restart_after_delay()
    return render_template('restarting.html', production_mode=state.PRODUCTION_MODE,
                           mode=mode, new_path=new_path)


def _win_drives():
    """List existing drive roots (Windows) as folder entries."""
    import string
    drives = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.exists(root):
            drives.append({'name': root, 'path': root})
    return drives


def _dir_listing(path, is_win):
    """Immediate non-hidden subdirectories of `path`, plus parent navigation."""
    entries = []
    try:
        for name in sorted(os.listdir(path), key=str.lower):
            if name.startswith('.'):
                continue
            full = os.path.join(path, name)
            try:
                if os.path.isdir(full):
                    entries.append({'name': name, 'path': full})
            except OSError:
                continue
    except OSError:
        return {'status': 'error', 'message': 'This folder cannot be opened.'}, 403
    parent = os.path.dirname(path)
    if parent == path:  # already at a filesystem root
        parent = '::drives' if is_win else None
    return {'status': 'success', 'path': path, 'parent': parent,
            'dirs': entries, 'home': os.path.expanduser('~'), 'is_drives': False}, 200


@core_bp.route('/browse_dirs', methods=['GET'])
def browse_dirs():
    """Read-only directory browser for the data-folder picker (settings)."""
    import platform
    is_win = platform.system().lower().startswith('win')
    raw = request.args.get('path', '')
    if is_win and raw == '::drives':
        return jsonify({'status': 'success', 'path': '', 'parent': None,
                        'dirs': _win_drives(), 'home': os.path.expanduser('~'),
                        'is_drives': True})
    if not raw:
        raw = os.path.expanduser('~')
    path = os.path.abspath(os.path.expanduser(raw))
    if not os.path.isdir(path):
        return jsonify({'status': 'error', 'message': 'Not a folder'}), 400
    body, code = _dir_listing(path, is_win)
    return jsonify(body), code


@core_bp.route('/event_log', methods=['GET'])
def get_event_log():
    return jsonify({'status': 'success', 'events': event_logger.read_all()})


@core_bp.route('/event_log', methods=['POST'])
def post_event_log():
    data = request.get_json(silent=True) or {}
    event_type = str(data.get('type', '')).strip()
    action = str(data.get('action', '')).strip()
    if not event_type or not action:
        return jsonify({'status': 'error', 'message': 'type and action are required'}), 400
    event_logger.append(event_type, action, data.get('details'))
    return jsonify({'status': 'success'})


# Cap on how many event-log files a single bug-report attachment may bundle.
MAX_EVENT_LOG_SELECTION = 5


def _events_root():
    return os.path.join(state.script_dir, 'log', 'events')


def _resolve_event_log_path(rel_path):
    """Resolve a client-supplied relative event-log path against the events root.
    Returns the absolute path if it is a real .jsonl file safely inside the root,
    otherwise None (guards against path traversal)."""
    root = _events_root()
    rel = str(rel_path).replace('\\', '/').strip().lstrip('/')
    if not rel.endswith('.jsonl'):
        return None
    abs_path = os.path.normpath(os.path.join(root, rel))
    if not (abs_path == root or abs_path.startswith(root + os.sep)):
        return None
    if not os.path.isfile(abs_path):
        return None
    return abs_path


@core_bp.route('/list_event_log_files', methods=['GET'])
def list_event_log_files():
    """List available event-log session files (log/events/**/*.jsonl), newest
    first, so the user can pick which ones to attach to a bug report."""
    root = _events_root()
    files = []
    if os.path.isdir(root):
        for dirpath, _dirs, names in os.walk(root):
            for name in names:
                if not name.endswith('.jsonl'):
                    continue
                abs_path = os.path.join(dirpath, name)
                rel_path = os.path.relpath(abs_path, root).replace(os.sep, '/')
                try:
                    st = os.stat(abs_path)
                    files.append({'path': rel_path, 'size': st.st_size, 'modified': st.st_mtime})
                except OSError:
                    pass
    files.sort(key=lambda f: f['modified'], reverse=True)
    return jsonify({'status': 'success', 'files': files})


@core_bp.route('/download_event_logs', methods=['GET', 'POST'])
def download_event_logs():
    """Bundle event-log session files (log/events/**/*.jsonl) into an in-memory
    zip the user can attach to a bug-report email.

    GET  → bundles all event logs (legacy "attach everything" behaviour).
    POST → bundles only the files listed in JSON {"files": [...]} (max
           MAX_EVENT_LOG_SELECTION), used by the "Report a Bug" file picker.

    If nothing matches, the zip still contains a short note so the user always
    has a file to attach."""
    events_root = _events_root()

    selected_paths = None
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        requested = data.get('files')
        if not isinstance(requested, list) or not requested:
            return jsonify({'status': 'error', 'message': 'No files selected'}), 400
        if len(requested) > MAX_EVENT_LOG_SELECTION:
            return jsonify({'status': 'error',
                            'message': f'Select at most {MAX_EVENT_LOG_SELECTION} files'}), 400
        selected_paths = []
        for rel in requested:
            abs_path = _resolve_event_log_path(rel)
            if abs_path is None:
                return jsonify({'status': 'error', 'message': f'Invalid file: {rel}'}), 400
            selected_paths.append(abs_path)

    buf = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        if selected_paths is not None:
            for abs_path in selected_paths:
                arcname = os.path.join('events', os.path.relpath(abs_path, events_root))
                try:
                    zf.write(abs_path, arcname)
                    file_count += 1
                except OSError:
                    pass
        elif os.path.isdir(events_root):
            for dirpath, _dirs, files in os.walk(events_root):
                for name in files:
                    if not name.endswith('.jsonl'):
                        continue
                    abs_path = os.path.join(dirpath, name)
                    # Keep the date-folder structure inside the archive.
                    arcname = os.path.join('events', os.path.relpath(abs_path, events_root))
                    try:
                        zf.write(abs_path, arcname)
                        file_count += 1
                    except OSError:
                        pass
        if file_count == 0:
            zf.writestr('events/README.txt',
                        'No event log files were found for this installation.\n')

    buf.seek(0)
    event_logger.append('bug_report', 'download_logs', {'file_count': file_count})
    filename = f"easyokapi-logs-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    return send_file(
        buf,
        mimetype='application/zip',
        as_attachment=True,
        attachment_filename=filename,
    )


@core_bp.route('/get_report_subjects', methods=['GET'])
def get_report_subjects():
    report_path = state.report_root_path
    if os.path.exists(report_path):
        # List only directories
        subjects = [d for d in os.listdir(report_path) if os.path.isdir(os.path.join(report_path, d))]
        subjects.sort()
        time_tag_format = _user_settings.load().get("time_tag_format", "iso")
        subjects_meta = build_meta(report_path, subjects, time_format=time_tag_format)
        return jsonify({'status': 'success', 'subjects': subjects, 'subjects_meta': subjects_meta})
    return jsonify({'status': 'error', 'message': "Report directory not found"})
