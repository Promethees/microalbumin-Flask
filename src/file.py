import os
import glob
import os 
import json
import pandas as pd
import io

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
                'metadata': metadata
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