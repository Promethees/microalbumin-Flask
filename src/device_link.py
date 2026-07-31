"""Idle-time control link to the colorimeter over the CDC serial port.

The app's data path never touches the port: `log_cdc_data.py` runs as a
subprocess and owns it for the whole of a reading session, which is why
"Measure now" and Pause/Resume are file triggers that logger forwards
(Rule.md 2.29). **This module is the other half of that rule, not an exception
to it** — it only ever opens the port when *no* session is running, so there is
still exactly one owner at any moment.

That is also why the virtual controller is an idle-time tool. During a run the
device is already answering the logger, and the controls that make sense mid-run
(pause, stop, measure) exist as routes of their own; a blank or a gain change
underneath a recording would silently invalidate it.

Two things guarantee the port is free when the logger wants it:

  * ``close()`` is called by ``/run_script`` before the logger is spawned, and
  * a reaper thread drops the connection after ``IDLE_TIMEOUT`` with no command,
    so an external tool (a firmware update, a serial monitor) can claim the port
    on a machine where the app is merely sitting open.

The connection is held between commands rather than reopened per press: opening
costs a settle delay plus the PING probe that picks the data endpoint out of the
two identical CDC ports (§2.28) — around half a second, which is the difference
between a button pad and a form submission.
"""

import threading
import time

import send_command

# Drop the port after this long with no command. Long enough that a session of
# poking at the controller never reconnects mid-use, short enough that a user who
# wanders off does not keep the port from a firmware update.
IDLE_TIMEOUT = 30.0

# How often the reaper looks. Coarse on purpose — it exists to release a resource
# eventually, not promptly.
REAP_INTERVAL = 5.0

# Budget for one command's reply. The firmware answers within a main-loop period
# (~0.174 s, §2.28); the slack covers a device busy repainting a screen it had to
# reallocate, which is the slowest thing a button press can trigger.
REPLY_TIMEOUT = 3.0

# Fields of a STATE line that are integers, lists of integers, or lists of text.
# Kept in lockstep with the firmware's SerialManager._state_line().
_STATE_INTS = ("blanked", "needsblank", "talking", "paused", "maxchan", "menupos", "sel")
_STATE_INT_LISTS = ("chans",)
_STATE_TEXT_LISTS = ("caps", "gains", "itimes", "vals")


class DeviceLinkError(Exception):
    """The device could not be reached, or refused the command."""


