"""Firestore persistence via the REST API.

Uses google-auth + requests instead of firebase-admin/gRPC so that
all network calls are cooperative with eventlet's monkey-patched sockets.
No gRPC channels means no 30-second cold-start hang and no R12/H12 errors.
"""

import json
import os
import threading
from typing import Optional

_session = None        # google.auth.transport.requests.AuthorizedSession
_project_id: Optional[str] = None
_initialized = False
_lock = threading.Lock()

_SCOPES = ['https://www.googleapis.com/auth/datastore']


def _get_session():
    global _session, _project_id, _initialized
    if _initialized:
        return _session
    with _lock:
        if _initialized:
            return _session
        _initialized = True
        try:
            creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
            if not creds_json:
                print("[Firebase] FIREBASE_CREDENTIALS_JSON not set; Firebase persistence disabled.")
                return None

            creds_dict = json.loads(creds_json)
            _project_id = creds_dict.get('project_id')
            if not _project_id:
                print("[Firebase] project_id missing from credentials; Firebase persistence disabled.")
                return None

            from google.oauth2 import service_account
            from google.auth.transport.requests import AuthorizedSession

            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=_SCOPES
            )
            _session = AuthorizedSession(creds)
            print(f"[Firebase] REST session ready (project={_project_id}).")
        except Exception as e:
            print(f"[Firebase] Session init failed: {e}")
        return _session


def _doc_url(account_id: int) -> str:
    return (
        f"https://firestore.googleapis.com/v1/projects/{_project_id}"
        f"/databases/(default)/documents/users/{account_id}"
    )


def prewarm():
    """Initialise the REST session early. Fast — no network call until the
    first actual read/write, so safe to call at app startup."""
    _get_session()


def shutdown():
    """Close the HTTP session on worker exit (gunicorn worker_exit hook)."""
    global _session
    if _session is not None:
        try:
            _session.close()
        except Exception as e:
            print(f"[Firebase] Error closing session: {e}")
    print("[Firebase] Shutdown complete.")


def load_user_data(account_id: int) -> Optional[dict]:
    session = _get_session()
    if not session:
        return None
    try:
        resp = session.get(_doc_url(account_id), timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        raw = resp.json().get('fields', {}).get('working_data', {}).get('stringValue')
        if raw:
            return json.loads(raw)
    except Exception as e:
        print(f"[Firebase] Load error for account {account_id}: {e}")
    return None


def save_user_data(account_id: int, user_data: dict):
    session = _get_session()
    if not session:
        print(f"[Firebase] Save skipped for account {account_id}: no session (check FIREBASE_CREDENTIALS_JSON).")
        return
    try:
        body = {"fields": {"working_data": {"stringValue": json.dumps(user_data)}}}
        resp = session.patch(
            _doc_url(account_id),
            json=body,
            params={"updateMask.fieldPaths": "working_data"},
            timeout=10,
        )
        resp.raise_for_status()
        print(f"[Firebase] Saved data for account {account_id}.")
    except Exception as e:
        print(f"[Firebase] Save error for account {account_id}: {e}")


def delete_user_data(account_id: int):
    session = _get_session()
    if not session:
        return
    try:
        resp = session.delete(_doc_url(account_id), timeout=10)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()
        print(f"[Firebase] Deleted data for account {account_id}.")
    except Exception as e:
        print(f"[Firebase] Delete error for account {account_id}: {e}")


def save_user_data_async(account_id: int, user_data: dict):
    """Fire-and-forget write so it does not block HTTP responses."""
    import copy
    snapshot = copy.deepcopy(user_data)
    print(f"[Firebase] Queued async save for account {account_id}.")
    t = threading.Thread(target=save_user_data, args=(account_id, snapshot), daemon=True)
    t.start()
