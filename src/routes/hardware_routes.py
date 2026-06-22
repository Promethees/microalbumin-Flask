from flask import Blueprint, jsonify
import os
import sys
import platform
import subprocess
import signal
import state
from script_monitor import check_log_for_errors, check_log_for_session_start
from file_path import is_reserved_data_folder_name, RESERVED_ARCHIVE_FOLDER
from validators import validate_json

hardware_bp = Blueprint('hardware', __name__)

# Data capture uses the CDC (USB serial) transport by default: a single logger
# subprocess (log_cdc_data.py) owns the serial port for the whole session — it
# sends the start commands, waits for the device ACKs, then reads the data
# stream on the same connection. Flask must NOT also open the port (one owner
# only). The device's keyboard-typing path is reserved as a manual fallback the
# user triggers with the device's Left button (see firmware serial_manager.py).


def clear_logs():
    try:
        with open(state.log_file, 'w', encoding='utf-8') as f:
            f.write("")
    except Exception:
        pass


def _logger_command(base_dir, base_name, timeout_sec, interval_sec):
    """Build the CDC logger subprocess command. CDC needs no elevated privileges.

    Frozen: there is no python interpreter or log_cdc_data.py on disk, so we
    re-invoke the app binary itself in --cdc-logger mode (sys.executable IS the
    binary; main.py dispatches the collector before Flask loads).
    Dev: run log_cdc_data.py with the running interpreter (which has pyserial)."""
    if getattr(sys, 'frozen', False):
        cmd = [sys.executable, '--cdc-logger']
    else:
        script_path = os.path.join(state.bundle_dir, 'log_cdc_data.py')
        if "window" in platform.system().lower():
            venv_python = os.path.join(state.script_dir, 'venv', 'Scripts', 'python.exe')
            python_exe = venv_python if os.path.exists(venv_python) else sys.executable
        else:
            python_exe = sys.executable or 'python3'
        cmd = [python_exe, script_path]
    cmd += ['--base-dir', base_dir, '--base-name', base_name]
    if timeout_sec is not None:
        cmd += ['--timeout-sec', str(float(timeout_sec))]
    if interval_sec is not None:
        cmd += ['--interval-sec', str(float(interval_sec))]
    return cmd


