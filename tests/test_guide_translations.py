"""Guide translation overlays (work-list A15; schema shared with main B8)."""
import json
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import ai_assistant  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
LANGS = ["vi", "zh", "fr", "ja", "ru", "ko"]


def _overlay(lang):
    with open(os.path.join(ROOT, "guide_translations", f"{lang}.json"), encoding="utf-8") as f:
        return {e["id"]: e for e in json.load(f)}


GUIDES = {e["id"]: e for e in ai_assistant._load_guide_examples("en")}


@pytest.mark.parametrize("lang", LANGS)
def test_every_guide_has_an_overlay_entry(lang):
    assert set(GUIDES) <= set(_overlay(lang))


@pytest.mark.parametrize("lang", LANGS)
def test_every_step_is_translated(lang):
    missing = []
    for gid, ex in GUIDES.items():
        loc = ai_assistant._guide_example_by_id(gid, lang)
        for en_step, loc_step in zip(ex["steps"], loc["steps"]):
            if not loc_step["description"] or loc_step["description"] == en_step["description"]:
                missing.append((gid, en_step["target"]))
    assert not missing, missing


@pytest.mark.parametrize("lang", LANGS)
def test_keyed_overlay_entries_have_no_orphan_targets(lang):
    orphans = []
    for gid, item in _overlay(lang).items():
        if gid not in GUIDES:
            continue
        targets = {s["target"] for s in GUIDES[gid]["steps"]}
        for st in item.get("steps", []):
            if isinstance(st, dict) and st.get("target") not in targets:
                orphans.append((gid, st.get("target")))
    assert not orphans, orphans


def test_keyed_steps_match_by_target_not_position():
    en_steps = [{"target": "#a", "title": "A", "description": "a"},
                {"target": "#b", "title": "B", "description": "b"},
                {"target": "#a", "title": "A2", "description": "a2"}]
    tr = [{"target": "#b", "description": "bb", "title": "BB"},
          {"target": "#a", "description": "aa"},
          {"target": "#a", "description": "aa2"}]
    got = ai_assistant._overlay_step_translations(en_steps, tr)
    assert [g.get("description") for g in got] == ["aa", "bb", "aa2"]
    assert got[1]["title"] == "BB"


def test_legacy_string_overlays_still_apply_by_position():
    en_steps = [{"target": "#a", "description": "a"}, {"target": "#b", "description": "b"}]
    got = ai_assistant._overlay_step_translations(en_steps, ["x", "y"])
    assert [g["description"] for g in got] == ["x", "y"]


@pytest.mark.parametrize("lang", ["vi", "zh", "fr", "ja", "ru"])
def test_online_only_guides_are_localized_with_titles(lang):
    ex = ai_assistant._guide_example_by_id("google_drive_sync", lang)
    en = GUIDES["google_drive_sync"]
    assert all(a["title"] != b["title"] or "Push" in a["title"] for a, b in zip(ex["steps"], en["steps"]))
    assert ex["steps"][0]["description"] != en["steps"][0]["description"]


# ── First visit follows the page language ────────────────────────────────────

@pytest.fixture
def client():
    import routes.ai_routes as ai_routes
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 't'
    from rate_limit import limiter
    limiter.init_app(app)
    app.register_blueprint(ai_routes.ai_bp)
    return app.test_client()


def test_language_chosen_flag(client):
    assert client.get('/ai/status').get_json()['language_chosen'] is False
    r = client.post('/ai/settings', json={'preferred_languages': ['vi']})
    assert r.get_json()['status'] == 'success'
    assert client.get('/ai/status').get_json()['language_chosen'] is True


def test_settings_reject_unsupported_language(client):
    client.post('/ai/settings', json={'preferred_languages': ['xx']})
    assert client.get('/ai/status').get_json()['settings']['preferred_languages'] == ['en']


def test_chat_strings_cover_every_language():
    import i18n
    import ai_settings
    app = Flask(__name__)
    i18n.init_app(app)
    strings = app.jinja_env.globals['ai_chat_strings']()
    assert set(strings) == set(ai_settings.SUPPORTED_LANGUAGES)
    for lang, cat in strings.items():
        assert cat.get('ai.err.rate_limit'), lang
        assert cat.get('ai.err.upstream_error'), lang


def test_widget_loads_guides_after_status_and_seeds_ui_language():
    js = open(os.path.join(ROOT, 'static', 'script', 'ai-chat.js'), encoding='utf-8').read()
    body = js[js.index('function _loadStatus()'):js.index('function _loadGuides()')]
    assert body.index('AI.activeLang = uiLang') < body.index('_loadGuides();')
    assert 'language_chosen' in body
    assert "'⚠ ' + event.error" not in js
