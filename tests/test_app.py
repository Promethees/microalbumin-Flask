import pytest
from unittest.mock import patch, MagicMock
import os
import json
import subprocess
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

def test_run_script_success(client, tmp_path):
    """A CDC logger subprocess that stays alive (wait() times out) => success.

    The CDC logger owns the serial port: it does the connect + command
    handshake itself, so run_script only launches it and treats a still-running
    process as a successfully started session.

    state.script_dir / state.log_file are redirected under tmp_path so the test
    never touches the real (possibly unwritable) log dir — run_script opens
    state.log_file for the subprocess's stdout and would otherwise fail there.
    """
    (tmp_path / 'log').mkdir()
    with patch.object(state, 'script_dir', str(tmp_path)), \
         patch.object(state, 'log_file', str(tmp_path / 'log' / 'script_logs.txt')), \
         patch('subprocess.Popen') as mock_popen:
        proc = MagicMock()
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd='log_cdc_data.py', timeout=2)
        mock_popen.return_value = proc
        rv = client.post('/run_script', json={
            'base_name': 'test',
            'timeout_sec': 10,
            'interval_sec': 1
        })
        assert rv.status_code == 200
        assert rv.get_json()['status'] == 'success'

def test_run_script_clears_stale_current_output_marker(client, tmp_path):
    """run_script must blank log/current_output.txt before the logger starts.

    Otherwise "View live data" (enabled the instant run_script succeeds) would
    resolve /api/current_output to the *previous* session's CSV during the window
    before the new session writes its header. After a successful start the marker
    must be empty, so api_current_output returns 204 and the client keeps polling.
    """
    log_dir = tmp_path / 'log'
    log_dir.mkdir()
    marker = log_dir / 'current_output.txt'
    # Simulate a leftover marker from a prior session.
    marker.write_text('/old/data/26Jun2026/previous_session_0.csv', encoding='utf-8')

    with patch.object(state, 'script_dir', str(tmp_path)), \
         patch.object(state, 'log_file', str(log_dir / 'script_logs.txt')), \
         patch('subprocess.Popen') as mock_popen:
        proc = MagicMock()
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd='log_cdc_data.py', timeout=2)
        mock_popen.return_value = proc
        rv = client.post('/run_script', json={'base_name': 'test'})

        assert rv.status_code == 200
        assert rv.get_json()['status'] == 'success'
        # Marker is blanked: the stale path is gone, so the endpoint reports 204.
        assert marker.read_text(encoding='utf-8') == ''
        rv2 = client.get('/api/current_output')
        assert rv2.status_code == 204


def test_run_script_device_not_found(client, tmp_path):
    """A logger that exits immediately and logged a missing device => device_not_found.

    state.script_dir / state.log_file are redirected under tmp_path so run_script
    can open state.log_file (the subprocess stdout sink) without touching the real
    log dir.
    """
    (tmp_path / 'log').mkdir()
    with patch.object(state, 'script_dir', str(tmp_path)), \
         patch.object(state, 'log_file', str(tmp_path / 'log' / 'script_logs.txt')), \
         patch('subprocess.Popen') as mock_popen, \
         patch('routes.hardware_routes.check_log_for_errors', return_value='device_not_found'):
        proc = MagicMock()
        proc.wait.return_value = 1  # exits quickly (no TimeoutExpired)
        mock_popen.return_value = proc
        rv = client.post('/run_script', json={'base_name': 'test'})
        assert rv.status_code == 200
        assert rv.get_json()['status'] == 'device_not_found'


def test_run_script_rejects_reserved_subfolder(client):
    """The archive staging name 'root' is reserved and must be refused."""
    rv = client.post('/run_script', json={'subfolder': 'root'})
    assert rv.status_code == 400
    assert rv.get_json()['status'] == 'failure'
    assert 'reserved' in rv.get_json()['message'].lower()


def test_run_script_rejects_reserved_subfolder_case_insensitive(client):
    """Reserved-name check is case-insensitive ('ROOT' is also refused)."""
    rv = client.post('/run_script', json={'subfolder': 'ROOT'})
    assert rv.status_code == 400
    assert rv.get_json()['status'] == 'failure'


