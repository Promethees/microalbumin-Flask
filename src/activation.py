import base64
import json
import os
import socket
import time
from urllib.parse import urlsplit

import state
import hwid as hwid_mod

# activation.json is writable user data: in a frozen build it lives in the
# per-user app-data dir (state.script_dir), not beside the read-only binary.
_ACTIVATION_PATH = os.path.join(state.script_dir, 'activation.json')

# ── Service endpoints (one deployment, several names) ─────────────────────────
# Activation, license checks, the AI proxy and in-app updates all talk to one
# Flask deployment. That deployment answers on a branded custom domain AND on its
# platform-assigned hostname, and the custom domain is a DNS + CDN + TLS layer in
# front of the very same dyno — a layer that can break (bad CNAME, expired or
# mismatched certificate, a CDN parked on the name) while the app itself is
# perfectly healthy. That is not hypothetical: it is exactly the failure this
# list exists for. Every base below serves the same API, so any that answers will
# do; we just have to be willing to try more than one.
#
# Order is "most preferred first". AI_SERVICE_URL keeps its old meaning — the
# branded name, and what the UI shows the user — so nothing that merely displays
# it has to change.
AI_SERVICE_URL = os.environ.get('AI_SERVICE_URL', 'https://www.easyokapi.cbbiotec.vn').rstrip('/')

# Alternates, tried in order after AI_SERVICE_URL. Setting AI_SERVICE_URL (dev,
# self-hosting) does not remove them: a custom primary is a preference, not a
# reason to lose the fallbacks. Duplicates are collapsed by service_bases().
FALLBACK_SERVICE_URLS = tuple(
    u.strip().rstrip('/')
    for u in os.environ.get(
        'AI_SERVICE_FALLBACK_URLS',
        'https://easyokapi.cbbiotec.vn,'
        'https://easysensor-kit-ea7db935ce81.herokuapp.com'
    ).split(',')
    if u.strip()
)

# The base that last answered, cached beside activation.json. Without it a dead
# primary costs a failed request on every single launch; with it, the app pays
# that once and then goes straight to what works.
_ENDPOINT_PATH = os.path.join(state.script_dir, 'service_endpoint.json')

# Per-attempt budget: (connect, read). The connect leg is short because a wrong
# or dead name is exactly what fails there, and the whole point is to move on to
# the next base quickly rather than sit out a full timeout per candidate.
SERVICE_TIMEOUT = (5, 30)


def _load_last_good_base():
    try:
        with open(_ENDPOINT_PATH, 'r', encoding='utf-8') as f:
            base = (json.load(f).get('base') or '').strip().rstrip('/')
    except Exception:
        return None
    # Only honour a remembered base that is still one we ship. Otherwise a stale
    # file (or an edited one) could pin the app to a host we no longer trust.
    return base if base in service_bases(include_last_good=False) else None


def _remember_base(base):
    """Persist the base that just worked. Best-effort — never breaks a good call."""
    if not base or base == _load_last_good_base():
        return
    try:
        with open(_ENDPOINT_PATH, 'w', encoding='utf-8') as f:
            json.dump({'base': base, 'at': time.time()}, f, indent=2)
    except Exception:
        pass


def service_bases(include_last_good=True):
    """The bases to try, best first, de-duplicated and order-preserving."""
    ordered = []
    if include_last_good:
        last = _load_last_good_base()
        if last:
            ordered.append(last)
    ordered.append(AI_SERVICE_URL)
    ordered.extend(FALLBACK_SERVICE_URLS)
    seen = set()
    return [b for b in ordered if b and not (b in seen or seen.add(b))]


def service_base():
    """The single best base for callers that cannot fail over mid-flight.

    Streaming callers (the update download, the AI chat proxy) commit to one host
    before the first byte, so they take the best *known* answer rather than
    probing. It is normally already correct: the startup license check and the
    update version check both run through service_request() and keep the
    remembered base current.
    """
    return service_bases()[0]


def _is_our_api(resp):
    """True when `resp` came from our API rather than from whatever else owns the name.

    A dead custom domain rarely fails cleanly — it gets parked on a CDN error
    page or, in our case, on an unrelated hosting control panel that cheerfully
    answers 404 in HTML. Those are HTTP responses, so status code alone cannot
    tell them from ours. Our API answers JSON on every one of these endpoints,
    including its errors, so "the body parses as JSON" is the test that actually
    separates the two.
    """
    try:
        resp.json()
        return True
    except Exception:
        return False


