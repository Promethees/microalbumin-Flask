import pytest
import os
import json
import io
import csv
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
    csv_content = "Concentration,maxRate,Slope,Sat,Time To Sat\n10,0.5,0.1,1.0,20\n5,0.2,0.05,0.5,10\n"
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)
    
    measure.sort_csv_file(str(csv_file), "kinetics")
    
    sorted_content = csv_file.read_text()
    lines = sorted_content.strip().split("\n")
    assert lines[1].startswith("5.0") or lines[1].startswith("5,")

def test_export_data_helpers():
    meta = {'Measurement': 'ABS', 'MeasUnit': 'AU', 'TimeUnit': None, 'MeasMode': None}
    assert export_data.is_metadata_consistent(meta, "ABS", "AU", None, None) is True

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


# ---------------------------------------------------------------------------
# export_cal_json — 2D coefficients and error paths
# ---------------------------------------------------------------------------

def test_process_json_coef_2d_success():
    result = export_cal_json.processJSONCoef(
        ["maxRate", "slope"],
        [[1.0, 2.0], [3.0, 4.0]],
        "linear"
    )
    assert "maxrate" in result
    assert result["maxrate"]["fit_coef"]["a"] == 1.0
    assert result["slope"]["fit_coef"]["a"] == 3.0


def test_process_json_coef_2d_length_mismatch_raises():
    with pytest.raises(ValueError, match="same length"):
        export_cal_json.processJSONCoef(["p1"], [[1.0, 2.0], [3.0, 4.0]], "linear")


def test_process_json_coef_invalid_cal_params_type_raises():
    with pytest.raises(ValueError):
        export_cal_json.processJSONCoef("not_a_list", [1.0, 2.0], "linear")


def test_process_json_coef_too_few_coefficients_raises():
    with pytest.raises(ValueError, match="at least 2"):
        export_cal_json.processJSONCoef(["p1"], [1.0], "linear")


def test_process_json_coef_mixed_1d_2d_raises():
    with pytest.raises(ValueError):
        export_cal_json.processJSONCoef(["p1", "p2"], [1.0, [2.0, 3.0]], "linear")


# ---------------------------------------------------------------------------
# export_cal_json.extractAnalysisCoefficients
# ---------------------------------------------------------------------------

def test_extract_analysis_coefs_above_threshold_returns_coefs():
    entry = {"rSquared": 0.99, "coefficients": [1.0, 2.0]}
    result = export_cal_json.extractAnalysisCoefficients(entry, threshold=0.9)
    assert result == [1.0, 2.0]


def test_extract_analysis_coefs_below_threshold_returns_nones():
    entry = {"rSquared": 0.5, "coefficients": [1.0, 2.0]}
    result = export_cal_json.extractAnalysisCoefficients(entry, threshold=0.9)
    assert all(v is None for v in result)


def test_extract_analysis_coefs_none_coefficients_returns_nones():
    entry = {"rSquared": 0.99, "coefficients": None}
    result = export_cal_json.extractAnalysisCoefficients(entry, threshold=0.9)
    assert all(v is None for v in result)


def test_extract_analysis_coefs_string_rsquared_is_coerced():
    entry = {"rSquared": "0.95", "coefficients": [1.0, 2.0]}
    result = export_cal_json.extractAnalysisCoefficients(entry, threshold=0.9)
    assert result == [1.0, 2.0]


def test_extract_analysis_coefs_list_of_entries():
    entries = [
        {"rSquared": 0.99, "coefficients": [1.0, 2.0]},
        {"rSquared": 0.3, "coefficients": [3.0, 4.0]},
    ]
    result = export_cal_json.extractAnalysisCoefficients(entries, threshold=0.9)
    assert result[0] == [1.0, 2.0]
    assert all(v is None for v in result[1])


def test_extract_analysis_coefs_polynomial_below_threshold_returns_three_nones():
    entry = {"rSquared": 0.1, "coefficients": [1.0, 2.0, 3.0]}
    result = export_cal_json.extractAnalysisCoefficients(entry, threshold=0.9, regress_algo="polynomial")
    assert result == [None, None, None]


