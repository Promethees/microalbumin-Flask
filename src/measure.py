import pandas as pd
import os
import csv

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

def sort_csv_file(file_path, meas_mode):
    """
    Sorts the data in the CSV file based on concentration and time_point (for point mode)
    while maintaining the original column order.
    
    Args:
        file_path (str): Path to the CSV file
        meas_mode (str): Either "kinetics" or "point" mode
    """
    try:
        # Read all data from the file
        with open(file_path, 'r', newline='') as f:
            reader = csv.reader(f)
            headers = next(reader)  # Read header row
            rows = list(reader)
        
        # Determine sort keys based on measurement mode
        if meas_mode == "kinetics":
            print("Sorting in kinetics mode")
            # Sort by concentration (index 1), vmax (index 2), slope (index 3), sat (index 4), time_to_sat (index 5), blank type (index 8)
            sorted_rows = sorted(rows, key=lambda x: (float(x[1]), float(x[2]), float(x[3]), x[4], x[5], x[8]))
            # sorted_rows = sorted(rows, key=lambda x: (x[1]))
        elif meas_mode == "point":
            # Sort by concentration (index 1), time_point (index 4), and blank type (index 6)
            sorted_rows = sorted(rows, key=lambda x: (float(x[1]), float(x[4]), x[6]))
        else:
            # Sort by timestamp (index 0) and blank type (index 5)
            sorted_rows = sorted(rows, key=lambda x: (float(x[0]), x[5]))

        # Write sorted data back to file
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(sorted_rows)

        f.close()
            
    except Exception as e:
        print(f"Error sorting CSV file: {str(e)}")
        raise