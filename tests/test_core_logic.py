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

def test_close_port():
    with patch('subprocess.run') as mock_run:
        # Mock lsof result
        mock_run.return_value = MagicMock(stdout="1234\n5678\n")
        with patch('os.getpid', return_value=1234):
            browser_mgt.close_port(5099)
            # Should kill 5678, skip 1234
            kill_call = [call for call in mock_run.call_args_list if 'kill' in call.args[0]]
            assert len(kill_call) == 1
            assert '5678' in kill_call[0].args[0]