def test_extract_analysis_coefs_invalid_input_raises():
    with pytest.raises(Exception):
        export_cal_json.extractAnalysisCoefficients("not_a_dict_or_list", threshold=0.0)


# ---------------------------------------------------------------------------
# export_data helpers
# ---------------------------------------------------------------------------

def test_is_metadata_consistent_mismatch_returns_false():
    meta = {'Measurement': 'ABS', 'MeasUnit': 'AU', 'TimeUnit': None, 'MeasMode': None}
    assert export_data.is_metadata_consistent(meta, "FLUOR", "AU", None, None) is False


def test_write_metadata_writes_all_fields():
    output = io.StringIO()
    export_data.write_metadata(output, "ABS", "AU", "minutes", "kinetics")
    result = output.getvalue()
    assert "# Measurement: ABS" in result
    assert "# MeasUnit: AU" in result
    assert "# TimeUnit: minutes" in result
    assert "# MeasMode: kinetics" in result


def test_write_headers_kinetics():
    output = io.StringIO()
    writer = csv.writer(output)
    export_data.write_headers(writer, "kinetics")
    assert "maxRate" in output.getvalue()
    assert "Concentration" in output.getvalue()


def test_write_headers_point():
    output = io.StringIO()
    writer = csv.writer(output)
    export_data.write_headers(writer, "point")
    assert "Value" in output.getvalue()
    assert "TimePoint" in output.getvalue()


def test_extract_single_entry_kinetics():
    data = {'con': 1.0, 'maxrate': 0.5, 'slope': 0.1, 'sat': 1.0, 'timeSat': 20}
    result = export_data.extract_single_entry(data, "kinetics")
    assert result[0] == 1.0
    assert result[1] == 0.5
    assert len(result) == 5


def test_extract_single_entry_point():
    data = {'con': 2.0, 'estValue': 0.7, 'timePoint': 5.0}
    result = export_data.extract_single_entry(data, "point")
    assert result[0] == 2.0
    assert result[1] == 0.7
    assert result[2] == 5.0


def test_extract_single_entry_missing_keys_return_none_placeholder():
    result = export_data.extract_single_entry({}, "kinetics")
    assert result[0] == 'NONE'


def test_sort_csv_content_sorts_ascending_by_concentration():
    content = "# Measurement: ABS\n# MeasUnit: AU\nConcentration,Value\n10,0.9\n2,0.3\n5,0.6"
    result = export_data.sort_csv_content(content)
    data_lines = [l for l in result.splitlines() if not l.startswith('#') and l.strip()]
    assert data_lines[1].startswith('2')
    assert data_lines[3].startswith('10')


def test_sort_csv_content_no_data_lines_unchanged():
    content = "# Measurement: ABS\n"
    assert export_data.sort_csv_content(content) == content


# ---------------------------------------------------------------------------
# file.get_dynamic_data — JSON and error paths
# ---------------------------------------------------------------------------

def test_get_dynamic_data_file_not_found():
    res = file.get_dynamic_data("/nonexistent/path/data.csv")
    assert res['error'] == 'File not found'
    assert res['data'] == []


def test_get_dynamic_data_json_file(tmp_path):
    json_file = tmp_path / "data.json"
    json_file.write_text('[{"Unit": "AU", "x": 1}]')
    res = file.get_dynamic_data(str(json_file))
    assert res['error'] is None
    assert res['unit'] == "AU"
    assert len(res['data']) == 1


def test_get_dynamic_data_json_single_object(tmp_path):
    json_file = tmp_path / "data.json"
    json_file.write_text('{"MeasUnit": "mg/L", "val": 0.5}')
    res = file.get_dynamic_data(str(json_file))
    assert res['unit'] == "mg/L"


def test_get_dynamic_data_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json}")
    res = file.get_dynamic_data(str(bad))
    assert res['error'] is not None
    assert 'Invalid JSON' in res['error']


