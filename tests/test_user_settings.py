import pytest
import json
import os
from unittest.mock import patch

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import state
import user_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_settings(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# user_settings.load()
# ---------------------------------------------------------------------------

class TestLoad:
    def test_returns_defaults_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        result = user_settings.load()
        assert result == user_settings.DEFAULTS

    def test_merges_stored_values_over_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        _write_settings(tmp_path / "user_settings.json", {
            "theme": "dark",
            "default_window_size": 10,
        })
        result = user_settings.load()
        assert result["theme"] == "dark"
        assert result["default_window_size"] == 10
        # Unset keys fall back to defaults
        assert result["default_mode"] == user_settings.DEFAULTS["default_mode"]

    def test_ignores_unknown_keys(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        _write_settings(tmp_path / "user_settings.json", {
            "theme": "light",
            "unknown_future_key": "some_value",
        })
        result = user_settings.load()
        assert "unknown_future_key" not in result

    def test_returns_defaults_on_corrupt_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        (tmp_path / "user_settings.json").write_text("{ not valid json }")
        result = user_settings.load()
        assert result == user_settings.DEFAULTS

    def test_subfolder_none_by_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        result = user_settings.load()
        assert result["default_subfolder"] is None


# ---------------------------------------------------------------------------
# user_settings.save()
# ---------------------------------------------------------------------------

class TestSave:
    def test_saves_valid_theme(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({"theme": "dark"}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["theme"] == "dark"

    def test_rejects_invalid_theme(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"theme": "invalid_theme"})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["theme"] == user_settings.DEFAULTS["theme"]

    def test_saves_valid_mode(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        for mode in ("kinetics", "point", "calibrate"):
            assert user_settings.save({"default_mode": mode}) is True
            saved = json.loads((tmp_path / "user_settings.json").read_text())
            assert saved["default_mode"] == mode

    def test_rejects_invalid_mode(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"default_mode": "report"})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["default_mode"] == user_settings.DEFAULTS["default_mode"]

    def test_saves_valid_window_size(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({"default_window_size": 8}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["default_window_size"] == 8

    def test_rejects_window_size_below_minimum(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"default_window_size": 1})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["default_window_size"] == user_settings.DEFAULTS["default_window_size"]

    def test_rejects_non_numeric_window_size(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"default_window_size": "abc"})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["default_window_size"] == user_settings.DEFAULTS["default_window_size"]

    def test_saves_valid_concentration_unit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({"default_concentration_unit": "nM"}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["default_concentration_unit"] == "nM"

    def test_saves_percent_concentration_unit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({"default_concentration_unit": "%"}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["default_concentration_unit"] == "%"

    def test_rejects_invalid_concentration_unit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"default_concentration_unit": "mol/L"})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["default_concentration_unit"] == user_settings.DEFAULTS["default_concentration_unit"]

    def test_concentration_unit_default_is_ng_ul(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.load()["default_concentration_unit"] == "ng/µL"

    def test_y_axis_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        s = user_settings.load()
        assert s["y_axis_scale_mode"] == "auto"
        assert s["y_axis_custom_min"] == 0.0
        assert s["y_axis_custom_max"] == 0.6

    def test_saves_valid_y_axis_mode(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({"y_axis_scale_mode": "custom"}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["y_axis_scale_mode"] == "custom"

    def test_rejects_invalid_y_axis_mode(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"y_axis_scale_mode": "logarithmic"})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["y_axis_scale_mode"] == user_settings.DEFAULTS["y_axis_scale_mode"]

    def test_saves_custom_y_axis_bounds(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"y_axis_custom_min": -0.2, "y_axis_custom_max": 1.5})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["y_axis_custom_min"] == -0.2
        assert saved["y_axis_custom_max"] == 1.5

    def test_rejects_non_numeric_y_axis_bounds(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"y_axis_custom_max": "high"})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["y_axis_custom_max"] == user_settings.DEFAULTS["y_axis_custom_max"]

    def test_saves_valid_subfolder(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({"default_subfolder": "experiment_1"}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["default_subfolder"] == "experiment_1"

    def test_saves_subfolder_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"default_subfolder": "experiment_1"})
        user_settings.save({"default_subfolder": None})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["default_subfolder"] is None

    def test_partial_update_preserves_other_keys(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"theme": "dark", "default_window_size": 6})
        user_settings.save({"theme": "light"})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["theme"] == "light"
        assert saved["default_window_size"] == 6

    def test_returns_false_on_os_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        with patch("builtins.open", side_effect=OSError("disk full")):
            result = user_settings.save({"theme": "dark"})
        assert result is False

    def test_saves_valid_file_table_height(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({"file_table_height": 400}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["file_table_height"] == 400

    def test_rejects_file_table_height_below_minimum(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"file_table_height": 50})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["file_table_height"] == user_settings.DEFAULTS["file_table_height"]

    def test_rejects_non_numeric_file_table_height(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"file_table_height": "tall"})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["file_table_height"] == user_settings.DEFAULTS["file_table_height"]

    def test_saves_valid_max_csv_rows(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({"max_csv_rows": 20}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["max_csv_rows"] == 20

    def test_saves_max_csv_rows_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"max_csv_rows": 20})
        assert user_settings.save({"max_csv_rows": 0}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["max_csv_rows"] == 0

    def test_rejects_negative_max_csv_rows(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"max_csv_rows": -5})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["max_csv_rows"] == user_settings.DEFAULTS["max_csv_rows"]

    def test_saves_valid_max_json_rows(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({"max_json_rows": 10}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["max_json_rows"] == 10

    def test_rejects_negative_max_json_rows(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"max_json_rows": -1})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["max_json_rows"] == user_settings.DEFAULTS["max_json_rows"]

    def test_saves_valid_event_log_retention_days(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({"event_log_retention_days": 90}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["event_log_retention_days"] == 90

    def test_saves_event_log_retention_days_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"event_log_retention_days": 30})
        assert user_settings.save({"event_log_retention_days": 0}) is True
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["event_log_retention_days"] == 0

    def test_rejects_negative_event_log_retention_days(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"event_log_retention_days": -1})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["event_log_retention_days"] == user_settings.DEFAULTS["event_log_retention_days"]

    def test_rejects_non_numeric_event_log_retention_days(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"event_log_retention_days": "forever"})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["event_log_retention_days"] == user_settings.DEFAULTS["event_log_retention_days"]

    def test_event_log_retention_days_default_is_30(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        result = user_settings.load()
        assert result["event_log_retention_days"] == 30

    def test_merge_directory_picker_default_is_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        result = user_settings.load()
        assert result["merge_directory_picker"] is False

    def test_saves_merge_directory_picker(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"merge_directory_picker": True})
        assert user_settings.load()["merge_directory_picker"] is True
        user_settings.save({"merge_directory_picker": False})
        assert user_settings.load()["merge_directory_picker"] is False

    def test_time_tag_format_default_is_iso(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        result = user_settings.load()
        assert result["time_tag_format"] == "iso"

    def test_saves_valid_time_tag_format(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        for fmt in ("iso", "iso_sec", "us", "eu", "date_only"):
            assert user_settings.save({"time_tag_format": fmt}) is True
            assert user_settings.load()["time_tag_format"] == fmt

    def test_rejects_invalid_time_tag_format(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"time_tag_format": "klingon"})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["time_tag_format"] == user_settings.DEFAULTS["time_tag_format"]

    def test_file_sort_order_default_is_date_desc(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        result = user_settings.load()
        assert result["file_sort_order"] == "date_desc"

    def test_saves_valid_file_sort_order(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        for order in ("name_asc", "name_desc", "date_asc", "date_desc"):
            assert user_settings.save({"file_sort_order": order}) is True
            assert user_settings.load()["file_sort_order"] == order

    def test_rejects_invalid_file_sort_order(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"file_sort_order": "size_asc"})
        saved = json.loads((tmp_path / "user_settings.json").read_text())
        assert saved["file_sort_order"] == user_settings.DEFAULTS["file_sort_order"]

    def test_disable_popups_default_is_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        result = user_settings.load()
        assert result["disable_popups"] is False

    def test_saves_disable_popups(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"disable_popups": True})
        assert user_settings.load()["disable_popups"] is True
        user_settings.save({"disable_popups": False})
        assert user_settings.load()["disable_popups"] is False

    def test_ai_feedback_enabled_default_is_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.load()["ai_feedback_enabled"] is True

    def test_saves_ai_feedback_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"ai_feedback_enabled": False})
        assert user_settings.load()["ai_feedback_enabled"] is False
        user_settings.save({"ai_feedback_enabled": True})
        assert user_settings.load()["ai_feedback_enabled"] is True


