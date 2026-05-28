import json
import queue
import threading
from flask import Blueprint, jsonify, request, Response, stream_with_context
import requests as _requests
import update_service
import activation as activation_mod

update_bp = Blueprint('update', __name__, url_prefix='/update')


@update_bp.route('/check', methods=['GET'])
def check_update():
    """Return current vs latest version info from the online server."""
    try:
        info = update_service.check_for_update()
        return jsonify({'status': 'success', **info})
    except (_requests.exceptions.ConnectionError, _requests.exceptions.Timeout):
        return jsonify({'status': 'unreachable', 'message': 'Update server is not reachable.'})
    except _requests.exceptions.HTTPError as e:
        return jsonify({'status': 'unreachable', 'message': str(e)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@update_bp.route('/apply', methods=['POST'])
def apply_update():
    """SSE stream: download + apply update, then restart.

    Events: {"pct": int, "label": str}
    Final events: {"pct": 100, "label": "...", "done": true}
                  {"pct": 0,   "label": "...", "error": true}
    """
    if not activation_mod.get_license_token():
        return jsonify({'status': 'error', 'message': 'Not activated'}), 403

    def generate():
        q = queue.Queue()
        result = {}

        def progress_cb(pct, label):
            q.put({'pct': pct, 'label': label})

        def worker():
            try:
                update_service.download_and_apply(progress_cb=progress_cb)
                result['ok'] = True
            except Exception as e:
                result['error'] = str(e)
            finally:
                q.put(None)

        threading.Thread(target=worker, daemon=True).start()

        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

        if result.get('ok'):
            yield f"data: {json.dumps({'pct': 100, 'label': 'Restarting...', 'done': True})}\n\n"
            yield "data: [DONE]\n\n"
            update_service.restart_after_delay(1.5)
        else:
            err = result.get('error', 'Unknown error')
            yield f"data: {json.dumps({'pct': 0, 'label': err, 'error': True})}\n\n"
            yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
