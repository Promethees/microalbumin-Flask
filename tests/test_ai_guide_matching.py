"""
Regression tests for AI assistant guide routing (src/ai_assistant.py).

Covers the matcher (`_match_guide_example`) and the firing gate
(`_should_launch_guide`) against realistic user phrasings. Guards the fixes for:
  * recording/measurement questions routing to the device-console guide instead
    of the generic app tour (commits ab49712, 6a4c36b);
  * imperative commands firing without an explicit "how to" marker;
  * conceptual questions ("what is R²") still deferring to the LLM;
  * "how do i ..." nav phrasing taking precedence over the "how do" conceptual
    marker;
  * greedy single-shared-word keywords no longer hijacking unrelated queries.
"""
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import ai_assistant  # noqa: E402

# UI contexts the matcher receives from the frontend.
KIN_NODATA = {"mode": "kinetics", "data_loaded": False, "app_started": True}
KIN_DATA = {"mode": "kinetics", "data_loaded": True, "app_started": True}
CAL_DATA = {"mode": "calibrate", "data_loaded": True, "app_started": True}


def route(query, ctx=KIN_NODATA):
    """Return (matched_id_or_None, score) for a query."""
    best, score = ai_assistant._match_guide_example(query, ctx, "en")
    return (best["id"] if best else None), score


def fires(query, ctx=KIN_NODATA):
    """Return True if the query would short-circuit to a guide (vs. the LLM)."""
    best, score = ai_assistant._match_guide_example(query, ctx, "en")
    return bool(best and ai_assistant._should_launch_guide(query, score))


# ---------------------------------------------------------------------------
# Routing: recording-domain questions reach the right guide
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query, expected, ctx", [
    # The originally reported bug: a recording question must reach the device
    # console guide, NOT the generic app-introduction tour.
    ("how to start a colorimetric recording", "measurement_guide", KIN_NODATA),
    ("how do I record data from the colorimeter", "measurement_guide", KIN_NODATA),
    ("how do I start a measurement", "measurement_guide", KIN_NODATA),
    ("how to take colorimeter readings", "measurement_guide", KIN_NODATA),
    ("record a kinetics measurement", "measurement_guide", KIN_NODATA),
    ("start the device", "start_device", KIN_NODATA),
    ("how do I stop the recording", "stop_device", KIN_NODATA),
    ("stop the measurement", "stop_device", KIN_NODATA),
    ("halt the colorimeter", "stop_device", KIN_NODATA),
    ("where do I set the timeout", "set_timeout", KIN_NODATA),
    ("set recording duration", "set_timeout", KIN_NODATA),
    ("change measurement interval", "set_interval", KIN_NODATA),
    ("how to name my recording file", "base_name_input", KIN_NODATA),
    ("where is the recording log", "view_log", KIN_NODATA),
    ("where is my recorded data", "live_view_inactive", KIN_NODATA),
])
def test_recording_queries_route_correctly(query, expected, ctx):
    matched, score = route(query, ctx)
    assert matched == expected, f"{query!r} routed to {matched!r} ({score:.2f}), expected {expected!r}"


def test_recording_query_not_app_introduction():
    """The exact reported regression: must not fall into the 17-step app tour."""
    matched, _ = route("how to start a colorimetric recording", KIN_NODATA)
    assert matched != "app_introduction"
    assert fires("how to start a colorimetric recording", KIN_NODATA)


# ---------------------------------------------------------------------------
# Regression guard: greedy shared-word keywords must not hijack
# ("recording" / "colorimeter" must not pull start/log queries into stop_device)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query", [
    "how to start the sensor recording",
    "how do I begin recording",
    "where is the recording log",
])
def test_recording_queries_not_hijacked_by_stop_device(query):
    matched, _ = route(query, KIN_NODATA)
    assert matched != "stop_device", f"{query!r} wrongly hijacked to stop_device"


