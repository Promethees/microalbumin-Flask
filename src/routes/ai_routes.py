import collections
import io
import json
import os
import re
import threading
import time
import zipfile
import requests
from flask import Blueprint, jsonify, request, Response, stream_with_context, send_file
import user_settings
import ai_assistant
import ai_feedback
import activation as activation_mod
import state
from validators import validate_json

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')


# ── Server-side rate limit + payload caps (backstop for /ai/chat) ─────────────
# The browser already throttles at 15/60s (ai-chat.js), but that is trivially
# bypassed by calling the endpoint directly, and every accepted call spends a
# paid Groq/proxy request. These are the authoritative server-side guards: a
# sliding-window limiter and hard size caps applied before any upstream call.
# The app is single-user, so one process-wide window (guarded by a lock for the
# threaded dev server) is sufficient.

_RATE_MAX = 20            # requests …
_RATE_WINDOW = 60.0       # … per this many seconds
_MAX_MESSAGES = 24        # newest-N messages forwarded; older turns dropped
_MAX_MSG_CHARS = 8000     # per-message content ceiling
_MAX_TOTAL_CHARS = 24000  # summed content ceiling

_rate_lock = threading.Lock()
_rate_hits = collections.deque()

_RATE_LIMITED_MSG = {
    'en': 'Too many requests. Please wait {s}s and try again.',
    'vi': 'Quá nhiều yêu cầu. Vui lòng chờ {s}s rồi thử lại.',
    'zh': '请求过于频繁。请等待 {s} 秒后重试。',
    'fr': 'Trop de requêtes. Veuillez patienter {s}s avant de réessayer.',
    'ja': 'リクエストが多すぎます。{s} 秒待ってから再試行してください。',
    'ru': 'Слишком много запросов. Подождите {s} сек. и повторите попытку.',
}

_TOO_LARGE_MSG = {
    'en': 'Message is too long. Please shorten it and try again.',
    'vi': 'Tin nhắn quá dài. Vui lòng rút ngắn và thử lại.',
    'zh': '消息过长。请缩短后重试。',
    'fr': 'Message trop long. Veuillez le raccourcir et réessayer.',
    'ja': 'メッセージが長すぎます。短くして再試行してください。',
    'ru': 'Сообщение слишком длинное. Сократите его и повторите попытку.',
}


def _rate_limit_retry_after():
    """Return seconds to wait if the window is full, else 0 (and record a hit)."""
    now = time.monotonic()
    with _rate_lock:
        while _rate_hits and now - _rate_hits[0] > _RATE_WINDOW:
            _rate_hits.popleft()
        if len(_rate_hits) >= _RATE_MAX:
            return int(_RATE_WINDOW - (now - _rate_hits[0])) + 1
        _rate_hits.append(now)
        return 0


def _localized(table, language):
    return table.get(language if language in table else 'en', table['en'])


def _parse_env_value(raw):
    """Parse the value half of a dotenv `KEY=value` line.

    A quoted value is taken verbatim (so a literal '#' can be kept by quoting).
    An UNquoted value drops any inline ' # comment' — without this the comment
    glues onto the value and silently corrupts it; a `GROQ_API_KEY=gsk_… # note`
    line then ships a malformed key that Groq rejects with 401 (api_key_invalid).
    """
    v = raw.strip()
    if v[:1] in ('"', "'"):
        quote = v[0]
        end = v.find(quote, 1)
        return v[1:end] if end != -1 else v[1:]
    return re.split(r'\s#', v, maxsplit=1)[0].strip()


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
                os.environ.setdefault(_k.strip(), _parse_env_value(_v))

_DEV_GROQ_KEY = os.environ.get('GROQ_API_KEY', '')
_AI_MODEL = os.environ.get('AI_MODEL', 'llama-3.1-8b-instant')


