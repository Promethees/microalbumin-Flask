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
