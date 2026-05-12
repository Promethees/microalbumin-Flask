import unittest
from unittest.mock import MagicMock, patch
import json
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

class TestRedisIntegration(unittest.TestCase):
    def setUp(self):
        # Mock Redis client
        self.mock_redis = MagicMock()
        self.patcher = patch('redis.from_url', return_value=self.mock_redis)
        self.mock_from_url = self.patcher.start()

        # Reload user_data AND config so the REDIS_URL patch.dict takes effect.
        # Other test modules may have stubbed config with REDIS_URL=None.
        for mod in ('user_data', 'config'):
            sys.modules.pop(mod, None)

    def tearDown(self):
        self.patcher.stop()
        for mod in ('user_data', 'config'):
            sys.modules.pop(mod, None)

    def test_save_load_redis(self):
        with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
            import user_data
            from flask import Flask, session
            
            app = Flask(__name__)
            app.secret_key = 'test'
            
            with app.test_request_context():
                session['user_id'] = 'test-user'
                uid = 'test-user'
                
                # Mock get to return nothing initially
                self.mock_redis.get.return_value = None
                
                # 1. Test get_user_data (should create default and save)
                data = user_data.get_user_data(uid)
                self.assertEqual(data['drive']['mode'], 'guest')
                self.mock_redis.setex.assert_called()
                
                # 2. Test save_user_data
                data['csv']['test.csv'] = 'content'
                user_data.save_user_data(data, uid)
                
                # Verify setex was called with correct data
                args, kwargs = self.mock_redis.setex.call_args
                self.assertEqual(args[0], f"user:{uid}")
                saved_data = json.loads(args[2])
                self.assertEqual(saved_data['csv']['test.csv'], 'content')
                
                # 3. Test context manager
                # Reset mock
                self.mock_redis.setex.reset_mock()
                # Mock get to return the data we just "saved"
                self.mock_redis.get.return_value = json.dumps(data)
                
                with user_data.user_data_session(uid) as d:
                    d['json']['kinetics']['test.json'] = '{}'
                
                # Verify automatic save on exit
                self.mock_redis.setex.assert_called_once()
                args, kwargs = self.mock_redis.setex.call_args
                saved_data = json.loads(args[2])
                self.assertEqual(saved_data['json']['kinetics']['test.json'], '{}')

if __name__ == '__main__':
    unittest.main()
