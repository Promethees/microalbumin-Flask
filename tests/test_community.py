"""Tests for the curated community content (reviews + publication reference).

The security-relevant property here is that **nothing a visitor sends is ever
published**: `/api/testimonials/submit` only validates and emails. These tests
pin that, plus the validation rules and the shape of the curated readers.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

_STUBBED = ('config', 'firebase_admin', 'firebase_service', 'flask_socketio',
            'eventlet', 'account', 'flask_sqlalchemy', 'sqlalchemy')
_saved_modules = {_m: sys.modules.get(_m) for _m in _STUBBED}
for _mod in _STUBBED:
    sys.modules[_mod] = MagicMock()
sys.modules['config'].Config.REDIS_URL = None
sys.modules['config'].Config.SECRET_KEY = 'test-secret'

from flask import Flask
import community
from routes.community_routes import community_bp
from rate_limit import limiter

for _mod, _orig in _saved_modules.items():
    if _orig is None:
        sys.modules.pop(_mod, None)
    else:
        sys.modules[_mod] = _orig


class TestCuratedReaders(unittest.TestCase):
    def setUp(self):
        community._cache.clear()

    def tearDown(self):
        community._cache.clear()

    def test_testimonials_drop_entries_without_name_or_quote(self):
        community._cache['testimonials'] = {'testimonials': [
            {'name': 'A', 'quote': 'a real review'},
            {'name': '', 'quote': 'no name'},
            {'name': 'C', 'quote': ''},
            'not a dict',
        ]}
        items = community.get_testimonials()
        assert [i['name'] for i in items] == ['A']

    def test_testimonials_clamp_rating_and_sort_newest_first(self):
        community._cache['testimonials'] = {'testimonials': [
            {'name': 'Old', 'quote': 'x' * 30, 'rating': 9, 'date': '2025-01-01'},
            {'name': 'New', 'quote': 'y' * 30, 'rating': 0, 'date': '2026-01-01'},
        ]}
        items = community.get_testimonials()
        assert [i['name'] for i in items] == ['New', 'Old']
        assert items[0]['rating'] == 1 and items[1]['rating'] == 5

    def test_testimonial_fields_are_length_capped(self):
        community._cache['testimonials'] = {'testimonials': [
            {'name': 'N' * 500, 'quote': 'Q' * 5000},
        ]}
        item = community.get_testimonials()[0]
        assert len(item['name']) == community.MAX_NAME_LEN
        assert len(item['quote']) == community.MAX_QUOTE_LEN

    def test_missing_file_yields_empty_lists_not_an_error(self):
        with patch.object(community, 'TESTIMONIALS_FILE', '/nonexistent/x.json'):
            assert community.get_testimonials() == []

    def test_publications_drop_untitled_and_sort_newest_first(self):
        community._cache['publications'] = {
            'citation': {'apa': 'cite me'},
            'publications': [
                {'title': 'Older', 'year': 2020},
                {'title': 'Newer', 'year': 2026},
                {'title': '', 'year': 2030},
            ],
        }
        data = community.get_publications()
        assert [p['title'] for p in data['publications']] == ['Newer', 'Older']
        assert data['citation']['apa'] == 'cite me'

    def test_shipped_files_parse(self):
        # The committed curated files must always load — a syntax error in them
        # would silently blank both sections in production.
        assert isinstance(community.get_testimonials(), list)
        assert isinstance(community.get_publications()['publications'], list)


class TestValidateSubmission(unittest.TestCase):
    @staticmethod
    def _payload(**over):
        base = {'name': 'Ada', 'email': 'ada@example.com',
                'quote': 'Easy OKAPI saved us a whole afternoon of work.'}
        base.update(over)
        return base

    def test_valid_submission_passes(self):
        review, err = community.validate_submission(self._payload())
        assert err is None
        assert review['name'] == 'Ada' and review['rating'] == 5

    def test_missing_name_rejected(self):
        _, err = community.validate_submission(self._payload(name='   '))
        assert 'name' in err.lower()

    def test_bad_email_rejected(self):
        _, err = community.validate_submission(self._payload(email='not-an-email'))
        assert 'email' in err.lower()

    def test_too_short_quote_rejected(self):
        _, err = community.validate_submission(self._payload(quote='nice'))
        assert 'characters' in err.lower()

    def test_non_dict_payload_rejected(self):
        _, err = community.validate_submission('hello')
        assert err

    def test_whitespace_and_length_are_normalized(self):
        review, err = community.validate_submission(
            self._payload(name='  Ada    Lovelace  ', quote='a' * 5000))
        assert err is None
        assert review['name'] == 'Ada Lovelace'
        assert len(review['quote']) == community.MAX_QUOTE_LEN

    def test_rating_is_clamped(self):
        review, _ = community.validate_submission(self._payload(rating=99))
        assert review['rating'] == 5


class TestCommunityRoutes(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        app.register_blueprint(community_bp)
        limiter.init_app(app)
        limiter.enabled = False  # rate limiting is covered separately
        self.client = app.test_client()
        community._cache.clear()

    def tearDown(self):
        limiter.enabled = True
        community._cache.clear()

    def test_get_testimonials_returns_curated_list(self):
        community._cache['testimonials'] = {'testimonials': [
            {'name': 'Ada', 'quote': 'x' * 30, 'rating': 5, 'date': '2026-01-01'}]}
        body = self.client.get('/api/testimonials').get_json()
        assert body['status'] == 'success'
        assert body['testimonials'][0]['name'] == 'Ada'

    def test_get_publications_returns_citation_and_list(self):
        body = self.client.get('/api/publications').get_json()
        assert body['status'] == 'success'
        assert 'citation' in body and 'publications' in body

    def test_submit_sends_email_and_publishes_nothing(self):
        community._cache['testimonials'] = {'testimonials': []}
        with patch.object(community, 'send_testimonial_submission') as send:
            rv = self.client.post('/api/testimonials/submit', json={
                'name': 'Ada', 'email': 'ada@example.com',
                'quote': 'Easy OKAPI saved us a whole afternoon of work.'})
        assert rv.get_json()['status'] == 'success'
        send.assert_called_once()
        # The public list is untouched — approval happens out of band.
        assert self.client.get('/api/testimonials').get_json()['testimonials'] == []

    def test_submit_rejects_invalid_payload_with_400(self):
        with patch.object(community, 'send_testimonial_submission') as send:
            rv = self.client.post('/api/testimonials/submit',
                                  json={'name': 'Ada', 'email': 'bad', 'quote': 'x' * 40})
        assert rv.status_code == 400
        send.assert_not_called()

    def test_submit_reports_503_when_mail_fails(self):
        with patch.object(community, 'send_testimonial_submission',
                          side_effect=RuntimeError('smtp down')):
            rv = self.client.post('/api/testimonials/submit', json={
                'name': 'Ada', 'email': 'ada@example.com',
                'quote': 'Easy OKAPI saved us a whole afternoon of work.'})
        assert rv.status_code == 503
        # The SMTP failure detail must not leak to the caller.
        assert 'smtp' not in rv.get_json()['message'].lower()

    def test_submit_rejects_non_json_body(self):
        rv = self.client.post('/api/testimonials/submit', data='name=Ada')
        assert rv.status_code == 400


if __name__ == '__main__':
    unittest.main()
