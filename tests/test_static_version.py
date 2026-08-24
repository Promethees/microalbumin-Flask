"""The cache-busting stamp has to follow the assets, not the process.

It used to be the process start time, which was wrong in both directions:
editing a .js while the app ran left the stamp alone, so the browser kept
serving its cached copy and the change did not appear — and a plain reload could
not help, because the URL being revalidated was byte-identical. Meanwhile every
restart moved it, discarding a good cache of ~30 files for an install that
changed nothing.

This is the bug behind "the button does nothing": the panel's markup is
server-rendered and appeared, while the JavaScript that gives it behaviour was
the stale copy from cache, so the inline onclick called a function that did not
exist in the loaded file.
"""

import os
import time

from main import app

STATIC_VERSION = app.jinja_env.globals['STATIC_VERSION']


def _stamp():
    """What the template's `{{ STATIC_VERSION }}` would render."""
    return str(STATIC_VERSION)


def test_the_stamp_is_a_plain_number_in_the_url():
    """Jinja does not call a callable global, so anything but a str/__str__ here
    renders a function repr into all 22 asset URLs."""
    stamp = _stamp()
    assert stamp.isdigit(), f'{stamp!r} is not something to put after ?v='


def test_the_stamp_moves_when_an_asset_changes(tmp_path, monkeypatch):
    asset = tmp_path / 'script'
    asset.mkdir()
    target = asset / 'thing.js'
    target.write_text('// one')
    monkeypatch.setattr(app, 'static_folder', str(tmp_path))

    type(STATIC_VERSION)._TTL, ttl = 0.0, type(STATIC_VERSION)._TTL
    try:
        before = _stamp()
        os.utime(target, (time.time() + 60, time.time() + 60))
        after = _stamp()
    finally:
        type(STATIC_VERSION)._TTL = ttl
    assert after != before, 'a changed asset must change the stamp'


def test_the_stamp_holds_still_when_nothing_changes(tmp_path, monkeypatch):
    """The other half: a restart that changed no file must not throw the cache
    away. Two separate reads, past the memo, with the tree untouched."""
    (tmp_path / 'thing.js').write_text('// one')
    monkeypatch.setattr(app, 'static_folder', str(tmp_path))

    type(STATIC_VERSION)._TTL, ttl = 0.0, type(STATIC_VERSION)._TTL
    try:
        assert _stamp() == _stamp()
    finally:
        type(STATIC_VERSION)._TTL = ttl


def test_an_unwalkable_tree_still_yields_a_stamp(monkeypatch):
    """A frozen bundle with an unexpected layout serves assets with the old
    process-time stamp rather than no stamp at all."""
    monkeypatch.setattr(app, 'static_folder', None)
    type(STATIC_VERSION)._TTL, ttl = 0.0, type(STATIC_VERSION)._TTL
    try:
        assert _stamp().isdigit()
    finally:
        type(STATIC_VERSION)._TTL = ttl
