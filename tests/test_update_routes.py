"""Tests for src/routes/update_routes.py finalize shutdown handling.

The non-obvious behaviour here is the failure path of the deferred shutdown that
finalize triggers: a frozen build hands off to apply_pending_swap_and_exit(),
and if THAT raises (e.g. the swap-coordinator spawn raising because powershell is
unresolvable on a stripped frozen PATH) the failure used to vanish silently — the
app fell through to a normal shutdown and reopened on the old version with no
trace. _delayed_shutdown() now records the exception to update_swap.txt before
falling through, so a stuck update is diagnosable.
"""

import os
from unittest.mock import patch, MagicMock

import routes.update_routes as ur


def test_delayed_shutdown_logs_when_handoff_raises(tmp_path):
    swap_log = os.path.join(str(tmp_path), 'log', 'update_swap.txt')
    with patch.object(ur.update_service, 'apply_pending_swap_and_exit',
                      side_effect=RuntimeError('powershell not found')), \
         patch.object(ur.update_service, '_swap_log_path', return_value=swap_log), \
         patch.object(ur.update_service, '_shutdown_current_process'), \
         patch.object(ur.time, 'sleep'), \
         patch.object(ur.os, 'kill') as kill:
        ur._delayed_shutdown(delay_secs=0)

    # The failure was recorded instead of swallowed...
    assert os.path.isfile(swap_log)
    with open(swap_log, encoding='utf-8') as f:
        body = f.read()
    assert 'apply_pending_swap_and_exit failed' in body
    assert 'RuntimeError' in body
    assert 'powershell not found' in body
    # ...and the normal shutdown still ran (SIGTERM to self).
    kill.assert_called_once()


def test_delayed_shutdown_no_log_when_handoff_returns_false(tmp_path):
    # Source build / nothing staged: apply returns False, the fallback shutdown
    # runs, and nothing is written to the swap log (there was no failure).
    swap_log = os.path.join(str(tmp_path), 'log', 'update_swap.txt')
    with patch.object(ur.update_service, 'apply_pending_swap_and_exit', return_value=False), \
         patch.object(ur.update_service, '_swap_log_path', return_value=swap_log), \
         patch.object(ur.update_service, '_shutdown_current_process'), \
         patch.object(ur.time, 'sleep'), \
         patch.object(ur.os, 'kill') as kill:
        ur._delayed_shutdown(delay_secs=0)

    assert not os.path.exists(swap_log)
    kill.assert_called_once()


def test_log_swap_failure_is_best_effort_and_never_raises():
    # An unwritable log path must not propagate — finalize's shutdown must proceed.
    with patch.object(ur.update_service, '_swap_log_path',
                      side_effect=OSError('no path')):
        ur._log_swap_failure(RuntimeError('boom'))  # must not raise
