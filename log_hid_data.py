import hid
import time
import datetime
import os
import re
import argparse
import sys

sys.path.append('src')
from get_next_filename import get_next_filename

# PyBadge USB VID and PID (Adafruit PyBadge)
PYBADGE_VID = 0x239A  # Adafruit's Vendor ID
PYBADGE_PID = 0x8034  # PyBadge Product ID (from hid_read_keyboard.py)

# Standard USB HID keyboard report format: 8 bytes
# Byte 0: Modifier keys (ignored)
# Byte 1: Reserved (0x00)
# Bytes 2-7: Keycodes
REPORT_LENGTH = 8

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
    0x2C: 'space', 0x36: ',', 0x37: '.', 0x33: ':', 0x2F: '/'
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
        self.metadata_pattern = r"^3 (MEASUREMENT|UNIT|CONCENTRATION):\s*([A-Za-z0-9]+)$"
        self.header_pattern = r"^TIMESTAMP,VALUE:\d+(?:,VALUE:\d+)*\n$"
        self.data_pattern = r"^\d+\.\d{1,2},(?:\d+\.\d{1,3}|OVFL)(?:,(?:\d+\.\d{1,3}|OVFL))*\n$"
        self.end_pattern = r"^SESSION TIMEOUT\n$"
        
        self.session_started = False
        self.num_values = None # Track number of VALUE fields in the incoming data
        
        # Logging setup
        self.log_dir = os.path.join(os.getcwd(), "log")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.log_dir, "script_logs.txt")
        self.log_file = open(self.log_file_path, 'a')

    def log(self, message):
        """Write a message to the log file with a timestamp."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_file_path, 'a') as f:
            f.write(f"[{timestamp}] {message}\n")

    def find_pybadge(self):
        """Find the PyBadge HID device by VID and PID."""
        for device_info in hid.enumerate():
            if device_info['vendor_id'] == PYBADGE_VID and device_info['product_id'] == PYBADGE_PID:
                return device_info
        return None

    def decode_report(self, report):
        """Decode an 8-byte HID keyboard report into keys, using shifted map by default."""
        if len(report) != REPORT_LENGTH:
            return []

        keycodes = report[2:8]  # Keycodes are in bytes 2-7
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
        # timestamp + values (allow OVFL too)
        return len(values) == self.num_values + 1

    def is_end_session(self, line):
        """Check if the line matches the session end pattern."""
        return bool(re.match(self.end_pattern, line))

    def handle_metadata(self, line):
        """Process metadata header lines."""
        match = re.match(self.metadata_pattern, line)
        if match:
            key, value = match.groups()
            if value == "UWCM2":
                value = "\u03BCW/cm\u00B2"  # Replace with proper micro symbol
            self.metadata[key] = value
            self.log(f"Received metadata: {key} = {value}")

    def handle_main_header(self, line):
        """Process the main CSV header and start the session if metadata is complete."""
        if len(self.metadata) != 3:
            self.log("Main header received but metadata incomplete.")
            return

        self.output_file = get_next_filename(self.extension, self.base_dir, self.base_name)
        os.makedirs(self.base_dir, exist_ok=True)
        with open(self.output_file, "w") as f:
            # Write metadata as comments
            for key, value in self.metadata.items():
                f.write(f"# {key.title()}: {value}\n")
            # Convert header to desired case
            header = line.replace('TIMESTAMP', 'Timestamp').replace('VALUE:', 'Value ')
            f.write(header)
        self.log(f"New session started. Header written to {self.output_file}")

        # Save latest output path so Flask can find it
        latest_file_marker = os.path.join(self.log_dir, "current_output.txt")
        open(latest_file_marker, "w").close()
        with open(latest_file_marker, "w") as marker:
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
            with open(self.output_file, "a") as f:
                f.write(data)
        except ValueError as e:
            self.log(f"Error parsing data: {e}")

    def start(self):
        """Start the HID data collection process."""
        self.log("Searching for PyBadge HID device...")
        device_info = self.find_pybadge()
        if not device_info:
            self.log("PyBadge not found. Ensure it is connected and configured as an HID keyboard.")
            self.log_file.close()
            sys.exit(1)

        self.log(f"Found PyBadge: {device_info['product_string']} (VID: {hex(device_info['vendor_id'])}, PID: {hex(device_info['product_id'])})")

        device = hid.Device(PYBADGE_VID, PYBADGE_PID)

        try:
            self.log("Reading HID reports. Press Ctrl+C to stop.")
            while self.running:
                report = device.read(REPORT_LENGTH, timeout=5000)
                if report:
                    keys = self.decode_report(report)
                    if keys:
                        for key in keys:
                            self.process_key(key)
                time.sleep(0.001)

        except KeyboardInterrupt:
            self.log("Stopped by user.")

        finally:
            device.close()
            self.log("HID device closed.")
            self.log_file.close()

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

    # Check if the provided base_dir is an environment variable
    base_dir = os.getenv(args.base_dir, args.base_dir)
    
    # Ensure the directory path is absolute and normalized
    args.base_dir = os.path.abspath(os.path.expanduser(base_dir))
    return args

if __name__ == "__main__":
    args = parse_arguments()
    collector = HIDDataCollector(args.base_dir, args.base_name)
    collector.start()