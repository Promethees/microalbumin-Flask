"""Guards for the UI localization catalogs and the language-aware URL layer.

The catalogs are six files that have to be edited in lockstep, and nothing in
the app fails loudly when they drift — a missing key silently falls back to
English, which is exactly the failure mode a test has to catch. The drift guard
below is the main thing here; the rest checks that the catalog loader and the
per-request language resolution behave as `src/i18n.py` documents.

Route-level checks live here too but stay deliberately thin: they exercise the
URL rules through a bare Flask app, because importing main.py pulls in
flask_socketio, firebase and the rest of the production stack, which the test
venv does not install (see tests/conftest.py for the same reasoning).
"""
import json
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import i18n  # noqa: E402

CATALOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ui_translations')
LANGS = ('en', 'vi', 'zh', 'fr', 'ja', 'ru')


def _load(lang):
    with open(os.path.join(CATALOG_DIR, '%s.json' % lang), encoding='utf-8') as f:
        return json.load(f)


# ── Catalog integrity ─────────────────────────────────────────────────────────

def test_every_language_has_a_catalog():
    for lang in LANGS:
        assert os.path.isfile(os.path.join(CATALOG_DIR, '%s.json' % lang)), lang


def test_supported_languages_match_the_files_on_disk():
    assert set(i18n.SUPPORTED_UI_LANGUAGES) == set(LANGS)
    assert i18n.DEFAULT_UI_LANG in i18n.SUPPORTED_UI_LANGUAGES
    # The default is served from the bare path, so it must NOT be a URL prefix.
    assert i18n.DEFAULT_UI_LANG not in i18n.PREFIXED_LANGUAGES
    assert set(i18n.PREFIXED_LANGUAGES) | {i18n.DEFAULT_UI_LANG} == set(LANGS)
    assert set(i18n.HTML_LANG_TAGS) == set(LANGS)


@pytest.mark.parametrize('lang', [l for l in LANGS if l != 'en'])
def test_no_key_drift_against_english(lang):
    """English is the baseline: every catalog holds exactly the same keys.

    A missing key falls back to English at runtime and an extra key is dead
    weight — neither raises, so this is where they get caught.
    """
    english = _load('en')
    other = _load(lang)
    missing = sorted(set(english) - set(other))
    extra = sorted(set(other) - set(english))
    assert not missing, '%s is missing %d keys, e.g. %s' % (lang, len(missing), missing[:5])
    assert not extra, '%s has %d keys English does not, e.g. %s' % (lang, len(extra), extra[:5])


@pytest.mark.parametrize('lang', LANGS)
def test_every_value_is_a_non_empty_string(lang):
    for key, value in _load(lang).items():
        assert isinstance(value, str), '%s: %s is not a string' % (lang, key)
        assert value.strip() != '' or key.endswith('_before'), \
            '%s: %s is empty' % (lang, key)


@pytest.mark.parametrize('lang', [l for l in LANGS if l != 'en'])
def test_placeholders_survive_translation(lang):
    """A `{name}` slot the code substitutes must exist in every translation.

    Losing one turns a sentence into a lie (the number simply never appears);
    inventing one leaves a literal `{n}` on screen.
    """
    import re
    english = _load('en')
    other = _load(lang)
    pattern = re.compile(r'\{[a-z_]+\}')
    for key, value in english.items():
        expected = set(pattern.findall(value))
        actual = set(pattern.findall(other[key]))
        assert expected == actual, \
            '%s: %s has placeholders %s, English has %s' % (lang, key, sorted(actual), sorted(expected))


# ── Catalog loading ───────────────────────────────────────────────────────────

def test_missing_keys_fall_back_to_english():
    i18n.clear_cache()
    english = i18n.load_catalog('en')
    vietnamese = i18n.load_catalog('vi')
    assert set(vietnamese) >= set(english)


def test_unknown_language_yields_english():
    i18n.clear_cache()
    assert i18n.normalize_lang('klingon') == 'en'
    assert i18n.normalize_lang(None) == 'en'
    assert i18n.load_catalog('klingon') == i18n.load_catalog('en')


def test_accept_language_header_picks_the_best_supported_match():
    assert i18n.best_match_from_header('fr-CA,fr;q=0.9,en;q=0.8') == 'fr'
    assert i18n.best_match_from_header('de,en;q=0.5') == 'en'
    assert i18n.best_match_from_header('de-DE') == 'en'   # nothing supported
    assert i18n.best_match_from_header('') == 'en'
    # Lower q on the first tag must not win over a higher one later.
    assert i18n.best_match_from_header('en;q=0.2,ja;q=0.9') == 'ja'


# ── URL layer ─────────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    """A bare app carrying the same page endpoints i18n.init_app localizes."""
    application = Flask(__name__)
    application.config['TESTING'] = True

    @application.route('/')
    def landing():
        return i18n.current_lang()

    @application.route('/terms')
    def terms():
        return i18n.current_lang()

    i18n.init_app(application)
    return application


def test_bare_path_is_english_and_prefixed_paths_are_not(app):
    client = app.test_client()
    assert client.get('/terms').get_data(as_text=True) == 'en'
    for code in i18n.PREFIXED_LANGUAGES:
        assert client.get('/%s/terms' % code).get_data(as_text=True) == code


def test_an_unsupported_prefix_is_not_a_route(app):
    assert app.test_client().get('/de/terms').status_code == 404


def test_url_for_carries_the_active_language(app):
    from flask import g, url_for
    with app.test_request_context('/vi/terms'):
        g.ui_lang = 'vi'
        assert url_for('landing') == '/vi/'
        assert i18n.url_for_lang('en') == '/terms'
        assert i18n.url_for_lang('ja') == '/ja/terms'
    with app.test_request_context('/terms'):
        g.ui_lang = 'en'
        assert url_for('landing') == '/'


def test_alternates_cover_every_language(app):
    with app.test_request_context('/terms'):
        from flask import g
        g.ui_lang = 'en'
        alternates = i18n.lang_alternates()
        assert [code for code, _, _ in alternates] == list(i18n.SUPPORTED_UI_LANGUAGES)
        assert dict((code, url) for code, _, url in alternates)['ru'] == '/ru/terms'


def test_reading_a_language_records_it_in_the_cookie(app):
    client = app.test_client()
    response = client.get('/fr/terms')
    assert 'ui_lang=fr' in response.headers.get('Set-Cookie', '')
    # Second visit in the same language: the cookie already says fr, so nothing
    # is re-sent.
    assert 'Set-Cookie' not in client.get('/fr/terms').headers


def test_language_switch_sets_the_cookie_and_redirects(app):
    client = app.test_client()
    response = client.get('/set-language/ja?next=/ja/terms')
    assert response.status_code == 302
    assert response.headers['Location'] == '/ja/terms'
    assert 'ui_lang=ja' in response.headers.get('Set-Cookie', '')


def test_language_switch_refuses_an_offsite_next(app):
    """`next` is attacker-controllable, so it must stay a same-site path."""
    client = app.test_client()
    for hostile in ('https://evil.example/', '//evil.example/', 'javascript:alert(1)'):
        response = client.get('/set-language/vi', query_string={'next': hostile})
        assert response.headers['Location'] == '/'
