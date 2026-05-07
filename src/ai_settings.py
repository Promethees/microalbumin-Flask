import json
import os

_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'ai_settings.json'
)

DEFAULTS = {
    "enabled": True,
    "preferred_languages": ["en"],
    "model": "qwen2.5:7b",
    "ollama_url": "http://localhost:11434",
    "first_run_shown": False,
}

SUPPORTED_LANGUAGES = {
    "en": "English",
    "vi": "Tiếng Việt",
    "zh": "中文 (简体)",
    "fr": "Français",
    "ja": "日本語",
    "ru": "Русский",
}

AVAILABLE_MODELS = [
    {"name": "qwen2.5:7b",  "size": "4.7 GB", "note": "Best multilingual (recommended)"},
    {"name": "qwen2.5:3b",  "size": "1.9 GB", "note": "Lighter, still multilingual"},
    {"name": "llama3.2:3b", "size": "2.0 GB", "note": "Good English/French, weaker Asian"},
    {"name": "mistral:7b",  "size": "4.1 GB", "note": "Good European languages"},
]


def load() -> dict:
    base = dict(DEFAULTS)
    if os.path.exists(_SETTINGS_PATH):
        try:
            with open(_SETTINGS_PATH, 'r', encoding='utf-8') as f:
                stored = json.load(f)

            # Backward-compat: migrate old single-language string to list
            if 'preferred_language' in stored and 'preferred_languages' not in stored:
                stored['preferred_languages'] = [stored.pop('preferred_language')]
            elif 'preferred_language' in stored:
                del stored['preferred_language']

            return {**base, **stored}
        except Exception:
            pass
    return base


def save(settings: dict) -> bool:
    try:
        # Migrate on save as well
        if 'preferred_language' in settings and 'preferred_languages' not in settings:
            settings = dict(settings)
            settings['preferred_languages'] = [settings.pop('preferred_language')]
        elif 'preferred_language' in settings:
            settings = dict(settings)
            del settings['preferred_language']

        merged = {**DEFAULTS, **settings}
        # Guarantee preferred_languages is always a non-empty list
        langs = merged.get('preferred_languages')
        if not isinstance(langs, list) or not langs:
            merged['preferred_languages'] = ['en']

        with open(_SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False
