import os
import platform

# Global Process State
process = None
monitor_thread = None
args = None

# Paths
script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_file = os.path.join(script_dir, "log", "script_logs.txt")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
json_root_path = os.path.join(script_dir, "json")
report_root_path = os.path.join(script_dir, "report")
data_root_path = os.path.join(script_dir, "data")
os.makedirs(report_root_path, exist_ok=True)
os.makedirs(data_root_path, exist_ok=True)


os_name = platform.system().lower()
if "window" in os_name:
    delimiter = "\\\\"
else:
    delimiter = "/"

# Configuration
PRODUCTION_MODE = True
APP_VERSION = "1.0.6"

# Resend configuration
MAX_RESEND_ATTEMPTS = 3   # Maximum number of reading-request resend attempts
resend_attempt = 0         # Current resend attempt count for the active session
last_run_params = None     # Parameters from the most recent run_script call (for resending)
subprocess_start_time = None  # When the HID subprocess was last spawned
last_resend_time = None    # When the last resend was issued
