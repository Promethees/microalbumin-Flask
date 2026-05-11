import json
from typing import List, Dict, Union, Any
import datetime
from decimal import Decimal

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        elif hasattr(obj, '__dict__'):
            return obj.__dict__  # Handle custom classes
        return super().default(obj) 

def processJSONCoef(
    cal_params: List[str],
    coefficients: Union[List[float], List[List[float]]],
    regress_algo: str
) -> Dict[str, Any]:
    """
    Process coefficients into a JSON-compatible structure where `fit_coef` is a **dict**.

    - 1D coefficients → {"fit_coef": {"VMax": ..., "Km": ...}}  (if is_menten)
    - 2D coefficients → {param: {"fit_coef": {"a": ..., "b": ..., ...}}, ...}

    Args:
        cal_params: List of parameter names (used only in 2D case)
        coefficients: [v1, v2, ...] or [[v1, v2, ...], ...]
        regress_algo: If regress_algo is "Michaelis-Menten", first two keys are "VMax" and "Km"

    Returns:
        dict with `fit_coef` as a **dictionary object** (not JSON string)
    """
    print("Cal params: ", cal_params)
    print("Coefficients: ", coefficients)
    if not isinstance(cal_params, list):
        raise ValueError("cal_params must be a list")
    if not isinstance(coefficients, list):
        raise ValueError("coefficients must be a list")

    def sanitize(v: Any) -> Union[float, str]:
        return v if v is not None else "NONE"

    def build_coef_dict(coef_list: List[Any]) -> Dict[str, Any]:
        if len(coef_list) < 2:
            raise ValueError("Each coefficient set must have at least 2 values")
        sanitized = [sanitize(v) for v in coef_list]

        if regress_algo == "Michaelis-Menten":
            if len(sanitized) != 2:
                raise ValueError("Michaelis-Menten requires exactly 2 coefficients (VMax, Km)")
            keys = ["VMax", "Km"]
        else:
            keys = [chr(ord('a') + i) for i in range(len(sanitized))]

        return dict(zip(keys, sanitized))

    # Case 1: 1D coefficients
    if all(not isinstance(x, list) for x in coefficients):
        return {"fit_coef": build_coef_dict(coefficients)}

    # Case 2: 2D coefficients
    if all(isinstance(x, list) for x in coefficients):
        if len(cal_params) != len(coefficients):
            raise ValueError("cal_params and coefficients must have same length in 2D mode")

        result: Dict[str, Any] = {}
        for param, coef in zip(cal_params, coefficients):
            if not isinstance(coef, list) or len(coef) < 2:
                raise ValueError(f"Coefficient for '{param}' must be list with >=2 values")

            key = param.lower().replace(" ", "_")
            result[key] = {"fit_coef": build_coef_dict(coef)}
        return result

    raise ValueError("coefficients must be 1D list or 2D list of lists")

def extractAnalysisCoefficients(
    data: Union[List[Dict[str, Any]], Dict[str, Any]], 
    threshold: float = 0.0,  # Default threshold (adjust as needed),
    regress_algo: str = 'linear'
) -> Union[List[Any], List[List[Any]]]:
    """
    Extracts coefficients, setting them to null if rSquared < threshold.
    
    Args:
        data: Single slope object or array of slope objects.
        threshold: Minimum rSquared value to keep coefficients.
        regress_algo: Regression algorithm to use.

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
        if r_squared is None or (isinstance(r_squared, (float, int)) and r_squared < threshold) or entry["coefficients"] is None:
            if regress_algo in ['polynomial', 'exponential', 'logarithmic']:
                return [None] * 3
            return [None] * 2
        return entry["coefficients"]
    
    # Case 1: Single object
    if isinstance(data, dict):
        return process_entry(data)
    
    # Case 2: Array of objects
    elif isinstance(data, list):
        return [process_entry(entry) for entry in data]
    
    else:
        raise Exception("Input must be a slope object or array of slope objects")