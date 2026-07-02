"""Request-origin guard for the local, single-user app.

The app binds 127.0.0.1 and has no login, sessions, or CSRF tokens, yet it is
driven from the browser and reachable at an aliased host (``easyokapi.com`` via
the hosts file). That makes every state-changing route reachable by:

  * **CSRF** — any web page the user visits can issue a cross-origin ``POST`` to
    ``http://127.0.0.1:<port>/`` (or the alias) and trigger ``/delete_file``,
    ``/edit_file``, ``/shutdown``, etc. A simple form/`fetch` POST needs no CORS
    preflight, so nothing stops it today.
  * **DNS rebinding** — an attacker domain that re-resolves to 127.0.0.1 becomes
    "same origin" in the browser, defeating an Origin check alone.

Rather than thread a CSRF token through every form, this installs one
``before_request`` guard that, for unsafe methods, requires:

  1. the **Host** the browser addressed to be one of ours (blocks rebinding —
     a rebound request carries ``Host: attacker.com``), and
  2. the **Origin** (when present) to be one of ours (blocks cross-origin CSRF —
     a cross-origin browser POST always carries an ``Origin``; the attacker
     cannot suppress it, so an *absent* Origin is not a cross-origin request).
     When Origin is absent, the ``Referer`` is checked as a fallback.

Comparison is by hostname only (scheme/port ignored): the app is the sole
listener on its loopback port, so port-pinning adds no security, and hostname
matching keeps the Flask test client (``Host: localhost``) and a custom
``--alias`` working without special cases.
"""

from urllib.parse import urlsplit
from flask import request, jsonify
import state

# Methods that can change server state. Safe methods (GET/HEAD/OPTIONS) are not
# guarded — they are reads, and a state-changing GET would be a separate bug.
_UNSAFE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

# Loopback hostnames the app is always reachable at (IPv4, name, IPv6).
_LOOPBACK = frozenset({'127.0.0.1', 'localhost', '::1'})

# Argparse default; used when state.args is not yet set (import time / tests).
_DEFAULT_ALIAS = 'easyokapi.com'


def _hostname(value):
    """Lower-cased hostname from a URL or a bare ``host[:port]``, else None."""
    if not value:
        return None
    # urlsplit needs a scheme/authority marker to populate .hostname; add one for
    # a bare "host:port" (a Host header) without disturbing a full URL (an Origin).
    if '://' not in value:
        value = '//' + value
    try:
        return (urlsplit(value).hostname or '').lower() or None
    except ValueError:
        return None


def _allowed_hostnames():
    """The hostnames this instance answers to: loopback + the configured alias."""
    hosts = set(_LOOPBACK)
    args = getattr(state, 'args', None)
    alias = getattr(args, 'alias', None) if args is not None else None
    alias_host = _hostname(alias or _DEFAULT_ALIAS)
    if alias_host:
        hosts.add(alias_host)
    return hosts


def _forbidden(reason):
    return jsonify({'status': 'error',
                    'message': 'Request blocked: cross-origin or unexpected host.',
                    'code': f'forbidden_{reason}'}), 403


def init_request_guard(app):
    """Register the Host/Origin guard as a ``before_request`` on ``app``."""

    @app.before_request
    def _guard_request_origin():
        if request.method not in _UNSAFE_METHODS:
            return None

        allowed = _allowed_hostnames()

        # (1) Anti-DNS-rebinding: the addressed Host must be one of ours.
        host_name = _hostname(request.headers.get('Host'))
        if host_name is not None and host_name not in allowed:
            return _forbidden('host')

        # (2) Anti-CSRF: a present Origin must be ours; an absent Origin means the
        # request is not a cross-origin browser POST (which always sends one), so
        # fall back to Referer only when it is provided.
        origin = request.headers.get('Origin')
        if origin is not None:
            if _hostname(origin) not in allowed:
                return _forbidden('origin')
        else:
            referer = request.headers.get('Referer')
            if referer and _hostname(referer) not in allowed:
                return _forbidden('referer')

        return None
