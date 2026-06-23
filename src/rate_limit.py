"""Shared Flask-Limiter singleton for abuse / cost-drain protection.

Kept in its own module (NOT extensions.py, which imports flask_socketio →
eventlet) so route modules can `from rate_limit import limiter` and decorate
endpoints without dragging the SocketIO/eventlet stack into them.

Wiring: main.py calls `limiter.init_app(app)` once. Storage is Redis when
REDIS_URL is configured (so limits hold across Heroku dynos / restarts), else
in-memory (fine for a single process / tests, but per-process only).

Limit strings are module constants so a route decorator and its test reference
the same number — change the limit in one place.
"""
import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Per-endpoint limits. AI endpoints proxy to a paid Groq key, so they are the
# costly surface; keep them tight. Activation is abuse-sensitive (token minting).
AI_CHAT_LIMIT = "30 per minute"        # website logged-in chat (/ai/chat)
AI_PROXY_LIMIT = "30 per minute"       # desktop proxy chat (/ai/proxy/chat)
ACTIVATE_LIMIT = "10 per minute"       # token exchange (/api/activate)
LICENSE_CHECK_LIMIT = "60 per minute"  # desktop revocation poll (/api/license/check)


def _storage_uri():
    """Redis when available so limits are shared across processes; else in-memory."""
    return os.environ.get('REDIS_URL') or "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage_uri(),
    headers_enabled=True,
    # Robustness: if the configured store is unreachable (e.g. a Heroku Redis
    # rediss:// cert hiccup), fall back to in-memory counting and never let a
    # storage error 500 the request. Rate limiting is a safeguard, not a hard
    # dependency — degrade rather than take the AI/activation endpoints down.
    in_memory_fallback_enabled=True,
    swallow_errors=True,
)
