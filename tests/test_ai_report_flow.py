"""Tests for the report quick/full clarification flow and streamed chat loop.

Guards:
  * the clarification question is asked AND its answer understood in every UI
    language, not English only (the old substring check silently broke for
    vi/zh/fr/ja/ru);
  * chat_stream relays streamed content deltas live and still reassembles tool
    calls from their streamed argument fragments.
"""
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import ai_assistant  # noqa: E402


# ── Report clarification (multilingual) ──────────────────────────────────────

@pytest.mark.parametrize("lang,report_q,quick_a,full_a", [
    ("en", "how do I make a report", "quick one please", "the full one"),
    ("vi", "làm báo cáo thế nào", "nhanh thôi", "đầy đủ nhé"),
    ("zh", "怎么生成报告", "快速", "完整"),
    ("fr", "comment créer un rapport", "rapide", "complet"),
    ("ja", "レポートの作り方", "クイック", "フル"),
    ("ru", "как сделать отчёт", "быстро", "полный"),
])
def test_report_clarification_roundtrip_all_languages(lang, report_q, quick_a, full_a):
    # 1) A bare report ask (no quick/full hint) triggers the clarification.
    assert ai_assistant._needs_report_clarification(report_q, [{"role": "user", "content": report_q}])

    clarify = ai_assistant._REPORT_CLARIFY_PROMPTS[lang]

    # 2) With the clarify prompt as the prior assistant turn, the user's answer resolves.
    quick_msgs = [
        {"role": "user", "content": report_q},
        {"role": "assistant", "content": clarify},
        {"role": "user", "content": quick_a},
    ]
    assert ai_assistant._get_pending_report_type(quick_msgs) == "quick"

    full_msgs = [
        {"role": "user", "content": report_q},
        {"role": "assistant", "content": clarify},
        {"role": "user", "content": full_a},
    ]
    assert ai_assistant._get_pending_report_type(full_msgs) == "full"


def test_no_reask_after_clarify_prompt():
    msgs = [
        {"role": "user", "content": "make a report"},
        {"role": "assistant", "content": ai_assistant._REPORT_CLARIFY_PROMPTS["en"]},
        {"role": "user", "content": "make a report"},
    ]
    assert ai_assistant._needs_report_clarification("make a report", msgs) is False


def test_specific_report_kind_skips_clarification():
    assert ai_assistant._needs_report_clarification("create a quick report", []) is False
    assert ai_assistant._needs_report_clarification("export data to report", []) is False


def test_non_report_query_no_clarification():
    assert ai_assistant._needs_report_clarification("what is R squared", []) is False


# ── Pending state is explicit, not prose-matched ─────────────────────────────
# The clarify turn emits a machine-readable marker that the frontend echoes back
# in ui_context. Recovering the state from the rendered prompt text (the old
# behaviour) meant any edit to that user-facing copy — a translator fixing a
# typo, extra markdown, trailing whitespace — silently killed the flow: the
# user's "quick" was ignored with no error anywhere.

PENDING_CTX = {"mode": "kinetics", "data_loaded": True, "app_started": True,
               "pending": ai_assistant.PENDING_REPORT_TYPE}


def test_clarify_turn_emits_the_pending_marker():
    events = ai_assistant.deterministic_events(
        [{"role": "user", "content": "how do I make a report"}], "en", {})
    assert events is not None
    assert events[0]["type"] == "chunk"
    assert events[0]["content"] == ai_assistant._REPORT_CLARIFY_PROMPTS["en"]
    assert {"type": "pending", "pending": "report_type"} in events


@pytest.mark.parametrize("answer,expected", [("quick one please", "quick"),
                                             ("the full one", "full")])
def test_pending_marker_resolves_the_answer(answer, expected):
    msgs = [
        {"role": "user", "content": "how do I make a report"},
        {"role": "assistant", "content": ai_assistant._REPORT_CLARIFY_PROMPTS["en"]},
        {"role": "user", "content": answer},
    ]
    assert ai_assistant._get_pending_report_type(msgs, PENDING_CTX) == expected