# ---------------------------------------------------------------------------
# Firing gate: conceptual questions defer to the LLM
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query", [
    "what is R squared",
    "what is maxRate",
    "explain Michaelis-Menten",
    "why is my R2 low",
    "what does Vmax mean",
    "what is the difference between slope and maxRate",
])
def test_conceptual_questions_do_not_fire_guide(query):
    assert not fires(query, KIN_DATA), f"conceptual query {query!r} should defer to the LLM"


# ---------------------------------------------------------------------------
# Firing gate: nav and imperative phrasings fire
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query, ctx", [
    # "how do i ..." must win over the broader "how do" conceptual marker.
    ("how do I delete a file", KIN_DATA),
    ("how do I stop the recording", KIN_NODATA),
    ("how do I calculate concentration", KIN_DATA),
    # Imperative commands with no nav marker fire on a strong match.
    ("switch to point mode", KIN_NODATA),
    ("change the interval", KIN_NODATA),
    ("merge two csv files", KIN_NODATA),
])
def test_actionable_queries_fire_guide(query, ctx):
    assert fires(query, ctx), f"{query!r} should launch a guide"


# ---------------------------------------------------------------------------
# Helper-level guards
# ---------------------------------------------------------------------------
def test_nav_intent_precedes_conceptual_marker():
    # Contains both "how do i" (nav) and "how do" (conceptual); nav must win.
    assert ai_assistant._has_nav_intent("how do i delete a file") is True


def test_is_conceptual_detects_explanatory_phrasing():
    assert ai_assistant._is_conceptual("what is r squared") is True
    assert ai_assistant._is_conceptual("how to start a recording") is False


def test_weak_match_without_nav_defers_to_llm():
    # A correct but weak (single-keyword) match with no nav marker should fall
    # through to the LLM rather than firing a low-confidence guide.
    matched, score = route("normalize my data", KIN_DATA)
    assert matched == "normalize_data"
    assert score < ai_assistant._STRONG_MATCH_SCORE
    assert not fires("normalize my data", KIN_DATA)


# ===========================================================================
# Regression batch for the four routing defects found by the query harness.
# ===========================================================================

# ---------------------------------------------------------------------------
# #1 — Prefix-only token matching.
# A base word embedded as a *suffix* of a negation/derivation form must not
# cross-match ('select' ⊂ 'deselect'/'unselect'), while genuine stem variants
# ('record'/'recorded', 'file'/'files') still do.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("a, b, expected", [
    ("file", "files", True),
    ("record", "recorded", True),
    ("source", "sources", True),
    ("select", "deselect", False),
    ("select", "unselect", False),
    ("load", "unload", False),
])
def test_token_match_is_prefix_only(a, b, expected):
    assert ai_assistant._token_match(a, b) is expected
    assert ai_assistant._token_match(b, a) is expected  # symmetric


def test_select_file_not_hijacked_by_deselect():
    """'select a file' must reach select_file, not the antonym deselect_file."""
    matched, score = route("where do I select a file", KIN_DATA)
    assert matched == "select_file", f"routed to {matched!r} ({score:.2f})"
    assert fires("where do I select a file", KIN_DATA)


def test_genuine_deselect_still_reaches_deselect_file():
    """Inverse guard: real deselect phrasing still routes to deselect_file."""
    matched, _ = route("how do I deselect a file", KIN_DATA)
    assert matched == "deselect_file"


# ---------------------------------------------------------------------------
# #2 / #3 — Specificity-weighted exact matches.
# One long, specific exact phrase must outrank a pile of short generic or
# near-duplicate fuzzy keywords summed from a less-relevant example.
# ---------------------------------------------------------------------------
def test_export_to_report_beats_generic_export():
    """'export data to report' is the report-subject guide, not plain export."""
    matched, score = route("export data to report", KIN_DATA)
    assert matched == "export_to_report_subject", f"routed to {matched!r} ({score:.2f})"
    assert fires("export data to report", KIN_DATA)


def test_record_data_reaches_measurement_guide_not_live_view():
    """'record data' reaches the measurement guide, not live_view_inactive, whose
    several near-duplicate '...recorded data' keywords previously out-summed it."""
    matched, score = route("how do I record data", KIN_DATA)
    assert matched == "measurement_guide", f"routed to {matched!r} ({score:.2f})"


