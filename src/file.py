import os
import glob
import json
import csv
from collections import MutableMapping, Sequence

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
    
def get_dynamic_data(file_path):
    if not os.path.exists(file_path):
        return {'data': [], 'error': 'File not found', 'unit': "NONE"}

    try:
        if file_path.lower().endswith('.csv'):
            metadata = {}
            data = []

            def valid_data_lines(file_obj):
                for line in file_obj:
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        if ":" in line:
                            parts = line[1:].split(":", 1)
                            if len(parts) == 2:
                                key, value = parts
                                metadata[key.strip()] = value.strip()
                    elif stripped:
                        yield line

            with open(file_path, "r", encoding='utf-8') as f:
                line_generator = valid_data_lines(f)
                try:
                    raw_headers_line = next(line_generator)
                    raw_headers = next(csv.reader([raw_headers_line]))
                    headers = [h.strip() for h in raw_headers]

                    reader = csv.DictReader(line_generator, fieldnames=headers)
                    data = []
                    for row in reader:
                        cleaned_row = {k: (v if v is not None and v != "" else "NONE") for k, v in row.items()}
                        data.append(cleaned_row)
                    num_sources = sum(1 for h in headers if h.startswith('Value:'))
                except StopIteration:
                    data = []
                    num_sources = 1

            # Unit resolution priority: check metadata keys
            unit = "NONE"
            for possible_name in ['Unit', 'MeasUnit']:
                if possible_name in metadata:
                    unit = metadata[possible_name]
                    break

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
            
            # Attempt to find a unit field in JSON data
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
    def parse_csv_with_metadata(path):
        metadata = []
        if not os.path.exists(path):
            return None, None

        def iter_data_lines(f):
            for line in f:
                if line.strip().startswith('#'):
                    metadata.append(line.strip())
                elif line.strip():
                    yield line

        with open(path, 'r', encoding='utf-8') as f:
            line_generator = iter_data_lines(f)
            try:
                raw_headers_line = next(line_generator)
                raw_headers = next(csv.reader([raw_headers_line]))
                headers = [h.strip() for h in raw_headers]
                data = list(csv.DictReader(line_generator, fieldnames=headers))
            except StopIteration:
                data = []

        return metadata, data

    parsed = [parse_csv_with_metadata(p) for p in file_paths]

    if any(meta is None for meta, _ in parsed):
        return False, "One or more files not found"

    if all(not rows for _, rows in parsed):
        return False, "All files are empty"

    all_headers = [list(rows[0].keys()) if rows else [] for _, rows in parsed]

    if all('Timestamp' in h for h in all_headers):
        join_key = 'Timestamp'
    elif all('Concentration' in h for h in all_headers):
        join_key = 'Concentration'
    else:
        return False, "Could not find common key column (Timestamp or Concentration)"

    if join_key == 'Timestamp':
        combined = {}
        value_offset = 0

        for _, rows in parsed:
            if not rows:
                continue
            headers = list(rows[0].keys())
            value_cols = [c for c in headers if c.startswith('Value:')]

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
        for _, rows in parsed:
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
    for meta, _ in parsed:
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