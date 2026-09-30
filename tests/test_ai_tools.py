"""Tool execution, help docs and language handling in src/ai_assistant.py."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import ai_assistant  # noqa: E402
import ai_settings  # noqa: E402


# ── A17: language validation ─────────────────────────────────────────────────

def test_valid_langs_is_the_settings_registry():
    assert ai_assistant.VALID_LANGS == frozenset(ai_settings.SUPPORTED_LANGUAGES)


def test_unknown_language_falls_back_to_en_and_cache_stays_bounded():
    ai_assistant._GUIDE_CACHE.clear()
    en = ai_assistant._load_guide_examples("en")
    for junk in ["xx", "../etc", "EN", "", "zz" * 50] + [f"l{i}" for i in range(100)]:
        assert ai_assistant._load_guide_examples(junk) == en
    assert set(ai_assistant._GUIDE_CACHE) <= set(ai_settings.SUPPORTED_LANGUAGES)
