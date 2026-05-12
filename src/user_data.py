import uuid
import json
import os
from pathlib import Path
from threading import Lock
from collections import OrderedDict
from flask import session
from typing import Dict, Optional, Any
from contextlib import contextmanager

try:
    import redis
except ImportError:
    redis = None

from config import Config

# ------------------------------------------------------------------
# 1. Redis Initialization
# ------------------------------------------------------------------
# Connect to Redis if REDIS_URL is provided, otherwise fallback to in-memory
redis_client: Optional[Any] = None
if Config.REDIS_URL and redis:
    try:
        redis_client = redis.from_url(Config.REDIS_URL, decode_responses=True)
        redis_client.ping()
        print("[INFO] Connected to Redis for session storage")
    except Exception as e:
        print(f"[ERROR] Failed to connect to Redis: {e}")
        redis_client = None
elif Config.REDIS_URL and not redis:
    print("[WARN] REDIS_URL set but 'redis' package not installed. Falling back to memory.")

# Bounded LRU in-memory storage (fallback when Redis is unavailable).
# Caps at 100 users to prevent unbounded memory growth.
class _BoundedDict:
    def __init__(self, maxsize: int = 100):
        self._data: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._lock = Lock()

    def get(self, key, default=None):
        with self._lock:
            if key not in self._data:
                return default
            self._data.move_to_end(key)
            return self._data[key]

    def __setitem__(self, key, value):
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = value
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

USER_DATA: _BoundedDict = _BoundedDict(maxsize=100)

# ------------------------------------------------------------------
# 2. Core Redis Helpers
# ------------------------------------------------------------------
def _get_from_redis(uid: str) -> Optional[dict]:
    # 1. Try fast in-process / Redis cache
    if not redis_client:
        cached = USER_DATA.get(uid)
    else:
        cached = None
        try:
            data_str = redis_client.get(f"user:{uid}")
            if data_str:
                cached = json.loads(data_str)
        except Exception as e:
            print(f"[ERROR] Redis error on get for {uid}: {e}")
        if cached is None:
            cached = USER_DATA.get(uid)

    if cached is not None:
        return cached

    # 2. For logged-in users, fall back to Firebase when cache is cold
    account_id = _extract_account_id(uid)
    if account_id is not None:
        try:
            from firebase_service import load_user_data as fb_load
            firebase_data = fb_load(account_id)
            if firebase_data is not None:
                # Warm the local cache so subsequent requests are fast
                _save_to_redis(uid, firebase_data)
                return firebase_data
        except Exception as e:
            print(f"[ERROR] Firebase fallback failed for {uid}: {e}")

    return None

def _save_to_redis(uid: str, data: dict):
    # Always write to Redis / in-memory cache
    if not redis_client:
        USER_DATA[uid] = data
    else:
        try:
            redis_client.setex(f"user:{uid}", 86400, json.dumps(data))
        except Exception as e:
            print(f"[ERROR] Redis error on save for {uid}: {e}")
            USER_DATA[uid] = data

    # For logged-in users, also persist asynchronously to Firebase
    account_id = _extract_account_id(uid)
    if account_id is not None:
        try:
            from firebase_service import save_user_data_async
            save_user_data_async(account_id, data)
        except Exception as e:
            print(f"[ERROR] Firebase async save failed for {uid}: {e}")

# ------------------------------------------------------------------
# 3. Core helpers – defined in the same module as the data
# ------------------------------------------------------------------
def get_user_id() -> str:
    """Return a stable key for the current user.

    Logged-in account users get a persistent 'account_{id}' key so their
    data survives session expiry (backed by Firebase).  Guests get a
    random UUID that lives only as long as Redis/memory holds it.
    """
    account_id = session.get('account_user_id')
    if account_id:
        return f'account_{account_id}'
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']


def _extract_account_id(uid: str) -> Optional[int]:
    """Return the integer account ID from an 'account_N' uid, else None."""
    if uid.startswith('account_'):
        try:
            return int(uid[len('account_'):])
        except ValueError:
            pass
    return None

