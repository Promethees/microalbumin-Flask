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

def test_get_file_meta(tmp_path):
    (tmp_path / "a.csv").write_text("data")
    (tmp_path / ".hidden.csv").write_text("data")
    (tmp_path / "skip.txt").write_text("data")

    meta = file.get_file_meta(str(tmp_path))
    assert set(meta.keys()) == {"a.csv"}
    assert meta["a.csv"]["mtime"] > 0
    # Default ("iso") display string follows the "YYYY-MM-DD HH:MM" pattern
    assert len(meta["a.csv"]["display"]) == 16
    assert meta["a.csv"]["display"][4] == "-"


def test_build_meta_handles_directories(tmp_path):
    # Report subjects are directories, not files
    (tmp_path / "subjectA").mkdir()
    (tmp_path / "subjectB").mkdir()
    meta = file.build_meta(str(tmp_path), ["subjectA", "subjectB"])
    assert set(meta.keys()) == {"subjectA", "subjectB"}
    assert meta["subjectA"]["mtime"] > 0
    assert len(meta["subjectA"]["display"]) == 16  # default iso


def test_build_meta_missing_entry_falls_back(tmp_path):
    meta = file.build_meta(str(tmp_path), ["does_not_exist"])
    assert meta["does_not_exist"] == {"mtime": 0, "display": ""}


def test_get_file_meta_time_format(tmp_path):
    (tmp_path / "a.csv").write_text("data")

    # date_only drops the time component
    d = file.get_file_meta(str(tmp_path), time_format="date_only")["a.csv"]["display"]
    assert len(d) == 10 and d[4] == "-"

    # eu uses slashes and day-first ordering
    eu = file.get_file_meta(str(tmp_path), time_format="eu")["a.csv"]["display"]
    assert eu[2] == "/" and eu[5] == "/"

    # iso_sec includes seconds
    sec = file.get_file_meta(str(tmp_path), time_format="iso_sec")["a.csv"]["display"]
    assert len(sec) == 19

    # Unknown key falls back to iso
    iso = file.get_file_meta(str(tmp_path), time_format="bogus")["a.csv"]["display"]
    assert len(iso) == 16 and iso[4] == "-"


def test_sort_file_names_by_name():
    names = ["b.csv", "A.csv", "c.csv"]
    meta = {}
    assert file.sort_file_names(names, meta, "name_asc") == ["A.csv", "b.csv", "c.csv"]
    assert file.sort_file_names(names, meta, "name_desc") == ["c.csv", "b.csv", "A.csv"]


def test_sort_file_names_by_date():
    names = ["old.csv", "new.csv", "mid.csv"]
    meta = {
        "old.csv": {"mtime": 100, "display": ""},
        "mid.csv": {"mtime": 200, "display": ""},
        "new.csv": {"mtime": 300, "display": ""},
    }
    assert file.sort_file_names(names, meta, "date_asc") == ["old.csv", "mid.csv", "new.csv"]
    assert file.sort_file_names(names, meta, "date_desc") == ["new.csv", "mid.csv", "old.csv"]
    # Missing metadata sorts as oldest
    assert file.sort_file_names(["x.csv", "new.csv"], meta, "date_desc")[0] == "new.csv"


def test_sort_file_names_invalid_order_falls_back():
    names = ["new.csv", "old.csv"]
    meta = {"old.csv": {"mtime": 100}, "new.csv": {"mtime": 300}}
    # Unknown order behaves like the date_desc default
    assert file.sort_file_names(names, meta, "bogus") == ["new.csv", "old.csv"]


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


# ---------------------------------------------------------------------------
# Concentration unit (# ConcenUnit) — metadata, export guard, helper
# ---------------------------------------------------------------------------
from src import file_path


def test_concen_units_catalog():
    # Exactly the four allowed units, default ng/µL.
    assert file_path.CONCEN_UNITS == ["ng/µL", "nM", "%", "CFU"]
    assert file_path.DEFAULT_CONCEN_UNIT == "ng/µL"


