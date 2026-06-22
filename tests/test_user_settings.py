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
