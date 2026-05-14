import pytest
import os
import os
import json
import io
from src import file, file_operations, measure, export_data, export_cal_json

def test_get_file_list(tmp_path):
    (tmp_path / "test1.csv").write_text("data")
    (tmp_path / "test2.txt").write_text("data")
    (tmp_path / "test3.csv").write_text("data")
    
    files = file.get_file_list(str(tmp_path))
    assert len(files) == 2
    assert "test1.csv" in files
    assert "test3.csv" in files

def test_get_dynamic_data_csv(tmp_path):
    csv_content = """# Measurement: ABS
# MeasUnit: AU
Timestamp,Value:1
0,0.5
1,0.6
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)
    
    res = file.get_dynamic_data(str(csv_file))
    assert res['unit'] == "AU"
    assert len(res['data']) == 2
    assert res['num_sources'] == 1
    assert res['metadata']['Measurement'] == "ABS"

def test_replace_empty():
    data = {"a": "", "b": [], "c": {"d": None}, "e": [1, None]}
    expected = {"a": "NONE", "b": "NONE", "c": {"d": "NONE"}, "e": [1, "NONE"]}
    assert file.replace_empty(data) == expected

def test_merge_csv_files(tmp_path):
    f1 = tmp_path / "f1.csv"
    f1.write_text("# Measurement: ABS\nTimestamp,Value:1\n0,0.1\n")
    f2 = tmp_path / "f2.csv"
    f2.write_text("# Measurement: ABS\nTimestamp,Value:1\n0,0.2\n")
    out = tmp_path / "out.csv"

    success, msg = file.merge_csv_files([str(f1), str(f2)], str(out))
    assert success is True

    merged_content = out.read_text()
    assert "Value:1" in merged_content
    assert "Value:2" in merged_content
    assert "0,0.1,0.2" in merged_content or "0,0.1,0.2" in merged_content.replace(" ", "")

def test_merge_csv_files_three(tmp_path):
    f1 = tmp_path / "f1.csv"
    f1.write_text("# Measurement: ABS\nTimestamp,Value:1\n0,0.1\n1,0.2\n")
    f2 = tmp_path / "f2.csv"
    f2.write_text("# Measurement: ABS\nTimestamp,Value:1\n0,0.3\n1,0.4\n")
    f3 = tmp_path / "f3.csv"
    f3.write_text("# Measurement: ABS\nTimestamp,Value:1\n0,0.5\n1,0.6\n")
    out = tmp_path / "out.csv"

    success, msg = file.merge_csv_files([str(f1), str(f2), str(f3)], str(out))
    assert success is True

    merged_content = out.read_text()
    assert "Value:1" in merged_content
    assert "Value:2" in merged_content
    assert "Value:3" in merged_content

def test_remove_csv_columns(tmp_path):
    csv_content = "# Meta\nTimestamp,Value:1,Value:2\n0,0.1,0.2\n"
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)
    
    success, msg = file_operations.remove_csv_columns(str(csv_file), ["Value:1"])
    assert success is True
    
    new_content = csv_file.read_text()
    assert "Value:1" in new_content
    assert "Value:2" not in new_content
    assert "0,0.2" in new_content

def test_sort_csv_file(tmp_path):
    csv_content = "Concentration,maxRate,Slope,Sat,TimeToSat\n10,0.5,0.1,1.0,20\n5,0.2,0.05,0.5,10\n"
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)
    
    measure.sort_csv_file(str(csv_file), "kinetics")
    
    sorted_content = csv_file.read_text()
    lines = sorted_content.strip().split("\n")
    assert lines[1].startswith("5.0") or lines[1].startswith("5,")

def test_export_data_helpers():
    meta = "# Measurement: ABS\n# MeasUnit: AU\n"
    parsed = export_data.parse_metadata(meta)
    assert parsed['Measurement'] == "ABS"
    assert export_data.is_metadata_consistent(parsed, "ABS", "AU", None, None) is True

def test_export_cal_json_logic():
    coefs = [1.0, 2.0, 3.0]
    res = export_cal_json.processJSONCoef(["p1"], coefs, "linear")
    assert res['fit_coef']['a'] == 1.0
    assert res['fit_coef']['b'] == 2.0
    assert res['fit_coef']['c'] == 3.0
    
    # Michaelis-Menten positive: exactly 2 coefficients
    res_mm = export_cal_json.processJSONCoef(["p1"], [1.0, 2.0], "Michaelis-Menten")
    assert res_mm['fit_coef']['VMax'] == 1.0
    assert res_mm['fit_coef']['Km'] == 2.0

    # Michaelis-Menten negative: 3 coefficients must be rejected
    with pytest.raises(ValueError, match="Michaelis-Menten requires exactly 2 coefficients"):
        export_cal_json.processJSONCoef(["p1"], [1.0, 2.0, 3.0], "Michaelis-Menten")