@pytest.mark.parametrize("edited", [
    # The ways the old string-equality check broke. (Trailing whitespace is the
    # one edit it survived — the comparison strips — so it is not listed here.)
    ai_assistant._REPORT_CLARIFY_PROMPTS["en"].replace("quick report", "Quick Report"),
    "> " + ai_assistant._REPORT_CLARIFY_PROMPTS["en"],
    "Would you like a quick report or a full report?",   # copy rewritten wholesale
])
def test_edited_clarify_copy_still_resolves_with_the_marker(edited):
    msgs = [
        {"role": "user", "content": "how do I make a report"},
        {"role": "assistant", "content": edited},
        {"role": "user", "content": "quick please"},
    ]
    # Prose match alone fails (that is the bug) …
    assert ai_assistant._get_pending_report_type(msgs) is None
    # … the explicit marker still resolves it.
    assert ai_assistant._get_pending_report_type(msgs, PENDING_CTX) == "quick"


def test_marker_suppresses_a_re_ask():
    msgs = [
        {"role": "user", "content": "make a report"},
        {"role": "assistant", "content": "…copy that no longer matches…"},
        {"role": "user", "content": "make a report"},
    ]
    assert ai_assistant._needs_report_clarification("make a report", msgs, PENDING_CTX) is False


def test_marker_absent_falls_back_to_the_prose_match():
    """Transitional: a chat already open in a browser across the upgrade still works."""
    msgs = [
        {"role": "user", "content": "how do I make a report"},
        {"role": "assistant", "content": ai_assistant._REPORT_CLARIFY_PROMPTS["vi"]},
        {"role": "user", "content": "nhanh thôi"},
    ]
    no_marker = {"mode": "kinetics", "data_loaded": True, "app_started": True}
    assert ai_assistant._get_pending_report_type(msgs, no_marker) == "quick"


def test_no_pending_marker_means_no_pending_type():
    """An unrelated turn must not be read as an answer to a question never asked."""
    msgs = [
        {"role": "user", "content": "how do I read a file"},
        {"role": "assistant", "content": "Open the file selection panel."},
        {"role": "user", "content": "quick"},
    ]
    assert ai_assistant._get_pending_report_type(msgs, {}) is None


def test_pending_marker_never_reaches_the_model_as_a_message(monkeypatch):
    """The marker rides in ui_context, so no message dict grows an unknown field.

    /ai/chat forwards the caller's own message dicts verbatim to Groq; an extra
    per-message key would be a hard 400 upstream.
    """
    seen = {}

    def fake(api_key, model, messages, tools):
        seen["messages"] = messages
        yield ("chunk", "ok")
        yield ("result", {"role": "assistant", "content": "ok"})

    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", fake)
    list(ai_assistant.chat_stream(
        [{"role": "user", "content": "explain R squared please"}], "en", "k", "m", PENDING_CTX))
    for msg in seen["messages"]:
        assert set(msg) <= {"role", "content", "tool_calls", "tool_call_id"}, msg


def test_quick_answer_launches_the_report_dialog_guide():
    """End-to-end: marker in, guide out (no LLM turn spent)."""
    msgs = [
        {"role": "user", "content": "how do I make a report"},
        {"role": "assistant", "content": "…rewritten copy…"},
        {"role": "user", "content": "quick"},
    ]
    events = ai_assistant.deterministic_events(msgs, "en", PENDING_CTX)
    assert events is not None
    guide = [e for e in events if e.get("type") == "guide"]
    assert guide and guide[0]["guide_action"]["custom_steps"]


# ── Streamed chat loop ───────────────────────────────────────────────────────

def _fake_stream(events):
    """Build a _groq_chat_stream stand-in yielding the given (kind, payload)s."""
    def _gen(api_key, model, messages, tools):
        for e in events:
            yield e
    return _gen


def test_chat_stream_relays_content_deltas(monkeypatch):
    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", _fake_stream([
        ("chunk", "Hel"),
        ("chunk", "lo"),
        ("result", {"role": "assistant", "content": "Hello"}),
    ]))
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "explain R squared please"}], "en", "k", "m", {}))
    chunks = [e["content"] for e in events if e.get("type") == "chunk"]
    assert chunks == ["Hel", "lo"]
    assert all(e.get("type") != "error" for e in events)


