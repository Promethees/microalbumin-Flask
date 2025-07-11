import usb.core
import usb.util
import time
import datetime
import os
import re
import glob
import argparse
import sys
from get_next_filename import get_next_filename

# PyBadge USB VID and PID (Adafruit PyBadge)
PYBADGE_VID = 0x239A  # Adafruit's Vendor ID
PYBADGE_PID = 0x8034  # PyBadge Product ID

# Standard USB HID keyboard report format: 8 bytes
# Bytes 0-5: Keycodes (one key per report for KeyboardLayoutUS.write())
REPORT_LENGTH = 9

# Keycode mapping (from USB HID Usage Tables, Keyboard/Keypad Page)
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
        self.data_pattern = r"^\d+\.\d{1,2},[A-Za-z]+,\d+\.\d{1,2},[A-Za-z]+,[A-Za-z]+,[A-Za-z]+,(NONE|\d+\.\d{1,2})\n$"
        self.session_started = False
        self.device = None
        self.endpoint = None
        self.interface = None
        self.last_report = None
        # Initialize log file in /log directory
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
        """Find the PyBadge USB device by VID and PID."""
        all_devices = usb.core.show_devices()
        self.log(f"Available USB devices: {all_devices}")
        device = usb.core.find(idVendor=PYBADGE_VID, idProduct=PYBADGE_PID)
        if device is None:
            return None
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

        keycodes = report[0:5]  # Keycodes in bytes 0-5
        keys = []
        for keycode in keycodes:
            if keycode != 0 and keycode in KEYCODE_MAP:
                keys.append(KEYCODE_MAP[keycode])
        return keys

    def process_key(self, key):
        """Process a single keypress, buffering until newline."""
        # self.log(f"Processing key: {key}")
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

    def is_header(self, line):
        return bool(re.match(self.header_pattern, line))

    def is_valid_data(self, line):
        return bool(re.match(self.data_pattern, line))

    def handle_header(self):
        self.output_file = get_next_filename(self.extension, self.base_dir, self.base_name)
        os.makedirs(self.base_dir, exist_ok=True)
        with open(self.output_file, "w") as f:
            f.write("Timestamp,Measurement,Value,Unit,Type,Blanked,Concentration\n")
        self.log(f"New session started. Header written to {self.output_file}")

    def process_data(self, data):
        try:
            timestamp, measurement_name, value, units, type_tag, blanked, concen = data.strip().split(',')
            self.log(f"Received: Timestamp: {timestamp}s, Measurement: {measurement_name}, Value: {value} {units}, Type: {type_tag}, Blanked: {blanked}, Concentration: {concen}")
            with open(self.output_file, "a") as f:
                f.write(data)
        except ValueError as e:
            self.log(f"Error parsing data: {e}")

    def start(self):
        self.log("Searching for PyBadge HID device...")
        self.device = self.find_pybadge()
        if not self.device:
            self.log("PyBadge not found. Ensure it is connected and configured with libusbK driver.")
            self.log("Terminating script.")
            self.log_file.close()
            sys.exit(1)  # Exit with non-zero status to indicate failure

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
            last_report = None

            while self.running:
                try:
                    # Read data from input endpoint
                    data = self.device.read(self.endpoint.bEndpointAddress, REPORT_LENGTH, timeout=5000)
                    # self.log(f"Raw data received: {data}")
                    if data and (data != last_report or not self.decode_report(data)):
                        # self.log(f"Received: {list(data)}")
                        keys = self.decode_report(data)
                        if keys:
                            # self.log(f"Decoded keys: {keys}")
                            for key in keys:
                                self.process_key(key)
                        last_report = data
                    time.sleep(0.001)  # Prevent CPU overuse
                except usb.core.USBError as e:
                    if e.errno == 110:  # Timeout
                        pass                        
                    else:
                        if not self.find_pybadge():
                            self.log("PyBadge not found. Ensure it is connected and configured with libusbK driver.")
                            self.log("Terminating script.")
                            self.device = None
                            sys.exit(1) # Exit with non-zero status to indicate failure

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