import re
import json

def validate_json_content(content: str):
    """
    Validate that the content is valid JSON.
    Returns (True, parsed_json) if valid, (False, error_message) otherwise.
    """
    try:
        parsed_json = json.loads(content)
        return True, parsed_json
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON format: {str(e)}"

def validate_csv_content(content: str):
    """
    Validate CSV content against predefined patterns for Easy OKAPI.
    Returns (True, pattern_match_info) if valid, (False, error_message) otherwise.
    """
    pattern_sets = [
        {
            'header': r"^Concentration,maxRate,Slope,Sat,TimeToSat$",
            'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+\.\d+),(NONE|\d+|\d+\.\d*)$",
            'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
            'error': 'Invalid format (Kinetics calibration). Header must be: Concentration,maxRate,Slope,Sat,Time To Sat. Metadata must include Measurement, MeasUnit, TimeUnit, and MeasMode.'
        },
        {
            'header': r"^Concentration,Value,TimePoint$",
            'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d*)$",
            'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
            'error': 'Invalid format (Point calibration). Header must be: Concentration,Value,TimePoint. Metadata must include Measurement, MeasUnit, TimeUnit and MeasMode.'
        },
        {
            'header': r'^\s*Timestamp\s*,\s*Value:\d+(?:\s*,\s*Value:\d+)*\s*$',
            'data': r'^\s*\d+(?:\.\d{1,2})?\s*(?:(?:,\s*)?(?:-?\d+(?:\.\d{1,3})?|OVFL|NONE)?\s*)*$',
            'meta': ["Measurement", "Unit", "Concentration"],
            'error': 'Invalid format (Pattern 4). Header must be: Timestamp,Value:1,Value:2,... Metadata must include Measurement, Unit, and Concentration.'
        }
    ]

    lines = content.strip().split('\n')
    if not lines:
        return False, "Content cannot be empty"

    metadata_lines = [line.strip() for line in lines if line.strip().startswith('#')]
    data_lines = [line.strip() for line in lines if not line.strip().startswith('#')]

    if not data_lines:
        return False, "CSV must contain at least a header row after metadata"

    header_line = data_lines[0].replace(" ", "")
    matched_pattern = None
    for pattern in pattern_sets:
        if re.match(pattern['header'], header_line):
            matched_pattern = pattern
            break

    if not matched_pattern:
        valid_headers = " OR ".join(p['error'].split('Header must be: ')[1] for p in pattern_sets)
        return False, f"Invalid CSV header. Must match one of: {valid_headers}"

    # Validate metadata
    required_meta = matched_pattern.get("meta", [])
    meta_dict = {}
    if required_meta:
        for line in metadata_lines:
            if ":" in line:
                key, value = line.lstrip("#").split(":", 1)
                meta_dict[key.strip()] = value.strip()
        
        # Check for required keys, allowing 'Unit' and 'MeasUnit' to be interchangeable
        for req_key in required_meta:
            if req_key in ['Unit', 'MeasUnit']:
                if 'Unit' not in meta_dict and 'MeasUnit' not in meta_dict:
                    return False, matched_pattern.get('error', f'Missing metadata: Unit or MeasUnit')
            elif req_key not in meta_dict:
                return False, matched_pattern.get('error', f'Missing metadata: {req_key}')

    # Validate data rows
    for i, line in enumerate(data_lines[1:], 2):
        if not re.match(matched_pattern['data'], line):
            return False, f"Invalid data in row {i} for the detected format."

    return True, {"pattern": matched_pattern, "metadata": meta_dict if required_meta else {}}
