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

    'disconnected' — the device dropped mid-run and never came back inside the
    logger's reconnect window (log_cdc_data.DISCONNECTED_SENTINEL), so the file
    holds a real but shortened series; 'stopped' — manual stop on the device
    (Left button, firmware emits "SESSION STOPPED"); 'timeout' — session timeout
    ("SESSION TIMEOUT"); None — no sentinel present (e.g. the user terminated
    from the UI).

    Disconnection is checked first: a run that reconnected and then lost the
    device for good can carry an earlier sentinel from the same log, and what
    the operator needs told is how it actually ended.
    """
    if not os.path.exists(log_path):
        return None
    with open(log_path, 'r') as f:
        content = f.read()
    if "SESSION DISCONNECTED" in content:
        return "disconnected"
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