def get_user_data(user_id: str = None) -> dict:
    """Return user data dict, creating if needed."""
    uid = user_id or get_user_id()
    data = _get_from_redis(uid)

    if data is None:
        data = {
            'csv': {},
            'json': {
                'kinetics': {},
                'point': {}
            },
            'metadata_cache': {},
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
        # For account users, don't write the empty structure back to Firebase —
        # the Firebase load may have failed transiently and overwriting would destroy
        # real data. Cache locally so the next request retries Firebase normally.
        if _extract_account_id(uid) is not None:
            if not redis_client:
                USER_DATA[uid] = data
            else:
                try:
                    redis_client.setex(f"user:{uid}", 86400, json.dumps(data))
                except Exception as e:
                    print(f"[ERROR] Redis error on cache for {uid}: {e}")
                    USER_DATA[uid] = data
        else:
            _save_to_redis(uid, data)

    return data

@contextmanager
def user_data_session(user_id: str = None):
    """
    Context manager to safely modify user data and ensure it's saved to Redis.
    Usage:
        with user_data_session() as data:
            data['csv']['file.csv'] = content
    """
    uid = user_id or get_user_id()
    data = get_user_data(uid)
    try:
        yield data
    finally:
        _save_to_redis(uid, data)

def save_user_data(data: dict, user_id: str = None):
    """Explicitly save user data to Redis."""
    uid = user_id or get_user_id()
    _save_to_redis(uid, data)

def purge_user_data(uid: str):
    """Remove all cached data for a uid — called on account deletion."""
    if redis_client:
        try:
            redis_client.delete(f"user:{uid}")
        except Exception as e:
            print(f"[ERROR] Redis delete failed for {uid}: {e}")
    try:
        del USER_DATA._data[uid]
    except (KeyError, AttributeError):
        pass

# ------------------------------------------------------------------
# 4. File loaders
# ------------------------------------------------------------------
def _load_file(path: Path) -> str:
    """Load a CSV/JSON file and return its raw content as a string."""
    if not path.exists():
        print(f"[WARN] File not found – skipping: {path}")
        return ""

    try:
        raw_bytes = path.read_bytes()
        content = raw_bytes.decode('utf-8')
        return content
    except Exception as e:
        print(f"[ERROR] Failed to read {path}: {e}")
        return ""

# ------------------------------------------------------------------
# 5. Metadata and Init
# ------------------------------------------------------------------
def get_file_metadata(filename: str, user_id: str = None) -> dict:
    """Retrieve cached metadata for a file."""
    user_data = get_user_data(user_id)
    return user_data.get('metadata_cache', {}).get(filename)

def update_file_metadata(filename: str, content: str, user_id: str = None):
    """Parse and cache metadata (source count) for a file."""
    with user_data_session(user_id) as user_data:
        if 'metadata_cache' not in user_data:
            user_data['metadata_cache'] = {}
        
        if filename.lower().endswith('.csv'):
            try:
                lines = content.splitlines()
                header = next((l for l in lines if l.strip() and not l.lstrip().startswith('#')), "")
                if header:
                    count = sum(1 for col in header.split(',') if col.strip().startswith('Value:'))
                    user_data['metadata_cache'][filename] = {'num_sources': count if count > 0 else 1}
            except:
                pass

def init_user_data(csv_dir: str | Path = "csv", json_dir: str | Path = "json", clear_existing: bool = False) -> dict:
    csv_dir = Path(csv_dir)
    json_dir = Path(json_dir)

    # Account users persist their data in Firebase — never load guest demo files
    # into their workspace and never treat an empty Firebase response as "no data".
    # Return their current cached data without touching Firebase.
    uid = get_user_id()
    if _extract_account_id(uid) is not None and not clear_existing:
        return get_user_data(uid)

    with user_data_session() as user_data:
        if clear_existing:
            user_data['csv'].clear()
            user_data['json']['kinetics'].clear()
            user_data['json']['point'].clear()
            user_data['metadata_cache'].clear()

        if user_data['csv'] or user_data['json']['kinetics'] or user_data['json']['point']:
            return user_data

        if get_drive_mode() == 'connected' and not clear_existing:
            return user_data

        for fname in ("multi.csv", "single.csv"):
            csv_data = _load_file(csv_dir / fname)
            if csv_data:
                user_data["csv"][fname] = csv_data
                if 'metadata_cache' not in user_data: user_data['metadata_cache'] = {}
                try:
                    lines = csv_data.splitlines()
                    header = next((l for l in lines if l.strip() and not l.lstrip().startswith('#')), "")
                    if header:
                        count = sum(1 for col in header.split(',') if col.strip().startswith('Value:'))
                        user_data['metadata_cache'][fname] = {'num_sources': count if count > 0 else 1}
                except: pass

        for mode, file in [("kinetics", "exp_kinetics.json"), ("point", "exp_point.json")]:
            raw = _load_file(json_dir / file)
            if raw:
                user_data["json"][mode][file] = raw

        return user_data

# ------------------------------------------------------------------
# 6. Drive Helpers
# ------------------------------------------------------------------
def get_drive_mode(user_id: str = None):
    uid = user_id or get_user_id()
    user_data = get_user_data(uid)
    return user_data.get('drive', {}).get('mode', 'guest')

def get_drive_credentials(user_id: str = None):
    uid = user_id or get_user_id()
    user_data = get_user_data(uid)
    return user_data.get('drive', {}).get('credentials')

def set_drive_credentials(credentials, user_id: str = None):
    with user_data_session(user_id) as user_data:
        user_data['drive']['credentials'] = credentials
        user_data['drive']['authenticated'] = True
        user_data['drive']['mode'] = 'connected'

def get_drive_folder(user_id: str = None):
    uid = user_id or get_user_id()
    user_data = get_user_data(uid)
    return user_data.get('drive', {}).get('folder_id')

def set_drive_folder(folder_id: str, folder_name: str, user_id: str = None):
    with user_data_session(user_id) as user_data:
        user_data['drive']['folder_id'] = folder_id
        user_data['drive']['folder_name'] = folder_name

def set_drive_preference(key: str, value, user_id: str = None):
    with user_data_session(user_id) as user_data:
        user_data['drive'][key] = value

def is_auto_sync_enabled(user_id: str = None):
    uid = user_id or get_user_id()
    user_data = get_user_data(uid)
    return user_data.get('drive', {}).get('auto_sync_on_close', False)

def disconnect_drive(user_id: str = None):
    uid = user_id or get_user_id()
    with user_data_session(uid) as user_data:
        user_data['drive'] = {
            'mode': 'guest',
            'authenticated': False,
            'folder_id': None,
            'folder_name': None,
            'credentials': None,
            'last_sync': None,
            'auto_sync_on_close': False,
            'file_mapping': {},
            'pending_oauth_state': None
        }
    # Only reset to demo defaults for guest users. Account users' CSV/JSON data
    # lives in Firebase and must not be wiped just because Drive is disconnected.
    if _extract_account_id(uid) is None:
        init_user_data(clear_existing=True)

def set_pending_oauth_state(state: str, user_id: str = None):
    with user_data_session(user_id) as user_data:
        user_data['drive']['pending_oauth_state'] = state

def get_pending_oauth_state(user_id: str = None) -> str:
    uid = user_id or get_user_id()
    user_data = get_user_data(uid)
    return user_data['drive'].get('pending_oauth_state')