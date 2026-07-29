"""Public read-only community endpoints + the review submission relay.

`GET /api/testimonials` and `GET /api/publications` serve the curated files.
`POST /api/testimonials/submit` does **not** publish anything: it validates the
payload and emails it to the admin, who adds it to `testimonials.json` by hand
after confirming consent. That is the whole moderation model — see
`src/community.py`.
"""
from flask import Blueprint, request, jsonify

import community
from rate_limit import limiter, REVIEW_SUBMIT_LIMIT
from validators import validate_json

community_bp = Blueprint('community', __name__)


@community_bp.route('/api/testimonials', methods=['GET'])
def testimonials():
    return jsonify({'status': 'success', 'testimonials': community.get_testimonials()})


@community_bp.route('/api/publications', methods=['GET'])
def publications():
    data = community.get_publications()
    return jsonify({'status': 'success',
                    'citation': data['citation'],
                    'publications': data['publications']})


@community_bp.route('/api/testimonials/submit', methods=['POST'])
@limiter.limit(REVIEW_SUBMIT_LIMIT)
@validate_json({
    'name': (str, '', False),
    'email': (str, '', False),
    'role': (str, '', False),
    'affiliation': (str, '', False),
    'quote': (str, '', False),
    'rating': (int, 5, False),
})
def submit_testimonial(validated_data):
    review, error = community.validate_submission(validated_data)
    if error:
        return jsonify({'status': 'error', 'message': error}), 400

    try:
        community.send_testimonial_submission(review)
    except Exception as e:
        # The reviewer should not see SMTP internals, and a mail outage is not
        # their problem — log it and report a generic failure.
        print(f"submit_testimonial: send failed: {e}")
        return jsonify({'status': 'error',
                        'message': 'Could not send your review right now. Please try again later.'}), 503

    return jsonify({'status': 'success',
                    'message': 'Thank you! Your review was sent to our team for review before publishing.'})
