"""Tests for the developer-only performance monitor (devtools/, --monitor).

The properties that matter here are the ones that keep a developer tool from
becoming a user-facing one: the routes do not exist unless the monitor is
attached, the flag is refused in a frozen build, the production modules are
wrapped only while attached and are restored exactly on detach, and the
snapshot keeps its shape whether or not psutil is installed.

Every test attaches to a *local* Flask app rather than the shared ``main.app``:
Flask 3 refuses blueprint/``before_request`` registration once an app has served
a request (Rule.md §2.37), and the shared app is used by ~40 other test modules.
"""

import sys
from unittest.mock import patch

import pytest
from flask import Flask

import devtools
from devtools import hooks, metrics as _metrics, monitor
from devtools.metrics import Registry, registry


@pytest.fixture
def dev_app():
    """A fresh app with the monitor attached; detached again on teardown."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    registry.reset_counters()
    assert monitor.attach_monitor(app) is True
    try:
        yield app
    finally:
        monitor.detach_monitor()
        registry.reset_counters()


@pytest.fixture
def dev_client(dev_app):
    return dev_app.test_client()


# --- the routes do not exist unless attached ---------------------------------

def test_routes_404_when_flag_is_off(client):
    """The shared app never had attach_monitor() called: nothing is registered."""
    assert monitor.is_enabled() is False
    for path in ('/__dev/monitor', '/__dev/monitor/', '/__dev/monitor/metrics',
                 '/__dev/monitor/assets/monitor.css'):
        assert client.get(path).status_code == 404, path


def test_routes_404_after_detach(dev_app):
    """Attached-then-detached must look exactly like never-attached.

    Flask cannot unregister a blueprint, so the rules survive detach; the
    blueprint's own before_request is what makes them 404 anyway.
    """
    dev_client = dev_app.test_client()
    assert dev_client.get('/__dev/monitor/metrics').status_code == 200

    monitor.detach_monitor()
    assert dev_client.get('/__dev/monitor/metrics').status_code == 404
    assert dev_client.get('/__dev/monitor/').status_code == 404
    # The bare prefix has its own rule, so it 404s rather than 308-ing.
    assert dev_client.get('/__dev/monitor').status_code == 404
    assert dev_client.get('/__dev/monitor/assets/monitor.css').status_code == 404
    assert dev_client.post('/__dev/monitor/control',
                           json={'action': 'reset'}).status_code == 404


def test_bare_prefix_does_not_redirect_when_disabled(client):
    """A 308 to the slashed URL would confirm the namespace exists.

    Routing redirects are produced before any blueprint before_request runs, so
    both spellings have to be real rules — see devtools/routes.py.
    """
    assert client.get('/__dev/monitor').status_code == 404


# --- the frozen refusal ------------------------------------------------------

def test_monitor_refused_when_frozen():
    app = Flask(__name__)
    with patch.object(sys, 'frozen', True, create=True):
        assert monitor.is_frozen() is True
        assert monitor.attach_monitor(app) is False
    assert monitor.is_enabled() is False
    assert 'devtools' not in app.blueprints


def test_monitor_refused_when_state_reports_frozen():
    """state.IS_FROZEN is the repo's own frozen flag; honour it too."""
    import state
    app = Flask(__name__)
    with patch.object(state, 'IS_FROZEN', True):
        assert monitor.attach_monitor(app) is False
    assert monitor.is_enabled() is False


