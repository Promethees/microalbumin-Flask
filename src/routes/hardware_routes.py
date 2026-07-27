from flask import Blueprint, jsonify, Response, stream_with_context
import os
import sys
import platform
import subprocess
import signal
import state
import live_stream
from script_monitor import check_log_for_errors, check_log_for_session_start, check_log_for_end_reason
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


def clear_current_output_marker():
    """Blank log/current_output.txt at the start of a run.

    The logger writes this marker (the live CSV path) only once it has received
    the device's full header (log_cdc_data.handle_main_header). Until then the
    file still holds the *previous* session's path, so "View live data" — which
    is enabled the instant run_script succeeds — would resolve /api/current_output
    to a stale file from a prior run. Blanking it makes that endpoint return 204
    ("still writing"), so the client keeps polling until the new session's header
    lands. Kept in sync with file_routes.api_current_output / log_cdc_data.py."""
    try:
        marker_path = os.path.join(state.script_dir, 'log', 'current_output.txt')
        os.makedirs(os.path.dirname(marker_path), exist_ok=True)
        with open(marker_path, 'w', encoding='utf-8') as f:
            f.write("")
    except Exception:
        pass


def _measure_trigger_path():
    """Path of the manual-capture trigger file. /measure_point drops it and the
    running logger (log_cdc_data.CDCDataCollector) polls + consumes it to send a
    MEASURE command to the device. Kept in sync with log_cdc_data.trigger_path."""
    return os.path.join(state.script_dir, 'log', 'measure_trigger.txt')


def clear_measure_trigger():
    """Remove any stale manual-measure trigger at the start of a run so the first
    MEASURE reflects a real button press, not a leftover from a prior session."""
    try:
        path = _measure_trigger_path()
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _control_trigger_path():
    """Path of the pause/resume trigger file. Same IPC shape as the measure
    trigger (Flask cannot touch the serial port — the logger owns it), but the
    file holds the DESIRED STATE token ("PAUSE" / "RESUME") rather than being a
    bare flag: an unconsumed write is simply overwritten, so last press wins,
    which is exactly the right semantics for two opposite commands.
    Kept in sync with log_cdc_data.control_path."""
    return os.path.join(state.script_dir, 'log', 'control_trigger.txt')


def clear_control_trigger():
    """Drop any stale pause/resume request and clear the paused flag, so a new
    run never starts mid-pause because of a leftover from the previous session."""
    state.reading_paused = False
    try:
        path = _control_trigger_path()
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _request_pause_state(paused):
    """Shared body of /pause_reading and /resume_reading: drop the control
    trigger the running logger polls and forwards to the device."""
    if state.process is None or state.process.poll() is not None:
        return jsonify({'status': 'failure', 'message': 'No reading session is running'}), 409
    try:
        path = _control_trigger_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('PAUSE' if paused else 'RESUME')
        state.reading_paused = bool(paused)
        return jsonify({
            'status': 'success',
            'paused': state.reading_paused,
            'message': 'Reading paused' if paused else 'Reading resumed',
        })
    except Exception as e:
        verb = 'pause' if paused else 'resume'
        return jsonify({'status': 'failure', 'message': f'Failed to {verb} reading: {str(e)}'}), 500


def _logger_command(base_dir, base_name, timeout_sec, interval_sec, axis="time", manual=False):
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
    cmd += ['--axis', 'turn' if axis == 'turn' else 'time']
    if manual:
        cmd += ['--manual']
    return cmd


