import csv
import io

from file_path import DEFAULT_CONCEN_UNIT

# Helper: Check metadata consistency
def is_metadata_consistent(meta_dict, measurement, meas_unit, time_unit, meas_mode,
                           concen_unit=DEFAULT_CONCEN_UNIT):
    # The target file's concentration unit must match the unit being exported —
    # you cannot append nM rows to a file recorded as ng/µL (or vice versa). A
    # file predating ConcenUnit is treated as the default (ng/µL), so only a
    # matching-default export may be appended to it.
    return not metadata_mismatches(meta_dict, measurement, meas_unit, time_unit,
                                   meas_mode, concen_unit)


def metadata_mismatches(meta_dict, measurement, meas_unit, time_unit, meas_mode,
                        concen_unit=DEFAULT_CONCEN_UNIT):
    """Return the list of metadata fields that differ between the target file and
    the export, as ``(label, existing, incoming)`` tuples. Empty when the file is
    a valid append target. Used both for the boolean consistency check above and
    to build a human-readable explanation of *what* clashed."""
    checks = [
        ('Measurement', meta_dict.get('Measurement'), measurement),
        ('MeasUnit', meta_dict.get('MeasUnit'), meas_unit),
        ('TimeUnit', meta_dict.get('TimeUnit'), time_unit),
        ('MeasMode', meta_dict.get('MeasMode'), meas_mode),
        # A file predating ConcenUnit is treated as the default (ng/µL).
        ('ConcenUnit', meta_dict.get('ConcenUnit', DEFAULT_CONCEN_UNIT), concen_unit),
    ]
    return [(label, existing, incoming)
            for label, existing, incoming in checks if existing != incoming]

# Helper: Write metadata
def write_metadata(output, measurement, meas_unit, time_unit, meas_mode,
                   concen_unit=DEFAULT_CONCEN_UNIT):
    output.write(f"# Measurement: {measurement}\n")
    output.write(f"# MeasUnit: {meas_unit}\n")
    output.write(f"# TimeUnit: {time_unit}\n")
    output.write(f"# MeasMode: {meas_mode}\n")
    output.write(f"# ConcenUnit: {concen_unit}\n")

# Helper: Write headers
def write_headers(writer, meas_mode):
    if meas_mode == "kinetics":
        writer.writerow(['Concentration', 'maxRate', 'Slope', 'Sat', 'Time To Sat'])
    else:
        writer.writerow(['Concentration', 'Value', 'TimePoint'])

# Helper: Extract single entry from data
def extract_single_entry(data, meas_mode):
    concentration = data.get('con', 'NONE')
    if meas_mode == "kinetics":
        return [
            concentration,
            data.get('maxrate', 'NONE'),
            data.get('slope', 'NONE'),
            data.get('sat', 'NONE'),
            data.get('timeSat', 'NONE')
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
        
    reader = csv.reader(io.StringIO('\n'.join(data_lines)))
    headers = next(reader)
    rows = list(reader)
    
    def _safe_float(val):
        try:
            return float(val)
        except (ValueError, TypeError):
            return float('inf') # Push non-numeric to the end
            
    # Sort by the first column (Concentration)
    rows.sort(key=lambda x: _safe_float(x[0]))
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    
    return '\n'.join(metadata) + '\n' + output.getvalue().strip()