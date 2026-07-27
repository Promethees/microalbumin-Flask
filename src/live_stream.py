"""Server-sent-events tail of a live reading session.

Before this module the browser learned about new measurements by polling: a
500 ms loop re-fetched the whole active CSV (``/get_data`` → full reparse → full
chart rebuild) and a 2 s loop re-fetched the whole log file (``/get_logs``) and
counted ``Received:`` matches with a regex to notice a new row. Both clocks ran
whether or not a byte had changed, neither was tied to the event that actually
produced data, and in manual point mode the "Measure now" button stayed disabled
for up to 2 s after its row had already landed on disk.

``/stream_session`` replaces both. One generator tails the two files the session
writes — the log (``state.log_file``) and the active CSV (whose path the logger
publishes in ``log/current_output.txt``) — by byte offset, and pushes only what
was appended. The poll does not disappear entirely (a plain file append has no
OS-level notification without a watcher dependency), but it moves server-side to
two ``os.stat`` calls per tick instead of an HTTP round trip that re-read every
CSV in the folder.

Events emitted (all ``data:`` payloads are JSON):

``meta``    once per CSV, as soon as the header lands: file identity plus the
            metadata/num_sources/x_axis the client needs to render.
``rows``    one or more newly appended data rows, already normalised the way
            ``file.get_dynamic_data`` normalises them (``Turn`` → ``Timestamp``,
            empty → ``NONE``) so the client can feed them to the existing render
            path unchanged.
``log``     newly appended log text.
``end``     the logger process is gone. The client closes the stream and lets
            ``/check_status`` (which owns the run-end state machine, including
            why it ended and clearing the log) perform the actual UI transition.

Truncation is tolerated on both files: ``/check_status`` blanks the log at the
end of a session and a new run writes a new CSV, so a size that went backwards
means "start over", not "corrupt".
"""

import csv
import json
import os
import time

import state
from file_path import parse_csv_metadata, timeseries_x_column

# How often the generator stats the two session files. Sized against the
# firmware's ~0.174 s loop period: fast enough that a row is pushed within one
# device tick, cheap enough (two stat calls) to be irrelevant next to the
# per-request file reads it replaces.
POLL_INTERVAL = 0.12

# A comment line is written at least this often when nothing else is happening.
# This is the only way a generator blocked on an idle session notices that the
# browser navigated away — the write fails and the generator is closed.
HEARTBEAT_SECONDS = 15.0

# After the logger exits, keep draining for this long so the final rows and log
# lines it flushed on the way out are delivered before the stream closes.
END_GRACE_SECONDS = 1.0


def _sse(event, payload):
    return "event: {}\ndata: {}\n\n".format(
        event, json.dumps(payload, ensure_ascii=False))


def _marker_path():
    """Path of the live-CSV marker the logger writes once it has the header.

    Kept in sync with ``log_cdc_data.py`` and
    ``hardware_routes.clear_current_output_marker``.
    """
    return os.path.join(state.script_dir, 'log', 'current_output.txt')


