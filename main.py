# ── CDC-logger re-entrant mode ───────────────────────────────────────────────
# To collect colorimeter readings the app re-invokes *itself* with --cdc-logger
# (see routes/hardware_routes.run_script). In a frozen build there is no python
# interpreter or log_cdc_data.py on disk to spawn, so the single binary plays
# both roles: this branch runs the CDC data collector and exits before Flask is
# imported. CDC serial needs no elevated privileges. In dev this path is unused
# (hardware_routes runs log_cdc_data.py directly), but it works there too.
import sys as _sys

if '--cdc-logger' in _sys.argv:
    import os as _o

    # In dev the collector modules sit in the project root + src/; a frozen build
    # bundles them so they import directly.
    if not getattr(_sys, 'frozen', False):
        _root = _o.path.dirname(_o.path.abspath(__file__))
        for _p in (_root, _o.path.join(_root, 'src')):
            if _p not in _sys.path:
                _sys.path.insert(0, _p)

    import log_cdc_data as _logger
    _sys.exit(_logger.main())

# ── Startup progress reporter ────────────────────────────────────────────────
# Writes "pct label\n" lines to a named FIFO or temporary file so launch
# scripts can drive the terminal progress bar in real time.
# Fails silently when the channel is absent.
import os as _os

if _os.name == "nt":  # Windows
    # On Windows, we use a plain file in the temp directory
    _PROGRESS_PIPE = _os.path.join(_os.environ.get("TEMP", "."), "easyokapi_progress.txt")
else:                  # POSIX (macOS, Linux)
    # On Unix, we use a named pipe (FIFO)
    _PROGRESS_PIPE = "/tmp/easyokapi_progress.pipe"

_progress_fd = None

def _report(pct: int, label: str) -> None:
    """Send a progress update to the launch script (non-blocking)."""
    global _progress_fd
    try:
        if _os.name == "nt":
            # Direct file write for Windows polling
            with open(_PROGRESS_PIPE, "w") as f:
                f.write(f"{pct} {label}\n")
        else:
            # POSIX pipe logic
            if _progress_fd is None and _os.path.exists(_PROGRESS_PIPE):
                fd = _os.open(_PROGRESS_PIPE, _os.O_WRONLY | _os.O_NONBLOCK)
                _progress_fd = _os.fdopen(fd, "w", buffering=1)
            if _progress_fd is not None:
                _progress_fd.write(f"{pct} {label}\n")
                _progress_fd.flush()
    except (OSError, IOError):
        pass        # path not ready yet or pipe closed — ignore

_report(5, "Python runtime ready …")

# ── Core stdlib + Flask ──────────────────────────────────────────────────────
from flask import Flask, request, redirect, render_template, jsonify
_report(15, "Loading Flask framework …")

import sys
import argparse
import threading
import signal
import atexit
_report(25, "Loading standard libraries …")

# ── Source path setup ────────────────────────────────────────────────────────
# Dev only: a frozen build bundles these modules so no path tweaking is needed.
if not getattr(sys, 'frozen', False):
    if _os.name == "nt":  # Windows
        sys.path.append(r"code\src")
    else:                  # Linux, macOS
        sys.path.append("src")

# ── Project file-path / utility modules ─────────────────────────────────────
# NB: many of these imports are not referenced in this file, but they are
# load-bearing — PyInstaller discovers frozen-build dependencies from them, and
# each import group paces a _report() progress stage. Do not remove as "unused".
_report(30, "Loading file-path utilities …")
from file_path import is_multi_value_timeseries_csv_header
from range import get_range_input
_report(40, "Loading measurement modules …")
from mode import get_mode_input
from measure import sort_csv_file
from quantity import get_quantity_input
_report(50, "Loading file/data modules …")
from file import get_file_list, get_dynamic_data, replace_empty, merge_csv_files
from file_operations import remove_csv_columns
from get_next_filename import get_next_filename
_report(60, "Loading monitoring & export modules …")
from script_monitor import check_log_for_errors
from export_cal_json import processJSONCoef, extractAnalysisCoefficients, CustomEncoder
from export_data import is_metadata_consistent, write_metadata, write_headers, extract_single_entry
_report(70, "Loading browser & state modules …")
from browser_mgt import open_browser, cleanup, ensure_host_mapping
import state

