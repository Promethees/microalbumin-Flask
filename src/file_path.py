import os
from pathlib import Path
import re
import state

# All user data is confined to the writable data/ directory. In dev this is the
# project root; in a frozen build it is the per-user app-data dir (state.script_dir),
# never the read-only bundle. Kept in lockstep with state.data_root_path.
DATA_ROOT = os.path.join(state.script_dir, 'data')
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


def validate_in_allowed_roots(path: str):
    """Return abs path if it resolves inside a managed root, else None.

    The managed roots are the data root, the report root, and the calibration
    ``json/`` root — the only trees the app reads/edits/deletes on the user's
    behalf. Confining here (rather than the weak ``'..' in normpath`` check)
    stops a client-supplied ABSOLUTE path from escaping to arbitrary files:
    ``os.path.abspath`` resolves any ``..`` first, so both traversal and a bare
    absolute path (e.g. ``/etc/passwd``) that names something outside every root
    return None. Export destinations the user explicitly picks are NOT gated
    here — that is a deliberate "save out of the app" action.
    """
    if not path:
        return None
    abs_path = os.path.abspath(os.path.expanduser(path))
    roots = [DATA_ROOT]
    for attr in ('report_root_path', 'json_root_path'):
        root = getattr(state, attr, None)
        if root:
            roots.append(os.path.abspath(root))
    for root in roots:
        if abs_path == root or abs_path.startswith(root + os.sep):
            return abs_path
    return None


def validate_in_json_root(path: str):
    """Return abs path if it's within the calibration ``json/`` root, else None.

    The AI assistant's ``read_calibration_file`` tool takes an LLM-supplied
    filename/mode; confining the resolved path here stops a crafted ``..`` from
    escaping ``json/`` and reading sibling files in the data root such as
    ``activation.json`` (the license token) or ``.env``.
    """
    root = os.path.abspath(state.json_root_path)
    abs_path = os.path.abspath(path)
    if abs_path == root or abs_path.startswith(root + os.sep):
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


def _is_multi_value_series_header(header_line: str, x_column: str) -> bool:
    """Shared check for a raw multi-sensor series header whose first column is
    ``x_column`` (``Timestamp`` or ``Turn``): ``<x_column>,Value:1,Value:2,...``
    (extra spaces tolerated)."""
    cleaned = re.sub(r'\s+', '', header_line.strip())
    prefix = x_column + ','
    if not cleaned.startswith(prefix):
        return False
    parts = cleaned.split(',')
    if len(parts) < 2:
        return False
    value_parts = parts[1:]
    return all(part.startswith('Value:') for part in value_parts)


def is_multi_value_timeseries_csv_header(header_line: str) -> bool:
    """
    Checks if the header matches the pattern used for raw multi-sensor/time-series data:
    Timestamp,Value:1,Value:2,Value:3,... (with possible extra spaces)
    """
    return _is_multi_value_series_header(header_line, 'Timestamp')


def is_multi_value_turn_csv_header(header_line: str) -> bool:
    """
    Point-mode Turn variant of the raw multi-sensor series header:
    Turn,Value:1,Value:2,... — the X column is a 1,2,3… turn (measurement)
    index instead of a Timestamp. A Turn file never carries a Timestamp column.
    """
    return _is_multi_value_series_header(header_line, 'Turn')


# ---------------------------------------------------------------------------
# CSV schema constants
# ---------------------------------------------------------------------------
CSV_SCHEMA_TIMESERIES = 'timeseries'            # Timestamp,Value:1[,Value:2,...]
CSV_SCHEMA_TIMESERIES_TURN = 'timeseries_turn'  # Turn,Value:1[,Value:2,...] (point mode)
CSV_SCHEMA_KINETICS_CAL = 'kinetics_cal'   # Concentration,maxRate,Slope,Sat,Time To Sat
CSV_SCHEMA_POINT_CAL = 'point_cal'         # Concentration,Value,TimePoint
CSV_SCHEMA_POINT_CAL_TURN = 'point_cal_turn'  # Concentration,Value (turn-based point cal — each Turn is a standard, no TimePoint)


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
    if is_multi_value_turn_csv_header(header):
        return CSV_SCHEMA_TIMESERIES_TURN
    header_norm = re.sub(r'\s*,\s*', ',', header)
    if header_norm == 'Concentration,maxRate,Slope,Sat,Time To Sat':
        return CSV_SCHEMA_KINETICS_CAL
    if header_norm == 'Concentration,Value,TimePoint':
        return CSV_SCHEMA_POINT_CAL
    if header_norm == 'Concentration,Value':
        return CSV_SCHEMA_POINT_CAL_TURN
    return None


def timeseries_x_column(header_line: str):
    """Return the X-column name of a raw series header — ``'Turn'`` for a Turn
    (point-mode index) file, ``'Timestamp'`` for a time-series file, or ``None``
    when the header is not a raw multi-value series header."""
    if is_multi_value_turn_csv_header(header_line):
        return 'Turn'
    if is_multi_value_timeseries_csv_header(header_line):
        return 'Timestamp'
    return None


# ---------------------------------------------------------------------------
# Concentration unit
# ---------------------------------------------------------------------------
# The unit a Concentration value (the ``# Concentration:`` metadata of a raw
# timeseries file, or the ``Concentration`` column of a calibration file) is
# expressed in. Recorded as a ``# ConcenUnit:`` metadata line. Older files
# predate this line; when it is absent the value is assumed to be ``ng/µL``
# (``DEFAULT_CONCEN_UNIT``). This is a label only — switching units never
# converts the recorded numbers.
CONCEN_UNITS = ['ng/µL', 'nM', '%', 'CFU', 'OD600']
DEFAULT_CONCEN_UNIT = 'ng/µL'


def get_concen_unit(meta: dict) -> str:
    """Return the concentration unit from parsed metadata, defaulting to
    ``DEFAULT_CONCEN_UNIT`` when the ``ConcenUnit`` key is absent or empty."""
    return (meta or {}).get('ConcenUnit') or DEFAULT_CONCEN_UNIT
