import os

def check_log_for_session_start(log_path):
    """Returns True if the log shows a measurement session was established.

    Used by the CDC reader path to distinguish a completed (or terminated)
    reading session from a handshake/connection failure where the logger
    exited before any data was captured.
    """
    if not os.path.exists(log_path):
        return False
    with open(log_path, 'r') as f:
        return "New session started" in f.read()


def check_log_for_end_reason(log_path):
    """Return why a completed reading session ended, for the UI announcement.

    'stopped' — manual stop on the device (Left button, firmware emits
    "SESSION STOPPED"); 'timeout' — session timeout ("SESSION TIMEOUT");
    None — neither sentinel present (e.g. the user terminated from the UI).
    """
    if not os.path.exists(log_path):
        return None
    with open(log_path, 'r') as f:
        content = f.read()
    if "SESSION STOPPED" in content:
        return "stopped"
    if "SESSION TIMEOUT" in content:
        return "timeout"
    return None


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
