import uuid
import json
import pandas as pd
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
def init_user_data(csv_dir: str | Path = "csv", json_dir: str | Path = "json") -> None:
    csv_dir = Path(csv_dir)
    json_dir = Path(json_dir)
    user_data = get_user_data()
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