def test_get_dynamic_data_unsupported_type(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("some data")
    res = file.get_dynamic_data(str(f))
    assert res['error'] == 'Unsupported file type'


# ---------------------------------------------------------------------------
# file.merge_csv_files — error paths
# ---------------------------------------------------------------------------

def test_merge_csv_files_file_not_found(tmp_path):
    success, msg = file.merge_csv_files(
        ["/nonexistent.csv"], str(tmp_path / "out.csv")
    )
    assert success is False
    assert "not found" in msg.lower()


def test_merge_csv_files_no_common_key(tmp_path):
    f1 = tmp_path / "f1.csv"
    f1.write_text("ColA,ColB\n1,2\n")
    f2 = tmp_path / "f2.csv"
    f2.write_text("ColX,ColY\n3,4\n")
    success, msg = file.merge_csv_files([str(f1), str(f2)], str(tmp_path / "out.csv"))
    assert success is False
    assert "common key" in msg.lower()


def test_merge_csv_files_concentration_join_key(tmp_path):
    f1 = tmp_path / "f1.csv"
    f1.write_text("Concentration,Value\n1,0.1\n2,0.2\n")
    f2 = tmp_path / "f2.csv"
    f2.write_text("Concentration,Value\n1,0.3\n2,0.4\n")
    out = tmp_path / "out.csv"
    success, msg = file.merge_csv_files([str(f1), str(f2)], str(out))
    assert success is True
    content = out.read_text()
    assert "Concentration" in content


# ---------------------------------------------------------------------------
# file_operations.remove_csv_columns — error paths
# ---------------------------------------------------------------------------

def test_remove_csv_columns_file_not_found():
    success, msg = file_operations.remove_csv_columns("/nonexistent.csv", ["Value:1"])
    assert success is False
    assert "does not exist" in msg


def test_remove_csv_columns_cannot_remove_timestamp(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("Timestamp,Value:1\n0,0.5\n")
    success, msg = file_operations.remove_csv_columns(str(f), ["Timestamp"])
    assert success is False
    assert "Timestamp" in msg


def test_remove_csv_columns_no_timestamp_column(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("Concentration,Value:1\n1,0.5\n")
    success, msg = file_operations.remove_csv_columns(str(f), ["Value:1"])
    assert success is False
    assert "Timestamp" in msg


def test_remove_csv_columns_no_value_columns(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("Timestamp,Concentration\n0,1\n")
    success, msg = file_operations.remove_csv_columns(str(f), ["Concentration"])
    assert success is False
    assert "Value:" in msg


def test_remove_csv_columns_removing_all_value_cols(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("Timestamp,Value:1\n0,0.5\n")
    success, msg = file_operations.remove_csv_columns(str(f), ["Value:1"])
    assert success is False
    assert "Cannot remove all" in msg


# ---------------------------------------------------------------------------
# measure._safe_float
# ---------------------------------------------------------------------------

def test_safe_float_none_returns_default():
    assert measure._safe_float(None) == 0.0


def test_safe_float_non_numeric_string_returns_default():
    assert measure._safe_float("NONE") == 0.0


def test_safe_float_valid_string():
    assert measure._safe_float("3.14") == pytest.approx(3.14)


def test_safe_float_custom_default():
    assert measure._safe_float("bad", default=99.0) == 99.0


# ---------------------------------------------------------------------------
# measure.sort_csv_file — point and fallback modes
# ---------------------------------------------------------------------------

def test_sort_csv_file_point_mode(tmp_path):
    content = (
        "# Measurement: ABS\n"
        "Concentration,Value,TimePoint\n"
        "10,0.5,2.0\n"
        "5,0.2,1.0\n"
    )
    f = tmp_path / "test.csv"
    f.write_text(content)
    measure.sort_csv_file(str(f), "point")
    lines = [l for l in f.read_text().splitlines() if not l.startswith('#') and l.strip()]
    assert lines[1].startswith('5')


def test_sort_csv_file_unknown_mode_sorts_by_first_col(tmp_path):
    content = "# Measurement: ABS\nConcentration,Value\n10,0.9\n2,0.3\n"
    f = tmp_path / "test.csv"
    f.write_text(content)
    measure.sort_csv_file(str(f), "unknown")
    lines = [l for l in f.read_text().splitlines() if not l.startswith('#') and l.strip()]
    assert lines[1].startswith('2')
