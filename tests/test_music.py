import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import music
import music_queue
import state
import user_settings


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    music._probe_cache["at"] = 0.0
    music._probe_cache["online"] = False
    yield
    music._probe_cache["at"] = 0.0
    music._probe_cache["online"] = False


# ---------------------------------------------------------------------------
# Station catalogue
# ---------------------------------------------------------------------------

class TestStations:
    def test_catalogue_is_non_empty(self):
        assert len(music.list_stations()) >= 3

    def test_ids_are_unique(self):
        ids = [s["id"] for s in music.STATIONS]
        assert len(ids) == len(set(ids))

    def test_every_station_has_required_fields(self):
        for s in music.STATIONS:
            for key in ("id", "name", "description", "url", "provider", "home"):
                assert s.get(key), "%s missing %s" % (s.get("id"), key)

    def test_streams_are_https(self):
        # An http stream on a page the browser may serve over https would be
        # blocked as mixed content, and it leaks the listening habit in clear.
        for s in music.STATIONS:
            assert s["url"].startswith("https://"), s["id"]

    def test_default_station_is_in_catalogue(self):
        assert music.valid_station_id(music.DEFAULT_STATION_ID)

    def test_default_setting_matches_a_real_station(self):
        assert music.valid_station_id(user_settings.DEFAULTS["music_station"])

    def test_list_stations_returns_copies(self):
        listed = music.list_stations()
        listed[0]["name"] = "mutated"
        assert music.STATIONS[0]["name"] != "mutated"

    def test_get_station_known_and_unknown(self):
        assert music.get_station(music.DEFAULT_STATION_ID)["id"] == music.DEFAULT_STATION_ID
        assert music.get_station("no-such-station") is None

    def test_valid_station_id_rejects_unknown(self):
        assert not music.valid_station_id("no-such-station")
        assert not music.valid_station_id("")


# ---------------------------------------------------------------------------
# Connectivity probe
# ---------------------------------------------------------------------------

class TestIsOnline:
    def test_true_when_a_host_answers(self):
        with patch.object(music, "_probe", return_value=True) as p:
            assert music.is_online(force=True) is True
        assert p.call_count == 1  # stops at the first host that answers

    def test_false_when_no_host_answers(self):
        with patch.object(music, "_probe", return_value=False):
            assert music.is_online(force=True) is False

    def test_falls_through_to_second_host(self):
        with patch.object(music, "_probe", side_effect=[False, True]) as p:
            assert music.is_online(force=True) is True
        assert p.call_count == 2

    def test_verdict_is_cached(self):
        with patch.object(music, "_probe", return_value=True):
            assert music.is_online(force=True) is True
        with patch.object(music, "_probe", return_value=False) as p:
            assert music.is_online() is True  # served from cache
            p.assert_not_called()

    def test_force_bypasses_cache(self):
        with patch.object(music, "_probe", return_value=True):
            music.is_online(force=True)
        with patch.object(music, "_probe", return_value=False):
            assert music.is_online(force=True) is False

    def test_probe_swallows_socket_errors(self):
        with patch("socket.create_connection", side_effect=OSError("unreachable")):
            assert music._probe("example.invalid", 443, 0.01) is False


# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------

class TestMusicSettings:
    def test_defaults_are_off(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        s = user_settings.load()
        assert s["music_enabled"] is False
        assert s["music_volume"] == 40

    def test_enable_toggle_saves(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"music_enabled": True})
        assert user_settings.load()["music_enabled"] is True

    def test_station_must_exist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"music_station": "dronezone"})
        assert user_settings.load()["music_station"] == "dronezone"
        user_settings.save({"music_station": "not-a-station"})
        assert user_settings.load()["music_station"] == "dronezone"

    def test_volume_is_clamped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"music_volume": 150})
        assert user_settings.load()["music_volume"] == 100
        user_settings.save({"music_volume": -20})
        assert user_settings.load()["music_volume"] == 0

    def test_volume_rejects_garbage(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"music_volume": "loud"})
        assert user_settings.load()["music_volume"] == 40


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

