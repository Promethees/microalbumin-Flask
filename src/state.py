import os
import sys
import shutil
import platform

# Global Process State
process = None
monitor_thread = None
args = None
# True while the live reading session is paused (host asked the device to hold
# off streaming — see /pause_reading). Purely a UI-resync aid: the authoritative
# pause lives in the device + logger, but a page reload mid-run has no other way
# to learn the session is paused. Reset on every run start and session end.
reading_paused = False


# ── Frozen-vs-source path resolution ─────────────────────────────────────────
# The app ships two ways:
#   • Source/dev: run `python main.py` from a checkout. Assets and writable data
#     all live in the project root (historical behaviour — unchanged).
#   • Frozen: a PyInstaller onedir binary with NO .py on disk. Read-only assets
#     (templates/, static/, json/ defaults, guide_training.json, sample_data/)
#     are bundled and resolve from sys._MEIPASS; writable user data
#     (data/, json/, report/, log/, user_settings.json, activation.json, .env)
#     lives in a VISIBLE, user-owned folder so people can find and open their
#     measurements/curves/reports directly: Documents/EasyOKAPI on Windows &
#     macOS, ~/EasyOKAPI on Linux. It sits outside the install dir, so it
#     survives update / reinstall / recovery untouched. Older frozen builds put
#     this under a hidden app-data dir (%LOCALAPPDATA% etc.);
#     _migrate_legacy_app_data() moves that content here once, so in-app updates
#     migrate too (the installer migrates as well, for re-run-installer updates).
#     Bundled json defaults + sample_data are seeded only on explicit first-run
#     consent (demo_prompt_pending / seed_demo_content), never silently.
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


def _windows_documents_dir():
    r"""Resolve the user's real Documents folder, honouring redirection (OneDrive).

    Reads the same shell-folder registry value NSIS's $DOCUMENTS uses, so the
    installer and the running app always agree on one path. Falls back to
    ~/Documents when the lookup fails.
    """
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
        ) as key:
            val, _ = winreg.QueryValueEx(key, 'Personal')
        val = os.path.expandvars(val)
        if val:
            return val
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


def _user_data_base():
    """Parent of the visible EasyOKAPI data folder, per OS (frozen builds only)."""
    system = platform.system().lower()
    if system.startswith('win') or system == 'nt':
        return _windows_documents_dir()
    if system == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Documents')
    return os.path.expanduser('~')  # linux: ~/EasyOKAPI


def _default_app_data_dir():
    """The DEFAULT writable per-user data root — a VISIBLE folder the user can
    open directly.

    Frozen: <Documents>/EasyOKAPI (win/mac) or ~/EasyOKAPI (linux). Source/dev:
    the project root (unchanged). This is the location the user can relocate
    AWAY from via the data-root pointer (see _read_dataroot_override); it always
    holds the pointer file even when the live data lives elsewhere.
    """
    if not _is_frozen():
        return _find_project_root()
    return os.path.join(_user_data_base(), 'EasyOKAPI')


# ── User-selectable data root (frozen builds) ────────────────────────────────
# The data root can be relocated by the user from App Settings. Its location
# cannot be stored in user_settings.json because that file lives INSIDE the data
# root (chicken-and-egg). Instead a tiny pointer file `.easyokapi_dataroot` is
# kept BESIDE the default data folder (i.e. in <Documents> / <home>, the parent
# of the default EasyOKAPI folder, deterministic per OS). Keeping it OUTSIDE the
# data folder means the pointer — and therefore the link to the relocated data —
# survives the user deleting the (now-empty) default folder, so both the app and
# the uninstaller can still find the real data. On Windows this parent is exactly
# NSIS's $DOCUMENTS, so the uninstaller reads the same file.
# Source/dev runs ignore the pointer entirely and always use the project root.
_DATAROOT_POINTER = '.easyokapi_dataroot'
# Windows writes the pointer as UTF-16LE with a BOM: NSIS has no UTF-8 file I/O
# (FileWrite/FileRead are ANSI), so UTF-16 is the only encoding the installer,
# the uninstaller and the app all round-trip a non-ASCII path through. Elsewhere
# the uninstallers `cat` it, so it stays UTF-8. Readers sniff the BOM.
_DATAROOT_POINTER_ENCODING = 'utf-16' if os.name == 'nt' else 'utf-8'


def _decode_pointer(raw):
    """Decode pointer-file bytes: UTF-16 by BOM, else UTF-8 (BOM optional)."""
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return raw.decode('utf-16')
    return raw.decode('utf-8-sig')


def _dataroot_pointer_path():
    # Anchor on the PARENT of the default data folder, so the pointer is a sibling
    # of <Documents>/EasyOKAPI rather than living inside it. Use the module-level
    # default_data_root once it exists (set just before script_dir at import).
    base = globals().get('default_data_root') or _default_app_data_dir()
    return os.path.join(os.path.dirname(base), _DATAROOT_POINTER)


