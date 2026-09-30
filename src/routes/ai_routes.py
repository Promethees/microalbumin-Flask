import json
from flask import Blueprint, jsonify, request, Response, stream_with_context, session
from user_data import get_user_data
import ai_settings
import ai_assistant
import jwt as pyjwt
from account import User
from download_service import validate_activation_token
from flask_limiter.util import get_remote_address
from rate_limit import limiter, AI_CHAT_LIMIT, AI_PROXY_LIMIT

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')


# ── Input caps (both chat endpoints) ──────────────────────────────────────────
# Same numbers as main's /ai/chat backstop (main src/routes/ai_routes.py), so a
# payload the desktop accepts is never rejected here. Every accepted call spends
# the paid Groq key, and a malformed element used to raise inside the SSE
# generator — after the 200 headers were already sent.
_MAX_MESSAGES = 24        # newest-N messages forwarded; older turns dropped
_MAX_MSG_CHARS = 8000     # per-message content ceiling
_MAX_TOTAL_CHARS = 24000  # summed content ceiling
# Client grounding (desktop builds): main 1.5.11 sends a ~5 KB prompt and ~6 KB
# of help docs, so 16 KB each leaves room without letting a crafted request
# push an arbitrary prompt through our key.
_MAX_GROUNDING_PROMPT_BYTES = 16 * 1024
_MAX_GROUNDING_HELP_BYTES = 16 * 1024


def _proxy_rate_key():
    """Rate-limit bucket for /ai/proxy/chat: the licence, not the address.

    Every desktop build shares whatever address the router presents, and one
    office NAT can hold many licensed machines, so an IP bucket is both too
    coarse and too easy to share. A token that verifies keys the bucket on its
    account (`sub`); anything else (no token, a forged one) falls back to the
    client address — which ProxyFix(x_for=1) makes the real client, not the
    Heroku router.
    """
    try:
        data = request.get_json(silent=True)
        token = data.get('license_token') if isinstance(data, dict) else None
        if isinstance(token, str) and token.strip():
            sub = validate_activation_token(token.strip()).get('sub')
            if sub:
                return f'licence:{sub}'
    except Exception:
        pass
    return get_remote_address()


@ai_bp.errorhandler(429)
def _rate_limited(e):
    """JSON 429 for the AI endpoints, so a client can map it (code=rate_limit)
    instead of seeing Flask-Limiter's HTML page as 'service unavailable'."""
    return jsonify({'status': 'failure', 'code': 'rate_limit',
                    'message': 'Too many requests. Please wait a moment and try again.'}), 429


def _clean_messages(raw):
    """Keep only {role: user|assistant, content: str} dicts, newest N.

    Returns (messages, error_response_or_None).
    """
    if not isinstance(raw, list):
        raw = []
    messages = [
        {'role': m['role'], 'content': m['content']}
        for m in raw
        if isinstance(m, dict)
        and m.get('role') in ('user', 'assistant')
        and isinstance(m.get('content'), str)
    ]
    if not messages:
        return None, (jsonify({'status': 'failure', 'message': 'No messages provided'}), 400)
    messages = messages[-_MAX_MESSAGES:]
    if sum(len(m['content']) for m in messages) > _MAX_TOTAL_CHARS or any(
        len(m['content']) > _MAX_MSG_CHARS for m in messages
    ):
        return None, (jsonify({'status': 'failure', 'code': 'too_large',
                               'message': 'Message is too long. Please shorten it and try again.'}), 413)
    return messages, None


def _valid_language(value, fallback='en'):
    """A request's language, validated against the one supported-language list."""
    if isinstance(value, str) and value in ai_settings.SUPPORTED_LANGUAGES:
        return value
    return fallback if fallback in ai_settings.SUPPORTED_LANGUAGES else 'en'


def _utf8_len(value) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False).encode('utf-8'))
    except (TypeError, ValueError):
        return 0


@ai_bp.route('/status', methods=['GET'])
def ai_status():
    from config import Config
    settings = ai_settings.load()
    api_ready = bool(Config.GROQ_API_KEY)
    return jsonify({
        'status': 'success',
        'api_ready': api_ready,
        'settings': settings,
        'supported_languages': ai_settings.SUPPORTED_LANGUAGES,
    })


@ai_bp.route('/settings', methods=['GET'])
def get_settings():
    return jsonify({
        'status': 'success',
        'settings': ai_settings.load(),
        'supported_languages': ai_settings.SUPPORTED_LANGUAGES,
    })


@ai_bp.route('/settings', methods=['POST'])
def save_settings():
    data = request.get_json(silent=True) or {}
    current = ai_settings.load()
    allowed = {'enabled', 'preferred_languages', 'preferred_language', 'first_run_shown'}
    updates = {k: v for k, v in data.items() if k in allowed}
    merged = {**current, **updates}
    if ai_settings.save(merged):
        return jsonify({'status': 'success', 'settings': ai_settings.load()})
    return jsonify({'status': 'failure', 'message': 'Could not save settings'}), 500


