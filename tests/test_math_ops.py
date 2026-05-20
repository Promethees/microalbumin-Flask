import sys
import os
import pytest
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from math_ops import (
    compute_r_squared,
    linear_func,
    poly_func,
    log_func,
    exp_func,
    mm_func,
    map_duplicates,
    calculate_coef_and_rsquared,
    get_rsquared_threshold,
    calculate_kinetics_quantities,
)


# ---------------------------------------------------------------------------
# compute_r_squared
# ---------------------------------------------------------------------------

def test_compute_r_squared_perfect_fit():
    assert compute_r_squared([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)


def test_compute_r_squared_constant_actual_returns_zero():
    # ss_tot == 0 guard at math_ops.py:10 — must return 0.0, not NaN
    assert compute_r_squared([5, 5, 5], [1, 2, 3]) == 0.0


def test_compute_r_squared_empty_lists_return_zero():
    assert compute_r_squared([], []) == 0.0


def test_compute_r_squared_length_mismatch_returns_zero():
    assert compute_r_squared([1, 2, 3], [1, 2]) == 0.0


# ---------------------------------------------------------------------------
# linear_func
# ---------------------------------------------------------------------------

def test_linear_func_known_output():
    # 2*3 + 1 = 7
    assert linear_func(3, 2, 1) == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# poly_func
# ---------------------------------------------------------------------------

def test_poly_func_known_output():
    # 2*x^2 + 3*x + 1 at x=2 → 2*4 + 3*2 + 1 = 15
    assert poly_func(2, 2, 3, 1) == pytest.approx(15.0)


def test_poly_func_zero_x():
    # a*0 + b*0 + c = c
    assert poly_func(0, 5, 3, 7) == pytest.approx(7.0)


def test_poly_func_negative_x():
    # 1*(-2)^2 + 0*(-2) + 0 = 4
    assert poly_func(-2, 1, 0, 0) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# log_func
# ---------------------------------------------------------------------------

def test_log_func_known_output():
    # a * ln(x + b) + c  at x=0, b=1, a=1, c=0 → ln(1) = 0
    assert log_func(0, 1, 1, 0) == pytest.approx(0.0)


def test_log_func_with_offset():
    # 2 * ln(3 + 1) + 5 = 2*ln(4) + 5
    expected = 2 * np.log(4) + 5
    assert log_func(3, 2, 1, 5) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# exp_func
# ---------------------------------------------------------------------------

def test_exp_func_known_output():
    # 1 * e^(0 * x) + 0 = 1
    assert exp_func(99, 1, 0, 0) == pytest.approx(1.0)


def test_exp_func_with_params():
    # 2 * e^(0.5 * 2) + 1 = 2*e + 1
    expected = 2 * np.exp(0.5 * 2) + 1
    assert exp_func(2, 2, 0.5, 1) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# mm_func — TC-06 (documents the division-by-zero bug; must pass after fix)
# ---------------------------------------------------------------------------

def test_mm_func_vmax_equals_x_does_not_raise():
    # Before fix: raises ZeroDivisionError.
    # After fix: must return inf, not raise.
    result = mm_func(5.0, vmax=5.0, km=2.0)
    assert np.isinf(result)


def test_mm_func_known_output():
    # (km * x) / (vmax - x) = (2 * 1) / (5 - 1) = 0.5
    assert mm_func(1.0, vmax=5.0, km=2.0) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# map_duplicates
# ---------------------------------------------------------------------------

def test_map_duplicates_averages_same_x():
    px, py = map_duplicates([1, 1, 2], [2.0, 4.0, 6.0])
    idx = px.index(1.0)
    assert py[idx] == pytest.approx(3.0)  # avg(2.0, 4.0)


def test_map_duplicates_skips_none_ovfl_by_default():
    px, py = map_duplicates([1, 2, 3], ["NONE", 5.0, "OVFL"])
    assert px == [2.0]
    assert py == [5.0]


def test_map_duplicates_keep_gaps_preserves_none_placeholder():
    px, py = map_duplicates([1, 2], ["NONE", 5.0], keep_gaps=True)
    idx = px.index(1.0)
    assert py[idx] is None


def test_map_duplicates_all_none_returns_empty_when_no_gaps():
    px, py = map_duplicates([1, 2], ["NONE", "NONE"])
    assert px == [] and py == []


# ---------------------------------------------------------------------------
# calculate_coef_and_rsquared
# ---------------------------------------------------------------------------

def test_calculate_coef_linear_perfect_fit():
    result = calculate_coef_and_rsquared([0, 1, 2, 3], [0, 2, 4, 6], "linear")
    assert result["slope"] == pytest.approx(2.0, rel=1e-3)
    assert result["rSquared"] == pytest.approx(1.0, rel=1e-3)
    assert result["coefficients"] is not None


def test_calculate_coef_too_few_points_returns_zero_dict():
    result = calculate_coef_and_rsquared([1], [1.0], "linear")
    assert result == {"slope": 0, "rSquared": 0, "coefficients": None}


def test_calculate_coef_all_none_y_returns_zero_dict():
    result = calculate_coef_and_rsquared([1, 2, 3], ["NONE", "NONE", "NONE"], "linear")
    assert result["coefficients"] is None


def test_calculate_coef_unknown_algo_returns_zero_dict():
    # Falls through all elif branches; coefficients stays None, exception caught
    result = calculate_coef_and_rsquared([0, 1, 2], [0, 1, 2], "unknownAlgo")
    assert result["coefficients"] is None and result["slope"] == 0


def test_calculate_coef_polynomial_perfect_fit():
    xs = [0, 1, 2, 3, 4]
    ys = [float(x ** 2) for x in xs]
    result = calculate_coef_and_rsquared(xs, ys, "polynomial")
    assert result["rSquared"] == pytest.approx(1.0, rel=1e-3)
    assert len(result["coefficients"]) == 3


def test_calculate_coef_exponential_perfect_fit():
    xs = [0, 1, 2, 3]
    ys = [2 * np.exp(0.5 * x) for x in xs]
    result = calculate_coef_and_rsquared(xs, ys, "exponential")
    assert result["rSquared"] == pytest.approx(1.0, rel=1e-2)
    assert len(result["coefficients"]) == 3


def test_calculate_coef_michaelis_menten_returns_two_coefficients():
    vmax, km = 3.0, 0.5
    rates = [0.1, 0.2, 0.5, 1.0, 2.0]
    analyte = [km * r / (vmax - r) for r in rates]
    result = calculate_coef_and_rsquared(rates, analyte, "Michaelis-Menten")
    assert result["rSquared"] == pytest.approx(1.0, rel=1e-2)
    assert len(result["coefficients"]) == 2


def test_calculate_coef_deduplicates_x_before_fitting():
    # x=0 appears twice with y=0 and y=2 → averaged to y=1; then fits [0,1,2]→[1,2,4]
    result = calculate_coef_and_rsquared([0, 0, 1, 2], [0.0, 2.0, 2.0, 4.0], "linear")
    assert result["coefficients"] is not None


# ---------------------------------------------------------------------------
# get_rsquared_threshold
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ws,dl", [(2, 10), (5, 3), (0, 0), (3, -1)])
def test_get_rsquared_threshold_invalid_args_return_0_9(ws, dl):
    assert get_rsquared_threshold(ws, dl) == 0.9


def test_get_rsquared_threshold_minimum_window_returns_max():
    # window_size == 3 == min_window → slope term is 0 → max threshold 0.97
    assert get_rsquared_threshold(3, 10) == pytest.approx(0.97)


@pytest.mark.parametrize("ws,dl", [(3, 10), (5, 10), (8, 10), (10, 10), (3, 100), (50, 100)])
def test_get_rsquared_threshold_always_within_valid_range(ws, dl):
    t = get_rsquared_threshold(ws, dl)
    assert 0.9 <= t <= 0.97


# ---------------------------------------------------------------------------
# calculate_kinetics_quantities
# ---------------------------------------------------------------------------

def test_calc_kinetics_too_few_valid_pairs_returns_defaults():
    result = calculate_kinetics_quantities([None, "NONE"], [None, "NONE"], 3)
    assert result["slope"] == 0
    assert result["saturationValue"] == "--"
    assert result["timeToSaturation"] == "--"


def test_calc_kinetics_detects_linear_region_and_max_rate():
    # Ramp then plateau: clear linear region followed by saturation
    x = [0, 1, 2, 3, 4, 5]
    y = [0.0, 2.0, 4.0, 6.0, 6.0, 6.0]
    result = calculate_kinetics_quantities(x, y, 3)
    assert float(result["maxRate"]) > 0
    assert result["linearXMin"] is not None


def test_calc_kinetics_oversized_window_does_not_raise():
    # window_size >> len(data) must clamp silently
    result = calculate_kinetics_quantities([0, 1, 2], [0.0, 1.0, 2.0], 999)
    assert isinstance(result, dict)


def test_calc_kinetics_no_linear_region_uses_median_saturation():
    # Flat data → maxRate stays 0, linear_start_idx == -1, saturation fallback used
    result = calculate_kinetics_quantities([0, 1, 2, 3], [5.0, 5.0, 5.0, 5.0], 3)
    assert result["linearXMin"] is None
    assert result["saturationValue"] != "--"


def test_calc_kinetics_filters_ovfl_values_does_not_raise():
    result = calculate_kinetics_quantities(
        [0, 1, 2, 3, 4], [0.0, "OVFL", 4.0, 6.0, 6.0], 2
    )
    assert isinstance(result, dict)
