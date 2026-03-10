import os
import glob
import json
import pandas as pd
import io
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

            with open(file_path, "r") as f:
                lines = f.readlines()

            # Separate metadata and CSV data
            data_lines = []
            for line in lines:
                if line.strip().startswith("#"):
                    if ":" in line:
                        key, value = line[1:].split(":", 1)
                        metadata[key.strip()] = value.strip()
                elif line.strip():
                    data_lines.append(line)

            # Parse the CSV part into a DataFrame
            if data_lines:
                df = pd.read_csv(io.StringIO("".join(data_lines)))
                df = df.fillna("NONE")
                data = df.to_dict('records')
            else:
                data = []

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
                'num_sources': len([col for col in df.columns if col.startswith('Value:')]) if 'Value:' in ''.join(df.columns) else 1
            }

        elif file_path.lower().endswith('.json'):
            with open(file_path, 'r') as f:
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
    if isinstance(obj, MutableMapping):               # dict-like
        return {k: replace_empty(v) for k, v in obj.items()}
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return [replace_empty(v) for v in obj]        # list / tuple / etc.
    else:
        # leaf value
        if obj in ('', [], {}, None):
            return "NONE"
        return obj

def merge_csv_files(file1_path, file2_path, output_path):
    """
    Merge two CSV files based on Timestamp or Concentration.
    Handles measured data (Value:n) and calibration data.
    """
    def parse_csv_with_metadata(path):
        metadata = []
        data_lines = []
        if not os.path.exists(path):
            return None, None
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('#'):
                    metadata.append(line.strip())
                elif line.strip():
                    data_lines.append(line)
        if not data_lines:
            return metadata, pd.DataFrame()
        df = pd.read_csv(io.StringIO("".join(data_lines)))
        return metadata, df

    meta1, df1 = parse_csv_with_metadata(file1_path)
    meta2, df2 = parse_csv_with_metadata(file2_path)

    if df1 is None or df2 is None:
        return False, "One or both files not found"

    # Identify key column
    if 'Timestamp' in df1.columns and 'Timestamp' in df2.columns:
        join_key = 'Timestamp'
    elif 'Concentration' in df1.columns and 'Concentration' in df2.columns:
        join_key = 'Concentration'
    else:
        return False, "Could not find common key column (Timestamp or Concentration)"

    # Merge logic based on the detected key
    if join_key == 'Timestamp':
        # Measured data: Rename Value:x columns and perform outer join
        df1_value_cols = [c for c in df1.columns if c.startswith('Value:')]
        df2_value_cols = [c for c in df2.columns if c.startswith('Value:')]
        
        n = len(df1_value_cols)
        rename_map = {}
        for i, col in enumerate(df2_value_cols, 1):
            rename_map[col] = f"Value:{n + i}"
        df2 = df2.rename(columns=rename_map)
        
        merged_df = pd.merge(df1, df2, on='Timestamp', how='outer')
    else:
        # Calibration data: Concatenate rows to maintain format
        merged_df = pd.concat([df1, df2], ignore_index=True)

    merged_df = merged_df.sort_values(by=join_key)
    merged_df = merged_df.fillna("NONE")

    # Combine metadata (unique lines)
    combined_meta = list(dict.fromkeys(meta1 + meta2))

    # Write to file
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        for line in combined_meta:
            f.write(f"{line}\n")
        merged_df.to_csv(f, index=False)

    return True, os.path.basename(output_path)