def test_chat_stream_surfaces_error(monkeypatch):
    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", _fake_stream([
        ("result", {"role": "assistant", "content": "", "error": "rate_limit"}),
    ]))
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "explain R squared please"}], "en", "k", "m", {}))
    assert any(e.get("type") == "error" and e.get("error") == "rate_limit" for e in events)


# ── Invalid-tool-call recovery ───────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "Failed to call a function. Please adjust your prompt. See 'failed_generation' for more details.",
    "tool call validation failed: parameters for tool get_help_topic did not match schema",
    "Error code: 400 - {'code': 'tool_use_failed'}",
])
def test_map_groq_error_detects_tool_failure(raw):
    assert ai_assistant._map_groq_error(raw) == "tool_call_failed"


def test_chat_stream_recovers_from_tool_call_failure(monkeypatch):
    # First call (tools enabled) → Groq rejects the invalid tool call; the loop
    # must retry the same turn with tools disabled and stream the plain answer.
    calls = []

    def fake(api_key, model, messages, tools):
        calls.append(tools)
        if tools:
            yield ("result", {"role": "assistant", "content": "", "error": "tool_call_failed"})
        else:
            yield ("chunk", "This is a colorimeter data app.")
            yield ("result", {"role": "assistant", "content": "This is a colorimeter data app."})

    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", fake)
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "what is this software about"}], "en", "k", "m", {}))

    assert all(e.get("type") != "error" for e in events)
    text = "".join(e["content"] for e in events if e.get("type") == "chunk")
    assert "colorimeter" in text
    assert calls == [ai_assistant.TOOLS, None]  # retried once with tools off


def test_chat_stream_persistent_tool_failure_surfaces_code(monkeypatch):
    # If it keeps failing even without tools, surface the stable code (the
    # frontend renders it as a friendly message) — and don't loop forever.
    monkeypatch.setattr(ai_assistant, "_groq_chat_stream", _fake_stream([
        ("result", {"role": "assistant", "content": "", "error": "tool_call_failed"}),
    ]))
    events = list(ai_assistant.chat_stream(
        [{"role": "user", "content": "what is this software about"}], "en", "k", "m", {}))
    assert any(e.get("type") == "error" and e.get("error") == "tool_call_failed" for e in events)


# ── Seven-language parity of the clarify vocabulary ──────────────────────────
# `_REPORT_WORDS` / `_QUICK_KWS` / `_FULL_KWS` are substring-matched, so a
# language is only really supported when (a) it has an entry at all and (b) the
# entry is the STEM, not one surface form. Korean had no entry in any of the
# three sets — «보고서 만들기» never even triggered the clarification, so the
# whole flow was inert in 1 of the 7 supported languages. Russian and French had
# entries that missed their own natural adjectival answers: «быстрый отчёт» (the
# exact wording of the app's own quick-report button) and "rapport complète"
# both resolved to None while «быстро» / "complet" worked.

ARMED = {"mode": "kinetics", "data_loaded": True, "app_started": True,
         "pending": ai_assistant.PENDING_REPORT_TYPE}

# (language, bare report ask, quick answers, full answers) — the answers are the
# natural inflected forms a speaker types, plus the app's own button wording.
LANGUAGE_VOCAB = [
    ("en", "how do I make a report", ["quick", "a quick report"], ["full", "the full report"]),
    ("vi", "làm báo cáo thế nào", ["nhanh", "báo cáo nhanh"], ["đầy đủ", "báo cáo đầy đủ"]),
    ("zh", "怎么生成报告", ["快速", "快速报告"], ["完整", "完整报告"]),
    ("fr", "comment créer un rapport", ["rapide", "rapport rapide"], ["complet", "rapport complète"]),
    ("ja", "レポートの作り方", ["クイック", "クイックレポート"], ["フル", "フルレポート"]),
    ("ru", "как сделать отчёт", ["быстро", "быстрый отчёт"], ["полный", "полная версия"]),
    ("ko", "보고서 만들기", ["빠른", "빠른 보고서"], ["전체", "전체 보고서"]),
]


