import re
import json
from functools import wraps
from flask import request, jsonify
from file_path import (parse_csv_metadata, detect_csv_schema,
                       CSV_SCHEMA_TIMESERIES, CSV_SCHEMA_KINETICS_CAL, CSV_SCHEMA_POINT_CAL)

def validate_json(schema):
    """
    A lightweight validator for incoming JSON payloads.
    `schema` is a dictionary where keys are expected JSON fields
    and values are types (e.g. str, int, float, bool, list, dict)
    or a tuple of (type, default_value, is_required).
    
    Example schema:
    {
        'filename': (str, None, True),
        'timeout_sec': (float, None, False)
    }
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify({'status': 'failure', 'message': 'Request must be JSON'}), 400
                
            data = request.get_json()
            validated_data = {}
            
            for key, rules in schema.items():
                if isinstance(rules, tuple):
                    expected_type, default_val, is_required = rules
                else:
                    expected_type, default_val, is_required = rules, None, True
                    
                val = data.get(key)
                
                if val is None:
                    if is_required:
                        return jsonify({'status': 'error', 'message': f'Missing required field: {key}'}), 400
                    else:
                        validated_data[key] = default_val
                        continue
                        
                # Type coercion
                try:
                    if expected_type == bool:
                        if isinstance(val, str):
                            validated_data[key] = val.lower() in ('true', '1', 'yes')
                        else:
                            validated_data[key] = bool(val)
                    elif expected_type == float:
                        validated_data[key] = float(val)
                    elif expected_type == int:
                        validated_data[key] = int(val)
                    else:
                        if not isinstance(val, expected_type):
                            return jsonify({'status': 'error', 'message': f'Field {key} must be of type {expected_type.__name__}'}), 400
                        validated_data[key] = val
                except (ValueError, TypeError):
                    return jsonify({'status': 'error', 'message': f'Invalid value for field {key}. Expected {expected_type.__name__}'}), 400
                    
            # Inject validated_data into the route handler
            kwargs['validated_data'] = validated_data
            return f(*args, **kwargs)
        return wrapper
    return decorator


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

_SCHEMA_VALIDATORS = {
    CSV_SCHEMA_KINETICS_CAL: {
        'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+\.\d+),(NONE|\d+|\d+\.\d*)$",
        'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
        'error': 'Invalid format (Kinetics calibration). Header must be: Concentration,maxRate,Slope,Sat,Time To Sat. Metadata must include Measurement, MeasUnit, TimeUnit, and MeasMode.'
    },
    CSV_SCHEMA_POINT_CAL: {
        'data': r"^(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d+),(NONE|\d+|\d+\.\d*)$",
        'meta': ["Measurement", "MeasUnit", "TimeUnit", "MeasMode"],
        'error': 'Invalid format (Point calibration). Header must be: Concentration,Value,TimePoint. Metadata must include Measurement, MeasUnit, TimeUnit and MeasMode.'
    },
    CSV_SCHEMA_TIMESERIES: {
        'data': r'^\s*\d+(?:\.\d{1,2})?\s*(?:(?:,\s*)?(?:-?\d+(?:\.\d{1,3})?|OVFL|NONE)?\s*)*$',
        'meta': ["Measurement", "Unit", "Concentration"],
        'error': 'Invalid format (Pattern 4). Header must be: Timestamp,Value:1,Value:2,... Metadata must include Measurement, Unit, and Concentration.'
    },
}


def validate_csv_content(content: str):
    """
    Validate CSV content against predefined patterns for Easy OKAPI.
    Returns (True, pattern_match_info) if valid, (False, error_message) otherwise.
    """
    lines = content.strip().split('\n')
    if not lines:
        return False, "Content cannot be empty"

    metadata_lines = [line.strip() for line in lines if line.strip().startswith('#')]
    data_lines = [line.strip() for line in lines if not line.strip().startswith('#')]

    if not data_lines:
        return False, "CSV must contain at least a header row after metadata"

    schema = detect_csv_schema(data_lines[0])
    matched_pattern = _SCHEMA_VALIDATORS.get(schema)
    if not matched_pattern:
        return False, "Invalid CSV header."

    required_meta = matched_pattern.get("meta", [])
    meta_dict = parse_csv_metadata(metadata_lines) if required_meta else {}

    for req_key in required_meta:
        if req_key in ('Unit', 'MeasUnit'):
            if 'Unit' not in meta_dict and 'MeasUnit' not in meta_dict:
                return False, matched_pattern.get('error', 'Missing metadata: Unit or MeasUnit')
        elif req_key not in meta_dict:
            return False, matched_pattern.get('error', f'Missing metadata: {req_key}')

    for i, line in enumerate(data_lines[1:], 2):
        if not re.match(matched_pattern['data'], line):
            return False, f"Invalid data in row {i} for the detected format."

    return True, {"pattern": matched_pattern, "metadata": meta_dict}
