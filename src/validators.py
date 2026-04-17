from functools import wraps
from flask import request, jsonify

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