class TestStationsRoute:
    def test_returns_catalogue_and_verdict(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        with patch.object(music, "is_online", return_value=True):
            resp = client.get('/music/stations')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['status'] == 'success'
        assert data['online'] is True
        assert data['enabled'] is False           # default-off
        assert len(data['stations']) == len(music.STATIONS)
        assert music.valid_station_id(data['current'])

    def test_reports_offline(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        with patch.object(music, "is_online", return_value=False):
            data = json.loads(client.get('/music/stations').data)
        assert data['online'] is False

    def test_reflects_saved_preferences(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"music_enabled": True, "music_station": "lush", "music_volume": 15})
        with patch.object(music, "is_online", return_value=True):
            data = json.loads(client.get('/music/stations').data)
        assert data['enabled'] is True
        assert data['current'] == 'lush'
        assert data['volume'] == 15

    def test_route_does_not_probe_the_network_per_call(self, client, tmp_path, monkeypatch):
        # The widget re-asks on every open and every `online` event; the cache
        # is what keeps that from becoming a DNS lookup per click.
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        with patch.object(music, "_probe", return_value=True) as p:
            client.get('/music/stations')
            client.get('/music/stations')
        assert p.call_count == 1


# ---------------------------------------------------------------------------
# YouTube reference parsing (paste-a-link; no API key)
# ---------------------------------------------------------------------------

VIDEO_ID = "jfKfPfyJRdk"
PLAYLIST_ID = "PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI"


class TestParseYoutubeRef:
    @pytest.mark.parametrize("text", [
        "https://www.youtube.com/watch?v=" + VIDEO_ID,
        "http://youtube.com/watch?v=" + VIDEO_ID,
        "https://m.youtube.com/watch?v=" + VIDEO_ID,
        "https://music.youtube.com/watch?v=" + VIDEO_ID,
        "https://youtu.be/" + VIDEO_ID,
        "https://youtu.be/%s?si=abcd" % VIDEO_ID,
        "https://www.youtube.com/embed/" + VIDEO_ID,
        "https://www.youtube.com/shorts/" + VIDEO_ID,
        "https://www.youtube-nocookie.com/embed/" + VIDEO_ID,
        "www.youtube.com/watch?v=" + VIDEO_ID,       # no scheme
        "  https://youtu.be/%s  " % VIDEO_ID,        # padded paste
        VIDEO_ID,                                    # bare id
    ])
    def test_video_forms(self, text):
        assert music.parse_youtube_ref(text) == {"kind": "video", "id": VIDEO_ID}

    @pytest.mark.parametrize("text", [
        "https://www.youtube.com/playlist?list=" + PLAYLIST_ID,
        "https://www.youtube.com/watch?v=%s&list=%s" % (VIDEO_ID, PLAYLIST_ID),
        PLAYLIST_ID,
    ])
    def test_playlist_forms(self, text):
        assert music.parse_youtube_ref(text) == {"kind": "playlist", "id": PLAYLIST_ID}

    def test_watch_url_with_list_prefers_playlist(self):
        # Copying the address bar while playing from a playlist yields both
        # params; the user meant the playlist.
        ref = music.parse_youtube_ref(
            "https://www.youtube.com/watch?v=%s&list=%s&index=3" % (VIDEO_ID, PLAYLIST_ID))
        assert ref["kind"] == "playlist"

    @pytest.mark.parametrize("text", [
        "https://vimeo.com/123456",
        "https://evil.example.com/watch?v=" + VIDEO_ID,   # non-YouTube host
        "https://www.youtube.com/watch?v=short",          # malformed id
        "https://www.youtube.com/",
        "just some words",
        "",
        "   ",
        None,
        12345,
    ])
    def test_rejects_non_youtube(self, text):
        assert music.parse_youtube_ref(text) is None


class TestResolveYoutube:
    def _oembed(self, payload):
        class _Response:
            def read(self_inner):
                return json.dumps(payload).encode("utf-8")

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False
        return _Response()

    def test_names_a_video_via_oembed(self):
        payload = {"title": "lofi beats", "author_name": "Some Channel",
                   "thumbnail_url": "https://i.ytimg.com/vi/x/hq.jpg"}
        with patch.object(music, "urlopen", return_value=self._oembed(payload)):
            item = music.resolve_youtube("https://youtu.be/" + VIDEO_ID)
        assert item["kind"] == "video"
        assert item["id"] == VIDEO_ID
        assert item["title"] == "lofi beats"
        assert item["author"] == "Some Channel"
        assert item["url"] == "https://www.youtube.com/watch?v=" + VIDEO_ID

    def test_playlist_gets_canonical_url(self):
        with patch.object(music, "urlopen", side_effect=OSError("offline")):
            item = music.resolve_youtube(PLAYLIST_ID)
        assert item["kind"] == "playlist"
        assert item["url"] == "https://www.youtube.com/playlist?list=" + PLAYLIST_ID

    def test_failed_lookup_still_returns_a_usable_item(self):
        # Naming is best-effort: a queue entry with a fallback title beats a
        # refused paste, and the player reports the real reason if it cannot
        # actually be embedded.
        with patch.object(music, "urlopen", side_effect=OSError("no network")):
            item = music.resolve_youtube(VIDEO_ID)
        assert item["id"] == VIDEO_ID
        assert item["title"] == VIDEO_ID

    def test_rejects_non_youtube_text(self):
        with pytest.raises(ValueError):
            music.resolve_youtube("https://vimeo.com/123")

    def test_never_requests_media(self):
        # The whole point of oEmbed here: metadata only, no media endpoint.
        captured = {}

        def _fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return self._oembed({"title": "x"})

        with patch.object(music, "urlopen", side_effect=_fake_urlopen):
            music.resolve_youtube(VIDEO_ID)
        assert captured['url'].startswith(music.OEMBED_URL)


# ---------------------------------------------------------------------------
# Persisted queue
# ---------------------------------------------------------------------------

def _item(ref_id="abc12345678", kind="video", title="t"):
    return {"kind": kind, "id": ref_id, "url": "u", "title": title,
            "author": "a", "thumbnail": "th"}


class TestQueueStore:
    def test_missing_file_is_an_empty_queue(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert music_queue.load() == []

    def test_corrupt_file_is_an_empty_queue(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        (tmp_path / "music_queue.json").write_text("{not json")
        assert music_queue.load() == []

    def test_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        music_queue.save([_item("aaa11111111"), _item("bbb22222222")])
        loaded = music_queue.load()
        assert [i["id"] for i in loaded] == ["aaa11111111", "bbb22222222"]

    def test_drops_malformed_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        music_queue.save([_item(), {"kind": "video"}, "nope", None,
                          {"kind": "podcast", "id": "x"}])
        assert len(music_queue.load()) == 1

    def test_strips_unknown_keys(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        item = _item()
        item["onclick"] = "alert(1)"
        music_queue.save([item])
        assert "onclick" not in music_queue.load()[0]

    def test_non_string_values_become_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        item = _item()
        item["title"] = {"nested": "object"}
        music_queue.save([item])
        assert music_queue.load()[0]["title"] == ""

    def test_add_dedupes_and_moves_to_end(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        music_queue.add(_item("aaa11111111"))
        music_queue.add(_item("bbb22222222"))
        music_queue.add(_item("aaa11111111", title="again"))
        ids = [i["id"] for i in music_queue.load()]
        assert ids == ["bbb22222222", "aaa11111111"]

    def test_add_keeps_video_and_playlist_with_same_id_apart(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        music_queue.add(_item("same12345678", kind="video"))
        music_queue.add(_item("same12345678", kind="playlist"))
        assert len(music_queue.load()) == 2

    def test_capped_at_max_items(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        music_queue.save([_item("id%08d" % i) for i in range(music_queue.MAX_ITEMS + 25)])
        assert len(music_queue.load()) == music_queue.MAX_ITEMS

    def test_save_rejects_non_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        assert music_queue.save({"not": "a list"}) is False


# ---------------------------------------------------------------------------
# Queue + resolve routes
# ---------------------------------------------------------------------------

class TestQueueRoutes:
    def test_stations_route_carries_queue_and_modes(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        music_queue.save([_item()])
        user_settings.save({"music_source": "youtube", "music_loop_mode": "one",
                            "music_shuffle": True})
        with patch.object(music, "is_online", return_value=True):
            data = json.loads(client.get('/music/stations').data)
        assert data['source'] == 'youtube'
        assert data['loop_mode'] == 'one'
        assert data['shuffle'] is True
        assert len(data['queue']) == 1

    def test_resolve_accepts_a_link(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        with patch.object(music, "urlopen", side_effect=OSError("offline")):
            resp = client.post('/music/resolve', json={'ref': 'https://youtu.be/' + VIDEO_ID})
        assert resp.status_code == 200
        assert json.loads(resp.data)['item']['id'] == VIDEO_ID

    def test_resolve_rejects_junk_with_400(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        resp = client.post('/music/resolve', json={'ref': 'https://vimeo.com/1'})
        assert resp.status_code == 400
        assert json.loads(resp.data)['status'] == 'failure'

    def test_add_route_appends(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        with patch.object(music, "urlopen", side_effect=OSError("offline")):
            resp = client.post('/music/queue/add', json={'ref': VIDEO_ID})
        data = json.loads(resp.data)
        assert data['status'] == 'success'
        assert [i['id'] for i in data['queue']] == [VIDEO_ID]
        assert [i['id'] for i in music_queue.load()] == [VIDEO_ID]

    def test_add_route_rejects_junk(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        resp = client.post('/music/queue/add', json={'ref': 'not a link'})
        assert resp.status_code == 400
        assert music_queue.load() == []

    def test_post_queue_replaces_wholesale(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        music_queue.save([_item("aaa11111111"), _item("bbb22222222")])
        resp = client.post('/music/queue', json={'queue': [_item("bbb22222222")]})
        assert resp.status_code == 200
        assert [i['id'] for i in music_queue.load()] == ["bbb22222222"]

    def test_get_queue(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        music_queue.save([_item()])
        data = json.loads(client.get('/music/queue').data)
        assert len(data['queue']) == 1


# ---------------------------------------------------------------------------
# Source / loop settings
# ---------------------------------------------------------------------------

class TestSourceSettings:
    def test_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        s = user_settings.load()
        assert s["music_source"] == "radio"
        assert s["music_loop_mode"] == "all"
        assert s["music_shuffle"] is False

    def test_source_must_be_known(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"music_source": "youtube"})
        assert user_settings.load()["music_source"] == "youtube"
        user_settings.save({"music_source": "spotify"})
        assert user_settings.load()["music_source"] == "youtube"

    def test_loop_mode_must_be_known(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "script_dir", str(tmp_path))
        user_settings.save({"music_loop_mode": "one"})
        assert user_settings.load()["music_loop_mode"] == "one"
        user_settings.save({"music_loop_mode": "sideways"})
        assert user_settings.load()["music_loop_mode"] == "one"