def test_main_declares_the_flag():
    """--monitor must be an argparse flag beside the existing ones."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'main.py'), encoding='utf-8') as f:
        source = f.read()
    assert "add_argument('--monitor', action='store_true'" in source
    # The import must stay inside the flag: a top-level `import devtools` would
    # make a shipped build (which has no devtools/) fail at startup.
    assert 'from devtools import attach_monitor' in source
    assert source.index("if getattr(state.args, 'monitor', False):") \
        < source.index('from devtools import attach_monitor')


def test_devtools_is_excluded_from_the_frozen_build():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'easyokapi.spec'), encoding='utf-8') as f:
        spec = f.read()
    excludes = spec[spec.index('excludes=['):]
    excludes = excludes[:excludes.index(']')]
    assert "'devtools'" in excludes
    # …and no hiddenimport may drag it back in.
    hidden = spec[spec.index('hiddenimports = ['):spec.index('block_cipher')]
    assert 'devtools' not in hidden


def test_devtools_is_excluded_from_the_source_tarball():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, '.gitattributes'), encoding='utf-8') as f:
        assert '/devtools export-ignore' in f.read()


# --- metrics JSON shape ------------------------------------------------------

def test_metrics_json_shape(dev_client):
    payload = dev_client.get('/__dev/monitor/metrics').get_json()
    assert payload['status'] == 'success'
    assert payload['uptime_sec'] >= 0

    process = payload['process']
    for key in ('pid', 'source', 'cpu_percent', 'threads', 'open_fds', 'gc', 'tracemalloc'):
        assert key in process, key
    for key in ('counts', 'collections', 'collected', 'uncollectable', 'garbage'):
        assert key in process['gc'], key
    # No total object count: len(gc.get_objects()) walks the whole heap (~45 ms
    # and ~2.5 MB of transient list at 300k objects), which at 1 Hz would show
    # up on the monitor's own allocation table. See devtools/metrics._gc_stats.
    assert 'objects' not in process['gc']
    assert set(payload['http']) == {'total', 'errors', 'in_flight', 'routes'}

    device = payload['device']
    for key in ('bytes_in', 'bytes_out', 'lines_in', 'read_timeouts', 'malformed_lines',
                'lines_unmatched', 'lines_per_sec', 'connects', 'connect_failures',
                'port', 'ping_probe', 'command', 'link_connected', 'session_owns_port',
                'logger'):
        assert key in device, key

    stream = payload['stream']
    for key in ('clients_active', 'clients_total', 'frames', 'bytes_pushed',
                'last_log_offset', 'last_csv_offset'):
        assert key in stream, key


def test_metrics_shape_survives_psutil_being_absent(dev_client):
    """No user installs psutil, so the fallback path has to keep the contract."""
    import devtools.metrics as metrics_mod
    with patch.object(metrics_mod, 'psutil', None):
        payload = dev_client.get('/__dev/monitor/metrics').get_json()
    process = payload['process']
    assert process['source'] == 'stdlib'
    assert process['cpu_percent'] is not None
    assert process['threads'] >= 1
    # getrusage can only give the peak, and the fallback must not pass a peak
    # off as the current RSS.
    assert process['rss_bytes'] is None
    assert 'rss_peak_bytes' in process


def test_page_renders(dev_client):
    body = dev_client.get('/__dev/monitor/').get_data(as_text=True)
    assert 'Performance Monitor' in body
    assert '/__dev/monitor/assets/monitor.js' in body


def test_control_resets_counters(dev_client):
    registry.http_end('x', '/x', 12.0, 200)
    assert dev_client.get('/__dev/monitor/metrics').get_json()['http']['total'] == 1

    rv = dev_client.post('/__dev/monitor/control', json={'action': 'reset'})
    assert rv.status_code == 200
    assert dev_client.get('/__dev/monitor/metrics').get_json()['http']['total'] == 0


def test_control_rejects_unknown_action_and_non_json(dev_client):
    assert dev_client.post('/__dev/monitor/control',
                           json={'action': 'rm -rf'}).status_code == 400
    # @validate_json guards the body like every other JSON POST in the app.
    assert dev_client.post('/__dev/monitor/control',
                           data='action=reset').status_code == 400
    assert dev_client.post('/__dev/monitor/control', json={}).status_code == 400


# --- HTTP timing hooks -------------------------------------------------------

def test_http_timers_count_requests_and_errors(dev_app):
    @dev_app.route('/ok')
    def _ok():
        return 'ok'

    @dev_app.route('/boom')
    def _boom():
        return 'no', 500

    c = dev_app.test_client()
    c.get('/ok')
    c.get('/ok')
    c.get('/boom')

    http = c.get('/__dev/monitor/metrics').get_json()['http']
    assert http['total'] == 3
    assert http['errors'] == 1
    assert http['in_flight'] == 0
    rules = {row['rule']: row for row in http['routes']}
    assert rules['/ok']['count'] == 2
    assert rules['/ok']['mean_ms'] is not None
    assert rules['/boom']['errors'] == 1
    # The monitor never counts its own polling.
    assert '/__dev/monitor/metrics' not in rules


# --- monkeypatch wrappers: counting and clean restoration --------------------

def _originals():
    import device_link
    import live_stream
    import send_command
    return {
        'read_lines': send_command.LineReader.read_lines,
        'probe': send_command._probe,
        'connect': send_command.connect_to_device,
        'exchange': device_link.DeviceLink._exchange_locked,
        'close': device_link.DeviceLink._close_locked,
        'iter': live_stream.iter_session_events,
        'tail': live_stream._ByteTail.read_lines,
    }


def test_hooks_install_and_restore_cleanly():
    before = _originals()
    assert hooks.installed() is False

    app = Flask(__name__)
    monitor.attach_monitor(app)
    try:
        during = _originals()
        assert hooks.installed() is True
        assert all(during[k] is not before[k] for k in before)
    finally:
        monitor.detach_monitor()

    assert hooks.installed() is False
    assert _originals() == before


def test_hooks_install_is_idempotent():
    app = Flask(__name__)
    monitor.attach_monitor(app)
    try:
        # A second install must not stack a wrapper on a wrapper — that would
        # double every count and never unwind.
        assert hooks.install() == []
        wrapped = _originals()
        assert hooks.install() == []
        assert _originals() == wrapped
    finally:
        monitor.detach_monitor()


class _FakeSerial:
    """Just enough of pyserial for send_command.LineReader."""

    def __init__(self, payload):
        self._payload = payload

    @property
    def in_waiting(self):
        return len(self._payload)

    def read(self, size):
        chunk, self._payload = self._payload[:size], self._payload[size:]
        return chunk


def test_line_reader_wrapper_counts_lines_bytes_and_timeouts(dev_app):
    import send_command
    reader = send_command.LineReader(_FakeSerial(b'ACK_PING\nSTATE:mode=MEASURE;\n'))

    assert reader.read_lines() == ['ACK_PING', 'STATE:mode=MEASURE;']
    # Nothing left: a call that frames no line is a read timeout.
    reader.serial._payload = b''
    assert reader.read_lines() == []

    device = dev_app.test_client().get('/__dev/monitor/metrics').get_json()['device']
    assert device['lines_in'] == 2
    assert device['read_calls'] == 2
    assert device['read_timeouts'] == 1
    assert device['bytes_in'] == len(b'ACK_PING\nSTATE:mode=MEASURE;\n')
    assert device['malformed_lines'] == 0


def test_line_reader_wrapper_flags_malformed_lines(dev_app):
    import send_command
    # An undecodable byte becomes U+FFFD — framing damage, not a device message.
    reader = send_command.LineReader(_FakeSerial(b'AC\xffK\n'))
    reader.read_lines()

    device = dev_app.test_client().get('/__dev/monitor/metrics').get_json()['device']
    assert device['malformed_lines'] == 1


def test_probe_wrapper_times_a_failed_ping_without_opening_a_port(dev_app):
    """The monitor observes the probe; it never runs one of its own.

    ``serial.Serial`` is made to fail, so nothing is opened and the real
    ``_probe`` returns None — the wrapper's failure path, timed.
    """
    import send_command

    with patch('serial.Serial', side_effect=OSError('no such port')):
        assert send_command._probe('/dev/null-not-a-port') is None

    device = dev_app.test_client().get('/__dev/monitor/metrics').get_json()['device']
    assert device['ping_probe']['count'] == 1
    assert device['ping_probe']['errors'] == 1
    assert device['ping_probe']['last_ms'] >= 0
    # Nothing was written anywhere, so the write counter must still be zero.
    assert device['bytes_out'] == 0


def test_connect_wrapper_counts_a_failed_open(dev_app):
    import send_command

    with patch('serial.tools.list_ports.comports', return_value=[]):
        with pytest.raises(Exception):
            send_command.connect_to_device()

    device = dev_app.test_client().get('/__dev/monitor/metrics').get_json()['device']
    assert device['connect_failures'] == 1
    assert device['connects'] == 0
    assert device['port'] is None


class _FakePort:
    """The handful of pyserial methods device_link._exchange_locked calls."""

    def __init__(self):
        self.written = b''

    def reset_input_buffer(self):
        pass

    def write(self, payload):
        self.written += payload

    def flush(self):
        pass


class _FakeReader:
    def __init__(self, lines):
        self.buffer = b''
        self._lines = list(lines)

    def read_lines(self):
        lines, self._lines = self._lines, []
        return lines


def test_device_link_wrapper_counts_command_round_trips(dev_app):
    import device_link

    link = device_link.DeviceLink()
    link._serial = _FakePort()

    # A reply that matches: one command, one matched line, 7 bytes out.
    link._reader = _FakeReader(['ACK_STATE'])
    assert link._exchange_locked('STATE?', lambda line: True) == 'ACK_STATE'

    # No reply: the no-answer timeout, which is the number worth watching.
    link._reader = _FakeReader([])
    with patch.object(device_link, 'REPLY_TIMEOUT', 0.05):
        with pytest.raises(device_link.DeviceLinkError):
            link._exchange_locked('MENU?', lambda line: True)

    device = dev_app.test_client().get('/__dev/monitor/metrics').get_json()['device']
    assert device['command']['count'] == 2
    assert device['command']['errors'] == 1
    assert device['replies_matched'] == 1
    assert device['bytes_out'] == len(b'STATE?\n') + len(b'MENU?\n')
    assert link._serial.written == b'STATE?\nMENU?\n'


def test_device_link_close_wrapper_counts_only_a_real_close(dev_app):
    import device_link

    link = device_link.DeviceLink()
    link._close_locked()                  # nothing was open: not a close
    link._serial = _FakePort()
    link._serial.is_open = False          # close() is skipped, the slot is cleared
    link._close_locked()

    device = dev_app.test_client().get('/__dev/monitor/metrics').get_json()['device']
    assert device['closes'] == 1


def test_live_stream_wrapper_counts_clients_and_frames(dev_app):
    """Drives the real generator through its no-session path."""
    import live_stream

    with patch.object(live_stream, '_session_running', return_value=False):
        frames = list(live_stream.iter_session_events())

    assert len(frames) == 1 and 'not_running' in frames[0]

    stream = dev_app.test_client().get('/__dev/monitor/metrics').get_json()['stream']
    assert stream['clients_total'] == 1
    assert stream['clients_active'] == 0
    assert stream['frames'] == 1
    assert stream['bytes_pushed'] == len(frames[0].encode('utf-8'))


def test_live_stream_wrapper_releases_a_client_that_goes_away(dev_app):
    """A tab that closes closes the generator; it never returns from it.

    Without the ``finally`` in the wrapper, clients_active would ratchet up one
    per abandoned stream and never come down.
    """
    import live_stream

    client = dev_app.test_client()
    with patch.object(live_stream, '_session_running', return_value=False):
        generator = live_stream.iter_session_events()
        next(generator)
        assert client.get('/__dev/monitor/metrics').get_json()['stream']['clients_active'] == 1
        generator.close()

    assert client.get('/__dev/monitor/metrics').get_json()['stream']['clients_active'] == 0


def test_byte_tail_wrapper_reports_offsets(dev_app, tmp_path):
    import live_stream

    csv_path = tmp_path / 'run.csv'
    csv_path.write_text('Timestamp,Value:1\n1,0.5\n', encoding='utf-8')
    tail = live_stream._ByteTail(str(csv_path))
    tail.read_lines()

    stream = dev_app.test_client().get('/__dev/monitor/metrics').get_json()['stream']
    assert stream['last_csv_offset'] == csv_path.stat().st_size
    assert stream['last_csv_path'] == str(csv_path)
    assert stream['last_log_offset'] is None


# --- tracemalloc coexistence with --mem-monitor ------------------------------

def test_tracemalloc_owner_is_recorded_and_only_ours_is_stopped():
    import tracemalloc

    reg = Registry()
    was_tracing = tracemalloc.is_tracing()
    if was_tracing:
        tracemalloc.stop()
    try:
        assert reg.start_tracemalloc() == 'devtools'
        assert tracemalloc.is_tracing() is True
        assert reg.stop_tracemalloc() is True
        assert tracemalloc.is_tracing() is False

        # Something else (the --mem-monitor thread) got there first: adopt the
        # reading, never stop the tracing.
        tracemalloc.start()
        other = Registry()
        assert other.start_tracemalloc() == 'external'
        assert other.stop_tracemalloc() is False
        assert tracemalloc.is_tracing() is True
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        if was_tracing:
            tracemalloc.start()


def test_registry_latency_ring_is_bounded():
    from devtools.metrics import SAMPLE_WINDOW

    reg = Registry()
    for i in range(SAMPLE_WINDOW * 3):
        reg.http_begin()
        reg.http_end('e', '/e', float(i), 200)
    row = reg.snapshot()['http']['routes'][0]
    assert row['count'] == SAMPLE_WINDOW * 3
    assert len(reg._http['e'].samples) == SAMPLE_WINDOW


def test_public_api_surface():
    for name in ('attach_monitor', 'detach_monitor', 'is_enabled', 'is_frozen',
                 'monitor_url', 'MONITOR_PREFIX'):
        assert hasattr(devtools, name), name
    assert devtools.MONITOR_PREFIX == '/__dev/monitor'
    assert devtools.monitor_url('easyokapi.com', 5099) == \
        'http://easyokapi.com:5099/__dev/monitor'


# --- the port is never touched, and the readout never waits on its lock -------

_FORBIDDEN_CALLS = frozenset({
    # Opening or enumerating a port.
    'Serial', 'comports', 'connect_to_device', '_probe',
    # Driving the idle-time control link.
    'command', 'send_command_and_wait_ack', 'set_menu', 'set_conc', 'set_timing',
    # Anything that would move bytes over one.
    'write', 'flush', 'read', 'readline', 'read_lines', 'drain',
    'reset_input_buffer', 'reset_output_buffer',
})


def _devtools_python_files():
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    package = os.path.join(here, 'devtools')
    return [os.path.join(package, name) for name in sorted(os.listdir(package))
            if name.endswith('.py')]


def test_devtools_never_calls_anything_that_could_open_the_port():
    """The §2.28/§2.35 guarantee, enforced against the AST rather than a grep.

    The port has exactly one owner. A grep cannot tell ``_patch(send_command,
    'connect_to_device', …)`` — a string naming the function to wrap — from a
    call to it, so this walks every call node in the package instead and fails
    on the name of anything that opens, enumerates, reads or writes a port.
    """
    import ast

    offenders = []
    for path in _devtools_python_files():
        with open(path, encoding='utf-8') as handle:
            tree = ast.parse(handle.read(), path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', None)
            if name in _FORBIDDEN_CALLS:
                offenders.append(f'{path}:{node.lineno} calls {name}()')
    assert offenders == [], offenders


def test_devtools_never_imports_pyserial():
    """Not even the module: there is no metric here that needs it."""
    import ast

    for path in _devtools_python_files():
        with open(path, encoding='utf-8') as handle:
            tree = ast.parse(handle.read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or '']
            else:
                continue
            for name in names:
                assert not name.split('.')[0] == 'serial', f'{path}:{node.lineno} imports {name}'


class _LinkThatMustNotBeAsked:
    """A stand-in for ``device_link.link`` whose lock-taking property explodes.

    ``DeviceLink.connected`` acquires the link's own RLock, and
    ``DeviceLink.command()`` holds that lock across a whole exchange — including
    ``connect_to_device()``, which can spend ``PROBE_TIMEOUT`` on each candidate
    port. A snapshot that went through the property would block the polling
    request behind device I/O for seconds.
    """

    def __init__(self, serial_port=None):
        self._serial = serial_port

    @property
    def connected(self):                      # pragma: no cover - must not run
        raise AssertionError('the monitor took the device link lock')


class _OpenPort:
    is_open = True


def test_link_status_is_read_without_taking_the_device_link_lock():
    import device_link
    from devtools.metrics import _link_connected

    original = device_link.link
    try:
        device_link.link = _LinkThatMustNotBeAsked()
        assert _link_connected() is False
        device_link.link = _LinkThatMustNotBeAsked(_OpenPort())
        assert _link_connected() is True
    finally:
        device_link.link = original


def test_snapshot_is_prompt_while_the_device_link_is_busy(dev_app):
    """End to end: a held link lock must not slow the metrics request down."""
    import threading
    import time

    import device_link

    original = device_link.link
    holding = threading.Event()
    release = threading.Event()

    def hold():
        with original._lock:
            holding.set()
            release.wait(2.0)

    worker = threading.Thread(target=hold, daemon=True)
    worker.start()
    try:
        assert holding.wait(2.0)
        started = time.monotonic()
        payload = dev_app.test_client().get('/__dev/monitor/metrics').get_json()
        elapsed = time.monotonic() - started
    finally:
        release.set()
        worker.join(3.0)

    assert payload['device']['link_connected'] is False
    assert elapsed < 0.5, f'metrics waited {elapsed:.2f}s on the device link lock'


# --- the route table cannot be grown, or poisoned, from outside ---------------

def test_unmatched_requests_collapse_to_one_row_and_keep_no_path(dev_app):
    """404 spam must not grow the table, and must not plant markup in it.

    The rule string is rendered into the page. A page the developer is visiting
    can issue a cross-origin GET to any path on the app (the origin guard covers
    unsafe methods only), so a 404's path is caller-chosen text — it is never
    stored, and every unrouted request shares one row.
    """
    client = dev_app.test_client()
    for path in ('/nope-1', '/nope-2', '/nope-3',
                 '/<img src=x onerror=alert(1)>', '/%3Cscript%3E'):
        assert client.get(path).status_code == 404

    payload = client.get('/__dev/monitor/metrics').get_json()
    rows = payload['http']['routes']
    assert len(rows) == 1
    assert rows[0]['endpoint'] == '(unmatched)'
    assert rows[0]['count'] == 5
    assert rows[0]['rule'] == ''

    import json
    body = json.dumps(payload)
    assert 'nope-1' not in body and 'onerror' not in body and 'img src' not in body


def test_matched_routes_still_report_their_rule(dev_app):
    """The bound above must not cost the thing the table is for."""
    @dev_app.route('/widgets/<int:widget_id>')
    def _widget(widget_id):
        return str(widget_id)

    client = dev_app.test_client()
    client.get('/widgets/7')
    rows = client.get('/__dev/monitor/metrics').get_json()['http']['routes']
    assert rows[0]['rule'] == '/widgets/<int:widget_id>'


# --- the dev routes are not exempt from the request-origin guard -------------

def test_control_post_is_refused_cross_origin():
    """§2.24: the POST is an unsafe method and rides the app's own guard."""
    from security import init_request_guard

    app = Flask(__name__)
    app.config['TESTING'] = True
    init_request_guard(app)                   # exactly as main.py does, first
    assert monitor.attach_monitor(app) is True
    try:
        client = app.test_client()
        blocked = client.post('/__dev/monitor/control', json={'action': 'reset'},
                              headers={'Origin': 'http://evil.example'})
        assert blocked.status_code == 403
        assert blocked.get_json()['code'] == 'forbidden_origin'

        same_origin = client.post('/__dev/monitor/control', json={'action': 'reset'},
                                  headers={'Origin': 'http://localhost'})
        assert same_origin.status_code == 200
    finally:
        monitor.detach_monitor()