def test_get_concen_unit_defaults_when_absent():
    assert file_path.get_concen_unit({}) == "ng/µL"
    assert file_path.get_concen_unit({"ConcenUnit": ""}) == "ng/µL"
    assert file_path.get_concen_unit(None) == "ng/µL"


def test_get_concen_unit_reads_percent():
    assert file_path.get_concen_unit({"ConcenUnit": "%"}) == "%"


def test_get_concen_unit_reads_value():
    assert file_path.get_concen_unit({"ConcenUnit": "nM"}) == "nM"


def test_write_metadata_emits_concen_unit():
    output = io.StringIO()
    export_data.write_metadata(output, "ABS", "AU", "minutes", "kinetics", "nM")
    assert "# ConcenUnit: nM" in output.getvalue()


def test_write_metadata_concen_unit_defaults_to_ng_ul():
    output = io.StringIO()
    export_data.write_metadata(output, "ABS", "AU", "minutes", "kinetics")
    assert "# ConcenUnit: ng/µL" in output.getvalue()


def test_is_metadata_consistent_missing_concen_unit_treated_as_default():
    # A legacy file with no ConcenUnit is assumed ng/µL: only a matching-default
    # export is consistent with it.
    meta = {'Measurement': 'ABS', 'MeasUnit': 'AU', 'TimeUnit': 'minutes', 'MeasMode': 'kinetics'}
    assert export_data.is_metadata_consistent(meta, "ABS", "AU", "minutes", "kinetics", "ng/µL") is True
    assert export_data.is_metadata_consistent(meta, "ABS", "AU", "minutes", "kinetics", "nM") is False


def test_is_metadata_consistent_concen_unit_must_match():
    meta = {'Measurement': 'ABS', 'MeasUnit': 'AU', 'TimeUnit': 'minutes',
            'MeasMode': 'kinetics', 'ConcenUnit': 'nM'}
    assert export_data.is_metadata_consistent(meta, "ABS", "AU", "minutes", "kinetics", "nM") is True
    assert export_data.is_metadata_consistent(meta, "ABS", "AU", "minutes", "kinetics", "ng/µL") is False


def _kinetics_cal_file(path, concen_unit_line=""):
    path.write_text(
        "# Measurement: ABS\n# MeasUnit: AU\n# TimeUnit: minutes\n# MeasMode: kinetics\n"
        + concen_unit_line +
        "Concentration,maxRate,Slope,Sat,Time To Sat\n5,0.1,0.2,0.3,10\n"
    )


def test_ensure_concen_unit_adds_line_to_legacy_file(tmp_path):
    f = tmp_path / "a_kinetics.csv"
    _kinetics_cal_file(f)
    migrated = file.ensure_concen_unit_in_dir(str(tmp_path))
    assert migrated == 1
    text = f.read_text()
    assert "# ConcenUnit: ng/µL" in text
    # Inserted into the metadata block, before the data header
    lines = text.splitlines()
    header_idx = next(i for i, l in enumerate(lines) if l.startswith("Concentration"))
    concen_idx = next(i for i, l in enumerate(lines) if l.startswith("# ConcenUnit"))
    assert concen_idx < header_idx


def test_ensure_concen_unit_is_idempotent(tmp_path):
    f = tmp_path / "a_kinetics.csv"
    _kinetics_cal_file(f)
    assert file.ensure_concen_unit_in_dir(str(tmp_path)) == 1
    # Second pass: already present → no rewrite
    assert file.ensure_concen_unit_in_dir(str(tmp_path)) == 0
    assert f.read_text().count("# ConcenUnit") == 1


def test_ensure_concen_unit_skips_files_already_having_it(tmp_path):
    f = tmp_path / "a_kinetics.csv"
    _kinetics_cal_file(f, concen_unit_line="# ConcenUnit: nM\n")
    assert file.ensure_concen_unit_in_dir(str(tmp_path)) == 0
    assert "# ConcenUnit: nM" in f.read_text()


