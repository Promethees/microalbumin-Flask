"""UI localization (i18n) catalogs for Easy OKAPI.

Per-language flat key->string catalogs live in ``ui_translations/<lang>.json``,
shipped beside the app and resolved from ``state.bundle_dir`` (the read-only
program folder), mirroring how ``ai_assistant.py`` loads ``guide_translations/``.

English (``en.json``) is the baseline source of truth: a non-English catalog is
overlaid onto English so any missing key falls back to English. Loading is
best-effort and cached per process — a missing or broken file never raises into
a request, it just yields English (or an empty dict if even English is absent).

Technical terms (mode names, units, Absorbance, maxRate, rSquared, CSV/JSON,
brand names) are intentionally left in English inside every catalog.
"""

import json
import os

import state
from ai_settings import SUPPORTED_LANGUAGES

DEFAULT_UI_LANG = "en"

# Single source of truth for the supported language codes + native names — shared
# with the AI assistant so the Settings dropdown and the chat selector never drift.
SUPPORTED_UI_LANGUAGES = dict(SUPPORTED_LANGUAGES)

_TRANSLATIONS_DIR = os.path.join(state.bundle_dir, "ui_translations")

# Per-language merged-catalog cache: {lang: {key: value}}.
_cache = {}


def normalize_lang(lang) -> str:
    """Return ``lang`` if it is a supported code, else the default (``en``)."""
    if isinstance(lang, str) and lang in SUPPORTED_UI_LANGUAGES:
        return lang
    return DEFAULT_UI_LANG


def _read_file(lang: str) -> dict:
    """Read one raw ``<lang>.json`` catalog; ``{}`` on any failure."""
    path = os.path.join(_TRANSLATIONS_DIR, "{}.json".format(lang))
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if isinstance(v, str)}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def load_catalog(lang: str) -> dict:
    """Return the merged catalog for ``lang`` (English baseline + overlay).

    Missing keys in the requested language fall back to the English value. The
    result is cached per language.
    """
    lang = normalize_lang(lang)
    if lang in _cache:
        return _cache[lang]

    base = _read_file(DEFAULT_UI_LANG)
    if lang == DEFAULT_UI_LANG:
        merged = dict(base)
    else:
        merged = dict(base)
        merged.update(_read_file(lang))  # overlay translated keys over English

    _cache[lang] = merged
    return merged


def clear_cache() -> None:
    """Drop the in-memory catalog cache (used by tests)."""
    _cache.clear()
