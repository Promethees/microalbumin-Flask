import pytest
import os
from unittest.mock import patch
import file_path
import mode
import quantity
import range
import get_next_filename

def test_get_data_subfolders(tmp_path):
    (tmp_path / "child1").mkdir()
    (tmp_path / "child2").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "_internal").mkdir()

    with patch.object(file_path, 'DATA_ROOT', str(tmp_path)):
        subfolders = file_path.get_data_subfolders()
    names = [f["name"] for f in subfolders]
    assert "child1" in names
    assert "child2" in names
    assert ".hidden" not in names
    assert "_internal" not in names

def test_is_multi_value_header():
    valid = "Timestamp, Value:1, Value:2 "
    assert file_path.is_multi_value_timeseries_csv_header(valid) is True
    
    invalid = "Concentration, maxRate"
    assert file_path.is_multi_value_timeseries_csv_header(invalid) is False

def test_ui_getters():
    m = mode.get_mode_input()
    assert 'kinetics' in m['modes']
    
    q = quantity.get_quantity_input()
    assert 'maxRate' in q['quantities']
    
    r = range.get_range_input()
    assert r['value_start'] == 0
    assert 'seconds' in r['units']

def test_get_next_filename(tmp_path):
    base_dir = str(tmp_path)
    base_name = "test"
    file_type = ".csv"
    
    # Empty dir
    next_f = get_next_filename.get_next_filename(file_type, base_dir, base_name)
    assert os.path.basename(next_f) == "test_0.csv"
    
    # One file exists
    (tmp_path / "test_0.csv").write_text("data")
    next_f = get_next_filename.get_next_filename(file_type, base_dir, base_name)
    assert os.path.basename(next_f) == "test_1.csv"
    
    # Multiple files exist with gaps
    (tmp_path / "test_5.csv").write_text("data")
    next_f = get_next_filename.get_next_filename(file_type, base_dir, base_name)
    assert os.path.basename(next_f) == "test_6.csv"


# ---------------------------------------------------------------------------
# file_path.validate_in_data_root
# ---------------------------------------------------------------------------

def test_validate_in_data_root_inside(tmp_path):
    inner = str(tmp_path / "subdir" / "file.csv")
    with patch.object(file_path, 'DATA_ROOT', str(tmp_path)):
        result = file_path.validate_in_data_root(inner)
    assert result is not None
    assert result.startswith(str(tmp_path))


def test_validate_in_data_root_equals_root(tmp_path):
    with patch.object(file_path, 'DATA_ROOT', str(tmp_path)):
        result = file_path.validate_in_data_root(str(tmp_path))
    assert result is not None


def test_validate_in_data_root_outside(tmp_path, tmp_path_factory):
    other = str(tmp_path_factory.mktemp("other"))
    with patch.object(file_path, 'DATA_ROOT', str(tmp_path)):
        result = file_path.validate_in_data_root(other)
    assert result is None


# ---------------------------------------------------------------------------
# file_path.is_reserved_data_folder_name
# ---------------------------------------------------------------------------

def test_is_reserved_data_folder_name_matches_root_any_case():
    assert file_path.is_reserved_data_folder_name("root")
    assert file_path.is_reserved_data_folder_name("ROOT")
    assert file_path.is_reserved_data_folder_name("  Root  ")


def test_is_reserved_data_folder_name_allows_other_names():
    assert not file_path.is_reserved_data_folder_name("rootfolder")
    assert not file_path.is_reserved_data_folder_name("my_data")
    assert not file_path.is_reserved_data_folder_name("")
    assert not file_path.is_reserved_data_folder_name(None)


# ---------------------------------------------------------------------------
# file_path.parse_csv_metadata
# ---------------------------------------------------------------------------

def test_parse_csv_metadata_extracts_key_value_pairs():
    lines = ["# Measurement: ABS\n", "# MeasUnit: AU\n", "Timestamp,Value:1\n"]
    meta = file_path.parse_csv_metadata(lines)
    assert meta["Measurement"] == "ABS"
    assert meta["MeasUnit"] == "AU"
    assert len(meta) == 2


def test_parse_csv_metadata_empty_input():
    assert file_path.parse_csv_metadata([]) == {}


def test_parse_csv_metadata_no_metadata_lines():
    assert file_path.parse_csv_metadata(["Timestamp,Value:1\n", "0,0.5\n"]) == {}


def test_parse_csv_metadata_value_with_colon_preserved():
    lines = ["# URL: http://example.com\n"]
    meta = file_path.parse_csv_metadata(lines)
    assert meta["URL"] == "http://example.com"


# ---------------------------------------------------------------------------
# file_path.detect_csv_schema
# ---------------------------------------------------------------------------

def test_detect_csv_schema_timeseries():
    assert file_path.detect_csv_schema("Timestamp,Value:1") == file_path.CSV_SCHEMA_TIMESERIES


def test_detect_csv_schema_timeseries_multi_value():
    assert file_path.detect_csv_schema("Timestamp,Value:1,Value:2,Value:3") == file_path.CSV_SCHEMA_TIMESERIES


def test_detect_csv_schema_kinetics_cal():
    header = "Concentration,maxRate,Slope,Sat,Time To Sat"
    assert file_path.detect_csv_schema(header) == file_path.CSV_SCHEMA_KINETICS_CAL


def test_detect_csv_schema_point_cal():
    assert file_path.detect_csv_schema("Concentration,Value,TimePoint") == file_path.CSV_SCHEMA_POINT_CAL


def test_detect_csv_schema_unknown_returns_none():
    assert file_path.detect_csv_schema("Unknown,Col1,Col2") is None


def test_detect_csv_schema_strips_whitespace():
    assert file_path.detect_csv_schema("  Concentration,Value,TimePoint  ") == file_path.CSV_SCHEMA_POINT_CAL
