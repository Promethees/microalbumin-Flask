"""Attach/detach for the developer performance monitor.

``attach_monitor(app)`` is the single entry point ``main.py`` knows about. It
registers the dev blueprint, installs the HTTP timers and the production-module
wrappers, and flips the flag every dev route checks. Nothing in this package
runs until it is called, and it is only called behind ``--monitor``.

It refuses to attach in a frozen build. That is belt and braces — ``devtools``
is excluded from ``easyokapi.spec`` so the package is not even present in a
shipped bundle — but the check is here rather than in ``main.py`` so it is one
testable function rather than a condition in a script's ``__main__``.
"""

import sys
import time

from .metrics import registry

# Dev routes live under one obviously non-production prefix. Everything below it
# 404s unless the monitor is attached, so a normal run looks like a build that
# never had these routes.
MONITOR_PREFIX = '/__dev/monitor'

_enabled = False
_attached_app = None


def is_enabled():
    """True only while the monitor is attached to a running app."""
    return _enabled


def is_frozen():
    """Frozen/production context detection, matching src/state.IS_FROZEN."""
    if getattr(sys, 'frozen', False):
        return True
    try:
        import state
        return bool(getattr(state, 'IS_FROZEN', False))
    except Exception:
        return False


def monitor_url(host='127.0.0.1', port=5099):
    return f'http://{host}:{port}{MONITOR_PREFIX}'


def attach_monitor(app, install_hooks=True, trace_allocations=False):
    """Turn the monitor on for ``app``. Returns True when it attached.

    Must run before the app serves its first request — Flask 3 refuses a
    blueprint or ``before_request`` registration after that (Rule.md §2.37) —
    which is exactly where ``main.py`` calls it.

    Allocation tracing is **off** until you ask for it on the page. Measured on
    this app: ``/__dev/monitor/metrics`` answers in 14.5 ms with tracing off and
    246 ms with it on — ``take_snapshot()`` copies every traced allocation — so
    leaving it on by default would spend a quarter of a core inside a request
    handler for as long as a tab is open, to answer a question nobody asked yet.
    """
    global _enabled, _attached_app

    if is_frozen():
        print('[devmon] --monitor ignored: the performance monitor is a '
              'source-tree developer tool and never runs in a frozen build.',
              file=sys.stderr, flush=True)
        return False

    from .routes import devtools_bp

    # Guarded on the app, not on _enabled: attaching to a second app (a test's
    # throwaway one, say) must still register there, while attaching twice to
    # the same app must not stack a second copy of the request timers.
    if 'devtools' not in app.blueprints:
        app.register_blueprint(devtools_bp)
        _install_http_timers(app)

    if trace_allocations:
        registry.start_tracemalloc()
    if install_hooks:
        from . import hooks
        hooks.install()

    _enabled = True
    _attached_app = app
    return True


def detach_monitor():
    """Undo what attach_monitor did to the production modules.

    The blueprint and the ``before_request`` cannot be unregistered — Flask has
    no API for it — but every dev route is gated on ``is_enabled()``, so a
    detached monitor's routes 404 like they were never there. The wrappers and
    the tracing, which are the parts with a cost, are genuinely removed.
    """
    global _enabled, _attached_app
    from . import hooks
    hooks.uninstall()
    registry.stop_tracemalloc()
    _enabled = False
    _attached_app = None


def _install_http_timers(app):
    """Per-request clock, registered from here and nowhere else.

    Requests to the monitor's own routes are skipped: the page polls once a
    second, so counting itself would make the busiest route in every readout
    the readout.

    This hook is registered last (``attach_monitor`` runs after the origin guard
    and the licence gates), so a request one of *those* rejects never starts our
    clock. It is still counted — with no latency sample — rather than dropped,
    because a wall of blocked POSTs is exactly the sort of thing the readout is
    for.
    """
    from flask import g, request

    def _identify():
        # Only a *matched* rule is ever stored. Everything unrouted collapses
        # onto the single '(unmatched)' row — which is what keeps the table
        # bounded under 404 spam — and its raw path is never kept: that path is
        # caller-supplied text, and the page renders these strings. A page the
        # developer happens to be visiting can issue a cross-origin GET to
        # http://127.0.0.1:<port>/<anything> (the origin guard only covers
        # unsafe methods, as it should — a GET changes nothing), so the path of
        # a 404 is attacker-chosen, and storing it would hand that string to
        # the monitor page to render inside the app's own origin.
        endpoint = request.endpoint or '(unmatched)'
        rule = str(request.url_rule) if request.url_rule else ''
        return endpoint, rule

    def _record(elapsed_ms, status_code, failed=False):
        endpoint, rule = _identify()
        registry.http_end(endpoint, rule, elapsed_ms, status_code, failed=failed)

    @app.before_request
    def _devmon_request_begin():
        if request.path.startswith(MONITOR_PREFIX):
            return None
        g._devmon_started = time.monotonic()
        registry.http_begin()
        return None

    @app.after_request
    def _devmon_request_end(response):
        if request.path.startswith(MONITOR_PREFIX):
            return response
        started = g.pop('_devmon_started', None)
        elapsed = None if started is None else (time.monotonic() - started) * 1000.0
        if started is None:
            # Never entered our before_request: an earlier gate short-circuited.
            registry.http_begin()
        _record(elapsed, response.status_code)
        return response

    @app.teardown_request
    def _devmon_request_teardown(exc):
        # after_request does not run when the view raised, so the in-flight
        # count would drift up by one per unhandled exception without this.
        started = g.pop('_devmon_started', None)
        if started is None:
            return
        _record((time.monotonic() - started) * 1000.0, None, failed=True)
