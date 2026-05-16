from flask import Blueprint, jsonify
import os
import platform
import subprocess
import signal
import time
import state
from script_monitor import check_log_for_errors, check_log_for_missed_read
from send_command import connect_to_device, send_command_and_wait_ack
from validators import validate_json

hardware_bp = Blueprint('hardware', __name__)

# Seconds after subprocess launch before the first missed-read check
_MISSED_READ_CHECK_DELAY = 5.0
# Seconds to wait after a resend before rechecking (gives PyBadge time to respond)
_RESEND_COOLDOWN = 5.0

def clear_logs():
    try:
        with open(state.log_file, 'w', encoding='utf-8') as f:
            f.write("")
    except Exception:
        pass

@hardware_bp.route('/run_script', methods=['POST'])
@validate_json({
    'subfolder': (str, '', False),
    'base_name': (str, 'colorimeter_data', False),
    'timeout_sec': (float, None, False),
    'interval_sec': (float, None, False)
})
def run_script(validated_data):
    os_name = platform.system().lower()

    if state.process and state.process.poll() is None:
        return jsonify({'status': 'failure', 'message': 'A script is already running'})

    subfolder = validated_data['subfolder'].strip()
    base_name = validated_data['base_name']
    timeout_sec = validated_data['timeout_sec']
    interval_sec = validated_data['interval_sec']

    # Subfolder must be a simple name with no path traversal
    if subfolder and any(c in subfolder for c in ('/', '\\', '..')):
        return jsonify({'status': 'failure', 'message': 'Invalid subfolder name'}), 400
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
    print("Interval seconds is ", interval_sec)

    state.last_run_params = {'timeout_sec': timeout_sec, 'interval_sec': interval_sec}
    state.resend_attempt = 0
    state.subprocess_start_time = None
    state.last_resend_time = None

    try:
        pybadge = connect_to_device()
        print(f"Connected to PyBadge at {pybadge.port}")
        
        commands = [
            "1\n",
            f"TIMEOUT:{float(timeout_sec) if timeout_sec is not None else -1}\n",
            f"INTERVAL:{float(interval_sec) if interval_sec is not None else -1}\n"
        ]
        expected_acks = ["ACK_START", "ACK_TIMEOUT", "ACK_INTERVAL"]
        error_acks = ["ERR_START", "ERR_TIMEOUT", "ERR_INTERVAL"]
        
        success, error_msg = send_command_and_wait_ack(pybadge, commands, expected_acks, error_acks)
        if not success:
            pybadge.close()
            return jsonify({'status': 'failure', 'message': error_msg})
        
        if "window" in os_name:
            venv_python = os.path.join(state.script_dir, 'venv', 'Scripts', 'python.exe')
            script_path = os.path.join(state.script_dir, 'log_hid_data_pyusb.py')
            cmd = [venv_python, script_path, '--base-dir', base_dir, '--base-name', base_name]
        else:
            script_path = os.path.join(state.script_dir, 'log_hid_data.py')
            cmd = ['sudo', 'python3', script_path, '--base-dir', base_dir, '--base-name', base_name]
        
        with open(state.log_file, 'a', encoding='utf-8') as f:
            state.process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            state.subprocess_start_time = time.time()
            try:
                state.process.wait(timeout=1)
                error = check_log_for_errors(state.log_file)
                if error:
                    state.process = None
                    clear_logs()
                    if error == "device_not_found":
                        print("Device not found in log, returning error")
                        return jsonify({'status': 'device_not_found', 'message': 'PyBadge device not connected. Please connect the device and try again.'})
                    elif error == "input_endpoint_error":
                        return jsonify({'status': 'failure', 'message': 'Failed to find input endpoint. Please check the device connection.'})
                return jsonify({'status': 'success', 'message': 'Script is still running'})
            except subprocess.TimeoutExpired:
                return jsonify({'status': 'success', 'message': 'Script is still running'})
                
    except Exception as e:
        state.process = None
        if 'pybadge' in locals():
            pybadge.close()
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
        elif error == "input_endpoint_error":
            return jsonify({'status': 'failure', 'message': 'Input endpoint error detected during runtime.'})
    
    if state.process.poll() is None:
        # Check whether the HID subprocess missed early characters and needs a resend.
        if state.subprocess_start_time is not None and state.last_run_params is not None:
            now = time.time()
            initial_wait_done = (now - state.subprocess_start_time) > _MISSED_READ_CHECK_DELAY

            if state.last_resend_time is not None:
                in_cooldown = (now - state.last_resend_time) < _RESEND_COOLDOWN
                if in_cooldown:
                    return jsonify({
                        'status': 'resending',
                        'message': (
                            f'Resend attempt {state.resend_attempt}/{state.MAX_RESEND_ATTEMPTS}: '
                            'waiting for device to respond...'
                        )
                    })

            if initial_wait_done and check_log_for_missed_read(state.log_file):
                if state.resend_attempt >= state.MAX_RESEND_ATTEMPTS:
                    state.process = None
                    return jsonify({
                        'status': 'failure',
                        'message': (
                            f'Could not capture data after {state.MAX_RESEND_ATTEMPTS} '
                            'resend attempts. Please restart the reading.'
                        )
                    })

                state.resend_attempt += 1
                attempt = state.resend_attempt
                print(f"Missed read detected — resending reading request (attempt {attempt}/{state.MAX_RESEND_ATTEMPTS})")
                clear_logs()
                try:
                    pybadge = connect_to_device()
                    params = state.last_run_params
                    commands = [
                        "1\n",
                        f"TIMEOUT:{float(params['timeout_sec']) if params['timeout_sec'] is not None else -1}\n",
                        f"INTERVAL:{float(params['interval_sec']) if params['interval_sec'] is not None else -1}\n"
                    ]
                    success, error_msg = send_command_and_wait_ack(
                        pybadge, commands,
                        ["ACK_START", "ACK_TIMEOUT", "ACK_INTERVAL"],
                        ["ERR_START", "ERR_TIMEOUT", "ERR_INTERVAL"]
                    )
                    pybadge.close()
                    state.last_resend_time = time.time()
                    if success:
                        return jsonify({
                            'status': 'resending',
                            'message': (
                                f'Reading request resent (attempt {attempt}/{state.MAX_RESEND_ATTEMPTS}). '
                                'Waiting for device data...'
                            )
                        })
                    return jsonify({
                        'status': 'failure',
                        'message': f'Resend attempt {attempt} failed: {error_msg}'
                    })
                except Exception as e:
                    if 'pybadge' in locals():
                        pybadge.close()
                    state.last_resend_time = time.time()
                    return jsonify({
                        'status': 'failure',
                        'message': f'Error during resend attempt {attempt}: {str(e)}'
                    })

        return jsonify({'status': 'running', 'message': 'Script is running'})
    else:
        error = check_log_for_errors(state.log_file)
        state.process = None
        if error:
            if error == "device_not_found":
                return jsonify({'status': 'device_not_found', 'message': 'PyBadge device was not found.'})
            elif error == "input_endpoint_error":
                return jsonify({'status': 'failure', 'message': 'Failed to find input endpoint.'})
        return jsonify({'status': 'success', 'message': 'Script still running, waiting for device to send next report'})
    
