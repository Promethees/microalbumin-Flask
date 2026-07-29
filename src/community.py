"""Curated community content: user reviews and publication references.

Both lists are **curated files in the repo** (`testimonials.json`,
`publications.json`) — nothing a visitor sends is ever written to them. A
visitor's review goes out as an email to the admin (`REVIEW_ADMIN_EMAIL`), who
decides whether to add it to `testimonials.json` by hand. That keeps the public
banner free of spam and impersonation without a moderation database.

Files are read once and cached in-process; they only change on deploy.
"""
import json
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from email_service import _smtp_connection

# Repo root — the JSON files sit beside main.py.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

TESTIMONIALS_FILE = os.path.join(_ROOT, 'testimonials.json')
PUBLICATIONS_FILE = os.path.join(_ROOT, 'publications.json')

# Submission limits — a review is a short blurb, not an essay. Enforced before
# anything is put in an email so an oversized body can never be composed.
MAX_NAME_LEN = 120
MAX_AFFILIATION_LEN = 200
MAX_QUOTE_LEN = 1200
MIN_QUOTE_LEN = 20

_cache = {}


def _load(path, key):
    """Read and cache one curated JSON file; a missing/broken file yields {}."""
    if key not in _cache:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _cache[key] = data if isinstance(data, dict) else {}
        except Exception as e:
            print(f"community: could not load {path}: {e}")
            _cache[key] = {}
    return _cache[key]


def _clean(value, limit):
    """Trim to a plain single-spaced string, capped at `limit` characters."""
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]


def get_testimonials():
    """Published reviews, newest first. Entries missing name or quote are dropped."""
    raw = _load(TESTIMONIALS_FILE, 'testimonials').get('testimonials') or []
    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = _clean(entry.get('name'), MAX_NAME_LEN)
        quote = _clean(entry.get('quote'), MAX_QUOTE_LEN)
        if not name or not quote:
            continue
        try:
            rating = int(entry.get('rating', 5))
        except (TypeError, ValueError):
            rating = 5
        items.append({
            'name': name,
            'role': _clean(entry.get('role'), MAX_NAME_LEN),
            'affiliation': _clean(entry.get('affiliation'), MAX_AFFILIATION_LEN),
            'quote': quote,
            'rating': min(5, max(1, rating)),
            'date': _clean(entry.get('date'), 32),
        })
    # Undated entries sort last rather than jumping to the front.
    return sorted(items, key=lambda i: i['date'] or '', reverse=True)


def get_publications():
    """`{citation, publications}` for the Publication reference section."""
    data = _load(PUBLICATIONS_FILE, 'publications')
    citation = data.get('citation') if isinstance(data.get('citation'), dict) else {}
    raw = data.get('publications') or []
    pubs = []
    for entry in raw:
        if not isinstance(entry, dict) or not _clean(entry.get('title'), 400):
            continue
        pubs.append({
            'title': _clean(entry.get('title'), 400),
            'authors': _clean(entry.get('authors'), 600),
            'journal': _clean(entry.get('journal'), 300),
            'year': entry.get('year'),
            'volume': _clean(entry.get('volume'), 60),
            'pages': _clean(entry.get('pages'), 60),
            'doi': _clean(entry.get('doi'), 200),
            'url': _clean(entry.get('url'), 500),
            'note': _clean(entry.get('note'), 300),
        })
    # Newest first; a missing year sorts last.
    pubs.sort(key=lambda p: (p.get('year') or 0), reverse=True)
    return {'citation': citation, 'publications': pubs}


_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def validate_submission(payload):
    """Validate a visitor's review submission.

    Returns ``(cleaned_dict, None)`` on success or ``(None, message)`` on
    rejection. The email address is required so the admin can reply and confirm
    consent before publishing the review under someone's name.
    """
    if not isinstance(payload, dict):
        return None, 'Invalid submission.'

    name = _clean(payload.get('name'), MAX_NAME_LEN)
    email = _clean(payload.get('email'), MAX_NAME_LEN)
    quote = _clean(payload.get('quote'), MAX_QUOTE_LEN)

    if not name:
        return None, 'Please enter your name.'
    if not _EMAIL_RE.match(email):
        return None, 'Please enter a valid email address so we can reach you.'
    if len(quote) < MIN_QUOTE_LEN:
        return None, f'Please write at least {MIN_QUOTE_LEN} characters about your experience.'

    try:
        rating = int(payload.get('rating', 5))
    except (TypeError, ValueError):
        rating = 5

    return {
        'name': name,
        'email': email,
        'role': _clean(payload.get('role'), MAX_NAME_LEN),
        'affiliation': _clean(payload.get('affiliation'), MAX_AFFILIATION_LEN),
        'quote': quote,
        'rating': min(5, max(1, rating)),
    }, None


def admin_recipient():
    """Where review submissions are sent. Falls back to the SMTP sender."""
    return os.environ.get('REVIEW_ADMIN_EMAIL') or os.environ.get('SMTP_USER', '')


def send_testimonial_submission(review):
    """Email one validated review to the admin for approval.

    Plain text only: the body is visitor-supplied, so it must never be rendered
    as HTML in the admin's mail client.
    """
    recipient = admin_recipient()
    if not recipient:
        raise RuntimeError('No review recipient configured (REVIEW_ADMIN_EMAIL).')

    sender = os.environ.get('SMTP_USER', '')
    msg = MIMEMultipart()
    msg['Subject'] = f"Easy OKAPI review from {review['name']}"
    msg['From'] = f"Easy OKAPI <{sender}>"
    msg['To'] = recipient
    # Replying goes to the reviewer, so consent can be confirmed in one click.
    msg['Reply-To'] = review['email']

    body = (
        "A visitor submitted a review of Easy OKAPI.\n\n"
        f"Name:        {review['name']}\n"
        f"Email:       {review['email']}\n"
        f"Role:        {review['role'] or '-'}\n"
        f"Affiliation: {review['affiliation'] or '-'}\n"
        f"Rating:      {review['rating']}/5\n\n"
        "Review:\n"
        f"{review['quote']}\n\n"
        "---\n"
        "Nothing has been published. To publish it, confirm consent with the\n"
        "reviewer, then add the entry to testimonials.json and redeploy.\n"
    )
    msg.attach(MIMEText(body, 'plain'))

    server, _ = _smtp_connection()
    try:
        server.sendmail(sender, [recipient], msg.as_string())
    finally:
        server.quit()
