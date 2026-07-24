"""CDC (USB serial) data collector — default transport for host-initiated
measurement sessions with the PyBadge colorimeter.

This is the collector for the app's automated "Run" flow; the device's
Left-button keyboard-typing path is kept only as a manual fallback. Unlike that
fallback, this collector:

  * owns the single CDC serial port for BOTH control and data (one process),
  * sends the start command set ("1", "TIMEOUT:x", "INTERVAL:x") and waits for
    the device ACKs, then reads the data stream on the same connection,
  * reads clean UTF-8 text lines — no keycode decoding, no lossy charset,
  * requires no elevated privileges (plain serial access, no sudo/libusbK),
  * is fully cross-platform (pyserial).

On termination (SIGINT/SIGTERM) it sends "0" so the device leaves talking mode
cleanly, then closes the port (which also drops DTR, a secondary stop signal).

Usage (normally launched by the Flask app, but runnable standalone for testing):

    python log_cdc_data.py --base-dir ./data --base-name colorimeter_data \
        --timeout-sec 1200 --interval-sec 60
"""

import os
import re
import sys
import time
import signal
import datetime
import argparse

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(_SCRIPT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.append(_SRC_DIR)

import state
from get_next_filename import get_next_filename
from send_command import connect_to_device, send_command_and_wait_ack, LineReader


class CDCDataCollector:
    def __init__(self, base_dir, base_name="colorimeter_data", extension=".csv",
                 timeout_sec=None, interval_sec=None, axis="time", manual=False):
        self.base_dir = base_dir
        self.base_name = base_name
        self.extension = extension
        self.timeout_sec = timeout_sec
        self.interval_sec = interval_sec
        # X-axis for this session: "turn" logs a 1,2,3… turn index under a "Turn"
        # header (point-mode files); otherwise the elapsed "Timestamp" in seconds.
        self.axis = "turn" if str(axis).strip().lower() == "turn" else "time"
        # Manual point-mode capture: the device stays idle and we send a MEASURE
        # command (one row per press) whenever Flask drops the trigger file. Only
        # ever combined with the turn axis (a manual reading is a turn). While
        # manual, the device does not auto-stream on the interval and does not
        # time out — the session ends only on the "0" stop we send on shutdown.
        self.manual = bool(manual)
        if self.manual:
            self.axis = "turn"

        self.serial = None
        self.output_file = None
        self.running = True

        self.metadata = {}
        self.num_values = None
        self.session_started = False
        # First-column name from the received header ("Timestamp" or "Turn"),
        # used only for log wording.
        self.x_label = "Timestamp"

        # CDC delivers the device's exact bytes, so these patterns match the
        # clean text emitted by serial_manager._write() — no up-casing /
        # modifier-stripping like the old keyboard path had to undo.
        self.metadata_pattern = r"^#\s*(Measurement|Unit|Concentration|ConcenUnit):\s*(.+?)\s*$"
        # The first column is Timestamp (elapsed seconds) or Turn (a 1,2,3… index);
        # accept either header and either first-field form (int turn or decimal
        # timestamp). A Turn file never carries a Timestamp column.
        self.header_pattern = r"^(?:Timestamp|Turn),Value:\d+(?:,Value:\d+)*$"
        self.data_pattern = r"^\d+(?:\.\d{1,2})?,(?:-?\d+\.\d{1,3}|OVFL)(?:,(?:-?\d+\.\d{1,3}|OVFL))*$"
        self.end_pattern = r"^SESSION TIMEOUT$"
        # Device-side manual stop (Left button) of a host session — distinct from
        # a timeout so the UI can announce it differently (firmware serial_manager).
        self.stop_pattern = r"^SESSION STOPPED$"

        # Writable log dir: project root in dev, per-user app-data when frozen
        # (state.script_dir). Must match where Flask reads logs (state.log_file).
        self.log_dir = os.path.join(state.script_dir, "log")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.log_dir, "script_logs.txt")
        # Manual-capture IPC: Flask cannot touch the serial port (this process
        # owns it), so /measure_point drops this trigger file and the read loop
        # forwards a MEASURE command to the device. Matches hardware_routes.
        self.trigger_path = os.path.join(self.log_dir, "measure_trigger.txt")

    def log(self, message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_file_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")

    # ── line classification ─────────────────────────────────────────────
    def is_metadata(self, line):
        return bool(re.match(self.metadata_pattern, line))

    def is_main_header(self, line):
        if re.match(self.header_pattern, line):
            self.num_values = len(line.split(",")) - 1  # exclude the X column
            self.x_label = line.split(",", 1)[0].strip()  # "Timestamp" or "Turn"
            return True
        return False

    def is_valid_data(self, line):
        if self.num_values is None or not re.match(self.data_pattern, line):
            return False
        return len(line.split(",")) == self.num_values + 1

    def is_end_session(self, line):
        return bool(re.match(self.end_pattern, line))

    def is_stopped(self, line):
        return bool(re.match(self.stop_pattern, line))

    # ── handlers ────────────────────────────────────────────────────────
    def handle_metadata(self, line):
        match = re.match(self.metadata_pattern, line)
        if match:
            key, value = match.groups()
            if value == "UWCM2":
                value = "μW/cm²"  # μW/cm² (kept for older calibration sentinels)
            self.metadata[key] = value
            self.log(f"Received metadata: {key} = {value}")

    def handle_main_header(self, line):
        # A host-initiated CDC session must send all four metadata lines —
        # Measurement, Unit, Concentration, ConcenUnit — before the data header.
        # The firmware (open_colorimeter_firmware, a separate repo) is updated in
        # lockstep to always emit "# ConcenUnit:", so this gate now requires 4.
        if len(self.metadata) != 4:
            self.log("Main header received but metadata incomplete.")
            return
        self.output_file = get_next_filename(self.extension, self.base_dir, self.base_name)
        # Save latest output path so Flask can find it.
        marker = os.path.join(self.log_dir, "current_output.txt")
        with open(marker, "w", encoding="utf-8") as m:
            m.write(self.output_file)
        os.makedirs(self.base_dir, exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            for key, value in self.metadata.items():
                f.write(f"# {key}: {value}\n")
            f.write(line + "\n")
        self.log(f"New session started. Header written to {self.output_file}")
        self.session_started = True

    def process_data(self, line):
        fields = line.split(",")
        unit = "" if self.x_label == "Turn" else "s"
        self.log(f"Received: {self.x_label}: {fields[0]}{unit}, Values: {', '.join(fields[1:])}")
        with open(self.output_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def process_line(self, raw):
        line = raw.strip()
        if not line:
            return
        try:
            if self.is_metadata(line) and not self.session_started:
                self.handle_metadata(line)
            elif self.is_main_header(line) and not self.session_started:
                self.handle_main_header(line)
            elif self.is_valid_data(line) and self.session_started:
                self.process_data(line)
            elif self.is_end_session(line) and self.session_started:
                # A host-initiated session is one-shot: once the device times
                # out we're done, so stop and let the app report completion.
                self._finish_session("SESSION TIMEOUT")
            elif self.is_stopped(line) and self.session_started:
                # Manual stop from the device's Left button — same one-shot end as
                # a timeout, but logged distinctly so the UI announces it as a
                # device stop rather than a timeout.
                self._finish_session("SESSION STOPPED")
            else:
                self.log(f"Unexpected line: {line}")
        except Exception as e:
            self.log(f"Error processing line '{line}': {e}")

    def _send_measure(self, reason=""):
        """Send one MEASURE command to the device (manual capture). Best-effort —
        a failed send is logged and the caller/next press retries."""
        try:
            self.serial.write(b"MEASURE\n")
            self.serial.flush()
            self.log(f"MEASURE sent{f' ({reason})' if reason else ''}.")
        except Exception as e:
            self.log(f"Failed to send MEASURE: {e}")

    def _check_measure_trigger(self):
        """Manual capture: if Flask dropped the trigger file, consume it and send
        one MEASURE command to the device. No-op when not in manual mode."""
        if not self.manual:
            return
        try:
            if not os.path.exists(self.trigger_path):
                return
            os.remove(self.trigger_path)
        except OSError:
            return
        self._send_measure("manual request")

    def _finish_session(self, reason):
        """End the one-shot session, logging `reason` (SESSION TIMEOUT / STOPPED)
        so the host UI can announce why the reading ended."""
        self.log(reason)
        self.session_started = False
        self.metadata = {}
        self.num_values = None
        self.running = False

    # ── lifecycle ───────────────────────────────────────────────────────
    def _send_start_commands(self):
        timeout = float(self.timeout_sec) if self.timeout_sec is not None else -1
        interval = float(self.interval_sec) if self.interval_sec is not None else -1
        # AXIS goes between TIMEOUT and INTERVAL (INTERVAL is the stage that
        # starts the device talking, so the axis must be set before it). For a
        # manual capture, MANUAL:1 is inserted between AXIS and INTERVAL so the
        # device arms manual mode before it would otherwise begin streaming.
        if self.manual:
            commands = ["1\n", f"TIMEOUT:{timeout}\n", f"AXIS:{self.axis}\n",
                        "MANUAL:1\n", f"INTERVAL:{interval}\n"]
            acks = ["ACK_START", "ACK_TIMEOUT", "ACK_AXIS", "ACK_MANUAL", "ACK_INTERVAL"]
            errs = ["ERR_START", "ERR_TIMEOUT", "ERR_AXIS", "ERR_MANUAL", "ERR_INTERVAL"]
        else:
            commands = ["1\n", f"TIMEOUT:{timeout}\n", f"AXIS:{self.axis}\n", f"INTERVAL:{interval}\n"]
            acks = ["ACK_START", "ACK_TIMEOUT", "ACK_AXIS", "ACK_INTERVAL"]
            errs = ["ERR_START", "ERR_TIMEOUT", "ERR_AXIS", "ERR_INTERVAL"]
        return send_command_and_wait_ack(self.serial, commands, acks, errs)

    def start(self):
        # Handle SIGTERM/SIGINT so the finally block runs and the device is told
        # to stop, mirroring the legacy collector's clean-shutdown contract.
        def _handle_signal(signum, frame):
            self.log(f"Received signal {signum}, stopping cleanly...")
            self.running = False

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        # Drop any stale trigger from a prior run so the first MEASURE is a real,
        # user-initiated press (mirrors hardware_routes.clear_measure_trigger).
        try:
            if os.path.exists(self.trigger_path):
                os.remove(self.trigger_path)
        except OSError:
            pass

        self.log("Connecting to PyBadge over CDC serial...")
        try:
            self.serial = connect_to_device()
        except Exception as e:
            # check_log_for_errors() in script_monitor keys off "PyBadge not found".
            self.log(f"PyBadge not found. {e}")
            return 1
        self.log(f"Connected to PyBadge at {self.serial.port}")

        try:
            success, error_msg = self._send_start_commands()
            if not success:
                self.log(f"Failed to start session: {error_msg}")
                return 1

            self.log("Reading CDC data stream. Send SIGINT/SIGTERM to stop.")
            # Manual capture: record the first Turn immediately on start (the
            # device idles otherwise, so Turn 1 would wait for the first press).
            # The device buffers this until it finishes its connection settle,
            # then emits Turn 1 — arriving after the header, so the stream order
            # stays valid.
            if self.manual:
                self._send_measure("initial Turn on start")
            # LineReader, not readline(): the port timeout is short so the manual
            # trigger is picked up promptly, and at that cadence readline() would
            # hand back partial lines. LineReader buffers and yields whole lines.
            reader = LineReader(self.serial)
            while self.running:
                # Forward any pending manual-measure request before blocking on
                # the next read (each read blocks ≤ one port timeout, 0.15s).
                self._check_measure_trigger()
                for line in reader.read_lines():
                    self.process_line(line)
                    if not self.running:
                        break
        except Exception as e:
            self.log(f"Error: {e}")
            return 1
        finally:
            # Best-effort: tell the device to leave talking mode, then close
            # (closing also drops DTR, which the firmware treats as a stop).
            try:
                if self.serial and self.serial.is_open:
                    self.serial.write(b"0\n")
                    self.serial.flush()
                    time.sleep(0.2)
            except Exception:
                pass
            try:
                if self.serial and self.serial.is_open:
                    self.serial.close()
            except Exception:
                pass
            self.log("CDC serial closed.")
        return 0


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description="CDC Data Collector for PyBadge")
    # Accept (and ignore) the dispatch flag in case we're invoked via it.
    parser.add_argument("--cdc-logger", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--base-dir", type=str, default=os.path.join(os.getcwd(), "data"),
        help="Directory to save output CSV files (default: ./data)")
    parser.add_argument(
        "--base-name", type=str, default="colorimeter_data",
        help="Base name for output CSV files (default: colorimeter_data)")
    parser.add_argument(
        "--timeout-sec", type=float, default=None,
        help="Session timeout in seconds (omit/negative for infinite)")
    parser.add_argument(
        "--interval-sec", type=float, default=None,
        help="Transmission interval in seconds")
    parser.add_argument(
        "--axis", type=str, default="time", choices=["time", "turn"],
        help="First-column axis: 'time' (Timestamp seconds) or 'turn' (1,2,3… index)")
    parser.add_argument(
        "--manual", action="store_true",
        help="Manual point-mode capture: device idles, one row per MEASURE (implies --axis turn)")
    args = parser.parse_args(argv)
    base_dir = os.getenv(args.base_dir, args.base_dir)
    args.base_dir = os.path.abspath(os.path.expanduser(base_dir))
    return args


def main(argv=None):
    args = parse_arguments(argv)
    collector = CDCDataCollector(
        args.base_dir, args.base_name,
        timeout_sec=args.timeout_sec, interval_sec=args.interval_sec,
        axis=args.axis, manual=args.manual,
    )
    return collector.start()


if __name__ == "__main__":
    sys.exit(main())
