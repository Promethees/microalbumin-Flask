import os
import json
import threading
from typing import Optional

_db = None
_initialized = False
_lock = threading.Lock()


def _get_db():
    global _db, _initialized
    if _initialized:
        return _db
    with _lock:
        if _initialized:
            return _db
        _initialized = True
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
            if not creds_json:
                print("[Firebase] FIREBASE_CREDENTIALS_JSON not set; Firebase persistence disabled.")
                return None

            creds_dict = json.loads(creds_json)
            if not firebase_admin._apps:
                cred = credentials.Certificate(creds_dict)
                firebase_admin.initialize_app(cred)

            _db = firestore.client()
            print("[Firebase] Connected to Firestore.")
        except ImportError:
            print("[Firebase] firebase-admin package not installed.")
        except Exception as e:
            print(f"[Firebase] Initialization failed: {e}")
        return _db


def load_user_data(account_id: int) -> Optional[dict]:
    db = _get_db()
    if not db:
        return None
    try:
        doc = db.collection('users').document(str(account_id)).get()
        if doc.exists:
            raw = doc.to_dict().get('working_data')
            if raw:
                return json.loads(raw)
    except Exception as e:
        print(f"[Firebase] Load error for account {account_id}: {e}")
    return None


def save_user_data(account_id: int, user_data: dict):
    db = _get_db()
    if not db:
        return
    try:
        db.collection('users').document(str(account_id)).set(
            {'working_data': json.dumps(user_data)},
            merge=True
        )
    except Exception as e:
        print(f"[Firebase] Save error for account {account_id}: {e}")


def delete_user_data(account_id: int):
    db = _get_db()
    if not db:
        return
    try:
        db.collection('users').document(str(account_id)).delete()
        print(f"[Firebase] Deleted data for account {account_id}.")
    except Exception as e:
        print(f"[Firebase] Delete error for account {account_id}: {e}")


def save_user_data_async(account_id: int, user_data: dict):
    """Fire-and-forget Firebase write so it doesn't block HTTP responses."""
    import copy
    snapshot = copy.deepcopy(user_data)
    t = threading.Thread(target=save_user_data, args=(account_id, snapshot), daemon=True)
    t.start()
