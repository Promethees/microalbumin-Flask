import os
import threading

def check_log_for_errors(log_path):
    """Check the log file for specific error patterns"""
    if not os.path.exists(log_path):
        return None
    
    with open(log_path, 'r') as f:
        content = f.read()
        if "PyBadge not found" in content:
            return "device_not_found"
        elif "Failed to find input endpoint. Exiting." in content:
            return "input_endpoint_error"
    return None

def check_log_for_timeout_msg(log_path):
    """Check the log file for specific error patterns"""
    if not os.path.exists(log_path):
        return None
    
    with open(log_path, 'r') as f:
        content = f.read()
        if "SESSION TIMEOUT" in content:
            return "SESSION TIMEOUT"
    return None

def monitor_process(proc, log_path, event_queue):
    try:
        while proc.poll() is None:
            # Check log for errors
            error = check_log_for_errors(log_path)
            if error:
                print(f"Monitor: Detected error '{error}'")
                event_queue.put("terminate")
                break

            # Check for session timeout/end
            timeout_signal = check_log_for_timeout_msg(log_path)
            if timeout_signal:
                print(f"Monitor: Detected '{timeout_signal}'")
                event_queue.put("terminate")
                break
    except Exception as e:
        print(f"Error in monitor_process: {e}")

