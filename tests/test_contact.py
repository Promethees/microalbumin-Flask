"""Tests for the contact form relay (`src/contact.py`, `/api/contact`).

The properties that matter here: nothing is stored, a submission can never
inject a mail header, the honeypot drops bots without telling them, and an SMTP
failure never leaks to the caller.
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
import contact
from routes.contact_routes import contact_bp
from rate_limit import limiter

for _mod, _orig in _saved_modules.items():
    if _orig is None:
        sys.modules.pop(_mod, None)
    else:
        sys.modules[_mod] = _orig


def _payload(**over):
    base = {'name': 'Ada', 'email': 'ada@example.com',
            'message': 'The 520 nm calibration will not import from my CSV.'}
    base.update(over)
    return base


class TestValidateMessage(unittest.TestCase):
    def test_valid_message_passes_with_default_topic(self):
        msg, err = contact.validate_message(_payload())
        assert err is None
        assert msg['name'] == 'Ada'
        assert msg['topic'] == contact.DEFAULT_TOPIC

    def test_missing_name_rejected(self):
        _, err = contact.validate_message(_payload(name='   '))
        assert 'name' in err.lower()

    def test_bad_email_rejected(self):
        _, err = contact.validate_message(_payload(email='not-an-email'))
        assert 'email' in err.lower()

    def test_too_short_message_rejected(self):
        _, err = contact.validate_message(_payload(message='help'))
        assert 'characters' in err.lower()

    def test_non_dict_payload_rejected(self):
        _, err = contact.validate_message('hello')
        assert err

    def test_unknown_topic_falls_back_to_default(self):
        msg, _ = contact.validate_message(_payload(topic='Free crypto'))
        assert msg['topic'] == contact.DEFAULT_TOPIC

    def test_known_topic_is_kept(self):
        msg, _ = contact.validate_message(_payload(topic='Bug report'))
        assert msg['topic'] == 'Bug report'

    def test_message_keeps_paragraphs_but_is_length_capped(self):
        msg, err = contact.validate_message(
            _payload(message='first line\r\n\r\n\r\n\r\nsecond line ' + 'x' * 9000))
        assert err is None
        assert 'first line\n\nsecond line' in msg['message']
        assert len(msg['message']) == contact.MAX_MESSAGE_LEN

    def test_header_fields_cannot_carry_newlines(self):
        # Header injection: a name or address holding CRLF would let a
        # submission append headers of its own to the outgoing mail.
        msg, err = contact.validate_message(_payload(
            name='Ada\r\nBcc: victim@example.com',
            email='ada@example.com'))
        assert err is None
        assert '\n' not in msg['name'] and '\r' not in msg['name']

    def test_honeypot_detection(self):
        assert contact.is_automated({'website': 'http://spam.example'})
        assert not contact.is_automated({'website': '   '})
        assert not contact.is_automated({})


class TestRecipient(unittest.TestCase):
    def test_contact_email_wins_over_review_inbox(self):
        with patch.dict(os.environ, {'CONTACT_EMAIL': 'support@example.com',
                                     'REVIEW_ADMIN_EMAIL': 'reviews@example.com',
                                     'SMTP_USER': 'bot@example.com'}):
            assert contact.contact_recipient() == 'support@example.com'

    def test_falls_back_to_review_inbox_then_smtp_user(self):
        with patch.dict(os.environ, {'REVIEW_ADMIN_EMAIL': 'reviews@example.com',
                                     'SMTP_USER': 'bot@example.com'}, clear=True):
            assert contact.contact_recipient() == 'reviews@example.com'
        with patch.dict(os.environ, {'SMTP_USER': 'bot@example.com'}, clear=True):
            assert contact.contact_recipient() == 'bot@example.com'

    def test_send_without_recipient_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                contact.send_contact_message(contact.validate_message(_payload())[0])


class TestSendComposition(unittest.TestCase):
    def _sent_message(self, payload):
        server = MagicMock()
        with patch.dict(os.environ, {'CONTACT_EMAIL': 'support@example.com',
                                     'SMTP_USER': 'bot@example.com'}):
            with patch.object(contact, '_smtp_connection', return_value=(server, 'bot@example.com')):
                contact.send_contact_message(contact.validate_message(payload)[0])
        server.sendmail.assert_called_once()
        args = server.sendmail.call_args[0]
        return args[0], args[1], args[2]

    def test_reply_to_is_the_visitor_and_body_is_plain_text(self):
        sender, recipients, raw = self._sent_message(_payload())
        assert sender == 'bot@example.com'
        assert recipients == ['support@example.com']
        assert 'Reply-To: ada@example.com' in raw
        assert 'text/plain' in raw
        assert 'text/html' not in raw

    def test_injected_header_does_not_survive_into_the_mail(self):
        # The text may appear inside the body (it is part of the name the
        # visitor typed); what must not happen is it becoming a header line.
        _, _, raw = self._sent_message(_payload(name='Ada\r\nBcc: victim@example.com'))
        assert not any(line.lower().startswith('bcc:') for line in raw.splitlines())


class TestContactRoutes(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        app.register_blueprint(contact_bp)
        limiter.init_app(app)
        limiter.enabled = False  # rate limiting is covered separately
        self.client = app.test_client()

    def tearDown(self):
        limiter.enabled = True

    def test_valid_submission_sends_mail(self):
        with patch.object(contact, 'send_contact_message') as send:
            rv = self.client.post('/api/contact', json=_payload())
        assert rv.get_json()['status'] == 'success'
        send.assert_called_once()

    def test_invalid_submission_rejected_with_400(self):
        with patch.object(contact, 'send_contact_message') as send:
            rv = self.client.post('/api/contact', json=_payload(email='bad'))
        assert rv.status_code == 400
        send.assert_not_called()

    def test_honeypot_submission_is_accepted_but_never_sent(self):
        with patch.object(contact, 'send_contact_message') as send:
            rv = self.client.post('/api/contact', json=_payload(website='http://spam.example'))
        assert rv.status_code == 200
        assert rv.get_json()['status'] == 'success'
        send.assert_not_called()

    def test_reports_503_when_mail_fails_without_leaking_smtp_detail(self):
        with patch.object(contact, 'send_contact_message',
                          side_effect=RuntimeError('smtp down')):
            rv = self.client.post('/api/contact', json=_payload())
        assert rv.status_code == 503
        assert 'smtp' not in rv.get_json()['message'].lower()

    def test_non_json_body_rejected(self):
        rv = self.client.post('/api/contact', data='name=Ada')
        assert rv.status_code == 400


if __name__ == '__main__':
    unittest.main()