def test_ensure_concen_unit_skips_unrecognized_schema(tmp_path):
    f = tmp_path / "notes.csv"
    f.write_text("# Some: thing\nfoo,bar\n1,2\n")
    assert file.ensure_concen_unit_in_dir(str(tmp_path)) == 0
    assert "ConcenUnit" not in f.read_text()


def test_ensure_concen_unit_migrates_timeseries(tmp_path):
    f = tmp_path / "raw.csv"
    f.write_text(
        "# Measurement: ABS\n# Unit: AU\n# Concentration: 5\n"
        "Timestamp,Value:1\n0,0.1\n1,0.2\n"
    )
    assert file.ensure_concen_unit_in_dir(str(tmp_path)) == 1
    assert "# ConcenUnit: ng/µL" in f.read_text()


# ---------------------------------------------------------------------------
# CDC logger — ConcenUnit metadata is recognized and mandated (4 keys)
# ---------------------------------------------------------------------------

def _make_collector(tmp_path, monkeypatch):
    import state as _state
    monkeypatch.setattr(_state, "script_dir", str(tmp_path))
    import log_cdc_data
    return log_cdc_data.CDCDataCollector(str(tmp_path / "data"))


def test_cdc_metadata_pattern_matches_concen_unit(tmp_path, monkeypatch):
    c = _make_collector(tmp_path, monkeypatch)
    assert c.is_metadata("# ConcenUnit: nM")
    c.handle_metadata("# ConcenUnit: nM")
    assert c.metadata.get("ConcenUnit") == "nM"


def test_cdc_main_header_requires_four_metadata(tmp_path, monkeypatch):
    c = _make_collector(tmp_path, monkeypatch)
    header = "Timestamp,Value:1"
    c.is_main_header(header)  # sets num_values

    # Only 3 legacy keys → header rejected, no session
    c.metadata = {"Measurement": "ABS", "Unit": "AU", "Concentration": "5"}
    c.handle_main_header(header)
    assert c.session_started is False

    # 4th key present → session starts and the file is written
    c.metadata = {"Measurement": "ABS", "Unit": "AU", "Concentration": "5", "ConcenUnit": "nM"}
    c.handle_main_header(header)
    assert c.session_started is True
    assert "# ConcenUnit: nM" in open(c.output_file, encoding="utf-8").read()


def _started_collector(tmp_path, monkeypatch):
    """A CDCDataCollector with an active session (header written)."""
    c = _make_collector(tmp_path, monkeypatch)
    c.is_main_header("Timestamp,Value:1")  # sets num_values
    c.metadata = {"Measurement": "ABS", "Unit": "AU", "Concentration": "5", "ConcenUnit": "nM"}
    c.handle_main_header("Timestamp,Value:1")
    assert c.session_started is True
    return c


def test_cdc_session_stopped_ends_session_and_logs_distinctly(tmp_path, monkeypatch):
    """The device-button stop sentinel ends the one-shot session and is logged as
    SESSION STOPPED (not TIMEOUT) so the UI can announce a manual device stop."""
    c = _started_collector(tmp_path, monkeypatch)
    assert c.is_stopped("SESSION STOPPED")

    c.process_line("SESSION STOPPED")
    assert c.session_started is False
    assert c.running is False  # one-shot: logger loop exits

    log = open(c.log_file_path, encoding="utf-8").read()
    assert "SESSION STOPPED" in log
    assert "SESSION TIMEOUT" not in log


def test_cdc_session_timeout_still_logs_timeout(tmp_path, monkeypatch):
    """The timeout sentinel remains distinct from the device-stop sentinel."""
    c = _started_collector(tmp_path, monkeypatch)
    c.process_line("SESSION TIMEOUT")
    assert c.session_started is False
    assert c.running is False
    log = open(c.log_file_path, encoding="utf-8").read()
    assert "SESSION TIMEOUT" in log
    assert "SESSION STOPPED" not in log