def test_check_status_not_running(client):
    """Test check_status when no script is running."""
    rv = client.get('/check_status')
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'not_running'


def test_check_status_completed(client):
    """A finished logger process that established a session => success (completed)."""
    state.process = MagicMock()
    state.process.poll.return_value = 0  # process has exited
    with patch('routes.hardware_routes.check_log_for_errors', return_value=None), \
         patch('routes.hardware_routes.check_log_for_session_start', return_value=True):
        rv = client.get('/check_status')
        assert rv.status_code == 200
        assert rv.get_json()['status'] == 'success'
        assert state.process is None

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
# file_routes — /move_file
# ---------------------------------------------------------------------------

def test_move_file_success(client, tmp_path):
    src = tmp_path / "src"; src.mkdir()
    dst = tmp_path / "dst"; dst.mkdir()
    (src / "m.csv").write_text("data")
    with patch('file_path.DATA_ROOT', str(tmp_path)):
        rv = client.post('/move_file', data={
            'filename': 'm.csv', 'path': str(src), 'dest_path': str(dst)
        })
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    assert not (src / "m.csv").exists()
    assert (dst / "m.csv").exists()


def test_move_file_autorenames_on_conflict(client, tmp_path):
    src = tmp_path / "src"; src.mkdir()
    dst = tmp_path / "dst"; dst.mkdir()
    (src / "m.csv").write_text("new")
    (dst / "m.csv").write_text("existing")
    with patch('file_path.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.get_next_filename', return_value=str(dst / "m_1.csv")):
        rv = client.post('/move_file', data={
            'filename': 'm.csv', 'path': str(src), 'dest_path': str(dst)
        })
    assert rv.status_code == 200
    assert (dst / "m.csv").read_text() == "existing"   # original not clobbered
    assert (dst / "m_1.csv").read_text() == "new"
    assert not (src / "m.csv").exists()


def test_move_file_same_folder_rejected(client, tmp_path):
    src = tmp_path / "src"; src.mkdir()
    (src / "m.csv").write_text("data")
    with patch('file_path.DATA_ROOT', str(tmp_path)):
        rv = client.post('/move_file', data={
            'filename': 'm.csv', 'path': str(src), 'dest_path': str(src)
        })
    assert rv.status_code == 400
    assert 'same' in rv.get_json()['message'].lower()
    assert (src / "m.csv").exists()


def test_move_file_process_running_returns_locked(client):
    state.process = MagicMock()
    state.process.poll.return_value = None
    rv = client.post('/move_file', data={'filename': 'm.csv', 'path': '/data/a', 'dest_path': '/data/b'})
    assert rv.status_code == 423


def test_move_file_missing_source(client, tmp_path):
    src = tmp_path / "src"; src.mkdir()
    dst = tmp_path / "dst"; dst.mkdir()
    with patch('file_path.DATA_ROOT', str(tmp_path)):
        rv = client.post('/move_file', data={
            'filename': 'ghost.csv', 'path': str(src), 'dest_path': str(dst)
        })
    assert rv.status_code == 404


def test_move_file_rejects_traversal_filename(client, tmp_path):
    with patch('file_path.DATA_ROOT', str(tmp_path)):
        rv = client.post('/move_file', data={
            'filename': '../evil.csv', 'path': str(tmp_path), 'dest_path': str(tmp_path / "dst")
        })
    assert rv.status_code == 400
    assert 'filename' in rv.get_json()['message'].lower()


def test_move_file_dest_outside_data_root(client, tmp_path, tmp_path_factory):
    src = tmp_path / "src"; src.mkdir()
    (src / "m.csv").write_text("data")
    outside = str(tmp_path_factory.mktemp("outside"))
    with patch('file_path.DATA_ROOT', str(tmp_path)):
        rv = client.post('/move_file', data={
            'filename': 'm.csv', 'path': str(src), 'dest_path': outside
        })
    assert rv.status_code == 400
    assert 'invalid folder' in rv.get_json()['message'].lower()
    assert (src / "m.csv").exists()


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


