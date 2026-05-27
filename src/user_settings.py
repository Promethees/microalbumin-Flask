import json
import os
import state

_VALID_THEMES = {"light", "dark", "auto"}
_VALID_MODES = {"kinetics", "point", "calibrate"}

DEFAULTS = {
    "theme": "auto",
    "default_mode": "kinetics",
    "default_window_size": 4,
    "default_subfolder": None,
    "file_table_height": 240,
    "max_csv_rows": 0,
    "max_json_rows": 0,
    "event_log_retention_days": 30,
    "chart_height": 600,
    "default_normalize": False,
    "default_split_sources": False,
    "range_expanded_default": False,
    "export_expanded_default": False,
}


def _path():
    return os.path.join(state.script_dir, "user_settings.json")


def load() -> dict:
    settings = dict(DEFAULTS)
    path = _path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            for k in DEFAULTS:
                if k in stored:
                    settings[k] = stored[k]
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save(updates: dict) -> bool:
    current = load()
    if "theme" in updates and updates["theme"] in _VALID_THEMES:
        current["theme"] = updates["theme"]
    if "default_mode" in updates and updates["default_mode"] in _VALID_MODES:
        current["default_mode"] = updates["default_mode"]
    if "default_window_size" in updates:
        try:
            ws = int(updates["default_window_size"])
            if ws >= 2:
                current["default_window_size"] = ws
        except (ValueError, TypeError):
            pass
    if "default_subfolder" in updates:
        val = updates["default_subfolder"]
        current["default_subfolder"] = val if (isinstance(val, str) and val) or val is None else None
    if "file_table_height" in updates:
        try:
            h = int(updates["file_table_height"])
            if h >= 80:
                current["file_table_height"] = h
        except (ValueError, TypeError):
            pass
    if "max_csv_rows" in updates:
        try:
            n = int(updates["max_csv_rows"])
            if n >= 0:
                current["max_csv_rows"] = n
        except (ValueError, TypeError):
            pass
    if "max_json_rows" in updates:
        try:
            n = int(updates["max_json_rows"])
            if n >= 0:
                current["max_json_rows"] = n
        except (ValueError, TypeError):
            pass
    if "event_log_retention_days" in updates:
        try:
            n = int(updates["event_log_retention_days"])
            if n >= 0:
                current["event_log_retention_days"] = n
        except (ValueError, TypeError):
            pass
    if "chart_height" in updates:
        try:
            h = int(updates["chart_height"])
            if h >= 200:
                current["chart_height"] = h
        except (ValueError, TypeError):
            pass
    for bool_key in ("default_normalize", "default_split_sources",
                     "range_expanded_default", "export_expanded_default"):
        if bool_key in updates:
            current[bool_key] = bool(updates[bool_key])
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        return True
    except OSError:
        return False