def _read_dataroot_override():
    """Return the user's custom data root from the pointer file, or None.

    Frozen builds only. The pointer holds one absolute path; it is honoured only
    when it is absolute and not inside the read-only bundle. The directory is
    created if missing so a relocated root survives a wiped target. Best-effort:
    any problem falls back to the default root.
    """
    if not _is_frozen():
        return None
    try:
        path = _dataroot_pointer_path()
        if not os.path.isfile(path):
            return None
        with open(path, 'rb') as f:
            target = _decode_pointer(f.read()).strip()
        if not target:
            return None
        target = os.path.abspath(os.path.expanduser(os.path.expandvars(target)))
        bundle = _bundle_dir()
        if target == bundle or target.startswith(bundle + os.sep):
            return None  # never point the data root inside the read-only bundle
        os.makedirs(target, exist_ok=True)
        return target
    except Exception:
        return None


def _app_data_dir():
    """Writable per-user data root, honouring a user-selected override (frozen)."""
    default = _default_app_data_dir()
    if not _is_frozen():
        return default
    override = _read_dataroot_override()
    if override and os.path.abspath(override) != os.path.abspath(default):
        return override
    return default


def _legacy_app_data_dirs():
    """Hidden roots used by earlier frozen builds — migrated into the visible one once."""
    if not _is_frozen():
        return []
    system = platform.system().lower()
    if system.startswith('win') or system == 'nt':
        base = os.environ.get('LOCALAPPDATA')
        return [os.path.join(base, 'EasyOKAPI')] if base else []
    if system == 'darwin':
        return [os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'EasyOKAPI')]
    base = os.environ.get('XDG_DATA_HOME') or os.path.join(
        os.path.expanduser('~'), '.local', 'share')
    return [os.path.join(base, 'EasyOKAPI')]


bundle_dir = _bundle_dir()
default_data_root = _default_app_data_dir()  # where the .dataroot pointer lives
script_dir = _app_data_dir()                 # honours the pointer (frozen only)
os.makedirs(script_dir, exist_ok=True)


def _migrate_legacy_app_data():
    """One-time MOVE of user data from an older hidden app-data dir into script_dir.

    Early frozen builds stored data under a hidden dir (%LOCALAPPDATA%\\EasyOKAPI,
    ~/Library/Application Support/EasyOKAPI, ~/.local/share/EasyOKAPI). We copy it
    into the visible data folder once, then REMOVE the hidden source. Removing it
    is important: the "already migrated" marker lives in script_dir, so if a user
    clears their visible data folder the marker is gone too — and a hidden source
    left behind would silently resurrect the old data on the next launch. The
    hidden location is pure legacy (the current build only ever uses script_dir),
    so deleting it is safe. Best-effort; never blocks startup.
    """
    if bundle_dir == script_dir:
        return
    try:
        legacy_dirs = [l for l in _legacy_app_data_dirs()
                       if os.path.abspath(l) != os.path.abspath(script_dir) and os.path.isdir(l)]
        if not legacy_dirs:
            return
        marker = os.path.join(script_dir, '.migrated_appdata')
        if not os.path.exists(marker):
            for legacy in legacy_dirs:
                for name in ('data', 'json', 'report', 'log'):
                    src = os.path.join(legacy, name)
                    dst = os.path.join(script_dir, name)
                    if os.path.isdir(src) and not (os.path.isdir(dst) and os.listdir(dst)):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                for fname in ('activation.json', 'user_settings.json', '.env'):
                    s, d = os.path.join(legacy, fname), os.path.join(script_dir, fname)
                    if os.path.isfile(s) and not os.path.exists(d):
                        shutil.copy2(s, d)
            with open(marker, 'w', encoding='utf-8') as f:
                f.write('1')
        # Always remove the hidden legacy folder(s) once we know the data has been
        # migrated (marker present), so they can never resurrect cleared data.
        for legacy in legacy_dirs:
            shutil.rmtree(legacy, ignore_errors=True)
    except Exception:
        pass  # best-effort: never block startup


_migrate_legacy_app_data()


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
# Create the writable working folders empty. The bundled json defaults and
# sample measurements are NOT seeded automatically — they are offered as an
# opt-in on first run (see demo_prompt_pending()/seed_demo_content()).
os.makedirs(json_root_path, exist_ok=True)
os.makedirs(os.path.join(json_root_path, "kinetics"), exist_ok=True)
os.makedirs(os.path.join(json_root_path, "point"), exist_ok=True)
os.makedirs(report_root_path, exist_ok=True)
os.makedirs(data_root_path, exist_ok=True)


# ── First-run demo content (opt-in) ──────────────────────────────────────────
# A frozen build bundles default calibration curves (json/) and sample
# measurements (sample_data/). Rather than seeding them silently, the app asks
# the user once on first launch whether to load them. The choice is recorded so
# the prompt never reappears.
_DEMO_MARKER = os.path.join(script_dir, ".demo_prompt_done")