# ---------------------------------------------------------------------------
# core_routes — untested endpoints
# ---------------------------------------------------------------------------

def test_clear_logs_success(client, tmp_path):
    log = tmp_path / "test.log"
    log.write_text("old content")
    with patch.object(state, 'log_file', str(log)):
        rv = client.post('/clear_logs')
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    assert log.read_text() == ""


def test_download_event_logs_bundles_jsonl(client, tmp_path):
    import io
    import zipfile
    events_root = tmp_path / "log" / "events" / "2026-06-03"
    events_root.mkdir(parents=True)
    (events_root / "10-00-00.jsonl").write_text('{"ts":"x","type":"session","action":"start"}\n')
    with patch.object(state, 'script_dir', str(tmp_path)):
        rv = client.get('/download_event_logs')
    assert rv.status_code == 200
    assert rv.mimetype == 'application/zip'
    assert 'easyokapi-logs-' in rv.headers.get('Content-Disposition', '')
    z = zipfile.ZipFile(io.BytesIO(rv.data))
    assert z.testzip() is None
    assert any(n.endswith('10-00-00.jsonl') for n in z.namelist())


def test_download_event_logs_empty_still_returns_zip(client, tmp_path):
    import io
    import zipfile
    # No log/events directory at all — must still return a valid zip with a note.
    with patch.object(state, 'script_dir', str(tmp_path)):
        rv = client.get('/download_event_logs')
    assert rv.status_code == 200
    assert rv.mimetype == 'application/zip'
    z = zipfile.ZipFile(io.BytesIO(rv.data))
    assert z.testzip() is None
    assert 'events/README.txt' in z.namelist()


def test_list_event_log_files_newest_first(client, tmp_path):
    events_root = tmp_path / "log" / "events" / "2026-06-03"
    events_root.mkdir(parents=True)
    (events_root / "10-00-00.jsonl").write_text('{"a":1}\n')
    (events_root / "11-00-00.jsonl").write_text('{"a":2}\n')
    import os as _os
    # Make 11-00-00 the more recently modified file.
    _os.utime(str(events_root / "10-00-00.jsonl"), (1000, 1000))
    _os.utime(str(events_root / "11-00-00.jsonl"), (2000, 2000))
    with patch.object(state, 'script_dir', str(tmp_path)):
        rv = client.get('/list_event_log_files')
    assert rv.status_code == 200
    files = rv.get_json()['files']
    assert [f['path'] for f in files] == ['2026-06-03/11-00-00.jsonl', '2026-06-03/10-00-00.jsonl']
    assert all('size' in f for f in files)


def test_download_event_logs_post_selection(client, tmp_path):
    import io
    import zipfile
    events_root = tmp_path / "log" / "events" / "2026-06-03"
    events_root.mkdir(parents=True)
    (events_root / "10-00-00.jsonl").write_text('{"a":1}\n')
    (events_root / "11-00-00.jsonl").write_text('{"a":2}\n')
    with patch.object(state, 'script_dir', str(tmp_path)):
        rv = client.post('/download_event_logs', json={'files': ['2026-06-03/10-00-00.jsonl']})
    assert rv.status_code == 200
    assert rv.mimetype == 'application/zip'
    z = zipfile.ZipFile(io.BytesIO(rv.data))
    assert z.namelist() == ['events/2026-06-03/10-00-00.jsonl']


def test_download_event_logs_post_rejects_traversal(client, tmp_path):
    with patch.object(state, 'script_dir', str(tmp_path)):
        rv = client.post('/download_event_logs', json={'files': ['../../../etc/passwd']})
    assert rv.status_code == 400


def test_download_event_logs_post_rejects_too_many(client, tmp_path):
    with patch.object(state, 'script_dir', str(tmp_path)):
        rv = client.post('/download_event_logs', json={'files': ['a.jsonl'] * 6})
    assert rv.status_code == 400


def test_download_event_logs_post_rejects_empty(client, tmp_path):
    with patch.object(state, 'script_dir', str(tmp_path)):
        rv = client.post('/download_event_logs', json={'files': []})
    assert rv.status_code == 400


