import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from export_cal_json import processJSONCoef, extractAnalysisCoefficients, replace_empty


# ---------------------------------------------------------------------------
# processJSONCoef — 1D coefficients
# ---------------------------------------------------------------------------

def test_process_1d_linear_returns_fit_coef_dict():
    result = processJSONCoef([], [1.0, 2.0], 'linear')
    assert 'fit_coef' in result
    assert result['fit_coef'] == {'a': 1.0, 'b': 2.0}


def test_process_1d_three_coefs_assigns_a_b_c():
    result = processJSONCoef([], [1.0, 2.0, 3.0], 'polynomial')
    assert result['fit_coef'] == {'a': 1.0, 'b': 2.0, 'c': 3.0}


def test_process_1d_michaelis_menten_uses_vmax_km_keys():
    result = processJSONCoef([], [5.0, 0.5], 'michaelis-menten')
    assert result['fit_coef']['VMax'] == 5.0
    assert result['fit_coef']['Km'] == 0.5


def test_process_1d_none_value_becomes_none_string():
    result = processJSONCoef([], [None, 2.0], 'linear')
    assert result['fit_coef']['a'] == 'NONE'


def test_process_1d_too_few_coefs_raises():
    with pytest.raises(ValueError):
        processJSONCoef([], [1.0], 'linear')


# ---------------------------------------------------------------------------
# processJSONCoef — 2D coefficients
# ---------------------------------------------------------------------------

def test_process_2d_returns_keyed_by_param():
    result = processJSONCoef(['maxRate', 'Slope'], [[1.0, 0.5], [2.0, 0.1]], 'linear')
    assert 'maxrate' in result
    assert 'slope' in result
    assert result['maxrate']['fit_coef'] == {'a': 1.0, 'b': 0.5}


def test_process_2d_length_mismatch_raises():
    with pytest.raises(ValueError):
        processJSONCoef(['maxRate'], [[1.0, 0.5], [2.0, 0.1]], 'linear')


def test_process_2d_param_space_replaced_with_underscore():
    result = processJSONCoef(['Time To Sat'], [[1.0, 0.5]], 'linear')
    assert 'time_to_sat' in result


def test_process_2d_inner_too_few_coefs_raises():
    with pytest.raises(ValueError):
        processJSONCoef(['maxRate'], [[1.0]], 'linear')


# ---------------------------------------------------------------------------
# processJSONCoef — mixed (invalid) input
# ---------------------------------------------------------------------------

def test_process_mixed_1d_2d_raises():
    with pytest.raises(ValueError):
        processJSONCoef(['a'], [1.0, [2.0, 3.0]], 'linear')


def test_process_non_list_cal_params_raises():
    with pytest.raises(ValueError):
        processJSONCoef('not_a_list', [1.0, 2.0], 'linear')


def test_process_non_list_coefficients_raises():
    with pytest.raises(ValueError):
        processJSONCoef([], 'not_a_list', 'linear')


# ---------------------------------------------------------------------------
# extractAnalysisCoefficients — single dict
# ---------------------------------------------------------------------------

def test_extract_single_above_threshold_returns_coefficients():
    entry = {'rSquared': 0.95, 'coefficients': [1.0, 2.0]}
    result = extractAnalysisCoefficients(entry, threshold=0.9)
    assert result == [1.0, 2.0]


def test_extract_single_below_threshold_returns_nulls():
    entry = {'rSquared': 0.5, 'coefficients': [1.0, 2.0]}
    result = extractAnalysisCoefficients(entry, threshold=0.9)
    assert result == [None, None]


def test_extract_single_none_coefficients_returns_nulls():
    entry = {'rSquared': 0.99, 'coefficients': None}
    result = extractAnalysisCoefficients(entry, threshold=0.0)
    assert result == [None, None]


def test_extract_single_string_rsquared_is_coerced():
    entry = {'rSquared': '0.95', 'coefficients': [1.0, 2.0]}
    result = extractAnalysisCoefficients(entry, threshold=0.9)
    assert result == [1.0, 2.0]


def test_extract_single_invalid_string_rsquared_returns_nulls():
    entry = {'rSquared': 'bad', 'coefficients': [1.0, 2.0]}
    result = extractAnalysisCoefficients(entry, threshold=0.0)
    assert result == [None, None]


def test_extract_single_polynomial_below_threshold_returns_three_nulls():
    entry = {'rSquared': 0.1, 'coefficients': [1.0, 2.0, 3.0]}
    result = extractAnalysisCoefficients(entry, threshold=0.9, regress_algo='polynomial')
    assert result == [None, None, None]


# ---------------------------------------------------------------------------
# extractAnalysisCoefficients — list of dicts
# ---------------------------------------------------------------------------

def test_extract_list_returns_list_of_results():
    entries = [
        {'rSquared': 0.95, 'coefficients': [1.0, 2.0]},
        {'rSquared': 0.5,  'coefficients': [3.0, 4.0]},
    ]
    result = extractAnalysisCoefficients(entries, threshold=0.9)
    assert result[0] == [1.0, 2.0]
    assert result[1] == [None, None]


def test_extract_invalid_type_raises():
    with pytest.raises(Exception):
        extractAnalysisCoefficients('not_valid', threshold=0.9)


# ---------------------------------------------------------------------------
# replace_empty
# ---------------------------------------------------------------------------

def test_replace_empty_none_becomes_none_string():
    assert replace_empty(None) == 'NONE'


def test_replace_empty_empty_string_becomes_none_string():
    assert replace_empty('') == 'NONE'


def test_replace_empty_empty_list_stays_empty():
    # replace_empty iterates the list, so an empty list yields an empty list.
    assert replace_empty([]) == []


def test_replace_empty_empty_dict_stays_empty():
    # Same reasoning: iterating an empty dict yields an empty dict.
    assert replace_empty({}) == {}


def test_replace_empty_non_empty_value_unchanged():
    assert replace_empty(42) == 42
    assert replace_empty('hello') == 'hello'
    assert replace_empty([1, 2]) == [1, 2]


def test_replace_empty_nested_dict():
    result = replace_empty({'a': None, 'b': {'c': ''}})
    assert result == {'a': 'NONE', 'b': {'c': 'NONE'}}


def test_replace_empty_nested_list():
    # Nested empty list iterates to [] (not "NONE") — leaf check is only for scalars.
    result = replace_empty([None, '', []])
    assert result == ['NONE', 'NONE', []]


def test_replace_empty_mixed_nested():
    result = replace_empty({'key': [None, 1, '']})
    assert result == {'key': ['NONE', 1, 'NONE']}