def test_specificity_weight_orders_exact_matches():
    """A longer exact phrase scores strictly higher than a one-word exact match."""
    qc = ai_assistant._content_words("export data to report")
    long_phrase = ai_assistant._score_keyword("export data to report", "export data to report", qc)
    one_word = ai_assistant._score_keyword("export", "export data to report", qc)
    assert long_phrase > one_word


# ---------------------------------------------------------------------------
# #4 — A single incidental fuzzy hit (0.8) on an out-of-context word must not
# hijack into an unrelated guide. The right guide still fires in its own mode.
# ---------------------------------------------------------------------------
def test_regression_query_wrong_mode_defers_to_llm():
    """'select a regression algorithm' in kinetics must NOT open the file guide
    (its only hit there is the incidental word 'select')."""
    matched, score = route("how do I select a regression algorithm", KIN_NODATA)
    assert not fires("how do I select a regression algorithm", KIN_NODATA), \
        f"weak fuzzy match {matched!r} ({score:.2f}) should defer to the LLM"


def test_regression_query_fires_in_calibrate_mode():
    """The same query in the correct mode reaches the regression-algorithm guide."""
    matched, _ = route("how do I select a regression algorithm", CAL_DATA)
    assert matched == "select_regression"
    assert fires("how do I select a regression algorithm", CAL_DATA)


def test_nav_launch_requires_a_solid_hit():
    """The nav/how-to path needs >= _NAV_LAUNCH_SCORE; a lone 0.8 fuzzy is not enough."""
    assert ai_assistant._NAV_LAUNCH_SCORE >= 1.0


# ---------------------------------------------------------------------------
# Firing gate: explicit full-tour requests launch even on a weak keyword score.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query", [
    "walk me through the whole app",
    "guide me through everything",
    "give me a step by step walkthrough",
])
def test_full_tour_requests_fire_app_introduction(query):
    matched, score = route(query, KIN_NODATA)
    assert matched == "app_introduction", f"{query!r} routed to {matched!r}"
    assert fires(query, KIN_NODATA), f"{query!r} (score {score:.2f}) should launch the tour"


# ===========================================================================
# Semantic-intent layer: spell-correction (typos / phrasing) + local resolver.
# ===========================================================================

# ---------------------------------------------------------------------------
# Query words are spell-corrected to the guide vocabulary BEFORE scoring, so
# misspellings still reach the right guide. Guards keep genuine out-of-domain
# words and antonyms from being mis-corrected.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("typo, canonical", [
    ("measurment", "measurement"),
    ("mesure", "measure"),
    ("calibrte", "calibrate"),
    ("kinetcs", "kinetics"),
    ("colorimiter", "colorimeter"),
])
def test_nearest_keyword_word_fixes_typos(typo, canonical):
    vocab = ai_assistant._guide_vocabulary(ai_assistant._load_guide_examples("en"))
    assert canonical in vocab, f"test premise: {canonical!r} should be in the guide vocabulary"
    assert ai_assistant._nearest_keyword_word(typo, vocab) == canonical


@pytest.mark.parametrize("word", [
    "internal",   # real word, near 'interval' — must NOT be corrected
    "deselect",   # antonym of 'select' — must stay itself
    "report",     # already in vocabulary
])
def test_nearest_keyword_word_leaves_valid_words(word):
    vocab = ai_assistant._guide_vocabulary(ai_assistant._load_guide_examples("en"))
    assert ai_assistant._nearest_keyword_word(word, vocab) == word


@pytest.mark.parametrize("query, expected", [
    ("how to do measurment", "measurement_guide"),
    ("how to mesure kinetics", "measurement_guide"),
    ("how to start a colorimetic recording", "measurement_guide"),
    ("how do I calibrte", "nav_calibrate_mode"),
    ("swich to point mode", "nav_point_mode"),
    ("how do I delete a fle", "delete_file"),
])
def test_misspelled_queries_still_route(query, expected):
    matched, score = route(query, KIN_NODATA)
    assert matched == expected, f"{query!r} routed to {matched!r} ({score:.2f})"


