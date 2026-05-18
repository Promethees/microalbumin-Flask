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
    with patch('routes.core_routes.get_file_list', return_value=[]):
        rv = client.get('/')
        assert rv.status_code == 200
        assert b'Easy OKAPI' in rv.data

def test_ping(client):
    """Test the ping endpoint."""
    rv = client.get('/ping')
    assert rv.status_code == 200
    assert rv.get_json() == {'status': 'success'}

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


# ---------------------------------------------------------------------------
# edit_file Route Tests
# ---------------------------------------------------------------------------

_KINETICS_CAL = (
    "# Measurement: ABS\n"
    "# MeasUnit: AU\n"
    "# TimeUnit: minutes\n"
    "# MeasMode: kinetics\n"
    "Concentration,maxRate,Slope,Sat,Time To Sat\n"
    "1,0.5,0.1,1.0,20\n"
)

_POINT_CAL = (
    "# Measurement: ABS\n"
    "# MeasUnit: AU\n"
    "# TimeUnit: minute\n"
    "# MeasMode: point\n"
    "Concentration,Value,TimePoint\n"
    "1,0.5,2.0\n"
)

_TIMESERIES = (
    "# Measurement: ABS\n"
    "# Unit: AU\n"
    "# Concentration: 10\n"
    "Timestamp,Value:1\n"
    "0,0.5\n"
    "1,0.6\n"
)


def test_edit_file_missing_filename(client):
    rv = client.post('/edit_file', data={'content': _KINETICS_CAL})
    assert rv.status_code == 400
    assert rv.get_json()['status'] == 'error'


def test_edit_file_missing_content(client, tmp_path):
    f = tmp_path / "test.csv"
    f.write_text(_KINETICS_CAL)
    rv = client.post('/edit_file', data={'filename': 'test.csv', 'path': str(tmp_path)})
    assert rv.status_code == 400
    assert rv.get_json()['status'] == 'error'


