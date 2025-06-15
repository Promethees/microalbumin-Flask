import hid
import time
import datetime
import os
import re
import glob
import argparse

# PyBadge USB VID and PID (Adafruit PyBadge)
PYBADGE_VID = 0x239A  # Adafruit's Vendor ID
PYBADGE_PID = 0x8034  # PyBadge Product ID (from hid_read_keyboard.py)

# Standard USB HID keyboard report format: 8 bytes
# Byte 0: Modifier keys (ignored)
# Byte 1: Reserved (0x00)
# Bytes 2-7: Keycodes (one key per report for KeyboardLayoutUS.write())
REPORT_LENGTH = 8

# Keycode mapping (from USB HID Usage Tables, Keyboard/Keypad Page)
# Maps to uppercase letters and literal characters as sent by KeyboardLayoutUS.write()
KEYCODE_MAP = {
    0x04: 'A', 0x05: 'B', 0x06: 'C', 0x07: 'D', 0x08: 'E', 0x09: 'F',
    0x0A: 'G', 0x0B: 'H', 0x0C: 'I', 0x0D: 'J', 0x0E: 'K', 0x0F: 'L',
    0x10: 'M', 0x11: 'N', 0x12: 'O', 0x13: 'P', 0x14: 'Q', 0x15: 'R',
    0x16: 'S', 0x17: 'T', 0x18: 'U', 0x19: 'V', 0x1A: 'W', 0x1B: 'X',
    0x1C: 'Y', 0x1D: 'Z',
    0x1E: '1', 0x1F: '2', 0x20: '3', 0x21: '4', 0x22: '5', 0x23: '6',
    0x24: '7', 0x25: '8', 0x26: '9', 0x27: '0',
    0x28: 'enter', 0x29: 'escape', 0x2A: 'backspace', 0x2B: 'tab',
    0x2C: 'space', 0x36: ',', 0x37: '.'
}

class HIDDataCollector:
    def __init__(self, base_dir, base_name="colorimeter_data", extension=".csv"):
        self.base_dir = base_dir
        self.base_name = base_name
        self.extension = extension
        self.output_file = None
        self.running = True
        self.buffer = ""
        self.header_pattern = r"^TIMESTAMP,MEASUREMENT,VALUE,UNIT,TYPE,BLANKED,CONCENTRATION\n$"
        self.data_pattern = r"^\d+\.\d{1,2},[A-Za-z]+,\d+\.\d{1,2},[A-Za-z]+,[A-Za-z]+,[A-Za-z]+\n$"
        self.session_started = False

    def find_pybadge(self):
        """Find the PyBadge HID device by VID and PID."""
        for device_info in hid.enumerate():
            if device_info['vendor_id'] == PYBADGE_VID and device_info['product_id'] == PYBADGE_PID:
                return device_info
        return None

    def decode_report(self, report):
        """Decode an 8-byte HID keyboard report into keys."""
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
        if key == 'enter':
            self.buffer += '\n'
            lines = self.buffer.split('\n')
            for line in lines[:-1]:
                line_with_newline = line + '\n'
                if self.is_header(line_with_newline):
                    self.handle_header()
                    self.session_started = True
                elif self.is_valid_data(line_with_newline) and self.session_started:
                    self.process_data(line_with_newline)
            self.buffer = lines[-1]
        elif key == "space":
            self.buffer += ' '
        else:
            self.buffer += key
        # print(f"Current buffer is {self.buffer}")

    def is_header(self, line):
        return bool(re.match(self.header_pattern, line))

    def is_valid_data(self, line):
        return bool(re.match(self.data_pattern, line))

    def handle_header(self):
        self.output_file = self.get_next_filename()
        os.makedirs(self.base_dir, exist_ok=True)
        with open(self.output_file, "w") as f:
            f.write("Timestamp,Measurement,Value,Unit,Type,Blanked\n")
        print(f"New session started. Header written to {self.output_file}")

    def process_data(self, data):
        try:
            timestamp, measurement_name, value, units, type_tag, blanked, concen = data.strip().split(',')
            print(f"Received: Timestamp: {timestamp}s, Measurement: {measurement_name}, Value: {value} {units}, Type: {type_tag}, Blanked: {blanked}, Concentration: {concen}")
            with open(self.output_file, "a") as f:
                f.write(data)
        except ValueError as e:
            print(f"Error parsing data: {e}")

    def get_next_filename(self):
        pattern = os.path.join(self.base_dir, f"{self.base_name}_*[0-9].csv")
        existing_files = glob.glob(pattern)
        number_pattern = re.compile(rf"{self.base_name}_(\d+)\.csv$")
        numbers = []
        for file in existing_files:
            match = number_pattern.search(os.path.basename(file))
            if match:
                numbers.append(int(match.group(1)))
        next_number = max(numbers, default=-1) + 1
        return os.path.join(self.base_dir, f"{self.base_name}_{next_number}{self.extension}")

    def start(self):
        print("Searching for PyBadge HID device...")
        device_info = self.find_pybadge()
        if not device_info:
            print("PyBadge not found. Ensure it is connected and configured as an HID keyboard.")
            return

        print(f"Found PyBadge: {device_info['product_string']} (VID: {hex(device_info['vendor_id'])}, PID: {hex(device_info['product_id'])})")

        device = hid.Device(PYBADGE_VID, PYBADGE_PID)
        try:
            print("Reading HID reports. Press Ctrl+C to stop.")
            last_report = None

            while self.running:
                report = device.read(REPORT_LENGTH, timeout=5000)
                if report:
                    timestamp = time.time()
                    keys = self.decode_report(report)
                    if keys and (report != last_report or not keys):
                        for key in keys:  # Process each key in the report
                            self.process_key(key)
                        last_report = report
                time.sleep(0.001)

        except KeyboardInterrupt:
            print("Stopped by user.")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            device.close()
            print("HID device closed.")

def parse_arguments():
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