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

os_name = platform.system().lower()
if "window" in os_name:
    delimiter = "\\\\"
else:
    delimiter = "/"

# Configuration
PRODUCTION_MODE = True
