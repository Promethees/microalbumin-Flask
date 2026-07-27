"""Tests for the SSE live-session stream (src/live_stream.py, /stream_session).

The stream replaces the browser's 500 ms chart poll and 2 s log poll for the
duration of a run, so the properties that matter here are: rows are pushed once
and only once, a row that is half-written when the generator stats the file is
held back rather than shipped truncated, Turn files are normalised exactly the
way a full fetch normalises them, and the stream closes rather than spinning
forever when the logger exits.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

import live_stream
import state
from main import app


TIME_HEADER = (
    "# Measurement: Absorbance\n"
    "# Unit: %\n"
    "# ConcenUnit: ng/µL\n"
    "Timestamp,Value:1\n"
)
TURN_HEADER = (
    "# Measurement: Absorbance\n"
    "# Unit: %\n"
    "Turn,Value:1\n"
)


@pytest.fixture
def session(tmp_path):
    """A writable script_dir with a log/ folder, as a live session would have."""
    (tmp_path / "log").mkdir()
    with patch.object(state, "script_dir", str(tmp_path)):
        yield tmp_path


def _write(path, text, mode="a"):
    with open(path, mode, encoding="utf-8") as f:
        f.write(text)


def _set_marker(root, csv_path):
    _write(root / "log" / "current_output.txt", str(csv_path), mode="w")


# --- _ByteTail ---------------------------------------------------------------

def test_byte_tail_yields_only_complete_lines(tmp_path):
    """A row still being written must not be shipped truncated."""
    path = tmp_path / "f.txt"
    _write(path, "one\ntwo\nthr", mode="w")
    tail = live_stream._ByteTail(str(path))

    lines, _ = tail.read_lines()
    assert lines == ["one", "two"]

    # The partial third line completes on the next append.
    _write(path, "ee\n")
    lines, _ = tail.read_lines()
    assert lines == ["three"]


def test_byte_tail_never_repeats_a_line(tmp_path):
    path = tmp_path / "f.txt"
    _write(path, "a\n", mode="w")
    tail = live_stream._ByteTail(str(path))
    assert tail.read_lines()[0] == ["a"]
    assert tail.read_lines()[0] == []
    _write(path, "b\n")
    assert tail.read_lines()[0] == ["b"]


def test_byte_tail_reports_truncation_and_restarts(tmp_path):
    """/check_status blanks the log at session end — a shrunk file means restart."""
    path = tmp_path / "f.txt"
    _write(path, "a longer first session\n", mode="w")
    tail = live_stream._ByteTail(str(path))
    tail.read_lines()

    _write(path, "new\n", mode="w")  # truncate + rewrite, shorter
    lines, truncated = tail.read_lines()
    assert truncated is True
    assert lines == ["new"]


def test_byte_tail_detects_a_replaced_file_of_the_same_size(tmp_path):
    """A same-length rewrite leaves the offset where it was, so size alone cannot
    see it — the inode identity is what catches a rename-replace."""
    path = tmp_path / "f.txt"
    other = tmp_path / "other.txt"
    _write(path, "old\n", mode="w")
    tail = live_stream._ByteTail(str(path))
    assert tail.read_lines()[0] == ["old"]

    _write(other, "new\n", mode="w")
    os.replace(str(other), str(path))
    lines, truncated = tail.read_lines()
    assert truncated is True
    assert lines == ["new"]


def test_byte_tail_survives_multibyte_split(tmp_path):
    """A chunk boundary must not land inside a character (the µ of ng/µL)."""
    path = tmp_path / "f.txt"
    raw = "# ConcenUnit: ng/µL\n".encode("utf-8")
    with open(path, "wb") as f:
        f.write(raw[:-4])           # cut mid-line, after the multi-byte char
    tail = live_stream._ByteTail(str(path))
    assert tail.read_lines()[0] == []   # no newline yet, nothing shipped

    with open(path, "ab") as f:
        f.write(raw[-4:])
    assert tail.read_lines()[0] == ["# ConcenUnit: ng/µL"]


# --- _CsvSession -------------------------------------------------------------

def test_csv_session_emits_meta_once_then_rows(session):
    csv_path = session / "run.csv"
    _write(csv_path, TIME_HEADER + "0.0,0.1\n", mode="w")
    _set_marker(session, csv_path)

    s = live_stream._CsvSession()
    meta, rows = s.poll()
    assert meta["filename"] == "run.csv"
    assert meta["num_sources"] == 1
    assert meta["x_axis"] == "time"
    assert meta["unit"] == "%"
    assert meta["metadata"]["Measurement"] == "Absorbance"
    assert rows == [{"Timestamp": "0.0", "Value:1": "0.1"}]

    # Header is written once, so meta never repeats.
    _write(csv_path, "1.0,0.2\n")
    meta, rows = s.poll()
    assert meta is None
    assert rows == [{"Timestamp": "1.0", "Value:1": "0.2"}]

    # Nothing appended -> nothing pushed.
    assert s.poll() == (None, [])


def test_csv_session_renames_turn_to_timestamp(session):
    """Mirror file.get_dynamic_data: a Turn file's X key is renamed on read so the
    whole Timestamp-keyed client pipeline is unchanged (Rule 2.27)."""
    csv_path = session / "turns.csv"
    _write(csv_path, TURN_HEADER + "1,0.5\n", mode="w")
    _set_marker(session, csv_path)

    meta, rows = live_stream._CsvSession().poll()
    assert meta["x_axis"] == "turn"
    assert rows == [{"Timestamp": "1", "Value:1": "0.5"}]


def test_csv_session_blanks_empty_cells(session):
    """Empty cells become "NONE", as a full fetch would return them."""
    csv_path = session / "run.csv"
    _write(csv_path, TIME_HEADER + "0.0,\n", mode="w")
    _set_marker(session, csv_path)

    _, rows = live_stream._CsvSession().poll()
    assert rows == [{"Timestamp": "0.0", "Value:1": "NONE"}]


def test_csv_session_multi_source_counted(session):
    csv_path = session / "run.csv"
    _write(csv_path, "# Unit: %\nTimestamp,Value:1,Value:2,Value:3\n0.0,1,2,3\n", mode="w")
    _set_marker(session, csv_path)

    meta, rows = live_stream._CsvSession().poll()
    assert meta["num_sources"] == 3
    assert rows == [{"Timestamp": "0.0", "Value:1": "1", "Value:2": "2", "Value:3": "3"}]


def test_csv_session_waits_for_the_marker(session):
    """Before the logger has the device's header the marker is blank — "still
    writing", not an error (same state /api/current_output reports as 204)."""
    _write(session / "log" / "current_output.txt", "", mode="w")
    assert live_stream._CsvSession().poll() == (None, [])


