import csv

def check_row_exist(full_path, concentration, blankT, timePoint=None, measMode="kinetics"):
    try:
        with open(full_path, mode='r', newline='') as f:
            reader = csv.reader(f)
            # Assuming column indices based on headers
            con_col = 1  # Concentration
            blankT_col_kin = 8  # BlankType for kinetics
            blankT_col_pnt = 6  # BlankType for point
            time_point_col = 4  # TimePoint for point
            for row in reader:
                if measMode == "kinetics":
                    if row[con_col] == concentration and row[blankT_col_kin] == blankT:
                        return True
                elif measMode == "point":
                    if row[con_col] == concentration and row[blankT_col_pnt] == blankT and row[time_point_col] == timePoint:
                        return True
    except FileNotFoundError:
        return False
    return False

def check_metadata_consistency(file_path, measurement, meas_unit, time_unit, meas_mode):
    """
    Check if existing metadata in file matches the given metadata.
    Raises ValueError if mismatch is found.
    """
    with open(file_path, "r") as f:
        for line in f:
            if line.startswith("# Measurement:"):
                existing_measurement = line.strip().split(":", 1)[1].strip()
                if existing_measurement.lower() != measurement.lower():
                    raise ValueError(f"Measurement mismatch: existing '{existing_measurement}' vs new '{measurement}'")
            elif line.startswith("# MeasUnit:"):
                existing_meas_unit = line.strip().split(":", 1)[1].strip()
                if existing_meas_unit.lower() != meas_unit.lower():
                    raise ValueError(f"MeasUnit mismatch: existing '{existing_meas_unit}' vs new '{meas_unit}'")
            elif line.startswith("# TimeUnit:"):
                existing_time_unit = line.strip().split(":", 1)[1].strip()
                if existing_time_unit.lower() != time_unit.lower():
                    raise ValueError(f"TimeUnit mismatch: existing '{existing_time_unit}' vs new '{time_unit}'")
            elif line.startswith("# MeasMode:"):
                existing_meas_mode = line.strip().split(":", 1)[1].strip()
                if existing_meas_mode.lower() != meas_mode.lower():
                    raise ValueError(f"MeasMode mismatch: existing '{existing_meas_mode}' vs new '{meas_mode}'")
            # Stop reading once we leave metadata section
            if not line.startswith("#"):
                break