@hardware_bp.route('/run_script', methods=['POST'])
@validate_json({
    'subfolder': (str, '', False),
    'base_name': (str, 'colorimeter_data', False),
    'timeout_sec': (float, None, False),
    'interval_sec': (float, None, False),
    'axis': (str, 'time', False),
    'manual': (bool, False, False)
})
def run_script(validated_data):
    if state.process and state.process.poll() is None:
        return jsonify({'status': 'failure', 'message': 'A script is already running'})

    subfolder = validated_data['subfolder'].strip()
    base_name = validated_data['base_name']
    timeout_sec = validated_data['timeout_sec']
    interval_sec = validated_data['interval_sec']
    axis = 'turn' if str(validated_data.get('axis', 'time')).strip().lower() == 'turn' else 'time'
    # Manual point-mode capture: device idles and emits one row per /measure_point.
    # A manual reading is a turn, so manual forces the turn axis regardless of axis.
    manual = bool(validated_data.get('manual', False))
    if manual:
        axis = 'turn'

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

    cmd = _logger_command(base_dir, base_name, timeout_sec, interval_sec, axis, manual)

    # Fresh log so device/session detection reflects only this run.
    clear_logs()
    # Stale-marker guard: clear the live-file marker so "View live data" can't
    # resolve to the previous session's CSV before this run writes its header.
    clear_current_output_marker()
    # Drop any leftover manual-measure trigger so the first press is a real one.
    clear_measure_trigger()
    # Same for a leftover pause/resume request — a new run always starts running.
    clear_control_trigger()

    try:
        with open(state.log_file, 'a', encoding='utf-8') as f:
            state.process = subprocess.Popen(
                cmd, stdout=f, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        try:
            # A missing device makes the logger exit almost immediately
            # (connect_to_device scans the ports and raises BEFORE any settle
            # delay), so a short window is enough to surface device_not_found. A
            # connected device keeps the logger alive (it settles + handshakes),
            # so this times out and we report success — and the shorter wait lets
            # the client start its timer/polling ~1.5s sooner.
            state.process.wait(timeout=0.5)
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


@hardware_bp.route('/measure_point', methods=['POST'])
def measure_point():
    """Manual point-mode capture: request one on-demand reading from the device.

    Flask cannot write to the serial port (the logger subprocess owns it), so we
    drop a trigger file the running logger polls and forwards as a MEASURE command
    (log_cdc_data._check_measure_trigger). Only valid while a session is running."""
    if state.process is None or state.process.poll() is not None:
        return jsonify({'status': 'failure', 'message': 'No reading session is running'}), 409
    try:
        path = _measure_trigger_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('1')
        return jsonify({'status': 'success', 'message': 'Measurement requested'})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': f'Failed to request measurement: {str(e)}'}), 500


@hardware_bp.route('/pause_reading', methods=['POST'])
def pause_reading():
    """Pause a live reading session: hold off the device's interval streaming
    without ending the run. Only valid while a session is running."""
    return _request_pause_state(True)


@hardware_bp.route('/resume_reading', methods=['POST'])
def resume_reading():
    """Resume a paused reading session (see /pause_reading)."""
    return _request_pause_state(False)


@hardware_bp.route('/stream_session', methods=['GET'])
def stream_session():
    """SSE tail of the running session: new CSV rows + new log text, pushed.

    Replaces the client's 500 ms ``/get_data`` chart poll and 2 s ``/get_logs``
    poll for the duration of a run (see src/live_stream.py). Deliberately does
    NOT own the run-end transition: it emits an ``end`` event and closes, and the
    client calls /check_status, which remains the single place that decides why a
    session finished and clears the log.
    """
    return Response(
        stream_with_context(live_stream.iter_session_events()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            # Belt-and-braces against a buffering intermediary; the app is local,
            # but a user-configured proxy would otherwise hold every frame.
            'X-Accel-Buffering': 'no',
        },
    )


@hardware_bp.route('/check_status', methods=['GET'])
def check_status():
    if state.process is None:
        return jsonify({'status': 'not_running', 'message': 'No process running'})

    error = check_log_for_errors(state.log_file)
    if error:
        state.process = None
        state.reading_paused = False
        clear_logs()
        if error == "device_not_found":
            return jsonify({'status': 'device_not_found', 'message': 'PyBadge device not connected during runtime.'})
        return jsonify({'status': 'failure', 'message': 'Device communication error detected during runtime.'})

    if state.process.poll() is None:
        # `paused` lets a reloaded page resync its Pause/Resume controls with a
        # run that is already on hold.
        return jsonify({'status': 'running', 'message': 'Script is running', 'paused': state.reading_paused})

    # The logger exited: a clean end-of-session (device timeout / user stop)
    # always logs "New session started"; a handshake failure does not.
    started = check_log_for_session_start(state.log_file)
    # Why it ended (read BEFORE clear_logs) so the UI can announce a device-button
    # stop distinctly from a timeout.
    reason = check_log_for_end_reason(state.log_file)
    state.process = None
    state.reading_paused = False
    # Session is over — reset the log file here, the authoritative server-side
    # completion point. The frontend only clears logs via terminateScript()
    # (the fetchLogs/terminate path); when this status poll detects completion
    # first, that path never runs, so without this the log file is left dirty.
    clear_logs()
    if started:
        message = {
            'stopped': 'Session stopped manually on the device.',
            'timeout': 'Session ended due to timeout.',
        }.get(reason, 'Reading session completed.')
        return jsonify({'status': 'success', 'message': message})
    return jsonify({'status': 'failure', 'message': 'Reading session ended before any data was captured.'})


@hardware_bp.route('/terminate_script', methods=['POST'])
def terminate_script():
    state.reading_paused = False
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
