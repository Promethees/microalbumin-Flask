import json
import os
import state

# Canonical registry of the six languages the UI and AI chat support. This is
# the single source of truth, imported by i18n.py and routes/ai_routes.py.
SUPPORTED_LANGUAGES = {
    "en": "English",
    "vi": "Tiếng Việt",
    "zh": "中文 (简体)",
    "fr": "Français",
    "ja": "日本語",
    "ru": "Русский",
}

_VALID_THEMES = {"light", "dark", "auto"}
_VALID_UI_LANGUAGES = set(SUPPORTED_LANGUAGES)
_VALID_MODES = {"kinetics", "point", "calibrate"}
_VALID_UNITS = {"seconds", "minutes", "hours"}
_VALID_SORT_ORDERS = {"name_asc", "name_desc", "date_asc", "date_desc"}
_VALID_TIME_TAG_FORMATS = {"iso", "iso_sec", "us", "eu", "date_only"}
_VALID_CONCEN_UNITS = {"ng/µL", "nM", "%", "CFU", "OD600"}
_VALID_Y_AXIS_MODES = {"auto", "custom"}

DEFAULTS = {
    "theme": "auto",
    "ui_language": "en",
    "time_tag_format": "iso",
    "default_mode": "kinetics",
    "default_window_size": 4,
    "default_subfolder": None,
    "file_table_height": 240,
    "file_sort_order": "date_desc",
    "max_csv_rows": 0,
    "max_json_rows": 0,
    "event_log_retention_days": 30,
    "chart_height": 600,
    "default_normalize": False,
    "default_split_sources": False,
    "range_expanded_default": False,
    "export_expanded_default": False,
    "log_display_height": 300,
    "log_section_collapsed": False,
    "default_notify": True,
    "default_inf_timeout": False,
    "default_timeout": None,
    "default_timeout_unit": "seconds",
    "default_interval": None,
    "default_interval_unit": "seconds",
    "cdc_axis": "time",
    "cdc_run_mode": "auto",
    # Seconds to wait for a started run to actually reach the device before the
    # client calls it a failed start. Covers port probing + the command
    # handshake (worst case ~15 s of retries) + the firmware settle, none of
    # which produce visible output — hence the wait notice. Configurable because
    # a slow/hub-attached board legitimately takes longer on some machines.
    "reading_start_timeout_sec": 60,
    "merge_directory_picker": False,
    "disable_popups": False,
    "default_concentration_unit": "ng/µL",
    "ai_feedback_enabled": True,
    "y_axis_scale_mode": "auto",
    "y_axis_custom_min": 0.0,
    "y_axis_custom_max": 0.6,
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
    if "ui_language" in updates and updates["ui_language"] in _VALID_UI_LANGUAGES:
        current["ui_language"] = updates["ui_language"]
    if "default_mode" in updates and updates["default_mode"] in _VALID_MODES:
        current["default_mode"] = updates["default_mode"]
    if "default_window_size" in updates:
        try:
            ws = int(updates["default_window_size"])
            if ws >= 2:
                current["default_window_size"] = ws
        except (ValueError, TypeError):
            pass
    if "file_sort_order" in updates and updates["file_sort_order"] in _VALID_SORT_ORDERS:
        current["file_sort_order"] = updates["file_sort_order"]
    if "time_tag_format" in updates and updates["time_tag_format"] in _VALID_TIME_TAG_FORMATS:
        current["time_tag_format"] = updates["time_tag_format"]
    if "default_concentration_unit" in updates and updates["default_concentration_unit"] in _VALID_CONCEN_UNITS:
        current["default_concentration_unit"] = updates["default_concentration_unit"]
    if "cdc_axis" in updates and updates["cdc_axis"] in ("time", "turn"):
        current["cdc_axis"] = updates["cdc_axis"]
    if "cdc_run_mode" in updates and updates["cdc_run_mode"] in ("auto", "manual"):
        current["cdc_run_mode"] = updates["cdc_run_mode"]
    if "reading_start_timeout_sec" in updates:
        try:
            # Floor of 10 s: anything shorter would fire during a normal
            # handshake and kill working runs. Ceiling keeps a typo from
            # disabling the guard outright.
            secs = int(updates["reading_start_timeout_sec"])
            if 10 <= secs <= 600:
                current["reading_start_timeout_sec"] = secs
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
                     "range_expanded_default", "export_expanded_default",
                     "log_section_collapsed", "default_notify",
                     "default_inf_timeout", "merge_directory_picker",
                     "disable_popups", "ai_feedback_enabled"):
        if bool_key in updates:
            current[bool_key] = bool(updates[bool_key])
    if "log_display_height" in updates:
        try:
            h = int(updates["log_display_height"])
            if h >= 100:
                current["log_display_height"] = h
        except (ValueError, TypeError):
            pass
    for unit_key in ("default_timeout_unit", "default_interval_unit"):
        if unit_key in updates and updates[unit_key] in _VALID_UNITS:
            current[unit_key] = updates[unit_key]
    for num_key in ("default_timeout", "default_interval"):
        if num_key in updates:
            val = updates[num_key]
            if val is None:
                current[num_key] = None
            else:
                try:
                    n = float(val)
                    if n >= 0:
                        current[num_key] = n
                except (ValueError, TypeError):
                    pass
    if "y_axis_scale_mode" in updates and updates["y_axis_scale_mode"] in _VALID_Y_AXIS_MODES:
        current["y_axis_scale_mode"] = updates["y_axis_scale_mode"]
    for axis_key in ("y_axis_custom_min", "y_axis_custom_max"):
        if axis_key in updates:
            try:
                current[axis_key] = float(updates[axis_key])
            except (ValueError, TypeError):
                pass
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        return True
    except OSError:
        return False
