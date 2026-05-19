import json
import os

_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'ai_settings.json'
)

DEFAULTS = {
    "enabled": True,
    "preferred_languages": ["en"],
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


def load() -> dict:
    base = dict(DEFAULTS)
    if os.path.exists(_SETTINGS_PATH):
        try:
            with open(_SETTINGS_PATH, 'r', encoding='utf-8') as f:
                stored = json.load(f)

            if 'preferred_language' in stored and 'preferred_languages' not in stored:
                stored['preferred_languages'] = [stored.pop('preferred_language')]
            elif 'preferred_language' in stored:
                del stored['preferred_language']

            # Drop obsolete Ollama keys
            for obsolete in ('model', 'ollama_url'):
                stored.pop(obsolete, None)

            return {**base, **stored}
        except Exception:
            pass
    return base


def save(settings: dict) -> bool:
    try:
        if 'preferred_language' in settings and 'preferred_languages' not in settings:
            settings = dict(settings)
            settings['preferred_languages'] = [settings.pop('preferred_language')]
        elif 'preferred_language' in settings:
            settings = dict(settings)
            del settings['preferred_language']

        allowed = {'enabled', 'preferred_languages', 'first_run_shown'}
        clean = {k: v for k, v in settings.items() if k in allowed}
        merged = {**DEFAULTS, **clean}
        langs = merged.get('preferred_languages')
        if not isinstance(langs, list) or not langs:
            merged['preferred_languages'] = ['en']

        with open(_SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False