# --- tracemalloc: --mem-monitor's tracing is never ours to stop ---------------

def test_mem_monitor_flag_keeps_ownership_external():
    """``--monitor --mem-monitor`` together.

    MemGuard starts tracing from its own thread; attach_monitor runs on the main
    thread a moment later and normally wins the race. Without this the page's
    *trace off* button would stop the tracing MemGuard is reading, and its
    growth report would sit at 0 MB for the rest of the run.
    """
    import argparse
    import tracemalloc

    import state

    was_tracing = tracemalloc.is_tracing()
    if was_tracing:
        tracemalloc.stop()
    original_args = state.args          # None outside main.py's __main__ block
    try:
        state.args = argparse.Namespace(mem_monitor=True)
        reg = Registry()
        assert reg.start_tracemalloc() == 'external'
        assert tracemalloc.is_tracing() is True
        assert reg.stop_tracemalloc() is False
        assert tracemalloc.is_tracing() is True
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        state.args = original_args
        if was_tracing:
            tracemalloc.start()


# --- the exemptions are real, not just claimed -------------------------------

def test_no_i18n_and_no_user_settings_leaked_into_the_package():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    package = os.path.join(root, 'devtools')
    for folder, _dirs, files in os.walk(package):
        for name in files:
            if not name.endswith(('.py', '.html', '.js', '.css')):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding='utf-8') as handle:
                body = handle.read()
            # The attribute, not the word: the template and this package's
            # docstrings name `data-i18n` precisely to record the exemption.
            assert 'data-i18n=' not in body, path
            assert 'ui_translations/' not in body, path
            assert 'import user_settings' not in body, path
            assert 'load_catalog' not in body, path

    # …and nothing went the other way either.
    for name in sorted(os.listdir(os.path.join(root, 'ui_translations'))):
        with open(os.path.join(root, 'ui_translations', name), encoding='utf-8') as handle:
            assert '__dev' not in handle.read(), name
    with open(os.path.join(root, 'src', 'user_settings.py'), encoding='utf-8') as handle:
        source = handle.read()
    # No DEFAULTS key, no validation, no mention: the poll interval and the
    # tracing switch are controls on the page, not machine preferences.
    assert 'devtools' not in source
    assert '__dev' not in source


