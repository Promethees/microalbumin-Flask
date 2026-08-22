import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import state
import i18n
import user_settings


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------

class TestLoadCatalog:
    def setup_method(self):
        i18n.clear_cache()

    def test_english_catalog_is_non_empty(self):
        en = i18n.load_catalog("en")
        assert isinstance(en, dict)
        assert len(en) > 0
        # A couple of representative keys must exist.
        assert "topbar.shutdown" in en
        assert "settings.language" in en

    def test_every_language_has_same_keys_as_english(self):
        """No orphan keys and no missing translations in any language file —
        keeps en.json and the 6 translated files in lockstep (Rule §2.22)."""
        en_keys = set(i18n.load_catalog("en"))
        for lang in i18n.SUPPORTED_UI_LANGUAGES:
            if lang == "en":
                continue
            i18n.clear_cache()
            cat = i18n.load_catalog(lang)
            cat_keys = set(cat)
            assert cat_keys == en_keys, (
                "%s catalog key drift: missing=%s extra=%s"
                % (lang, sorted(en_keys - cat_keys), sorted(cat_keys - en_keys))
            )

    def test_missing_key_falls_back_to_english(self, monkeypatch, tmp_path):
        # Point the loader at a temp dir with an English baseline and a partial
        # French overlay; the missing French key must fall back to English.
        d = tmp_path / "ui_translations"
        d.mkdir()
        (d / "en.json").write_text(
            '{"a": "Alpha", "b": "Beta"}', encoding="utf-8")
        (d / "fr.json").write_text('{"a": "Alpha-fr"}', encoding="utf-8")
        monkeypatch.setattr(i18n, "_TRANSLATIONS_DIR", str(d))
        i18n.clear_cache()
        fr = i18n.load_catalog("fr")
        assert fr["a"] == "Alpha-fr"   # overlaid
        assert fr["b"] == "Beta"       # fell back to English

    def test_broken_file_is_best_effort(self, monkeypatch, tmp_path):
        d = tmp_path / "ui_translations"
        d.mkdir()
        (d / "en.json").write_text("{ not valid json", encoding="utf-8")
        monkeypatch.setattr(i18n, "_TRANSLATIONS_DIR", str(d))
        i18n.clear_cache()
        # Must not raise; returns an empty dict rather than blowing up a request.
        # A file that exists but is corrupt is authoritative — the loader must NOT
        # fall through to a lower-priority directory and hide the breakage.
        assert i18n.load_catalog("en") == {}


# ---------------------------------------------------------------------------
# Catalog lookup path (frozen-build recovery)
# ---------------------------------------------------------------------------

class TestSearchDirs:
    def setup_method(self):
        i18n.clear_cache()

    def teardown_method(self):
        i18n.clear_cache()

    def test_bundle_dir_is_first(self):
        dirs = i18n._search_dirs()
        assert dirs[0] == i18n._TRANSLATIONS_DIR

    def test_no_duplicate_dirs(self):
        """In a source run bundle_dir == script_dir; the list must collapse."""
        dirs = [os.path.normcase(os.path.abspath(d)) for d in i18n._search_dirs()]
        assert len(dirs) == len(set(dirs))

    def test_data_root_copy_recovers_a_missing_bundled_catalog(self, monkeypatch, tmp_path):
        """The v1.5.3 frozen build shipped without ui_translations/ — dropping the
        folder into the data root must restore localization without a reinstall."""
        bundled = tmp_path / "bundle" / "ui_translations"   # deliberately absent
        recovery = tmp_path / "data" / "ui_translations"
        recovery.mkdir(parents=True)
        (recovery / "en.json").write_text('{"a": "Alpha"}', encoding="utf-8")
        (recovery / "fr.json").write_text('{"a": "Alpha-fr"}', encoding="utf-8")

        monkeypatch.setattr(i18n, "_TRANSLATIONS_DIR", str(bundled))
        monkeypatch.setattr(state, "script_dir", str(tmp_path / "data"))
        i18n.clear_cache()
        assert i18n.load_catalog("fr")["a"] == "Alpha-fr"

    def test_bundled_copy_wins_over_the_recovery_copy(self, monkeypatch, tmp_path):
        bundled = tmp_path / "bundle" / "ui_translations"
        bundled.mkdir(parents=True)
        (bundled / "en.json").write_text('{"a": "bundled"}', encoding="utf-8")
        recovery = tmp_path / "data" / "ui_translations"
        recovery.mkdir(parents=True)
        (recovery / "en.json").write_text('{"a": "stale"}', encoding="utf-8")

        monkeypatch.setattr(i18n, "_TRANSLATIONS_DIR", str(bundled))
        monkeypatch.setattr(state, "script_dir", str(tmp_path / "data"))
        i18n.clear_cache()
        assert i18n.load_catalog("en")["a"] == "bundled"


# ---------------------------------------------------------------------------
# normalize_lang
# ---------------------------------------------------------------------------

class TestNormalizeLang:
    def test_supported_passthrough(self):
        for lang in ("en", "vi", "zh", "fr", "ja", "ru"):
            assert i18n.normalize_lang(lang) == lang

    def test_unknown_clamps_to_default(self):
        assert i18n.normalize_lang("xx") == "en"
        assert i18n.normalize_lang("") == "en"
        assert i18n.normalize_lang(None) == "en"


# ---------------------------------------------------------------------------
# user_settings.ui_language
# ---------------------------------------------------------------------------

class TestUiLanguageSetting:
    def test_default_is_english(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.load()["ui_language"] == "en"

    def test_valid_language_persists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert user_settings.save({"ui_language": "fr"}) is True
        assert user_settings.load()["ui_language"] == "fr"

    def test_invalid_language_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"ui_language": "vi"})
        user_settings.save({"ui_language": "klingon"})
        # The bogus code is ignored; the last valid value stands.
        assert user_settings.load()["ui_language"] == "vi"
