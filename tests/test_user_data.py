import unittest
import sys
import os
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Mock flask session before importing user_data
import flask
flask.session = {}

from user_data import (
    get_user_data, update_file_metadata, get_file_metadata,
    USER_DATA
)

class TestUserData(unittest.TestCase):
    def setUp(self):
        # Clear global USER_DATA before each test
        USER_DATA.clear()
        flask.session.clear()
        flask.session['user_id'] = 'test-user-123'

    def test_get_user_data_initialization(self):
        data = get_user_data()
        self.assertIn('csv', data)
        self.assertIn('json', data)
        self.assertIn('metadata_cache', data)
        self.assertEqual(data['csv'], {})

    def test_metadata_cache_update(self):
        content = """# Measurement: ABSORBANCE
# Unit: NONE
Timestamp,Value:1,Value:2
0,0.1,0.2
"""
        filename = "test_multi.csv"
        update_file_metadata(filename, content)
        
        metadata = get_file_metadata(filename)
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata['num_sources'], 2)

    def test_metadata_cache_persistence(self):
        content = "Timestamp,Value:1\n0,0.1"
        filename = "test_single.csv"
        
        # Update cache
        update_file_metadata(filename, content)
        
        # Verify via get_file_metadata
        metadata = get_file_metadata(filename)
        self.assertEqual(metadata['num_sources'], 1)
        
        # Direct check on internal STRUCTURE
        uid = flask.session['user_id']
        self.assertIn(filename, USER_DATA[uid]['metadata_cache'])

    def test_metadata_cache_missing_header(self):
        # Just metadata, no header
        content = "# Measurement: VOID\n"
        filename = "empty.csv"
        update_file_metadata(filename, content)
        
        metadata = get_file_metadata(filename)
        self.assertIsNone(metadata)

if __name__ == '__main__':
    unittest.main()
