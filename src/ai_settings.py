from flask import session

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
    "ko": "한국어",
}


def language_chosen() -> bool:
    """True once this session has a chat language of its own.

    Sessions saved before the ``language_chosen`` flag existed carry only
    ``preferred_languages`` (or the legacy ``preferred_language``): a stored
    non-default choice counts as chosen, so those visitors keep their language
    after the deploy instead of being re-seeded from the page language (M4).
    """
    try:
        stored = session.get('ai_settings', {}) or {}
    except Exception:
        return False
    if stored.get('language_chosen'):
        return True
    langs = stored.get('preferred_languages')
    if not langs and stored.get('preferred_language'):
        langs = [stored.get('preferred_language')]
    return isinstance(langs, list) and bool(langs) and langs != DEFAULTS['preferred_languages']


def load() -> dict:
    try:
        stored = dict(session.get('ai_settings', {}))
    except Exception:
        stored = {}

    if 'preferred_language' in stored and 'preferred_languages' not in stored:
        stored['preferred_languages'] = [stored.pop('preferred_language')]
    elif 'preferred_language' in stored:
        del stored['preferred_language']

    result = {**DEFAULTS, **stored}
    langs = result.get('preferred_languages')
    if not isinstance(langs, list) or not langs:
        result['preferred_languages'] = ['en']
    return result


def save(settings: dict) -> bool:
    try:
        settings = dict(settings)
        if 'preferred_language' in settings and 'preferred_languages' not in settings:
            settings['preferred_languages'] = [settings.pop('preferred_language')]
        elif 'preferred_language' in settings:
            del settings['preferred_language']

        allowed = {'enabled', 'preferred_languages', 'first_run_shown', 'language_chosen'}
        clean = {k: v for k, v in settings.items() if k in allowed}
        langs = clean.get('preferred_languages')
        if isinstance(langs, list):
            clean['preferred_languages'] = [l for l in langs if l in SUPPORTED_LANGUAGES]
        merged = {**DEFAULTS, **clean}
        langs = merged.get('preferred_languages')
        if not isinstance(langs, list) or not langs:
            merged['preferred_languages'] = ['en']
        session['ai_settings'] = merged
        return True
    except Exception:
        return False
