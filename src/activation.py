import base64
import json
import os
import time
import state

# activation.json is writable user data: in a frozen build it lives in the
# per-user app-data dir (state.script_dir), not beside the read-only binary.
_ACTIVATION_PATH = os.path.join(state.script_dir, 'activation.json')
AI_SERVICE_URL = os.environ.get('AI_SERVICE_URL', 'https://www.easyokapi.cbbiotec.vn').rstrip('/')

_token_cache = ...  # type: Optional[str]  # sentinel: ... means "not yet loaded"


def load():
    try:
        with open(_ACTIVATION_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def get_license_token():
    global _token_cache
    if _token_cache is ...:
        _token_cache = load().get('license_token') or None
    return _token_cache


def save(license_token):
    global _token_cache
    try:
        with open(_ACTIVATION_PATH, 'w', encoding='utf-8') as f:
            json.dump({'license_token': license_token}, f, indent=2)
        _token_cache = license_token or None
        return True
    except Exception:
        return False


def _token_has_expiry(token):
    """Return True if the JWT carries an 'exp' claim.

    A short-lived download token (what the installers persist) has 'exp'; a
    permanent activation token does not. Best-effort, signature is not verified —
    on any decode error we return False so the exchange is skipped.
    """
    try:
        seg = token.split('.')[1]
        seg += '=' * (-len(seg) % 4)
        return 'exp' in json.loads(base64.urlsafe_b64decode(seg))
    except Exception:
        return False


def ensure_permanent_token():
    """Upgrade a raw download token in activation.json to a permanent license token.

    Every installer persists the user's 30-minute download token verbatim as the
    license token (it doubles as the download credential). Left as-is it expires
    within the hour, after which both the AI proxy and in-app updates fail
    (/api/download -> 401). We therefore exchange it once, while it is still
    fresh, for a permanent activation token (no exp) via /api/activate.

    No-op (and no network call) when there is no token or the token is already
    permanent — so on normal startups this returns immediately. Best-effort: any
    failure leaves the existing token untouched so a later run can retry while the
    download token is still valid. Returns True only when a permanent token was
    saved.
    """
    token = get_license_token()
    if not token or not _token_has_expiry(token):
        return False
    try:
        import requests
        resp = requests.post(f'{AI_SERVICE_URL}/api/activate',
                             json={'token': token}, timeout=15)
        if resp.status_code != 200:
            return False
        permanent = (resp.json().get('license_token') or '').strip()
    except Exception:
        return False
    if not permanent or _token_has_expiry(permanent):
        return False
    return save(permanent)


def _token_is_expired(token):
    """True only when the token carries an 'exp' claim that is already past.

    A permanent activation token (no 'exp') never expires. Best-effort: an
    unparseable token is treated as NOT expired (it is still a present token the
    server issued), so a present token is not rejected on a decode hiccup.
    """
    try:
        seg = token.split('.')[1]
        seg += '=' * (-len(seg) % 4)
        exp = json.loads(base64.urlsafe_b64decode(seg)).get('exp')
    except Exception:
        return False
    if exp is None:
        return False
    try:
        return time.time() >= float(exp)
    except (TypeError, ValueError):
        return False


def is_activated():
    """True when a usable license token is stored.

    A permanent activation token (saved after the server validated it via
    /api/activate) counts; an expired raw download token does not.
    """
    token = get_license_token()
    return bool(token) and not _token_is_expired(token)


def needs_activation():
    """Whether the app must show the activation gate before it can be used.

    Frozen builds are licence-gated: a valid token is required to use the app,
    matching the Windows installer's compulsory token. Always False in source/dev
    so developers are never blocked.
    """
    return state._is_frozen() and not is_activated()