def test_edit_file_invalid_extension(client, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("data")
    rv = client.post('/edit_file', data={
        'filename': 'test.txt',
        'new_filename': 'test.txt',
        'path': str(tmp_path),
        'content': 'data',
    })
    assert rv.status_code == 400
    assert 'must end with' in rv.get_json()['message']


def test_edit_file_path_traversal_rejected(client):
    # Relative 'path' causes normpath to retain '..' — the guard fires before the
    # existence check, so no real file is needed.
    rv = client.post('/edit_file', data={
        'filename': '../../etc/passwd.csv',
        'path': 'data',
        'content': _KINETICS_CAL,
    })
    assert rv.status_code == 400
    assert rv.get_json()['status'] == 'error'


def test_edit_file_file_not_found(client, tmp_path):
    rv = client.post('/edit_file', data={
        'filename': 'nonexistent.csv',
        'path': str(tmp_path),
        'content': _KINETICS_CAL,
    })
    assert rv.status_code == 404
    assert rv.get_json()['status'] == 'error'


def test_edit_file_process_running_returns_locked(client):
    state.process = MagicMock()
    state.process.poll.return_value = None
    rv = client.post('/edit_file', data={
        'filename': 'test.csv',
        'content': _KINETICS_CAL,
    })
    assert rv.status_code == 423


def test_edit_file_rename_conflict(client, tmp_path):
    (tmp_path / "original.csv").write_text(_KINETICS_CAL)
    (tmp_path / "existing.csv").write_text(_KINETICS_CAL)
    rv = client.post('/edit_file', data={
        'filename': 'original.csv',
        'new_filename': 'existing.csv',
        'path': str(tmp_path),
        'content': _KINETICS_CAL,
    })
    assert rv.status_code == 409
    assert rv.get_json()['status'] == 'error'


def test_edit_file_invalid_json_content(client, tmp_path):
    f = tmp_path / "cal.json"
    f.write_text('{"key": "value"}')
    rv = client.post('/edit_file', data={
        'filename': 'cal.json',
        'path': str(tmp_path),
        'content': '{not valid json}',
    })
    assert rv.status_code == 400
    assert 'Invalid JSON' in rv.get_json()['message']


def test_edit_file_json_success(client, tmp_path):
    f = tmp_path / "cal.json"
    f.write_text('{"key": "old"}')
    rv = client.post('/edit_file', data={
        'filename': 'cal.json',
        'path': str(tmp_path),
        'content': '{"key": "updated"}',
    })
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    assert json.loads(f.read_text())['key'] == 'updated'


def test_edit_file_csv_no_data_lines(client, tmp_path):
    f = tmp_path / "test.csv"
    f.write_text(_KINETICS_CAL)
    rv = client.post('/edit_file', data={
        'filename': 'test.csv',
        'path': str(tmp_path),
        'content': '# Measurement: ABS\n# MeasUnit: AU\n',
    })
    assert rv.status_code == 400
    assert 'header row' in rv.get_json()['message']


def test_edit_file_csv_unknown_schema(client, tmp_path):
    f = tmp_path / "test.csv"
    f.write_text(_KINETICS_CAL)
    rv = client.post('/edit_file', data={
        'filename': 'test.csv',
        'path': str(tmp_path),
        'content': '# Measurement: ABS\nUnknownCol1,UnknownCol2\n1,2\n',
    })
    assert rv.status_code == 400
    assert 'Invalid CSV header' in rv.get_json()['message']


def test_edit_file_csv_missing_metadata_fields(client, tmp_path):
    f = tmp_path / "test.csv"
    f.write_text(_KINETICS_CAL)
    # kinetics_cal header present but MeasUnit/TimeUnit/MeasMode metadata absent
    content = (
        "# Measurement: ABS\n"
        "Concentration,maxRate,Slope,Sat,Time To Sat\n"
        "1,0.5,0.1,1.0,20\n"
    )
    rv = client.post('/edit_file', data={
        'filename': 'test.csv',
        'path': str(tmp_path),
        'content': content,
    })
    assert rv.status_code == 400
    assert 'Missing metadata' in rv.get_json()['message']


def test_edit_file_csv_invalid_data_row(client, tmp_path):
    f = tmp_path / "test.csv"
    f.write_text(_KINETICS_CAL)
    content = (
        "# Measurement: ABS\n# MeasUnit: AU\n# TimeUnit: minutes\n# MeasMode: kinetics\n"
        "Concentration,maxRate,Slope,Sat,Time To Sat\n"
        "not_a_number,bad,data,row,here\n"
    )
    rv = client.post('/edit_file', data={
        'filename': 'test.csv',
        'path': str(tmp_path),
        'content': content,
    })
    assert rv.status_code == 400
    assert 'Invalid data in row' in rv.get_json()['message']


def test_edit_file_csv_kinetics_cal_success(client, tmp_path):
    f = tmp_path / "test.csv"
    f.write_text(_KINETICS_CAL)
    new_content = (
        "# Measurement: ABS\n# MeasUnit: AU\n# TimeUnit: minutes\n# MeasMode: kinetics\n"
        "Concentration,maxRate,Slope,Sat,Time To Sat\n"
        "2,0.8,0.2,2.0,30\n"
    )
    rv = client.post('/edit_file', data={
        'filename': 'test.csv',
        'path': str(tmp_path),
        'content': new_content,
    })
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    assert '2,0.8,0.2,2.0,30' in f.read_text()


def test_edit_file_csv_point_cal_success(client, tmp_path):
    f = tmp_path / "test.csv"
    f.write_text(_POINT_CAL)
    rv = client.post('/edit_file', data={
        'filename': 'test.csv',
        'path': str(tmp_path),
        'content': _POINT_CAL,
    })
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'


def test_edit_file_csv_timeseries_success(client, tmp_path):
    f = tmp_path / "test.csv"
    f.write_text(_TIMESERIES)
    rv = client.post('/edit_file', data={
        'filename': 'test.csv',
        'path': str(tmp_path),
        'content': _TIMESERIES,
    })
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'


def test_edit_file_csv_calibrate_mode_sorts_rows(client, tmp_path):
    f = tmp_path / "test.csv"
    # Write rows out of order — calibrate_mode should sort by concentration ascending.
    content = (
        "# Measurement: ABS\n# MeasUnit: AU\n# TimeUnit: minutes\n# MeasMode: kinetics\n"
        "Concentration,maxRate,Slope,Sat,Time To Sat\n"
        "5,0.8,0.2,2.0,30\n"
        "1,0.5,0.1,1.0,20\n"
    )
    f.write_text(content)
    rv = client.post('/edit_file', data={
        'filename': 'test.csv',
        'path': str(tmp_path),
        'content': content,
        'calibrate_mode': 'kinetics',
    })
    assert rv.status_code == 200
    lines = [l for l in f.read_text().splitlines() if l and not l.startswith('#')]
    assert lines[1].startswith('1')  # concentration 1 sorted before 5
    assert lines[2].startswith('5')


def test_edit_file_rename_success(client, tmp_path):
    f_orig = tmp_path / "original.csv"
    f_orig.write_text(_KINETICS_CAL)
    rv = client.post('/edit_file', data={
        'filename': 'original.csv',
        'new_filename': 'renamed.csv',
        'path': str(tmp_path),
        'content': _KINETICS_CAL,
    })
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    assert not f_orig.exists()
    assert (tmp_path / 'renamed.csv').exists()
