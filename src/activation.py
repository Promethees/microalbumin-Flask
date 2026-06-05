import base64
import json
import os
import time
import state
import hwid as hwid_mod

# activation.json is writable user data: in a frozen build it lives in the
# per-user app-data dir (state.script_dir), not beside the read-only binary.
_ACTIVATION_PATH = os.path.join(state.script_dir, 'activation.json')
AI_SERVICE_URL = os.environ.get('AI_SERVICE_URL', 'https://www.easyokapi.cbbiotec.vn').rstrip('/')

# Permanent activation tokens issued by the server are RS256-signed and carry an
# 'hwid' claim binding them to one machine. We verify that signature offline with
# the embedded public key (src/activation_pubkey.py) and check the claim against
# this machine's fingerprint — so a copied token fails on a different machine and
# a hand-forged token fails the signature check.
#
# Legacy permanent tokens (issued before hardware locking) are HS256 and carry no
# 'hwid' claim. We cannot verify their signature on the client (HS256 secret is
# server-only), so they are grandfathered in: an existing install keeps working
# without forcing a re-activation. Flip this to False once every deployed install
# has re-activated under the RS256 scheme, to refuse unverifiable tokens entirely.
_ALLOW_LEGACY_HS256 = True

_token_cache = ...  # type: Optional[str]  # sentinel: ... means "not yet loaded"


def get_hwid():
    """This machine's hardware fingerprint (see src/hwid.py)."""
    return hwid_mod.get_hwid()


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


# ── JWT helpers (no signature verification) ───────────────────────────────────

def _decode_header(token):
    try:
        seg = token.split('.')[0]
        seg += '=' * (-len(seg) % 4)
        return json.loads(base64.urlsafe_b64decode(seg))
    except Exception:
        return {}


def _decode_payload(token):
    """Best-effort decode of the JWT payload WITHOUT verifying the signature."""
    try:
        seg = token.split('.')[1]
        seg += '=' * (-len(seg) % 4)
        return json.loads(base64.urlsafe_b64decode(seg))
    except Exception:
        return {}


def _token_has_expiry(token):
    """Return True if the JWT carries an 'exp' claim.

    A short-lived download token (what the installers persist) has 'exp'; a
    permanent activation token does not. Best-effort, signature is not verified —
    on any decode error we return False so the exchange is skipped.
    """
    return 'exp' in _decode_payload(token)


def _token_is_expired(token):
    """True only when the token carries an 'exp' claim that is already past.

    A permanent activation token (no 'exp') never expires. Best-effort: an
    unparseable token is treated as NOT expired (it is still a present token the
    server issued), so a present token is not rejected on a decode hiccup.
    """
    exp = _decode_payload(token).get('exp')
    if exp is None:
        return False
    try:
        return time.time() >= float(exp)
    except (TypeError, ValueError):
        return False


# ── Cryptographic verification (RS256 + hwid binding) ─────────────────────────

def _verify_rs256(token):
    """Verify an RS256 token with the embedded public key.

    Returns the payload dict on a valid signature, or None when the signature is
    invalid / the token is not RS256 / the verification libraries are unavailable.
    A None result is intentionally indistinguishable to the caller between "bad
    token" and "cannot verify here" — callers handle those cases via the alg.
    """
    try:
        import jwt  # PyJWT (+ cryptography) — bundled in frozen builds
        from activation_pubkey import ACTIVATION_PUBLIC_KEY_PEM
    except Exception:
        return None
    try:
        # Permanent tokens have no 'exp'; verify_exp is harmless either way.
        return jwt.decode(token, ACTIVATION_PUBLIC_KEY_PEM, algorithms=['RS256'])
    except Exception:
        return None


def _libs_available():
    try:
        import jwt  # noqa: F401
        from activation_pubkey import ACTIVATION_PUBLIC_KEY_PEM  # noqa: F401
        return True
    except Exception:
        return False


def verify_token(token):
    """Return the token's payload if it is a usable license for THIS machine, else None.

    Decision table:
      * RS256 token  → signature MUST verify with the embedded public key; if it
        carries an 'hwid' claim it MUST equal this machine's fingerprint; not
        expired. Otherwise rejected. This is the hardware lock.
      * HS256 token  → legacy. Cannot verify the signature on the client. Accepted
        only when _ALLOW_LEGACY_HS256 is True, the purpose is 'app_download', it
        carries NO 'hwid' claim (a genuine legacy token never does — an 'hwid' on
        an unverifiable token signals tampering), and it is not expired.
      * anything else → rejected.
    """
    if not token:
        return None

    if _token_is_expired(token):
        return None

    alg = (_decode_header(token).get('alg') or '').upper()

    if alg == 'RS256':
        payload = _verify_rs256(token)
        if payload is None:
            # Either a bad signature (reject) or libs missing (dev only). In a
            # frozen build libs are present, so None means bad signature → reject.
            # In dev, fall back to claim checks so developers are not blocked.
            if _libs_available() or state._is_frozen():
                return None
            payload = _decode_payload(token)
        claimed = payload.get('hwid')
        if claimed and claimed != get_hwid():
            return None  # token belongs to a different machine
        return payload

    if alg == 'HS256':
        if not _ALLOW_LEGACY_HS256:
            return None
        payload = _decode_payload(token)
        if payload.get('purpose') != 'app_download':
            return None
        if payload.get('hwid'):
            return None  # unverifiable token claiming an hwid → reject
        return payload

    return None


# ── Token lifecycle ───────────────────────────────────────────────────────────

def ensure_permanent_token():
    """Upgrade a raw download token in activation.json to a permanent license token.

    Every installer persists the user's 30-minute download token verbatim as the
    license token (it doubles as the download credential). Left as-is it expires
    within the hour, after which both the AI proxy and in-app updates fail
    (/api/download -> 401). We therefore exchange it once, while it is still
    fresh, for a permanent activation token (no exp) via /api/activate — sending
    this machine's hwid so the server binds and stamps the token to this machine.

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
                             json={'token': token, 'hwid': get_hwid()}, timeout=15)
        if resp.status_code != 200:
            return False
        permanent = (resp.json().get('license_token') or '').strip()
    except Exception:
        return False
    if not permanent or _token_has_expiry(permanent):
        return False
    return save(permanent)


def is_activated():
    """True when a usable license token is stored for THIS machine.

    A permanent activation token whose signature and hwid binding verify counts;
    an expired download token, a token bound to another machine, or a forged token
    does not. See verify_token() for the full decision table.
    """
    return verify_token(get_license_token()) is not None


def needs_activation():
    """Whether the app must show the activation gate before it can be used.

    Frozen builds are licence-gated: a valid token is required to use the app,
    matching the Windows installer's compulsory token. Always False in source/dev
    so developers are never blocked.
    """
    return state._is_frozen() and not is_activated()