def test_typo_does_not_break_antonym_guard():
    # 'deselct' (typo of deselect) must reach deselect_file, never select_file.
    matched, _ = route("how do I deselct a file", KIN_DATA)
    assert matched == "deselect_file"


# ---------------------------------------------------------------------------
# resolve_guide(): the local, no-LLM resolver used by the /ai/match endpoint.
# ---------------------------------------------------------------------------
def test_resolve_guide_returns_local_steps():
    guide_id, steps = ai_assistant.resolve_guide("how to do measurement", KIN_NODATA, "en")
    assert guide_id == "measurement_guide"
    assert steps and len(steps) == 7
    # Steps are real desktop targets, resolved locally (not the cloud's 2-step stub).
    assert steps[0]["target"] == "#measurement-mode"


def test_resolve_guide_defers_conceptual_and_greeting():
    assert ai_assistant.resolve_guide("what is R squared", KIN_DATA, "en") == (None, None)
    assert ai_assistant.resolve_guide("hello there", KIN_NODATA, "en") == (None, None)
    assert ai_assistant.resolve_guide("", KIN_NODATA, "en") == (None, None)


# ---------------------------------------------------------------------------
# /ai/match HTTP route — local guide resolution, no activation required.
# ---------------------------------------------------------------------------
def test_ai_match_route_fires_for_measurement(client):
    resp = client.post("/ai/match", json={
        "query": "how to do measurment",  # misspelled on purpose
        "language": "en",
        "ui_context": {"mode": "kinetics", "data_loaded": False, "app_started": True},
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["fires"] is True
    assert data["guide_id"] == "measurement_guide"
    assert len(data["steps"]) == 7


def test_ai_match_route_defers_conceptual(client):
    resp = client.post("/ai/match", json={
        "query": "what is maxRate",
        "language": "en",
        "ui_context": {"mode": "kinetics", "data_loaded": True, "app_started": True},
    })
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["fires"] is False
    assert data["guide_id"] is None
    assert data["steps"] == []


# ---------------------------------------------------------------------------
# save_linearity_range — soft mode gate + correct button selector.
# Regression for "how to save linearity range" launching a guide that pointed
# at #log-cdc-data: the hard conditions.mode==kinetics gate excluded the guide
# outside kinetics, so the query fell through to the LLM and landed on the CDC
# logging console. It is now a soft `requires_mode` that keeps the guide
# matchable everywhere and prepends a switch-to-kinetics step instead.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ctx", [
    {"mode": "kinetics", "data_loaded": True, "app_started": True},
    {"mode": "point", "data_loaded": True, "app_started": True},
    {"mode": "calibrate", "data_loaded": True, "app_started": True},
    {"mode": "unknown", "data_loaded": False, "app_started": True},
])
def test_save_linearity_range_fires_in_every_mode(ctx):
    gid, steps = ai_assistant.resolve_guide("how to save linearity range", ctx, "en")
    assert gid == "save_linearity_range"
    assert steps


def test_save_linearity_range_prepends_switch_mode_when_not_kinetics():
    gid, steps = ai_assistant.resolve_guide(
        "how to save linearity range",
        {"mode": "point", "data_loaded": True, "app_started": True}, "en")
    assert steps[0]["target"] == "#meas-mode-section"
    assert "kinetics" in steps[0]["description"]


def test_save_linearity_range_no_switch_mode_in_kinetics():
    gid, steps = ai_assistant.resolve_guide(
        "how to save linearity range",
        {"mode": "kinetics", "data_loaded": True, "app_started": True}, "en")
    assert steps[0]["target"] != "#meas-mode-section"


