import pandas as pd
import os

def get_dynamic_data(file_path, range_value, time_unit):
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        most_recent_time = df['Timestamp'].max()  # In seconds (for reference, not filtering)
        if not df.empty and 'Unit' in df.columns:
            unit = df['Unit'].iloc[0]
        else:
            unit = "NONE"
        return {
            'data': df.to_dict('records'),
            'unit': unit
        }
    return {'data': [], 'error': 'File not found', 'unit': "NONE"}