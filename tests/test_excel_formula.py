import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from excel_formula import excel_formula, formulas_from_content


def test_linear_formula():
    assert excel_formula('linear', {'a': 2, 'b': -3}) == '=(2)*A1+(-3)'


def test_polynomial_formula():
    assert excel_formula('polynomial', {'a': 1, 'b': -2, 'c': 0.5}) == '=(1)*A1^2+(-2)*A1+(0.5)'


def test_logarithmic_formula():
    assert excel_formula('logarithmic', {'a': 1.5, 'b': 2, 'c': -1}) == '=(1.5)*LN(A1+(2))+(-1)'


def test_exponential_formula():
    assert excel_formula('exponential', {'a': 0.1, 'b': 0.3, 'c': 4}) == '=(0.1)*EXP((0.3)*A1)+(4)'


def test_michaelis_menten_formula():
    assert excel_formula('Michaelis-Menten', {'VMax': 10, 'Km': 2.5}) == '=((2.5)*A1)/((10)-A1)'


def test_custom_cell_reference():
    assert excel_formula('linear', {'a': 2, 'b': 1}, cell='B2') == '=(2)*B2+(1)'


def test_negative_coefficients_are_parenthesised():
    # Wrapping in parens keeps a negative valid Excel syntax (never "+-").
    f = excel_formula('linear', {'a': -0.5, 'b': -10})
    assert '+(-10)' in f and '(-0.5)' in f


def test_missing_coefficient_returns_none():
    assert excel_formula('linear', {'a': 'NONE', 'b': 1}) is None
    assert excel_formula('polynomial', {'a': 1, 'b': 2}) is None  # missing c
    assert excel_formula('Michaelis-Menten', {'VMax': 10}) is None  # missing Km


def test_unknown_algo_returns_none():
    assert excel_formula('sigmoid', {'a': 1, 'b': 2}) is None


def test_formulas_from_content_single():
    out = formulas_from_content({'fit_coef': {'a': 2, 'b': 1}, 'fit_type': 'linear'}, 'linear')
    assert out == [{'label': None, 'formula': '=(2)*A1+(1)'}]


def test_formulas_from_content_multi_source():
    content = {
        'source_1': {'fit_coef': {'a': 2, 'b': 1}},
        'source_2': {'fit_coef': {'a': 3, 'b': 0}},
        'fit_type': 'linear', 'for_meas': 'ABS',
    }
    out = formulas_from_content(content, 'linear', 'B2')
    assert {'label': 'source_1', 'formula': '=(2)*B2+(1)'} in out
    assert {'label': 'source_2', 'formula': '=(3)*B2+(0)'} in out
    assert len(out) == 2  # metadata keys skipped


def test_formulas_from_content_null_for_missing_fit():
    out = formulas_from_content({'fit_coef': {'a': 'NONE', 'b': 'NONE'}}, 'linear')
    assert out == [{'label': None, 'formula': None}]