def service_stream(path, **kwargs):
    """Open a streaming GET on the first base that actually starts serving the file.

    A stream cannot fail over once the body is flowing, but it does not have to:
    the response headers arrive first, so a base can still be rejected without a
    byte of payload read. Anything but a 2xx means this host is not serving our
    download — the parked domain answers 404 here too — so close it and try the
    next name.

    Returns ``(response, base)`` with the body unread, or ``(None, None)``.

    This is what keeps an update from depending on the remembered base being
    warm. It often is (check_for_update runs first), but "often" is not a
    guarantee: a restart between the check and the download, or a banner drawn
    from a cached result, would otherwise send the download at a dead name.
    """
    try:
        import requests
    except Exception:
        return None, None
    kwargs.setdefault('stream', True)
    kwargs.setdefault('timeout', SERVICE_TIMEOUT)
    for base in service_bases():
        try:
            resp = requests.get(base + path, **kwargs)
        except Exception:
            continue
        if resp.status_code >= 400:
            try:
                resp.close()
            except Exception:
                pass
            continue
        _remember_base(base)
        return resp, base
    return None, None


def service_request(method, path, expect_json=True, **kwargs):
    """Send `path` to the first service base that gives us a real answer.

    Returns ``(response, base)``, or ``(None, None)`` when nothing answered at
    all. A base is skipped when the request raises (DNS, TLS, refused, timeout)
    and, for JSON endpoints, when what came back is not our API (_is_our_api).
    Any answer that IS ours — including 400/401/403/409 — is authoritative and
    ends the search; those are verdicts, not outages, and failing over past a
    verdict would turn "your token expired" into "the server is down".

    When no base produces an API answer but some host did reply, that first reply
    is returned rather than None: an HTTP status from *something* is more
    information than nothing, and the caller can still report it.

    The winning base is remembered for next time.
    """
    try:
        import requests
    except Exception:
        return None, None
    kwargs.setdefault('timeout', SERVICE_TIMEOUT)
    # Dispatch through requests.get/.post rather than requests.request: those are
    # the names every caller (and every test) patches, and routing around them
    # would silently escape interception.
    send = getattr(requests, method.lower(), None) or (
        lambda url, **kw: requests.request(method, url, **kw))

    non_api = None  # first reply that was not our API, kept as a last resort
    for base in service_bases():
        try:
            resp = send(base + path, **kwargs)
        except Exception:
            continue
        usable = _is_our_api(resp) if expect_json else resp.status_code < 400
        if not usable:
            if non_api is None:
                non_api = (resp, base)
            continue
        _remember_base(base)
        return resp, base
    return non_api if non_api is not None else (None, None)


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
    resp, _base = service_request('POST', '/api/activate',
                                 json={'token': token, 'hwid': get_hwid()})
    if resp is None or resp.status_code != 200:
        return False
    try:
        permanent = (resp.json().get('license_token') or '').strip()
    except Exception:
        return False
    if not permanent or _token_has_expiry(permanent):
        return False
    if not save(permanent):
        return False
    # The server just confirmed and bound this token (200 from /api/activate), so
    # start the revocation grace clock from this known-good online event.
    record_status('active')
    return True


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


# ── Admin revocation (client-side enforcement) ────────────────────────────────
# A permanent activation token verifies entirely offline, so the client cannot
# tell on its own that the admin has revoked the license server-side. We poll
# POST /api/license/check and cache the verdict in license_status.json (beside
# activation.json). The cache makes a 'revoked' verdict STICKY — it survives going
# offline and restarting — while a recent 'active' verdict is trusted within a
# grace window so a briefly-offline user is never blocked. Past the grace window,
# with no fresh confirmation, the app asks the user to reconnect (a soft reverify
# gate) rather than bricking; reconnecting re-checks and refreshes the cycle.

_STATUS_PATH = os.path.join(state.script_dir, 'license_status.json')
# Paths, not URLs: the host is chosen per call by service_request(), because the
# branded name can be down while the app behind it is not.
LICENSE_CHECK_PATH = '/api/license/check'
RELEASE_PATH = '/api/license/release'


