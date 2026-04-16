import pytest
import os
from src import file_path, mode, quantity, range, get_next_filename

def test_file_path_directory():
    # Test getting directory (should be root by default in src/file_path.py)
    # The current_directory is set at import time.
    directory = file_path.get_directory()
    assert os.path.isabs(directory)

def test_browse_directory(tmp_path):
    # Create a test directory
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    
    result = file_path.browse_directory(str(test_dir))
    assert result == str(test_dir).replace('\\', '\\\\')
    assert file_path.get_directory() == str(test_dir)

def test_get_parent_directory():
    path = "/path/to/parent/child"
    # Note: os.path.abspath will normalize the path based on current OS
    parent = file_path.get_parent_directory(path)
    assert "parent" in parent
    assert "child" not in parent

def test_get_child_directories(tmp_path):
    # Create children
    (tmp_path / "child1").mkdir()
    (tmp_path / "child2").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "_internal").mkdir()
    
    children = file_path.get_child_directories(str(tmp_path))
    assert len(children) == 2
    assert any("child1" in c for c in children)
    assert any("child2" in c for c in children)
    assert not any(".hidden" in c for c in children)
    assert not any("_internal" in c for c in children)

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
