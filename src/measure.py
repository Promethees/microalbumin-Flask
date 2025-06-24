import pandas as pd
import os

def get_dynamic_data(file_path):
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)

        # Determine which column to use for the unit
        unit_column = None
        for possible_name in ['Unit', 'MeasUnit']:
            if possible_name in df.columns:
                unit_column = possible_name
                break

        unit = df[unit_column].iloc[0] if unit_column and not df.empty else "NONE"

        return {
            'data': df.to_dict('records'),
            'unit': unit
        }

    return {'data': [], 'error': 'File not found', 'unit': "NONE"}