def test_save_linearity_range_button_uses_data_hint_selector():
    # The real button carries data-hint (native title= is stripped by tooltip.js),
    # so a button[title=...] target would spotlight nothing.
    _, steps = ai_assistant.resolve_guide(
        "how to save linearity range",
        {"mode": "kinetics", "data_loaded": True, "app_started": True}, "en")
    targets = [s["target"] for s in steps]
    assert any('data-hint="Save the linearity range' in t for t in targets)
    assert not any("[title=" in t for t in targets)


@pytest.mark.parametrize("lang", ["vi", "zh", "fr", "ja", "ru"])
def test_save_linearity_range_steps_are_translated(lang):
    # The guide's two steps must be localized in every non-English overlay (they
    # were English-only before) — resolve returns per-language step text.
    _, en_steps = ai_assistant.resolve_guide(
        "how to save linearity range",
        {"mode": "kinetics", "data_loaded": True, "app_started": True}, "en")
    _, steps = ai_assistant.resolve_guide(
        "how to save linearity range",
        {"mode": "kinetics", "data_loaded": True, "app_started": True}, lang)
    assert steps and len(steps) == len(en_steps)
    # Each step description is actually translated (differs from the English one).
    for en_s, s in zip(en_steps, steps):
        assert s["description"] and s["description"] != en_s["description"]


# ---------------------------------------------------------------------------
# edit_file — free-text edit guide (data files + calibration JSON), with a
# dialog-flow step sequence (panel/awaitSwalOpen → in-dialog steps).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "how to edit csv file",
    "how do I edit a data file",
    "how to modify csv",
    "how do I rename a file",
    "change csv values",
])
def test_edit_file_fires_from_free_text(query):
    # Data-CSV edits route to edit_file; calibration-curve edits have their own
    # guide (see test_calibration_edit_routes_to_dedicated_guide).
    gid, steps = ai_assistant.resolve_guide(query, KIN_DATA, "en")
    assert gid == "edit_file"
    assert steps


def test_edit_file_step_sequence():
    _, steps = ai_assistant.resolve_guide("how to edit csv file", KIN_DATA, "en")
    # Opener panel (await-open + expands both file lists) → three in-dialog steps.
    assert steps[0]["target"] == "#file-selection"
    assert steps[0].get("awaitSwalOpen") is True
    assert "json-sel-collapse" in (steps[0].get("expand") or [])
    targets = [s["target"] for s in steps]
    assert targets[1:] == ["#swal-input-filename", "#toggle-mode", ".swal2-confirm"]
    # #toggle-mode's selector doesn't advertise "swal", so it must be flagged.
    assert steps[2].get("dialogStep") is True


@pytest.mark.parametrize("lang,query", [
    ("vi", "chỉnh sửa tệp"),
    ("zh", "如何编辑文件"),
    ("fr", "modifier un fichier"),
    ("ja", "ファイルの編集方法"),
    ("ru", "редактировать файл"),
])
def test_edit_file_translated_and_fires(lang, query):
    gid, steps = ai_assistant.resolve_guide(query, KIN_DATA, lang)
    assert gid == "edit_file"
    _, en_steps = ai_assistant.resolve_guide("edit a file", KIN_DATA, "en")
    # Each step description is localized (differs from English).
    for en_s, s in zip(en_steps, steps):
        assert s["description"] and s["description"] != en_s["description"]


def test_japanese_houhou_registers_as_nav_intent():
    # "方法" ("the method / how to") is the most common Japanese how-to phrasing;
    # it must count as navigation so a bare feature phrase + 方法 launches a guide.
    assert ai_assistant._has_nav_intent("csvを編集する方法") is True


# ---------------------------------------------------------------------------
# edit_calibration_curve — editing a saved calibration JSON (the Select-
# Coefficients panel), distinct from editing a data CSV (edit_file). The panel
# is shown only in kinetics/point, so the guide carries a soft requires_mode
# LIST and points at #cal-json-sel-section.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "how to modify a calibration curve",
    "how to edit a calibration curve",
    "edit calibration json",
    "change the calibration curve",
    "edit standard curve",
])
def test_calibration_edit_routes_to_dedicated_guide(query):
    gid, steps = ai_assistant.resolve_guide(query, KIN_DATA, "en")
    assert gid == "edit_calibration_curve"
    assert steps


