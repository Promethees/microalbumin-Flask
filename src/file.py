import os
import glob
import json
import csv
from collections.abc import MutableMapping, Sequence

from file_path import parse_csv_metadata

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
                'num_sources': num_sources
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
