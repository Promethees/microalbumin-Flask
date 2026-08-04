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

# A command that changes a screen (MENU:, CONC:, TIMING:) is *queued* by the
# firmware and applied from its main loop, because building or repainting a
# screen from inside the serial handler runs three frames deeper than a keypad
# press — deep and tight enough that the font stopped loading uncached glyphs and
# screens came out with letters missing. The ACK therefore arrives before the
# work is done, so the state read straight after would still be the old one.
# One loop period is ~0.174 s; this is that with room for a screen rebuild.
SETTLE_AFTER_QUEUED = 0.4

# Fields of a STATE line that are integers, lists of integers, or lists of text.
# Kept in lockstep with the firmware's SerialManager._state_line().
_STATE_INTS = ("blanked", "needsblank", "talking", "paused", "maxchan", "menupos", "sel",
               # Bumped by the device on every accepted factor change. The panel
               # caches the whole multiplexer-indexed array and rcf below only
               # carries the active channels, so this counter is how a
               # keypad-side calibration — or a Clear that reset a channel the
               # panel is not showing — reaches the host at all.
               "rcfrev")
_STATE_INT_LISTS = ("chans",)
_STATE_TEXT_LISTS = ("caps", "gains", "itimes", "vals")
# rcf: the raw count factor of each ACTIVE channel, in the same order as
# `chans`, `gains` and `itimes` — the display view. The full per-multiplexer-
# channel array, which is what configuration.json stores, comes from
# calibration_factors() instead. Typed here rather than left as text because the
# controller compares them against 1.0 to show which holders are corrected.
_STATE_FLOAT_LISTS = ("rcf",)


class DeviceLinkError(Exception):
    """The device could not be reached, or refused the command."""