@pytest.mark.parametrize("lang,ask,quick_answers,full_answers", LANGUAGE_VOCAB,
                         ids=[v[0] for v in LANGUAGE_VOCAB])
def test_every_language_can_ask_and_answer(lang, ask, quick_answers, full_answers):
    """All seven languages reach the clarification AND resolve its answer."""
    assert ai_assistant._needs_report_clarification(ask, [{"role": "user", "content": ask}]), (
        f"{lang}: {ask!r} does not trigger the quick/full clarification"
    )
    events = ai_assistant.deterministic_events([{"role": "user", "content": ask}], lang, {})
    assert events and events[0]["content"] == ai_assistant._REPORT_CLARIFY_PROMPTS[lang]
    assert {"type": "pending", "pending": ai_assistant.PENDING_REPORT_TYPE} in events

    for answer in quick_answers:
        msgs = [{"role": "user", "content": answer}]
        assert ai_assistant._get_pending_report_type(msgs, ARMED) == "quick", \
            f"{lang}: {answer!r} did not resolve to quick"
    for answer in full_answers:
        msgs = [{"role": "user", "content": answer}]
        assert ai_assistant._get_pending_report_type(msgs, ARMED) == "full", \
            f"{lang}: {answer!r} did not resolve to full"


@pytest.mark.parametrize("lang", ["en", "vi", "zh", "fr", "ja", "ru", "ko"])
def test_the_apps_own_clarify_prompt_names_words_it_can_parse(lang):
    """The prompt offers two choices; echoing either one back must resolve.

    The Russian button reads «⚡ Быстрый отчёт» while `_QUICK_KWS` only held
    «быстро» — the app asked a question phrased in words it could not read.
    """
    prompt = ai_assistant._REPORT_CLARIFY_PROMPTS[lang].lower()
    assert any(kw in prompt for kw in ai_assistant._QUICK_KWS), \
        f"{lang}: the clarify prompt contains no recognisable quick keyword"
    assert any(kw in prompt for kw in ai_assistant._FULL_KWS), \
        f"{lang}: the clarify prompt contains no recognisable full keyword"


def test_clarify_vocabulary_has_no_unsupported_language():
    """Every keyword must belong to a language the app actually ships.

    `_QUICK_KWS` carried "schnell" — German is not in SUPPORTED_LANGUAGES, so it
    was unreachable weight that only widened the false-positive surface.
    """
    assert "schnell" not in ai_assistant._QUICK_KWS


# ── The transitional prose fallback is bounded by the wire, not by a date ────

def test_a_current_client_never_reaches_the_prose_fallback():
    """`pending` present-but-empty means "marker-aware client, nothing armed".

    The assistant's last turn IS the clarify prompt here, so the prose match
    would fire — it must not, or an unarmed turn could still be read as an
    answer to a question the client says is not outstanding.
    """
    msgs = [
        {"role": "user", "content": "how do I make a report"},
        {"role": "assistant", "content": ai_assistant._REPORT_CLARIFY_PROMPTS["en"]},
        {"role": "user", "content": "quick"},
    ]
    current_client = {"mode": "kinetics", "app_started": True, "pending": ""}
    assert ai_assistant._prose_fallback_applies(current_client) is False
    assert ai_assistant._get_pending_report_type(msgs, current_client) is None
    # …and with the marker actually armed it resolves, no prose involved.
    assert ai_assistant._get_pending_report_type(msgs, ARMED) == "quick"


def test_a_pre_marker_client_still_reaches_the_prose_fallback():
    """The removal criterion: no `pending` key at all == a client older than the marker."""
    msgs = [
        {"role": "user", "content": "how do I make a report"},
        {"role": "assistant", "content": ai_assistant._REPORT_CLARIFY_PROMPTS["ru"]},
        {"role": "user", "content": "быстро"},
    ]
    old_client = {"mode": "kinetics", "app_started": True}
    assert ai_assistant._prose_fallback_applies(old_client) is True
    assert ai_assistant._get_pending_report_type(msgs, old_client) == "quick"


