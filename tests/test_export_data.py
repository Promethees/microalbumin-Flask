import sys
import os
import csv
import io
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from export_data import (
    parse_metadata,
    is_metadata_consistent,
    write_metadata,
    write_headers,
    extract_single_entry,
    sort_csv_content,
    get_user_lock,
)


# ---------------------------------------------------------------------------
# parse_metadata
# ---------------------------------------------------------------------------

def test_parse_metadata_basic():
    content = "# Measurement: ABSORBANCE\n# MeasUnit: AU\n# MeasMode: kinetics\n"
    result = parse_metadata(content)
    assert result == {'Measurement': 'ABSORBANCE', 'MeasUnit': 'AU', 'MeasMode': 'kinetics'}


def test_parse_metadata_ignores_data_lines():
    content = "# Measurement: ABS\nConcentration,Value\n0,0.1\n"
    result = parse_metadata(content)
    assert 'Concentration' not in result


def test_parse_metadata_value_with_colon():
    content = "# URL: http://example.com\n"
    result = parse_metadata(content)
    assert result['URL'] == 'http://example.com'


def test_parse_metadata_empty_returns_empty_dict():
    assert parse_metadata('') == {}


def test_parse_metadata_no_meta_lines_returns_empty_dict():
    assert parse_metadata('Concentration,Value\n0,0.1\n') == {}


# ---------------------------------------------------------------------------
# is_metadata_consistent
# ---------------------------------------------------------------------------

def test_is_metadata_consistent_returns_true_when_matching():
    meta = {'Measurement': 'ABS', 'MeasUnit': 'AU', 'TimeUnit': 'min', 'MeasMode': 'kinetics'}
    assert is_metadata_consistent(meta, 'ABS', 'AU', 'min', 'kinetics') is True


def test_is_metadata_consistent_returns_false_on_mismatch():
    meta = {'Measurement': 'ABS', 'MeasUnit': 'AU', 'TimeUnit': 'min', 'MeasMode': 'kinetics'}
    assert is_metadata_consistent(meta, 'ABS', 'AU', 'sec', 'kinetics') is False


def test_is_metadata_consistent_missing_key_returns_false():
    assert is_metadata_consistent({}, 'ABS', 'AU', 'min', 'kinetics') is False


# ---------------------------------------------------------------------------
# write_metadata
# ---------------------------------------------------------------------------

def test_write_metadata_outputs_four_lines():
    buf = io.StringIO()
    write_metadata(buf, 'ABS', 'AU', 'min', 'kinetics')
    output = buf.getvalue()
    assert '# Measurement: ABS\n' in output
    assert '# MeasUnit: AU\n' in output
    assert '# TimeUnit: min\n' in output
    assert '# MeasMode: kinetics\n' in output


# ---------------------------------------------------------------------------
# write_headers
# ---------------------------------------------------------------------------

def test_write_headers_kinetics():
    buf = io.StringIO()
    writer = csv.writer(buf)
    write_headers(writer, 'kinetics')
    assert 'maxRate' in buf.getvalue()
    assert 'Concentration' in buf.getvalue()


def test_write_headers_point():
    buf = io.StringIO()
    writer = csv.writer(buf)
    write_headers(writer, 'point')
    assert 'Value' in buf.getvalue()
    assert 'TimePoint' in buf.getvalue()


# ---------------------------------------------------------------------------
# extract_single_entry
# ---------------------------------------------------------------------------

def test_extract_single_entry_kinetics():
    data = {'con': 10, 'maxrate': 0.5, 'slope': 0.1, 'sat': 1.0, 'timeSat': 20}
    row = extract_single_entry(data, 'kinetics')
    assert row[0] == 10
    assert row[1] == 0.5
    assert len(row) == 5


def test_extract_single_entry_point():
    data = {'con': 5, 'estValue': 0.25, 'timePoint': 2}
    row = extract_single_entry(data, 'point')
    assert row[0] == 5
    assert row[1] == 0.25
    assert len(row) == 3


def test_extract_single_entry_missing_keys_fallback_to_none_string():
    row = extract_single_entry({}, 'kinetics')
    assert all(v == 'NONE' for v in row)


# ---------------------------------------------------------------------------
# sort_csv_content
# ---------------------------------------------------------------------------

_UNSORTED_KINETICS = (
    "# Measurement: ABS\n"
    "# MeasMode: kinetics\n"
    "Concentration,maxRate,Slope,Sat,Time To Sat\n"
    "10,0.5,0.1,1.0,20\n"
    "0,0.0,0.0,0.0,0\n"
    "5,0.25,0.05,0.5,10\n"
)


def test_sort_csv_content_sorts_by_concentration():
    result = sort_csv_content(_UNSORTED_KINETICS)
    data_lines = [l for l in result.splitlines() if l and not l.startswith('#')]
    concentrations = [float(row.split(',')[0]) for row in data_lines[1:]]
    assert concentrations == sorted(concentrations)


def test_sort_csv_content_preserves_metadata():
    result = sort_csv_content(_UNSORTED_KINETICS)
    assert '# Measurement: ABS' in result
    assert '# MeasMode: kinetics' in result