def _read_marker():
    """Return the active CSV path from the marker, or None while it is unwritten.

    An absent or blank marker means the logger has not received the device's
    header yet — the same "still writing" state ``/api/current_output`` reports
    as 404/204.
    """
    try:
        path = _marker_path()
        if not os.path.isfile(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        return os.path.normpath(content) if content else None
    except OSError:
        return None


class _ByteTail:
    """Incremental line reader over a file that is being appended to.

    Tracks a byte offset rather than using text-mode ``seek``/``tell`` (whose
    values are opaque) and only ever yields lines terminated by a newline, so a
    row that is half-written when we stat the file is held back until it is
    complete. Splitting on ``b'\\n'`` before decoding also means a chunk boundary
    can never land inside a multi-byte character (the ``µ`` of ``ng/µL`` shows up
    in the metadata block).
    """

    def __init__(self, path=None):
        self.path = path
        self.offset = 0
        self.buf = b''
        self.ident = None

    def reset(self, path=None):
        self.path = path
        self.offset = 0
        self.buf = b''
        self.ident = None

    def read_lines(self):
        """Return the complete lines appended since the last call.

        Returns ``(lines, truncated)``. ``truncated`` is True when the file
        started over — it shrank (blanked in place, as ``clear_logs`` does) or a
        different file now occupies the path (rename-replace, caught by the
        inode/device identity). Both are normal here, not errors.

        Note the one case this cannot see: a same-length rewrite of the same
        inode. Neither session file does that — the log is blanked to zero and a
        new run writes a new CSV path — so detecting it is not worth stat-ing
        content.
        """
        if not self.path:
            return [], False
        try:
            st = os.stat(self.path)
        except OSError:
            return [], True

        size = st.st_size
        ident = (st.st_dev, st.st_ino)
        truncated = False
        if self.ident is not None and ident != self.ident:
            # A different file is at this path now: start from its top.
            self.offset = 0
            self.buf = b''
            truncated = True
        self.ident = ident
        if size < self.offset:
            # Rewritten in place (the log is blanked at session end).
            self.offset = 0
            self.buf = b''
            truncated = True
        if size == self.offset:
            return [], truncated

        try:
            with open(self.path, 'rb') as f:
                f.seek(self.offset)
                chunk = f.read(size - self.offset)
        except OSError:
            return [], truncated

        self.offset += len(chunk)
        self.buf += chunk
        if b'\n' not in self.buf:
            return [], truncated

        *complete, self.buf = self.buf.split(b'\n')
        return [line.decode('utf-8', 'replace') for line in complete], truncated


class _CsvSession:
    """Header-aware tail of the CSV the running logger is appending rows to.

    The metadata block and header line are written once, at the top of the file,
    so they are parsed exactly once per session and shipped as the ``meta``
    event; everything after is a data row. Row normalisation mirrors
    ``file.get_dynamic_data`` — a Turn file's ``Turn`` key is renamed to
    ``Timestamp`` and empties become ``"NONE"`` — so the client can feed these
    rows straight into the same render path a full fetch feeds.
    """

    def __init__(self):
        self.tail = _ByteTail()
        self.meta_lines = []
        self.headers = None
        self.x_axis = 'time'
        self.pending_meta = None

    def _adopt(self, path):
        self.tail.reset(path)
        self.meta_lines = []
        self.headers = None
        self.x_axis = 'time'
        self.pending_meta = None

    def poll(self):
        """Return ``(meta_or_None, rows)`` for whatever was appended since the
        last call. ``meta`` is non-None only on the tick the header completes."""
        path = _read_marker()
        if not path:
            return None, []
        if path != self.tail.path:
            self._adopt(path)

        lines, truncated = self.tail.read_lines()
        if truncated and self.headers is not None:
            # The active CSV cannot legitimately shrink; if it did, the file was
            # replaced under us, so re-derive the header from the top.
            self._adopt(path)
            lines, _ = self.tail.read_lines()
        if not lines:
            return None, []

        meta_event = None
        data_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if self.headers is None:
                if stripped.startswith('#'):
                    self.meta_lines.append(stripped)
                    continue
                self.headers = [h.strip() for h in next(csv.reader([line]))]
                self.x_axis = ('turn' if timeseries_x_column(",".join(self.headers)) == 'Turn'
                               else 'time')
                metadata = parse_csv_metadata(self.meta_lines)
                dirpath, filename = os.path.split(self.tail.path)
                meta_event = {
                    'full_path': self.tail.path,
                    'dir': dirpath,
                    'filename': filename,
                    'metadata': metadata,
                    'unit': next((metadata[n] for n in ('Unit', 'MeasUnit')
                                  if n in metadata), "NONE"),
                    'num_sources': sum(1 for h in self.headers if h.startswith('Value:')),
                    'x_axis': self.x_axis,
                }
                continue
            data_lines.append(line)

        return meta_event, self._parse_rows(data_lines)

    def _parse_rows(self, data_lines):
        if not data_lines or not self.headers:
            return []
        rows = []
        reader = csv.DictReader(data_lines, fieldnames=self.headers)
        for row in reader:
            normalised = {}
            for key, value in row.items():
                if key is None:
                    continue  # extra columns beyond the header — ignore
                if self.x_axis == 'turn' and key == 'Turn':
                    key = 'Timestamp'
                normalised[key] = value if value not in (None, "") else "NONE"
            rows.append(normalised)
        return rows


def _session_running():
    return state.process is not None and state.process.poll() is None


def iter_session_events():
    """Yield SSE frames for the running session until it ends or the client leaves.

    Terminates on three conditions: the logger exits (after a short drain so its
    final rows are not lost), the client disconnects (the heartbeat write raises
    and the generator is closed), or there was no session to begin with.
    """
    if not _session_running():
        yield _sse('end', {'reason': 'not_running'})
        return

    log_tail = _ByteTail(state.log_file)
    # Every connection starts from the top of both files — a page reloaded
    # mid-run needs the session so far, and EventSource's own reconnect creates a
    # fresh generator that cannot know what the previous one delivered. That
    # makes the first frame of each kind a REPLAY, which the client must replace
    # with rather than append to: `reset` marks it, and the CSV's `meta` (always
    # re-emitted, since the header is re-read) plays the same role for rows.
    csv_session = _CsvSession()
    log_replayed = False
    last_beat = time.time()
    ended_at = None

    while True:
        sent = False

        log_lines, _ = log_tail.read_lines()
        if log_lines:
            yield _sse('log', {'chunk': "\n".join(log_lines) + "\n",
                               'reset': not log_replayed})
            log_replayed = True
            sent = True

        meta_event, rows = csv_session.poll()
        if meta_event:
            yield _sse('meta', meta_event)
            sent = True
        if rows:
            yield _sse('rows', {'rows': rows, 'x_axis': csv_session.x_axis})
            sent = True

        if ended_at is not None:
            if time.time() - ended_at >= END_GRACE_SECONDS:
                yield _sse('end', {'reason': 'session_ended'})
                return
        elif not _session_running():
            # Drain whatever the logger flushed on its way out before closing.
            ended_at = time.time()

        now = time.time()
        if sent:
            last_beat = now
        elif now - last_beat >= HEARTBEAT_SECONDS:
            # Comment frame: ignored by EventSource, but the write is what
            # surfaces a client that has gone away.
            yield ": ping\n\n"
            last_beat = now

        time.sleep(POLL_INTERVAL)
