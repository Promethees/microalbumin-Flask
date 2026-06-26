import pytest
from unittest.mock import patch, MagicMock
import os
from src import browser_mgt, script_monitor

def test_is_port_open():
    with patch('socket.socket') as mock_sock:
        mock_instance = mock_sock.return_value
        mock_instance.connect_ex.return_value = 0
        assert browser_mgt.is_port_open('localhost', 80) is True
        
        mock_instance.connect_ex.return_value = 1
        assert browser_mgt.is_port_open('localhost', 80) is False

def test_open_browser_main_process():
    with patch.dict(os.environ, {'WERKZEUG_RUN_MAIN': 'true'}):
        with patch('time.sleep'):  # Skip wait
            with patch('src.browser_mgt.is_port_open', return_value=True):
                with patch('webbrowser.open') as mock_open:
                    browser_mgt.open_browser('localhost', 5099)
                    mock_open.assert_called_once_with('http://localhost:5099')

def test_open_browser_reloader():
    with patch.dict(os.environ, {'WERKZEUG_RUN_MAIN': 'false'}):
        with patch('webbrowser.open') as mock_open:
            browser_mgt.open_browser('localhost', 5099)
            mock_open.assert_not_called()

def test_check_log_for_errors(tmp_path):
    log_file = tmp_path / "test.log"
    
    # No error
    log_file.write_text("All systems normal.")
    assert script_monitor.check_log_for_errors(str(log_file)) is None
    
    # Device error
    log_file.write_text("Error: PyBadge not found in system")
    assert script_monitor.check_log_for_errors(str(log_file)) == "device_not_found"
    
    # Endpoint error
    log_file.write_text("Fatal: Failed to find input endpoint. Exiting.")
    assert script_monitor.check_log_for_errors(str(log_file)) == "input_endpoint_error"

def test_close_port_unix():
    with patch('src.browser_mgt.platform.system', return_value='Linux'):
        with patch('subprocess.run') as mock_run:
            # Mock lsof result
            mock_run.return_value = MagicMock(stdout="1234\n5678\n")
            with patch('os.getpid', return_value=1234):
                browser_mgt.close_port(5099)
                # Should kill 5678, skip 1234
                kill_call = [call for call in mock_run.call_args_list if 'kill' in call.args[0]]
                assert len(kill_call) == 1

def test_close_port_windows():
    # netstat output: skip own PID (1234), kill the other listener (5678),
    # ignore non-LISTENING rows and rows for a different port.
    netstat_out = (
        "  Proto  Local Address          Foreign Address        State           PID\n"
        "  TCP    127.0.0.1:5099         0.0.0.0:0              LISTENING       1234\n"
        "  TCP    0.0.0.0:5099           0.0.0.0:0              LISTENING       5678\n"
        "  TCP    127.0.0.1:5099         127.0.0.1:55000        ESTABLISHED     9999\n"
        "  TCP    0.0.0.0:8080           0.0.0.0:0              LISTENING       4321\n"
    )
    with patch('src.browser_mgt.platform.system', return_value='Windows'):
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout=netstat_out)
            with patch('os.getpid', return_value=1234):
                browser_mgt.close_port(5099)
                kill_calls = [c for c in mock_run.call_args_list if 'taskkill' in c.args[0]]
                killed_pids = {c.args[0][-1] for c in kill_calls}
                assert killed_pids == {'5678'}


def test_windows_relaunch_script_quotes_args_with_spaces():
    # Regression: app installs to "C:\Program Files\EasyOKAPI" (path has a
    # space). Start-Process -ArgumentList does not quote elements containing
    # spaces, so the main.py path must be passed embedded in double quotes or
    # Python gets a split argv ("C:\Program") and the relaunch silently dies.
    import update_service
    exe = r"C:\Program Files\EasyOKAPI\code\venv\Scripts\python.exe"
    main = r"C:\Program Files\EasyOKAPI\code\main.py"
    script = update_service._build_windows_relaunch_script(
        [exe, main], r"C:\Program Files\EasyOKAPI", 5099)
    # The main.py argument must appear double-quoted inside the ArgumentList.
    assert '@(\'"' + main + '"\')' in script
    # And it must not appear bare (unquoted) in the ArgumentList.
    assert "@('" + main + "')" not in script


