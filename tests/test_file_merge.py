import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from file_merge import merge_csv_contents

_TS_A = (
    "# Measurement: ABS\n"
    "# Unit: AU\n"
    "Timestamp,Value:1\n"
    "0,0.1\n"
    "1,0.2\n"
)

_TS_B = (
    "# Measurement: ABS\n"
    "# Unit: AU\n"
    "Timestamp,Value:1\n"
    "0,0.3\n"
    "2,0.4\n"
)

_CAL_A = (
    "# Measurement: ABS\n"
    "# MeasUnit: AU\n"
    "Concentration,Value,TimePoint\n"
    "0,0.0,2\n"
    "10,0.5,2\n"
)

_CAL_B = (
    "# Measurement: ABS\n"
    "# MeasUnit: AU\n"
    "Concentration,Value,TimePoint\n"
    "5,0.25,2\n"
    "20,1.0,2\n"
)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_empty_content_returns_error():
    success, msg = merge_csv_contents(["# only meta\n", _TS_A])
    assert not success
    assert "empty" in msg.lower() or "invalid" in msg.lower()


def test_no_common_key_returns_error():
    # Mixing timeseries and calibration → no shared join key.
    success, msg = merge_csv_contents([_TS_A, _CAL_A])
    assert not success
    assert "common key" in msg.lower()


# ---------------------------------------------------------------------------
# Timeseries merge (outer join on Timestamp)
# ---------------------------------------------------------------------------

def test_timeseries_merge_renames_value_columns():
    success, result = merge_csv_contents([_TS_A, _TS_B])
    assert success
    assert 'Value:1' in result
    assert 'Value:2' in result


def test_timeseries_merge_outer_join_fills_none_for_missing():
    success, result = merge_csv_contents([_TS_A, _TS_B])
    assert success
    # Timestamp=1 is only in A; Timestamp=2 only in B → the other gets NONE.
    assert 'NONE' in result


def test_timeseries_merge_all_timestamps_present():
    success, result = merge_csv_contents([_TS_A, _TS_B])
    assert success
    lines = result.splitlines()
    data_lines = [l for l in lines if l and not l.startswith('#')]
    timestamps = {row.split(',')[0] for row in data_lines[1:]}
    assert '0' in timestamps
    assert '1' in timestamps
    assert '2' in timestamps


def test_timeseries_merge_deduplicates_metadata():
    # Both files share the same metadata lines.
    success, result = merge_csv_contents([_TS_A, _TS_B])
    assert success
    assert result.count('# Measurement: ABS') == 1


# ---------------------------------------------------------------------------
# Calibration merge (concat on Concentration)
# ---------------------------------------------------------------------------

def test_calibration_merge_concatenates_rows():
    success, result = merge_csv_contents([_CAL_A, _CAL_B])
    assert success
    lines = result.splitlines()
    data_lines = [l for l in lines if l and not l.startswith('#')]
    # header + 4 data rows
    assert len(data_lines) == 5


def test_calibration_merge_sorted_by_concentration():
    success, result = merge_csv_contents([_CAL_B, _CAL_A])
    assert success
    lines = result.splitlines()
    data_lines = [l for l in lines if l and not l.startswith('#')]
    concentrations = [float(row.split(',')[0]) for row in data_lines[1:]]
    assert concentrations == sorted(concentrations)


def test_calibration_merge_preserves_metadata():
    success, result = merge_csv_contents([_CAL_A, _CAL_B])
    assert success
    assert '# Measurement: ABS' in result


# ---------------------------------------------------------------------------
# Single file (edge case)
# ---------------------------------------------------------------------------

def test_single_timeseries_file_succeeds():
    success, result = merge_csv_contents([_TS_A])
    assert success
    assert 'Value:1' in result