def test_monitor_css_uses_tokens_only():
    """Rule.md §2.33 applies here even though §2.22 does not."""
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'devtools', 'static', 'monitor.css'), encoding='utf-8') as handle:
        css = handle.read()
    # Strip comments first — the file explains the rule in one.
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b', css)
    assert 'gradient' not in css
    assert not re.search(r'\b(rgba?|hsla?)\(', css)


def test_nothing_in_the_app_knows_devtools_exists():
    """The dependency arrow points one way: devtools imports src, never back.

    A reference from ``src/`` or a template is what would drag the package into
    a frozen build against ``easyokapi.spec``'s exclude, and what would make a
    user's install — which has no ``devtools/`` at all — fail to start.
    """
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    offenders = []
    for folder in ('src', 'templates', 'static'):
        for where, _dirs, files in os.walk(os.path.join(root, folder)):
            for name in files:
                if not name.endswith(('.py', '.html', '.js', '.css')):
                    continue
                path = os.path.join(where, name)
                with open(path, encoding='utf-8', errors='replace') as handle:
                    if 'devtools' in handle.read():
                        offenders.append(path)
    assert offenders == [], offenders


# --- psutil handles are kept, or CPU% is 0.0 for ever ------------------------

class _FakeProc:
    """The few psutil.Process members the sampler uses."""

    def __init__(self, pid=4242):
        self.pid = pid
        self.cpu_calls = 0

    def oneshot(self):
        from contextlib import nullcontext
        return nullcontext()

    def memory_info(self):
        return type('m', (), {'rss': 111, 'vms': 222})()

    def cpu_percent(self, interval=None):
        # The real one answers 0.0 on a handle's first call and a real delta
        # afterwards. Same shape here, so a per-poll handle shows as 0.0.
        self.cpu_calls += 1
        return 0.0 if self.cpu_calls == 1 else 12.5

    def num_threads(self):
        return 7

    def num_fds(self):
        return 21