def test_sort_csv_content_preserves_header_row():
    result = sort_csv_content(_UNSORTED_KINETICS)
    data_lines = [l for l in result.splitlines() if l and not l.startswith('#')]
    assert data_lines[0].startswith('Concentration')


def test_sort_csv_content_none_concentration_goes_to_end():
    content = (
        "Concentration,Value\n"
        "NONE,0.1\n"
        "0,0.0\n"
        "5,0.5\n"
    )
    result = sort_csv_content(content)
    lines = [l for l in result.splitlines() if l]
    last_data = lines[-1]
    assert last_data.startswith('NONE')


def test_sort_csv_content_no_data_rows_unchanged():
    content = "# meta\nConcentration,Value\n"
    result = sort_csv_content(content)
    assert 'Concentration,Value' in result


# ---------------------------------------------------------------------------
# get_user_lock
# ---------------------------------------------------------------------------

def test_get_user_lock_returns_lock():
    from threading import Lock
    lock = get_user_lock('user-abc')
    assert hasattr(lock, 'acquire') and hasattr(lock, 'release')


def test_get_user_lock_same_user_returns_same_lock():
    lock1 = get_user_lock('user-xyz')
    lock2 = get_user_lock('user-xyz')
    assert lock1 is lock2


def test_get_user_lock_different_users_return_different_locks():
    lock_a = get_user_lock('user-a')
    lock_b = get_user_lock('user-b')
    assert lock_a is not lock_b


# ---------------------------------------------------------------------------
# Concentration unit (# ConcenUnit)
# ---------------------------------------------------------------------------

def test_write_metadata_emits_concen_unit():
    buf = io.StringIO()
    write_metadata(buf, 'ABS', 'AU', 'min', 'kinetics', '%')
    assert '# ConcenUnit: %\n' in buf.getvalue()


def test_write_metadata_concen_unit_defaults_to_ng_ul():
    buf = io.StringIO()
    write_metadata(buf, 'ABS', 'AU', 'min', 'kinetics')
    assert '# ConcenUnit: ng/µL\n' in buf.getvalue()


def test_is_metadata_consistent_missing_concen_unit_treated_as_default():
    meta = {'Measurement': 'ABS', 'MeasUnit': 'AU', 'TimeUnit': 'min', 'MeasMode': 'kinetics'}
    assert is_metadata_consistent(meta, 'ABS', 'AU', 'min', 'kinetics', 'ng/µL') is True
    assert is_metadata_consistent(meta, 'ABS', 'AU', 'min', 'kinetics', 'nM') is False


def test_is_metadata_consistent_concen_unit_must_match():
    meta = {'Measurement': 'ABS', 'MeasUnit': 'AU', 'TimeUnit': 'min',
            'MeasMode': 'kinetics', 'ConcenUnit': 'nM'}
    assert is_metadata_consistent(meta, 'ABS', 'AU', 'min', 'kinetics', 'nM') is True
    assert is_metadata_consistent(meta, 'ABS', 'AU', 'min', 'kinetics', '%') is False


# ---------------------------------------------------------------------------
# Turn-based point calibration (Concentration,Value — no TimePoint)
# ---------------------------------------------------------------------------

def test_write_headers_point_turn_drops_timepoint():
    out = io.StringIO()
    write_headers(csv.writer(out), 'point', 'turn')
    assert out.getvalue().strip() == 'Concentration,Value'


def test_write_headers_point_time_keeps_timepoint():
    out = io.StringIO()
    write_headers(csv.writer(out), 'point', 'time')
    assert out.getvalue().strip() == 'Concentration,Value,TimePoint'


def test_write_headers_kinetics_ignores_x_axis():
    out = io.StringIO()
    write_headers(csv.writer(out), 'kinetics', 'turn')
    assert out.getvalue().strip() == 'Concentration,maxRate,Slope,Sat,Time To Sat'


def test_extract_single_entry_point_turn_two_columns():
    entry = {'con': '5', 'estValue': '0.42', 'timePoint': '2'}
    assert extract_single_entry(entry, 'point', 'turn') == ['5', '0.42']


def test_extract_single_entry_point_time_three_columns():
    entry = {'con': '5', 'estValue': '0.42', 'timePoint': '2'}
    assert extract_single_entry(entry, 'point', 'time') == ['5', '0.42', '2']


def test_extract_single_entry_defaults_to_time_axis():
    entry = {'con': '5', 'estValue': '0.42', 'timePoint': '2'}
    assert extract_single_entry(entry, 'point') == ['5', '0.42', '2']


def test_sort_csv_content_handles_two_column_turn_table():
    content = (
        "# MeasMode: point\n"
        "Concentration,Value\n"
        "10,0.5\n"
        "2,0.1\n"
    )
    sorted_content = sort_csv_content(content)
    rows = [l for l in sorted_content.splitlines() if l and not l.startswith('#')]
    assert rows == ['Concentration,Value', '2,0.1', '10,0.5']
