import os
import json
import threading
from typing import Optional

_db = None
_initialized = False  # True only after init completes (success or failure)
_lock = threading.Lock()  # held for the duration of background init


def _tpool(fn, *args, **kwargs):
    """Run a blocking gRPC call via eventlet tpool when in a green-thread
    context so the hub stays free; falls back to a direct call otherwise."""
    try:
        from eventlet import tpool
        return tpool.execute(fn, *args, **kwargs)
    except ImportError:
        return fn(*args, **kwargs)


def _get_db():
    """Return the Firestore client, or None if not yet initialised.

    Always non-blocking: the first call triggers background initialisation
    in a real OS thread and returns None immediately. Callers should treat
    None as 'Firebase temporarily unavailable' and fall back to Redis/cache.
    """
    global _db, _initialized
    if _initialized:
        return _db

    # Try to be the one thread that starts initialisation.
    if not _lock.acquire(blocking=False):
        return None  # init already in progress

    def _do_init():
        global _db, _initialized
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
            if not creds_json:
                print("[Firebase] FIREBASE_CREDENTIALS_JSON not set; Firebase persistence disabled.")
                return

            creds_dict = json.loads(creds_json)
            if not firebase_admin._apps:
                cred = credentials.Certificate(creds_dict)
                firebase_admin.initialize_app(cred)

            # This gRPC call can take ~30 s on a cold Heroku dyno.
            # Running it here (real OS thread) keeps the eventlet hub free.
            _db = firestore.client()
            print("[Firebase] Connected to Firestore.")
        except ImportError:
            print("[Firebase] firebase-admin package not installed.")
        except Exception as e:
            print(f"[Firebase] Initialization failed: {e}")
        finally:
            _initialized = True
            _lock.release()

    # Use the original (non-monkey-patched) Thread so this is a real OS
    # thread that never needs the eventlet hub to make progress.
    try:
        import eventlet.patcher
        RealThread = eventlet.patcher.original('threading').Thread
    except Exception:
        RealThread = threading.Thread

    RealThread(target=_do_init, daemon=True, name='firebase-init').start()
    return None  # not ready yet; callers should handle gracefully


def prewarm():
    """Trigger Firebase background initialisation early so it is likely ready
    by the time the first user request needs it. Returns immediately."""
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
        print(f"[Firebase] Save skipped for account {account_id}: Firebase not ready yet.")
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
    """Fire-and-forget Firebase write so it does not block HTTP responses."""
    import copy
    snapshot = copy.deepcopy(user_data)
    print(f"[Firebase] Queued async save for account {account_id}.")
    t = threading.Thread(target=save_user_data, args=(account_id, snapshot), daemon=True)
    t.start()
