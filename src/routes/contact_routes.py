"""The contact form relay.

`POST /api/contact` stores nothing: it validates the payload and emails it to
the team inbox (see `src/contact.py`). The page that posts here is
`templates/contact.html`, which replaced the old `mailto:` footer link — a
visitor with no desktop mail client configured could not use that at all.
"""
from flask import Blueprint, request, jsonify

import contact
from rate_limit import limiter, CONTACT_LIMIT
from validators import validate_json

contact_bp = Blueprint('contact', __name__)

# Same wording whether the message was sent or silently dropped as automated —
# a bot that is told it failed simply retries.
_SENT_MESSAGE = 'Thank you! Your message is on its way — we usually reply within a few working days.'


@contact_bp.route('/api/contact', methods=['POST'])
@limiter.limit(CONTACT_LIMIT)
@validate_json({
    'name': (str, '', False),
    'email': (str, '', False),
    'affiliation': (str, '', False),
    'topic': (str, '', False),
    'message': (str, '', False),
    'website': (str, '', False),   # honeypot; only bots fill it
})
def submit_contact(validated_data):
    if contact.is_automated(validated_data):
        return jsonify({'status': 'success', 'message': _SENT_MESSAGE})

    payload, error = contact.validate_message(validated_data)
    if error:
        return jsonify({'status': 'error', 'message': error}), 400

    try:
        contact.send_contact_message(payload)
    except Exception as e:
        # The visitor should not see SMTP internals, and a mail outage is not
        # their problem — log it and report a generic failure.
        print(f"submit_contact: send failed: {e}")
        return jsonify({'status': 'error',
                        'message': 'Could not send your message right now. Please try again later.'}), 503

    return jsonify({'status': 'success', 'message': _SENT_MESSAGE})
