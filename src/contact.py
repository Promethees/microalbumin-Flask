"""Visitor contact form: validate a message and relay it to the team inbox.

Nothing is stored and nothing is published. `POST /api/contact` validates the
payload and emails it to `CONTACT_EMAIL` (falling back to the review inbox, then
the SMTP sender) with `Reply-To` set to the visitor, so answering is one click
and no database ever holds the message.

Plain text only: the body is visitor-supplied, so it must never be rendered as
HTML in the recipient's mail client. Every field that reaches a mail *header*
(name, email, topic) goes through `_clean`, which collapses all whitespace —
including CR/LF — so a submission cannot inject a header of its own.
"""
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from email_service import _smtp_connection

# Submission limits — a contact message is a question, not a manuscript.
# Enforced before anything is put in an email so an oversized body can never be
# composed.
MAX_NAME_LEN = 120
MAX_EMAIL_LEN = 200
MAX_AFFILIATION_LEN = 200
MAX_MESSAGE_LEN = 4000
MIN_MESSAGE_LEN = 20

# The topic is a closed set: it becomes part of the subject line, so it is
# picked from here rather than trusted from the request.
TOPICS = (
    'General enquiry',
    'Technical support',
    'Licensing and activation',
    'Bug report',
    'Privacy or data request',
    'Partnership or collaboration',
)
DEFAULT_TOPIC = TOPICS[0]

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _clean(value, limit):
    """Trim to a plain single-spaced string, capped at `limit` characters."""
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]


def _clean_message(value, limit):
    """Normalise the message body while keeping its paragraph breaks.

    A message is prose, so unlike a header field it keeps newlines. CR is
    dropped and runs of blank lines collapse, which keeps the relayed mail
    readable without letting a submission pad the inbox with whitespace.
    """
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()[:limit]


def is_automated(payload):
    """True when the honeypot field came back filled.

    The form renders a `website` input that is hidden from people and skipped by
    the tab order, so only a form-filling bot ever populates it. The caller
    answers such a submission with the normal success message and sends nothing
    — a bot that is told it failed simply retries.
    """
    if not isinstance(payload, dict):
        return False
    return bool(_clean(payload.get('website'), 200))


def validate_message(payload):
    """Validate a visitor's contact submission.

    Returns ``(cleaned_dict, None)`` on success or ``(None, message)`` on
    rejection. The email address is required — a message we cannot answer is of
    no use to either side.
    """
    if not isinstance(payload, dict):
        return None, 'Invalid submission.'

    name = _clean(payload.get('name'), MAX_NAME_LEN)
    email = _clean(payload.get('email'), MAX_EMAIL_LEN)
    message = _clean_message(payload.get('message'), MAX_MESSAGE_LEN)
    topic = _clean(payload.get('topic'), MAX_NAME_LEN)

    if not name:
        return None, 'Please enter your name.'
    if not _EMAIL_RE.match(email):
        return None, 'Please enter a valid email address so we can reply.'
    if len(message) < MIN_MESSAGE_LEN:
        return None, f'Please write at least {MIN_MESSAGE_LEN} characters so we can help.'

    return {
        'name': name,
        'email': email,
        'affiliation': _clean(payload.get('affiliation'), MAX_AFFILIATION_LEN),
        'topic': topic if topic in TOPICS else DEFAULT_TOPIC,
        'message': message,
    }, None


def contact_recipient():
    """Where contact messages are sent.

    `CONTACT_EMAIL` first so support mail can be routed away from the review
    inbox later without touching code; otherwise the review inbox, otherwise the
    SMTP sender.
    """
    return (os.environ.get('CONTACT_EMAIL')
            or os.environ.get('REVIEW_ADMIN_EMAIL')
            or os.environ.get('SMTP_USER', ''))


def send_contact_message(message):
    """Email one validated contact message to the team inbox."""
    recipient = contact_recipient()
    if not recipient:
        raise RuntimeError('No contact recipient configured (CONTACT_EMAIL).')

    sender = os.environ.get('SMTP_USER', '')
    msg = MIMEMultipart()
    msg['Subject'] = f"Easy OKAPI contact — {message['topic']} — {message['name']}"
    msg['From'] = f"Easy OKAPI <{sender}>"
    msg['To'] = recipient
    # Replying goes to the visitor, so the thread continues in one click.
    msg['Reply-To'] = message['email']

    body = (
        "A visitor sent a message through the Easy OKAPI contact form.\n\n"
        f"Name:        {message['name']}\n"
        f"Email:       {message['email']}\n"
        f"Affiliation: {message['affiliation'] or '-'}\n"
        f"Topic:       {message['topic']}\n\n"
        "Message:\n"
        f"{message['message']}\n\n"
        "---\n"
        "Reply to this email to answer the sender directly. Nothing was stored.\n"
    )
    msg.attach(MIMEText(body, 'plain'))

    server, _ = _smtp_connection()
    try:
        server.sendmail(sender, [recipient], msg.as_string())
    finally:
        server.quit()
