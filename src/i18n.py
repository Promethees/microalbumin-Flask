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
import sys

import state
from user_settings import SUPPORTED_LANGUAGES

DEFAULT_UI_LANG = "en"

# Single source of truth for the supported language codes + native names — shared
# with the AI assistant so the Settings dropdown and the chat selector never drift.
SUPPORTED_UI_LANGUAGES = dict(SUPPORTED_LANGUAGES)

_TRANSLATIONS_DIR = os.path.join(state.bundle_dir, "ui_translations")


def _search_dirs():
    """Directories to look for ``<lang>.json`` in, most authoritative first.

    Normally only the bundled copy exists. The extra locations are a recovery
    path for a frozen build shipped without the catalogs (they were absent from
    ``easyokapi.spec`` up to v1.5.4): dropping a ``ui_translations/`` folder next
    to ``EasyOKAPI.exe`` or into the data root restores localization without a
    reinstall. Duplicates are dropped so the common case reads one directory.
    """
    dirs = [_TRANSLATIONS_DIR]
    if getattr(sys, "frozen", False):
        # onedir bundle: sys.executable sits one level above _MEIPASS (_internal/)
        dirs.append(os.path.join(
            os.path.dirname(os.path.abspath(sys.executable)), "ui_translations"))
    dirs.append(os.path.join(state.script_dir, "ui_translations"))

    seen, out = set(), []
    for d in dirs:
        key = os.path.normcase(os.path.abspath(d))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out

# Per-language merged-catalog cache: {lang: {key: value}}.
_cache = {}


def normalize_lang(lang) -> str:
    """Return ``lang`` if it is a supported code, else the default (``en``)."""
    if isinstance(lang, str) and lang in SUPPORTED_UI_LANGUAGES:
        return lang
    return DEFAULT_UI_LANG


def _read_file(lang: str) -> dict:
    """Read one raw ``<lang>.json`` catalog; ``{}`` on any failure.

    The first *existing* copy across ``_search_dirs()`` wins. A file that exists
    but is corrupt or not an object yields ``{}`` — it is the authoritative copy
    and silently reading a stale one from a lower-priority directory would hide
    the breakage. Only an absent (or unreadable) file falls through.
    """
    for d in _search_dirs():
        path = os.path.join(d, "{}.json".format(lang))
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except OSError:
            continue
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if isinstance(v, str)}
        return {}
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
