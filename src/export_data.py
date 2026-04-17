# Helper: Parse metadata from content
import pandas as pd
import io

def parse_metadata(content):
    meta_dict = {}
    for line in content.split('\n'):
        if line.startswith('# '):
            if ':' in line:
                key, val = line[2:].split(':', 1)
                meta_dict[key.strip()] = val.strip()
    return meta_dict

# Helper: Check metadata consistency
def is_metadata_consistent(meta_dict, measurement, meas_unit, time_unit, meas_mode):
    return (meta_dict.get('Measurement') == measurement and
            meta_dict.get('MeasUnit') == meas_unit and
            meta_dict.get('TimeUnit') == time_unit and
            meta_dict.get('MeasMode') == meas_mode)

# Helper: Write metadata
def write_metadata(output, measurement, meas_unit, time_unit, meas_mode):
    output.write(f"# Measurement: {measurement}\n")
    output.write(f"# MeasUnit: {meas_unit}\n")
    output.write(f"# TimeUnit: {time_unit}\n")
    output.write(f"# MeasMode: {meas_mode}\n")

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
        
    df = pd.read_csv(io.StringIO('\n'.join(data_lines)))
    first_col = df.columns[0]
    
    # Temporarily replace 'NONE' with NaN to sort properly
    df['_sort_key'] = pd.to_numeric(df[first_col], errors='coerce')
    df = df.sort_values(by='_sort_key', na_position='last').drop(columns=['_sort_key'])
    
    csv_buffer = io.StringIO()
    # Fill any NaNs created by read_csv back to 'NONE' if necessary, though 'NONE' usually parses as string
    df = df.fillna('NONE')
    df.to_csv(csv_buffer, index=False)
    
    return '\n'.join(metadata) + '\n' + csv_buffer.getvalue()