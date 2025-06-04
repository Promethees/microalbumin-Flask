import pandas as pd
import os

def get_dynamic_data(file_path, range_value, time_unit):
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        most_recent_time = df['Timestamp'].max()
        multiplier = {'seconds': 1, 'minutes': 60, 'hours': 3600, 'milli-sec': 0.001}.get(time_unit, 1)
        time_threshold = most_recent_time - (int(range_value) * multiplier)
        filtered_df = df[df['Timestamp'] >= time_threshold]
        # units = df['Unit'].iloc[0] if not filtered_df.empty and 'Unit' in df.columns else "None"
        if not filtered_df.empty and 'Unit' in df.columns:
            unit = df['Unit'].iloc[0]
        else:
            unit = "NONE"
        return {
            'data': filtered_df.to_dict('records'),
            'unit': unit
        }
    return {'data': [], 'error': 'File not found', 'unit': "None"}
