import pandas as pd
import csv

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
            all_lines = f.readlines()
        # Separate metadata and data
        metadata_lines = [line for line in all_lines if line.strip().startswith("#")]
        data_lines = [line.strip() for line in all_lines if not line.strip().startswith("#")]

        if not data_lines:
            print("No data lines found, skipping sort.")
            return

        reader = csv.reader(data_lines)
        headers = next(reader)  # First non-metadata line is the header
        rows = list(reader)
        
        # Determine sort keys based on measurement mode
        if meas_mode == "kinetics":
            print("Sorting in kinetics mode")
            # Sort by concentration (index 0), maxrate (index 1), slope (index 2), sat (index 3), time_to_sat (index 4), blank type (index 5)
            sorted_rows = sorted(rows, key=lambda x: (float(x[0]), float(x[1]), float(x[2]), x[3], x[4], x[5]))
            # sorted_rows = sorted(rows, key=lambda x: (x[1]))
        elif meas_mode == "point":
            # Sort by concentration (index 0), time_point (index 2), value (index 1) and blank type (index 3)
            sorted_rows = sorted(rows, key=lambda x: (float(x[0]), float(x[2]), float(x[1]), x[3]))
        else:
            # Sort by timestamp (index 0) and blank type (index 3)
            sorted_rows = sorted(rows, key=lambda x: (float(x[0]), x[3]))

        # Write sorted data back to file
        with open(file_path, 'w', newline='') as f:
            for line in metadata_lines:
                f.write(line if line.endswith("\n") else line + "\n")
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(sorted_rows)

        f.close()
            
    except Exception as e:
        print(f"Error sorting CSV file: {str(e)}")
        raise