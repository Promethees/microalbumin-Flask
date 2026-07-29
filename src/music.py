"""Background music for the entertainment widget: radio stations + YouTube refs.

A bench run is long and mostly waiting, so the app can play music in the browser
while it records. There are two sources, and **neither one's audio passes
through Flask** — this module is metadata only:

* **Radio** — the browser's ``<audio>`` element connects straight to the
  broadcaster's published stream URL.
* **YouTube** — the browser embeds the official IFrame player, which fetches
  everything itself. Flask only *parses and names* a link the user pasted.

Consequences, all load-bearing:

* **The feature is online-only.** The app itself is a local desktop tool that
  works offline; the music does not. ``is_online()`` is a cheap TCP probe used
  to tell the widget "there is no network" *before* the user presses play and
  gets a silent, unexplained failure.
* **Stations must be free, public, listener-supported streams.** These are the
  broadcasters' own published direct URLs, which they offer for exactly this
  use. Do not add a station that requires a key, a session, or an account.
* **YouTube is embed-only.** ``resolve_youtube()`` calls the keyless *oEmbed*
  endpoint, which returns a title and a thumbnail and nothing else — it does not
  and must not touch media. Extracting, downloading or caching the audio (a
  ``yt-dlp`` style path) is against YouTube's terms and is the one thing this
  module exists to make unnecessary. Playback belongs to the IFrame player, and
  the player must stay visible while it plays.
* **No API key, ever.** Search would need a YouTube Data API key with a
  10,000-unit daily quota (100 per search), and one key shipped inside the app
  would be shared by every install and exhausted immediately. Users paste a
  link instead; oEmbed names it for free.
"""

import json
import re
import socket
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

# Curated chill stations. ``id`` is what gets persisted in the ``music_station``
# user setting, so treat it as stable — renaming one silently resets that
# user's choice to the default.
STATIONS = [
    {
        "id": "groovesalad",
        "name": "Groove Salad",
        "description": "Chilled ambient downtempo",
        "url": "https://ice1.somafm.com/groovesalad-128-mp3",
        "provider": "SomaFM",
        "home": "https://somafm.com/groovesalad/",
    },
    {
        "id": "dronezone",
        "name": "Drone Zone",
        "description": "Atmospheric textures, minimal beats",
        "url": "https://ice1.somafm.com/dronezone-128-mp3",
        "provider": "SomaFM",
        "home": "https://somafm.com/dronezone/",
    },
    {
        "id": "lush",
        "name": "Lush",
        "description": "Mellow vocals, sensuous and mostly female",
        "url": "https://ice1.somafm.com/lush-128-mp3",
        "provider": "SomaFM",
        "home": "https://somafm.com/lush/",
    },
    {
        "id": "deepspaceone",
        "name": "Deep Space One",
        "description": "Deep ambient and experimental space music",
        "url": "https://ice1.somafm.com/deepspaceone-128-mp3",
        "provider": "SomaFM",
        "home": "https://somafm.com/deepspaceone/",
    },
    {
        "id": "fluid",
        "name": "Fluid",
        "description": "Instrumental hip hop and future soul",
        "url": "https://ice1.somafm.com/fluid-128-mp3",
        "provider": "SomaFM",
        "home": "https://somafm.com/fluid/",
    },
    {
        "id": "spacestation",
        "name": "Space Station Soma",
        "description": "Spaced-out ambient and mid-tempo electronica",
        "url": "https://ice1.somafm.com/spacestation-128-mp3",
        "provider": "SomaFM",
        "home": "https://somafm.com/spacestation/",
    },
    {
        "id": "rp-mellow",
        "name": "Radio Paradise Mellow",
        "description": "Hand-picked mellow eclectic mix",
        "url": "https://stream.radioparadise.com/mellow-128",
        "provider": "Radio Paradise",
        "home": "https://radioparadise.com/",
    },
]

DEFAULT_STATION_ID = STATIONS[0]["id"]

# Probe budget. Short enough that the widget's first paint is not held up by a
# dead network, long enough to survive a slow DNS answer on a lab Wi-Fi.
PROBE_TIMEOUT = 2.0
# Verdicts are cached this long. The widget re-asks on every open and on every
# browser `online` event, so without a cache a user toggling the panel would
# fire a DNS lookup per click.
PROBE_CACHE_SECONDS = 30.0

_probe_cache = {"at": 0.0, "online": False}


def list_stations():
    """Return a copy of the station catalogue (safe for the caller to mutate)."""
    return [dict(s) for s in STATIONS]


def get_station(station_id):
    """Return the station with ``station_id``, or ``None``."""
    for s in STATIONS:
        if s["id"] == station_id:
            return dict(s)
    return None


def valid_station_id(station_id):
    return any(s["id"] == station_id for s in STATIONS)


