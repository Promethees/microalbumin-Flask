import json
import os
import requests
from flask import Blueprint, jsonify, request, Response, stream_with_context
import ai_settings
import ai_assistant
import activation as activation_mod
import state

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')

# Load .env for dev-mode override (GROQ_API_KEY in .env bypasses activation — dev only).
# .env is writable user data: it lives in the app-data dir for a frozen build,
# and in the project root in dev (both == state.script_dir).
_env_path = os.path.join(state.script_dir, '.env')
if os.path.exists(_env_path):
    with open(_env_path, encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

_DEV_GROQ_KEY = os.environ.get('GROQ_API_KEY', '')
_AI_MODEL = os.environ.get('AI_MODEL', 'llama-3.1-8b-instant')


def _get_api_mode():
    """Return ('proxy', license_token), ('dev', api_key), or (None, None)."""
    token = activation_mod.get_license_token()
    if token:
        return 'proxy', token
    if _DEV_GROQ_KEY:
        return 'dev', _DEV_GROQ_KEY
    return None, None


@ai_bp.route('/status', methods=['GET'])
def ai_status():
    mode, _ = _get_api_mode()
    return jsonify({
        'status': 'success',
        'api_ready': mode is not None,
        'activated': mode == 'proxy',
        'dev_mode': mode == 'dev',
        'supported_languages': ai_settings.SUPPORTED_LANGUAGES,
    })


@ai_bp.route('/activate', methods=['POST'])
def activate():
    """Exchange the pasted Easy OKAPI download token for a permanent license token.

    The website only issues short-lived (30-min) download tokens. Saving that raw
    token verbatim means it expires within the hour, after which the server rejects
    both AI proxy calls and in-app update downloads (/api/download → 401). We
    therefore exchange it once via the server's /api/activate endpoint, which
    returns a permanent activation token (no exp), and persist that instead.
    """
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'status': 'failure', 'message': 'Token is required'}), 400

    try:
        resp = requests.post(
            f'{activation_mod.AI_SERVICE_URL}/api/activate',
            json={'token': token}, timeout=15,
        )
    except requests.RequestException as e:
        return jsonify({'status': 'failure',
                        'message': f'Could not reach activation server: {e}'}), 502

    if resp.status_code != 200:
        message = 'Activation failed. The token may be invalid or expired — get a fresh one at easyokapi.cbbiotec.vn.'
        try:
            message = resp.json().get('message', message)
        except ValueError:
            pass
        return jsonify({'status': 'failure', 'message': message}), resp.status_code

    try:
        license_token = (resp.json().get('license_token') or '').strip()
    except ValueError:
        license_token = ''
    if not license_token:
        return jsonify({'status': 'failure',
                        'message': 'Activation server did not return a license token'}), 502

    if not activation_mod.save(license_token):
        return jsonify({'status': 'failure', 'message': 'Could not save activation token'}), 500

    return jsonify({'status': 'success', 'message': 'AI assistant activated'})


@ai_bp.route('/chat', methods=['POST'])
def ai_chat():
    data = request.get_json(silent=True) or {}
    raw_messages = data.get('messages', [])
    messages = [
        m for m in raw_messages
        if isinstance(m, dict)
        and m.get('role') in ('user', 'assistant')
        and isinstance(m.get('content', ''), str)
    ]
    if not messages:
        return jsonify({'status': 'failure', 'message': 'No messages provided'}), 400

    mode, credential = _get_api_mode()
    if not mode:
        return jsonify({'status': 'failure', 'message': 'AI assistant is not activated'}), 503

    language = data.get('language') or 'en'
    ui_context = data.get('ui_context') or {}

    _PROXY_TRANSIENT_ERRORS = frozenset({'proxy_unreachable', 'proxy_timeout'})

    if mode == 'proxy':
        def generate():
            fell_back = False
            for event in ai_assistant.proxy_chat_stream(
                messages, language, credential,
                activation_mod.AI_SERVICE_URL, _AI_MODEL, ui_context,
            ):
                if event.get('type') == 'error' and event.get('error') in _PROXY_TRANSIENT_ERRORS and _DEV_GROQ_KEY:
                    fell_back = True
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if fell_back:
                for event in ai_assistant.chat_stream(messages, language, _DEV_GROQ_KEY, _AI_MODEL, ui_context):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
    else:
        def generate():
            for event in ai_assistant.chat_stream(messages, language, credential, _AI_MODEL, ui_context):
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


@ai_bp.route('/match', methods=['POST'])
def ai_match():
    """Local, no-LLM guide resolution for the desktop client.

    The desktop UI differs from the cloud UI, so navigation guides must be
    resolved against this app's own elements rather than delegated to the cloud
    proxy. The frontend calls this before any chat request: a hit launches the
    local guide; a miss falls through to the normal (LLM) chat. No activation
    required — guide navigation is purely local.
    """
    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    if not query:
        msgs = data.get('messages') or []
        query = next(
            (m.get('content', '') for m in reversed(msgs)
             if isinstance(m, dict) and m.get('role') == 'user'),
            '',
        ).strip()

    language = data.get('language') or 'en'
    if language not in ai_settings.SUPPORTED_LANGUAGES:
        language = 'en'
    ui_context = data.get('ui_context') or {}

    guide_id, steps = ai_assistant.resolve_guide(query, ui_context, language)
    return jsonify({
        'status': 'success',
        'fires': bool(steps),
        'guide_id': guide_id,
        'steps': steps or [],
    })