@hardware_bp.route('/terminate_script', methods=['POST'])
def terminate_script():
    if state.process is None or state.process.poll() is not None:
        return jsonify({'status': 'failure', 'message': 'No process running'})

    try:
        pybadge = connect_to_device()
        print(f"Connected to PyBadge at {pybadge.port}")

        success, error_msg = send_command_and_wait_ack(pybadge, ["0\n"], ["ACK_STOP"], ["ERR_STOP"])
        pybadge.close()
        if not success:
            return jsonify({'status': 'failure', 'message': error_msg})
        
        os_name = platform.system().lower()
        if "window" in os_name:
            state.process.terminate()
            try:
                state.process.wait(timeout=3)
                state.process = None
                return jsonify({'status': 'success'})
            except subprocess.TimeoutExpired:
                state.process.kill()
                state.process = None
                return jsonify({'status': 'success'})
        else:
            try:
                pgid = os.getpgid(state.process.pid)
                # SIGINT first — triggers KeyboardInterrupt in the HID script,
                # allowing its finally block to close the device and log file,
                # which prevents semaphore leaks.
                os.killpg(pgid, signal.SIGINT)
                try:
                    state.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Then SIGTERM
                    os.killpg(pgid, signal.SIGTERM)
                    try:
                        state.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        # Finally SIGKILL as last resort
                        os.killpg(pgid, signal.SIGKILL)
                state.process = None
                return jsonify({'status': 'success'})
            except ProcessLookupError:
                state.process = None
                return jsonify({'status': 'success'})
                
    except Exception as e:
        if 'pybadge' in locals():
            pybadge.close()
        return jsonify({'status': 'failure', 'message': f'Error terminating process: {str(e)}'})

@hardware_bp.route('/get_logs', methods=['GET'])
def get_logs():
    if os.path.exists(state.log_file):
        with open(state.log_file, 'r', encoding='utf-8') as f:
            logs = f.read()
        return jsonify({'status': 'success', 'logs': logs})
    return jsonify({'status': 'success', 'logs': 'No logs available'})