def test_clear_cache_sets_no_cache_headers(client):
    rv = client.post('/clear_cache')
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    assert 'no-store' in rv.headers.get('Cache-Control', '')


def test_get_data_folders_returns_success(client):
    with patch('routes.core_routes.get_data_subfolders', return_value=[]):
        rv = client.get('/get_data_folders')
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    assert rv.get_json()['folders'] == []


def test_browse_export_no_path_param(client):
    rv = client.get('/browse_export')
    assert rv.status_code == 400


def test_browse_export_existing_path(client, tmp_path):
    rv = client.get(f'/browse_export?path={str(tmp_path)}')
    assert rv.status_code == 200
    assert rv.get_json()['exists'] is True


def test_browse_export_nonexistent_path(client):
    rv = client.get('/browse_export?path=/nonexistent/xyz_abc_123')
    assert rv.status_code == 200
    assert rv.get_json()['exists'] is False


def test_get_json_cal_invalid_mode_returns_empty(client):
    rv = client.get('/get_json_cal?mode=invalid')
    assert rv.status_code == 200
    assert rv.get_json()['files'] == []


def test_get_json_cal_kinetics_mode(client, tmp_path):
    with patch.object(state, 'json_root_path', str(tmp_path)):
        rv = client.get('/get_json_cal?mode=kinetics')
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'


def test_browse_no_path_returns_400(client):
    rv = client.post('/browse', data={})
    assert rv.status_code == 400


def test_browse_path_outside_roots_returns_error(client):
    with patch.object(state, 'data_root_path', '/fake/data'), \
         patch.object(state, 'report_root_path', '/fake/report'):
        rv = client.post('/browse', data={'path': '/etc'})
    assert rv.get_json()['status'] == 'error'
    assert 'Invalid' in rv.get_json()['message']


# ---------------------------------------------------------------------------
# file_routes — get_headers error paths
# ---------------------------------------------------------------------------

def test_get_headers_no_file_param(client):
    rv = client.get('/get_headers')
    assert rv.status_code == 400