# ---------------------------------------------------------------------------
# GET /settings route
# ---------------------------------------------------------------------------

class TestGetSettingsRoute:
    @pytest.fixture
    def client(self):
        from main import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_returns_success_status(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        rv = client.get("/settings")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "success"
        assert "settings" in data

    def test_returns_all_expected_keys(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        rv = client.get("/settings")
        settings = rv.get_json()["settings"]
        for key in user_settings.DEFAULTS:
            assert key in settings

    def test_reflects_saved_values(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        _write_settings(tmp_path / "user_settings.json", {"theme": "dark"})
        rv = client.get("/settings")
        assert rv.get_json()["settings"]["theme"] == "dark"


# ---------------------------------------------------------------------------
# POST /settings route
# ---------------------------------------------------------------------------

class TestPostSettingsRoute:
    @pytest.fixture
    def client(self):
        from main import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_updates_theme(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        rv = client.post("/settings", json={"theme": "light"})
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "success"
        assert user_settings.load()["theme"] == "light"

    def test_updates_default_mode(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        rv = client.post("/settings", json={"default_mode": "point"})
        assert rv.status_code == 200
        assert user_settings.load()["default_mode"] == "point"

    def test_updates_window_size(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        rv = client.post("/settings", json={"default_window_size": 7})
        assert rv.status_code == 200
        assert user_settings.load()["default_window_size"] == 7

    def test_updates_subfolder(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        rv = client.post("/settings", json={"default_subfolder": "my_folder"})
        assert rv.status_code == 200
        assert user_settings.load()["default_subfolder"] == "my_folder"

    def test_rejects_missing_body(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        rv = client.post("/settings", data="not json",
                         content_type="text/plain")
        assert rv.status_code == 400

    def test_accepts_partial_update(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        client.post("/settings", json={"theme": "dark", "default_window_size": 5})
        rv = client.post("/settings", json={"theme": "auto"})
        assert rv.status_code == 200
        loaded = user_settings.load()
        assert loaded["theme"] == "auto"
        assert loaded["default_window_size"] == 5  # unchanged

    def test_returns_error_on_save_failure(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        with patch("routes.core_routes._user_settings.save", return_value=False):
            rv = client.post("/settings", json={"theme": "dark"})
        assert rv.status_code == 500


class TestReadingStartTimeout:
    """The start-up wait guard (Rule §2.30). Bounds matter: too low and the
    notice fires during a normal handshake and kills working runs; unbounded
    and a typo disables the guard."""

    def test_default_is_sixty_seconds(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.load()["reading_start_timeout_sec"] == 60

    def test_accepts_value_in_range(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"reading_start_timeout_sec": 120})
        assert user_settings.load()["reading_start_timeout_sec"] == 120

    @pytest.mark.parametrize("bad", [9, 0, -5, 601, 10000])
    def test_rejects_out_of_range(self, tmp_path, monkeypatch, bad):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"reading_start_timeout_sec": bad})
        assert user_settings.load()["reading_start_timeout_sec"] == 60

    @pytest.mark.parametrize("bad", ["soon", None, [], {}])
    def test_rejects_non_numeric(self, tmp_path, monkeypatch, bad):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"reading_start_timeout_sec": bad})
        assert user_settings.load()["reading_start_timeout_sec"] == 60

    def test_accepts_boundary_values(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"reading_start_timeout_sec": 10})
        assert user_settings.load()["reading_start_timeout_sec"] == 10
        user_settings.save({"reading_start_timeout_sec": 600})
        assert user_settings.load()["reading_start_timeout_sec"] == 600


class TestUiStyle:
    """`ui_style` picks the interface's visual language (Rule.md §2.34).

    A closed choice, like `ui_language`: the value is stamped straight onto
    <body> as a class by the index render, and the chart palette and session
    strip branch on it, so an unknown value must never reach the template.
    """

    def test_defaults_to_instrument(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.load()["ui_style"] == "instrument"

    @pytest.mark.parametrize("value", ["classic", "instrument"])
    def test_accepts_known_styles(self, tmp_path, monkeypatch, value):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"ui_style": value})
        assert user_settings.load()["ui_style"] == value

    def test_normalises_case_and_whitespace(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"ui_style": "  Classic  "})
        assert user_settings.load()["ui_style"] == "classic"

    @pytest.mark.parametrize("bad", ["retro", "", None, 1, [], {}])
    def test_rejects_unknown_styles(self, tmp_path, monkeypatch, bad):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"ui_style": "classic"})
        user_settings.save({"ui_style": bad})
        assert user_settings.load()["ui_style"] == "classic"


class TestDeviceLinkSetting:
    """`device_link_enabled` is the controller's connection switch: whether the
    app may hold the serial port while the panel is open. Distinct from
    `device_control_enabled`, which hides the panel altogether."""

    def test_defaults_on(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.load()["device_link_enabled"] is True

    @pytest.mark.parametrize("value,expected", [(False, False), (True, True), (0, False), (1, True)])
    def test_coerced_to_bool(self, tmp_path, monkeypatch, value, expected):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"device_link_enabled": value})
        assert user_settings.load()["device_link_enabled"] is expected

    def test_is_independent_of_the_panel_setting(self, tmp_path, monkeypatch):
        """Parking the port must not hide the panel, and vice versa."""
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"device_link_enabled": False})
        loaded = user_settings.load()
        assert loaded["device_link_enabled"] is False
        assert loaded["device_control_enabled"] is True


