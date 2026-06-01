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
# script_monitor.check_log_for_missed_read
# ---------------------------------------------------------------------------

def test_check_log_for_missed_read_file_not_found():
    assert script_monitor.check_log_for_missed_read("/nonexistent/log.txt") is False


def test_check_log_for_missed_read_unexpected_without_session(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("Unexpected line: 0x01 0x02")
    assert script_monitor.check_log_for_missed_read(str(log)) is True


def test_check_log_for_missed_read_unexpected_with_session_started(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("New session started\nUnexpected line: 0x01 0x02")
    assert script_monitor.check_log_for_missed_read(str(log)) is False


def test_check_log_for_missed_read_clean_log(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("New session started\nAll data received.")
    assert script_monitor.check_log_for_missed_read(str(log)) is False


def test_check_log_for_missed_read_no_unexpected_no_session(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("Receiving data normally.")
    assert script_monitor.check_log_for_missed_read(str(log)) is False
