from flask import Blueprint, jsonify, request
import os
import platform
import subprocess
import signal
import state
from script_monitor import check_log_for_errors
from send_command import connect_to_device, send_command_and_wait_ack
from validators import validate_json

hardware_bp = Blueprint('hardware', __name__)

def clear_logs():
    try:
        with open(state.log_file, 'w') as f:
            f.write("")
    except Exception:
        pass

@hardware_bp.route('/run_script', methods=['POST'])
@validate_json({
    'base_dir': (str, 'data', False),
    'base_name': (str, 'colorimeter_data', False),
    'timeout_sec': (float, None, False),
    'interval_sec': (float, None, False)
})
def run_script(validated_data):
    os_name = platform.system().lower()
    
    if state.process and state.process.poll() is None:
        return jsonify({'status': 'failure', 'message': 'A script is already running'})
    
    base_dir = validated_data['base_dir']
    base_name = validated_data['base_name']
    timeout_sec = validated_data['timeout_sec']
    interval_sec = validated_data['interval_sec']
    print("Interval seconds is ", interval_sec)
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
        
        with open(state.log_file, 'a') as f:
            state.process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True, start_new_session=True)    
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
                os.killpg(os.getpgid(state.process.pid), signal.SIGTERM)
                state.process.wait(timeout=3)
                state.process = None
                return jsonify({'status': 'success'})
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(state.process.pid), signal.SIGKILL)
                state.process = None
                return jsonify({'status': 'success'})
                
    except Exception as e:
        if 'pybadge' in locals():
            pybadge.close()
        return jsonify({'status': 'failure', 'message': f'Error terminating process: {str(e)}'})

@hardware_bp.route('/get_logs', methods=['GET'])
def get_logs():
    if os.path.exists(state.log_file):
        with open(state.log_file, 'r') as f:
            logs = f.read()
        return jsonify({'status': 'success', 'logs': logs})
    return jsonify({'status': 'success', 'logs': 'No logs available'})
