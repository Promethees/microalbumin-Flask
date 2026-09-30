"""Out-of-scope pre-filter (work-list B6; same code as online A14)."""
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import ai_assistant  # noqa: E402

KIN = {"mode": "kinetics", "data_loaded": True, "app_started": True, "pending": ""}
CAL = {"mode": "calibrate", "data_loaded": True, "app_started": True, "pending": ""}


@pytest.mark.parametrize("query, ctx", [
    ("Where is the time point selection?", CAL),
    ("stock solution dilution", KIN),
    ("how do I select a source", KIN),
])
def test_app_questions_are_not_refused(query, ctx):
    assert ai_assistant._is_out_of_scope(query) is False
    events = ai_assistant.deterministic_events([{"role": "user", "content": query}], "en", ctx)
    assert not events or events[0].get("content") != ai_assistant._OUT_OF_SCOPE["en"]


@pytest.mark.parametrize("query", [
    "what is the stock price of apple",
    "tell me a joke",
    "recommend a movie",
    "play a song",      # music stays out of scope until decision D1
])
def test_off_topic_is_still_refused(query):
    assert ai_assistant._is_out_of_scope(query) is True