# One-shot sentinel set just before a restart (data-folder relocation or applied
# update) and consumed on the next index render to tell the client to come up in
# the default display (kinetics mode, default sections, no saved UI overrides).
# Lives beside the .dataroot pointer in default_data_root — NOT script_dir —
# because a relocation restart changes script_dir, and the new process must still
# find the flag at a location that does not move.
_RESET_DISPLAY_MARKER = os.path.join(default_data_root, ".reset_display_pending")


def _dir_has_content(path):
    if not os.path.isdir(path):
        return False
    with os.scandir(path) as it:
        return any(True for _ in it)


def _has_user_content():
    """True if the user already has saved curves or measurements."""
    return (_dir_has_content(os.path.join(json_root_path, "kinetics"))
            or _dir_has_content(os.path.join(json_root_path, "point"))
            or _dir_has_content(data_root_path))


def demo_prompt_pending():
    """Show the first-run 'load demo content?' prompt?

    Only for a frozen build that hasn't answered yet, has no user content, and
    actually has bundled demo content to offer. Always False in source/dev.
    """
    if not _is_frozen() or os.path.exists(_DEMO_MARKER) or _has_user_content():
        return False
    return (os.path.isdir(os.path.join(bundle_dir, "json"))
            or os.path.isdir(os.path.join(bundle_dir, "sample_data")))


def mark_demo_prompt_done():
    """Record that the first-run prompt was answered, so it never reappears."""
    try:
        with open(_DEMO_MARKER, "w", encoding="utf-8") as f:
            f.write("1")
    except Exception:
        pass


def seed_demo_content():
    """Copy the bundled default curves and sample measurements into writable data.

    Bundled json/{kinetics,point}/*.json → json/{kinetics,point}/, and
    sample_data/*.csv → data/sample_data/. Copies file-by-file and never clobbers
    anything the user already has — so the empty kinetics/point folders created at
    startup do NOT block the copy (the previous _seed_writable_from_bundle skipped
    when the json/ folder was non-empty, which it always was). Best-effort.
    """
    if bundle_dir == script_dir:
        return
    # Default calibration curves (walk the whole bundled json/ tree).
    bundle_json = os.path.join(bundle_dir, "json")
    if os.path.isdir(bundle_json):
        for root, _dirs, files in os.walk(bundle_json):
            rel = os.path.relpath(root, bundle_json)
            dst_dir = json_root_path if rel == "." else os.path.join(json_root_path, rel)
            os.makedirs(dst_dir, exist_ok=True)
            for fname in files:
                d = os.path.join(dst_dir, fname)
                if not os.path.exists(d):
                    try:
                        shutil.copy2(os.path.join(root, fname), d)
                    except Exception:
                        pass
    # Sample measurements → data/sample_data/.
    src = os.path.join(bundle_dir, "sample_data")
    if os.path.isdir(src):
        dst = os.path.join(data_root_path, "sample_data")
        os.makedirs(dst, exist_ok=True)
        try:
            for name in os.listdir(src):
                if name.lower().endswith(".csv"):
                    s = os.path.join(src, name)
                    if os.path.isfile(s) and not os.path.exists(os.path.join(dst, name)):
                        shutil.copy2(s, os.path.join(dst, name))
        except Exception:
            pass


def mark_reset_display_pending():
    """Flag that the next page load should come up in the default display.

    Called just before a restart (data-folder relocation or applied update) so the
    relaunched instance opens cleanly in kinetics mode with default sections instead
    of restoring the previous tab's localStorage layout. Best-effort.
    """
    try:
        os.makedirs(os.path.dirname(_RESET_DISPLAY_MARKER), exist_ok=True)
        with open(_RESET_DISPLAY_MARKER, "w", encoding="utf-8") as f:
            f.write("1")
    except Exception:
        pass


def consume_reset_display_pending():
    """Return True (and clear the flag) if a default-display reset is pending.

    One-shot: the sentinel is deleted on read so only the first load after a
    restart resets; subsequent manual refreshes keep the user's layout.
    """
    try:
        if os.path.exists(_RESET_DISPLAY_MARKER):
            os.remove(_RESET_DISPLAY_MARKER)
            return True
    except Exception:
        pass
    return False


os_name = platform.system().lower()
if "window" in os_name:
    delimiter = "\\\\"
else:
    delimiter = "/"

# Configuration
PRODUCTION_MODE = True
APP_VERSION = "1.5.10"

# True for an installed PyInstaller build (downloaded via the installer), False
# when run from source (`python main.py` / setup-3-run.command). Gates dev-only
# conveniences — notably the .env GROQ_API_KEY AI bypass in src/routes/ai_routes.py,
# which must NOT be honoured in an installed build (a real activation token is
# mandatory there).
IS_FROZEN = _is_frozen()

# Address bug reports are sent to (used by the "Report a Bug" button to
# pre-fill a mailto: link). This is the maintainer's inbox, not a per-machine
# user preference, so it lives here as a project constant.
MAINTAINER_EMAIL = "tqmthong@gmail.com"
