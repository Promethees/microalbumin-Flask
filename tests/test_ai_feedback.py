"""Tests for AI answer feedback + the learned guide-matcher weight layer.

Covers src/ai_feedback.py (logging, weight nudging, clamping, reinforced terms),
its effect on ai_assistant._match_guide_example, and the /ai/feedback route.
"""
import json
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import ai_feedback  # noqa: E402
import ai_assistant  # noqa: E402
import state  # noqa: E402


@pytest.fixture
def feedback_dir(tmp_path, monkeypatch):
    """Point the feedback files at an isolated tmp dir and reset the cache.

    ai_feedback reads state.script_dir at call time, so monkeypatching it here
    redirects both the log and the weights file. The cache is reset on the way
    in AND out so this test can't perturb other tests (e.g. the matcher suite).
    """
    monkeypatch.setattr(state, 'script_dir', str(tmp_path))
    ai_feedback.reload()
    yield tmp_path
    monkeypatch.undo()
    ai_feedback.reload()


# ── Logging ──────────────────────────────────────────────────────────────────

def test_feedback_is_logged(feedback_dir):
    ai_feedback.record_feedback('up', source='llm', query='what is R2',
                                answer='R-squared is...', language='en')
    ai_feedback.record_feedback('down', source='llm', query='bad', answer='nope',
                                comment='wrong answer')
    rows = ai_feedback.read_feedback()
    assert len(rows) == 2
    assert rows[0]['rating'] == 'up'
    assert rows[1]['rating'] == 'down'
    assert rows[1]['comment'] == 'wrong answer'
    # The append-only log file exists in the redirected dir.
    assert os.path.exists(os.path.join(str(feedback_dir), 'ai_feedback.jsonl'))


def test_llm_feedback_does_not_change_weights(feedback_dir):
    # LLM answers carry no guide_id → no coefficient should move.
    weight = ai_feedback.record_feedback('up', source='llm', query='hello')
    assert weight is None
    assert ai_feedback.learned_bonus('measurement_guide') == 0.0


# ── Weight nudging ───────────────────────────────────────────────────────────

def test_thumbs_up_raises_weight_and_records_terms(feedback_dir):
    w1 = ai_feedback.record_feedback('up', source='guide',
                                     guide_id='measurement_guide',
                                     query='record a colorimeter measurement')
    assert w1 == pytest.approx(ai_feedback._UP_STEP)
    assert ai_feedback.learned_bonus('measurement_guide') == pytest.approx(ai_feedback._UP_STEP)
    # Specific content words from the query are reinforced; short/filler dropped.
    terms = ai_feedback.learned_terms('measurement_guide')
    assert 'colorimeter' in terms
    assert 'measurement' in terms
    assert 'a' not in terms


def test_thumbs_down_lowers_weight(feedback_dir):
    ai_feedback.record_feedback('up', source='guide', guide_id='g', query='alpha bravo')
    w = ai_feedback.record_feedback('down', source='guide', guide_id='g', query='alpha bravo')
    assert w == pytest.approx(ai_feedback._UP_STEP - ai_feedback._DOWN_STEP)
    # A down-vote must not erase reinforced vocabulary.
    assert 'alpha' in ai_feedback.learned_terms('g')


def test_weight_is_clamped(feedback_dir):
    for _ in range(20):
        ai_feedback.record_feedback('up', source='guide', guide_id='g', query='x')
    assert ai_feedback.learned_bonus('g') == pytest.approx(ai_feedback._MAX_WEIGHT)
    for _ in range(40):
        ai_feedback.record_feedback('down', source='guide', guide_id='g', query='x')
    assert ai_feedback.learned_bonus('g') == pytest.approx(ai_feedback._MIN_WEIGHT)


def test_weights_persist_to_disk(feedback_dir):
    ai_feedback.record_feedback('up', source='guide', guide_id='g', query='persisted')
    path = os.path.join(str(feedback_dir), 'ai_guide_weights.json')
    assert os.path.exists(path)
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    assert data['g']['weight'] == pytest.approx(ai_feedback._UP_STEP)


# ── Matcher integration ──────────────────────────────────────────────────────

KIN = {"mode": "kinetics", "data_loaded": False, "app_started": True}


def test_thumbs_up_increases_match_score(feedback_dir):
    query = "how do I start a measurement"
    best, base = ai_assistant._match_guide_example(query, KIN, "en")
    assert best is not None
    gid = best["id"]
    ai_feedback.record_feedback('up', source='guide', guide_id=gid, query=query)
    _, boosted = ai_assistant._match_guide_example(query, KIN, "en")
    # A 👍 lifts the score by at least the weight coefficient (the reinforced
    # query terms re-match too, so the real boost is larger).
    assert boosted >= base + ai_feedback._UP_STEP
    assert ai_feedback.learned_bonus(gid) == pytest.approx(ai_feedback._UP_STEP)


def test_repeated_thumbs_down_suppresses_a_guide(feedback_dir):
    query = "how do I start a measurement"
    best, _ = ai_assistant._match_guide_example(query, KIN, "en")
    gid = best["id"]
    assert ai_assistant._should_launch_guide(query, _match_score(query)) is True
    for _ in range(6):
        ai_feedback.record_feedback('down', source='guide', guide_id=gid, query=query)
    # The heavily down-voted guide should no longer win/fire for that query.
    new_best, new_score = ai_assistant._match_guide_example(query, KIN, "en")
    fired = bool(new_best and ai_assistant._should_launch_guide(query, new_score))
    assert fired is False


