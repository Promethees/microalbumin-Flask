"""Attach-time wrappers around the production modules the monitor observes.

**Why monkeypatching rather than instrumentation.** The alternative is a
counter call inside ``send_command``, ``device_link`` and ``live_stream`` — a
permanent cost on the hot path of a shipped app, and three more places where a
developer-only concern has to be kept in step with a change. Wrapping at attach
time keeps the whole feature inside ``devtools/``: with the flag absent, nothing
here ever runs and the production modules are byte-for-byte what they were.

**What this never does.** It never opens, probes, reads or writes the serial
port (Rule.md §2.28/§2.35 — the port has exactly one owner). Every device number
in the readout is a byte that some *other* caller already moved; the wrappers
only add it up. There is likewise no metric that would require a request to the
device, which is why "device firmware version" and "device uptime" are absent
from the monitor.

``install()`` is idempotent and ``uninstall()`` restores the exact objects that
were there, so an attach/detach cycle inside one process leaves no trace.
"""

import functools
import time

from .metrics import registry

# (module, attribute, original) for everything install() replaced, in the order
# it was replaced. uninstall() walks it backwards.
_patches = []
_installed = False


def _ms(started):
    return (time.monotonic() - started) * 1000.0


def _patch(module, name, factory):
    """Replace ``module.name`` with ``factory(original)`` and remember it."""
    original = getattr(module, name)
    setattr(module, name, factory(original))
    _patches.append((module, name, original))


def install():
    """Wrap the observed call sites. Returns the list of modules instrumented."""
    global _installed
    if _installed:
        return []
    touched = []
    for name, installer in (('send_command', _install_send_command),
                            ('device_link', _install_device_link),
                            ('live_stream', _install_live_stream)):
        try:
            installer()
        except Exception:
            # A module that will not import is a metric the monitor does
            # without — never a reason for the app not to start.
            continue
        touched.append(name)
    _installed = True
    return touched


def uninstall():
    """Put every wrapped attribute back, newest first."""
    global _installed
    while _patches:
        module, name, original = _patches.pop()
        try:
            setattr(module, name, original)
        except Exception:
            pass
    _installed = False


def installed():
    return _installed


# ── src/send_command.py ─────────────────────────────────────────────────────
def _install_send_command():
    """Count framed bytes/lines, PING probes and port opens.

    ``LineReader`` is the single funnel every inbound byte of this process goes
    through (§2.28 forbids a bare ``readline()``), so wrapping its one method is
    the whole of the read accounting. Note this covers the **idle-time control
    link only** — a running session's traffic is read by the logger subprocess,
    which has its own interpreter and never executes this patch.
    """
    import send_command

    def wrap_read_lines(original):
        @functools.wraps(original)
        def read_lines(self):
            before = len(self.buffer)
            lines = original(self)
            # Bytes consumed from the port = what the unframed tail grew by,
            # plus everything the split handed out (payload + one '\n' each).
            # Slightly under the wire count, because the framer strips '\r' and
            # trailing whitespace before we can see it — a floor, not a guess.
            after = len(self.buffer)
            moved = sum(len(line) for line in lines) + len(lines) + after - before
            registry.device_read(max(0, moved), lines)
            return lines
        return read_lines

    def wrap_probe(original):
        @functools.wraps(original)
        def _probe(port):
            # Round-trip of one PING against one candidate port — the thing that
            # tells the CDC data endpoint from the byte-identical console one
            # (§2.28). A failure here is either "not the data port" or "the
            # device did not answer in PROBE_TIMEOUT"; both read as a failed
            # probe, which is what the operator needs to see.
            #
            # The 5 bytes of "PING\n" are deliberately NOT added to bytes_out: a
            # probe that could not even open the port never wrote them, and the
            # wrapper cannot tell the two apart from out here.
            started = time.monotonic()
            result = original(port)
            registry.device_ping(_ms(started), ok=result is not None)
            return result
        return _probe

    def wrap_connect(original):
        @functools.wraps(original)
        def connect_to_device(*args, **kwargs):
            started = time.monotonic()
            try:
                port = original(*args, **kwargs)
            except Exception:
                registry.device_open(_ms(started), error=True)
                raise
            registry.device_open(_ms(started), port=getattr(port, 'port', None))
            return port
        return connect_to_device

    _patch(send_command.LineReader, 'read_lines', wrap_read_lines)
    _patch(send_command, '_probe', wrap_probe)
    _patch(send_command, 'connect_to_device', wrap_connect)


# ── src/device_link.py ──────────────────────────────────────────────────────
def _install_device_link():
    """Time one command round-trip, and follow the port open/close.

    ``_exchange_locked`` is the only place a host command reaches the device, so
    it is both the write accounting and the round-trip clock. A
    ``DeviceLinkError`` out of it is the no-reply timeout — the number worth
    watching when a device stops answering.
    """
    import device_link

    def wrap_exchange(original):
        @functools.wraps(original)
        def _exchange_locked(self, command, matches):
            registry.device_write(len(command.encode('utf-8')) + 1)
            started = time.monotonic()
            try:
                reply = original(self, command, matches)
            except Exception:
                registry.device_command(_ms(started), error=True)
                raise
            registry.device_command(_ms(started), matched=True)
            return reply
        return _exchange_locked

    def wrap_close(original):
        @functools.wraps(original)
        def _close_locked(self):
            had_port = self._serial is not None
            result = original(self)
            if had_port:
                registry.device_close()
            return result
        return _close_locked

    _patch(device_link.DeviceLink, '_exchange_locked', wrap_exchange)
    _patch(device_link.DeviceLink, '_close_locked', wrap_close)


# ── src/live_stream.py ──────────────────────────────────────────────────────
def _install_live_stream():
    """Count SSE clients and pushed bytes, and follow both byte offsets.

    ``iter_session_events`` is a generator, so the client count has to be
    bracketed by a ``finally`` — a tab that goes away closes the generator
    rather than returning from it, which is precisely the case a naive
    increment/decrement pair would leak.
    """
    import live_stream

    def wrap_iter(original):
        @functools.wraps(original)
        def iter_session_events(*args, **kwargs):
            registry.stream_client_open()
            try:
                for frame in original(*args, **kwargs):
                    registry.stream_frame(len(frame.encode('utf-8')))
                    yield frame
            finally:
                registry.stream_client_close()
        return iter_session_events

    def wrap_tail(original):
        @functools.wraps(original)
        def read_lines(self):
            lines, truncated = original(self)
            # The CSV tail is re-pointed at each run's file; the log tail is
            # fixed at state.log_file. The path is what tells them apart.
            kind = 'csv' if (self.path or '').lower().endswith('.csv') else 'log'
            registry.stream_offset(kind, self.path, self.offset)
            return lines, truncated
        return read_lines

    _patch(live_stream, 'iter_session_events', wrap_iter)
    _patch(live_stream._ByteTail, 'read_lines', wrap_tail)
