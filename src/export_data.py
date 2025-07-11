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