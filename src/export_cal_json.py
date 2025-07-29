import json
from typing import List, Dict, Union, Any
import datetime

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        elif hasattr(obj, '__dict__'):
            return obj.__dict__  # Handle custom classes
        return super().default(obj) 

def processJSONCoef(cal_params: List[str], coefficients: Union[List[float], List[List[float]]]) -> Dict[str, Any]:
    """
    Process analysis parameters and coefficients into a structured JSON object.
    
    Args:
        cal_params: List of parameter names (e.g., ["maxRate", "slope", "sat", "Time To Sat"])
        coefficients: Either:
            - A 1D array [v, v] → Returns {"fit_coef": [v, v]}
            - A 2D array [[v, v], [v, v], ...] → Returns {param1: {"fit_coef": [v, v]}, ...}
    
    Returns:
        A JSON-compatible dictionary with "NONE" replacing None values.
    
    Raises:
        Exception: If inputs are invalid.
    """
    # Validate inputs
    if not isinstance(cal_params, list):
        raise Exception("cal_params must be a list")
    if not isinstance(coefficients, list):
        raise Exception("coefficients must be a list")

    def sanitize_value(v: Any) -> Union[float, str]:
        """Replace None with 'NONE' to avoid JSON issues."""
        return v if v is not None else "NONE"

    # Case 1: coefficients is 1D (e.g., [v, v])
    if all(not isinstance(x, list) for x in coefficients):
        if len(coefficients) < 2:
            raise Exception("1D coefficients must have at least 2 values")
        
        sanitized_coef = [sanitize_value(v) for v in coefficients]
        return {"fit_coef": sanitized_coef}

    # Case 2: coefficients is 2D (e.g., [[v, v], [v, v], ...])
    elif all(isinstance(x, list) for x in coefficients):
        if len(cal_params) != len(coefficients):
            raise Exception("For 2D coefficients, cal_params and coefficients must have the same length")
        
        result = {}
        for param, coef in zip(cal_params, coefficients):
            if len(coef) < 2:
                raise Exception(f"Each coefficient must be a list of at least 2 values (got {len(coef)})")
            
            processed_key = param.lower().replace(" ", "_")
            sanitized_coef = [sanitize_value(v) for v in coef]
            result[processed_key] = {"fit_coef": sanitized_coef}
        return result

    else:
        raise Exception("coefficients must be either [v, v] or [[v, v], [v, v], ...]")

def extractAnalysisCoefficients(
    data: Union[List[Dict[str, Any]], Dict[str, Any]], 
    threshold: float = 0.0  # Default threshold (adjust as needed)
) -> Union[List[Any], List[List[Any]]]:
    """
    Extracts coefficients, setting them to null if rSquared < threshold.
    
    Args:
        data: Single slope object or array of slope objects.
        threshold: Minimum rSquared value to keep coefficients.
    
    Returns:
        - Single object: Coefficients array (with null if filtered).
        - Array: List of coefficients arrays (with null if filtered).
    """
    def process_entry(entry: Dict[str, Any]) -> List[Any]:
        """Process one slope entry: return coefficients or nulls based on rSquared."""
        r_squared = entry.get("rSquared")
        # Convert rSquared to float if it's a string
        if isinstance(r_squared, str):
            try:
                r_squared = float(r_squared)
            except ValueError:
                r_squared = None  # Treat invalid strings as None
        if r_squared is None or (isinstance(r_squared, (float, int)) and r_squared < threshold):
            return [None] * len(entry.get("coefficients", []))
        return entry["coefficients"]
    
    # Case 1: Single object
    if isinstance(data, dict):
        return process_entry(data)
    
    # Case 2: Array of objects
    elif isinstance(data, list):
        return [process_entry(entry) for entry in data]
    
    else:
        raise Exception("Input must be a slope object or array of slope objects")