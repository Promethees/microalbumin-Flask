import math
import numpy as np
from scipy.optimize import curve_fit

def compute_r_squared(actual, predicted):
    if len(actual) != len(predicted) or len(actual) < 1:
        return 0.0
    actual = np.array(actual)
    predicted = np.array(predicted)
    ss_res = np.sum((actual - predicted)**2)
    ss_tot = np.sum((actual - np.mean(actual))**2)
    return 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

def linear_func(x, a, b):
    return a * x + b

def poly_func(x, a, b, c):
    # ax^2 + bx + c
    return a * (x**2) + b * x + c

def log_func(x, a, b, c):
    # a * ln(x + b) + c
    return a * np.log(x + b) + c

def exp_func(x, a, b, c):
    # a * e^(b * x) + c
    return a * np.exp(b * x) + c

def mm_func(x, vmax, km):
    # [S] = (Km * x) / (Vmax - x) -> Wait, JS formula is:
    # predicted = x.map(xi => coefficients[1] * xi / (coefficients[0] - xi))
    # where coefficients[0] = Vmax, [1] = Km. So predicted = (Km * x) / (Vmax - x)
    denom = vmax - x
    # Guard: scalar zero-denominator raises ZeroDivisionError; numpy arrays produce inf naturally.
    if np.isscalar(denom) and denom == 0:
        return np.inf
    return (km * x) / denom

def map_duplicates(x, y, keep_gaps=False):
    x_map = {}
    for xi, yi in zip(x, y):
        is_none = yi in ("NONE", None, "OVFL")
        if is_none:
            if not keep_gaps: continue
            if xi not in x_map:
                x_map[xi] = {'sum': 0.0, 'count': 0, 'has_valid': False}
        else:
            try:
                val = float(yi)
                if xi not in x_map:
                    x_map[xi] = {'sum': val, 'count': 1, 'has_valid': True}
                else:
                    x_map[xi]['sum'] += val
                    x_map[xi]['count'] += 1
                    x_map[xi]['has_valid'] = True
            except ValueError:
                if keep_gaps:
                    if xi not in x_map:
                        x_map[xi] = {'sum': 0.0, 'count': 0, 'has_valid': False}
    
    processed_x = []
    processed_y = []
    for k, v in x_map.items():
        processed_x.append(float(k))
        processed_y.append(float(v['sum']/v['count']) if v['has_valid'] else None)
        
    return processed_x, processed_y

