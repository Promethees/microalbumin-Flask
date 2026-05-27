import json
import os
import time
import state
import user_settings

_LOG_FILENAME = "event_log.jsonl"


def _log_path():
    return os.path.join(state.script_dir, "log", _LOG_FILENAME)


def append(event_type: str, action: str, details: dict = None) -> None:
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "type": event_type, "action": action}
    if details:
        entry["details"] = details

    path = _log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    settings = user_settings.load()
    max_entries = int(settings.get("max_event_log_entries", 200))
    if max_entries > 0:
        _trim(path, max_entries)


def _trim(path: str, max_entries: int) -> None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > max_entries:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[-max_entries:])
    except OSError:
        pass


def read_all() -> list:
    path = _log_path()
    if not os.path.isfile(path):
        return []
    events = []
    try:
        with open(path, "r", encoding="utf-8") as f:
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
