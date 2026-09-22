"""The model id is the server's choice, not a frozen build's (Rule.md §2.13).

A shipped binary cannot be edited, so any model id baked into one outlives the
model itself: installed 1.5.x copies kept asking Groq for `llama-3.1-8b-instant`
after it was retired and answered every chat with a 404 `model_not_found`.
The desktop app therefore sends NO `model` in its proxy payload unless one was
explicitly configured, leaving the choice to the proxy's own `Config.AI_MODEL`.
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import ai_assistant  # noqa: E402
import routes.ai_routes as ai_routes  # noqa: E402


class _Resp:
    """Minimal stand-in for the streaming requests.Response."""
    status_code = 200

    def iter_lines(self):
        return iter([b'data: [DONE]'])


def _captured_payload(monkeypatch, model):
    sent = {}

    def fake_post(url, json=None, **kwargs):
        sent.update(json or {})
        return _Resp()

    # proxy_chat_stream imports `requests` inside the function, so patch the module.
    monkeypatch.setattr('requests.post', fake_post)
    list(ai_assistant.proxy_chat_stream(
        [{'role': 'user', 'content': 'what is a calibration curve'}],
        'en', 'token', 'https://example.invalid', model,
    ))
    return sent


def test_proxy_payload_omits_model_when_unset(monkeypatch):
    assert 'model' not in _captured_payload(monkeypatch, '')


def test_proxy_payload_sends_an_explicit_model(monkeypatch):
    assert _captured_payload(monkeypatch, 'some/model')['model'] == 'some/model'


def test_client_default_leaves_the_choice_to_the_server():
    # An unset AI_MODEL must stay empty all the way to the payload — a default
    # here is the exact bug: it pins a model id inside the shipped binary.
    assert ai_routes._AI_MODEL == os.environ.get('AI_MODEL', '')


def test_dev_direct_groq_path_names_a_real_model():
    # The dev path talks to Groq itself, so it cannot send an empty model.
    assert ai_routes._LOCAL_AI_MODEL