def _dev_key():
    """The local Groq key, honoured ONLY in a source/dev run.

    The .env GROQ_API_KEY is a developer convenience: it lets a source run
    (`python main.py` / setup-3-run.command) use the AI chatbot with no
    activation token. An installed/frozen build must NOT honour it — otherwise
    dropping a .env beside the binary would bypass activation entirely — so a
    real token is mandatory there. Centralising the rule here keeps every AI
    code path (mode selection + proxy fallback) in lockstep.
    """
    return '' if state.IS_FROZEN else _DEV_GROQ_KEY


def _get_api_mode():
    """Return ('proxy', license_token), ('dev', api_key), or (None, None).

    Proxy mode requires a token that passes the same hardware-lock check as the
    activation gate (activation.is_activated() → verify_token(): RS256 signature +
    hwid claim + not expired). Keying off mere token presence would report an
    expired, forged, or copied-from-another-machine token as "activated/AI ready"
    here while the gate simultaneously rejects it — so a copied activation.json
    must be useless on the AI surface too, not just the page gate.

    The dev (local Groq key) branch is suppressed in an installed build via
    _dev_key(): there, only a valid activation token unlocks the AI assistant.
    """
    if activation_mod.is_activated():
        return 'proxy', activation_mod.get_license_token()
    dev_key = _dev_key()
    if dev_key:
        return 'dev', dev_key
    return None, None


