"""CDC (USB serial) data collector — default transport for host-initiated
measurement sessions with the PyBadge colorimeter.

This replaces the HID-keyboard reader (``log_hid_data.py`` / ``log_hid_data_pyusb.py``,
kept only as a manual fallback the device triggers via its Left button) for the
app's automated "Run" flow. Unlike the HID path, this collector:

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

from get_next_filename import get_next_filename
from send_command import connect_to_device, send_command_and_wait_ack


class CDCDataCollector:
    def __init__(self, base_dir, base_name="colorimeter_data", extension=".csv",
                 timeout_sec=None, interval_sec=None):
        self.base_dir = base_dir
        self.base_name = base_name
        self.extension = extension
        self.timeout_sec = timeout_sec
        self.interval_sec = interval_sec

        self.serial = None
        self.output_file = None
        self.running = True

        self.metadata = {}
        self.num_values = None
        self.session_started = False

        # CDC delivers the device's exact bytes, so these patterns match the
        # clean text emitted by serial_manager._write() — no HID up-casing /
        # modifier-stripping like the keyboard path had to undo.
        self.metadata_pattern = r"^#\s*(Measurement|Unit|Concentration):\s*(.+?)\s*$"
        self.header_pattern = r"^Timestamp,Value:\d+(?:,Value:\d+)*$"
        self.data_pattern = r"^\d+\.\d{1,2},(?:-?\d+\.\d{1,3}|OVFL)(?:,(?:-?\d+\.\d{1,3}|OVFL))*$"
        self.end_pattern = r"^SESSION TIMEOUT$"

        self.log_dir = os.path.join(_SCRIPT_DIR, "log")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.log_dir, "script_logs.txt")

    def log(self, message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_file_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")

    # ── line classification ─────────────────────────────────────────────
    def is_metadata(self, line):
        return bool(re.match(self.metadata_pattern, line))

    def is_main_header(self, line):
        if re.match(self.header_pattern, line):
            self.num_values = len(line.split(",")) - 1  # exclude Timestamp
            return True
        return False

    def is_valid_data(self, line):
        if self.num_values is None or not re.match(self.data_pattern, line):
            return False
        return len(line.split(",")) == self.num_values + 1

    def is_end_session(self, line):
        return bool(re.match(self.end_pattern, line))

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
        if len(self.metadata) != 3:
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
        self.log(f"Received: Timestamp: {fields[0]}s, Values: {', '.join(fields[1:])}")
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
                self.log("SESSION TIMEOUT")
                self.session_started = False
                self.metadata = {}
                self.num_values = None
                # A host-initiated session is one-shot: once the device times
                # out we're done, so stop and let the app report completion.
                self.running = False
            else:
                self.log(f"Unexpected line: {line}")
        except Exception as e:
            self.log(f"Error processing line '{line}': {e}")

    # ── lifecycle ───────────────────────────────────────────────────────
    def _send_start_commands(self):
        timeout = float(self.timeout_sec) if self.timeout_sec is not None else -1
        interval = float(self.interval_sec) if self.interval_sec is not None else -1
        commands = ["1\n", f"TIMEOUT:{timeout}\n", f"INTERVAL:{interval}\n"]
        return send_command_and_wait_ack(
            self.serial, commands,
            ["ACK_START", "ACK_TIMEOUT", "ACK_INTERVAL"],
            ["ERR_START", "ERR_TIMEOUT", "ERR_INTERVAL"],
        )

    def start(self):
        # Handle SIGTERM/SIGINT so the finally block runs and the device is told
        # to stop, mirroring the HID collector's clean-shutdown contract.
        def _handle_signal(signum, frame):
            self.log(f"Received signal {signum}, stopping cleanly...")
            self.running = False

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

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
            while self.running:
                line = self.serial.readline()
                if not line:
                    continue  # read timeout — keep waiting for the next line
                self.process_line(line.decode("utf-8", errors="replace"))
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
    args = parser.parse_args(argv)
    base_dir = os.getenv(args.base_dir, args.base_dir)
    args.base_dir = os.path.abspath(os.path.expanduser(base_dir))
    return args


def main(argv=None):
    args = parse_arguments(argv)
    collector = CDCDataCollector(
        args.base_dir, args.base_name,
        timeout_sec=args.timeout_sec, interval_sec=args.interval_sec,
    )
    return collector.start()


if __name__ == "__main__":
    sys.exit(main())
