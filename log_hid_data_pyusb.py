import usb.core
import usb.util
import time
import datetime
import os
import re
import argparse
import signal
import sys
sys.path.append('code\src')
from get_next_filename import get_next_filename

# PyBadge USB VID and PID (Adafruit PyBadge)
PYBADGE_VID = 0x239A  # Adafruit's Vendor ID
PYBADGE_PID = 0x8034  # PyBadge Product ID

# Standard USB HID keyboard report format: 8 bytes
# Byte 0: Modifier keys (ignored)
# Byte 1: Reserved (0x00)
# Bytes 2-7: Keycodes
REPORT_LENGTH = 9

# Keycode mapping (shifted characters only, as per US keyboard layout)
KEYCODE_MAP = {
    0x04: 'A', 0x05: 'B', 0x06: 'C', 0x07: 'D', 0x08: 'E', 0x09: 'F',
    0x0A: 'G', 0x0B: 'H', 0x0C: 'I', 0x0D: 'J', 0x0E: 'K', 0x0F: 'L',
    0x10: 'M', 0x11: 'N', 0x12: 'O', 0x13: 'P', 0x14: 'Q', 0x15: 'R',
    0x16: 'S', 0x17: 'T', 0x18: 'U', 0x19: 'V', 0x1A: 'W', 0x1B: 'X',
    0x1C: 'Y', 0x1D: 'Z',
    0x1E: '1', 0x1F: '2', 0x20: '3', 0x21: '4', 0x22: '5', 0x23: '6',
    0x24: '7', 0x25: '8', 0x26: '9', 0x27: '0',
    0x28: 'enter', 0x29: 'escape', 0x2A: 'backspace', 0x2B: 'tab',
    0x2C: 'space', 0x2D: '-', 0x36: ',', 0x37: '.', 0x33: ':'
}

