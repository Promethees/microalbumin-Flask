from threading import Lock
from collections import defaultdict

from file_path import DEFAULT_CONCEN_UNIT

_user_locks: defaultdict = defaultdict(Lock)

def get_user_lock(uid: str) -> Lock:
    """Return a per-user lock so concurrent exports never block each other."""
    return _user_locks[uid]

# Helper: Parse metadata from content
def parse_metadata(content):
    meta_dict = {}
    for line in content.split('\n'):
        if line.startswith('# '):
            if ':' in line:
                key, val = line[2:].split(':', 1)
                meta_dict[key.strip()] = val.strip()
    return meta_dict

# Helper: Check metadata consistency
def is_metadata_consistent(meta_dict, measurement, meas_unit, time_unit, meas_mode,
                           concen_unit=DEFAULT_CONCEN_UNIT):
    # The target file's concentration unit must match the unit being exported —
    # you cannot append nM rows to a file recorded as ng/µL (or vice versa). A
    # file predating ConcenUnit is treated as the default (ng/µL).
    return (meta_dict.get('Measurement') == measurement and
            meta_dict.get('MeasUnit') == meas_unit and
            meta_dict.get('TimeUnit') == time_unit and
            meta_dict.get('MeasMode') == meas_mode and
            meta_dict.get('ConcenUnit', DEFAULT_CONCEN_UNIT) == concen_unit)

# Helper: Write metadata
def write_metadata(output, measurement, meas_unit, time_unit, meas_mode,
                   concen_unit=DEFAULT_CONCEN_UNIT):
    output.write(f"# Measurement: {measurement}\n")
    output.write(f"# MeasUnit: {meas_unit}\n")
    output.write(f"# TimeUnit: {time_unit}\n")
    output.write(f"# MeasMode: {meas_mode}\n")
    output.write(f"# ConcenUnit: {concen_unit}\n")

# Helper: Write headers
# ``x_axis`` = 'turn' marks a point-mode Turn calibration (each Turn is a
# standard); it drops the TimePoint column — there is no time.
def write_headers(writer, meas_mode, x_axis='time'):
    if meas_mode == "kinetics":
        writer.writerow(['Concentration', 'maxRate', 'Slope', 'Sat', 'Time To Sat'])
    elif x_axis == 'turn':
        writer.writerow(['Concentration', 'Value'])
    else:
        writer.writerow(['Concentration', 'Value', 'TimePoint'])

# Helper: Extract single entry from data
def extract_single_entry(data, meas_mode, x_axis='time'):
    concentration = data.get('con', 'NONE')
    if meas_mode == "kinetics":
        return [
            concentration,
            data.get('maxrate', 'NONE'),
            data.get('slope', 'NONE'),
            data.get('sat', 'NONE'),
            data.get('timeSat', 'NONE')
        ]
    elif x_axis == 'turn':
        return [
            concentration,
            data.get('estValue', 'NONE')
        ]
    else:
        return [
            concentration,
            data.get('estValue', 'NONE'),
            data.get('timePoint', 'NONE')
        ]

# Helper: Sort CSV content by Concentration
def sort_csv_content(content):
    lines = content.split('\n')
    metadata = [l for l in lines if l.startswith('#')]
    data_lines = [l for l in lines if not l.startswith('#') and l.strip()]
    if not data_lines:
        return content
    header = data_lines[0]
    rows = data_lines[1:]
    parsed_rows = [r.split(',') for r in rows if r]
    parsed_rows.sort(key=lambda row: float(row[0]) if row[0] != 'NONE' else float('inf'))
    new_rows = [','.join(r) for r in parsed_rows]
    return '\n'.join(metadata + [header] + new_rows) + '\n'