class _FakePsutil:
    """Stands in for the module so this runs with or without psutil installed."""

    def __init__(self):
        self.constructions = 0

    def Process(self, pid=None):
        self.constructions += 1
        return _FakeProc(pid if pid is not None else 4242)


def test_psutil_handle_is_built_once_not_once_per_poll():
    """``cpu_percent(interval=None)`` is a delta against the handle's last call.

    A ``psutil.Process()`` built inside each poll has no previous call, so it
    answers a meaningless 0.0 % every time — the CPU row would sit at zero for
    the life of the process and look like good news.
    """
    fake = _FakePsutil()
    reg = Registry()
    with patch.object(_metrics, 'psutil', fake):
        first = reg._process_resources()
        second = reg._process_resources()
        third = reg._process_resources()

    assert fake.constructions == 1, 'a fresh psutil.Process per poll'
    assert first['cpu_percent'] == 0.0          # the handle's first call
    assert second['cpu_percent'] == 12.5        # a real delta from here on
    assert third['cpu_percent'] == 12.5
    assert second['source'] == 'psutil' and second['rss_bytes'] == 111


def test_psutil_child_handle_follows_a_new_logger_pid():
    """One slot, replaced when the session's subprocess is — never accumulated."""
    fake = _FakePsutil()
    reg = Registry()
    with patch.object(_metrics, 'psutil', fake):
        first = reg._psutil_child(101)
        assert reg._psutil_child(101) is first
        assert fake.constructions == 1
        second = reg._psutil_child(202)
        assert second is not first
    assert reg._child_handle[0] == 202


