import os
import glob
import json
import csv
from datetime import datetime
from collections.abc import MutableMapping, Sequence

from file_path import (parse_csv_metadata, detect_csv_schema,
                       get_concen_unit, DEFAULT_CONCEN_UNIT,
                       CSV_SCHEMA_TIMESERIES, timeseries_x_column)

VALID_SORT_ORDERS = {"name_asc", "name_desc", "date_asc", "date_desc"}

# Friendly time-tag format keys -> strftime patterns. The key is what is stored in
# user_settings ("time_tag_format"); "iso" is the default. Keep this in lockstep
# with user_settings._VALID_TIME_TAG_FORMATS and the settings-modal dropdown.
TIME_TAG_FORMATS = {
    "iso": "%Y-%m-%d %H:%M",
    "iso_sec": "%Y-%m-%d %H:%M:%S",
    "us": "%m/%d/%Y %I:%M %p",
    "eu": "%d/%m/%Y %H:%M",
    "date_only": "%Y-%m-%d",
}


def get_file_list(directory, fileType="*.csv"):
    try:
        print(f"Scanning directory: {directory}")
        files = glob.glob(os.path.join(directory, fileType))
        file_names = [os.path.basename(f) for f in files if not os.path.basename(f).startswith('.')]
        # Sort files alphabetically, case-insensitive
        file_names.sort(key=str.lower, reverse=True)
        print(f"Files found in {directory}: {file_names}")
        return file_names
    except Exception as e:
        print(f"Error listing files in {directory}: {e}")
        return []


def ensure_concen_unit_in_dir(directory, default=DEFAULT_CONCEN_UNIT):
    """Backfill a ``# ConcenUnit:`` metadata line into legacy CSV data files.

    Older files predate the concentration-unit feature and have no
    ``# ConcenUnit`` line; when one is absent the value is assumed to be the
    documented default (``ng/µL``). This materializes that assumption onto disk
    for every recognized CSV in ``directory`` (raw timeseries or calibration)
    that lacks the line, so the unit travels with the file. It runs as a data
    folder is selected (the ``/browse`` route).

    Idempotent and best-effort: files that already carry ``ConcenUnit`` or whose
    header is not a recognized schema are left untouched, and a failure on one
    file never aborts the pass. Always writes ``default`` (never a user-preferred
    unit) so it can never mislabel existing data. Returns the number of files
    migrated.
    """
    migrated = 0
    try:
        paths = glob.glob(os.path.join(directory, "*.csv"))
    except Exception as e:
        print(f"ensure_concen_unit_in_dir: cannot scan {directory}: {e}")
        return 0

    for path in paths:
        if os.path.basename(path).startswith('.'):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            meta = parse_csv_metadata(lines)
            if 'ConcenUnit' in meta:
                continue  # already has it — nothing to do

            # Locate the data header: the first non-empty, non-metadata line.
            header_idx = None
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith('#'):
                    continue
                header_idx = i
                break
            if header_idx is None:
                continue  # no data header — not a data file we recognize

            if detect_csv_schema(lines[header_idx]) is None:
                continue  # unrecognized schema — don't touch it

            # Insert the line just before the data header, preserving the line
            # ending style already used in the file's metadata block.
            newline = '\n'
            if header_idx > 0 and lines[header_idx - 1].endswith('\r\n'):
                newline = '\r\n'
            lines.insert(header_idx, f"# ConcenUnit: {default}{newline}")

            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            migrated += 1
        except Exception as e:
            print(f"ensure_concen_unit_in_dir: skipped {path}: {e}")
            continue

    return migrated


# Placeholder written for an unknown measurement unit — the codebase's convention
# (mirrors export_data's measUnit default). Normalized back to a wildcard (None) when
# matching, so a back-filled legacy calibration JSON still pairs with any unit.
DEFAULT_MEAS_UNIT = "NONE"


