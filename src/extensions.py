import os
from urllib.parse import urlsplit

from flask_socketio import SocketIO


def _normalize_origin(raw):
    """Reduce a configured URL to the bare ``scheme://host[:port]`` an Origin carries.

    A browser's Origin header never has a path or a trailing slash, and engine.io
    compares it to this list by **exact string match** (``origin not in
    allowed_origins``, engineio/server.py). So an ``APP_BASE_URL`` of
    ``https://example.com/`` — a perfectly ordinary way to write a base URL —
    would match nothing and refuse every socket with "Not an accepted origin".
    Normalize instead of trusting the config to be punctuation-perfect.

    Returns None for anything without a host, so junk is dropped rather than
    silently widening or breaking the allowlist.
    """
    raw = (raw or '').strip()
    if not raw:
        return None
    if '://' not in raw:
        raw = '//' + raw          # let urlsplit read a bare host[:port] as a netloc
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    # A real host has no whitespace; reject rather than admit a junk entry that
    # could never match an Origin header anyway.
    if not parts.netloc or not parts.hostname or any(c.isspace() for c in parts.netloc):
        return None
    return '{}://{}'.format(parts.scheme or 'https', parts.netloc.lower())


def _cors_origins():
    """Allowed WebSocket/Socket.IO origins — never '*' with cookie auth.

    A wildcard let any site open an authenticated socket as a visiting victim and
    receive their `update_csv`/`update_json` push events. Restrict to the app's
    own origin(s): SOCKETIO_CORS_ORIGINS (comma-separated) if set, else
    APP_BASE_URL, falling back to localhost for development.

    Every entry is normalized (see _normalize_origin) because these values come
    from operator-set config vars, where a trailing slash is invisible and would
    otherwise take down every socket.
    """
    raw = os.environ.get('SOCKETIO_CORS_ORIGINS') or os.environ.get('APP_BASE_URL', '')
    origins = []
    for part in raw.split(','):
        origin = _normalize_origin(part)
        if origin and origin not in origins:
            origins.append(origin)
    return origins or ['http://localhost:5003']


# Verbose engine/socket logging is a dev aid; off in production so request and
# session detail doesn't end up in the logs. Heroku/generic servers set DYNO/PORT.
_VERBOSE = not any(os.environ.get(k) for k in ('DYNO', 'PORT', 'HEROKU_APP_NAME'))

socketio = SocketIO(cors_allowed_origins=_cors_origins(),
                    async_mode='eventlet',
                    engineio_logger=_VERBOSE,
                    logger=_VERBOSE)
