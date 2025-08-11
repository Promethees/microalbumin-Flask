import os

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
