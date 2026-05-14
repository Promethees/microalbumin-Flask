import os
from pathlib import Path
import re

# All user data is confined to the data/ directory under the project root.
DATA_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
os.makedirs(DATA_ROOT, exist_ok=True)


def validate_in_data_root(path: str):
    """Return abs path if it's within DATA_ROOT, else None."""
    abs_path = os.path.abspath(path)
    if abs_path == DATA_ROOT or abs_path.startswith(DATA_ROOT + os.sep):
        return abs_path
    return None


def get_data_subfolders():
    """Returns immediate non-hidden subdirectories of DATA_ROOT, sorted by name."""
    root = Path(DATA_ROOT)
    if not root.is_dir():
        return []
    return sorted(
        [{"name": p.name, "path": str(p)} for p in root.iterdir()
         if p.is_dir() and not p.name.startswith('.') and not p.name.startswith('_')],
        key=lambda x: x["name"].lower()
    )


def is_multi_value_timeseries_csv_header(header_line: str) -> bool:
    """
    Checks if the header matches the pattern used for raw multi-sensor/time-series data:
    Timestamp,Value:1,Value:2,Value:3,... (with possible extra spaces)
    """
    cleaned = re.sub(r'\s+', '', header_line.strip())
    if not cleaned.startswith('Timestamp,'):
        return False
    parts = cleaned.split(',')
    if len(parts) < 2:
        return False
    value_parts = parts[1:]
    return all(part.startswith('Value:') for part in value_parts)