def test_source_reports_the_sampler_that_actually_answered(dev_client):
    """psutil present but failing must not be labelled 'psutil'.

    The label is what tells you whether ``rss_bytes: null`` means "this build
    cannot see RSS" or "something went wrong", so it is decided by the branch
    that produced the numbers, not by whether the import succeeded.
    """
    try:
        # _proc_handle is cleared alongside the patch: an earlier test may have
        # cached a real psutil handle on the singleton, and the point here is
        # that the *fake* produces the numbers.
        with patch.object(_metrics, 'psutil', _FakePsutil()), \
                patch.object(registry, '_proc_handle', None):
            process = dev_client.get('/__dev/monitor/metrics').get_json()['process']
    finally:
        # The handle cache is on the module-level registry: drop the fake so the
        # rest of the suite samples this process, not _FakeProc.
        registry._proc_handle = None
    assert process['source'] == 'psutil'
    assert process['rss_bytes'] == 111

    # psutil importable, sampling broken: patched onto the cached handle rather
    # than the module, because the whole point of that cache is that Process()
    # is not called per poll.
    with patch.object(_metrics, 'psutil', _FakePsutil()), \
            patch.object(registry, '_proc_handle', object()):
        process = dev_client.get('/__dev/monitor/metrics').get_json()['process']
    assert process['source'] == 'stdlib'
    assert process['rss_bytes'] is None
    assert process['rss_peak_bytes'] is None or process['rss_peak_bytes'] > 0


# --- the default poll must be cheap ------------------------------------------

def test_allocation_tracing_is_off_until_the_page_asks(dev_client):
    """Measured: /metrics is 14.5 ms with tracing off and 246 ms with it on.

    ``take_snapshot()`` copies every traced allocation, once per poll. On by
    default, a 1 Hz page would spend a quarter of a core inside a request
    handler for as long as a tab stayed open — the monitor becoming the thing
    worth monitoring.
    """
    assert dev_client.get('/__dev/monitor/metrics') \
        .get_json()['process']['tracemalloc']['enabled'] is False

    dev_client.post('/__dev/monitor/control', json={'action': 'trace_on'})
    try:
        traced = dev_client.get('/__dev/monitor/metrics').get_json()['process']['tracemalloc']
        assert traced['enabled'] is True
        assert traced['owner'] == 'devtools'
        assert traced['current_bytes'] > 0
    finally:
        dev_client.post('/__dev/monitor/control', json={'action': 'trace_off'})

    assert dev_client.get('/__dev/monitor/metrics') \
        .get_json()['process']['tracemalloc']['enabled'] is False


# --- memory history / escalation chart ---------------------------------------

def _fill_history(reg, values, step=5.0, traced=None, start=None):
    """Seed a registry's history with a known RSS series (bytes).

    ``start`` offsets the timestamps: the verdict ignores samples inside the
    first MEMORY_WARMUP_SEC, so a series about steady-state behaviour has to be
    seeded past it.
    """
    if start is None:
        start = _metrics.MEMORY_WARMUP_SEC
    reg._mem_history.clear()
    for i, value in enumerate(values):
        reg._mem_history.append((start + i * step, value, traced))


def test_memory_route_404s_when_the_monitor_is_off(client):
    assert monitor.is_enabled() is False
    assert client.get('/__dev/monitor/memory').status_code == 404


def test_memory_route_shape(dev_client):
    body = dev_client.get('/__dev/monitor/memory').get_json()
    assert body['status'] == 'success'
    for key in ('points', 'samples', 'verdict', 'verdict_reason', 'thresholds',
                'sample_interval_sec', 'retention_sec', 'sampler_running',
                'current_bytes', 'min_bytes', 'max_bytes', 'rss_available',
                'slope_mb_per_hour', 'floor_slope_mb_per_hour',
                'recent_floor_slope_mb_per_hour', 'floor_rise_mb',
                'verdict_samples', 'verdict_span_sec', 'warmup_sec'):
        assert key in body, key


def test_sampler_thread_runs_while_attached_and_stops_on_detach(dev_app):
    assert monitor.sampler_running() is True
    monitor.detach_monitor()
    assert monitor.sampler_running() is False
    # Re-attach so the fixture's own detach is a no-op rather than an error.
    monitor.attach_monitor(dev_app)