def test_get_headers_non_csv_extension(client, tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("col1\tval")
    rv = client.get(f'/get_headers?file={str(f)}')
    assert rv.status_code == 400
    assert 'CSV' in rv.get_json()['error']


def test_get_headers_file_not_found(client):
    rv = client.get('/get_headers?file=/nonexistent/path.csv')
    assert rv.status_code == 404


def test_get_headers_path_traversal_rejected(client):
    rv = client.get('/get_headers?file=../../etc/passwd.csv')
    assert rv.status_code == 400


# ---------------------------------------------------------------------------
# file_routes — export_to_report (data file -> report subject)
# ---------------------------------------------------------------------------

def test_export_to_report_copies_data_file(client, tmp_path):
    """A measurement file under data/ exports into report/<subject>/.

    Regression: the source must be confined to the DATA root (where
    measurements live), not the report root. Anchoring on report_root made
    every data-file export fail with 403 — and the failure surfaced after a
    user relocated the data folder.
    """
    data_root = tmp_path / "data"
    report_root = tmp_path / "report"
    (data_root / "kinetics").mkdir(parents=True)
    report_root.mkdir()
    src = data_root / "kinetics" / "sample.csv"
    src.write_text("time,abs\n0,0.1\n")

    with patch('routes.file_routes.DATA_ROOT', str(data_root)), \
         patch('file_path.DATA_ROOT', str(data_root)), \
         patch.object(state, 'report_root_path', str(report_root)):
        rv = client.post('/export_to_report', json={
            'subject': 'Patient A',
            'file_path': str(src),
            'metadata': {'mode': 'kinetics'},
        })

    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    assert (report_root / "Patient A" / "sample.csv").exists()


def test_export_to_report_rejects_path_outside_data_root(client, tmp_path):
    """A source outside the data root is rejected with 403 (traversal guard)."""
    data_root = tmp_path / "data"
    report_root = tmp_path / "report"
    data_root.mkdir()
    report_root.mkdir()
    outside = tmp_path / "secret.csv"
    outside.write_text("x")

    with patch('routes.file_routes.DATA_ROOT', str(data_root)), \
         patch('file_path.DATA_ROOT', str(data_root)), \
         patch.object(state, 'report_root_path', str(report_root)):
        rv = client.post('/export_to_report', json={
            'subject': 'S',
            'file_path': str(outside),
        })

    assert rv.status_code == 403
    assert rv.get_json()['status'] == 'error'


def test_get_headers_empty_csv_returns_empty_list(client, tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("")
    rv = client.get(f'/get_headers?file={str(f)}')
    assert rv.status_code == 200
    assert rv.get_json()['headers'] == []


def test_get_headers_skips_comment_lines(client, tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("# metadata\nTimestamp,Value:1\n0,0.5\n")
    rv = client.get(f'/get_headers?file={str(f)}')
    assert rv.status_code == 200
    assert 'Timestamp' in rv.get_json()['headers']


# ---------------------------------------------------------------------------
# file_routes — get_json_content error paths
# ---------------------------------------------------------------------------

def test_get_json_content_invalid_mode(client):
    rv = client.get('/get_json_content?json_name=test.json&mode=invalid')
    assert rv.status_code == 400


def test_get_json_content_path_traversal_rejected(client):
    rv = client.get('/get_json_content?json_name=../secret.json&mode=kinetics')
    assert rv.status_code == 400


# ---------------------------------------------------------------------------
# file_routes — /delete_data_folder
# ---------------------------------------------------------------------------

def test_delete_data_folder_success(client, tmp_path):
    folder = tmp_path / "sub"
    folder.mkdir()
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(folder)):
        rv = client.post('/delete_data_folder', json={'path': str(folder)})
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    assert not folder.exists()


def test_delete_data_folder_process_running_returns_locked(client):
    state.process = MagicMock()
    state.process.poll.return_value = None
    rv = client.post('/delete_data_folder', json={'path': '/data/sub'})
    assert rv.status_code == 423


def test_delete_data_folder_path_outside_data_root(client, tmp_path):
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=None):
        rv = client.post('/delete_data_folder', json={'path': '../../../etc'})
    assert rv.status_code == 400
    assert 'Invalid' in rv.get_json()['message']


def test_delete_data_folder_cannot_delete_data_root(client, tmp_path):
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(tmp_path)):
        rv = client.post('/delete_data_folder', json={'path': str(tmp_path)})
    assert rv.status_code == 400
    assert 'root' in rv.get_json()['message'].lower()


def test_delete_data_folder_not_found(client, tmp_path):
    ghost = str(tmp_path / "ghost")
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=ghost):
        rv = client.post('/delete_data_folder', json={'path': ghost})
    assert rv.status_code == 404
    assert 'not found' in rv.get_json()['message'].lower()


def test_delete_data_folder_permission_error(client, tmp_path):
    folder = tmp_path / "locked"
    folder.mkdir()
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(folder)), \
         patch('shutil.rmtree', side_effect=PermissionError("denied")):
        rv = client.post('/delete_data_folder', json={'path': str(folder)})
    assert rv.status_code == 403


def test_delete_data_folder_oserror(client, tmp_path):
    folder = tmp_path / "inuse"
    folder.mkdir()
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(folder)), \
         patch('shutil.rmtree', side_effect=OSError("busy")):
        rv = client.post('/delete_data_folder', json={'path': str(folder)})
    assert rv.status_code == 500


# ---------------------------------------------------------------------------
# file_routes — /rename_data_folder
# ---------------------------------------------------------------------------

def test_rename_data_folder_success(client, tmp_path):
    folder = tmp_path / "old"
    folder.mkdir()
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(folder)):
        rv = client.post('/rename_data_folder', json={'path': str(folder), 'new_name': 'new'})
    assert rv.status_code == 200
    body = rv.get_json()
    assert body['status'] == 'success'
    assert body['path'] == str(tmp_path / "new")
    assert not folder.exists()
    assert (tmp_path / "new").is_dir()


