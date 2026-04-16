import pytest
from unittest.mock import patch, MagicMock
import os
from main import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index_page(client):
    """Test that the index page loads."""
    with patch('src.routes.core_routes.get_directory', return_value='/tmp'):
        with patch('src.routes.core_routes.get_file_list', return_value=[]):
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
    with patch('src.routes.core_routes.get_directory', return_value='/tmp/test'):
        with patch('src.routes.core_routes.get_parent_directory', return_value='/tmp'):
            rv = client.get('/get_parents')
            assert rv.status_code == 200
            assert rv.get_json() == {'parent': '/tmp'}

def test_get_children(client):
    """Test the get_children endpoint."""
    with patch('src.routes.core_routes.get_directory', return_value='/tmp'):
        with patch('src.routes.core_routes.get_child_directories', return_value=['child1', 'child2']):
            rv = client.get('/get_children')
            assert rv.status_code == 200
            assert rv.get_json() == {'children': ['child1', 'child2']}

def test_browse_invalid_path(client):
    """Test the browse endpoint with an invalid path."""
    with patch('src.routes.core_routes.browse_directory', return_value=False):
        rv = client.post('/browse', data={'path': '/invalid/path'})
        assert rv.status_code == 200
        assert rv.get_json() == {'status': 'error', 'message': 'Invalid directory'}