@ai_bp.route('/status', methods=['GET'])
def ai_status():
    mode, _ = _get_api_mode()
    return jsonify({
        'status': 'success',
        'api_ready': mode is not None,
        'activated': mode == 'proxy',
        'dev_mode': mode == 'dev',
        'supported_languages': user_settings.SUPPORTED_LANGUAGES,
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
            json={'token': token, 'hwid': activation_mod.get_hwid()}, timeout=15,
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

    # Server just confirmed/bound the token — seed the revocation grace clock so
    # the freshly-activated app doesn't immediately hit the reverify gate.
    activation_mod.record_status('active')

    return jsonify({'status': 'success', 'message': 'AI assistant activated'})


@ai_bp.route('/chat', methods=['POST'])
def ai_chat():
    data = request.get_json(silent=True) or {}
    language = data.get('language') or 'en'
    raw_messages = data.get('messages', [])
    messages = [
        m for m in raw_messages
        if isinstance(m, dict)
        and m.get('role') in ('user', 'assistant')
        and isinstance(m.get('content', ''), str)
    ]
    if not messages:
        return jsonify({'status': 'failure', 'message': 'No messages provided'}), 400

    # Payload caps (before any upstream call): drop all but the newest N turns,
    # then reject anything still oversized so a crafted request can't run up a
    # huge paid proxy call or stall the model.
    messages = messages[-_MAX_MESSAGES:]
    total_chars = sum(len(m.get('content', '')) for m in messages)
    if total_chars > _MAX_TOTAL_CHARS or any(
        len(m.get('content', '')) > _MAX_MSG_CHARS for m in messages
    ):
        return jsonify({'status': 'failure',
                        'message': _localized(_TOO_LARGE_MSG, language)}), 413

    mode, credential = _get_api_mode()
    if not mode:
        return jsonify({'status': 'failure', 'message': 'AI assistant is not activated'}), 503

    # Server-side rate-limit backstop (the browser limiter is bypassable).
    wait = _rate_limit_retry_after()
    if wait > 0:
        resp = jsonify({'status': 'failure',
                        'message': _localized(_RATE_LIMITED_MSG, language).format(s=wait)})
        resp.headers['Retry-After'] = str(wait)
        return resp, 429

    ui_context = data.get('ui_context') or {}

    _PROXY_TRANSIENT_ERRORS = frozenset({'proxy_unreachable', 'proxy_timeout'})

    if mode == 'proxy':
        # On a transient proxy outage a source run can fall back to the local
        # Groq key; an installed build cannot (_dev_key() is empty when frozen),
        # so its AI stays strictly behind the activated proxy.
        dev_fallback = _dev_key()

        def generate():
            fell_back = False
            for event in ai_assistant.proxy_chat_stream(
                messages, language, credential,
                activation_mod.AI_SERVICE_URL, _AI_MODEL, ui_context,
            ):
                if event.get('type') == 'error' and event.get('error') in _PROXY_TRANSIENT_ERRORS and dev_fallback:
                    fell_back = True
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if fell_back:
                for event in ai_assistant.chat_stream(messages, language, dev_fallback, _AI_MODEL, ui_context):
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
    if lang not in user_settings.SUPPORTED_LANGUAGES:
        lang = 'en'
    return jsonify({
        'status': 'success',
        'examples': ai_assistant.get_guide_examples(lang),
    })


@ai_bp.route('/feedback', methods=['POST'])
@validate_json({
    'rating': (str, '', True),
    'source': (str, '', False),
    'guide_id': (str, '', False),
    'query': (str, '', False),
    'answer': (str, '', False),
    'language': (str, 'en', False),
    'comment': (str, '', False),
})
def ai_feedback_route(validated_data):
    """Record a 👍/👎 on an AI answer.

    Every rating is logged. When the answer was a locally matched guide
    (`source == "guide"` with a `guide_id`), the rating also nudges that guide's
    learned matcher coefficient (see src/ai_feedback.py). LLM answers are logged
    only — Groq cannot be retrained from here.
    """
    rating = (validated_data.get('rating') or '').strip().lower()
    if rating not in ('up', 'down'):
        return jsonify({'status': 'failure', 'message': 'rating must be "up" or "down"'}), 400

    # Respect the opt-out toggle (defence-in-depth; the UI already hides the row).
    if not ai_feedback.is_enabled():
        return jsonify({'status': 'success', 'recorded': False})

    new_weight = ai_feedback.record_feedback(
        rating,
        source=validated_data.get('source') or '',
        guide_id=validated_data.get('guide_id') or '',
        query=validated_data.get('query') or '',
        answer=validated_data.get('answer') or '',
        language=validated_data.get('language') or 'en',
        comment=validated_data.get('comment') or '',
    )
    return jsonify({'status': 'success', 'weight': new_weight})


@ai_bp.route('/feedback/stats', methods=['GET'])
def ai_feedback_stats():
    """Summary of feedback recorded on this machine, for the settings panel."""
    data = ai_feedback.stats()
    data['status'] = 'success'
    data['enabled'] = ai_feedback.is_enabled()
    return jsonify(data)


@ai_bp.route('/feedback/reset', methods=['POST'])
def ai_feedback_reset():
    """Reset learning: delete the rating log and the learned guide weights."""
    ai_feedback.clear(weights=True, log=True)
    return jsonify({'status': 'success'})


@ai_bp.route('/feedback/export', methods=['GET'])
def ai_feedback_export():
    """Download the feedback log + learned weights as a zip archive."""
    paths = ai_feedback.file_paths()
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for arcname, p in (('ai_feedback.jsonl', paths['log']),
                           ('ai_guide_weights.json', paths['weights'])):
            if os.path.exists(p):
                try:
                    zf.write(p, arcname)
                    count += 1
                except OSError:
                    pass
        if count == 0:
            zf.writestr('README.txt', 'No AI feedback has been recorded on this machine yet.\n')
    buf.seek(0)
    filename = f"easyokapi-ai-feedback-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, attachment_filename=filename)


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

    # Cap the query: the local matcher runs difflib over the guide vocabulary,
    # so an unbounded string is wasted work (a real nav phrase is short anyway).
    query = query[:_MAX_MSG_CHARS]

    language = data.get('language') or 'en'
    if language not in user_settings.SUPPORTED_LANGUAGES:
        language = 'en'
    ui_context = data.get('ui_context') or {}

    guide_id, steps = ai_assistant.resolve_guide(query, ui_context, language)
    return jsonify({
        'status': 'success',
        'fires': bool(steps),
        'guide_id': guide_id,
        'steps': steps or [],
    })
