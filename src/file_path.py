import os
from pathlib import Path
import re

# All user data is confined to the data/ directory under the project root.
def _find_project_root():
    d = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _ in range(3):
        if os.path.isfile(os.path.join(d, 'main.py')):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return d

DATA_ROOT = os.path.join(_find_project_root(), 'data')
os.makedirs(DATA_ROOT, exist_ok=True)

# Folder name reserved by the data-archive feature. When the app is uninstalled
# or updated, the installers stash loose files sitting directly in the data root
# into a ``data/<RESERVED_ARCHIVE_FOLDER>/`` staging folder so the archived
# ``data/`` tree is purely subfolder-based; on restore the staging folder is
# dissolved back into the data root. A user-created subfolder with this name
# would collide with that staging folder, so folder creation/rename forbids it.
RESERVED_ARCHIVE_FOLDER = "root"


def is_reserved_data_folder_name(name: str) -> bool:
    """True if ``name`` collides with a reserved data-folder name (case-insensitive)."""
    return (name or "").strip().lower() == RESERVED_ARCHIVE_FOLDER


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


def detect_csv_schema(header_line: str):
    """
    Identify the CSV schema from the header line.
    Returns one of the ``CSV_SCHEMA_*`` constants, or ``None`` for an
    unrecognised header.
    """
    header = header_line.strip()
    if is_multi_value_timeseries_csv_header(header):
        return CSV_SCHEMA_TIMESERIES
    header_norm = re.sub(r'\s*,\s*', ',', header)
    if header_norm == 'Concentration,maxRate,Slope,Sat,Time To Sat':
        return CSV_SCHEMA_KINETICS_CAL
    if header_norm == 'Concentration,Value,TimePoint':
        return CSV_SCHEMA_POINT_CAL
    return None