def _number_text(value):
    """Format a number the way the device would have produced it.

    The screens print a value verbatim and the keypad only ever makes whole
    numbers, so 12.0 goes out as "12" rather than "12.0".
    """
    number = float(value)
    return str(int(number)) if number == int(number) else repr(number)


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
        elif key in _STATE_FLOAT_LISTS:
            try:
                state[key] = [float(v) for v in value.split(",") if v]
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
        time.sleep(SETTLE_AFTER_QUEUED)
        return True

    def concentration_units(self):
        """The units the device's concentration screen cycles through (CONC?).

        Asked for rather than hardcoded: the list is the firmware's
        CONCENTRATION_UNITS, and a host offering a unit the device does not know
        would have the device refuse every set.
        """
        reply = self.command(
            "CONC?", lambda line: line.startswith("CONCUNITS") or line in ("ERR_CONC", "ERR_UNKNOWN"))
        if reply == "ERR_UNKNOWN":
            raise DeviceLinkError("This device's firmware cannot set the concentration")
        if reply == "ERR_CONC":
            raise DeviceLinkError("The device could not report its concentration units")
        body = reply[len("CONCUNITS"):].strip()
        return [unit.strip() for unit in body.split(",") if unit.strip()]

    def set_concentration(self, value, unit=None):
        """Set the concentration outright (CONC:). ``None`` means Unknown.

        Unknown is a value on that screen, not a missing one — it is what the
        device shows before a concentration is dialled in — so it is spelled out
        rather than skipped.
        """
        text = "none" if value is None else _number_text(value)
        spec = f"{text},{unit}" if unit else text
        reply = self.command(
            f"CONC:{spec}",
            lambda line: line == "ACK_CONC" or line.startswith("ERR_CONC") or line == "ERR_UNKNOWN")
        if reply == "ERR_UNKNOWN":
            raise DeviceLinkError("This device's firmware cannot set the concentration")
        if reply != "ACK_CONC":
            detail = reply[len("ERR_CONC"):].strip()
            raise DeviceLinkError(detail or "The device refused that concentration")
        time.sleep(SETTLE_AFTER_QUEUED)
        return True

    def timing_units(self):
        """The units the device's settings screen cycles (TIMING?)."""
        reply = self.command(
            "TIMING?", lambda line: line.startswith("TIMINGUNITS") or line in ("ERR_TIMING", "ERR_UNKNOWN"))
        if reply == "ERR_UNKNOWN":
            raise DeviceLinkError("This device's firmware cannot set the timing")
        if reply == "ERR_TIMING":
            raise DeviceLinkError("The device could not report its timing units")
        body = reply[len("TIMINGUNITS"):].strip()
        return [unit.strip() for unit in body.split(",") if unit.strip()]

    def set_timing(self, timeout_value, timeout_unit, interval_value, interval_unit):
        """Set the Settings screen's pair (TIMING:).

        ``timeout_value`` of ``None`` means **no timeout** — a real setting, not
        a missing one: the run then goes until the host stops it. The device
        refuses a timeout that does not outlast the interval, and the reason it
        gives is the one worth showing.
        """
        timeout = "none" if timeout_value is None else _number_text(timeout_value)
        spec = ",".join((timeout, timeout_unit or "", _number_text(interval_value), interval_unit or ""))
        reply = self.command(
            f"TIMING:{spec}",
            lambda line: line == "ACK_TIMING" or line.startswith("ERR_TIMING") or line == "ERR_UNKNOWN")
        if reply == "ERR_UNKNOWN":
            raise DeviceLinkError("This device's firmware cannot set the timing")
        if reply != "ACK_TIMING":
            detail = reply[len("ERR_TIMING"):].strip()
            raise DeviceLinkError(detail or "The device refused those timing values")
        time.sleep(SETTLE_AFTER_QUEUED)
        return True


    # ── raw count calibration ───────────────────────────────────────────
    # Equalising what the channels count when every cuvette holder is showing
    # them the same LED. See the firmware's raw_count_calibration.md: the factor
    # is one multiplier per MULTIPLEXER channel, so the array is always
    # `maxchan` long and indexed by channel number, not by position in `chans`.
    #
    # None of this survives a power cycle on the device — CircuitPython cannot
    # write its own filesystem — so keeping a calibration means writing the array
    # into configuration.json on the CIRCUITPY drive.

    def _factors_reply(self, command):
        """Send a command that answers CALFACTORS, and parse the array out."""
        reply = self.command(
            command,
            lambda line: line.startswith("CALFACTORS")
            or line.startswith("ERR_CALIB")
            or line == "ERR_UNKNOWN")
        if reply == "ERR_UNKNOWN":
            raise DeviceLinkError("This device's firmware has no sensor calibration")
        if reply.startswith("ERR_CALIB"):
            # The firmware appends the reason ("channel 2 reading zero: LED
            # off?"), which is the only thing that tells the operator what to
            # fix in the holder.
            detail = reply[len("ERR_CALIB"):].strip()
            raise DeviceLinkError(detail or "The device refused the calibration")
        body = reply[len("CALFACTORS"):].strip()
        try:
            return [float(part) for part in body.split(",") if part]
        except ValueError:
            raise DeviceLinkError("The device sent a calibration it could not be read from")

    def calibration_factors(self):
        """The per-multiplexer-channel raw count factors (CALIB?)."""
        return self._factors_reply("CALIB?")

    def set_calibration_factors(self, factors):
        """Write the factors outright (CALIB:). Pass None to clear them to 1.0.

        Send the whole array, not just the active channels: a short list is
        padded with 1.0 on the device, which would blank the factor of every
        holder not currently in use.
        """
        if factors is None:
            spec = "reset"
        else:
            spec = ",".join(_number_text(factor) for factor in factors)
        reply = self.command(
            f"CALIB:{spec}",
            lambda line: line == "ACK_CALIB" or line.startswith("ERR_CALIB") or line == "ERR_UNKNOWN")
        if reply == "ERR_UNKNOWN":
            raise DeviceLinkError("This device's firmware has no sensor calibration")
        if reply != "ACK_CALIB":
            detail = reply[len("ERR_CALIB"):].strip()
            raise DeviceLinkError(detail or "The device refused those factors")
        time.sleep(SETTLE_AFTER_QUEUED)
        return True

    def run_calibration(self):
        """Have the device measure and apply new factors now (CALIBRATE).

        The operator has to have arranged the preconditions first — the same
        contents in every holder, the same LED across them — because the device
        cannot tell a genuinely dimmer holder from a cuvette someone left in it.
        It refuses factors beyond 0.1..10x for that reason, and the refusal names
        the channel.

        Answers with the factors it derived and applied, so there is no follow-up
        read. This is the one device command that takes seconds of sampling
        before it replies; it stays inside REPLY_TIMEOUT because the firmware
        uses its short sample count on this path.
        """
        return self._factors_reply("CALIBRATE")


# One link per process: the port has one owner, so the object that owns it is a
# singleton rather than something a route constructs.
link = DeviceLink()
