"""Guard: every runtime asset resolved from ``state.bundle_dir`` is bundled.

A frozen build resolves read-only assets from ``sys._MEIPASS``, which only holds
what ``easyokapi.spec`` lists in ``datas``. An asset the source tree reads via
``state.bundle_dir`` but the spec never bundles fails *silently* in the frozen
build — ``ui_translations/`` was missing this way and every downloaded install
stayed English regardless of ``ui_language`` (loaders are best-effort by design,
so nothing raised).

These tests parse the spec textually rather than executing it: a .spec is only
valid inside PyInstaller's exec context (Analysis/PYZ/EXE are injected globals).
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, 'easyokapi.spec')

# Assets read at runtime from state.bundle_dir. Keep in lockstep with the
# `_data(...)` list in easyokapi.spec and with the bundle_dir consumers in src/.
REQUIRED_BUNDLED = [
    'templates',            # main.py template_folder
    'static',               # main.py static_folder
    'json',                 # default calibration curves seeded by state.py
    'guide_translations',   # ai_assistant.py
    'guide_training.json',  # ai_assistant.py
    'ui_translations',      # i18n.py — the UI localization catalogs
    'sample_data',          # state.py demo seeding
    'legal/EULA.md',        # core_routes.py /legal/<doc>
    'legal/PRIVACY.md',
]


def _spec_text():
    with open(SPEC, 'r', encoding='utf-8') as f:
        return f.read()


def _declared_sources():
    """Relative paths passed as the first argument of each ``_data(...)`` call."""
    return set(re.findall(r"_data\(\s*'([^']+)'", _spec_text()))


class TestSpecDatas:
    def test_every_bundle_dir_asset_is_declared(self):
        declared = _declared_sources()
        missing = [rel for rel in REQUIRED_BUNDLED if rel not in declared]
        assert not missing, (
            "easyokapi.spec does not bundle %s — the frozen build will fall back "
            "silently at runtime" % missing
        )

    def test_declared_assets_exist_in_the_tree(self):
        """`_data()` drops non-existent sources, so a typo bundles nothing."""
        missing = [rel for rel in REQUIRED_BUNDLED
                   if not os.path.exists(os.path.join(ROOT, rel))]
        assert not missing, "required asset absent from the source tree: %s" % missing


class TestUiTranslationsBundled:
    def test_every_supported_language_catalog_ships(self):
        """The spec bundles the whole directory — assert it holds all 7 files."""
        import sys
        sys.path.insert(0, os.path.join(ROOT, 'src'))
        from user_settings import SUPPORTED_LANGUAGES

        d = os.path.join(ROOT, 'ui_translations')
        missing = [lang for lang in SUPPORTED_LANGUAGES
                   if not os.path.isfile(os.path.join(d, '%s.json' % lang))]
        assert not missing, "ui_translations/ is missing catalogs: %s" % missing
