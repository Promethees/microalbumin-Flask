import os
import re

# This will point to the directory where main.py is located
current_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def get_directory():
    global current_directory
    # Convert single backslashes to double backslashes for JavaScript compatibility
    # return current_directory.replace('\\', '\\\\')
    return current_directory

def browse_directory(new_path):
    global current_directory
    new_path = os.path.expanduser(new_path)
    if os.path.isdir(new_path):
        current_directory = os.path.abspath(new_path)
        # Convert single backslashes to double backslashes for JavaScript compatibility
        return current_directory.replace('\\', '\\\\')
    return False

def get_parent_directory(path, levels=1):
    """
    Returns the parent directory of the given path.
    `levels` specifies how many levels up to go (default is 1).
    """
    if not path:
        raise ValueError("Path cannot be empty.")
    
    path = os.path.abspath(path)
    for _ in range(levels):
        path = os.path.dirname(path)
    
    # Convert single backslashes to double backslashes for JavaScript compatibility
    return path.replace('\\', '\\\\')

def get_child_directories(path):
    """
    Returns a list of full paths to all immediate subdirectories of the given path.
    """
    if not os.path.isdir(path):
        raise ValueError(f"'{path}' is not a valid directory.")

    # Convert each child directory path to use double backslashes
    path = os.path.abspath(path)
    return [
        os.path.join(path, name).replace('\\', '\\\\')
        for name in os.listdir(path)
        if os.path.isdir(os.path.join(path, name))
    ]


# ---------------------------------------------------------------------------
# CSV schema constants
# ---------------------------------------------------------------------------
CSV_SCHEMA_TIMESERIES = 'timeseries'       # Timestamp,Value:1[,Value:2,...]
CSV_SCHEMA_KINETICS_CAL = 'kinetics_cal'   # Concentration,maxRate,Slope,Sat,Time To Sat
CSV_SCHEMA_POINT_CAL = 'point_cal'         # Concentration,Value,TimePoint


def parse_csv_metadata(lines) -> dict:
    """
    Parse ``# Key: Value`` metadata from an iterable of CSV lines.
    Non-metadata lines (no leading ``#``) are silently skipped.
    Returns a plain dict of {key: value} strings.
    """
    meta = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#') and ':' in stripped:
            key, value = stripped[1:].split(':', 1)
            meta[key.strip()] = value.strip()
    return meta


def _is_timeseries_header(header_line: str) -> bool:
    cleaned = re.sub(r'\s+', '', header_line.strip())
    if not cleaned.startswith('Timestamp,'):
        return False
    parts = cleaned.split(',')
    return len(parts) >= 2 and all(p.startswith('Value:') for p in parts[1:])


def detect_csv_schema(header_line: str):
    """
    Identify the CSV schema from the header line.
    Returns one of the ``CSV_SCHEMA_*`` constants, or ``None`` for an
    unrecognised header.
    """
    header = header_line.strip()
    if _is_timeseries_header(header):
        return CSV_SCHEMA_TIMESERIES
    header_norm = re.sub(r'\s*,\s*', ',', header)
    if header_norm == 'Concentration,maxRate,Slope,Sat,Time To Sat':
        return CSV_SCHEMA_KINETICS_CAL
    if header_norm == 'Concentration,Value,TimePoint':
        return CSV_SCHEMA_POINT_CAL
    return None