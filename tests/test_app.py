import pytest
from unittest.mock import patch, MagicMock
import os
import json
from main import app
import state

@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Reset state.process before each test
    state.process = None
    with app.test_client() as client:
        yield client

# Core Routes Tests
def test_index_page(client):
    """Test that the index page loads."""
    with patch('routes.core_routes.get_directory', return_value='/tmp'):
        with patch('routes.core_routes.get_file_list', return_value=[]):
            rv = client.get('/')
            assert rv.status_code == 200
            assert b'Easy OKAPI' in rv.data

def test_ping(client):
    """Test the ping endpoint."""
    rv = client.get('/ping')
    assert rv.status_code == 200
    assert rv.get_json() == {'status': 'success'}

def test_get_parents(client):
    """Test the get_parents endpoint."""
    with patch('routes.core_routes.get_directory', return_value='/tmp/test'):
        with patch('routes.core_routes.get_parent_directory', return_value='/tmp'):
            rv = client.get('/get_parents')
            assert rv.status_code == 200
            assert rv.get_json() == {'parent': '/tmp'}

# Hardware Routes Tests
def test_run_script_already_running(client):
    """Test run_script when a process is already running."""
    state.process = MagicMock()
    state.process.poll.return_value = None
    rv = client.post('/run_script', json={})
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'failure'
    assert 'already running' in rv.get_json()['message']

def test_run_script_success(client):
    """Test successful run_script start."""
    with patch('routes.hardware_routes.connect_to_device') as mock_conn:
        with patch('routes.hardware_routes.send_command_and_wait_ack', return_value=(True, '')):
            with patch('subprocess.Popen') as mock_popen:
                mock_popen.return_value = MagicMock()
                rv = client.post('/run_script', json={
                    'base_dir': 'data',
                    'base_name': 'test',
                    'timeout_sec': 10,
                    'interval_sec': 1
                })
                assert rv.status_code == 200
                assert rv.get_json()['status'] == 'success'

def test_check_status_not_running(client):
    """Test check_status when no script is running."""
    rv = client.get('/check_status')
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'not_running'

# File Routes Tests
def test_get_json_content(client, tmp_path):
    """Test fetching JSON file content."""
    test_json = tmp_path / "test.json"
    test_json.write_text(json.dumps({'key': 'value'}))
    
    with patch('state.json_root_path', str(tmp_path)):
        # Join logic in file_routes: os.path.join(os.path.join(state.json_root_path, mode), selected_json)
        # So we need a subfolder for mode
        mode_dir = tmp_path / "kinetics"
        mode_dir.mkdir()
        test_json = mode_dir / "test.json"
        test_json.write_text(json.dumps({'key': 'value'}))
        
        rv = client.get('/get_json_content?json_name=test.json&mode=kinetics')
        assert rv.status_code == 200
        assert rv.get_json()['json'] == {'key': 'value'}

def test_get_headers(client, tmp_path):
    """Test fetching CSV headers."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("Col1,Col2\n1,2")
    
    rv = client.get(f'/get_headers?file={str(csv_file)}')
    assert rv.status_code == 200
    assert rv.get_json()['headers'] == ['Col1', 'Col2']

def test_delete_file(client, tmp_path):
    """Test deleting a file."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("data")
    
    rv = client.post('/delete_file', data={
        'filename': 'test.csv',
        'tabletype': '#csv-table',
        'path': str(tmp_path)
    })
    assert rv.status_code == 200
    assert not csv_file.exists()

def test_copy_file(client, tmp_path):
    """Test copying a file."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("data")
    
    with patch('routes.file_routes.get_next_filename', return_value=str(tmp_path / "test_1.csv")):
        rv = client.post('/copy_file', data={
            'filename': 'test.csv',
            'tabletype': '#csv-table',
            'path': str(tmp_path)
        })
        assert rv.status_code == 200
        assert (tmp_path / "test_1.csv").exists()