def _probe(host, port, timeout):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_online(force=False):
    """Best-effort "can we reach a station host?" check.

    A TCP connect to the stream hosts, not an HTTP request: it needs no
    response body, costs one round trip, and still exercises the two things
    that actually fail (DNS and egress). Both hosts are tried because one
    broadcaster being down is not the same as the machine being offline.
    """
    now = time.time()
    if not force and (now - _probe_cache["at"]) < PROBE_CACHE_SECONDS:
        return _probe_cache["online"]

    hosts = []
    for s in STATIONS:
        host = urlsplit(s["url"]).hostname
        if host and host not in hosts:
            hosts.append(host)

    online = False
    for host in hosts[:2]:
        if _probe(host, 443, PROBE_TIMEOUT):
            online = True
            break

    _probe_cache["at"] = now
    _probe_cache["online"] = online
    return online


# ---------------------------------------------------------------------------
# YouTube references (paste-a-link; no API key, no quota)
# ---------------------------------------------------------------------------

# Ids are fixed-alphabet and fixed-ish length. Validating them here means a
# pasted typo is refused by the server with a clear message instead of becoming
# an iframe that silently shows "video unavailable".
_VIDEO_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')
_PLAYLIST_ID_RE = re.compile(r'^[A-Za-z0-9_-]{12,50}$')

# Hosts a YouTube link can legitimately arrive on. Anything else is refused —
# the widget embeds what this returns, so an unvetted host would be an open
# redirect into the player.
_YT_HOSTS = frozenset({
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com",
    "youtu.be", "www.youtu.be",
})

OEMBED_URL = "https://www.youtube.com/oembed"
OEMBED_TIMEOUT = 6.0


def parse_youtube_ref(text):
    """Parse a pasted YouTube link (or bare id) into ``{kind, id}``.

    ``kind`` is ``'video'`` or ``'playlist'``. Returns ``None`` if the text is
    not something the IFrame player could load.

    Accepts what users actually paste: watch URLs, ``youtu.be`` short links,
    ``/embed/`` and ``/shorts/`` paths, ``music.youtube.com``, playlist URLs,
    and a bare 11-character video id. A watch URL carrying **both** ``v`` and
    ``list`` is treated as a playlist, because that is what the user sees when
    they copy the address bar while playing from one.
    """
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None

    # Bare ids, no URL at all.
    if _VIDEO_ID_RE.match(text):
        return {"kind": "video", "id": text}
    if text.startswith(("PL", "OL", "UU", "LL", "RD", "FL")) and _PLAYLIST_ID_RE.match(text):
        return {"kind": "playlist", "id": text}

    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.hostname not in _YT_HOSTS:
        return None

    query = parse_qs(parts.query)
    list_id = (query.get("list") or [""])[0]
    if list_id and _PLAYLIST_ID_RE.match(list_id):
        return {"kind": "playlist", "id": list_id}

    video_id = (query.get("v") or [""])[0]
    if not video_id:
        # Path-style ids: youtu.be/<id>, /embed/<id>, /shorts/<id>, /live/<id>.
        segments = [seg for seg in parts.path.split("/") if seg]
        if segments:
            if parts.hostname in ("youtu.be", "www.youtu.be"):
                video_id = segments[0]
            elif segments[0] in ("embed", "shorts", "live", "v") and len(segments) > 1:
                video_id = segments[1]

    if video_id and _VIDEO_ID_RE.match(video_id):
        return {"kind": "video", "id": video_id}
    return None


def _canonical_url(ref):
    if ref["kind"] == "playlist":
        return "https://www.youtube.com/playlist?list=" + ref["id"]
    return "https://www.youtube.com/watch?v=" + ref["id"]


def resolve_youtube(text, timeout=OEMBED_TIMEOUT):
    """Parse a pasted reference and name it via YouTube's keyless oEmbed.

    Returns ``{kind, id, url, title, author, thumbnail}``. Naming is
    **best-effort**: oEmbed refuses private, deleted and some region-locked
    items, and it is a network call that can simply fail. A queue entry with a
    fallback title is far more useful than a refused paste, so a failed lookup
    still returns the reference — the player reports the real problem (and its
    reason) if the item genuinely cannot be embedded.

    Raises ``ValueError`` only when the text is not a YouTube reference at all.
    """
    ref = parse_youtube_ref(text)
    if not ref:
        raise ValueError("Not a YouTube video or playlist link")

    url = _canonical_url(ref)
    item = {
        "kind": ref["kind"],
        "id": ref["id"],
        "url": url,
        "title": "",
        "author": "",
        "thumbnail": "",
    }

    query = urlencode({"url": url, "format": "json"})
    try:
        request = Request(OEMBED_URL + "?" + query, headers={"User-Agent": "EasyOKAPI"})
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        item["title"] = data.get("title") or ""
        item["author"] = data.get("author_name") or ""
        item["thumbnail"] = data.get("thumbnail_url") or ""
    except Exception:
        pass

    if not item["title"]:
        item["title"] = ("Playlist " if ref["kind"] == "playlist" else "") + ref["id"]
    return item