class HIDDataCollector:
    def __init__(self, base_dir, base_name="colorimeter_data", extension=".csv"):
        self.base_dir = base_dir
        self.base_name = base_name
        self.extension = extension
        self.output_file = None
        self.running = True
        self.buffer = ""
        self.metadata = {}
        self.metadata_pattern = r"^3 (MEASUREMENT|UNIT|CONCENTRATION):\s*([A-Za-z0-9μ]+)$"
        self.header_pattern = r"^TIMESTAMP,VALUE:\d+(?:,VALUE:\d+)*\n$"
        self.data_pattern = r"^\d+\.\d{1,2},(?:-?\d+\.\d{1,3}|OVFL)(?:,(?:-?\d+\.\d{1,3}|OVFL))*\n$"
        self.end_pattern = r"^SESSION TIMEOUT\n$"
        self.session_started = False
        self.current_header_index = None  # Track which header pattern is active
        self.num_values = None  # Track number of VALUE fields
        self.device = None
        self.endpoint = None
        self.interface = None

        # Logging setup
        self.log_dir = os.path.join(os.getcwd(), "code/log")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.log_dir, "script_logs.txt")
        self.log_file = open(self.log_file_path, 'a', encoding='utf-8')

    def log(self, message):
        """Write a message to the log file with a timestamp."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")

    def find_pybadge(self):
        """Find the PyBadge USB device by VID and PID."""
        device = usb.core.find(idVendor=PYBADGE_VID, idProduct=PYBADGE_PID)
        if device is None:
            self.log("PyBadge not found.")
            return None
        self.log("PyBadge found.")
        return device

    def find_input_endpoint(self):
        """Find the input endpoint for the PyBadge."""
        for cfg in self.device:
            for intf in cfg:
                if intf.bInterfaceClass == 3:  # HID class
                    for ep in intf:
                        if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN:
                            self.log(f"Found input endpoint: address=0x{ep.bEndpointAddress:x}, interface={intf.bInterfaceNumber}")
                            return ep, intf
        self.log("No HID input endpoint found")
        return None, None

    def decode_report(self, report):
        """Decode an 8-byte HID keyboard report into keys."""
        if len(report) != REPORT_LENGTH:
            self.log(f"Invalid report length: {len(report)}, expected {REPORT_LENGTH}")
            return []

        keycodes = report[2:8]  # Keycodes in bytes 2-7
        keys = []
        for keycode in keycodes:
            if keycode != 0 and keycode in KEYCODE_MAP:
                keys.append(KEYCODE_MAP[keycode])
        return keys

    def process_key(self, key):
        """Process a single keypress, buffering until newline."""
        if not self.is_valid_key(key):
            return  # Ignore invalid keys

        if key == 'enter':
            self.buffer += '\n'
            lines = self.buffer.split('\n')
            for line in lines[:-1]:
                line_with_newline = line + '\n'
                try:
                    if self.is_metadata(line_with_newline) and not self.session_started:
                        self.handle_metadata(line_with_newline)
                    elif self.is_main_header(line_with_newline) and not self.session_started:
                        self.handle_main_header(line_with_newline)
                    elif self.is_valid_data(line_with_newline) and self.session_started:
                        self.process_data(line_with_newline)
                    elif self.is_end_session(line_with_newline) and self.session_started:
                        self.log(line_with_newline)
                        self.session_started = False
                        self.buffer = ''
                        self.metadata = {}
                        self.num_values = None
                    else:
                        self.log(f"Unexpected line: {line_with_newline}")
                except Exception as e:
                    self.log(f"Error processing line '{line_with_newline}': {e}")
            self.buffer = lines[-1] if lines[-1] else ''
        elif key == "space":
            self.buffer += ' '
        else:
            self.buffer += key

    def is_valid_key(self, key):
        """Validate the input key."""
        return isinstance(key, str) and (key == 'enter' or key == 'space' or key.isprintable() or key in '#:')

    def is_metadata(self, line):
        """Check if the line matches the metadata pattern."""
        return bool(re.match(self.metadata_pattern, line))

    def is_main_header(self, line):
        """Check if the line matches the main header pattern."""
        if re.match(self.header_pattern, line):
            headers = line.strip().split(',')
            self.num_values = len(headers) - 1  # exclude TIMESTAMP
            return True
        return False

    def is_valid_data(self, line):
        """Check if data lines are corresponding to the headers"""
        if self.num_values is None:
            return False
        if not re.match(self.data_pattern, line):
            return False
        values = line.strip().split(',')
        return len(values) == self.num_values + 1  # +1 for timestamp

    def is_end_session(self, line):
        """Check if the line matches the session end pattern."""
        return bool(re.match(self.end_pattern, line))

    def handle_metadata(self, line):
        """Process metadata header lines."""
        match = re.match(self.metadata_pattern, line)
        if match:
            key, value = match.groups()
            if value == "UWCM2":
                value = "μW/cm²"  # Replace with proper micro symbol
            self.metadata[key] = value
            self.log(f"Received metadata: {key} = {value}")

    def handle_main_header(self, line):
        """Process the main CSV header and start the session if metadata is complete."""
        if len(self.metadata) != 3:
            self.log("Main header received but metadata incomplete.")
            return

        self.output_file = get_next_filename(self.extension, self.base_dir, self.base_name)
        os.makedirs(self.base_dir, exist_ok=True)
        with open(self.output_file, "w", encoding='utf-8') as f:
            # Write metadata as comments
            for key, value in self.metadata.items():
                f.write(f"# {key.title()}: {value}\n")
            # Convert header to desired case
            header = line.replace('TIMESTAMP', 'Timestamp').replace('VALUE', 'Value')
            f.write(header)
        self.log(f"New session started. Header written to {self.output_file}")

        # Save latest output path so Flask can find it
        latest_file_marker = os.path.join(self.log_dir, "current_output.txt")
        open(latest_file_marker, "w").close()
        with open(latest_file_marker, "w", encoding='utf-8') as marker:
            marker.write(self.output_file)

        self.session_started = True

    def process_data(self, data):
        """Process and log data lines, writing them to the output file."""
        try:
            fields = data.strip().split(',')
            timestamp = fields[0]
            values = fields[1:]  # All fields after timestamp
            log_message = f"Received: Timestamp: {timestamp}s, Values: {', '.join(values)}"
            self.log(log_message)
            with open(self.output_file, "a", encoding='utf-8') as f:
                f.write(data)
        except ValueError as e:
            self.log(f"Error parsing data: {e}")

    def start(self):
        """Start the HID data collection process."""
        # Handle SIGTERM and SIGINT gracefully so the finally block always runs,
        # which prevents semaphore leaks from abrupt process termination.
        def _handle_signal(signum, frame):
            self.log(f"Received signal {signum}, stopping cleanly...")
            self.running = False

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        self.log("Searching for PyBadge HID device...")
        self.device = self.find_pybadge()
        if not self.device:
            self.log("PyBadge not found. Ensure it is connected and configured with libusbK driver.")
            self.log("Terminating script.")
            self.log_file.close()
            sys.exit(1)

        self.log(f"Found PyBadge: {self.device.manufacturer} {self.device.product} (VID: {hex(self.device.idVendor)}, PID: {hex(self.device.idProduct)})")

        try:
            # Set configuration
            self.device.set_configuration()
            self.log("Device configuration set")

            # Find HID input endpoint
            self.endpoint, self.interface = self.find_input_endpoint()
            if not self.endpoint:
                self.log("Failed to find input endpoint. Exiting.")
                self.log_file.close()
                sys.exit(1)

            # Claim interface
            usb.util.claim_interface(self.device, self.interface)
            self.log("Reading HID reports. Press Ctrl+C to stop.")

            while self.running:
                try:
                    # Read data from input endpoint
                    data = self.device.read(self.endpoint.bEndpointAddress, REPORT_LENGTH, timeout=5000)
                    if data:
                        keys = self.decode_report(data)
                        if keys:
                            for key in keys:
                                self.process_key(key)
                    time.sleep(0.001)  # Prevent CPU overuse
                except usb.core.USBError as e:
                    if e.errno == 110:  # Timeout
                        pass
                    else:
                        if not self.find_pybadge():
                            self.log("PyBadge not found. Ensure it is connected and configured with libusbK driver.")
                            self.log("Terminating script.")
                            self.device = None
                            sys.exit(1)
                        self.log(f"Waiting for the next report sent by the device")
                    time.sleep(0.1)  # Slow down on errors

        except KeyboardInterrupt:
            self.log("Stopped by user.")
        except Exception as e:
            self.log(f"Error: {str(e)}")
        finally:
            if self.device:
                try:
                    if self.interface:
                        usb.util.release_interface(self.device, self.interface)
                        self.log("HID device closed.")
                    usb.util.dispose_resources(self.device)
                except Exception as e:
                    self.log(f"Error during cleanup: {str(e)}")
            self.log_file.close()
            self.log("Log file closed.")

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="HID Data Collector for PyBadge")
    parser.add_argument(
        "--base-dir",
        type=str,
        default=os.path.join(os.getcwd(), "data"),
        help="Directory to save output CSV files (default: ./data)"
    )
    parser.add_argument(
        "--base-name",
        type=str,
        default="colorimeter_data",
        help="Base name for output CSV files (default: colorimeter_data)"
    )
    args = parser.parse_args()
    base_dir = os.getenv(args.base_dir, args.base_dir)
    args.base_dir = os.path.abspath(os.path.expanduser(base_dir))
    return args

if __name__ == "__main__":
    args = parse_arguments()
    collector = HIDDataCollector(args.base_dir, args.base_name)
    collector.start()