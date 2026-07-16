"""Same-origin request guard for the public EasyOKAPI web app.

The browser-driven, state-changing routes (account, Drive, export, AI chat) are
authenticated by a session cookie. ``SESSION_COOKIE_SAMESITE='Lax'`` already
blocks most cross-site cookie-bearing POSTs, but this installs an explicit
Origin/Referer check as defense-in-depth: one ``before_request`` guard that, for
unsafe methods, rejects a request whose browser-supplied Origin is not one of
ours.

Only a *browser* attaches an Origin/Referer. The desktop client talks to the
token-authenticated endpoints (``/api/activate``, ``/api/license/check``,
``/ai/proxy/chat``, ``/api/download``) server-to-server with no Origin header, so
those calls are never blocked here — an **absent** Origin is treated as "not a
cross-origin browser request" (a cross-origin browser POST always sends one and
the page cannot suppress it).

The allowlist is **server-configured** (``APP_BASE_URL`` + optional
comma-separated ``EXTRA_ALLOWED_ORIGINS``). We deliberately do NOT trust the
request ``Host`` header for the allowlist — an attacker can spoof it.
"""

import os
from urllib.parse import urlsplit

from flask import request, jsonify

# Methods that can change server state. Safe methods (GET/HEAD/OPTIONS) are reads
# and are not guarded; a state-changing GET would be a separate bug.
_UNSAFE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

# Always-allowed for local development (a browser on the attacker's site cannot
# make the request carry Origin: localhost, so this does not help an attacker).
_DEV_HOSTS = frozenset({'localhost', '127.0.0.1', '::1'})


def _hostname(value):
    """Lower-cased hostname from a URL or bare ``host[:port]``, else None."""
    if not value:
        return None
    if '://' not in value:
        value = '//' + value
    try:
        return (urlsplit(value).hostname or '').lower() or None
    except ValueError:
        return None


def _allowed_hostnames():
    """Hostnames this deployment answers to: APP_BASE_URL + EXTRA_ALLOWED_ORIGINS."""
    hosts = set(_DEV_HOSTS)
    candidates = [os.environ.get('APP_BASE_URL', 'http://localhost:5003')]
    candidates += os.environ.get('EXTRA_ALLOWED_ORIGINS', '').split(',')
    for raw in candidates:
        h = _hostname((raw or '').strip())
        if h:
            hosts.add(h)
    return hosts


def _forbidden(reason):
    return jsonify({'status': 'error',
                    'message': 'Request blocked: cross-origin request rejected.',
                    'code': f'forbidden_{reason}'}), 403


def init_request_guard(app):
    """Register the Origin/Referer guard as a ``before_request`` on ``app``."""

    @app.before_request
    def _guard_request_origin():
        if request.method not in _UNSAFE_METHODS:
            return None

        allowed = _allowed_hostnames()

        # A present Origin must be ours. An absent Origin means the request is not
        # a cross-origin browser call (which always sends one), so fall back to
        # Referer only when it is provided (server-to-server clients send neither).
        origin = request.headers.get('Origin')
        if origin is not None:
            if _hostname(origin) not in allowed:
                return _forbidden('origin')
        else:
            referer = request.headers.get('Referer')
            if referer and _hostname(referer) not in allowed:
                return _forbidden('referer')

        return None
