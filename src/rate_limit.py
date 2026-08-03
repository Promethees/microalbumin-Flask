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
# Signup sends real mail, and a duplicate signup on an unverified account
# re-sends the verification link — so an unlimited endpoint lets anyone flood an
# arbitrary inbox and drain the mail quota. Low enough to make that useless,
# high enough for a human retrying a typo'd address.
REGISTER_LIMIT = "5 per hour"          # account signup (/api/account/register)
# A review submission sends real mail to the admin inbox, and needs no account —
# so it is the easiest endpoint to flood. A human writes one review, not five.
REVIEW_SUBMIT_LIMIT = "3 per hour"     # review submission (/api/testimonials/submit)
# The contact form also mails the admin inbox and needs no account. A little
# looser than a review because a real person may legitimately send a follow-up
# after their first message, or retry after a typo'd address.
CONTACT_LIMIT = "5 per hour"           # contact form (/api/contact)


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
