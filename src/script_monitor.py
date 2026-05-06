import os

def check_log_for_missed_read(log_path):
    """Returns True if the log shows HID data arriving before the session was established.

    This happens when the HID subprocess starts late and misses the metadata/header
    lines sent by the PyBadge, producing 'Unexpected line:' entries with no session start.
    """
    if not os.path.exists(log_path):
        return False
    with open(log_path, 'r') as f:
        content = f.read()
    return "Unexpected line:" in content and "New session started" not in content

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
