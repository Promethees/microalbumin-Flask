import os
import re
import json

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


def _is_multi_value_series_header(header_line: str, x_column: str) -> bool:
    """Shared check for a raw multi-sensor series header whose first column is
    ``x_column`` (``Timestamp`` or ``Turn``): ``<x_column>,Value:1,Value:2,...``
    (extra spaces tolerated)."""
    cleaned = re.sub(r'\s+', '', header_line.strip())
    if not cleaned.startswith(x_column + ','):
        return False
    parts = cleaned.split(',')
    return len(parts) >= 2 and all(p.startswith('Value:') for p in parts[1:])


def _is_timeseries_header(header_line: str) -> bool:
    return _is_multi_value_series_header(header_line, 'Timestamp')


def _is_turn_series_header(header_line: str) -> bool:
    """Point-mode Turn variant of the raw multi-sensor series header:
    ``Turn,Value:1,Value:2,...`` — the X column is a 1,2,3… turn (measurement)
    index instead of a Timestamp. A Turn file never carries a Timestamp column."""
    return _is_multi_value_series_header(header_line, 'Turn')


def detect_csv_schema(header_line: str):
    """
    Identify the CSV schema from the header line.
    Returns one of the ``CSV_SCHEMA_*`` constants, or ``None`` for an
    unrecognised header.
    """
    header = header_line.strip()
    if _is_timeseries_header(header):
        return CSV_SCHEMA_TIMESERIES
    if _is_turn_series_header(header):
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
    if _is_turn_series_header(header_line):
        return 'Turn'
    if _is_timeseries_header(header_line):
        return 'Timestamp'
    return None


# ---------------------------------------------------------------------------
# Concentration unit + CSV↔JSON identity
# ---------------------------------------------------------------------------
# The unit a Concentration value (the ``# Concentration:`` metadata of a raw
# timeseries file, or the ``Concentration`` column of a calibration file) is
# expressed in, recorded as a ``# ConcenUnit:`` line. One of three values; a
# label only (switching units never converts the recorded numbers). Older files
# predate the line — when absent the value is assumed ``ng/µL``.
CONCEN_UNITS = ['ng/µL', 'nM', '%']
DEFAULT_CONCEN_UNIT = 'ng/µL'


def get_concen_unit(meta: dict) -> str:
    """Concentration unit from parsed metadata, defaulting to ng/µL when the
    ``ConcenUnit`` key is absent or empty."""
    return (meta or {}).get('ConcenUnit') or DEFAULT_CONCEN_UNIT


def _norm_identity_value(v):
    """Normalize an identity value: blank or the ``NONE`` placeholder → ``None``
    (a wildcard when matching); otherwise the stripped string."""
    if v is None:
        return None
    s = str(v).strip()
    if s == '' or s.upper() == 'NONE':
        return None
    return s


def build_csv_identity_from_store(csv_dict) -> dict:
    """Identity of each in-memory CSV → ``{name: {measurement, unit, concen_unit}}``.

    ``csv_dict`` is the per-user ``user_data['csv']`` map (``{name: content}``).
    ``unit`` is the absorbance/measurement unit — ``# Unit`` for a raw timeseries
    file, ``# MeasUnit`` for a calibration file (mirrors the JS ``getMetaUnit``);
    ``concen_unit`` defaults ng/µL. measurement/unit ``NONE``/blank → wildcard.
    ``axis`` is the X axis of a raw measurement file (``'turn'``/``'time'``); it
    gates point-mode pairing against a calibration curve of the same kind. A
    calibration CSV is not a raw series → ``None`` (a wildcard).
    """
    identity = {}
    for name, content in (csv_dict or {}).items():
        info = {'measurement': None, 'unit': None, 'concen_unit': DEFAULT_CONCEN_UNIT,
                'axis': None}
        try:
            lines = (content or '').splitlines()
            meta = parse_csv_metadata(lines)
            info['measurement'] = _norm_identity_value(meta.get('Measurement'))
            header = next((l for l in lines if l.strip() and not l.strip().startswith('#')), '')
            schema = detect_csv_schema(header)
            unit = meta.get('Unit') if schema in (CSV_SCHEMA_TIMESERIES, CSV_SCHEMA_TIMESERIES_TURN) else meta.get('MeasUnit')
            info['unit'] = _norm_identity_value(unit if unit is not None else (meta.get('Unit') or meta.get('MeasUnit')))
            info['concen_unit'] = get_concen_unit(meta)
            if schema == CSV_SCHEMA_TIMESERIES_TURN:
                info['axis'] = 'turn'
            elif schema == CSV_SCHEMA_TIMESERIES:
                info['axis'] = 'time'
        except Exception:
            pass
        identity[name] = info
    return identity


def build_json_identity_from_store(json_dict) -> dict:
    """Identity of each in-memory calibration JSON → ``{name: {measurement, unit,
    concen_unit}}`` from its ``for_meas`` / ``meas_unit`` / ``concen_unit`` keys.

    ``json_dict`` is ``user_data['json'][mode]`` (``{name: json_str}``). A field
    absent from a legacy JSON → ``None`` (wildcard) except ``concen_unit`` which
    defaults ng/µL. ``*.meta.json`` sidecars are skipped.

    ``axis``: ``'turn'`` for a turn-based point curve (it records ``x_axis:
    'turn'``), ``'time'`` for a time-based point curve (it carries
    ``time``/``time-unit``), ``None`` for kinetics or legacy JSONs (a wildcard).
    """
    identity = {}
    for name, content in (json_dict or {}).items():
        if str(name).lower().endswith('.meta.json'):
            continue
        info = {'measurement': None, 'unit': None, 'concen_unit': DEFAULT_CONCEN_UNIT,
                'axis': None}
        try:
            obj = json.loads(content) if isinstance(content, str) else content
            if isinstance(obj, dict):
                info['measurement'] = _norm_identity_value(obj.get('for_meas'))
                info['unit'] = _norm_identity_value(obj.get('meas_unit'))
                cu = obj.get('concen_unit')
                info['concen_unit'] = cu if (cu and str(cu).strip()) else DEFAULT_CONCEN_UNIT
                if obj.get('x_axis') == 'turn':
                    info['axis'] = 'turn'
                elif 'time-unit' in obj or 'time' in obj:
                    info['axis'] = 'time'
        except Exception:
            pass
        identity[name] = info
    return identity