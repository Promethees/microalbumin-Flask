"""Tests for the default-display reset flag set across a restart.

A restart (data-folder relocation or applied update) writes a one-shot sentinel
(state.mark_reset_display_pending). The next index render consumes it
(state.consume_reset_display_pending) and tells the client to come up in the
default display (kinetics mode, fresh per-view UI state).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import state


def _cleanup():
    try:
        os.remove(state._RESET_DISPLAY_MARKER)
    except OSError:
        pass


def test_consume_is_false_when_not_marked():
    _cleanup()
    assert state.consume_reset_display_pending() is False


def test_mark_then_consume_is_true_once():
    _cleanup()
    state.mark_reset_display_pending()
    # First consume after a restart sees the flag…
    assert state.consume_reset_display_pending() is True
    # …and it is one-shot — a later refresh keeps the user's layout.
    assert state.consume_reset_display_pending() is False


def test_index_consumes_flag_and_injects_reset(client):
    _cleanup()
    state.mark_reset_display_pending()

    first = client.get('/')
    assert first.status_code == 200
    assert b'const RESET_DISPLAY = true;' in first.data

    # The flag is one-shot: a plain refresh must NOT reset the display again.
    second = client.get('/')
    assert b'const RESET_DISPLAY = false;' in second.data
    _cleanup()


def test_relaunch_suppresses_browser():
    """A restart relaunch must pass --no-browser.

    The flag above is one-shot. The user's tab reloads itself (restarting.html)
    and is meant to consume it. If the relaunched instance auto-opened a second
    tab, that tab would race the reload for the marker — and whichever lost would
    come up with reset_display=false, missing the default-display reset (kinetics
    mode + selected button). Suppressing the second tab keeps the marker for the
    one tab the user is looking at.
    """
    import update_service

    saved = sys.argv
    try:
        sys.argv = ['main.py', '--port', '5099']
        argv = update_service._relaunch_argv()
        assert '--no-browser' in argv
        # Idempotent: a relaunch of an already-suppressed instance adds no duplicate.
        sys.argv = ['main.py', '--port', '5099', '--no-browser']
        assert update_service._relaunch_argv().count('--no-browser') == 1
    finally:
        sys.argv = saved
