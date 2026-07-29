"""Background-music routes.

Metadata only — no audio passes through Flask, for either source. Radio plays
through the browser's ``<audio>`` element; YouTube plays through the official
IFrame player. Flask parses links and remembers a queue. See ``src/music.py``.
"""

from flask import Blueprint, jsonify

import music as _music
import music_queue as _music_queue
import user_settings as _user_settings
from validators import validate_json

music_bp = Blueprint('music', __name__)


@music_bp.route('/music/stations', methods=['GET'])
def get_stations():
    """Station catalogue, saved queue and connectivity verdict for the widget.

    The client asks on open and whenever the browser fires `online`, so the
    probe is cached (`music.PROBE_CACHE_SECONDS`) rather than run per call.
    """
    settings = _user_settings.load()
    return jsonify({
        'status': 'success',
        'enabled': bool(settings.get('music_enabled', False)),
        'online': _music.is_online(),
        'stations': _music.list_stations(),
        'current': settings.get('music_station', _music.DEFAULT_STATION_ID),
        'volume': settings.get('music_volume', 40),
        'source': settings.get('music_source', 'radio'),
        'loop_mode': settings.get('music_loop_mode', 'all'),
        'shuffle': bool(settings.get('music_shuffle', False)),
        'queue': _music_queue.load(),
    })


@music_bp.route('/music/resolve', methods=['POST'])
@validate_json({'ref': (str, '', True)})
def resolve_ref(validated_data):
    """Turn a pasted YouTube link into a named queue entry.

    Server-side because it both **validates** (an unparseable paste is refused
    here with a message, instead of becoming an iframe that silently shows
    "video unavailable") and **names** the item through the keyless oEmbed
    endpoint, which the browser cannot call without a CORS round trip.
    """
    try:
        item = _music.resolve_youtube(validated_data['ref'])
    except ValueError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 400
    return jsonify({'status': 'success', 'item': item})


@music_bp.route('/music/queue', methods=['GET'])
def get_queue():
    return jsonify({'status': 'success', 'queue': _music_queue.load()})


@music_bp.route('/music/queue', methods=['POST'])
@validate_json({'queue': (list, None, True)})
def set_queue(validated_data):
    """Replace the whole queue. Add, remove and reorder are all this one call —
    the client owns ordering, so there is no partial-update API to keep in sync
    with it."""
    if not _music_queue.save(validated_data['queue']):
        return jsonify({'status': 'failure', 'message': 'Could not save the queue'}), 500
    return jsonify({'status': 'success', 'queue': _music_queue.load()})


@music_bp.route('/music/queue/add', methods=['POST'])
@validate_json({'ref': (str, '', True)})
def add_to_queue(validated_data):
    """Resolve a pasted link and append it in one round trip (the common case)."""
    try:
        item = _music.resolve_youtube(validated_data['ref'])
    except ValueError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 400
    return jsonify({'status': 'success', 'item': item, 'queue': _music_queue.add(item)})
