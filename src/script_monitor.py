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

def monitor_process(proc, log_path):
    """Monitor the subprocess for errors during runtime"""
    try:
        while proc.poll() is None:
            # Check log for errors
            error = check_log_for_errors(log_path)
            if error:
                return error
            # Small sleep to prevent busy waiting
            threading.Event().wait(0.5)
        
        # Process has finished, check if it ended with errors
        return check_log_for_errors(log_path) or "process_completed"
    except Exception as e:
        print(f"Monitoring error: {e}")
        return "monitoring_error"