def test_rename_data_folder_process_running_returns_locked(client):
    state.process = MagicMock()
    state.process.poll.return_value = None
    rv = client.post('/rename_data_folder', json={'path': '/data/sub', 'new_name': 'x'})
    assert rv.status_code == 423


def test_rename_data_folder_path_outside_data_root(client, tmp_path):
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=None):
        rv = client.post('/rename_data_folder', json={'path': '../../../etc', 'new_name': 'x'})
    assert rv.status_code == 400
    assert 'Invalid folder path' in rv.get_json()['message']


def test_rename_data_folder_cannot_rename_data_root(client, tmp_path):
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(tmp_path)):
        rv = client.post('/rename_data_folder', json={'path': str(tmp_path), 'new_name': 'x'})
    assert rv.status_code == 400
    assert 'root' in rv.get_json()['message'].lower()


def test_rename_data_folder_not_found(client, tmp_path):
    ghost = str(tmp_path / "ghost")
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=ghost):
        rv = client.post('/rename_data_folder', json={'path': ghost, 'new_name': 'x'})
    assert rv.status_code == 404
    assert 'not found' in rv.get_json()['message'].lower()


def test_rename_data_folder_empty_name(client, tmp_path):
    folder = tmp_path / "old"
    folder.mkdir()
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(folder)):
        rv = client.post('/rename_data_folder', json={'path': str(folder), 'new_name': '   '})
    assert rv.status_code == 400
    assert 'required' in rv.get_json()['message'].lower()


def test_rename_data_folder_rejects_traversal_name(client, tmp_path):
    folder = tmp_path / "old"
    folder.mkdir()
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(folder)):
        rv = client.post('/rename_data_folder', json={'path': str(folder), 'new_name': '../escape'})
    assert rv.status_code == 400
    assert 'Invalid folder name' in rv.get_json()['message']
    assert folder.is_dir()


def test_rename_data_folder_rejects_hidden_prefix(client, tmp_path):
    folder = tmp_path / "old"
    folder.mkdir()
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(folder)):
        rv = client.post('/rename_data_folder', json={'path': str(folder), 'new_name': '_hidden'})
    assert rv.status_code == 400
    assert 'Invalid folder name' in rv.get_json()['message']


def test_rename_data_folder_rejects_reserved_name(client, tmp_path):
    folder = tmp_path / "old"
    folder.mkdir()
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(folder)):
        rv = client.post('/rename_data_folder', json={'path': str(folder), 'new_name': 'Root'})
    assert rv.status_code == 400
    assert 'reserved' in rv.get_json()['message'].lower()
    assert folder.is_dir()


def test_rename_data_folder_name_unchanged(client, tmp_path):
    folder = tmp_path / "same"
    folder.mkdir()
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(folder)):
        rv = client.post('/rename_data_folder', json={'path': str(folder), 'new_name': 'same'})
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    assert folder.is_dir()


def test_rename_data_folder_target_exists(client, tmp_path):
    folder = tmp_path / "old"
    folder.mkdir()
    (tmp_path / "taken").mkdir()
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)), \
         patch('routes.file_routes.validate_in_data_root', return_value=str(folder)):
        rv = client.post('/rename_data_folder', json={'path': str(folder), 'new_name': 'taken'})
    assert rv.status_code == 409
    assert 'already exists' in rv.get_json()['message'].lower()
    assert folder.is_dir()


# ---------------------------------------------------------------------------
# file_routes — /api/current_output
# ---------------------------------------------------------------------------

def test_api_current_output_marker_missing(client, tmp_path):
    with patch.object(state, 'script_dir', str(tmp_path)):
        rv = client.get('/api/current_output')
    assert rv.status_code == 404
    assert rv.get_json()['exists'] is False


def test_api_current_output_marker_empty(client, tmp_path):
    log_dir = tmp_path / "log"
    log_dir.mkdir()
    (log_dir / "current_output.txt").write_text("")
    with patch.object(state, 'script_dir', str(tmp_path)):
        rv = client.get('/api/current_output')
    assert rv.status_code == 204


