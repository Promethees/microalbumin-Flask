"""Blueprint for the developer performance monitor.

Namespaced under ``/__dev/monitor`` and dead unless ``attach_monitor()`` has
run: the blueprint's ``before_request`` answers **404**, not 403, for every
endpoint under it while the monitor is off, so a normal run looks like a build
that never had these routes rather than one that is hiding them.

The routes ride the app's own request-origin guard (``src/security.py``) like
every other route — the POST below is an unsafe method and is refused
cross-origin exactly as ``/delete_file`` is. Nothing is exempted here.

Deliberately **not** internationalised and **not** driven by ``user_settings``:
this is a developer tool with one audience and one machine. See
``devtools/README.md``.
"""

from flask import Blueprint, abort, jsonify, render_template

from validators import validate_json

from . import monitor
from .metrics import registry

devtools_bp = Blueprint(
    'devtools', __name__,
    url_prefix=monitor.MONITOR_PREFIX,
    template_folder='templates',
    static_folder='static',
    # Blueprint static paths are prefixed with url_prefix, so this serves at
    # /__dev/monitor/assets/… and stays inside the one dev namespace.
    static_url_path='/assets',
)


@devtools_bp.before_request
def _only_when_attached():
    """404 the whole namespace while the monitor is off."""
    if not monitor.is_enabled():
        abort(404)
    return None


# Both spellings get a real rule rather than one of them 308-ing to the other:
# a routing redirect is produced before any blueprint ``before_request`` runs,
# so the bare-prefix URL would answer 308 — and confirm the namespace exists —
# even with the monitor off.
@devtools_bp.route('', methods=['GET'])
@devtools_bp.route('/', methods=['GET'])
def monitor_page():
    return render_template('devtools_monitor.html')


@devtools_bp.route('/metrics', methods=['GET'])
def monitor_metrics():
    """The whole readout as JSON. The page polls this; so can curl."""
    payload = registry.snapshot()
    payload['status'] = 'success'
    return jsonify(payload)


@devtools_bp.route('/control', methods=['POST'])
@validate_json({'action': (str, None, True)})
def monitor_control(validated_data):
    """Counter reset and allocation-tracing toggle.

    Tracing is a toggle because it is the one expensive thing the monitor does:
    with it on, every allocation in the process takes a frame capture. Turning
    it off is how you measure the app rather than the monitor — and the switch
    never stops tracing that ``--mem-monitor`` started (see
    ``Registry.stop_tracemalloc``).
    """
    action = validated_data['action']
    if action == 'reset':
        registry.reset_counters()
    elif action == 'trace_on':
        registry.start_tracemalloc()
    elif action == 'trace_off':
        registry.stop_tracemalloc()
    else:
        return jsonify({'status': 'error', 'message': f'Unknown action: {action}'}), 400
    return jsonify({'status': 'success', 'action': action})