def test_attach_takes_a_sample_immediately(dev_client):
    """The chart must not be empty for a whole interval after attach."""
    body = dev_client.get('/__dev/monitor/memory').get_json()
    # psutil present -> a real sample; absent -> an honest empty series.
    assert body['samples'] >= 1 or body['rss_available'] is False


MB = 1024 * 1024


@pytest.mark.parametrize('name, values, expected', [
    ('flat',       [80 * MB] * 60, 'steady'),
    # A busy app: peaks swing, floor does not. The raw slope reads +6 MB/h here,
    # which is exactly why the verdict does not read the raw slope.
    ('sawtooth',   [80 * MB + (10 * MB if i % 2 else 0) for i in range(60)], 'steady'),
    # Triangle waves whose period does not divide the window alias against the
    # floor slices and manufacture a trend; the floor-rise gate ignores them.
    ('triangle10', [80 * MB + abs((i % 10) - 5) * 3 * MB for i in range(60)], 'steady'),
    ('triangle7',  [80 * MB + abs((i % 7) - 3) * 4 * MB for i in range(60)], 'steady'),
    ('one spike',  [80 * MB] * 29 + [300 * MB] + [80 * MB] * 30, 'steady'),
    ('falling',    [120 * MB - i * MB for i in range(60)], 'steady'),
    ('fast leak',  [80 * MB + i * MB for i in range(60)], 'climbing'),
    ('slow leak',  [80 * MB + int(i * 0.05 * MB) for i in range(60)], 'climbing'),
    # A finished step raises the floor for good but has stopped: 'rising', not
    # 'climbing'. It decays to 'steady' as the window rolls past it.
    ('step',       [80 * MB] * 30 + [100 * MB] * 30, 'rising'),
    ('step+noise', [80 * MB + (i % 3) * MB for i in range(30)] +
                   [100 * MB + (i % 3) * MB for i in range(30)], 'rising'),
])
def test_verdict_classifies_known_shapes(name, values, expected):
    reg = Registry()
    # _fill_history seeds past the warm-up window by default: these shapes are
    # statements about steady state, and the first two minutes are excluded by
    # design.
    _fill_history(reg, values)
    assert reg.memory_history()['verdict'] == expected, name


