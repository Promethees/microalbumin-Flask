import os
import sys
import shutil
import platform

# Global Process State
process = None
monitor_thread = None
args = None


# ── Frozen-vs-source path resolution ─────────────────────────────────────────
# The app ships two ways:
#   • Source/dev: run `python main.py` from a checkout. Assets and writable data
#     all live in the project root (historical behaviour — unchanged).
#   • Frozen: a PyInstaller onedir binary with NO .py on disk. Read-only assets
#     (templates/, static/, json/ defaults, guide_training.json, sample_data/)
#     are bundled and resolve from sys._MEIPASS; writable user data
#     (data/, json/, report/, log/, user_settings.json, activation.json, .env)
#     lives in a per-user app-data dir so it survives update / reinstall /
#     recovery. These four folders are exactly what update_service._PRESERVE
#     keeps, and the only things the user sees and owns.
#
# Two roots make that split explicit:
#   bundle_dir  → read-only bundled assets    (== project root in dev)
#   script_dir  → writable per-user data root (== project root in dev)

def _is_frozen():
    return getattr(sys, 'frozen', False)


def _find_project_root():
    # Walk up from src/ (or code/src/ on Windows installs) until main.py is found.
    d = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _ in range(3):
        if os.path.isfile(os.path.join(d, 'main.py')):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return d


def _bundle_dir():
    """Root of read-only bundled assets."""
    if _is_frozen():
        # PyInstaller sets _MEIPASS to the dir holding the bundled data files
        # (the onedir _internal folder). Fall back to the executable's dir.
        return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
    return _find_project_root()


def _app_data_dir():
    """Writable per-user data root. Preserved across updates and reinstalls."""
    if not _is_frozen():
        return _find_project_root()
    system = platform.system().lower()
    if system.startswith('win') or system == 'nt':
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    elif system == 'darwin':
        base = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support')
    else:  # linux and others
        base = os.environ.get('XDG_DATA_HOME') or os.path.join(
            os.path.expanduser('~'), '.local', 'share')
    return os.path.join(base, 'EasyOKAPI')


bundle_dir = _bundle_dir()
script_dir = _app_data_dir()
os.makedirs(script_dir, exist_ok=True)


def _seed_writable_from_bundle(name):
    """Copy a bundled default tree/file into the writable root on first run.

    Only seeds when the writable target is missing or empty, so user edits are
    never clobbered on a later launch. No-op in dev (bundle == writable root).
    """
    if bundle_dir == script_dir:
        return
    src = os.path.join(bundle_dir, name)
    dst = os.path.join(script_dir, name)
    if not os.path.exists(src):
        return
    try:
        if os.path.isdir(src):
            if os.path.isdir(dst) and os.listdir(dst):
                return  # user already has content — leave it alone
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            if os.path.exists(dst):
                return
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    except Exception:
        pass  # best-effort: a failed seed must not block startup


# Paths (all writable data hangs off script_dir)
log_file = os.path.join(script_dir, "log", "script_logs.txt")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
json_root_path = os.path.join(script_dir, "json")
report_root_path = os.path.join(script_dir, "report")
data_root_path = os.path.join(script_dir, "data")
# Seed bundled default calibration JSONs into the writable json/ on first run,
# then create the writable working folders.
_seed_writable_from_bundle("json")
os.makedirs(json_root_path, exist_ok=True)
os.makedirs(report_root_path, exist_ok=True)
os.makedirs(data_root_path, exist_ok=True)


os_name = platform.system().lower()
if "window" in os_name:
    delimiter = "\\\\"
else:
    delimiter = "/"

# Configuration
PRODUCTION_MODE = True
APP_VERSION = "1.1.8"

# Address bug reports are sent to (used by the "Report a Bug" button to
# pre-fill a mailto: link). This is the maintainer's inbox, not a per-machine
# user preference, so it lives here as a project constant.
MAINTAINER_EMAIL = "tqmthong@gmail.com"
