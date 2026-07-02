import os
from datetime import date, timedelta

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import state
import user_settings
import event_logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_date_folder(root, day, filename="10-00-00.jsonl"):
    """Create log/events/<day>/<filename> under root; returns the folder path."""
    folder = os.path.join(root, "log", "events", day.isoformat())
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, filename), "w") as f:
        f.write('{"ts": "%sT10:00:00", "type": "session", "action": "start"}\n'
                % day.isoformat())
    return folder


def _event_folders(root):
    events = os.path.join(root, "log", "events")
    if not os.path.isdir(events):
        return []
    return sorted(os.listdir(events))


# ---------------------------------------------------------------------------
# event_logger.cleanup_old_logs()
# ---------------------------------------------------------------------------

class TestCleanupOldLogs:
    def test_retention_one_keeps_only_today(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        today = date.today()
        _make_date_folder(str(tmp_path), today)
        _make_date_folder(str(tmp_path), today - timedelta(days=1))
        user_settings.save({"event_log_retention_days": 1})

        event_logger.cleanup_old_logs()

        assert _event_folders(str(tmp_path)) == [today.isoformat()]

    def test_retention_n_keeps_exactly_n_days(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        today = date.today()
        for age in range(5):
            _make_date_folder(str(tmp_path), today - timedelta(days=age))
        user_settings.save({"event_log_retention_days": 3})

        event_logger.cleanup_old_logs()

        expected = sorted((today - timedelta(days=age)).isoformat()
                          for age in range(3))
        assert _event_folders(str(tmp_path)) == expected

    def test_retention_zero_keeps_everything(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        today = date.today()
        _make_date_folder(str(tmp_path), today)
        _make_date_folder(str(tmp_path), today - timedelta(days=400))
        user_settings.save({"event_log_retention_days": 0})

        event_logger.cleanup_old_logs()

        assert len(_event_folders(str(tmp_path))) == 2

    def test_ignores_non_date_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        today = date.today()
        _make_date_folder(str(tmp_path), today)
        events_root = os.path.join(str(tmp_path), "log", "events")
        os.makedirs(os.path.join(events_root, "not-a-date"))
        with open(os.path.join(events_root, "stray.txt"), "w") as f:
            f.write("keep me")
        user_settings.save({"event_log_retention_days": 1})

        event_logger.cleanup_old_logs()

        assert _event_folders(str(tmp_path)) == sorted(
            [today.isoformat(), "not-a-date", "stray.txt"])

    def test_missing_events_root_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"event_log_retention_days": 1})
        event_logger.cleanup_old_logs()  # must not raise


# ---------------------------------------------------------------------------
# POST /settings applies a shrunk retention immediately
# ---------------------------------------------------------------------------

class TestSettingsSaveTriggersCleanup:
    def test_lowering_retention_removes_stale_folders(self, client, tmp_path,
                                                      monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        today = date.today()
        _make_date_folder(str(tmp_path), today)
        _make_date_folder(str(tmp_path), today - timedelta(days=1))
        _make_date_folder(str(tmp_path), today - timedelta(days=2))
        user_settings.save({"event_log_retention_days": 30})

        rv = client.post('/settings', json={"event_log_retention_days": 1})

        assert rv.status_code == 200
        assert rv.get_json()["status"] == "success"
        assert _event_folders(str(tmp_path)) == [today.isoformat()]
