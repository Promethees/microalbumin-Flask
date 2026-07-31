"""Non-numeric value tokens: INF must be recorded, never silently coerced.

A dark cuvette makes the device report an infinite absorbance for that channel
(firmware ``Absorbance.channel_value``). Before the INF token the device wrote
Python's ``inf``, which matched no row pattern here — so the row was dropped
whole and the healthy channels went with it, leaving an empty session file.
"""

import re

import pytest

import sentinels
from math_ops import map_duplicates, calculate_kinetics_quantities


def _timeseries_validator():
    from routes.file_routes import _SCHEMA_VALIDATORS
    from file_path import CSV_SCHEMA_TIMESERIES, CSV_SCHEMA_TIMESERIES_TURN
    return (_SCHEMA_VALIDATORS[CSV_SCHEMA_TIMESERIES]['data'],
            _SCHEMA_VALIDATORS[CSV_SCHEMA_TIMESERIES_TURN]['data'])


def _logger_data_pattern():
    import log_cdc_data
    collector = log_cdc_data.CDCDataCollector.__new__(log_cdc_data.CDCDataCollector)
    log_cdc_data.CDCDataCollector.__init__(collector, base_dir="/tmp")
    return collector.data_pattern


@pytest.mark.parametrize("value", ["INF", "-INF", "inf", "-inf", "OVFL", "NONE"])
def test_tokens_are_sentinels_and_never_numbers(value):
    assert sentinels.is_sentinel(value)
    assert sentinels.to_number(value) is None


def test_to_number_keeps_real_numbers_and_rejects_infinities():
    assert sentinels.to_number("-4.120") == pytest.approx(-4.12)
    assert sentinels.to_number(0) == 0.0
    assert sentinels.to_number("") is None
    assert sentinels.to_number("Infinity") is None      # float() would accept it
    assert sentinels.to_number("nan") is None
    assert sentinels.to_number(float("inf")) is None


def test_logger_accepts_a_row_carrying_inf():
    pattern = _logger_data_pattern()
    # One dark channel among three good ones: the row must still be recorded.
    assert re.match(pattern, "1,-4.120,INF,-4.149,-4.152")
    assert re.match(pattern, "0.00,INF")
    assert re.match(pattern, "1,-4.120,inf,-4.149,-4.152")   # pre-token firmware
    assert re.match(pattern, "1,-4.120,NONE,-4.149,OVFL")
    assert not re.match(pattern, "1,-4.120,oops,-4.149")


def test_upload_schemas_accept_inf():
    timeseries, turn = _timeseries_validator()
    assert re.match(timeseries, "0.00,-4.120,INF")
    assert re.match(timeseries, "0.00,-4.120,inf")
    assert re.match(turn, "1,-4.120,INF")
    assert not re.match(turn, "1,-4.120,INFINITE")


def test_fits_skip_inf_instead_of_exploding():
    x = [1, 2, 3, 4]
    y = ["0.100", "INF", "0.300", "0.400"]

    px, py = map_duplicates(x, y)
    assert px == [1, 3, 4]
    assert py == pytest.approx([0.1, 0.3, 0.4])

    px, py = map_duplicates(x, y, keep_gaps=True)
    assert px == [1, 2, 3, 4]
    assert py[1] is None

    # The INF point is skipped, so the fit is the one the three real points give
    # (maxRate comes back pre-formatted as a string).
    result = calculate_kinetics_quantities(x, y, window_size=2)
    clean = calculate_kinetics_quantities(x, ["0.100", "0.200", "0.300", "0.400"], window_size=2)
    assert result["slope"] == pytest.approx(clean["slope"])
    assert float(result["maxRate"]) == pytest.approx(float(clean["maxRate"]))
