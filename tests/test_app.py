import pytest
from main import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index_page(client):
    """Test that the index page loads."""
    rv = client.get('/')
    assert rv.status_code == 200
    assert b'Easy OKAPI' in rv.data or b'EasySensorKit' in rv.data