def _norm_identity_value(v):
    """Normalize an identity value: blank or the ``NONE`` placeholder → ``None``
    (a wildcard when matching); otherwise the stripped string."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.upper() == "NONE":
        return None
    return s


def ensure_cal_units_in_dir(directory, default_meas_unit=DEFAULT_MEAS_UNIT,
                            default_concen_unit=DEFAULT_CONCEN_UNIT):
    """Back-fill missing identity units into legacy calibration JSONs on disk.

    A calibration JSON predating the identity feature lacks ``meas_unit`` /
    ``concen_unit``. This writes the defaults for every non-meta JSON in
    ``directory`` missing either key (``meas_unit`` → ``"NONE"``, a wildcard when
    matching; ``concen_unit`` → ``ng/µL``), mirroring ``ensure_concen_unit_in_dir``
    for CSVs. Runs as the calibration list is fetched (``/get_json_cal``).
    Idempotent and best-effort. Returns the number of files migrated.
    """
    migrated = 0
    try:
        paths = glob.glob(os.path.join(directory, "*.json"))
    except Exception as e:
        print(f"ensure_cal_units_in_dir: cannot scan {directory}: {e}")
        return 0

    for path in paths:
        name = os.path.basename(path)
        if name.startswith('.') or name.lower().endswith('.meta.json'):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = json.load(f)
            if not isinstance(content, dict):
                continue
            changed = False
            if "meas_unit" not in content:
                content["meas_unit"] = default_meas_unit
                changed = True
            if "concen_unit" not in content:
                content["concen_unit"] = default_concen_unit
                changed = True
            if changed:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(content, f, indent=4)
                migrated += 1
        except Exception as e:
            print(f"ensure_cal_units_in_dir: skipped {path}: {e}")
            continue

    return migrated


def build_csv_identity(directory, names):
    """Return the matching identity of each CSV in ``names`` under ``directory``.

    Shape: ``{name: {"measurement": str|None, "unit": str|None, "concen_unit": str}}``.
    ``unit`` is the absorbance/measurement unit — ``# Unit`` for a raw timeseries file,
    ``# MeasUnit`` for a calibration file (mirrors the JS ``getMetaUnit``); ``concen_unit``
    defaults to ``ng/µL`` when absent (see ``get_concen_unit``). Used by the File Selection
    table to show each file's identity badge and to gate CSV↔JSON pairing. Best-effort: a
    file that cannot be read yields an all-unknown identity (never raises).
    """
    identity = {}
    for name in names:
        info = {"measurement": None, "unit": None, "concen_unit": DEFAULT_CONCEN_UNIT}
        try:
            path = os.path.join(directory, name)
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            meta = parse_csv_metadata(lines)
            info["measurement"] = _norm_identity_value(meta.get("Measurement"))
            header = next((l for l in lines
                           if l.strip() and not l.strip().startswith('#')), "")
            schema = detect_csv_schema(header)
            # Timeseries uses `# Unit`; calibration files use `# MeasUnit`.
            unit = meta.get("Unit") if schema == CSV_SCHEMA_TIMESERIES else meta.get("MeasUnit")
            info["unit"] = _norm_identity_value(unit if unit is not None else (meta.get("Unit") or meta.get("MeasUnit")))
            info["concen_unit"] = get_concen_unit(meta)
        except Exception as e:
            print(f"build_csv_identity: skipped {name}: {e}")
        identity[name] = info
    return identity


def build_json_identity(directory, names):
    """Return the matching identity of each calibration JSON in ``names``.

    Shape: ``{name: {"measurement": str|None, "unit": str|None, "concen_unit": str}}``
    read from the JSON's ``for_meas`` / ``meas_unit`` / ``concen_unit`` keys. A field
    absent from a legacy JSON stays ``None`` (treated as a wildcard when matching),
    except ``concen_unit`` which defaults to ``ng/µL``. ``*.meta.json`` sidecars are
    skipped. Best-effort: unreadable/invalid JSON yields an all-unknown identity.
    """
    identity = {}
    for name in names:
        if name.lower().endswith(".meta.json"):
            continue
        info = {"measurement": None, "unit": None, "concen_unit": DEFAULT_CONCEN_UNIT}
        try:
            with open(os.path.join(directory, name), "r", encoding="utf-8") as f:
                content = json.load(f)
            if isinstance(content, dict):
                info["measurement"] = _norm_identity_value(content.get("for_meas"))
                info["unit"] = _norm_identity_value(content.get("meas_unit"))
                cu = content.get("concen_unit")
                info["concen_unit"] = cu if (cu and str(cu).strip()) else DEFAULT_CONCEN_UNIT
        except Exception as e:
            print(f"build_json_identity: skipped {name}: {e}")
        identity[name] = info
    return identity


def build_meta(directory, names, time_format="iso"):
    """Return modified-date metadata for the given ``names`` under ``directory``.

    The shape is ``{name: {"mtime": <epoch float>, "display": <formatted time tag>}}``.
    Works for both files and directories (report subject folders). ``mtime`` is the
    raw modified time used for client-side date sorting; ``display`` is the
    human-readable time tag rendered with the ``time_format`` key (see
    ``TIME_TAG_FORMATS``; falls back to ``iso``). Entries that cannot be stat-ed
    fall back to ``mtime`` 0 and an empty display string.
    """
    pattern = TIME_TAG_FORMATS.get(time_format, TIME_TAG_FORMATS["iso"])
    meta = {}
    for name in names:
        try:
            mtime = os.path.getmtime(os.path.join(directory, name))
            display = datetime.fromtimestamp(mtime).strftime(pattern)
        except OSError:
            mtime, display = 0, ""
        meta[name] = {"mtime": mtime, "display": display}
    return meta


def get_file_meta(directory, fileType="*.csv", time_format="iso"):
    """Return per-file modified-date metadata for a directory keyed by file name.

    Globs ``directory`` for ``fileType`` (skipping dotfiles) and delegates to
    ``build_meta``. See ``build_meta`` for the returned shape.
    """
    try:
        files = glob.glob(os.path.join(directory, fileType))
        names = [os.path.basename(f) for f in files if not os.path.basename(f).startswith('.')]
    except Exception as e:
        print(f"Error reading file metadata in {directory}: {e}")
        return {}
    return build_meta(directory, names, time_format)


def sort_file_names(names, meta, order="date_desc"):
    """Return ``names`` ordered by the requested sort order.

    ``order`` is one of ``name_asc`` / ``name_desc`` / ``date_asc`` / ``date_desc``.
    Date sorting uses the ``mtime`` from ``meta`` (missing entries sort as oldest).
    Falls back to ``date_desc`` for an unrecognised order.
    """
    if order not in VALID_SORT_ORDERS:
        order = "date_desc"
    reverse = order.endswith("_desc")
    if order.startswith("date"):
        return sorted(names, key=lambda n: meta.get(n, {}).get("mtime", 0), reverse=reverse)
    return sorted(names, key=str.lower, reverse=reverse)


def _read_csv_raw(path):
    """
    Read a CSV file, separating raw metadata lines from data rows.
    Returns (meta_lines, headers, rows) where:
      - meta_lines: list of stripped raw '# ...' strings
      - headers:    list of column name strings (empty list if no data)
      - rows:       list of dicts from csv.DictReader
    Returns (None, None, None) if the file does not exist.
    """
    if not os.path.exists(path):
        return None, None, None
    with open(path, 'r', encoding='utf-8') as f:
        all_lines = f.readlines()
    meta_lines = [line.strip() for line in all_lines if line.strip().startswith('#')]
    data_lines = [line for line in all_lines if line.strip() and not line.strip().startswith('#')]
    if not data_lines:
        return meta_lines, [], []
    headers = [h.strip() for h in next(csv.reader([data_lines[0]]))]
    rows = list(csv.DictReader(iter(data_lines[1:]), fieldnames=headers))
    return meta_lines, headers, rows


def get_dynamic_data(file_path):
    if not os.path.exists(file_path):
        return {'data': [], 'error': 'File not found', 'unit': "NONE"}

    try:
        if file_path.lower().endswith('.csv'):
            meta_lines, headers, rows = _read_csv_raw(file_path)
            metadata = parse_csv_metadata(meta_lines)

            # Point-mode Turn files carry a "Turn" X column (1,2,3…) instead of
            # "Timestamp". Rather than teach the whole timeseries pipeline (plot,
            # value-at-point, reports — all keyed on "Timestamp") a second X name,
            # rename the key to "Timestamp" on read and flag x_axis="turn" so the
            # client relabels the axis / reference input. On disk the file keeps
            # its "Turn" header (a Turn file never has a Timestamp column).
            x_axis = 'time'
            if headers and timeseries_x_column(",".join(headers)) == 'Turn':
                x_axis = 'turn'
                rows = [
                    {('Timestamp' if k == 'Turn' else k): v for k, v in row.items()}
                    for row in rows
                ]

            if headers:
                data = [
                    {k: (v if v is not None and v != "" else "NONE") for k, v in row.items()}
                    for row in rows
                ]
                num_sources = sum(1 for h in headers if h.startswith('Value:'))
            else:
                data = []
                num_sources = 1

            unit = next((metadata[n] for n in ('Unit', 'MeasUnit') if n in metadata), "NONE")
            return {
                'data': data,
                'unit': unit,
                'error': None,
                'metadata': metadata,
                'num_sources': num_sources,
                'x_axis': x_axis
            }

        elif file_path.lower().endswith('.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            data = json_data if isinstance(json_data, list) else [json_data]

            unit = "NONE"
            if data and isinstance(data[0], dict):
                for possible_name in ['Unit', 'MeasUnit', 'unit', 'measUnit']:
                    if possible_name in data[0]:
                        unit = data[0][possible_name]
                        break

            return {
                'data': data,
                'unit': unit,
                'error': None
            }
        else:
            return {'data': [], 'error': 'Unsupported file type', 'unit': "NONE"}

    except json.JSONDecodeError as e:
        return {'data': [], 'error': f'Invalid JSON format: {str(e)}', 'unit': "NONE"}
    except Exception as e:
        return {'data': [], 'error': f'Error processing file: {str(e)}', 'unit': "NONE"}


def replace_empty(obj):
    """
    Recursively replace empty values with "NONE".
    Empty means:
        - ''  (empty string)
        - []  (empty list)
        - {}  (empty dict)
        - None
    """
    if obj in ('', [], {}, None):
        return "NONE"

    if isinstance(obj, MutableMapping):               # dict-like
        return {k: replace_empty(v) for k, v in obj.items()}
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return [replace_empty(v) for v in obj]        # list / tuple / etc.
    else:
        return obj


def merge_csv_files(file_paths, output_path):
    """
    Merge multiple CSV files based on Timestamp or Concentration.
    Handles measured data (Value:n) and calibration data.
    """
    parsed = [_read_csv_raw(p) for p in file_paths]

    if any(meta is None for meta, _, _ in parsed):
        return False, "One or more files not found"

    if all(not rows for _, _, rows in parsed):
        return False, "All files are empty"

    for i, (_, hdrs, rows) in enumerate(parsed):
        if hdrs and not rows:
            return False, f"File '{os.path.basename(file_paths[i])}' has no data rows"

    all_headers = [hdrs for _, hdrs, _ in parsed]

    if all('Timestamp' in h for h in all_headers):
        join_key = 'Timestamp'
    elif all('Concentration' in h for h in all_headers):
        join_key = 'Concentration'
    else:
        return False, "Could not find common key column (Timestamp or Concentration)"

    if join_key == 'Timestamp':
        combined = {}
        value_offset = 0

        for _, hdrs, rows in parsed:
            if not rows:
                continue
            value_cols = [c for c in hdrs if c.startswith('Value:')]

            for r in rows:
                key = r[join_key]
                if key not in combined:
                    combined[key] = {join_key: key}
                for i, col in enumerate(value_cols, 1):
                    combined[key][f"Value:{value_offset + i}"] = r.get(col, "NONE")

            value_offset += len(value_cols)

        merged_rows = list(combined.values())
        new_headers = [join_key] + [f"Value:{i + 1}" for i in range(value_offset)]
    else:
        # Calibration data: concatenate rows, union headers
        merged_rows = []
        seen = {}
        for h_list in all_headers:
            for h in h_list:
                if h not in seen:
                    seen[h] = True
        new_headers = list(seen.keys())
        for _, _, rows in parsed:
            merged_rows.extend(rows)

    def _safe_float(val):
        try:
            return float(val)
        except (ValueError, TypeError):
            return val

    merged_rows.sort(key=lambda x: _safe_float(x.get(join_key, "")))

    for row in merged_rows:
        for h in new_headers:
            if h not in row or row[h] == "" or row[h] is None:
                row[h] = "NONE"

    combined_meta = []
    for meta, _, _ in parsed:
        for line in meta:
            if line not in combined_meta:
                combined_meta.append(line)

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        for line in combined_meta:
            f.write(f"{line}\n")
        writer = csv.DictWriter(f, fieldnames=new_headers)
        writer.writeheader()
        writer.writerows(merged_rows)

    return True, os.path.basename(output_path)
