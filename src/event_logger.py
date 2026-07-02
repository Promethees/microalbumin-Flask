import json
import os
import shutil
import time
from datetime import date, timedelta

import state
import user_settings

# Set once at module import (= app startup). All events from this process
# write to the same session file: log/events/YYYY-MM-DD/HH-MM-SS.jsonl
_SESSION_DATE = time.strftime("%Y-%m-%d")
_SESSION_START = time.strftime("%H-%M-%S")


def _events_root() -> str:
    return os.path.join(state.script_dir, "log", "events")


def _session_file() -> str:
    return os.path.join(_events_root(), _SESSION_DATE, f"{_SESSION_START}.jsonl")


def append(event_type: str, action: str, details: dict = None) -> None:
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "type": event_type, "action": action}
    if details:
        entry["details"] = details

    path = _session_file()
    # Event logging is best-effort analytics; a non-writable log directory
    # (e.g. created under sudo, or a read-only deploy) must never break the
    # request that triggered the event.
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def read_all() -> list:
    """Return all events across all date folders and sessions, oldest first."""
    root = _events_root()
    if not os.path.isdir(root):
        return []
    events = []
    for date_dir in sorted(os.listdir(root)):
        date_path = os.path.join(root, date_dir)
        if not os.path.isdir(date_path):
            continue
        for session_file in sorted(os.listdir(date_path)):
            if not session_file.endswith(".jsonl"):
                continue
            try:
                with open(os.path.join(date_path, session_file), "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                events.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
            except OSError:
                pass
    return events


def cleanup_old_logs() -> None:
    """Remove date folders beyond event_log_retention_days. 0 = keep forever.

    Retention N keeps exactly the N most recent calendar days, counting
    today as day 1 (N=1 → only today's folder survives).
    """
    settings = user_settings.load()
    retention_days = int(settings.get("event_log_retention_days", 30))
    if retention_days <= 0:
        return

    cutoff = date.today() - timedelta(days=retention_days - 1)
    root = _events_root()
    if not os.path.isdir(root):
        return

    for name in os.listdir(root):
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        try:
            if date.fromisoformat(name) < cutoff:
                shutil.rmtree(folder, ignore_errors=True)
        except ValueError:
            pass