# ── /ai/match must stand down while a clarification is outstanding ───────────
# `resolve_guide` runs BEFORE /ai/chat on every turn. Without this guard the
# clarification is reached only by luck: a learned 👍 weight that pushes a report
# guide over the launch gate answers "make a report" locally and /ai/chat — the
# only place the flow lives — is never called.

@pytest.mark.parametrize("query,language", [
    ("rapport complet", "fr"),
    ("полный отчёт", "ru"),
    ("full report", "en"),
    ("make a report", "en"),
])
def test_local_guide_resolution_stands_down_while_pending(query, language):
    armed = {"mode": "report", "data_loaded": True, "app_started": True,
             "pending": ai_assistant.PENDING_REPORT_TYPE}
    assert ai_assistant.resolve_guide(query, armed, language) == (None, None)


def test_local_guide_resolution_is_unaffected_when_nothing_is_pending():
    """The guard is scoped to the pending turn — normal matching is untouched."""
    ctx = {"mode": "kinetics", "data_loaded": True, "app_started": True, "pending": ""}
    guide_id, steps = ai_assistant.resolve_guide("how do i select a file", ctx, "en")
    assert guide_id and steps


def test_the_french_answer_would_otherwise_open_the_wrong_variant():
    """Why the guard exists: the local match picks a variant the flow would not."""
    unarmed = {"mode": "report", "data_loaded": True, "app_started": True}
    assert ai_assistant.resolve_guide("rapport complet", unarmed, "fr")[0] == "report_full_from_data"


# ── AI.pending lifecycle in the shipped frontend ─────────────────────────────
# The marker is client state, and its whole failure mode is LEAKING: a turn that
# does not consume it echoes it on a later, unrelated turn and the full-report
# walkthrough launches over the user's actual question. This repo has no
# JavaScript test runner, so the lifecycle is pinned structurally against the
# shipped file: one armer, one consumer, one re-armer, and a consume at the head
# of every user-turn entry point. That is the invariant that makes the bound
# structural — the previous design cleared the marker on each exit path
# individually and was already leaking through four of them.

import re  # noqa: E402

AI_CHAT_JS = os.path.join(os.path.dirname(__file__), '..', 'static', 'script', 'ai-chat.js')

_FN_START = re.compile(r'(?:function\s+)?([A-Za-z_$][\w$]*)\s*\([^()]*\)\s*\{')
# `if (...) {`, `for (...) {` … look identical to a method shorthand.
_NOT_A_FUNCTION = frozenset({'if', 'for', 'while', 'switch', 'catch', 'with', 'do', 'else', 'return'})


def _js_source():
    """The file with whole-line comments blanked out.

    Every check below is about CODE; the explanatory comments name AI.pending
    repeatedly and would otherwise match. Only full-line comments are removed,
    so no string literal or regex literal can be corrupted.
    """
    with open(AI_CHAT_JS, encoding='utf-8') as fh:
        src = fh.read()
    out, in_block = [], False
    for line in src.split('\n'):
        stripped = line.strip()
        if in_block:
            out.append('')
            if '*/' in stripped:
                in_block = False
            continue
        if stripped.startswith('/*'):
            out.append('')
            in_block = '*/' not in stripped
            continue
        out.append('' if stripped.startswith('//') else line)
    return '\n'.join(out)