@hardware_bp.route('/run_script', methods=['POST'])
@validate_json({
    'subfolder': (str, '', False),
    'base_name': (str, 'colorimeter_data', False),
    'timeout_sec': (float, None, False),
    'interval_sec': (float, None, False)
})
def run_script(validated_data):
    if state.process and state.process.poll() is None:
        return jsonify({'status': 'failure', 'message': 'A script is already running'})

    subfolder = validated_data['subfolder'].strip()
    base_name = validated_data['base_name']
    timeout_sec = validated_data['timeout_sec']
    interval_sec = validated_data['interval_sec']

    # Subfolder must be a simple name with no path traversal
    if subfolder and any(c in subfolder for c in ('/', '\\', '..')):
        return jsonify({'status': 'failure', 'message': 'Invalid subfolder name'}), 400
    # "root" is reserved by the data-archive feature (see file_path.py).
    if subfolder and is_reserved_data_folder_name(subfolder):
        return jsonify({'status': 'failure', 'message': f"'{RESERVED_ARCHIVE_FOLDER}' is a reserved folder name and cannot be used"}), 400
    if any(c in base_name for c in ('/', '\\', '..')):
        return jsonify({'status': 'failure', 'message': 'Invalid base name'}), 400

    # Resolve and create the target directory under data/
    data_root = os.path.join(state.script_dir, 'data')
    if subfolder:
        abs_dir = os.path.normpath(os.path.join(data_root, subfolder))
        # Guard against path traversal that somehow escaped the name check
        if not abs_dir.startswith(data_root + os.sep) and abs_dir != data_root:
            return jsonify({'status': 'failure', 'message': 'Invalid subfolder'}), 400
        base_dir = abs_dir
    else:
        abs_dir = data_root
        base_dir = abs_dir

    os.makedirs(abs_dir, exist_ok=True)

    cmd = _logger_command(base_dir, base_name, timeout_sec, interval_sec)

    # Fresh log so device/session detection reflects only this run.
    clear_logs()

    try:
        with open(state.log_file, 'a', encoding='utf-8') as f:
            state.process = subprocess.Popen(
                cmd, stdout=f, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        try:
            # A missing device makes the logger exit almost immediately; give it
            # a brief window to surface that as device_not_found. A connected
            # device keeps the logger alive (it settles + handshakes), so this
            # times out and we report success.
            state.process.wait(timeout=2)
            error = check_log_for_errors(state.log_file)
            state.process = None
            if error == "device_not_found":
                return jsonify({'status': 'device_not_found', 'message': 'PyBadge device not connected. Please connect the device and try again.'})
            return jsonify({'status': 'failure', 'message': 'Failed to start reading session. Please check the device connection.'})
        except subprocess.TimeoutExpired:
            return jsonify({'status': 'success', 'message': 'Script is running'})
    except Exception as e:
        state.process = None
        return jsonify({'status': 'failure', 'message': f'Failed to start script: {str(e)}'})


@hardware_bp.route('/check_status', methods=['GET'])
def check_status():
    if state.process is None:
        return jsonify({'status': 'not_running', 'message': 'No process running'})

    error = check_log_for_errors(state.log_file)
    if error:
        state.process = None
        clear_logs()
        if error == "device_not_found":
            return jsonify({'status': 'device_not_found', 'message': 'PyBadge device not connected during runtime.'})
        return jsonify({'status': 'failure', 'message': 'Device communication error detected during runtime.'})

    if state.process.poll() is None:
        return jsonify({'status': 'running', 'message': 'Script is running'})

    # The logger exited: a clean end-of-session (device timeout / user stop)
    # always logs "New session started"; a handshake failure does not.
    started = check_log_for_session_start(state.log_file)
    state.process = None
    # Session is over — reset the log file here, the authoritative server-side
    # completion point. The frontend only clears logs via terminateScript()
    # (the fetchLogs/terminate path); when this status poll detects completion
    # first, that path never runs, so without this the log file is left dirty.
    clear_logs()
    if started:
        return jsonify({'status': 'success', 'message': 'Reading session completed.'})
    return jsonify({'status': 'failure', 'message': 'Reading session ended before any data was captured.'})


@hardware_bp.route('/terminate_script', methods=['POST'])
def terminate_script():
    if state.process is None or state.process.poll() is not None:
        return jsonify({'status': 'failure', 'message': 'No process running'})

    os_name = platform.system().lower()
    try:
        if "window" in os_name:
            # No POSIX process-group signalling: terminate the logger; closing
            # the port drops DTR, which the firmware detects to stop talking.
            state.process.terminate()
            try:
                state.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                state.process.kill()
            state.process = None
            return jsonify({'status': 'success'})

        # POSIX: SIGINT first lets the CDC logger's handler run — it sends "0"
        # to the device and closes the port before exiting. Escalate if it hangs.
        pgid = os.getpgid(state.process.pid)
        os.killpg(pgid, signal.SIGINT)
        try:
            state.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGTERM)
            try:
                state.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(pgid, signal.SIGKILL)
        state.process = None
        return jsonify({'status': 'success'})
    except ProcessLookupError:
        state.process = None
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': f'Error terminating process: {str(e)}'})


@hardware_bp.route('/get_logs', methods=['GET'])
def get_logs():
    if os.path.exists(state.log_file):
        with open(state.log_file, 'r', encoding='utf-8') as f:
            logs = f.read()
        return jsonify({'status': 'success', 'logs': logs})
    return jsonify({'status': 'success', 'logs': 'No logs available'})
