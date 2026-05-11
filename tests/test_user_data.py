import unittest
import sys
import os
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Stub out config (requires python-dotenv which is not in the test venv)
mock_config = MagicMock()
mock_config.Config.REDIS_URL = None
sys.modules['config'] = mock_config

# Prevent flask session proxy from raising outside a request context
import flask
flask.session = {}

from user_data import (
    get_user_data, update_file_metadata, get_file_metadata,
    USER_DATA
)

TEST_USER = 'test-user-123'

class TestUserData(unittest.TestCase):
    def setUp(self):
        USER_DATA._data.clear()

    def test_get_user_data_initialization(self):
        data = get_user_data(TEST_USER)
        self.assertIn('csv', data)
        self.assertIn('json', data)
        self.assertIn('metadata_cache', data)
        self.assertEqual(data['csv'], {})

    def test_metadata_cache_update(self):
        content = (
            "# Measurement: ABSORBANCE\n"
            "# Unit: NONE\n"
            "Timestamp,Value:1,Value:2\n"
            "0,0.1,0.2\n"
        )
        filename = "test_multi.csv"
        update_file_metadata(filename, content, user_id=TEST_USER)

        metadata = get_file_metadata(filename, user_id=TEST_USER)
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata['num_sources'], 2)

    def test_metadata_cache_persistence(self):
        content = "Timestamp,Value:1\n0,0.1"
        filename = "test_single.csv"

        update_file_metadata(filename, content, user_id=TEST_USER)

        metadata = get_file_metadata(filename, user_id=TEST_USER)
        self.assertEqual(metadata['num_sources'], 1)

        user_data = get_user_data(TEST_USER)
        self.assertIn(filename, user_data['metadata_cache'])

    def test_metadata_cache_missing_header(self):
        content = "# Measurement: VOID\n"
        filename = "empty.csv"
        update_file_metadata(filename, content, user_id=TEST_USER)

        metadata = get_file_metadata(filename, user_id=TEST_USER)
        self.assertIsNone(metadata)

if __name__ == '__main__':
    unittest.main()