# ── Routes (blueprints) ──────────────────────────────────────────────────────
_report(78, "Loading route blueprints …")
from routes.core_routes import core_bp
_report(83, "Loading route blueprints …")
from routes.hardware_routes import hardware_bp
_report(88, "Loading route blueprints …")
from routes.file_routes import file_bp
from routes.report_routes import report_bp
_report(93, "Loading route blueprints …")
from routes.math_routes import math_bp
from routes.ai_routes import ai_bp
from routes.update_routes import update_bp
from routes.music_routes import music_bp

# ── Flask application ────────────────────────────────────────────────────────
_report(95, "Configuring Flask application …")
import time as _time
# Assets are bundled read-only; resolve them from the bundle root (== project
# root in dev, sys._MEIPASS in a frozen build).
app = Flask(__name__,
            static_folder=_os.path.join(state.bundle_dir, 'static'),
            template_folder=_os.path.join(state.bundle_dir, 'templates'))
app.jinja_env.globals['STATIC_VERSION'] = str(int(_time.time()))
app.register_blueprint(core_bp)
app.register_blueprint(hardware_bp)
app.register_blueprint(file_bp)
app.register_blueprint(report_bp)
app.register_blueprint(math_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(update_bp)
app.register_blueprint(music_bp)

# ── Request-origin guard (CSRF + DNS-rebinding) ──────────────────────────────
# Registered first so a cross-origin / rebound state-changing request is refused
# before any activation/license logic runs. See src/security.py.
from security import init_request_guard
init_request_guard(app)

# ── Activation gate (frozen builds) ──────────────────────────────────────────
# A frozen build is licence-gated: until a valid activation token is stored, every
# page redirects to /activate and every API/AI call returns 403. This makes the
# token compulsory on macOS (drag-install DMG) and Linux (tarball) — which have no
# install-time prompt — mirroring the Windows installer's required token. Source/
# dev builds are never gated (activation.needs_activation() is False there).
import activation as _activation

# Paths reachable while unactivated: the gate page itself, the activation +
# status endpoints it calls, the health check, and static assets (theme/JS).
_ACTIVATION_OPEN_PATHS = {'/activate', '/ai/activate', '/ai/status', '/ping', '/favicon.ico'}


@app.before_request
def _enforce_activation():
    if not _activation.needs_activation():
        return
    path = request.path
    if path in _ACTIVATION_OPEN_PATHS or path.startswith('/static/'):
        return
    if path.startswith('/api/') or path.startswith('/ai/'):
        return jsonify({'status': 'error', 'code': 'not_activated',
                        'message': 'EasyOKAPI is not activated. Enter your activation token to continue.'}), 403
    return redirect('/activate')


@app.route('/activate')
def activate_page():
    # Already activated (or a non-gated dev build) → straight to the app.
    if not _activation.needs_activation():
        return redirect('/')
    return render_template('activate.html', title='Activate EasyOKAPI',
                           ai_service_url=_activation.AI_SERVICE_URL)


# ── License revocation gate (frozen builds) ──────────────────────────────────
# An activated machine whose license the admin has revoked server-side must stop
# working, even though its permanent token still verifies offline. license_state()
# reports 'revoked' (sticky, per-machine deactivation), 'banned' (sticky, whole
# account suspended), 'needs_recheck' (grace lapsed while offline — ask the user
# to reconnect) or 'active'. See src/activation.py.
_LICENSE_OPEN_PATHS = {'/license-blocked', '/license-banned', '/license-reverify',
                       '/license/recheck', '/ping', '/favicon.ico'}


@app.before_request
def _enforce_license():
    state_ = _activation.license_state()
    if state_ == 'active':
        return
    path = request.path
    if path in _LICENSE_OPEN_PATHS or path.startswith('/static/'):
        return
    if path.startswith('/api/') or path.startswith('/ai/'):
        code = {'revoked': 'license_revoked', 'banned': 'license_banned'}.get(state_, 'license_recheck')
        return jsonify({'status': 'error', 'code': code,
                        'message': 'This license is not currently valid on this machine.'}), 403
    if state_ == 'banned':
        return redirect('/license-banned')
    return redirect('/license-blocked' if state_ == 'revoked' else '/license-reverify')


@app.route('/license-blocked')
def license_blocked_page():
    # Only a revoked license sees this dead-end; anything else returns to the app
    # (or, for a banned account, to its own page via the gate on '/').
    if _activation.license_state() != 'revoked':
        return redirect('/')
    return render_template('license_blocked.html', title='License Deactivated',
                           ai_service_url=_activation.AI_SERVICE_URL,
                           support_email=state.MAINTAINER_EMAIL,
                           app_version=state.APP_VERSION)


@app.route('/license-banned')
def license_banned_page():
    # The dead-end for a whole-account ban (User.banned on the server). Distinct
    # from /license-blocked, which is a single-machine license deactivation.
    if _activation.license_state() != 'banned':
        return redirect('/')
    return render_template('license_banned.html', title='Account Suspended',
                           ai_service_url=_activation.AI_SERVICE_URL,
                           support_email=state.MAINTAINER_EMAIL,
                           app_version=state.APP_VERSION)


@app.route('/license-reverify')
def license_reverify_page():
    st = _activation.license_state()
    if st == 'active':
        return redirect('/')
    if st == 'revoked':
        return redirect('/license-blocked')
    if st == 'banned':
        return redirect('/license-banned')
    return render_template('license_reverify.html', title='Verify License',
                           ai_service_url=_activation.AI_SERVICE_URL,
                           support_email=state.MAINTAINER_EMAIL,
                           app_version=state.APP_VERSION)


@app.route('/license/recheck', methods=['POST'])
def license_recheck():
    """Re-poll the server now (used by the gate pages) and report the verdict.

    On an 'offline' result the page must tell the user whose problem it is — no
    internet on this machine, or our service being down — so the reply carries
    the reason from check_revocation_detailed() plus the few facts a support
    report needs (version, hwid, service URL). All of it is local to this
    machine and already known to it; nothing new is disclosed.
    """
    result, reason = _activation.check_revocation_detailed()
    return jsonify({'status': 'success', 'result': result, 'reason': reason,
                    'state': _activation.license_state(),
                    # The base actually in use, not the branded name — when the
                    # branded domain is the thing that broke, "which address did
                    # it manage to reach?" is the first question a report answers.
                    'service_url': _activation.service_base(),
                    'service_urls': _activation.service_bases(),
                    'app_version': state.APP_VERSION,
                    'hwid': _activation.get_hwid()})

# Endpoints moved to their respective blueprints

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the Flask app with a specified port and alias.')
    parser.add_argument('--port', type=int, default=5099, help='Port to run the Flask app on (default: 5099)')
    parser.add_argument('--alias', type=str, default='easyokapi.com', help='Optional domain alias (e.g., mydomain.com)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output (e.g. detailed HTTP logging).')
    parser.add_argument('--mem-monitor', action='store_true', help='Enable memory monitoring to guard against memory leaks.')
    parser.add_argument('--no-browser', action='store_true',
                        help='Do not auto-open a browser tab on startup. Used by restart relaunches '
                             '(data-folder relocation / applied update) where the existing tab reloads '
                             'itself — opening a second tab would race it for the one-shot reset-display '
                             'marker and leave the user-facing tab without the default-display reset.')

    # We assign to state args directly
    state.args = parser.parse_args()

    original_stdout = sys.stdout
    import logging
    import os
    if not state.args.verbose:
        # Hide standard HTTP request logs for a cleaner terminal interface
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        # Suppress all explicit backend print commands
        sys.stdout = open(os.devnull, 'w')

    if getattr(state.args, 'mem_monitor', False):
        def _mem_monitor_thread():
            import tracemalloc, time

            # ANSI color codes
            RED = "\033[91m"
            YELLOW = "\033[93m"
            GREEN = "\033[92m"
            RESET = "\033[0m"

            tracemalloc.start()
            baseline = None
            WARN_GROWTH_MB = float(os.environ.get("MEM_WARN_GROWTH_MB", "50"))
            CRITICAL_GROWTH_MB = float(os.environ.get("MEM_CRITICAL_GROWTH_MB", "100"))
            INTERVAL_SEC = int(os.environ.get("MEM_MONITOR_INTERVAL", "10"))

            print(f"{GREEN}[MemGuard] Memory tracking started.{RESET}", file=original_stdout, flush=True)

            while True:
                try:
                    time.sleep(INTERVAL_SEC)
                    current, peak = tracemalloc.get_traced_memory()
                    current_mb = current / 1024 / 1024
                    peak_mb = peak / 1024 / 1024

                    if baseline is None:
                        baseline = current_mb

                    growth = current_mb - baseline

                    if growth > CRITICAL_GROWTH_MB:
                        color = RED
                        flag = " 🔴 CRITICAL: Possible memory leak!"
                    elif growth > WARN_GROWTH_MB:
                        color = YELLOW
                        flag = " 🟡 WARNING: Memory growing"
                    else:
                        color = GREEN
                        flag = ""

                    print(
                        f"{color}[MemGuard] Current: {current_mb:.2f} MB | Peak: {peak_mb:.2f} MB"
                        f" | Growth: +{growth:.2f} MB{flag}{RESET}",
                        file=original_stdout, flush=True
                    )
                except Exception as e:
                    print(f"{RED}[MemGuard] Monitor error: {e}{RESET}", file=original_stdout, flush=True)
                    break
        threading.Thread(target=_mem_monitor_thread, daemon=True).start()

    host = '127.0.0.1'
    port = state.args.port
    alias = state.args.alias or host

    if alias and alias != '127.0.0.1':
        ensure_host_mapping(alias)

    # Launch browser with alias. Skipped on a restart relaunch (--no-browser):
    # the user's existing tab reloads itself, and opening a second tab here would
    # race it for the one-shot reset-display marker (see update_service.restart_after_delay).
    if not state.args.no_browser:
        browser_thread = threading.Thread(target=open_browser, args=(alias, port), daemon=True)
        browser_thread.start()

    # Best-effort: upgrade a freshly-installed raw download token to a permanent
    # license token while it is still valid. Runs off the launch path so a slow or
    # unreachable auth server never delays startup. See activation.ensure_permanent_token().
    def _ensure_permanent_token():
        try:
            import activation
            activation.ensure_permanent_token()
        except Exception:
            pass
    threading.Thread(target=_ensure_permanent_token, daemon=True).start()

    # Best-effort: poll the server for admin revocation of this machine's license,
    # once at startup and then periodically, so a revoke takes effect on a running
    # app without a restart. Runs off the launch path; a successful 'active' check
    # refreshes the grace clock, a 'revoked' verdict sticks. See activation.check_revocation().
    def _license_revocation_watch():
        import time as _t
        import activation
        # Re-upgrade race: give the token-upgrade thread a moment so a just-installed
        # download token becomes permanent before the first check.
        _t.sleep(3)
        interval = max(900, int(os.environ.get('LICENSE_CHECK_INTERVAL', str(6 * 3600))))
        while True:
            try:
                activation.check_revocation()
            except Exception:
                pass
            _t.sleep(interval)
    threading.Thread(target=_license_revocation_watch, daemon=True).start()

    # Keep the Windows uninstaller / Add-Remove Programs version in sync with this
    # build. An in-app binary swap replaces the exe but not the registry, so the
    # entry would otherwise advertise the previous version. Best-effort, off the
    # launch path. See update_service.refresh_uninstall_entry().
    def _refresh_uninstall_entry():
        try:
            import update_service
            update_service.refresh_uninstall_entry()
        except Exception:
            pass
    threading.Thread(target=_refresh_uninstall_entry, daemon=True).start()

    # Sweep the previous update's scratch files out of the data root. The swap
    # helpers outlive the process that spawns them, so startup is the only place
    # this can happen — see update_service.cleanup_stale_artifacts(), which
    # no-ops while a swap is still pending retry.
    def _cleanup_update_artifacts():
        try:
            import update_service
            update_service.cleanup_stale_artifacts()
        except Exception:
            pass
    threading.Thread(target=_cleanup_update_artifacts, daemon=True).start()

    atexit.register(cleanup, state.process, state.log_file, state.args)

    def _shutdown_handler(signum, frame):
        """Handle SIGTERM/SIGINT by triggering registered atexit handlers and exiting cleanly."""
        print(f"Received signal {signum}, shutting down gracefully...")
        sys.exit(0)  # triggers atexit.register(cleanup, ...)

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    _report(100, "Server starting …")
    if _progress_fd is not None:
        try:
            _progress_fd.close()
        except OSError:
            pass

    try:
        # use_reloader=False prevents Werkzeug from spawning a child reloader process.
        # That child process is the main source of "leaked semaphore" warnings on shutdown.
        #
        # debug is enabled ONLY for source/dev runs. A frozen/installed build must
        # never run with the Werkzeug interactive debugger: an unhandled exception
        # would render a full traceback (leaking source + locals) and expose the
        # PIN-gated code-execution console on 127.0.0.1 — a real RCE/info-disclosure
        # surface reachable from any web page the user visits (there is no CSRF
        # token on these localhost routes).
        app.run(debug=not state.IS_FROZEN, host=host, port=port, use_reloader=False)
    except Exception as e:
        print(f"Failed to start Flask server: {e}")
        sys.exit(1)