def test_api_current_output_ready(client, tmp_path):
    log_dir = tmp_path / "log"
    log_dir.mkdir()
    (log_dir / "current_output.txt").write_text("/data/sub/run1.csv")
    with patch.object(state, 'script_dir', str(tmp_path)):
        rv = client.get('/api/current_output')
    assert rv.status_code == 200
    body = rv.get_json()
    assert body['exists'] is True
    assert body['filename'] == 'run1.csv'
    assert body['dir'] == '/data/sub'


# ---------------------------------------------------------------------------
# file_routes — /get_num_sources
# ---------------------------------------------------------------------------

def test_get_num_sources_empty_folder_returns_empty_list(client, tmp_path):
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)):
        rv = client.get(f'/get_num_sources?path={str(tmp_path)}')
    assert rv.status_code == 200
    body = rv.get_json()
    assert body['status'] == 'success'
    assert body['num_sources'] == []


def test_get_num_sources_csv_with_two_sources(client, tmp_path):
    csv = tmp_path / "run.csv"
    csv.write_text("# Measurement: ABS\nTimestamp,Value:1,Value:2\n0,0.1,0.2\n")
    with patch('routes.file_routes.DATA_ROOT', str(tmp_path)):
        rv = client.get(f'/get_num_sources?path={str(tmp_path)}')
    assert rv.status_code == 200
    assert rv.get_json()['num_sources'] == [2]


# ---------------------------------------------------------------------------
# Concentration unit — /export_data records # ConcenUnit + guards mismatch;
# /browse migrates legacy CSVs in the selected data folder.
# ---------------------------------------------------------------------------

def _export_kinetics(client, save_dir, concen_unit):
    return client.post('/export_data', json={
        'save_dir': str(save_dir),
        'save_file': 'result',
        'measMode': 'kinetics',
        'meas': 'ABS',
        'measUnit': 'AU',
        'concenUnit': concen_unit,
        'newFile': True,
        'entries': [{'con': '5', 'maxrate': '0.1', 'slope': '0.2', 'sat': '0.3', 'timeSat': '10'}],
    })


def test_export_data_writes_concen_unit(client, tmp_path):
    rv = _export_kinetics(client, tmp_path, 'nM')
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    out = (tmp_path / 'result_kinetics.csv').read_text()
    assert '# ConcenUnit: nM' in out


def test_export_data_single_source_writes_real_values(client, tmp_path):
    # Single-source export sends row values at the top level (no `entries`). They
    # must be persisted, not written as NONE (regression: schema-stripped fields).
    rv = client.post('/export_data', json={
        'save_dir': str(tmp_path), 'save_file': 'one', 'measMode': 'kinetics',
        'meas': 'ABS', 'measUnit': 'abs', 'concenUnit': 'nM', 'newFile': True,
        'maxrate': '0.10', 'slope': '0.20', 'sat': '0.30', 'timeSat': '10', 'con': '5',
    })
    assert rv.get_json()['status'] == 'success'
    rows = [l for l in (tmp_path / 'one_kinetics.csv').read_text().splitlines()
            if l and not l.startswith('#') and not l.startswith('Concentration')]
    assert rows == ['5,0.10,0.20,0.30,10']
    assert 'NONE' not in rows[0]


def test_export_data_single_source_point_mode(client, tmp_path):
    rv = client.post('/export_data', json={
        'save_dir': str(tmp_path), 'save_file': 'pt', 'measMode': 'point',
        'meas': 'ABS', 'measUnit': 'abs', 'concenUnit': '%', 'newFile': True,
        'estValue': '0.4567', 'timePoint': 3, 'con': '12',
    })
    assert rv.get_json()['status'] == 'success'
    rows = [l for l in (tmp_path / 'pt_point.csv').read_text().splitlines()
            if l and not l.startswith('#') and not l.startswith('Concentration')]
    assert rows == ['12,0.4567,3']


def test_export_data_blocks_concen_unit_mismatch(client, tmp_path):
    assert _export_kinetics(client, tmp_path, 'nM').get_json()['status'] == 'success'
    # Appending a ng/µL export into the nM file must be rejected.
    body = _export_kinetics(client, tmp_path, 'ng/µL').get_json()
    assert body['status'] == 'error'
    assert 'unit mismatch' in body['message'].lower()