def test_warmup_is_charted_but_excluded_from_the_verdict():
    """A fresh interpreter fills caches; that ramp is not a leak.

    Caught on a live run: RSS climbed 66.9 -> 73.3 MB over the first 190 s of a
    freshly started app and the verdict read 'climbing'. Memory really was being
    kept — templates, i18n catalogs, file-metadata caches — so no measurement of
    the ramp can clear it. Excluding the warm-up window is the only honest fix.
    """
    reg = Registry()
    warmup = [66 * MB + int(i * 0.25 * MB) for i in range(26)]     # 0-125 s
    settled = [73 * MB + (i % 3) * MB // 4 for i in range(40)]     # then flat
    _fill_history(reg, warmup + settled, start=0.0)
    stats = reg.memory_history()
    assert stats['verdict'] == 'steady'
    # Charted in full; judged from MEMORY_WARMUP_SEC onward. That boundary is
    # inclusive and falls inside the ramp array here, so the 40 settled samples
    # plus the two ramp samples at t=120 and t=125 are what gets judged.
    assert stats['samples'] == 66
    assert stats['verdict_samples'] == 42
    assert stats['warmup_sec'] == _metrics.MEMORY_WARMUP_SEC
    assert len(stats['points']) == 66


def test_a_leak_that_outlives_the_warmup_is_still_caught():
    reg = Registry()
    warmup = [66 * MB + int(i * 0.25 * MB) for i in range(26)]
    _fill_history(reg, warmup + [73 * MB + i * MB for i in range(40)], start=0.0)
    assert reg.memory_history()['verdict'] == 'climbing'


def test_no_verdict_during_the_warmup_window():
    reg = Registry()
    _fill_history(reg, [66 * MB + int(i * 0.25 * MB) for i in range(20)], start=0.0)
    stats = reg.memory_history()
    assert stats['verdict'] == 'warming_up'
    assert 'warming up' in stats['verdict_reason'].lower()


def test_the_reason_quotes_the_window_the_verdict_used():
    """Not the charted span — they differ whenever warm-up was trimmed."""
    reg = Registry()
    warmup = [66 * MB + int(i * 0.25 * MB) for i in range(26)]
    settled = [73 * MB] * 40
    _fill_history(reg, warmup + settled, start=0.0)
    stats = reg.memory_history()
    assert stats['verdict_span_sec'] < stats['span_sec']


def test_the_raw_slope_is_reported_but_is_not_the_gate():
    """A sawtooth's raw slope is non-zero; its floor is flat and it reads steady."""
    reg = Registry()
    _fill_history(reg, [80 * MB + (10 * MB if i % 2 else 0) for i in range(60)])
    stats = reg.memory_history()
    assert stats['slope_mb_per_hour'] > _metrics.MEMORY_RISE_WARN_MB_H
    assert stats['floor_rise_mb'] == 0.0
    assert stats['verdict'] == 'steady'


def test_a_leak_slower_than_the_gate_reads_steady():
    """The documented sensitivity floor, asserted rather than left implicit."""
    reg = Registry()
    creep = _metrics.MEMORY_FLOOR_RISE_MB * 0.4 * MB / 60.0
    _fill_history(reg, [int(80 * MB + i * creep) for i in range(60)])
    stats = reg.memory_history()
    assert stats['floor_rise_mb'] < _metrics.MEMORY_FLOOR_RISE_MB
    assert stats['verdict'] == 'steady'


def test_a_flat_series_reads_steady():
    reg = Registry()
    _fill_history(reg, [80 * 1024 * 1024] * 60)
    stats = reg.memory_history()
    assert stats['verdict'] == 'steady'
    assert abs(stats['slope_mb_per_hour']) < 0.01
    assert stats['floor_rise_mb'] == 0.0


def test_a_rising_floor_is_reported_as_climbing():
    reg = Registry()
    base = 80 * 1024 * 1024
    # +1 MB per sample over 60 samples at 5 s = 720 MB/h, floor rising with it.
    _fill_history(reg, [base + i * 1024 * 1024 for i in range(60)])
    stats = reg.memory_history()
    assert stats['verdict'] == 'climbing'
    assert stats['floor_slope_mb_per_hour'] > _metrics.MEMORY_RISE_BAD_MB_H
    assert stats['recent_floor_slope_mb_per_hour'] > _metrics.MEMORY_RISE_WARN_MB_H
    assert stats['floor_rise_mb'] > _metrics.MEMORY_FLOOR_RISE_MB


def test_a_finished_step_is_not_still_going():
    reg = Registry()
    _fill_history(reg, [80 * MB] * 30 + [100 * MB] * 30)
    stats = reg.memory_history()
    assert stats['floor_rise_mb'] == 20.0
    assert stats['recent_floor_slope_mb_per_hour'] == 0.0
    assert stats['verdict'] == 'rising'


def test_no_verdict_before_enough_samples():
    reg = Registry()
    _fill_history(reg, [80 * 1024 * 1024] * 5)
    stats = reg.memory_history()
    assert stats['verdict'] == 'warming_up'
    assert stats['slope_mb_per_hour'] is None


def test_history_is_bounded():
    reg = Registry()
    for i in range(_metrics.MEMORY_HISTORY_MAX + 500):
        reg._mem_history.append((float(i), 1024, None))
    assert len(reg._mem_history) == _metrics.MEMORY_HISTORY_MAX


def test_series_is_bucketed_down_to_the_requested_points():
    reg = Registry()
    _fill_history(reg, [80 * 1024 * 1024 + i for i in range(2000)])
    stats = reg.memory_history(max_points=100)
    assert 0 < len(stats['points']) <= 100
    # Each bucket carries [t, avg, min, max, traced]; min <= avg <= max.
    for _t, avg, low, high, _traced in stats['points']:
        assert low <= avg <= high


def test_bucketing_keeps_the_extremes_a_stride_would_drop():
    """A spike between two strided samples must still reach the band."""
    reg = Registry()
    series = [80 * 1024 * 1024] * 200
    series[97] = 300 * 1024 * 1024               # one tall spike
    _fill_history(reg, series)
    stats = reg.memory_history(max_points=10)
    assert max(point[3] for point in stats['points']) == 300 * 1024 * 1024


def test_window_narrows_the_series(dev_client):
    reg = Registry()
    _fill_history(reg, [80 * 1024 * 1024] * 120, step=5.0)   # 600 s of history
    everything = reg.memory_history()
    recent = reg.memory_history(window_sec=100)
    assert recent['samples'] < everything['samples']


def test_a_peak_only_platform_never_charts_a_fake_climb():
    """getrusage gives a high-water mark; charting it would climb for ever."""
    reg = Registry()
    with patch.object(_metrics, 'psutil', None):
        assert reg._rss_bytes_only() is None
    stats = reg.memory_history()
    assert stats['rss_available'] is False
    assert stats['points'] == []
    assert stats['verdict'] == 'warming_up'
    assert 'psutil' in stats['verdict_reason']


def test_sampler_never_touches_cpu_percent_on_the_shared_handle():
    """cpu_percent() is a delta against the handle's previous call.

    A second caller on a different cadence would silently halve the figure the
    page shows, so the sampler must read memory_info() and nothing else.
    """
    reg = Registry()
    handle = type('H', (), {
        'memory_info': lambda self: type('M', (), {'rss': 123456})(),
        'cpu_percent': lambda self, interval=None: pytest.fail(
            'sampler called cpu_percent on the shared handle'),
    })()
    with patch.object(reg, '_psutil_self', return_value=handle), \
            patch.object(_metrics, 'psutil', object()):
        assert reg._rss_bytes_only() == 123456


def test_counter_reset_keeps_the_memory_history(dev_client):
    """Reset answers 'since when'; the history answers 'has it been growing'."""
    _fill_history(registry, [80 * 1024 * 1024] * 40)
    before = registry.memory_history()['samples']
    dev_client.post('/__dev/monitor/control', json={'action': 'reset'})
    assert registry.memory_history()['samples'] == before
    registry._mem_history.clear()


def test_memory_clear_is_its_own_action(dev_client):
    _fill_history(registry, [80 * 1024 * 1024] * 40)
    assert registry.memory_history()['samples'] == 40
    response = dev_client.post('/__dev/monitor/control', json={'action': 'memory_clear'})
    assert response.status_code == 200
    assert registry.memory_history()['samples'] == 0


def test_memory_route_clamps_a_silly_points_request(dev_client):
    body = dev_client.get('/__dev/monitor/memory?points=999999').get_json()
    assert len(body['points']) <= _metrics.MEMORY_MAX_POINTS
    assert dev_client.get('/__dev/monitor/memory?points=nonsense').status_code == 200
    assert dev_client.get('/__dev/monitor/memory?window=nonsense').status_code == 200


def test_page_has_the_chart_and_its_controls(dev_client):
    html = dev_client.get('/__dev/monitor/').get_data(as_text=True)
    for marker in ('m-mem-chart', 'm-mem-verdict', 'm-mem-window', 'm-mem-clear',
                   'm-mem-slope', 'm-mem-floorslope', 'm-mem-floor'):
        assert marker in html, marker
