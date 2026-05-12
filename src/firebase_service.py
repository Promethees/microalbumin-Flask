import os
import json
import threading
from typing import Optional

_db = None
_initialized = False
_lock = threading.Lock()


def _tpool(fn, *args, **kwargs):
    """Run a blocking gRPC call in eventlet's real-thread pool so the
    eventlet hub is never frozen by a long-running Firebase/gRPC call."""
    try:
        from eventlet import tpool
        return tpool.execute(fn, *args, **kwargs)
    except ImportError:
        return fn(*args, **kwargs)


def _get_db():
    global _db, _initialized
    if _initialized:
        return _db
    # Non-blocking: if another thread is already initialising, skip Firebase
    # for this call rather than blocking the eventlet hub.
    if not _lock.acquire(blocking=False):
        return _db
    try:
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

            # firestore.client() establishes the gRPC channel (~30 s cold start).
            # Run in a real OS thread via tpool so it doesn't freeze the eventlet hub.
            _db = _tpool(firestore.client)
            print("[Firebase] Connected to Firestore.")
        except ImportError:
            print("[Firebase] firebase-admin package not installed.")
        except Exception as e:
            print(f"[Firebase] Initialization failed: {e}")
        return _db
    finally:
        _lock.release()


def prewarm():
    """Call once at app startup to establish the Firestore gRPC connection
    before user requests arrive. Safe to call from a green thread."""
    _get_db()


def shutdown():
    """Close the Firestore gRPC channel so its background threads exit cleanly.
    Called from gunicorn's worker_exit hook to avoid R12 (exit timeout)."""
    global _db
    if _db is not None:
        try:
            _db.close()
        except Exception as e:
            print(f"[Firebase] Error closing Firestore client: {e}")
    try:
        import firebase_admin
        if firebase_admin._apps:
            firebase_admin.delete_app(firebase_admin.get_app())
    except Exception as e:
        print(f"[Firebase] Error deleting Firebase app: {e}")
    print("[Firebase] Shutdown complete.")


def load_user_data(account_id: int) -> Optional[dict]:
    db = _get_db()
    if not db:
        return None
    try:
        ref = db.collection('users').document(str(account_id))
        doc = _tpool(ref.get)
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
        print(f"[Firebase] Save skipped for account {account_id}: no database connection (check FIREBASE_CREDENTIALS_JSON).")
        return
    try:
        ref = db.collection('users').document(str(account_id))
        _tpool(ref.set, {'working_data': json.dumps(user_data)}, merge=True)
        print(f"[Firebase] Saved data for account {account_id}.")
    except Exception as e:
        print(f"[Firebase] Save error for account {account_id}: {e}")


def delete_user_data(account_id: int):
    db = _get_db()
    if not db:
        return
    try:
        ref = db.collection('users').document(str(account_id))
        _tpool(ref.delete)
        print(f"[Firebase] Deleted data for account {account_id}.")
    except Exception as e:
        print(f"[Firebase] Delete error for account {account_id}: {e}")


def save_user_data_async(account_id: int, user_data: dict):
    """Fire-and-forget Firebase write so it doesn't block HTTP responses."""
    import copy
    snapshot = copy.deepcopy(user_data)
    print(f"[Firebase] Queued async save for account {account_id}.")
    t = threading.Thread(target=save_user_data, args=(account_id, snapshot), daemon=True)
    t.start()
