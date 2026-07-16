import os

from flask_socketio import SocketIO


def _cors_origins():
    """Allowed WebSocket/Socket.IO origins — never '*' with cookie auth.

    A wildcard let any site open an authenticated socket as a visiting victim and
    receive their `update_csv`/`update_json` push events. Restrict to the app's
    own origin(s): SOCKETIO_CORS_ORIGINS (comma-separated) if set, else
    APP_BASE_URL, falling back to localhost for development.
    """
    raw = os.environ.get('SOCKETIO_CORS_ORIGINS') or os.environ.get('APP_BASE_URL', '')
    origins = [o.strip() for o in raw.split(',') if o.strip()]
    return origins or ['http://localhost:5003']


# Verbose engine/socket logging is a dev aid; off in production so request and
# session detail doesn't end up in the logs. Heroku/generic servers set DYNO/PORT.
_VERBOSE = not any(os.environ.get(k) for k in ('DYNO', 'PORT', 'HEROKU_APP_NAME'))

socketio = SocketIO(cors_allowed_origins=_cors_origins(),
                    async_mode='eventlet',
                    engineio_logger=_VERBOSE,
                    logger=_VERBOSE)