def _grace_seconds():
    """Seconds an 'active' verdict is trusted before a re-check is required.

    Env-tunable (LICENSE_GRACE_SECONDS); default 7 days, floored at 1 hour so a
    misconfiguration can't make the grace window uselessly short.
    """
    try:
        return max(3600, int(os.environ.get('LICENSE_GRACE_SECONDS', str(7 * 24 * 3600))))
    except (TypeError, ValueError):
        return 7 * 24 * 3600


def load_status():
    try:
        with open(_STATUS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def record_status(status):
    """Persist a license verdict ('active'|'revoked'|'banned') stamped with the current time."""
    try:
        with open(_STATUS_PATH, 'w', encoding='utf-8') as f:
            json.dump({'status': status, 'checked_at': time.time()}, f, indent=2)
        return True
    except Exception:
        return False


# ── Why "could not verify" happened ───────────────────────────────────────────
# An offline verdict has two very different causes with two different fixes: this
# machine has no internet (the user can fix it), or our license service is
# unreachable while the internet works (only we can fix it, and the user should
# be told to report it). The reverify gate has to say which, so the check reports
# a reason alongside an 'offline' verdict.

# IP literals, so a broken resolver cannot masquerade as "no internet"; port 443
# because captive portals and lab firewalls often pass 53 but not egress.
_NET_PROBE_HOSTS = (('1.1.1.1', 443), ('8.8.8.8', 443), ('9.9.9.9', 443))
NET_PROBE_TIMEOUT = 2.0
# The gate auto-checks on load and again on every "Check again" click; without a
# cache an impatient user fires three TCP connects per click.
NET_PROBE_CACHE_SECONDS = 15.0

_net_probe_cache = {'at': 0.0, 'online': False}

# Reasons attached to an 'offline' verdict.
OFFLINE_REASONS = ('no_token', 'no_internet', 'dns_failure', 'service_down', 'unknown')


def internet_reachable(force=False):
    """Best-effort "does this machine have internet at all?".

    A TCP connect to public resolver IPs, not an HTTP request: no DNS, no
    response body, one round trip. Three hosts because one of them being down is
    not the same as the machine being offline.
    """
    now = time.time()
    if not force and (now - _net_probe_cache['at']) < NET_PROBE_CACHE_SECONDS:
        return _net_probe_cache['online']
    online = False
    for host, port in _NET_PROBE_HOSTS:
        try:
            with socket.create_connection((host, port), timeout=NET_PROBE_TIMEOUT):
                online = True
                break
        except OSError:
            continue
    _net_probe_cache['at'] = now
    _net_probe_cache['online'] = online
    return online


def _service_host_resolves():
    """True when this machine can resolve **any** of our service hostnames.

    Any single one is enough: the bases are alternate names for one deployment,
    so a resolver that answers for one of them is working. Only when none of them
    resolves is DNS itself the thing to blame.
    """
    for base in service_bases():
        host = urlsplit(base).hostname
        if not host:
            continue
        try:
            socket.getaddrinfo(host, None)
            return True
        except OSError:
            continue
    return False


def _diagnose_transport():
    """Classify a failed request to the license service into an offline reason.

    Ordering matters: no internet at all explains everything else, and a name
    that will not resolve here explains a connect failure that has nothing to do
    with our servers being down.
    """
    if not internet_reachable():
        return 'no_internet'
    if not _service_host_resolves():
        return 'dns_failure'
    return 'service_down'


def check_revocation_detailed():
    """check_revocation() plus *why*, as a ``(verdict, reason)`` pair.

    ``reason`` is None for a conclusive verdict ('active'/'revoked'/'banned') and
    one of OFFLINE_REASONS when the verdict is 'offline':

      * 'no_token'     — nothing to check; this install is not activated
      * 'no_internet'  — the machine cannot reach the internet at all
      * 'dns_failure'  — internet is up, but our hostname does not resolve here
      * 'service_down' — the machine is online and our service is the thing failing
      * 'unknown'      — the probes were inconclusive (no requests available)

    Once the host answers *anything* the network has done its job, so every
    non-200, unparseable body or untrusted reply is 'service_down'.
    """
    token = get_license_token()
    if not token:
        return 'offline', 'no_token'
    try:
        import requests  # noqa: F401
    except Exception:
        return 'offline', 'unknown'
    resp, _base = service_request('POST', LICENSE_CHECK_PATH,
                                  json={'license_token': token, 'hwid': get_hwid()})
    if resp is None:
        # Every base was tried and none of them answered as our API.
        return 'offline', _diagnose_transport()
    if resp.status_code != 200:
        return 'offline', 'service_down'
    try:
        body = resp.json()
        status = (body.get('status') or '').lower()
        code = (body.get('code') or '').lower()
    except Exception:
        return 'offline', 'service_down'
    if status == 'revoked':
        verdict = 'banned' if code == 'account_banned' else 'revoked'
        record_status(verdict)
        return verdict, None
    if status == 'active':
        record_status('active')
        return 'active', None
    return 'offline', 'service_down'


def check_revocation():
    """Poll the server for this machine's license verdict and update the cache.

    Returns 'active', 'revoked', 'banned', or 'offline'. Best-effort: only an
    explicit 'active'/'revoked' (HTTP 200) changes the cached state, so an
    unreachable server, a 4xx/5xx, or an untrusted reply ('offline') never flips a
    working install to blocked — it just leaves the last known verdict in place.

    A whole-account ban is reported by the server as status 'revoked' with code
    'account_banned'; we cache it as the distinct sticky verdict 'banned' so the
    gate can show a dedicated "account suspended" screen instead of the
    per-machine "license deactivated" one.

    See check_revocation_detailed() when the caller also needs to know *why* an
    'offline' verdict happened.
    """
    return check_revocation_detailed()[0]


def forget():
    """Delete the stored token and cached verdict (this install is no longer licensed)."""
    global _token_cache
    for path in (_ACTIVATION_PATH, _STATUS_PATH, _ENDPOINT_PATH):
        try:
            os.remove(path)
        except OSError:
            pass
    _token_cache = None


def release_machine():
    """Free this machine's seat server-side so the license can be used elsewhere.

    A seat is consumed until it is explicitly released, so an install that is
    simply deleted holds its seat forever and the user hits the seat cap on their
    next machine. The uninstallers call POST /api/license/release before removing
    anything (they do it over plain HTTP, since Python is gone by then); this is
    the same call for in-app use and source installs.

    Returns 'released' (seat freed, or there was nothing to free), 'refused' (the
    server declined — a revoked seat or banned account cannot be released, or the
    token names another machine), 'no_token', or 'offline'. On 'released' the local
    token and cached verdict are dropped: the seat is gone, so the token would no
    longer pass the server's machine check anyway.
    """
    token = get_license_token()
    if not token:
        return 'no_token'
    resp, _base = service_request('POST', RELEASE_PATH,
                                  json={'license_token': token, 'hwid': get_hwid()})
    if resp is None:
        return 'offline'
    if resp.status_code == 403:
        return 'refused'
    if resp.status_code != 200:
        return 'offline'
    try:
        if (resp.json().get('status') or '').lower() != 'success':
            return 'offline'
    except Exception:
        return 'offline'
    forget()
    return 'released'


def license_state():
    """Client-side license verdict for the gate: 'active' | 'revoked' | 'banned' | 'needs_recheck'.

    Only meaningful for an activated, frozen build. Source/dev runs and not-yet-
    activated builds (the activation gate handles those) are always 'active' here,
    so revocation never interferes with them. For an activated frozen build:

      * cached 'banned'                     → 'banned'         (sticky; account-wide)
      * cached 'revoked'                    → 'revoked'        (sticky; works offline)
      * cached 'active' within grace window → 'active'
      * otherwise (no/stale confirmation)   → 'needs_recheck'  (ask to reconnect)
    """
    if not state._is_frozen() or not is_activated():
        return 'active'
    st = load_status()
    status = st.get('status')
    if status == 'banned':
        return 'banned'
    if status == 'revoked':
        return 'revoked'
    if status == 'active':
        try:
            if (time.time() - float(st.get('checked_at') or 0)) < _grace_seconds():
                return 'active'
        except (TypeError, ValueError):
            pass
    return 'needs_recheck'


def license_blocked():
    """True when the app must be blocked outright (license revoked or account banned)."""
    return license_state() in ('revoked', 'banned')