# ---------------------------------------------------------------------------
# CSV/JSON identity (Measurement / Unit / ConcenUnit) for CSV↔JSON matching
# ---------------------------------------------------------------------------

def test_build_csv_identity_kinetics_cal(tmp_path):
    f = tmp_path / "cal_kinetics.csv"
    f.write_text(
        "# Measurement: ABS\n# MeasUnit: abs\n# TimeUnit: minutes\n# MeasMode: kinetics\n"
        "# ConcenUnit: nM\nConcentration,maxRate,Slope,Sat,Time To Sat\n5,0.1,0.2,0.3,10\n"
    )
    ident = file.build_csv_identity(str(tmp_path), ["cal_kinetics.csv"])["cal_kinetics.csv"]
    assert ident == {"measurement": "ABS", "unit": "abs", "concen_unit": "nM"}


def test_build_csv_identity_timeseries_uses_unit_and_defaults_concen(tmp_path):
    f = tmp_path / "raw.csv"
    f.write_text("# Measurement: ABS\n# Unit: abs\n# Concentration: 5\nTimestamp,Value:1\n0,0.1\n")
    ident = file.build_csv_identity(str(tmp_path), ["raw.csv"])["raw.csv"]
    assert ident["measurement"] == "ABS"
    assert ident["unit"] == "abs"
    assert ident["concen_unit"] == "ng/µL"  # absent ⇒ default


def test_build_json_identity_full_and_legacy(tmp_path):
    (tmp_path / "curve.json").write_text(json.dumps(
        {"fit_type": "linear", "for_meas": "ABS", "meas_unit": "abs", "concen_unit": "nM"}))
    (tmp_path / "legacy.json").write_text(json.dumps({"fit_type": "linear", "for_meas": "ABS"}))
    (tmp_path / "skip.meta.json").write_text(json.dumps({"for_meas": "X"}))
    ident = file.build_json_identity(str(tmp_path), ["curve.json", "legacy.json", "skip.meta.json"])
    assert ident["curve.json"] == {"measurement": "ABS", "unit": "abs", "concen_unit": "nM"}
    # Legacy JSON: missing unit stays None (wildcard); concen defaults to ng/µL
    assert ident["legacy.json"] == {"measurement": "ABS", "unit": None, "concen_unit": "ng/µL"}
    assert "skip.meta.json" not in ident  # sidecar skipped


def test_ensure_cal_units_fills_legacy_json(tmp_path):
    legacy = tmp_path / "curve.json"
    legacy.write_text(json.dumps({"fit_type": "linear", "for_meas": "ABS"}))
    full = tmp_path / "full.json"
    full.write_text(json.dumps({"fit_type": "linear", "for_meas": "ABS",
                                "meas_unit": "abs", "concen_unit": "nM"}))
    meta = tmp_path / "x.meta.json"
    meta.write_text("{}")

    assert file.ensure_cal_units_in_dir(str(tmp_path)) == 1  # only the legacy one
    filled = json.loads(legacy.read_text())
    assert filled["meas_unit"] == "NONE"
    assert filled["concen_unit"] == "ng/µL"
    # An already-complete file and the .meta sidecar are left untouched
    assert json.loads(full.read_text())["meas_unit"] == "abs"
    assert json.loads(meta.read_text()) == {}
    # Idempotent on a second pass
    assert file.ensure_cal_units_in_dir(str(tmp_path)) == 0


def test_build_json_identity_none_meas_unit_is_wildcard(tmp_path):
    (tmp_path / "filled.json").write_text(json.dumps(
        {"fit_type": "linear", "for_meas": "ABS", "meas_unit": "NONE", "concen_unit": "ng/µL"}))
    ident = file.build_json_identity(str(tmp_path), ["filled.json"])["filled.json"]
    # A back-filled "NONE" meas_unit normalizes to None so it stays a matching wildcard
    assert ident == {"measurement": "ABS", "unit": None, "concen_unit": "ng/µL"}
