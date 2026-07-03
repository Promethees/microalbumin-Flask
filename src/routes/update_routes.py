import json
import os
import queue
import signal
import threading
import time
from flask import Blueprint, jsonify, render_template, Response, stream_with_context
import requests as _requests
import state
import update_service
import activation as activation_mod
from validators import validate_json

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
            # In-app auto-restart is unreliable (notably the Windows relauncher),
            # so we do not restart here. The client calls /update/finalize next,
            # which shuts the server down and shows a "please relaunch" page.
            yield f"data: {json.dumps({'pct': 100, 'label': 'Update applied. Finishing up...', 'done': True})}\n\n"
            yield "data: [DONE]\n\n"
        else:
            err = result.get('error', 'Unknown error')
            yield f"data: {json.dumps({'pct': 0, 'label': err, 'error': True})}\n\n"
            yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


def _delayed_shutdown(delay_secs=5):
    """Stop the data-logger subprocess, then shut down so the port frees.

    Frozen build with a staged update: hand off to the detached swap helper, which
    waits for the port to free, swaps the install dir, and relaunches the new
    binary. apply_pending_swap_and_exit() spawns that helper and os._exit()s, so it
    only returns (False) when there is nothing to swap (source build / no staged
    update), in which case we fall through to the normal SIGTERM shutdown (mirrors
    core_routes.delayed_termination)."""
    time.sleep(delay_secs)
    try:
        if update_service.apply_pending_swap_and_exit():
            return  # unreachable on success (process already replaced)
    except Exception as e:
        # A failure here (e.g. the swap-coordinator spawn raising because
        # powershell is unresolvable on a frozen PATH) used to vanish silently:
        # the app fell through to a normal shutdown and reopened on the old
        # version with no trace. Record it to the swap log so a stuck update is
        # diagnosable instead of invisible.
        _log_swap_failure(e)
    try:
        update_service._shutdown_current_process()
    except Exception:
        pass
    os.kill(os.getpid(), signal.SIGTERM)


def _log_swap_failure(exc):
    """Best-effort append of a pending-swap handoff failure to update_swap.txt."""
    try:
        log_path = update_service._swap_log_path()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        stamp = time.strftime('%Y-%m-%dT%H:%M:%S')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f'[{stamp}] [finalize] apply_pending_swap_and_exit failed: '
                    f'{type(exc).__name__}: {exc}\n')
    except Exception:
        pass


@update_bp.route('/finalize', methods=['POST'])
@validate_json({'mode': (str, 'light', False)})
def finalize_update(validated_data):
    """Shut the server down after an applied update and return a page that closes
    the tab and reminds the user to relaunch the app into the new code.

    Auto-restart from inside the running process is unreliable, so instead we stop
    cleanly here and let the user relaunch — same shutdown mechanism as /shutdown.
    """
    # Validation runs first, so a malformed body gets a 400 without marking the
    # reset-display sentinel or scheduling the shutdown.
    state.mark_reset_display_pending()
    threading.Thread(target=_delayed_shutdown, daemon=True).start()
    mode = validated_data['mode'] or 'light'
    return render_template('restart_required.html',
                           production_mode=state.PRODUCTION_MODE, mode=mode)
