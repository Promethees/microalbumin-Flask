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

def merge_csv_files(file1_path, file2_path, output_path):
    """
    Merge two CSV files based on Timestamp or Concentration.
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

    meta1, rows1 = parse_csv_with_metadata(file1_path)
    meta2, rows2 = parse_csv_with_metadata(file2_path)

    if rows1 is None or rows2 is None:
        return False, "One or both files not found"

    if not rows1 and not rows2:
        return False, "Both files are empty"
        
    # Get headers
    headers1 = list(rows1[0].keys()) if rows1 else []
    headers2 = list(rows2[0].keys()) if rows2 else []

    # Identify key column
    if 'Timestamp' in headers1 and 'Timestamp' in headers2:
        join_key = 'Timestamp'
    elif 'Concentration' in headers1 and 'Concentration' in headers2:
        join_key = 'Concentration'
    else:
        return False, "Could not find common key column (Timestamp or Concentration)"

    # Merge logic
    if join_key == 'Timestamp':
        # Measured data
        df1_value_cols = [c for c in headers1 if c.startswith('Value:')]
        df2_value_cols = [c for c in headers2 if c.startswith('Value:')]
        n = len(df1_value_cols)
        
        # Create a combined data structure
        combined = {} # key -> combined_row
        
        for r in rows1:
            combined[r[join_key]] = r.copy()
            
        for r in rows2:
            key = r[join_key]
            if key not in combined:
                combined[key] = {join_key: key}
            
            # Map Value:i in rows2 to Value:n+i
            for i, col in enumerate(df2_value_cols, 1):
                combined[key][f"Value:{n + i}"] = r.get(col, "NONE")

        # Resulting rows
        merged_rows = list(combined.values())
        
        # New headers
        all_val_cols = df1_value_cols + [f"Value:{n + i}" for i in range(1, len(df2_value_cols) + 1)]
        new_headers = [join_key] + all_val_cols
    else:
        # Calibration data: Concatenate
        merged_rows = rows1 + rows2
        new_headers = list(dict.fromkeys(headers1 + headers2))

    # Sort merged rows
    def _safe_float(val):
        try:
            return float(val)
        except (ValueError, TypeError):
            return val # fall back to string comparison if not float

    merged_rows.sort(key=lambda x: _safe_float(x.get(join_key, "")))

    # Fill NONEs for missing keys across all rows
    for row in merged_rows:
        for h in new_headers:
            if h not in row or row[h] == "" or row[h] is None:
                row[h] = "NONE"

    # Combine metadata (unique lines)
    combined_meta = list(dict.fromkeys(meta1 + meta2))

    # Write to file
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        for line in combined_meta:
            f.write(f"{line}\n")
        writer = csv.DictWriter(f, fieldnames=new_headers)
        writer.writeheader()
        writer.writerows(merged_rows)

    return True, os.path.basename(output_path)