"""Build Excel formula strings from fitted standard-curve coefficients.

The calibration curve is fit as ``quantity -> concentration`` (x = the measured
quantity such as maxRate / slope / Value, y = [S] = concentration), so a formula
here takes a cell holding a measured quantity and returns the derived
concentration — the same math the app applies internally (mirrors
``src/math_ops.py`` model functions and the JS curve evaluation).

Every coefficient is wrapped in parentheses so a negative value stays valid
Excel syntax (``+(-3)`` rather than ``+-3``). The public entry point is
``excel_formula(regress_algo, coef_dict, cell)``.
"""

from typing import Optional, Dict, Any

# Regression algorithms understood here (must match math_ops.py / calculate.js).
SUPPORTED_ALGOS = ('linear', 'polynomial', 'logarithmic', 'exponential', 'Michaelis-Menten')

_MISSING = (None, 'NONE', '')


def _num(v: Any) -> str:
    """Format a coefficient as a compact, Excel-safe decimal string."""
    return '%.12g' % float(v)


def _coef(coef_dict: Dict[str, Any], key: str) -> Optional[str]:
    """Return the formatted coefficient for ``key``, or None when absent/blank."""
    if not isinstance(coef_dict, dict) or key not in coef_dict:
        return None
    v = coef_dict[key]
    if v in _MISSING:
        return None
    try:
        return _num(v)
    except (TypeError, ValueError):
        return None


def excel_formula(regress_algo: str, coef_dict: Dict[str, Any], cell: str = 'A1') -> Optional[str]:
    """Build the Excel formula that maps ``cell`` (a measured quantity) to concentration.

    Returns the formula string (leading ``=``) or ``None`` when the coefficients
    are missing (an under-threshold / failed fit), so the caller can report that
    source as having no usable curve.

    Models (see math_ops.py):
      linear        y = a*x + b
      polynomial    y = a*x^2 + b*x + c
      logarithmic   y = a*ln(x + b) + c
      exponential   y = a*e^(b*x) + c
      Michaelis-Menten  y = (Km*x) / (VMax - x)
    """
    if regress_algo == 'Michaelis-Menten':
        vmax = _coef(coef_dict, 'VMax')
        km = _coef(coef_dict, 'Km')
        if vmax is None or km is None:
            return None
        return '=(({km})*{c})/(({vmax})-{c})'.format(km=km, vmax=vmax, c=cell)

    a = _coef(coef_dict, 'a')
    b = _coef(coef_dict, 'b')
    c = _coef(coef_dict, 'c')

    if regress_algo == 'linear':
        if a is None or b is None:
            return None
        return '=({a})*{cell}+({b})'.format(a=a, b=b, cell=cell)

    if regress_algo == 'polynomial':
        if a is None or b is None or c is None:
            return None
        return '=({a})*{cell}^2+({b})*{cell}+({c})'.format(a=a, b=b, c=c, cell=cell)

    if regress_algo == 'logarithmic':
        if a is None or b is None or c is None:
            return None
        return '=({a})*LN({cell}+({b}))+({c})'.format(a=a, b=b, c=c, cell=cell)

    if regress_algo == 'exponential':
        if a is None or b is None or c is None:
            return None
        return '=({a})*EXP(({b})*{cell})+({c})'.format(a=a, b=b, c=c, cell=cell)

    return None


def formulas_from_content(content: Dict[str, Any], regress_algo: str, cell: str = 'A1'):
    """Walk a ``processJSONCoef`` result into a list of labelled formulas.

    Single-source content carries a top-level ``fit_coef``; multi-source content
    is keyed per source, each holding its own ``fit_coef``. Non-coefficient
    metadata keys (fit_type, for_meas, …) are skipped. Each entry is
    ``{label, formula}`` where ``formula`` is None for an unusable fit.
    """
    out = []
    if isinstance(content, dict) and 'fit_coef' in content:
        out.append({'label': None, 'formula': excel_formula(regress_algo, content['fit_coef'], cell)})
    elif isinstance(content, dict):
        for key, val in content.items():
            if isinstance(val, dict) and 'fit_coef' in val:
                out.append({'label': key, 'formula': excel_formula(regress_algo, val['fit_coef'], cell)})
    return out
