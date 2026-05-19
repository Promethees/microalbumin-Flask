import json
import os
from flask import Blueprint, jsonify, request, Response, stream_with_context
import ai_settings
import ai_assistant
import activation as activation_mod

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')

# Load .env for dev-mode override (GROQ_API_KEY in .env bypasses activation — dev only)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.env')
if os.path.exists(_env_path):
    with open(_env_path, encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                os.environ.setdefault(_k.strip(), _v.strip())

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
    """Save the Easy OKAPI download token as the local license token."""
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'status': 'failure', 'message': 'Token is required'}), 400

    if not activation_mod.save(token):
        return jsonify({'status': 'failure', 'message': 'Could not save activation token'}), 500

    return jsonify({'status': 'success', 'message': 'AI assistant activated'})


@ai_bp.route('/chat', methods=['POST'])
def ai_chat():
    data = request.get_json(silent=True) or {}
    messages = data.get('messages', [])
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