def test_calibration_edit_points_at_json_panel():
    _, steps = ai_assistant.resolve_guide("edit calibration curve", KIN_DATA, "en")
    assert steps[0]["target"] == "#cal-json-sel-section"
    assert steps[0].get("awaitSwalOpen") is True
    assert "json-sel-collapse" in (steps[0].get("expand") or [])
    assert [s["target"] for s in steps[1:]] == ["#swal-input-filename", "#toggle-mode", ".swal2-confirm"]


def test_calibration_edit_data_csv_stays_edit_file():
    # A plain CSV edit must NOT be captured by the calibration guide.
    gid, _ = ai_assistant.resolve_guide("how to edit a csv file", KIN_DATA, "en")
    assert gid == "edit_file"


def test_calibration_edit_prepends_switch_mode_outside_kinetics_point():
    # The Select-Coefficients panel is hidden in calibrate/report; a soft
    # requires_mode LIST prepends a switch step naming both acceptable modes.
    _, steps = ai_assistant.resolve_guide(
        "edit calibration json",
        {"mode": "report", "data_loaded": True, "app_started": True}, "en")
    assert steps[0]["target"] == "#meas-mode-section"
    assert "kinetics / point" in steps[0]["description"]


def test_calibration_edit_no_switch_step_in_point_mode():
    _, steps = ai_assistant.resolve_guide(
        "edit calibration json",
        {"mode": "point", "data_loaded": True, "app_started": True}, "en")
    assert steps[0]["target"] == "#cal-json-sel-section"


@pytest.mark.parametrize("lang,query", [
    ("vi", "chỉnh sửa đường chuẩn"),
    ("zh", "修改校准曲线"),
    ("fr", "modifier la courbe d'étalonnage"),
    ("ja", "校正曲線を編集"),
    ("ru", "изменить калибровочную кривую"),
])
def test_calibration_edit_localized(lang, query):
    gid, steps = ai_assistant.resolve_guide(query, KIN_DATA, lang)
    assert gid == "edit_calibration_curve"
    _, en_steps = ai_assistant.resolve_guide("edit calibration curve", KIN_DATA, "en")
    for en_s, s in zip(en_steps, steps):
        assert s["description"] and s["description"] != en_s["description"]


@pytest.mark.parametrize("query", [
    "how to make a calibration curve",
    "how to create a standard curve",
    "what is a calibration curve",
])
def test_calibration_build_and_conceptual_not_captured_by_edit(query):
    # Building a curve (calibrate mode) or asking what one is must not route to
    # the edit guide.
    gid, _ = ai_assistant.resolve_guide(
        query, {"mode": "calibrate", "data_loaded": True, "app_started": True}, "en")
    assert gid != "edit_calibration_curve"


# ---------------------------------------------------------------------------
# app_settings — full dialog walkthrough (opener → every settings group → Save),
# not just the gear button.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "how to open settings",
    "app settings",
    "change the language",
    "change default mode",
    "how to customize the app",
])
def test_app_settings_fires_from_free_text(query):
    gid, steps = ai_assistant.resolve_guide(query, KIN_DATA, "en")
    assert gid == "app_settings"
    assert steps


def test_app_settings_walks_the_whole_dialog():
    _, steps = ai_assistant.resolve_guide("app settings", KIN_DATA, "en")
    # Opener (gear, await-open) then a dialog step per settings group, ending on Save.
    assert steps[0]["target"] == "#settingsBtn"
    assert steps[0].get("awaitSwalOpen") is True
    targets = [s["target"] for s in steps]
    for expected in ["#swal-ui-language", "#swal-theme", "#swal-mode",
                     "#swal-file-sort", "#swal-ai-feedback-enabled", ".swal2-confirm"]:
        assert expected in targets
    assert targets[-1] == ".swal2-confirm"
    # Every in-dialog target is auto-detected as a dialog step by the JS engine's
    # /swal2|#swal-/ heuristic, so no explicit dialogStep flag is needed here.
    for t in targets[1:]:
        assert "#swal-" in t or "swal2" in t


