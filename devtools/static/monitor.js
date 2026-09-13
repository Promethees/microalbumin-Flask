/* Developer performance monitor — page client.
 *
 * Polls GET /__dev/monitor/metrics and repaints. Polling rather than SSE on
 * purpose: an unconsumed stream_with_context response leaves a request context
 * pushed and breaks the NEXT request (Rule.md §2.37), and a monitor that can
 * damage the process it is monitoring is worse than one that refreshes a second
 * late. The same reasoning is why the poll pauses itself on an error instead of
 * hammering a struggling app.
 *
 * No i18n here by design — this is a developer tool (see devtools/README.md).
 */
(function () {
    'use strict';

    var BASE = '/__dev/monitor';

    // Same key the app's theme toggle writes (static/script/init.js).
    try {
        if (localStorage.getItem('theme') === 'dark') {
            document.body.classList.add('dark');
        }
    } catch (e) { /* private mode: light is a fine default */ }

    var $ = function (id) { return document.getElementById(id); };
    var timer = null;
    var tracingOn = false;

    function text(id, value) {
        var el = $(id);
        if (el) { el.textContent = value; }
    }

    function flag(id, cls, on) {
        var el = $(id);
        if (!el || !el.parentElement) { return; }
        el.parentElement.classList.toggle(cls, !!on);
    }

    function bytes(n) {
        if (n === null || n === undefined) { return '—'; }
        var units = ['B', 'KB', 'MB', 'GB'];
        var i = 0;
        var v = n;
        while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
        return (i === 0 ? v : v.toFixed(1)) + ' ' + units[i];
    }

    function ms(n) {
        return (n === null || n === undefined) ? '—' : n.toFixed(1) + ' ms';
    }

    function num(n) {
        return (n === null || n === undefined) ? '—' : String(n);
    }

    // Every string that reaches innerHTML goes through this. Route names and
    // allocation sites are the app's own data, not a user's, but they are still
    // text from outside this file being rendered inside the app's origin — and
    // this page is the one place in the process where a stray '<' would run.
    function esc(value) {
        return String(value === null || value === undefined ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function duration(seconds) {
        var s = Math.floor(seconds);
        var h = Math.floor(s / 3600);
        var m = Math.floor((s % 3600) / 60);
        return (h ? h + 'h ' : '') + (h || m ? m + 'm ' : '') + (s % 60) + 's';
    }

    function shortPath(file) {
        // The interesting half of an allocation site is the tail, and every
        // frame shares the same long prefix.
        var parts = String(file).split('/');
        return parts.slice(-2).join('/');
    }

    function error(message) {
        var el = $('m-error');
        el.textContent = message || '';
        el.hidden = !message;
    }

    // ── painters ────────────────────────────────────────────────────────
    function paintProcess(p) {
        text('m-proc-source', p.source === 'psutil' ? '' : '(psutil absent — stdlib fallback)');
        text('m-rss', p.rss_bytes === null && p.rss_peak_bytes !== undefined
            ? bytes(p.rss_peak_bytes) + ' peak'
            : bytes(p.rss_bytes));
        text('m-vms', bytes(p.vms_bytes));
        text('m-cpu', p.cpu_percent === null ? '—' : p.cpu_percent.toFixed(1) + ' %');
        text('m-threads', num(p.threads));
        text('m-fds', num(p.open_fds));
        text('m-pid', num(p.pid));

        var gc = p.gc || {};
        text('m-gc-collections', (gc.collections || []).join(' / ') || '—');
        var uncollectable = (gc.uncollectable || []).reduce(function (a, b) { return a + b; }, 0);
        text('m-gc-uncollectable', String(uncollectable));
        text('m-gc-garbage', num(gc.garbage));
        // Anything in gc.garbage or an uncollectable count above zero is a
        // reference cycle the collector gave up on — the one GC number that is
        // a defect rather than a reading.
        flag('m-gc-uncollectable', 'is-bad', uncollectable > 0);
        flag('m-gc-garbage', 'is-bad', gc.garbage > 0);
    }

    function paintAllocations(tm) {
        tracingOn = !!tm.enabled;
        var btn = $('m-trace');
        btn.textContent = 'Tracing: ' + (tracingOn ? 'on' : 'off');
        if (!tracingOn) {
            text('m-tm-summary', tm.owner ? '(stopped)' : '');
            $('m-tm-rows').innerHTML =
                '<tr><td colspan="3" class="devmon-empty">Tracing off.</td></tr>';
            return;
        }
        text('m-tm-summary', bytes(tm.current_bytes) + ' traced · ' +
            bytes(tm.peak_bytes) + ' peak · started by ' + (tm.owner || '?'));
        var rows = (tm.top || []).map(function (s) {
            return '<tr><td class="devmon-site">' + esc(shortPath(s.file)) + ':' + esc(s.line) +
                '</td><td class="devmon-r">' + bytes(s.size_bytes) +
                '</td><td class="devmon-r">' + esc(s.count) + '</td></tr>';
        });
        $('m-tm-rows').innerHTML = rows.join('') ||
            '<tr><td colspan="3" class="devmon-empty">No allocations traced yet.</td></tr>';
    }

    function paintHttp(http) {
        text('m-http-total', num(http.total));
        text('m-http-errors', num(http.errors));
        text('m-http-inflight', num(http.in_flight));
        flag('m-http-errors', 'is-bad', http.errors > 0);
        var rows = (http.routes || []).map(function (r) {
            return '<tr' + (r.errors ? ' class="is-bad"' : '') + '>' +
                '<td class="devmon-site">' + esc(r.rule || r.endpoint) + '</td>' +
                '<td class="devmon-r">' + esc(r.count) + '</td>' +
                '<td class="devmon-r">' + esc(r.errors) + '</td>' +
                '<td class="devmon-r">' + ms(r.mean_ms) + '</td>' +
                '<td class="devmon-r">' + ms(r.p95_ms) + '</td>' +
                '<td class="devmon-r">' + ms(r.max_ms) + '</td></tr>';
        });
        $('m-http-rows').innerHTML = rows.join('') ||
            '<tr><td colspan="6" class="devmon-empty">No requests yet.</td></tr>';
    }

    function paintDevice(d) {
        // Who owns the port is the first thing to read: a flat device readout
        // during a session is correct, not broken (Rule.md §2.35).
        text('m-dev-owner', d.session_owns_port
            ? '— a reading session owns the port'
            : (d.link_connected ? '— control link holds the port' : '— port idle'));
        text('m-dev-port', d.port || '—');
        text('m-dev-in', bytes(d.bytes_in));
        text('m-dev-out', bytes(d.bytes_out));
        text('m-dev-lines', num(d.lines_in));
        text('m-dev-rate', d.lines_per_sec.toFixed(2));
        text('m-dev-timeouts', num(d.read_timeouts));
        text('m-dev-malformed', num(d.malformed_lines));
        text('m-dev-unmatched', num(d.lines_unmatched));
        text('m-dev-connects', num(d.connects));
        text('m-dev-openfail', num(d.connect_failures));
        flag('m-dev-malformed', 'is-bad', d.malformed_lines > 0);
        flag('m-dev-openfail', 'is-warn', d.connect_failures > 0);
        flag('m-dev-port', 'is-live', !!d.port);

        var ping = d.ping_probe || {};
        text('m-dev-ping', ping.count
            ? ms(ping.last_ms) + ' · ' + ping.count + ' probes, ' + ping.errors + ' failed'
            : '—');
        flag('m-dev-ping', 'is-warn', ping.errors > 0);

        var cmd = d.command || {};
        text('m-dev-cmd', cmd.count
            ? ms(cmd.mean_ms) + ' mean · ' + ms(cmd.p95_ms) + ' p95 · ' + cmd.errors + ' timeouts'
            : '—');
        flag('m-dev-cmd', 'is-warn', cmd.errors > 0);

        var log = d.logger || {};
        text('m-log-pid', log.running ? num(log.pid) : '—');
        text('m-log-cpu', log.cpu_percent === undefined ? '—' : log.cpu_percent.toFixed(1) + ' %');
        text('m-log-rss', bytes(log.rss_bytes));
        flag('m-log-pid', 'is-live', !!log.running);
    }

    function paintStream(s) {
        text('m-sse-active', num(s.clients_active));
        text('m-sse-total', num(s.clients_total));
        text('m-sse-frames', num(s.frames));
        text('m-sse-bytes', bytes(s.bytes_pushed));
        text('m-sse-logoff', num(s.last_log_offset));
        text('m-sse-csvoff', num(s.last_csv_offset));
        flag('m-sse-active', 'is-live', s.clients_active > 0);
        text('m-sse-path', s.last_csv_path ? 'Active CSV: ' + s.last_csv_path : '');
    }

    // ── poll ────────────────────────────────────────────────────────────
    function refresh() {
        return fetch(BASE + '/metrics', { cache: 'no-store' })
            .then(function (r) {
                if (!r.ok) { throw new Error('HTTP ' + r.status); }
                return r.json();
            })
            .then(function (data) {
                error('');
                text('m-uptime', duration(data.uptime_sec));
                paintProcess(data.process);
                paintAllocations(data.process.tracemalloc || {});
                paintHttp(data.http);
                paintDevice(data.device);
                paintStream(data.stream);
            })
            .catch(function (err) {
                // Stop the timer rather than pile requests onto an app that is
                // already unhappy; the interval select restarts it.
                schedule(0);
                error('Metrics unavailable (' + err.message + '). Poll paused — ' +
                      'pick an interval to resume.');
            });
    }

    function schedule(interval) {
        if (timer) { clearInterval(timer); timer = null; }
        if (interval > 0) { timer = setInterval(refresh, interval); }
    }

    function control(action) {
        return fetch(BASE + '/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: action })
        }).then(refresh);
    }

    $('m-reset').addEventListener('click', function () { control('reset'); });
    $('m-trace').addEventListener('click', function () {
        control(tracingOn ? 'trace_off' : 'trace_on');
    });
    $('m-interval').addEventListener('change', function (e) {
        var value = parseInt(e.target.value, 10) || 0;
        schedule(value);
        if (value > 0) { refresh(); }
    });

    refresh();
    schedule(1000);
}());
