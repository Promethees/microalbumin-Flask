"""Persisted YouTube play queue for the background-music widget.

Kept **server-side**, in ``music_queue.json`` beside ``user_settings.json``,
rather than in ``localStorage``. Two reasons, both concrete:

* a restart (data-folder move, applied update) deliberately clears per-view
  ``localStorage`` — see Rule.md §2.20 — so a queue kept there would vanish
  exactly when the user least expects it;
* it is *content* the user assembled, not a per-view UI preference, which is
  also why it is not a ``user_settings.py`` key.

Entries hold a YouTube reference and its display name — never media. See
``src/music.py`` for why nothing here may touch the audio itself.
"""

import json
import os

import state

# Enough for a long working playlist, small enough that the file stays trivial
# to read and rewrite in full. Adds past the cap drop the oldest entries.
MAX_ITEMS = 200

_ALLOWED_KEYS = ("kind", "id", "url", "title", "author", "thumbnail")


def _path():
    return os.path.join(state.script_dir, "music_queue.json")


def _clean(item):
    """Keep only known keys, as strings — the file is rendered into the DOM."""
    if not isinstance(item, dict):
        return None
    kind = item.get("kind")
    ref_id = item.get("id")
    if kind not in ("video", "playlist") or not isinstance(ref_id, str) or not ref_id:
        return None
    out = {}
    for key in _ALLOWED_KEYS:
        value = item.get(key)
        out[key] = value if isinstance(value, str) else ""
    out["kind"] = kind
    return out


def load():
    """Return the saved queue. A missing or corrupt file is an empty queue —
    losing a play queue is not worth an error dialog on a settings read."""
    path = _path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            stored = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(stored, list):
        return []
    items = [_clean(entry) for entry in stored]
    return [item for item in items if item][:MAX_ITEMS]


def save(items):
    """Replace the whole queue. The client owns ordering, so a reorder, a
    removal and an add are all the same write — there is no partial-update API
    to keep consistent."""
    if not isinstance(items, list):
        return False
    cleaned = [_clean(entry) for entry in items]
    cleaned = [item for item in cleaned if item][-MAX_ITEMS:]
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


def add(item):
    """Append one resolved item, de-duplicated by ``(kind, id)``.

    Returns the new queue. A re-added item moves to the end rather than
    appearing twice — the queue is a playlist, not a history.
    """
    cleaned = _clean(item)
    if not cleaned:
        return load()
    items = [
        existing for existing in load()
        if not (existing["kind"] == cleaned["kind"] and existing["id"] == cleaned["id"])
    ]
    items.append(cleaned)
    save(items)
    return items[-MAX_ITEMS:]
