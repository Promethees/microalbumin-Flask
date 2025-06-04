import pandas as pd
import os

def get_dynamic_data(selected_file, range_value, time_unit):
    if not selected_file or not os.path.exists(selected_file):
        return {'data': [], 'error': 'No file selected or file does not exist'}
    
    try:
        df = pd.read_csv(selected_file)
        # Simulate dynamic data by taking the last N rows based on range
        range_value = int(range_value) if range_value else 100
        data = df.tail(range_value).to_dict(orient='records')
        
        # Adjust data based on time unit (simplified)
        for row in data:
            if 'time' in row:
                if time_unit == 'ms':
                    row['time'] = row['time'] * 1000
                elif time_unit == 'ps':
                    row['time'] = row['time'] * 1e12
                elif time_unit == 'ns':
                    row['time'] = row['time'] * 1e9
                elif time_unit == 'µs':
                    row['time'] = row['time'] * 1e6
        return {'data': data}
    except Exception as e:
        return {'data': [], 'error': str(e)}