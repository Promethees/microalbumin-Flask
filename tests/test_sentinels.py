"""Non-numeric value tokens: INF must survive an upload, never become a number.

A dark cuvette makes the device report an infinite absorbance for that channel,
and the desktop app records it as the ``INF`` token (firmware predating the
token wrote Python's ``inf``). The web app used to accept neither, so a file the
desktop had just written was rejected on upload — and a row is validated whole,
so the healthy channels in it went too.

The other half of the rule is that the token must never reach a fit: Python's
``float("INF")`` succeeds and returns an infinity, which poisons the curve, the
JSON response (``Infinity`` is not valid JSON) and every export downstream.
"""

import re

import pytest

import sentinels
from math_ops import map_duplicates, calculate_kinetics_quantities
from validators import _SCHEMA_VALIDATORS
from file_path import (CSV_SCHEMA_TIMESERIES, CSV_SCHEMA_TIMESERIES_TURN,
                       CSV_SCHEMA_KINETICS_CAL)


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


def test_upload_schemas_accept_inf():
    timeseries = _SCHEMA_VALIDATORS[CSV_SCHEMA_TIMESERIES]['data']
    turn = _SCHEMA_VALIDATORS[CSV_SCHEMA_TIMESERIES_TURN]['data']
    assert re.match(timeseries, "0.00,-4.120,INF")
    assert re.match(timeseries, "0.00,-4.120,inf")       # pre-token firmware
    assert re.match(timeseries, "0.00,-4.120,NONE,OVFL")
    assert re.match(turn, "1,-4.120,INF")
    assert not re.match(turn, "1,-4.120,INFINITE")
    assert not re.match(timeseries, "0.00,oops")


def test_kinetics_calibration_accepts_a_signed_whole_sat():
    """Sat is signed: a curve fitted against a falling signal plateaus below
    zero, and the desktop writer emits it with no decimal part."""
    kinetics_cal = _SCHEMA_VALIDATORS[CSV_SCHEMA_KINETICS_CAL]['data']
    assert re.match(kinetics_cal, "5,0.1,0.2,-0.5,12")
    assert re.match(kinetics_cal, "5,0.1,0.2,2,12")
    assert re.match(kinetics_cal, "5,0.1,0.2,0.5,12")
    assert re.match(kinetics_cal, "NONE,NONE,NONE,NONE,NONE")
    assert not re.match(kinetics_cal, "5,0.1,0.2,abc,12")


def test_fits_skip_inf_instead_of_exploding():
    x = [1, 2, 3, 4]
    y = ["0.100", "INF", "0.300", "0.400"]

    px, py = map_duplicates(x, y)
    assert px == [1, 3, 4]
    assert py == pytest.approx([0.1, 0.3, 0.4])

    px, py = map_duplicates(x, y, keep_gaps=True)
    assert px == [1, 2, 3, 4]
    assert py[1] is None

    # The INF point is skipped, so the fit is the one the three real points give.
    result = calculate_kinetics_quantities(x, y, window_size=2)
    clean = calculate_kinetics_quantities(x, ["0.100", "0.200", "0.300", "0.400"],
                                          window_size=2)
    assert result["slope"] == pytest.approx(clean["slope"])
