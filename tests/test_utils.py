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
