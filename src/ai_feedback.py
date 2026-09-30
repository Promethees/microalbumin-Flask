"""User feedback on AI answers + a learned weight layer over the guide matcher.

A 👍/👎 on an assistant answer is appended to an append-only log
(`ai_feedback.jsonl`). When the rated answer was a *locally matched guide*
(`source == "guide"` with a `guide_id`), the rating also nudges a per-guide
coefficient stored in `ai_guide_weights.json`:

    { "<guide_id>": {"weight": <float>, "terms": ["<word>", ...]} }

`ai_assistant._match_guide_example` adds `learned_bonus(guide_id)` to a guide's
score (after the baseline keyword gate) and treats `learned_terms(guide_id)` as
extra keywords, so a 👍 makes similar queries match that guide more confidently
and a 👎 suppresses it. LLM answers (Groq is a third-party model we cannot
retrain) are logged only — no weight change.

Both files live in the writable data root (`state.script_dir`, == project root
in a source run), alongside `user_settings.json`, and are
preserved across in-app updates (see `update_service._PRESERVE`).
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
from datetime import datetime

import state
import user_settings

_LOG_NAME = "ai_feedback.jsonl"
_WEIGHTS_NAME = "ai_guide_weights.json"

# Coefficient tuning. A single 👍 nudges a guide's score by +_UP_STEP; a 👎 by
# -_DOWN_STEP (down-votes bite a little harder). The weight is clamped to
# [_MIN_WEIGHT, _MAX_WEIGHT] so feedback can meaningfully re-rank and gate
# matches without one guide dominating or a vote brigade overflowing. _MIN_WEIGHT
# is negative enough (~5 down-votes) to push even a strong, mode-boosted match
# below the launch threshold. _MAX_TERMS caps reinforced query words per guide.
_UP_STEP = 0.5
_DOWN_STEP = 0.7
_MAX_WEIGHT = 2.0
_MIN_WEIGHT = -3.0
_MAX_TERMS = 12

# Reinforced-vocabulary extraction: the matcher's own tokenizer
# (ai_assistant._content_words — Unicode-aware, multilingual stop-words), plus
# a few extra filler words, so a 👍 doesn't teach a guide to fire on filler and
# French/Vietnamese/CJK words are kept whole ("données", not "donn").
_TERM_STOPWORDS = frozenset({
    "please", "could", "would", "should", "about", "using", "there", "thing",
    "stuff", "where", "which", "these", "those", "their", "every", "again",
})

_lock = threading.Lock()
_weights_cache = None   # lazily loaded dict; None = not yet read


def _path(name: str) -> str:
    return os.path.join(state.script_dir, name)


def file_paths() -> dict:
    """Absolute paths of the two feedback artifacts (for export/preserve)."""
    return {"log": _path(_LOG_NAME), "weights": _path(_WEIGHTS_NAME)}


def is_enabled() -> bool:
    """Whether feedback collection + learning is on (the user opt-out toggle).

    Read once per match in the matcher and once per request in the route — never
    in a per-guide loop. Defaults to True if settings can't be read.
    """
    try:
        return user_settings.load().get("ai_feedback_enabled", True) is not False
    except Exception:
        return True


def reload() -> None:
    """Drop the in-memory weights cache (for tests / after an external edit)."""
    global _weights_cache
    with _lock:
        _weights_cache = None


def stats() -> dict:
    """Summary counts for the settings panel."""
    rows = read_feedback()
    up = sum(1 for r in rows if r.get("rating") == "up")
    with _lock:
        weights = dict(_load_weights_unlocked())
    guides = sum(
        1 for v in weights.values()
        if isinstance(v, dict) and (v.get("weight") or v.get("terms"))
    )
    return {"ratings": len(rows), "up": up, "down": len(rows) - up, "guides_tuned": guides}


def clear(weights: bool = True, log: bool = True) -> None:
    """Delete the feedback artifacts (Reset learning). Best-effort; resets cache."""
    global _weights_cache
    with _lock:
        if weights:
            try:
                os.remove(_path(_WEIGHTS_NAME))
            except OSError:
                pass
            _weights_cache = {}
        if log:
            try:
                os.remove(_path(_LOG_NAME))
            except OSError:
                pass


# ── Weights persistence ──────────────────────────────────────────────────────

def _load_weights_unlocked() -> dict:
    global _weights_cache
    if _weights_cache is not None:
        return _weights_cache
    try:
        with open(_path(_WEIGHTS_NAME), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    _weights_cache = data
    return data


def _save_weights_unlocked(data: dict) -> None:
    global _weights_cache
    _weights_cache = data
    tmp = _path(_WEIGHTS_NAME) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _path(_WEIGHTS_NAME))
    except Exception:
        # Best-effort: persisting feedback must never break the chat.
        pass


# ── Public read API (consumed by the matcher) ────────────────────────────────

def _clamp_weight(value) -> float:
    """A stored weight as a finite float inside [_MIN_WEIGHT, _MAX_WEIGHT].

    The file is user data and may have been hand-edited or written by an older
    build: 1e9, NaN or inf must not decide routing.
    """
    try:
        w = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(w):
        return 0.0
    return max(_MIN_WEIGHT, min(_MAX_WEIGHT, w))


def learned_bonus(guide_id: str) -> float:
    """Learned additive coefficient for a guide (0.0 when unrated), clamped."""
    if not guide_id:
        return 0.0
    with _lock:
        rec = _load_weights_unlocked().get(guide_id)
    if not isinstance(rec, dict):
        return 0.0
    return _clamp_weight(rec.get("weight", 0.0))


def learned_terms(guide_id: str) -> list:
    """Reinforced query words for a guide (empty when unrated)."""
    if not guide_id:
        return []
    with _lock:
        rec = _load_weights_unlocked().get(guide_id)
    if not isinstance(rec, dict):
        return []
    terms = rec.get("terms", [])
    return [t for t in terms if isinstance(t, str)] if isinstance(terms, list) else []


# ── Recording feedback ───────────────────────────────────────────────────────

def _content_terms(text: str) -> list:
    """Content words of a query, in order, via the matcher's own tokenizer.

    Imported lazily: ai_assistant imports this module at load time.
    """
    import ai_assistant
    content = ai_assistant._content_words(text or "")
    seen, out = set(), []
    for w in (text or "").lower().split():
        w = w.strip(ai_assistant._EDGE_PUNCT)
        if w in content and w not in _TERM_STOPWORDS and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _known_guide_ids() -> frozenset:
    """Ids in guide_training.json; feedback for anything else changes nothing."""
    import ai_assistant
    return frozenset(e.get("id") for e in ai_assistant._load_guide_examples("en") if e.get("id"))


def _is_up(rating) -> bool:
    if isinstance(rating, str):
        return rating.strip().lower() in ("up", "1", "+1", "yes", "good", "helpful")
    try:
        return float(rating) > 0
    except (TypeError, ValueError):
        return False


def _append_log_unlocked(entry: dict) -> None:
    try:
        with open(_path(_LOG_NAME), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _adjust_weight_unlocked(guide_id: str, query: str, up: bool) -> float:
    data = _load_weights_unlocked()
    rec = data.get(guide_id) if isinstance(data.get(guide_id), dict) else {}
    weight = _clamp_weight(rec.get("weight", 0.0))
    raw_terms = rec.get("terms", [])
    terms = [t for t in raw_terms if isinstance(t, str)] if isinstance(raw_terms, list) else []
    query_terms = _content_terms(query)

    if up:
        weight = min(_MAX_WEIGHT, weight + _UP_STEP)
        for t in query_terms:
            if t not in terms:
                terms.append(t)
        if len(terms) > _MAX_TERMS:
            terms = terms[-_MAX_TERMS:]
    else:
        # A down-vote lowers the weight AND forgets the vocabulary this query
        # contributed — otherwise a wrongly learned word keeps pulling queries
        # to the guide the user just rejected.
        weight = max(_MIN_WEIGHT, weight - _DOWN_STEP)
        terms = [t for t in terms if t not in query_terms]

    data[guide_id] = {"weight": round(weight, 4), "terms": terms}
    _save_weights_unlocked(data)
    return weight


def record_feedback(rating, *, source: str = "", guide_id: str = "",
                    query: str = "", answer: str = "", language: str = "en",
                    comment: str = ""):
    """Persist one rating; update the weight layer for matched-guide answers.

    `rating` is "up"/"down" (or a signed number). Returns the guide's new weight
    when a guide coefficient changed, else None.
    """
    up = _is_up(rating)
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "rating": "up" if up else "down",
        "source": source or "",
        "guide_id": guide_id or "",
        "query": (query or "")[:500],
        "answer": (answer or "")[:2000],
        "language": language or "en",
        "comment": (comment or "")[:1000],
    }
    with _lock:
        _append_log_unlocked(entry)
        new_weight = None
        if source == "guide" and guide_id and guide_id in _known_guide_ids():
            new_weight = _adjust_weight_unlocked(guide_id, query, up)
    return new_weight


def read_feedback() -> list:
    """All logged feedback entries, oldest first (for review/export)."""
    out = []
    try:
        with open(_path(_LOG_NAME), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except FileNotFoundError:
        pass
    return out
