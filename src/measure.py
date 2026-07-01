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
            # Sort by concentration (index 0), maxrate (index 1), slope (index 2), sat (index 3), time_to_sat (index 4)
            sorted_rows = sorted(rows, key=lambda x: (_safe_float(x[0]), _safe_float(x[1]), _safe_float(x[2]), _safe_float(x[3]), _safe_float(x[4])))
        elif meas_mode == "point":
            # Sort by concentration (index 0), time_point (index 2), value (index 1)
            sorted_rows = sorted(rows, key=lambda x: (_safe_float(x[0]), _safe_float(x[2]), _safe_float(x[1])))
        else:
            sorted_rows = sorted(rows, key=lambda x: _safe_float(x[0]))

        # Write sorted data back to file
        with open(file_path, 'w', newline='') as f:
            for line in metadata_lines:
                f.write(line if line.endswith("\n") else line + "\n")
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(sorted_rows)

    except Exception as e:
        print(f"Error sorting CSV file: {str(e)}")
        raise

def _safe_float(val, default=0.0):
    """Convert to float, return default if impossible (e.g. empty string or non-numeric text)."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default