def test_export_data_appends_when_concen_unit_matches(client, tmp_path):
    assert _export_kinetics(client, tmp_path, 'nM').get_json()['status'] == 'success'
    assert _export_kinetics(client, tmp_path, 'nM').get_json()['status'] == 'success'
    out = (tmp_path / 'result_kinetics.csv').read_text()
    assert out.count('# ConcenUnit: nM') == 1  # metadata written once
    data_rows = [l for l in out.splitlines() if l and not l.startswith('#') and not l.startswith('Concentration')]
    assert len(data_rows) == 2


def test_browse_migrates_legacy_concen_unit(client, tmp_path, monkeypatch):
    monkeypatch.setattr(state, 'data_root_path', str(tmp_path))
    legacy = tmp_path / 'cal_kinetics.csv'
    legacy.write_text(
        "# Measurement: ABS\n# MeasUnit: AU\n# TimeUnit: minutes\n# MeasMode: kinetics\n"
        "Concentration,maxRate,Slope,Sat,Time To Sat\n5,0.1,0.2,0.3,10\n"
    )
    rv = client.post('/browse', data={'path': str(tmp_path)})
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    assert '# ConcenUnit: ng/µL' in legacy.read_text()


def test_browse_returns_files_identity(client, tmp_path, monkeypatch):
    monkeypatch.setattr(state, 'data_root_path', str(tmp_path))
    (tmp_path / 'raw.csv').write_text(
        "# Measurement: ABS\n# Unit: abs\n# Concentration: 5\n# ConcenUnit: nM\n"
        "Timestamp,Value:1\n0,0.1\n"
    )
    body = client.post('/browse', data={'path': str(tmp_path)}).get_json()
    assert body['files_identity']['raw.csv'] == {
        'measurement': 'ABS', 'unit': 'abs', 'concen_unit': 'nM'}


def test_get_json_cal_returns_files_identity(client, tmp_path, monkeypatch):
    monkeypatch.setattr(state, 'json_root_path', str(tmp_path))
    kdir = tmp_path / 'kinetics'
    kdir.mkdir()
    (kdir / 'curve.json').write_text(json.dumps(
        {'fit_type': 'linear', 'for_meas': 'ABS', 'meas_unit': 'abs', 'concen_unit': 'nM'}))
    body = client.get('/get_json_cal?mode=kinetics').get_json()
    assert body['files_identity']['curve.json'] == {
        'measurement': 'ABS', 'unit': 'abs', 'concen_unit': 'nM'}


def test_get_json_cal_backfills_legacy_units(client, tmp_path, monkeypatch):
    monkeypatch.setattr(state, 'json_root_path', str(tmp_path))
    kdir = tmp_path / 'kinetics'
    kdir.mkdir()
    legacy = kdir / 'legacy.json'
    legacy.write_text(json.dumps({'fit_type': 'linear', 'for_meas': 'ABS'}))
    client.get('/get_json_cal?mode=kinetics')  # triggers the back-fill
    filled = json.loads(legacy.read_text())
    assert filled['meas_unit'] == 'NONE'
    assert filled['concen_unit'] == 'ng/µL'


def test_export_cal_coefs_writes_identity(client, tmp_path, monkeypatch):
    monkeypatch.setattr(state, 'json_root_path', str(tmp_path))
    rv = client.post('/export_cal_coefs', json={
        'fit_type': 'linear',
        'for_meas': 'ABS',
        'measUnit': 'abs',
        'concenUnit': 'nM',
        'coef_content': [{'rSquared': 0.99, 'coefficients': [1.0, 2.0]}],
        'file_name': 'curve',
        'cal_mode': 'kinetics',
        'cal_params': ['maxRate'],
        'regress_algo': 'linear',
    })
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'success'
    out = json.loads(next((tmp_path / 'kinetics').glob('curve*.json')).read_text())
    assert out['meas_unit'] == 'abs'
    assert out['concen_unit'] == 'nM'
    assert out['for_meas'] == 'ABS'