def test_csv_session_follows_a_new_file(session):
    """A second run writes a new CSV; the tail must re-derive the header."""
    first = session / "a.csv"
    _write(first, TIME_HEADER + "0.0,0.1\n", mode="w")
    _set_marker(session, first)
    s = live_stream._CsvSession()
    s.poll()

    second = session / "b.csv"
    _write(second, TURN_HEADER + "1,0.9\n", mode="w")
    _set_marker(session, second)
    meta, rows = s.poll()
    assert meta["filename"] == "b.csv"
    assert meta["x_axis"] == "turn"
    assert rows == [{"Timestamp": "1", "Value:1": "0.9"}]


# --- iter_session_events -----------------------------------------------------

def _events(frames):
    """Parse SSE frames into (event_name, payload) pairs, skipping heartbeats."""
    out = []
    for frame in frames:
        if frame.startswith(":"):
            continue
        name = frame.split("\n", 1)[0].replace("event: ", "")
        data = frame.split("data: ", 1)[1].strip()
        out.append((name, json.loads(data)))
    return out


def test_stream_ends_immediately_when_nothing_is_running(session):
    with patch.object(state, "process", None):
        frames = list(live_stream.iter_session_events())
    assert _events(frames) == [("end", {"reason": "not_running"})]


def test_stream_pushes_log_rows_then_ends(session):
    csv_path = session / "run.csv"
    _write(csv_path, TIME_HEADER + "0.0,0.1\n", mode="w")
    _set_marker(session, csv_path)
    log_path = session / "log" / "script_logs.txt"
    _write(log_path, "Connected to PyBadge at /dev/x\n", mode="w")

    # Alive for the first liveness check, gone after — so the generator pushes
    # the pending data, then drains and closes instead of spinning.
    proc = MagicMock()
    proc.poll.side_effect = [None, 0, 0, 0, 0, 0, 0, 0]

    with patch.object(state, "process", proc), \
         patch.object(state, "log_file", str(log_path)), \
         patch.object(live_stream, "POLL_INTERVAL", 0), \
         patch.object(live_stream, "END_GRACE_SECONDS", 0):
        events = _events(list(live_stream.iter_session_events()))

    names = [name for name, _ in events]
    assert names[-1] == "end"
    assert events[-1][1]["reason"] == "session_ended"

    by_name = {name: payload for name, payload in events}
    assert "Connected to PyBadge" in by_name["log"]["chunk"]
    assert by_name["meta"]["filename"] == "run.csv"
    assert by_name["rows"]["rows"] == [{"Timestamp": "0.0", "Value:1": "0.1"}]


def test_stream_marks_the_first_log_frame_as_a_replay(session):
    """EventSource reconnects transparently and the new generator re-reads the log
    from the top, so the first frame of a connection must be flagged as a replay
    the client REPLACES with — appending it would duplicate the whole session."""
    log_path = session / "log" / "script_logs.txt"
    _write(log_path, "line one\n", mode="w")
    _write(session / "log" / "current_output.txt", "", mode="w")

    proc = MagicMock()
    # Alive long enough for two passes over the log, then gone.
    proc.poll.side_effect = [None, None, 0, 0, 0, 0]

    with patch.object(state, "process", proc), \
         patch.object(state, "log_file", str(log_path)), \
         patch.object(live_stream, "POLL_INTERVAL", 0), \
         patch.object(live_stream, "END_GRACE_SECONDS", 0):
        gen = live_stream.iter_session_events()
        first = next(gen)
        _write(log_path, "line two\n")
        rest = list(gen)

    logs = [p for name, p in _events([first] + rest) if name == "log"]
    assert logs[0] == {"chunk": "line one\n", "reset": True}
    assert logs[1] == {"chunk": "line two\n", "reset": False}


def test_stream_route_sets_event_stream_headers():
    app.config["TESTING"] = True
    with app.test_client() as client:
        with patch.object(state, "process", None):
            rv = client.get("/stream_session")
    assert rv.status_code == 200
    assert rv.mimetype == "text/event-stream"
    assert rv.headers["Cache-Control"].startswith("no-cache")
    assert b"not_running" in rv.data


def test_marker_path_matches_the_logger_contract(session):
    """The stream reads the same marker /api/current_output and the logger use."""
    assert live_stream._marker_path() == os.path.join(
        str(session), "log", "current_output.txt")
