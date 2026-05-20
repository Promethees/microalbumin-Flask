import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from file_path import (
    parse_csv_metadata,
    detect_csv_schema,
    _is_timeseries_header,
    get_parent_directory,
    get_child_directories,
    CSV_SCHEMA_TIMESERIES,
    CSV_SCHEMA_KINETICS_CAL,
    CSV_SCHEMA_POINT_CAL,
)


# ---------------------------------------------------------------------------
# parse_csv_metadata
# ---------------------------------------------------------------------------

def test_parse_csv_metadata_basic():
    lines = ['# Measurement: ABSORBANCE', '# MeasUnit: AU', '# MeasMode: kinetics']
    result = parse_csv_metadata(lines)
    assert result == {'Measurement': 'ABSORBANCE', 'MeasUnit': 'AU', 'MeasMode': 'kinetics'}


def test_parse_csv_metadata_skips_non_hash_lines():
    lines = ['# Key: Value', 'Concentration,maxRate']
    result = parse_csv_metadata(lines)
    assert 'Concentration' not in result
    assert result == {'Key': 'Value'}


def test_parse_csv_metadata_skips_hash_line_without_colon():
    lines = ['# no colon here', '# Key: Value']
    result = parse_csv_metadata(lines)
    assert result == {'Key': 'Value'}


def test_parse_csv_metadata_value_with_colon():
    # Value itself contains a colon — only the first colon is the separator.
    lines = ['# URL: http://example.com']
    result = parse_csv_metadata(lines)
    assert result['URL'] == 'http://example.com'


def test_parse_csv_metadata_empty_lines_returns_empty_dict():
    assert parse_csv_metadata([]) == {}


def test_parse_csv_metadata_strips_whitespace():
    lines = ['#   Key  :   Value  ']
    result = parse_csv_metadata(lines)
    assert result.get('Key') == 'Value'


# ---------------------------------------------------------------------------
# _is_timeseries_header
# ---------------------------------------------------------------------------

def test_is_timeseries_header_single_value_col():
    assert _is_timeseries_header('Timestamp,Value:1') is True


def test_is_timeseries_header_multiple_value_cols():
    assert _is_timeseries_header('Timestamp,Value:1,Value:2,Value:3') is True


def test_is_timeseries_header_wrong_first_col():
    assert _is_timeseries_header('Time,Value:1') is False


def test_is_timeseries_header_non_value_second_col():
    assert _is_timeseries_header('Timestamp,Rate:1') is False


def test_is_timeseries_header_only_timestamp():
    # Must have at least one Value:N column.
    assert _is_timeseries_header('Timestamp') is False


def test_is_timeseries_header_ignores_internal_spaces():
    assert _is_timeseries_header('Timestamp, Value:1') is True


# ---------------------------------------------------------------------------
# detect_csv_schema
# ---------------------------------------------------------------------------

def test_detect_csv_schema_timeseries():
    assert detect_csv_schema('Timestamp,Value:1,Value:2') == CSV_SCHEMA_TIMESERIES


def test_detect_csv_schema_kinetics_cal():
    assert detect_csv_schema('Concentration,maxRate,Slope,Sat,Time To Sat') == CSV_SCHEMA_KINETICS_CAL


def test_detect_csv_schema_kinetics_cal_with_spaces_around_comma():
    assert detect_csv_schema('Concentration , maxRate , Slope , Sat , Time To Sat') == CSV_SCHEMA_KINETICS_CAL


def test_detect_csv_schema_point_cal():
    assert detect_csv_schema('Concentration,Value,TimePoint') == CSV_SCHEMA_POINT_CAL


def test_detect_csv_schema_unknown_returns_none():
    assert detect_csv_schema('Unknown,Header,Columns') is None


def test_detect_csv_schema_empty_returns_none():
    assert detect_csv_schema('') is None


# ---------------------------------------------------------------------------
# get_parent_directory
# ---------------------------------------------------------------------------

def test_get_parent_directory_one_level():
    path = '/tmp/a/b/c'
    result = get_parent_directory(path, levels=1)
    assert result == '/tmp/a/b'


def test_get_parent_directory_two_levels():
    path = '/tmp/a/b/c'
    result = get_parent_directory(path, levels=2)
    assert result == '/tmp/a'


def test_get_parent_directory_empty_raises():
    with pytest.raises(ValueError):
        get_parent_directory('')


# ---------------------------------------------------------------------------
# get_child_directories
# ---------------------------------------------------------------------------

def test_get_child_directories_returns_subdirs():
    with tempfile.TemporaryDirectory() as tmp:
        sub1 = os.path.join(tmp, 'sub1')
        sub2 = os.path.join(tmp, 'sub2')
        os.makedirs(sub1)
        os.makedirs(sub2)
        # Also add a file to confirm only dirs are returned.
        open(os.path.join(tmp, 'file.txt'), 'w').close()

        children = get_child_directories(tmp)
        basenames = {os.path.basename(c) for c in children}
        assert 'sub1' in basenames
        assert 'sub2' in basenames
        assert 'file.txt' not in basenames


def test_get_child_directories_empty_dir():
    with tempfile.TemporaryDirectory() as tmp:
        assert get_child_directories(tmp) == []


def test_get_child_directories_non_dir_raises():
    with pytest.raises(ValueError):
        get_child_directories('/nonexistent/path/that/does/not/exist')