def _match_score(query):
    _, score = ai_assistant._match_guide_example(query, KIN, "en")
    return score


def test_positive_weight_does_not_make_unrelated_guide_fire(feedback_dir):
    # Up-voting one guide must not let it hijack a totally unrelated query that
    # produces zero keyword signal for it (the bonus is gated on baseline match).
    ai_feedback.record_feedback('up', source='guide', guide_id='measurement_guide',
                                query='measurement')
    best, _ = ai_assistant._match_guide_example('asdfqwer zzz', KIN, "en")
    assert best is None


def test_disabling_feedback_ignores_learned_weights(feedback_dir):
    query = "how do I start a measurement"
    best, base = ai_assistant._match_guide_example(query, KIN, "en")
    gid = best["id"]
    ai_feedback.record_feedback('up', source='guide', guide_id=gid, query=query)
    _, boosted = ai_assistant._match_guide_example(query, KIN, "en")
    assert boosted > base
    # Opt out → the matcher must ignore the learned weights entirely.
    with open(os.path.join(str(feedback_dir), 'user_settings.json'), 'w', encoding='utf-8') as f:
        json.dump({'ai_feedback_enabled': False}, f)
    assert ai_feedback.is_enabled() is False
    _, off = ai_assistant._match_guide_example(query, KIN, "en")
    assert off == pytest.approx(base)


# ── Stats / clear ────────────────────────────────────────────────────────────

def test_stats_counts(feedback_dir):
    ai_feedback.record_feedback('up', source='guide', guide_id='g1', query='alpha beta')
    ai_feedback.record_feedback('down', source='llm', query='x')
    s = ai_feedback.stats()
    assert s['ratings'] == 2 and s['up'] == 1 and s['down'] == 1
    assert s['guides_tuned'] == 1


def test_clear_removes_both_files(feedback_dir):
    ai_feedback.record_feedback('up', source='guide', guide_id='g', query='persisted word')
    log = os.path.join(str(feedback_dir), 'ai_feedback.jsonl')
    weights = os.path.join(str(feedback_dir), 'ai_guide_weights.json')
    assert os.path.exists(log) and os.path.exists(weights)
    ai_feedback.clear()
    assert not os.path.exists(log) and not os.path.exists(weights)
    assert ai_feedback.learned_bonus('g') == 0.0
    assert ai_feedback.stats()['ratings'] == 0


# ── Route ────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(state, 'script_dir', str(tmp_path))
    ai_feedback.reload()
    from main import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c
    monkeypatch.undo()
    ai_feedback.reload()


def test_feedback_route_records(client, tmp_path):
    rv = client.post('/ai/feedback', json={
        'rating': 'up', 'source': 'guide', 'guide_id': 'measurement_guide',
        'query': 'start a measurement', 'language': 'en',
    })
    assert rv.status_code == 200
    body = rv.get_json()
    assert body['status'] == 'success'
    assert body['weight'] == pytest.approx(ai_feedback._UP_STEP)


def test_feedback_route_rejects_bad_rating(client):
    rv = client.post('/ai/feedback', json={'rating': 'meh'})
    assert rv.status_code == 400


def test_feedback_route_requires_rating(client):
    rv = client.post('/ai/feedback', json={'source': 'llm'})
    assert rv.status_code == 400


def test_feedback_stats_route(client):
    rv = client.get('/ai/feedback/stats')
    assert rv.status_code == 200
    body = rv.get_json()
    assert body['status'] == 'success'
    assert body['enabled'] is True
    assert body['ratings'] == 0


def test_feedback_reset_route(client, tmp_path):
    client.post('/ai/feedback', json={
        'rating': 'up', 'source': 'guide', 'guide_id': 'g', 'query': 'word here'})
    assert os.path.exists(os.path.join(str(tmp_path), 'ai_guide_weights.json'))
    rv = client.post('/ai/feedback/reset')
    assert rv.status_code == 200
    assert not os.path.exists(os.path.join(str(tmp_path), 'ai_guide_weights.json'))


def test_feedback_export_route_returns_zip(client):
    rv = client.get('/ai/feedback/export')
    assert rv.status_code == 200
    assert rv.mimetype == 'application/zip'
    assert rv.data[:2] == b'PK'   # zip magic


def test_feedback_route_respects_opt_out(client, tmp_path):
    with open(os.path.join(str(tmp_path), 'user_settings.json'), 'w', encoding='utf-8') as f:
        json.dump({'ai_feedback_enabled': False}, f)
    rv = client.post('/ai/feedback', json={
        'rating': 'up', 'source': 'guide', 'guide_id': 'g', 'query': 'x'})
    assert rv.status_code == 200
    assert rv.get_json().get('recorded') is False
    # Nothing was written.
    assert not os.path.exists(os.path.join(str(tmp_path), 'ai_guide_weights.json'))
    assert not os.path.exists(os.path.join(str(tmp_path), 'ai_feedback.jsonl'))