def test_install_requirements_raises_on_pip_failure():
    # Regression: the in-app update never rebuilds the venv, so after applying an
    # update that adds a new dependency, download_and_apply must run pip and fail
    # loudly (so the app is not relaunched into an ImportError) instead of going
    # ahead silently.
    import update_service
    with patch.object(update_service, '_requirements_path', return_value=__file__), \
         patch('subprocess.run', return_value=MagicMock(returncode=1, stdout='boom')):
        with pytest.raises(RuntimeError):
            update_service._install_requirements()


def test_install_requirements_ok_when_pip_succeeds():
    import update_service
    with patch.object(update_service, '_requirements_path', return_value=__file__), \
         patch('subprocess.run', return_value=MagicMock(returncode=0, stdout='ok')) as run:
        update_service._install_requirements()  # must not raise
        assert run.called


def test_install_requirements_skips_when_no_requirements_file():
    import update_service
    missing = os.path.join(os.path.dirname(__file__), 'no_such_requirements.txt')
    with patch.object(update_service, '_requirements_path', return_value=missing), \
         patch('subprocess.run') as run:
        update_service._install_requirements()
        run.assert_not_called()


def test_windows_relaunch_script_uses_portable_port_probe():
    # Regression: the relaunch must probe the port with a .NET TcpClient connect,
    # not Get-NetTCPConnection. That cmdlet is missing on some Windows builds,
    # and the old fallback (a fixed "Start-Sleep -Seconds 3") re-introduced the
    # port race that bricked the relaunch (new instance binds before the dying
    # one frees the port → app.run → sys.exit(1), hidden, dies silently).
    import update_service
    script = update_service._build_windows_relaunch_script(
        [r"C:\py.exe", r"C:\main.py"], r"C:\app", 5099)
    assert "Get-NetTCPConnection" not in script
    assert "Start-Sleep -Seconds 3" not in script
    # Must use a connect probe to the loopback port.
    assert "System.Net.Sockets.TcpClient" in script
    assert "Connect('127.0.0.1', $p)" in script


# ---------------------------------------------------------------------------
# script_monitor.check_log_for_session_start
# ---------------------------------------------------------------------------

def test_check_log_for_session_start_file_not_found():
    assert script_monitor.check_log_for_session_start("/nonexistent/log.txt") is False


def test_check_log_for_session_start_true_when_session_logged(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("Connected to PyBadge\nNew session started. Header written to out.csv")
    assert script_monitor.check_log_for_session_start(str(log)) is True


def test_check_log_for_session_start_false_without_session(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("PyBadge not found. Device (Pybadge) not found.")
    assert script_monitor.check_log_for_session_start(str(log)) is False


# ---------------------------------------------------------------------------
# script_monitor.check_log_for_end_reason — timeout vs device-button stop
# ---------------------------------------------------------------------------

def test_check_log_for_end_reason_missing_file():
    assert script_monitor.check_log_for_end_reason("/nonexistent/log.txt") is None


def test_check_log_for_end_reason_stopped(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("New session started.\n[t] SESSION STOPPED\n")
    assert script_monitor.check_log_for_end_reason(str(log)) == "stopped"


def test_check_log_for_end_reason_timeout(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("New session started.\n[t] SESSION TIMEOUT\n")
    assert script_monitor.check_log_for_end_reason(str(log)) == "timeout"


def test_check_log_for_end_reason_none_when_no_sentinel(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("New session started.\nReceived: Timestamp: 0.00s, Values: 0.1\n")
    assert script_monitor.check_log_for_end_reason(str(log)) is None
