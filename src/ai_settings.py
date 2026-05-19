SUPPORTED_LANGUAGES = {
    "en": "English",
    "vi": "Tiếng Việt",
    "zh": "中文 (简体)",
    "fr": "Français",
    "ja": "日本語",
    "ru": "Русский",
}

DEFAULTS = {
    "enabled": True,
    "preferred_languages": ["en"],
    "first_run_shown": False,
}


def load() -> dict:
    return dict(DEFAULTS)


def save(_settings: dict) -> bool:
    return True