def calculate_coef_and_rsquared(x, y, regress_algo="linear"):
    px, py = map_duplicates(x, y)
    valid = [(xi, yi) for xi, yi in zip(px, py) if yi is not None]
    
    x = np.array([v[0] for v in valid], dtype=float)
    y = np.array([v[1] for v in valid], dtype=float)
    
    if len(x) != len(y) or len(x) < 2:
        return {"slope": 0, "rSquared": 0, "coefficients": None}
        
    slope = 0.0
    r_squared = 0.0
    coefficients = None
    
    try:
        if regress_algo == "linear":
            # np.polyfit (not curve_fit): a 2-point/collinear window is an exact
            # fit, whose singular covariance makes curve_fit emit OptimizeWarning.
            a, b = np.polyfit(x, y, 1)
            slope = a
            predicted = linear_func(x, a, b)
            r_squared = compute_r_squared(y, predicted)
            coefficients = [a, b]
            
        elif regress_algo == "polynomial":
            # Use np.polyfit for robustness (descending order: ax^2 + bx + c)
            a, b, c = np.polyfit(x, y, 2)
            predicted = poly_func(x, a, b, c)
            r_squared = compute_r_squared(y, predicted)
            mid_x = (np.max(x) + np.min(x)) / 2
            slope = 2 * a * mid_x + b
            coefficients = [a, b, c] # Descending order: [ax^2, bx, c] for JS
            
        elif regress_algo == "logarithmic":
            min_x = np.min(x)
            bounds = ([-np.inf, -min_x + 1e-5, -np.inf], [np.inf, np.inf, np.inf])
            coeffs, _ = curve_fit(log_func, x, y, bounds=bounds, maxfev=10000)
            a, b, c = coeffs
            predicted = log_func(x, a, b, c)
            r_squared = compute_r_squared(y, predicted)
            mid_x = (np.max(x) + np.min(x)) / 2
            slope = a / (mid_x + b)
            coefficients = [a, b, c]
            
        elif regress_algo == "exponential":
            c_guess = np.min(y) if np.min(y) > 0 else np.mean(y)
            p0 = [1.0, 0.1, c_guess]
            coeffs, _ = curve_fit(exp_func, x, y, p0=p0, maxfev=10000)
            a, b, c = coeffs
            predicted = exp_func(x, a, b, c)
            r_squared = compute_r_squared(y, predicted)
            mid_x = (np.max(x) + np.min(x)) / 2
            slope = a * b * np.exp(b * mid_x)
            coefficients = [a, b, c]
            
        elif regress_algo == "Michaelis-Menten":
            vmax_guess = np.max(x) * 1.1
            km_guess = y[len(y)//2]
            p0 = [vmax_guess, km_guess]
            
            # The function tries to fit y based on x? Wait!
            # In JS: `michaelisMentenConcentrationRegression(rates, analyte)` -> returns [Vmax, Km]
            # `rates` is X, `analyte` is Y? Yes, x=rates, y=analyte.
            # mm_func is y = (km * x) / (vmax - x)
            bounds = ([np.max(x) + 1e-5, 0], [np.inf, np.inf])
            coeffs, _ = curve_fit(mm_func, x, y, p0=p0, bounds=bounds, maxfev=10000)
            vmax, km = coeffs
            predicted = mm_func(x, vmax, km)
            r_squared = compute_r_squared(y, predicted)
            slope = km / (vmax - 1)
            coefficients = [vmax, km]
            
    except Exception as e:
        print(f"Regression error ({regress_algo}): {str(e)}")
        return {"slope": 0, "rSquared": 0, "coefficients": None}
        
    return {
        "slope": float(slope),
        "rSquared": float(r_squared),
        "coefficients": [float(c) for c in coefficients] if coefficients else None
    }

def evaluate_curve(regress_algo, coefficients, x):
    """Evaluate a fitted standard-curve model at ``x`` → the derived concentration.

    Same models as the fit functions above and ``excel_formula.py``:
      linear        a*x + b
      polynomial    a*x^2 + b*x + c
      logarithmic   a*ln(x + b) + c
      exponential   a*e^(b*x) + c
      Michaelis-Menten  (Km*x) / (VMax - x)

    ``coefficients`` may be a dict (``a``/``b``/``c`` or ``VMax``/``Km``) or an
    ordered list. Raises ``ValueError`` on a missing/non-numeric coefficient, an
    unknown algorithm, or a domain error (log of a non-positive argument,
    Michaelis-Menten zero denominator).
    """
    x = float(x)

    def _num(v, name):
        if v is None or v == "NONE" or v == "":
            raise ValueError("Missing coefficient: %s" % name)
        try:
            return float(v)
        except (TypeError, ValueError):
            raise ValueError("Coefficient %s must be a number" % name)

    if regress_algo == "Michaelis-Menten":
        if isinstance(coefficients, dict):
            vmax = _num(coefficients.get("VMax"), "VMax")
            km = _num(coefficients.get("Km"), "Km")
        else:
            if len(coefficients) < 2:
                raise ValueError("Michaelis-Menten requires VMax and Km")
            vmax = _num(coefficients[0], "VMax")
            km = _num(coefficients[1], "Km")
        denom = vmax - x
        if denom == 0:
            raise ValueError("VMax - x is zero (division by zero)")
        return (km * x) / denom

    if isinstance(coefficients, dict):
        a = _num(coefficients.get("a"), "a")
        b = _num(coefficients.get("b"), "b")
        c_raw = coefficients.get("c")
    else:
        if len(coefficients) < 2:
            raise ValueError("At least coefficients a and b are required")
        a = _num(coefficients[0], "a")
        b = _num(coefficients[1], "b")
        c_raw = coefficients[2] if len(coefficients) > 2 else None

    if regress_algo == "linear":
        return a * x + b
    if regress_algo == "polynomial":
        return a * x * x + b * x + _num(c_raw, "c")
    if regress_algo == "logarithmic":
        c = _num(c_raw, "c")
        if x + b <= 0:
            raise ValueError("x + b must be > 0 for the logarithm")
        return a * math.log(x + b) + c
    if regress_algo == "exponential":
        return a * math.exp(b * x) + _num(c_raw, "c")

    raise ValueError("Unknown regression algorithm: %s" % regress_algo)


def get_rsquared_threshold(window_size, data_length):
    if window_size < 3 or window_size > data_length or data_length <= 0:
        return 0.9

    min_window = 3
    max_r_squared = 0.97
    min_r_squared = 0.9

    # Guard: when data_length == min_window the denominator is 0; the window
    # spans the entire dataset so use the strictest threshold.
    if data_length <= min_window:
        return max_r_squared

    slope = (min_r_squared - max_r_squared) / (data_length - min_window)
    r_squared = max_r_squared + slope * (window_size - min_window)

    return max(min_r_squared, min(max_r_squared, r_squared))

# Saturation-plateau gate: the trailing segment counts as a real plateau only
# when it holds enough points AND its own slope has collapsed to a small
# fraction of the reaction's peak rate. Guards against an interrupted trace
# (signal still rising when logging stopped) being reported as saturated.
SAT_FLAT_FRACTION = 0.10  # tail slope must be <= 10% of max_rate to count as flat


def _tail_is_flat(x_tail, y_tail, max_rate, window_size):
    min_tail = max(3, window_size // 2)
    if len(y_tail) < min_tail or max_rate <= 0:
        return False
    fit = calculate_coef_and_rsquared(x_tail, y_tail, "linear")
    return abs(fit["slope"]) <= SAT_FLAT_FRACTION * max_rate


def calculate_kinetics_quantities(x_col, y_col, window_size):
    valid_pairs = [(x, y) for (x, y) in zip(x_col, y_col) if x not in (None, "NONE") and y not in (None, "NONE", "OVFL")]
    
    if len(valid_pairs) < 2:
        return {
            "slope": 0, "intercept": 0, "saturationValue": "--", "timeToSaturation": "--",
            "maxRate": 0, "linearSlope": 0, "linearYMin": 0, "linearYMax": 0, "linearXMin": 0, "linearXMax": 0
        }
        
    x_col_valid = [float(p[0]) for p in valid_pairs]
    y_col_valid = [float(p[1]) for p in valid_pairs]
    
    window_size = int(window_size)
    if window_size < 2 or window_size > len(x_col_valid):
        window_size = len(x_col_valid)
        
    local_slopes = []
    r_squared_values = []
    intercepts = []
    r_squared_threshold = get_rsquared_threshold(window_size, len(x_col_valid))
    
    for i in range(len(x_col_valid) - window_size + 1):
        x_win = x_col_valid[i:i+window_size]
        y_win = y_col_valid[i:i+window_size]
        calc = calculate_coef_and_rsquared(x_win, y_win, "linear")
        
        slope = calc["slope"]
        avg_x = sum(x_win) / len(x_win)
        avg_y = sum(y_win) / len(y_win)
        intercept = avg_y - slope * avg_x
        
        local_slopes.append(slope)
        r_squared_values.append(calc["rSquared"])
        intercepts.append(intercept)
        
    max_rate = 0
    threshold = 0
    start_max_rate = -1
    end_max_rate = -1
    y_max_rate_start = 0
    y_max_rate_end = 0
    
    for i in range(len(local_slopes)):
        adjusted_local = 3600 * local_slopes[i]
        if r_squared_values[i] >= r_squared_threshold and local_slopes[i] > max_rate and adjusted_local > threshold:
            max_rate = local_slopes[i]
            start_max_rate = i
            end_max_rate = start_max_rate + window_size - 1
            y_max_rate_start = max_rate * x_col_valid[start_max_rate] + intercepts[i]
            y_max_rate_end = max_rate * x_col_valid[end_max_rate] + intercepts[i]
            
    linear_start_idx = -1
    linear_end_idx = -1
    if max_rate != 0:
        for i in range(len(local_slopes)):
            if local_slopes[i] >= 0.8 * max_rate and r_squared_values[i] >= r_squared_threshold:
                if linear_start_idx == -1:
                    linear_start_idx = i
                linear_end_idx = i
                
    linear_slope = None
    linear_intercept = 0
    linear_x_min = 0
    linear_x_max = 0
    linear_y_min = 0
    linear_y_max = 0
    saturation_value = "--"
    time_to_saturation = "--"
    time_start_saturation = "--"
    
    if linear_start_idx != -1 and linear_end_idx != -1:
        start = linear_start_idx
        end = linear_end_idx + window_size
        if end > len(x_col_valid):
            end = len(x_col_valid)
            
        x_win = x_col_valid[start:end]
        y_win = y_col_valid[start:end]
        calc = calculate_coef_and_rsquared(x_win, y_win, "linear")
        
        linear_slope = calc["slope"]
        avg_x = sum(x_win) / len(x_win)
        avg_y = sum(y_win) / len(y_win)
        linear_intercept = avg_y - linear_slope * avg_x
        
        linear_x_min = x_col_valid[start]
        linear_x_max = x_col_valid[end - 1]
        linear_y_min = linear_slope * linear_x_min + linear_intercept
        linear_y_max = linear_slope * linear_x_max + linear_intercept
        
        tail_x = x_col_valid[end:]
        tail_y = y_col_valid[end:]
        if _tail_is_flat(tail_x, tail_y, max_rate, window_size):
            sorted_rest = sorted(tail_y)
            saturation_value = sorted_rest[len(sorted_rest) // 2]
            time_to_saturation = f"{(x_col_valid[end - 1] - x_col_valid[start]):.2f}"
            time_start_saturation = f"{x_col_valid[end - 1]:.2f}"
        else:
            # No confirmed plateau (trace interrupted or tail too short/still rising).
            saturation_value = "--"
            time_to_saturation = "--"
            time_start_saturation = "--"
    else:
        # No linear phase detected — cannot locate a plateau. Report undetected
        # rather than a meaningless median of the whole trace.
        saturation_value = "--"
        time_to_saturation = "--"
        time_start_saturation = "--"
        
    return {
        "slope": linear_slope,
        "intercept": f"{linear_intercept:.2f}",
        "saturationValue": saturation_value,
        "timeToSaturation": time_to_saturation,
        "maxRate": f"{max_rate:.6f}",
        "linearYMin": linear_y_min,
        "linearYMax": linear_y_max,
        "linearXMin": f"{linear_x_min:.2f}" if linear_start_idx != -1 else None,
        "linearXMax": f"{linear_x_max:.2f}" if linear_end_idx != -1 else None,
        "startMaxRate": f"{x_col_valid[start_max_rate]:.2f}" if start_max_rate != -1 else None,
        "endMaxRate": f"{x_col_valid[end_max_rate]:.2f}" if end_max_rate != -1 else None,
        "yMaxRateStart": y_max_rate_start,
        "yMaxRateEnd": y_max_rate_end,
        "timeStartSaturation": time_start_saturation
    }