def _enclosing_function(src, offset):
    """Innermost named JS function whose body spans `offset`."""
    best = None
    for m in _FN_START.finditer(src):
        if m.start() > offset:
            break
        if m.group(1) in _NOT_A_FUNCTION:
            continue
        depth, i, end = 0, m.end() - 1, None
        while i < len(src):
            if src[i] == '{':
                depth += 1
            elif src[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
            i += 1
        if end is not None and m.end() <= offset <= end:
            if best is None or m.start() > best[1]:
                best = (m.group(1), m.start())
    return best[0] if best else None


def _body_of(src, name):
    """Source text of the named function's body (first definition wins)."""
    for m in _FN_START.finditer(src):
        if m.group(1) != name or name in _NOT_A_FUNCTION:
            continue
        depth, i = 0, m.end() - 1
        while i < len(src):
            if src[i] == '{':
                depth += 1
            elif src[i] == '}':
                depth -= 1
                if depth == 0:
                    return src[m.end():i]
            i += 1
    raise AssertionError(f"{name}() not found in ai-chat.js")


def test_ai_pending_is_written_only_by_its_owners():
    """Any new bespoke clear/arm is a leak waiting to happen — fail on sight."""
    src = _js_source()
    writers = sorted({
        _enclosing_function(src, m.start())
        for m in re.finditer(r'\bAI\.pending\s*=', src)
    })
    assert writers == ['_consumePending', '_rearmPending', '_sendToLLM', 'clearHistory', 'newChat'], (
        "AI.pending must be assigned only by the consume/re-arm helpers, the "
        f"`pending` SSE handler in _sendToLLM, and the two reset paths; got {writers}"
    )


@pytest.mark.parametrize("fn", ["send", "_cmdExecute", "_saveEdit"])
def test_every_user_turn_entry_point_consumes_the_marker(fn):
    """send() is not enough: the command picker enters via _cmdExecute and the
    edit-and-resend flow enters via _saveEdit, both bypassing send()."""
    assert '_consumePending()' in _body_of(_js_source(), fn), \
        f"{fn}() does not consume AI.pending — the marker can outlive its turn"


def test_editing_a_message_drops_the_marker_rather_than_forwarding_it():
    """The edit-and-resend regression, pinned at the two places that cause it.

    Repro it fixed: ask "how do I make a report?", get the quick/full question,
    then edit your own message to "how do I export to Excel?" and save. The old
    _saveEdit truncated AI.messages but not AI.pending, so the edited text was
    sent with ui_context.pending='report_type' — see the backend half below.
    """
    body = _body_of(_js_source(), '_saveEdit')
    assert '_consumePending()' in body
    # The resend must not hand a marker on to _sendToLLM either.
    assert re.search(r'_sendToLLM\(\s*newText\s*\)', body), \
        "_saveEdit must resend with no pending marker"


def test_edited_query_with_a_leaked_marker_hijacks_the_turn():
    """The backend half: this is WHY _saveEdit must drop the marker.

    'excel' is a _FULL_KWS word, so a leaked marker turns an unrelated edited
    question into a full-report walkthrough instead of an answer.
    """
    edited = [{"role": "user", "content": "how do i export to excel"}]
    assert ai_assistant._get_pending_report_type(edited, ARMED) == "full"
    # With the marker correctly dropped, the same turn is just a question.
    unarmed = dict(ARMED, pending="")
    assert ai_assistant._get_pending_report_type(edited, unarmed) is None
    assert ai_assistant.deterministic_events(edited, "en", unarmed) is None


def test_the_context_builder_does_not_read_the_marker_itself():
    """`pending` is passed in, so a caller that is not a turn cannot leak it.

    _getUiContext() is also called by the guide launchers (_runGuideById,
    _runRedoAction, the live-view picker); reading AI.pending there is how a
    marker reached a request that was not the turn it belonged to.
    """
    body = _body_of(_js_source(), '_getUiContext')
    assert 'AI.pending' not in body
    assert 'pending: pending ||' in body


def test_the_marker_key_is_always_sent():
    """Its ABSENCE is the pre-marker-client signal the backend keys off."""
    assert re.search(r'pending:\s*pending\s*\|\|\s*[\'"]{2}', _body_of(_js_source(), '_getUiContext'))


def test_local_guide_lookup_is_skipped_while_a_clarification_is_outstanding():
    body = _body_of(_js_source(), '_tryLocalGuide')
    assert re.search(r'if\s*\(pending\)\s*return\s+Promise\.resolve\(false\)', body), \
        "_tryLocalGuide must stand down while AI.pending is armed (see resolve_guide)"


def test_a_turn_that_never_reached_the_server_re_arms():
    """Rate limit and transport failure must not burn the clarification."""
    body = _body_of(_js_source(), '_sendToLLM')
    assert body.count('_rearmPending(pending)') == 3, (
        "expected the client rate-limit return, the non-ok response and the "
        "network-error catch to each put the marker back"
    )


# ── B5: report-topic questions are not asked quick-vs-full ───────────────────

REPORT_MODE = {"mode": "report", "data_loaded": False, "app_started": True, "pending": ""}
KIN_CTX = {"mode": "kinetics", "data_loaded": True, "app_started": True, "pending": ""}


@pytest.mark.parametrize("query, ctx", [
    ("what is a report subject", REPORT_MODE),
    ("reporting issue with the chart", REPORT_MODE),
    ("the chart was reported wrong", KIN_CTX),
    ("how do I rename a report subject", REPORT_MODE),
    ("change the report layout watermark", REPORT_MODE),
    ("qu'est-ce qu'un sujet de rapport", REPORT_MODE),
    ("chủ đề báo cáo là gì", REPORT_MODE),
])
def test_report_topic_questions_do_not_get_the_question(query, ctx):
    events = ai_assistant.deterministic_events([{"role": "user", "content": query}], "en", ctx)
    assert not events or events[0].get("content") not in ai_assistant._REPORT_CLARIFY_PROMPTS.values()


@pytest.mark.parametrize("lang,ask", [(v[0], v[1]) for v in LANGUAGE_VOCAB])
def test_make_a_report_still_asks_in_report_mode(lang, ask):
    events = ai_assistant.deterministic_events([{"role": "user", "content": ask}], lang, REPORT_MODE)
    assert events and events[0]["content"] == ai_assistant._REPORT_CLARIFY_PROMPTS[lang]


# ── B11: one source for the full-report walkthrough ──────────────────────────

def _guide_targets(gid):
    return [s["target"] for s in ai_assistant._guide_example_by_id(gid, "en")["steps"]]


@pytest.mark.parametrize("mode, gid", [("kinetics", "report_full_from_data"),
                                       ("report", "report_full_in_report")])
def test_full_answer_equals_the_guide(mode, gid):
    ctx = {"mode": mode, "data_loaded": True, "app_started": True,
           "pending": ai_assistant.PENDING_REPORT_TYPE}
    events = ai_assistant.deterministic_events([{"role": "user", "content": "full"}], "en", ctx)
    steps = next(e for e in events if e["type"] == "guide")["guide_action"]["custom_steps"]
    assert [s["target"] for s in steps] == _guide_targets(gid)


def test_subject_step_comes_before_the_console():
    t = _guide_targets("report_full_from_data")
    assert t.index('#measurement-mode button[data-mode="report"]') < t.index("#file-selection") \
        < t.index("#report-console-section")
    x = _guide_targets("export_excel_nav")
    assert x.index("#file-selection") < x.index('button[onclick="finalizeReportExcel()"]')


def test_report_mode_step_targets_the_report_button_not_the_whole_section():
    for gid in ("report_full_from_data", "export_excel_nav"):
        assert "#measurement-mode" not in _guide_targets(gid)


def test_cal_xlabel_step_is_optional():
    ex = ai_assistant._guide_example_by_id("report_full_in_report", "en")
    step = next(s for s in ex["steps"] if s["target"] == ".cal-xlabel-input")
    assert step.get("optional") is True


def test_no_python_full_report_constants():
    assert not hasattr(ai_assistant, "_FULL_REPORT_STEPS_FROM_DATA")
    assert not hasattr(ai_assistant, "_FULL_REPORT_STEPS_IN_REPORT")


def test_slash_command_uses_the_same_guide_ids():
    js = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'script', 'ai-chat.js'),
              encoding='utf-8').read()
    for mode in ("kinetics", "report"):
        assert f"'{ai_assistant._full_report_guide_id(mode)}'" in js


# ── L1 (shared with online): "add to report" / report settings ───────────────

@pytest.mark.parametrize("query", [
    "thêm vào báo cáo", "ajouter au rapport", "добавить в отчёт", "添加到报告",
    "レポートに追加", "보고서에 추가", "настройки отчёта", "报告格式设置", "paramètres de rapport",
    "report settings",
])
def test_add_to_report_and_report_settings_are_not_asked(query):
    assert ai_assistant._needs_report_clarification(
        query, [{"role": "user", "content": query}], REPORT_MODE) is False
