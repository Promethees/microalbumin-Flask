// Live reading session over Server-Sent Events.
//
// A running capture used to reach the browser through two unrelated clocks: a
// 500 ms loop that re-fetched and re-rendered the entire active CSV, and a 2 s
// loop that re-fetched the entire log file and counted "Received:" matches to
// notice a new row. Nothing connected either clock to the event that actually
// produced a measurement, so in manual point mode the "Measure now" button could
// stay disabled for ~2 s after its row was already on disk, and the chart
// rebuilt itself twice a second whether or not anything had changed.
//
// This module opens /stream_session for the duration of a run and lets the
// server push what changed (see src/live_stream.py). Rows arrive as rows, so the
// re-render and the button re-arm both happen because the measurement landed.
//
// Fallback is automatic and requires no detection of its own: the polls in
// index.js and cdc-logging.js simply ask isLiveStreamActive() and keep running
// whenever the stream is not carrying the session — a browser without
// EventSource, a stream that never opened, or a reconnect gap all just fall back
// to the old behaviour for as long as they last.

let _liveES = null;
// True only while the stream has actually delivered something. Kept false during
// the connecting window and cleared on error, which is what makes the fallback
// polls resume by themselves rather than needing a separate health check.
let _liveStreamCarrying = false;
// Session-scoped accumulators. `_liveRows` mirrors what the server has appended
// so far; the chart is re-rendered from it instead of re-fetching the CSV.
let _liveMeta = null;
let _liveRows = [];
let _liveLogText = '';
// High-water mark of rows already announced via onNewDataPoint(), counted across
// the whole run rather than per connection. EventSource reconnects transparently
// and the new server-side generator replays the CSV from its header, so without
// this a dropped connection would re-announce every row already recorded —
// re-arming "Measure now" and corrupting the session timer's interval estimate.
let _liveRowsAnnounced = 0;
// Coalesces re-renders: an auto run at a short interval can deliver several rows
// inside one frame, and the render path rebuilds the whole chart.
let _liveRenderTimer = null;
const LIVE_RENDER_MIN_MS = 200;

function isLiveStreamActive() {
    return _liveStreamCarrying;
}

function liveStreamEnabled() {
    if (typeof EventSource === 'undefined') return false;
    if (typeof USER_SETTINGS === 'undefined') return true;
    return USER_SETTINGS.live_stream_enabled !== false;
}

// Called when a run starts (runScript success). Safe to call twice — an already
// open stream is left alone.
function startLiveStream() {
    if (!liveStreamEnabled() || _liveES) return;
    _liveMeta = null;
    _liveRows = [];
    _liveLogText = '';
    _liveRowsAnnounced = 0;
    try {
        _liveES = new EventSource('/stream_session');
    } catch (err) {
        console.warn('live stream unavailable, falling back to polling:', err);
        _liveES = null;
        return;
    }

    _liveES.addEventListener('log', (e) => {
        const payload = _liveParse(e);
        if (!payload || !payload.chunk) return;
        _liveStreamCarrying = true;
        // `reset` marks a connection's first log frame, which carries the session
        // from the top — appending it after a reconnect would duplicate the log.
        _liveLogText = payload.reset ? payload.chunk : _liveLogText + payload.chunk;
        $text('log-display', _liveLogText);
        // The notice matchers read the whole session log, not the delta — a
        // phase line delivered in an earlier chunk must still count.
        applyLogText(_liveLogText, { countDataPoints: false });
    });

    _liveES.addEventListener('meta', (e) => {
        const payload = _liveParse(e);
        if (!payload) return;
        _liveStreamCarrying = true;
        // A header is re-read whenever a connection starts, so this fires both for
        // a genuinely new CSV and for a reconnect replaying the current one.
        // Either way the row array is rebuilt from what follows.
        _liveMeta = payload;
        _liveRows = [];
    });

    _liveES.addEventListener('rows', (e) => {
        const payload = _liveParse(e);
        if (!payload || !Array.isArray(payload.rows) || !payload.rows.length) return;
        _liveStreamCarrying = true;
        payload.rows.forEach(row => _liveRows.push(row));
        // Announce only rows past the high-water mark. On a reconnect the batch
        // is a replay of rows already counted, so it re-populates the chart
        // without pretending measurements just happened.
        const fresh = _liveRows.length - _liveRowsAnnounced;
        if (fresh > 0) {
            _liveRowsAnnounced = _liveRows.length;
            // Keep the fallback path's counter aligned, so a mid-session drop to
            // polling does not replay every row as "new".
            _prevDataPointCount += fresh;
            // One per row: this is what re-arms "Measure now" in manual capture
            // and what drives the session timer's interval estimate.
            for (let i = 0; i < fresh; i++) onNewDataPoint();
        }
        _scheduleLiveRender();
    });

    _liveES.addEventListener('end', () => {
        stopLiveStream();
        // /check_status owns the run-end transition (why it ended, clearing the
        // log). The stream just gets it there without waiting out a poll tick.
        if (typeof checkScriptStatus === 'function') checkScriptStatus();
    });

    _liveES.onerror = () => {
        // EventSource reconnects on its own; drop the flag so the fallback polls
        // cover the gap and pick the stream back up on the next message.
        _liveStreamCarrying = false;
        if (_liveES && _liveES.readyState === EventSource.CLOSED) stopLiveStream();
    };
}

function stopLiveStream() {
    if (_liveRenderTimer) { clearTimeout(_liveRenderTimer); _liveRenderTimer = null; }
    if (_liveES) {
        try { _liveES.close(); } catch (_) { /* already closed */ }
        _liveES = null;
    }
    _liveStreamCarrying = false;
}

function _liveParse(e) {
    try {
        return JSON.parse(e.data);
    } catch (err) {
        console.warn('live stream: bad payload', err);
        return null;
    }
}

function _scheduleLiveRender() {
    if (_liveRenderTimer) return;
    _liveRenderTimer = setTimeout(() => {
        _liveRenderTimer = null;
        renderLiveRows();
    }, LIVE_RENDER_MIN_MS);
}

// Is the file the user has selected the one this session is writing?
// Only then does a pushed row belong on the chart — the user may well be looking
// at an older measurement while a capture runs.
function liveFileIsSelected() {
    if (!_liveMeta || !AppState.currentFile) return false;
    if (AppState.currentFile !== _liveMeta.filename) return false;
    const norm = p => String(p || '').replace(/[\\/]+$/, '').replace(/\\/g, '/');
    return norm(AppState.currentDirectory) === norm(_liveMeta.dir);
}

// Re-render the chart from the rows pushed so far.
//
// Deliberately reuses processResponse() rather than appending to the Chart.js
// datasets directly: the render path also recomputes the moving-average window,
// the per-source split, the kinetics analysis and the derived concentration, all
// of which depend on the full series. Feeding it a synthetic response keeps one
// rendering implementation for live and loaded files. What the stream removes is
// the HTTP round trip and the full CSV reparse behind it, not the redraw.
function renderLiveRows() {
    if (!liveFileIsSelected() || !_liveRows.length) return;
    if (typeof processResponse !== 'function') return;
    processResponse({
        data: _liveRows,
        metadata: _liveMeta.metadata,
        unit: _liveMeta.unit,
        num_sources: _liveMeta.num_sources,
        x_axis: _liveMeta.x_axis,
        error: null,
    }, AppState.currentJSONcontent);
}

// Selecting a file mid-run (notably via "View live data") must show the rows the
// stream already delivered, without waiting for the next one to arrive.
function refreshLiveSelection() {
    if (_liveStreamCarrying && liveFileIsSelected() && _liveRows.length) renderLiveRows();
}
