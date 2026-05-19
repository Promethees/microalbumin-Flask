import json
from flask import Blueprint, jsonify, request, Response, stream_with_context
from user_data import get_user_data
import ai_settings
import ai_assistant
import jwt as pyjwt
from account import User
from download_service import validate_activation_token

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')


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
def ai_chat():
    from config import Config
    data = request.get_json(silent=True) or {}
    messages = data.get('messages', [])
    if not messages:
        return jsonify({'status': 'failure', 'message': 'No messages provided'}), 400

    settings = ai_settings.load()
    if not settings.get('enabled', True):
        return jsonify({'status': 'failure', 'message': 'AI assistant is disabled'}), 403

    if not Config.GROQ_API_KEY:
        return jsonify({'status': 'failure', 'message': 'AI assistant is not configured on this server'}), 503

    langs = settings.get('preferred_languages', ['en'])
    language = data.get('language') or (langs[0] if langs else 'en')
    model = Config.AI_MODEL
    ui_context = data.get('ui_context') or {}
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
def proxy_chat():
    """AI proxy for desktop app instances. Validates activation token + active account."""
    from config import Config
    data = request.get_json(silent=True) or {}

    license_token = (data.get('license_token') or '').strip()
    if not license_token:
        return jsonify({'status': 'failure', 'message': 'License token required'}), 401

    try:
        payload = validate_activation_token(license_token)
    except pyjwt.InvalidTokenError as e:
        return jsonify({'status': 'failure', 'message': f'Invalid license token: {e}'}), 401

    user = User.query.get(int(payload['sub']))
    if not user or not user.is_verified:
        return jsonify({'status': 'failure', 'message': 'Account not found or not verified'}), 403

    messages = data.get('messages', [])
    if not messages:
        return jsonify({'status': 'failure', 'message': 'No messages provided'}), 400

    if not Config.GROQ_API_KEY:
        return jsonify({'status': 'failure', 'message': 'AI not configured on server'}), 503

    language = data.get('language', 'en')
    model = data.get('model') or Config.AI_MODEL
    ui_context = data.get('ui_context') or {}

    def generate():
        for event in ai_assistant.chat_stream(messages, language, Config.GROQ_API_KEY, model, ui_context):
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