def parse_state(line):
    """Parse a ``STATE k=v;k=v`` reply into a dict.

    Values the firmware sends as numbers or comma lists are converted here so the
    route can hand the browser a typed object; everything else stays text. An
    empty field becomes None (ints/lists) or "" (text), because the firmware
    writes "" for "not applicable" — no selected sensor, no concentration set.
    """
    body = line[len("STATE"):].strip() if line.startswith("STATE") else line
    state = {}
    for pair in body.split(";"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        key = key.strip()
        value = value.strip()
        if key in _STATE_INTS:
            try:
                state[key] = int(value)
            except ValueError:
                state[key] = None
        elif key in _STATE_INT_LISTS:
            try:
                state[key] = [int(v) for v in value.split(",") if v]
            except ValueError:
                state[key] = []
        elif key in _STATE_TEXT_LISTS:
            state[key] = [v for v in value.split(",") if v]
        else:
            state[key] = value
    return state


class DeviceLink:
    """Serialised access to the device's command channel while it is idle."""

    def __init__(self):
        # Re-entrant so a helper that already holds the lock can call another.
        self._lock = threading.RLock()
        self._serial = None
        self._reader = None
        self._last_used = 0.0
        self._reaper = None

    # ── connection ──────────────────────────────────────────────────────
    def _start_reaper(self):
        if self._reaper is not None and self._reaper.is_alive():
            return

        def reap():
            while True:
                time.sleep(REAP_INTERVAL)
                with self._lock:
                    if self._serial is None:
                        return
                    if time.monotonic() - self._last_used >= IDLE_TIMEOUT:
                        self._close_locked()
                        return

        self._reaper = threading.Thread(target=reap, daemon=True)
        self._reaper.start()

    def _open_locked(self):
        if self._serial is not None and self._serial.is_open:
            return
        self._serial = None
        self._reader = None
        try:
            # Same probe the logger uses: the console and data CDC endpoints are
            # byte-identical in USB metadata, so the port that answers PING is the
            # only way to tell them apart (§2.28).
            serial_port = send_command.connect_to_device()
        except Exception as error:
            raise DeviceLinkError(str(error))
        self._serial = serial_port
        self._reader = send_command.LineReader(serial_port)
        self._start_reaper()

    def _close_locked(self):
        port, self._serial, self._reader = self._serial, None, None
        if port is None:
            return
        try:
            if port.is_open:
                port.close()
        except Exception:
            pass

    def close(self):
        """Release the port. Called before the logger subprocess is spawned."""
        with self._lock:
            self._close_locked()

    @property
    def connected(self):
        with self._lock:
            return self._serial is not None and self._serial.is_open

    # ── command exchange ────────────────────────────────────────────────
    def _exchange_locked(self, command, matches):
        """Send `command` and return the first reply `matches` accepts.

        Lines that are not a reply to this command are dropped: the device is
        idle so the channel should be quiet, but a banner or the tail of an
        earlier session must not be mistaken for an answer — the same reasoning
        as send_command.send_command_and_wait_ack's non-ack skip.
        """
        self._serial.reset_input_buffer()
        self._reader.buffer = b""
        self._serial.write(f"{command}\n".encode("utf-8"))
        self._serial.flush()
        deadline = time.time() + REPLY_TIMEOUT
        while time.time() < deadline:
            for line in self._reader.read_lines():
                if line and matches(line):
                    return line
        raise DeviceLinkError(f"No reply to {command} from the device")

    def command(self, command, matches):
        """Run one command, reconnecting once if the port has gone away.

        A device that was unplugged and plugged back in leaves a handle that
        writes without error and never answers, so a single retry on a fresh
        connection is the difference between "reconnect the device" and a
        controller that stays dead until the app restarts.
        """
        with self._lock:
            for attempt in (0, 1):
                try:
                    self._open_locked()
                    reply = self._exchange_locked(command, matches)
                except DeviceLinkError:
                    self._close_locked()
                    if attempt:
                        raise
                    continue
                except Exception as error:
                    self._close_locked()
                    if attempt:
                        raise DeviceLinkError(str(error))
                    continue
                self._last_used = time.monotonic()
                return reply

    # ── operations ──────────────────────────────────────────────────────
    def state(self):
        """Snapshot of the device (mode, measurement, channels, values, …)."""
        reply = self.command("STATE?", lambda line: line.startswith("STATE ") or line == "ERR_STATE")
        if reply == "ERR_STATE":
            raise DeviceLinkError("The device could not report its state")
        return parse_state(reply)

    def press(self, button):
        """Press one device button by name (BTN:)."""
        reply = self.command(f"BTN:{button}", lambda line: line in ("ACK_BTN", "ERR_BTN", "ERR_UNKNOWN"))
        if reply == "ERR_UNKNOWN":
            raise DeviceLinkError("This device's firmware has no virtual controller")
        if reply != "ACK_BTN":
            raise DeviceLinkError(f"The device refused the {button} button")
        return True

    def set_channels(self, channels):
        """Set the active multiplexer channels (CHANNELS:)."""
        spec = ",".join(str(int(channel)) for channel in channels)
        reply = self.command(
            f"CHANNELS:{spec}",
            lambda line: line == "ACK_CHANNELS" or line.startswith("ERR_CHANNELS") or line == "ERR_UNKNOWN")
        if reply == "ERR_UNKNOWN":
            raise DeviceLinkError("This device's firmware cannot switch channels")
        if reply != "ACK_CHANNELS":
            # The firmware appends the reason ("sensor on mux channel 2 missing?"),
            # which is the only thing that tells the operator what to plug in.
            detail = reply[len("ERR_CHANNELS"):].strip()
            raise DeviceLinkError(detail or "The device refused the channel change")
        return True

    def menu_items(self):
        """The device's menu, in device order (MENU?).

        The list is built on the device from its own calibrations.json, so it
        cannot be derived here — it has to be asked for. An empty item is kept:
        the index *is* the address MENU: takes, so dropping one would silently
        shift every entry after it.
        """
        reply = self.command(
            "MENU?", lambda line: line.startswith("MENUITEMS") or line in ("ERR_MENU", "ERR_UNKNOWN"))
        if reply == "ERR_UNKNOWN":
            raise DeviceLinkError("This device's firmware cannot list its menu")
        if reply == "ERR_MENU":
            raise DeviceLinkError("The device could not report its menu")
        body = reply[len("MENUITEMS"):].strip()
        return [item.strip() for item in body.split(",")] if body else []

    def select_menu(self, index):
        """Open one menu entry by its index in menu_items() (MENU:)."""
        reply = self.command(
            f"MENU:{int(index)}",
            lambda line: line == "ACK_MENU" or line.startswith("ERR_MENU") or line == "ERR_UNKNOWN")
        if reply == "ERR_UNKNOWN":
            raise DeviceLinkError("This device's firmware cannot open menu entries")
        if reply != "ACK_MENU":
            detail = reply[len("ERR_MENU"):].strip()
            raise DeviceLinkError(detail or "The device refused that menu entry")
        return True


# One link per process: the port has one owner, so the object that owns it is a
# singleton rather than something a route constructs.
link = DeviceLink()