class TestSessionStripSetting:
    """`session_strip_enabled` is the instrument style's live-readout opt-out."""

    def test_defaults_on(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.load()["session_strip_enabled"] is True

    @pytest.mark.parametrize("value,expected", [(False, False), (True, True), (0, False), (1, True)])
    def test_coerced_to_bool(self, tmp_path, monkeypatch, value, expected):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"session_strip_enabled": value})
        assert user_settings.load()["session_strip_enabled"] is expected


class TestBulkLineStyleSettings:
    """The "Line styles" panel writes these four; they apply to every series."""

    def test_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        s = user_settings.load()
        assert s["chart_line_width"] == 2
        assert s["chart_dash_mode"] == "none"
        assert s["chart_marker_mode"] == "auto"
        # The sequential ramp stays the default: Rule.md 2.33 argues for it, and
        # the alternatives are a deliberate user choice for many-source files.
        assert s["chart_palette"] == "ramp"

    @pytest.mark.parametrize("value,expected", [(1, 1), (4, 4), (6, 6), (0, 1), (99, 6), ("3", 3)])
    def test_line_width_is_clamped(self, tmp_path, monkeypatch, value, expected):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"chart_line_width": value})
        assert user_settings.load()["chart_line_width"] == expected

    def test_line_width_rejects_nonsense(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"chart_line_width": "thick"})
        assert user_settings.load()["chart_line_width"] == 2

    @pytest.mark.parametrize("key,good,bad", [
        ("chart_dash_mode", "cycle", "zigzag"),
        ("chart_marker_mode", "never", "sometimes"),
        ("chart_palette", "distinct", "grey"),
    ])
    def test_enums_accept_known_and_reject_unknown(self, tmp_path, monkeypatch, key, good, bad):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({key: good}) is True
        assert user_settings.load()[key] == good
        user_settings.save({key: bad})
        assert user_settings.load()[key] == good

    def test_ramp_colour_defaults_to_the_theme(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.load()["chart_ramp_color"] is None

    @pytest.mark.parametrize("value", ["#b85207", "#B85207", "  #0a0b0c  "])
    def test_ramp_colour_accepts_hex(self, tmp_path, monkeypatch, value):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"chart_ramp_color": value})
        assert user_settings.load()["chart_ramp_color"] == value.strip().lower()

    @pytest.mark.parametrize("value", ["red", "#fff", "rgb(1,2,3)", "#gggggg", 12345])
    def test_ramp_colour_rejects_anything_else(self, tmp_path, monkeypatch, value):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"chart_ramp_color": "#b85207"})
        user_settings.save({"chart_ramp_color": value})
        assert user_settings.load()["chart_ramp_color"] == "#b85207"

    @pytest.mark.parametrize("value", [None, "", "default"])
    def test_ramp_colour_can_be_cleared(self, tmp_path, monkeypatch, value):
        """Clearing hands the ramp back to the theme's own tokens."""
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"chart_ramp_color": "#b85207"})
        user_settings.save({"chart_ramp_color": value})
        assert user_settings.load()["chart_ramp_color"] is None
