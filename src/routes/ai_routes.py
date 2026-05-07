import json
from flask import Blueprint, jsonify, request, Response, stream_with_context
import ai_settings
import ai_assistant

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')


@ai_bp.route('/status', methods=['GET'])
def ai_status():
    settings = ai_settings.load()
    ollama_info = ai_assistant.check_ollama(settings['ollama_url'])
    model_available = settings['model'] in ollama_info.get('models', [])
    return jsonify({
        'status': 'success',
        'ollama_running': ollama_info['running'],
        'model_available': model_available,
        'available_models': ollama_info.get('models', []),
        'settings': settings,
        'supported_languages': ai_settings.SUPPORTED_LANGUAGES,
        'available_models_catalog': ai_settings.AVAILABLE_MODELS,
    })


@ai_bp.route('/settings', methods=['GET'])
def get_settings():
    return jsonify({
        'status': 'success',
        'settings': ai_settings.load(),
        'supported_languages': ai_settings.SUPPORTED_LANGUAGES,
        'available_models_catalog': ai_settings.AVAILABLE_MODELS,
    })


@ai_bp.route('/settings', methods=['POST'])
def save_settings():
    data = request.get_json(silent=True) or {}
    current = ai_settings.load()
    allowed = {'enabled', 'preferred_languages', 'preferred_language',
               'model', 'ollama_url', 'first_run_shown'}
    updates = {k: v for k, v in data.items() if k in allowed}
    merged = {**current, **updates}
    if ai_settings.save(merged):
        return jsonify({'status': 'success', 'settings': ai_settings.load()})
    return jsonify({'status': 'failure', 'message': 'Could not save settings'}), 500


@ai_bp.route('/chat', methods=['POST'])
def ai_chat():
    data = request.get_json(silent=True) or {}
    messages = data.get('messages', [])
    if not messages:
        return jsonify({'status': 'failure', 'message': 'No messages provided'}), 400

    settings = ai_settings.load()
    if not settings.get('enabled', True):
        return jsonify({'status': 'failure', 'message': 'AI assistant is disabled'}), 403

    langs = settings.get('preferred_languages', ['en'])
    language = data.get('language') or (langs[0] if langs else 'en')
    model = data.get('model') or settings.get('model', 'qwen2.5:7b')
    ollama_url = settings.get('ollama_url', 'http://localhost:11434')

    def generate():
        for event in ai_assistant.chat_stream(messages, language, ollama_url, model):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@ai_bp.route('/pull_model', methods=['POST'])
def pull_model():
    data = request.get_json(silent=True) or {}
    settings = ai_settings.load()
    model = data.get('model') or settings.get('model', 'qwen2.5:7b')
    ollama_url = settings.get('ollama_url', 'http://localhost:11434')

    pull_state = ai_assistant.get_pull_state()
    if pull_state['active']:
        return jsonify({'status': 'failure', 'message': 'A download is already in progress'}), 409

    ollama_info = ai_assistant.check_ollama(ollama_url)
    if not ollama_info['running']:
        return jsonify({'status': 'failure', 'message': 'Ollama is not running'}), 503

    ai_assistant.start_model_pull(ollama_url, model)
    return jsonify({'status': 'success', 'message': f'Download started for {model}'})


@ai_bp.route('/pull_status', methods=['GET'])
def pull_status():
    pull_state = ai_assistant.get_pull_state()
    pct = 0
    if pull_state['total'] and pull_state['total'] > 0:
        pct = int(pull_state['completed'] / pull_state['total'] * 100)
    return jsonify({
        'status': 'success',
        'active': pull_state['active'],
        'model': pull_state['model'],
        'pull_status': pull_state['status'],
        'percent': pct,
        'done': pull_state['done'],
        'error': pull_state['error'],
    })