@ai_bp.route('/chat', methods=['POST'])
@limiter.limit(AI_CHAT_LIMIT)
def ai_chat():
    from config import Config
    # This endpoint spends the SERVER's Groq key, so it must not be open to the
    # public: it is the website's logged-in chat. Without this gate anyone could
    # POST here and drain the Groq quota, bypassing the activation/proxy scheme
    # that /ai/proxy/chat enforces for desktop clients.
    if not session.get('account_user_id'):
        return jsonify({'status': 'failure', 'code': 'auth_required',
                        'message': 'Sign in to use the assistant'}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    messages, err = _clean_messages(data.get('messages'))
    if err:
        return err

    settings = ai_settings.load()
    if not settings.get('enabled', True):
        return jsonify({'status': 'failure', 'message': 'AI assistant is disabled'}), 403

    if not Config.GROQ_API_KEY:
        return jsonify({'status': 'failure', 'message': 'AI assistant is not configured on this server'}), 503

    langs = settings.get('preferred_languages', ['en'])
    language = _valid_language(data.get('language'),
                               langs[0] if isinstance(langs, list) and langs else 'en')
    model = Config.AI_MODEL
    ui_context = data.get('ui_context') if isinstance(data.get('ui_context'), dict) else {}
    user_data = get_user_data()

    def generate():
        for event in ai_assistant.chat_stream(messages, language, Config.GROQ_API_KEY, model, ui_context, user_data):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@ai_bp.route('/proxy/chat', methods=['POST'])
@limiter.limit(AI_PROXY_LIMIT, key_func=_proxy_rate_key)
def proxy_chat():
    """AI proxy for desktop app instances. Validates activation token + active account."""
    from config import Config
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    license_token = data.get('license_token')
    license_token = license_token.strip() if isinstance(license_token, str) else ''

    if not license_token:
        return jsonify({'status': 'failure', 'message': 'License token required'}), 401

    try:
        payload = validate_activation_token(license_token)
    except pyjwt.InvalidTokenError as e:
        return jsonify({'status': 'failure', 'message': f'Invalid license token: {e}'}), 401

    user = User.query.get(int(payload['sub']))
    if not user or not user.is_verified:
        return jsonify({'status': 'failure', 'message': 'Account not found or not verified'}), 403

    # Hardware lock: a token bound to a machine may only be used from that machine.
    from routes.account_routes import _machine_is_licensed
    if not _machine_is_licensed(user, payload, data.get('hwid')):
        return jsonify({'status': 'failure', 'code': 'machine_mismatch',
                        'message': 'This license is not activated on this machine.'}), 403

    messages, err = _clean_messages(data.get('messages'))
    if err:
        return err

    grounding = data.get('client_grounding')
    grounding = grounding if isinstance(grounding, dict) else {}
    if (_utf8_len(grounding.get('system_prompt')) > _MAX_GROUNDING_PROMPT_BYTES
            or _utf8_len(grounding.get('help_docs')) > _MAX_GROUNDING_HELP_BYTES):
        return jsonify({'status': 'failure', 'code': 'too_large',
                        'message': 'Client grounding is too large.'}), 413

    if not Config.GROQ_API_KEY:
        return jsonify({'status': 'failure', 'message': 'AI not configured on server'}), 503

    language = _valid_language(data.get('language'))
    # The model is OUR choice, never the caller's. Honouring data['model'] meant
    # every installed desktop build pinned the model id that was current when it
    # was frozen, so Groq retiring `llama-3.1-8b-instant` 404'd the chat in copies
    # we can no longer edit. Ignoring it lets one Heroku config var move every
    # client, shipped or not, onto a live model.
    model = Config.AI_MODEL
    ui_context = data.get('ui_context') if isinstance(data.get('ui_context'), dict) else {}
    # No cloud user data for a proxied call: the desktop's files live on the
    # desktop, and the data tools are refused for every proxied request (see
    # ai_assistant._LOCAL_ONLY_TOOLS). Loading the account's cloud store here
    # used to hand the model a DIFFERENT set of files than the user is looking at.

    # The desktop (downloaded) app grounds the model in its OWN product docs so
    # answers describe the local app, not this cloud website. Pull the grounding
    # it sent (system prompt / help docs / tool schema); chat_stream validates
    # each and falls back to the server's own when absent or malformed.
    sys_override = grounding.get('system_prompt')
    system_prompt_override = sys_override if isinstance(sys_override, str) and sys_override.strip() else None
    help_docs_override = grounding.get('help_docs') if isinstance(grounding.get('help_docs'), dict) else None
    tools_override = grounding.get('tools') if isinstance(grounding.get('tools'), list) else None

    def generate():
        for event in ai_assistant.chat_stream(
            messages, language, Config.GROQ_API_KEY, model, ui_context, {},
            system_prompt_override=system_prompt_override,
            help_docs_override=help_docs_override,
            tools_override=tools_override,
            proxy_request=True,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@ai_bp.route('/guides', methods=['GET'])
def get_guides():
    lang = request.args.get('lang', 'en')
    if lang not in ai_settings.SUPPORTED_LANGUAGES:
        lang = 'en'
    return jsonify({
        'status': 'success',
        'examples': ai_assistant.get_guide_examples(lang),
    })