@pytest.mark.parametrize("lang,query", [
    ("zh", "应用设置"),
    ("fr", "paramètres de l'application"),
    ("ja", "アプリ設定"),
    ("ru", "настройки приложения"),
])
def test_app_settings_localized(lang, query):
    gid, steps = ai_assistant.resolve_guide(query, KIN_DATA, lang)
    assert gid == "app_settings"
    _, en_steps = ai_assistant.resolve_guide("app settings", KIN_DATA, "en")
    assert len(steps) == len(en_steps)
    for en_s, s in zip(en_steps, steps):
        assert s["description"] and s["description"] != en_s["description"]


# ---------------------------------------------------------------------------
# merge_files — full flow: enable the folder-browser picker in App Settings,
# then the two chained merge dialogs (Select Files → Next → Merge CSV Files).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "merge files",
    "how to merge csv",
    "combine multiple files",
    "how to combine csv files",
])
def test_merge_fires_from_free_text(query):
    gid, steps = ai_assistant.resolve_guide(query, KIN_DATA, "en")
    assert gid == "merge_files"
    assert steps


def test_merge_walks_settings_then_both_dialogs():
    _, steps = ai_assistant.resolve_guide("merge files", KIN_DATA, "en")
    targets = [s["target"] for s in steps]
    # 1) enable the picker in App Settings
    assert targets[0] == "#settingsBtn" and steps[0].get("awaitSwalOpen")
    assert "#swal-merge-picker" in targets
    # 2) open merge (await the dialog), 3) folder-browser dialog, 4) sort dialog
    assert "#merge-file-btn" in targets
    assert "#merge-pick-accordion" in targets     # dialog 1 (folder browser)
    assert ".merge-file-row" in targets           # dialog 2 (order sources)
    assert "#swal-output" in targets              # dialog 2 output name
    assert targets[-1] == ".swal2-confirm"        # final Merge


def test_merge_picker_step_message_and_chain_flag():
    _, steps = ai_assistant.resolve_guide("merge files", KIN_DATA, "en")
    picker = next(s for s in steps if s["target"] == "#swal-merge-picker")
    assert "checkbox" in picker["description"].lower()
    # The dialog-1 "Next" step must be flagged chainsDialog so the engine steps
    # INTO dialog 2 instead of skipping the run when dialog 1 closes.
    chain = [s for s in steps if s.get("chainsDialog")]
    assert len(chain) == 1
    assert chain[0]["target"] == ".swal2-confirm"


@pytest.mark.parametrize("lang,query", [
    ("fr", "fusionner des fichiers"),
    ("ru", "объединить файлы"),
    ("zh", "如何合并文件"),
    ("ja", "ファイルを結合する方法"),
])
def test_merge_localized(lang, query):
    gid, steps = ai_assistant.resolve_guide(query, KIN_DATA, lang)
    assert gid == "merge_files"
    _, en_steps = ai_assistant.resolve_guide("merge files", KIN_DATA, "en")
    assert len(steps) == len(en_steps)
    assert steps[1]["description"] != en_steps[1]["description"]


def test_requires_mode_list_helper():
    assert ai_assistant._requires_mode_satisfied(["kinetics", "point"], "point") is True
    assert ai_assistant._requires_mode_satisfied(["kinetics", "point"], "calibrate") is False
    assert ai_assistant._requires_mode_satisfied("kinetics", "kinetics") is True


def test_soft_mode_gate_does_not_crossfire_other_guides():
    # Removing save_linearity_range's hard mode gate must not let mode-specific
    # guides bleed across modes: point-mode concentration still routes to the
    # point variant, not the kinetics one.
    assert route("how do I calculate concentration", CAL_DATA)  # sanity: resolves
    gid, _ = ai_assistant.resolve_guide(
        "how do I calculate concentration",
        {"mode": "point", "data_loaded": True, "app_started": True}, "en")
    assert gid == "concentration_calc_point"
