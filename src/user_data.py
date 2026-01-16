import uuid
from pathlib import Path
from flask import session
from typing import Dict

# ------------------------------------------------------------------
# 1. Global in-memory storage
# ------------------------------------------------------------------
USER_DATA: Dict[str, dict] = {}

# ------------------------------------------------------------------
# 2. Core helpers – defined in the same module as the data
# ------------------------------------------------------------------
def get_user_id() -> str:
    """Generate or retrieve session-based user_id."""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

def get_user_data() -> dict:
    uid = get_user_id()
    """Return mutable user data dict, creating if needed."""
    if uid not in USER_DATA:
        USER_DATA[uid] = {
            'csv': {},
            'json': {
                'kinetics': {},
                'point': {}
            },
            'drive': {
                'mode': 'guest',
                'authenticated': False,
                'folder_id': None,
                'folder_name': None,
                'credentials': None,
                'last_sync': None,
                'auto_sync_on_close': False,
                'file_mapping': {}
            }
        }
    return USER_DATA[uid]

# ------------------------------------------------------------------
# 3. File loaders
# ------------------------------------------------------------------
def _load_file(path: Path) -> str:
    """
    Load a CSV file and return its *raw content* as a single UTF-8 string.
    - Uses read().decode('utf-8')
    - Returns empty string if file missing or unreadable
    - Prints debug info
    """
    if not path.exists():
        print(f"[WARN] CSV file not found – skipping: {path}")
        return ""

    try:
        raw_bytes = path.read_bytes()
        content = raw_bytes.decode('utf-8')
        print(f"[INFO] Loaded raw CSV: {path} ({len(content)} characters)")
        return content

    except Exception as e:
        print(f"[ERROR] Failed to read {path}: {e}")
        # Optional: show hex preview for debugging
        try:
            preview = path.read_bytes()[:200]
            print(f"Preview (hex): {preview.hex()[:100]}...")
        except:
            pass
        return ""

# ------------------------------------------------------------------
# 4. Main init function – populates USER_DATA from files
# ------------------------------------------------------------------
def init_user_data(csv_dir: str | Path = "csv", json_dir: str | Path = "json", clear_existing: bool = False) -> None:
    csv_dir = Path(csv_dir)
    json_dir = Path(json_dir)
    user_data = get_user_data()

    if clear_existing:
        user_data['csv'].clear()
        user_data['json']['kinetics'].clear()
        user_data['json']['point'].clear()
    
    # Do NOT load defaults if we already have data 
    if user_data['csv'] or user_data['json']['kinetics'] or user_data['json']['point']:
        return user_data
    
    # Do NOT load defaults if we are in Connected mode (unless forcing clear_existing)
    if get_drive_mode() == 'connected' and not clear_existing:
        return user_data

    # --- CSV: multi.csv + single.csv ---
    for fname in ("multi.csv", "single.csv"):
        csv_data = _load_file(csv_dir / fname)
        if csv_data:
            user_data["csv"][fname] = csv_data

    # --- JSON: kinetics ---
    kinetics_path = json_dir / "exp_kinetics.json"
    kinetics_raw = _load_file(kinetics_path)

    if kinetics_raw is not None:
        user_data["json"]["kinetics"]["exp_kinetics.json"] = kinetics_raw

    # --- JSON: point ---
    point_path = json_dir / "exp_point.json"
    point_raw = _load_file(point_path)

    if point_raw is not None:
        user_data["json"]["point"]["exp_point.json"] = point_raw

    return user_data

# ------------------------------------------------------------------
# 5. Google Drive helpers
# ------------------------------------------------------------------
def get_drive_credentials(user_id: str = None):
    """Retrieve stored Drive credentials for user."""
    uid = user_id or get_user_id()
    user_data = get_user_data()
    return user_data.get('drive', {}).get('credentials')

def set_drive_credentials(credentials, user_id: str = None):
    """Store Drive credentials for user."""
    uid = user_id or get_user_id()
    user_data = get_user_data()
    user_data['drive']['credentials'] = credentials
    user_data['drive']['authenticated'] = True
    user_data['drive']['mode'] = 'connected'

def get_drive_folder(user_id: str = None):
    """Get selected Drive folder ID."""
    uid = user_id or get_user_id()
    user_data = get_user_data()
    return user_data.get('drive', {}).get('folder_id')

def set_drive_folder(folder_id: str, folder_name: str, user_id: str = None):
    """Set user's Drive folder."""
    uid = user_id or get_user_id()
    user_data = get_user_data()
    user_data['drive']['folder_id'] = folder_id
    user_data['drive']['folder_name'] = folder_name

def get_drive_mode(user_id: str = None):
    """Get current mode ('guest' or 'connected')."""
    uid = user_id or get_user_id()
    user_data = get_user_data()
    return user_data.get('drive', {}).get('mode', 'guest')

def set_drive_preference(key: str, value, user_id: str = None):
    """Update Drive preferences."""
    uid = user_id or get_user_id()
    user_data = get_user_data()
    user_data['drive'][key] = value

def is_auto_sync_enabled(user_id: str = None):
    """Check if auto-sync is enabled."""
    uid = user_id or get_user_id()
    user_data = get_user_data()
    return user_data.get('drive', {}).get('auto_sync_on_close', False)

def disconnect_drive(user_id: str = None):
    """Disconnect Drive and return to guest mode with default data."""
    uid = user_id or get_user_id()
    user_data = get_user_data()
    user_data['drive'] = {
        'mode': 'guest',
        'authenticated': False,
        'folder_id': None,
        'folder_name': None,
        'credentials': None,
        'last_sync': None,
        'auto_sync_on_close': False,
        'file_mapping': {}
    }
    # Restore default data
    init_user_data(clear_existing=True)