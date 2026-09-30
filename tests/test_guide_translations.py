"""Guide translation overlays (work-list B8; schema shared with online A15).

Overlay steps are {target, description, title} dicts matched by TARGET, so a
step inserted into guide_training.json can never shift a translation onto the
wrong element (the positional scheme did exactly that to navigate_directory /
saving_directory). Legacy string entries still apply by position.
"""
import json
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import ai_assistant  # noqa: E402
import user_settings  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
LANGS = [l for l in user_settings.SUPPORTED_LANGUAGES if l != "en"]
GUIDES = {e["id"]: e for e in ai_assistant._load_guide_examples("en")}


def _overlay(lang):
    with open(os.path.join(ROOT, "guide_translations", f"{lang}.json"), encoding="utf-8") as f:
        return {e["id"]: e for e in json.load(f)}


@pytest.mark.parametrize("lang", LANGS)
def test_same_guide_ids_as_the_baseline(lang):
    assert set(_overlay(lang)) == set(GUIDES)


@pytest.mark.parametrize("lang", LANGS)
def test_every_en_step_has_a_translation(lang):
    missing = []
    for gid, ex in GUIDES.items():
        loc = ai_assistant._guide_example_by_id(gid, lang)
        for en_step, loc_step in zip(ex["steps"], loc["steps"]):
            if not loc_step["description"].strip() or loc_step["description"] == en_step["description"]:
                missing.append((gid, en_step["target"]))
    assert not missing, missing


@pytest.mark.parametrize("lang", LANGS)
def test_no_orphan_targets(lang):
    orphans = []
    for gid, item in _overlay(lang).items():
        en_targets = [s["target"] for s in GUIDES[gid]["steps"]]
        keyed = [s for s in item.get("steps", []) if isinstance(s, dict)]
        for st in keyed:
            if st.get("target") not in en_targets:
                orphans.append((gid, st.get("target")))
        # A repeated target needs as many entries as the EN guide has.
        for t in set(en_targets):
            if keyed and sum(1 for s in keyed if s.get("target") == t) > en_targets.count(t):
                orphans.append((gid, t, "extra"))
    assert not orphans, orphans


def test_keyed_steps_match_by_target_not_position():
    en_steps = [{"target": "#a", "description": "a"},
                {"target": "#b", "description": "b"},
                {"target": "#a", "description": "a2"}]
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


def test_vietnamese_saving_directory_matches_the_real_controls():
    ex = ai_assistant._guide_example_by_id("saving_directory", "vi")
    assert [s["target"] for s in ex["steps"]] == [
        "#cdc-save-section", "#cdc-subfolder-select", "#cdc-new-folder-name"]
    assert "Existing" in ex["steps"][0]["description"] and "New" in ex["steps"][0]["description"]
    assert "Browse Saving Location" not in json.dumps(ex, ensure_ascii=False)
    assert all(s["title"] != GUIDES["saving_directory"]["steps"][i]["title"]
               for i, s in enumerate(ex["steps"]))


@pytest.mark.parametrize("lang", LANGS)
def test_save_range_csv_is_translated(lang):
    ex = ai_assistant._guide_example_by_id("save_range_csv", lang)
    en = GUIDES["save_range_csv"]
    assert ex["steps"][0]["description"] != en["steps"][0]["description"]
