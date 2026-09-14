"""Counter store and process sampler for the developer performance monitor.

Everything here is process-local and in-memory: the monitor is a live readout,
not a logger, so nothing is written to disk and nothing survives a restart.

Two properties this module exists to keep:

  * **Bounded.** Latency is kept as a ring of the last ``SAMPLE_WINDOW``
    observations per key, never a growing list — a monitor that leaks is worse
    than no monitor.
  * **Cheap under a lock.** Every recorder is a few integer adds inside one
    short ``threading.Lock``; the percentile/mean arithmetic happens on
    ``snapshot()``, which runs once per poll rather than once per event.
  * **Undisturbing.** ``snapshot()`` runs once a second inside a request
    handler, so nothing in it may walk the heap, block on psutil, or wait on a
    lock some other component holds while it talks to the device. A reading
    that changes what it is reading is not a reading.

See ``devtools/README.md`` for what each field means and how to read it.
"""

import gc
import os
import sys
import threading
import time
from collections import deque

try:                                    # Optional — see requirements-dev.txt.
    import psutil                       # type: ignore
except Exception:                       # pragma: no cover - absence is the path we degrade to
    psutil = None

try:
    import resource                     # POSIX only; absent on Windows.
except Exception:                       # pragma: no cover
    resource = None

# Last N latency samples kept per key. 256 is ~4 minutes of a 1 Hz poll and a
# few seconds of a busy route — enough for a stable p95, small enough to forget.
SAMPLE_WINDOW = 256

# tracemalloc frames captured per allocation. 1 is deliberate: the top-N table
# names the allocation *site*, and deeper tracebacks multiply the tracing cost
# without changing which line is at the top.
TRACEMALLOC_FRAMES = 1

# Rows in the tracemalloc top-N table.
TRACEMALLOC_TOP = 12

# ── Memory history ──────────────────────────────────────────────────────────
# The escalation chart. Sampled by a background thread rather than by the page's
# poll, because the question it answers — "did this process climb overnight" —
# is about the hours when nobody had the tab open.
MEMORY_SAMPLE_SEC = 5.0
MEMORY_HISTORY_SPAN_SEC = 4 * 3600
MEMORY_HISTORY_MAX = int(MEMORY_HISTORY_SPAN_SEC / MEMORY_SAMPLE_SEC)   # 2880
# Points sent to the page. The series is bucketed down to this, never strided:
# a stride drops whichever samples it lands between, and the two features worth
# seeing here — a spike and a rising floor — are exactly what a stride hides.
MEMORY_MAX_POINTS = 240
# No verdict before this many samples (2 minutes at the default cadence). A
# slope fitted to four points of startup noise is not a leak report.
MEMORY_MIN_SAMPLES = 24
# Heuristics, and labelled as such on the page. They are a starting point for
# "look at this", not a specification — calibrate them against your own baseline
# before trusting them (devtools/README.md).
MEMORY_RISE_WARN_MB_H = 5.0
MEMORY_RISE_BAD_MB_H = 20.0
# Samples from the first ``MEMORY_WARMUP_SEC`` of the process are charted but
# excluded from the verdict. A fresh interpreter is not in steady state: it
# compiles templates, loads the i18n catalogs and fills its file-metadata caches
# on first use, and that ramp is memory deliberately kept — indistinguishable,
# by any of the numbers below, from a leak. Measured on this app, RSS climbs
# ~6 MB over the first three minutes and then sits flat.
MEMORY_WARMUP_SEC = 120.0

# A rising *floor* is what separates a leak from a sawtooth: peaks move with
# whatever the app is doing, but the low-water mark between them only climbs if
# something is being kept.
MEMORY_FLOOR_RISE_MB = 2.0

_MB = 1024.0 * 1024.0


def _pct(samples, fraction):
    """Nearest-rank percentile over an unsorted sample sequence (ms)."""
    if not samples:
        return None
    ordered = sorted(samples)
    index = int(round(fraction * (len(ordered) - 1)))
    return round(ordered[index], 3)


def _mean(samples):
    return round(sum(samples) / len(samples), 3) if samples else None


def _bucket_memory(points, max_points):
    """Reduce a (t, rss, traced) series to at most ``max_points`` buckets.

    Each bucket becomes ``[t, avg, min, max, traced_avg]`` so the page can draw
    a min/max band under the average line. That band is the whole point: a
    sawtooth and a staircase have the same average slope over a short window and
    are told apart by whether the *bottom* of the band moves.

    Samples whose RSS is ``None`` (the psutil-free fallback) are dropped rather
    than plotted as zero.
    """
    usable = [pt for pt in points if pt[1] is not None]
    if not usable:
        return []
    size = max(1, -(-len(usable) // max_points))        # ceil division
    out = []
    for start in range(0, len(usable), size):
        chunk = usable[start:start + size]
        values = [pt[1] for pt in chunk]
        traced = [pt[2] for pt in chunk if pt[2] is not None]
        out.append([
            round(chunk[-1][0], 1),
            int(sum(values) / len(values)),
            min(values),
            max(values),
            int(sum(traced) / len(traced)) if traced else None,
        ])
    return out


def _slope_mb_per_hour(points):
    """Least-squares slope of (t seconds, rss bytes), in MB/hour."""
    n = len(points)
    if n < 2:
        return 0.0
    mean_t = sum(pt[0] for pt in points) / n
    mean_y = sum(pt[1] for pt in points) / n
    numerator = sum((pt[0] - mean_t) * (pt[1] - mean_y) for pt in points)
    denominator = sum((pt[0] - mean_t) ** 2 for pt in points)
    if not denominator:
        return 0.0
    return (numerator / denominator) * 3600.0 / _MB


def _floor_series(points, segments=8):
    """The low-water mark of each of ``segments`` slices, as (t, rss).

    The verdict is fitted to this rather than to the raw samples. A sawtooth —
    a busy app allocating and releasing — has peaks that swing the raw slope
    around depending on which phase the window happens to end in, while its
    floor sits still. Only memory that is *kept* moves the floor.
    """
    if len(points) < segments:
        return [(pt[0], pt[1]) for pt in points]
    size = max(1, -(-len(points) // segments))
    out = []
    for start in range(0, len(points), size):
        chunk = points[start:start + size]
        low = min(pt[1] for pt in chunk)
        out.append((chunk[len(chunk) // 2][0], low))
    return out


def _memory_stats(points):
    """Trend of an (t, rss, traced) series: slope, floor rise, and a verdict.

    Three numbers, because one is not enough to tell a leak from a busy app:

      * **slope** — least squares over every sample, in MB/hour. Reported
        because it is what you would compute by eye, but NOT what the verdict
        reads: on an oscillating series it mostly measures which phase the
        window ended in.
      * **floor slope** — the same fit over the low-water mark of each of eight
        slices. This is the verdict's basis. A sawtooth's floor is flat; only
        memory that is kept lifts it.
      * **floor rise** — lowest RSS in the last quarter minus the lowest in the
        first, in MB. The blunt version of the same question, and what separates
        a real step from noise.

    A one-time step (opening a large CSV) raises the floor permanently and would
    otherwise be indistinguishable from a leak, so ``climbing`` also requires the
    floor to be *still* rising over the most recent half. A step that has
    finished reads ``rising`` and settles to ``steady`` as the window rolls past.

    The thresholds are heuristics (see the constants above) and the verdict says
    which rule fired so it can be argued with.
    """
    charted = [pt for pt in points if pt[1] is not None]
    # The verdict ignores the warm-up ramp; the chart still draws it.
    usable = [pt for pt in charted if pt[0] >= MEMORY_WARMUP_SEC]
    stats = {
        'samples': len(charted),
        'verdict_samples': len(usable),
        'verdict_span_sec': 0.0,
        'warmup_sec': MEMORY_WARMUP_SEC,
        'rss_available': bool(charted),
        'current_bytes': charted[-1][1] if charted else None,
        'min_bytes': min(pt[1] for pt in charted) if charted else None,
        'max_bytes': max(pt[1] for pt in charted) if charted else None,
        'span_sec': round(charted[-1][0] - charted[0][0], 1) if len(charted) > 1 else 0.0,
        'slope_mb_per_hour': None,
        'floor_slope_mb_per_hour': None,
        'recent_floor_slope_mb_per_hour': None,
        'floor_rise_mb': None,
        'verdict': 'warming_up',
        'verdict_reason': f'Fewer than {MEMORY_MIN_SAMPLES} samples so far.',
    }
    if len(usable) < MEMORY_MIN_SAMPLES:
        if not charted:
            stats['verdict_reason'] = ('No RSS readings — psutil is not installed, '
                                       'and the fallback can only report a peak.')
        elif charted[-1][0] < MEMORY_WARMUP_SEC:
            stats['verdict_reason'] = (
                f'Still warming up — the first {MEMORY_WARMUP_SEC:.0f} s of a process '
                f'fills caches, which no leak test can tell from a leak.')
        return stats

    n = len(usable)
    verdict_span = usable[-1][0] - usable[0][0]
    stats['verdict_span_sec'] = round(verdict_span, 1)
    floor = _floor_series(usable)
    slope_mb_h = _slope_mb_per_hour([(pt[0], pt[1]) for pt in usable])
    floor_slope_mb_h = _slope_mb_per_hour(floor)
    recent_floor_mb_h = _slope_mb_per_hour(floor[len(floor) // 2:])

    quarter = max(1, n // 4)
    floor_first = min(pt[1] for pt in usable[:quarter])
    floor_last = min(pt[1] for pt in usable[-quarter:])
    floor_rise_mb = (floor_last - floor_first) / _MB

    stats['slope_mb_per_hour'] = round(slope_mb_h, 2)
    stats['floor_slope_mb_per_hour'] = round(floor_slope_mb_h, 2)
    stats['recent_floor_slope_mb_per_hour'] = round(recent_floor_mb_h, 2)
    stats['floor_rise_mb'] = round(floor_rise_mb, 2)

    # A risen floor is the NECESSARY condition for any non-steady verdict, and
    # the slopes only grade it. Comparing the minimum of the last quarter with
    # the minimum of the first is immune to where in its cycle an oscillating
    # app happened to be when the window closed; a fitted slope is not — a
    # triangle wave whose period does not divide the window aliases against the
    # segment boundaries and produces a confident trend out of nothing.
    floor_rising = floor_rise_mb >= MEMORY_FLOOR_RISE_MB
    still_going = recent_floor_mb_h >= MEMORY_RISE_WARN_MB_H
    if floor_rising and floor_slope_mb_h >= MEMORY_RISE_BAD_MB_H and still_going:
        stats['verdict'] = 'climbing'
        stats['verdict_reason'] = (
            f'Floor up {floor_slope_mb_h:.1f} MB/h and {floor_rise_mb:.1f} MB higher '
            f'than it started, still rising over the last half — memory is being kept, '
            f'not reused.')
    elif floor_rising:
        stats['verdict'] = 'rising'
        stats['verdict_reason'] = (
            f'Floor {floor_rise_mb:+.1f} MB over {verdict_span / 60:.0f} min '
            f'({floor_slope_mb_h:+.1f} MB/h, last half {recent_floor_mb_h:+.1f} MB/h). '
            f'A one-time step looks like this — widen the window before calling it a leak.')
    else:
        stats['verdict'] = 'steady'
        stats['verdict_reason'] = (
            f'Floor {floor_rise_mb:+.1f} MB over {verdict_span / 60:.0f} min '
            f'(under the {MEMORY_FLOOR_RISE_MB:.0f} MB this window can resolve); '
            f'samples {slope_mb_h:+.1f} MB/h. Memory is being reused.')
    return stats


class _Series:
    """Count + error count + a bounded ring of millisecond latencies."""

    __slots__ = ('count', 'errors', 'samples', 'last')

    def __init__(self):
        self.count = 0
        self.errors = 0
        self.last = None
        self.samples = deque(maxlen=SAMPLE_WINDOW)

    def record(self, elapsed_ms=None, error=False):
        self.count += 1
        if error:
            self.errors += 1
        if elapsed_ms is not None:
            self.last = round(elapsed_ms, 3)
            self.samples.append(elapsed_ms)

    def as_dict(self):
        samples = list(self.samples)
        return {
            'count': self.count,
            'errors': self.errors,
            'last_ms': self.last,
            'mean_ms': _mean(samples),
            'p95_ms': _pct(samples, 0.95),
            'max_ms': round(max(samples), 3) if samples else None,
        }


class Registry:
    """All counters the monitor reports, behind one lock."""

    def __init__(self):
        self._lock = threading.Lock()
        self.started_at = time.time()
        self._started_monotonic = time.monotonic()
        # tracemalloc bookkeeping: 'devtools' when we started it, 'external'
        # when --mem-monitor (or anything else) got there first. We only ever
        # stop what we started — see stop_tracemalloc().
        self._tracemalloc_owner = None
        self._cpu_wall = time.monotonic()
        self._cpu_proc = time.process_time()
        # psutil.Process handles are kept, never rebuilt per poll: cpu_percent()
        # with no interval is a delta against the *instance's* previous call, so
        # a fresh handle each time reports 0.0 % for ever. Two slots only — this
        # process, and the one logger subprocess — so nothing accumulates.
        self._proc_handle = None
        self._child_handle = (None, None)     # (pid, psutil.Process)
        # Memory history is NOT cleared by reset_counters(): the counters answer
        # "what has happened since I pressed reset", the history answers "has
        # this process been growing", and throwing the second away to ask the
        # first is how you lose the overnight climb you were hunting.
        self._mem_history = deque(maxlen=MEMORY_HISTORY_MAX)
        self.reset_counters()

    # ── lifecycle ───────────────────────────────────────────────────────
    def reset_counters(self):
        """Zero every counter. Uptime and the tracemalloc owner are kept."""
        with self._lock:
            self._http = {}                     # endpoint -> _Series
            self._http_rules = {}               # endpoint -> url rule
            self._http_total = 0
            self._http_errors = 0
            self._http_in_flight = 0
            self._device = {
                'bytes_in': 0, 'bytes_out': 0,
                'lines_in': 0, 'read_calls': 0, 'read_timeouts': 0,
                'malformed_lines': 0, 'replies_matched': 0,
                'connects': 0, 'connect_failures': 0, 'closes': 0,
                'port': None,
            }
            self._device_cmd = _Series()        # one command round-trip
            self._device_open = _Series()       # port open incl. PING probe
            self._device_ping = _Series()       # a single PING probe attempt
            self._lines_marks = deque(maxlen=SAMPLE_WINDOW)   # (monotonic, lines)
            self._stream = {
                'clients_active': 0, 'clients_total': 0,
                'frames': 0, 'bytes_pushed': 0,
                'last_log_offset': None, 'last_csv_offset': None,
                'last_csv_path': None,
            }

    # ── tracemalloc (coexists with main.py's --mem-monitor thread) ──────
    def start_tracemalloc(self):
        """Start tracing unless something already is. Returns the owner tag.

        ``--mem-monitor`` calls ``tracemalloc.start()`` from its own thread and
        reads only ``get_traced_memory()``, which does not care about the frame
        count — so CPython's ``start()`` being a no-op while tracing means the
        two never fight. Recording the owner is what stops us stopping *their*
        tracing: ``stop_tracemalloc()`` only ever stops ``'devtools'``.

        The one case a start-order race would get wrong is ``--monitor
        --mem-monitor`` together: MemGuard starts tracing from a thread while
        ``attach_monitor()`` runs on the main thread a moment later, so we would
        usually win and become the owner — and then the page's *trace off*
        button would silently blank MemGuard's readings for the rest of the run.
        So when that flag is set the owner is 'external' whoever called first.
        """
        import tracemalloc
        with self._lock:
            if tracemalloc.is_tracing():
                if self._tracemalloc_owner is None:
                    self._tracemalloc_owner = 'external'
                return self._tracemalloc_owner
            tracemalloc.start(TRACEMALLOC_FRAMES)
            self._tracemalloc_owner = 'external' if _mem_monitor_flag() else 'devtools'
            return self._tracemalloc_owner

    def stop_tracemalloc(self):
        """Stop tracing only if the monitor was the one that started it."""
        import tracemalloc
        with self._lock:
            if self._tracemalloc_owner != 'devtools':
                return False
            if tracemalloc.is_tracing():
                tracemalloc.stop()
            self._tracemalloc_owner = None
            return True

    # ── memory history ──────────────────────────────────────────────────
    def sample_memory(self):
        """Append one RSS/traced-heap sample. Called by the sampler thread only.

        Reads ``memory_info()`` and nothing else. In particular it must never
        call ``cpu_percent()`` on the shared handle: that reading is a delta
        against the handle's *previous* call, so a second caller on a different
        cadence would silently halve the CPU figure the page shows.
        """
        rss = self._rss_bytes_only()
        traced = None
        try:
            import tracemalloc
            if tracemalloc.is_tracing():
                traced = tracemalloc.get_traced_memory()[0]
        except Exception:
            traced = None
        point = (time.monotonic() - self._started_monotonic, rss, traced)
        with self._lock:
            self._mem_history.append(point)
        return point

    def _rss_bytes_only(self):
        """Current RSS, or None when only a peak is available.

        The stdlib fallback deliberately returns nothing rather than
        ``ru_maxrss``: a peak never comes down, so charting it would draw a
        monotonic climb on a perfectly healthy process and the escalation
        verdict would read 'climbing' for ever.
        """
        if psutil is not None:
            try:
                return self._psutil_self().memory_info().rss
            except Exception:
                pass
        return None

    def memory_history(self, window_sec=None, max_points=MEMORY_MAX_POINTS):
        """The escalation series plus its trend, bucketed for the page."""
        with self._lock:
            points = list(self._mem_history)
        if window_sec:
            cutoff = (points[-1][0] - window_sec) if points else 0
            points = [pt for pt in points if pt[0] >= cutoff]
        stats = _memory_stats(points)
        stats.update({
            'sample_interval_sec': MEMORY_SAMPLE_SEC,
            'retention_sec': MEMORY_HISTORY_SPAN_SEC,
            'window_sec': window_sec,
            'thresholds': {
                'warn_mb_per_hour': MEMORY_RISE_WARN_MB_H,
                'bad_mb_per_hour': MEMORY_RISE_BAD_MB_H,
                'floor_rise_mb': MEMORY_FLOOR_RISE_MB,
            },
            'points': _bucket_memory(points, max_points),
        })
        return stats

    def clear_memory_history(self):
        with self._lock:
            self._mem_history.clear()

    # ── HTTP recorders ──────────────────────────────────────────────────
    def http_begin(self):
        with self._lock:
            self._http_in_flight += 1

    def http_end(self, endpoint, rule, elapsed_ms, status_code, failed=False):
        error = failed or (status_code is not None and status_code >= 400)
        with self._lock:
            self._http_in_flight = max(0, self._http_in_flight - 1)
            self._http_total += 1
            if error:
                self._http_errors += 1
            series = self._http.get(endpoint)
            if series is None:
                series = self._http[endpoint] = _Series()
            self._http_rules[endpoint] = rule
            series.record(elapsed_ms, error=error)

    # ── device recorders ────────────────────────────────────────────────
    def device_read(self, byte_count, lines):
        """One ``LineReader.read_lines()`` return.

        A call that yields no complete line is a **read timeout** in the sense
        that matters here: the port timeout (``send_command.PORT_TIMEOUT``,
        0.15 s) elapsed with nothing framed. That is normal on an idle link and
        pathological during an exchange, which is exactly the distinction the
        readout is for.
        """
        with self._lock:
            d = self._device
            d['read_calls'] += 1
            d['bytes_in'] += byte_count
            if not lines:
                d['read_timeouts'] += 1
                return
            d['lines_in'] += len(lines)
            # U+FFFD only appears when decode('utf-8', 'replace') hit a bad
            # byte — framing damage, not a device message.
            d['malformed_lines'] += sum(1 for line in lines if '�' in line)
            self._lines_marks.append((time.monotonic(), len(lines)))

    def device_write(self, byte_count):
        with self._lock:
            self._device['bytes_out'] += byte_count

    def device_command(self, elapsed_ms, error=False, matched=False):
        with self._lock:
            self._device_cmd.record(elapsed_ms, error=error)
            if matched:
                self._device['replies_matched'] += 1

    def device_open(self, elapsed_ms, error=False, port=None):
        with self._lock:
            self._device_open.record(elapsed_ms, error=error)
            d = self._device
            if error:
                d['connect_failures'] += 1
            else:
                d['connects'] += 1
                if port:
                    d['port'] = port

    def device_ping(self, elapsed_ms, ok):
        with self._lock:
            self._device_ping.record(elapsed_ms, error=not ok)

    def device_close(self):
        with self._lock:
            self._device['closes'] += 1
            self._device['port'] = None

    # ── live-stream recorders ───────────────────────────────────────────
    def stream_client_open(self):
        with self._lock:
            self._stream['clients_active'] += 1
            self._stream['clients_total'] += 1

    def stream_client_close(self):
        with self._lock:
            self._stream['clients_active'] = max(0, self._stream['clients_active'] - 1)

    def stream_frame(self, byte_count):
        with self._lock:
            self._stream['frames'] += 1
            self._stream['bytes_pushed'] += byte_count

    def stream_offset(self, kind, path, offset):
        with self._lock:
            if kind == 'csv':
                self._stream['last_csv_offset'] = offset
                self._stream['last_csv_path'] = path
            else:
                self._stream['last_log_offset'] = offset

    # ── snapshot ────────────────────────────────────────────────────────
    def snapshot(self):
        """Assemble the whole readout. Called once per poll, never per event."""
        return {
            'generated_at': time.time(),
            'uptime_sec': round(time.monotonic() - self._started_monotonic, 1),
            'process': self._process_section(),
            'http': self._http_section(),
            'device': self._device_section(),
            'stream': self._stream_section(),
        }

    def _http_section(self):
        with self._lock:
            routes = [
                dict(endpoint=endpoint, rule=self._http_rules.get(endpoint, ''),
                     **series.as_dict())
                for endpoint, series in self._http.items()
            ]
            total, errors, in_flight = self._http_total, self._http_errors, self._http_in_flight
        routes.sort(key=lambda r: r['count'], reverse=True)
        return {'total': total, 'errors': errors, 'in_flight': in_flight, 'routes': routes}

    def _device_section(self):
        with self._lock:
            device = dict(self._device)
            command = self._device_cmd.as_dict()
            opened = self._device_open.as_dict()
            ping = self._device_ping.as_dict()
            marks = list(self._lines_marks)
        # Lines/sec over the window still in the ring, so an idle link decays to
        # zero instead of averaging over the whole uptime.
        rate = 0.0
        if len(marks) >= 2:
            span = marks[-1][0] - marks[0][0]
            if span > 0:
                rate = round(sum(count for _, count in marks[1:]) / span, 2)
        # A line the link read but no predicate accepted: device banners, the
        # tail of an earlier session, console noise. Derived rather than counted
        # because the drop happens inside _exchange_locked's own loop.
        unmatched = max(0, device['lines_in'] - device['replies_matched'])
        device.update({
            'lines_per_sec': rate,
            'lines_unmatched': unmatched,
            'command': command,
            'open': opened,
            'ping_probe': ping,
            'link_connected': _link_connected(),
            'session_owns_port': _session_owns_port(),
            'logger': self._logger_process(),
        })
        return device

    def _stream_section(self):
        with self._lock:
            return dict(self._stream)

    def _process_section(self):
        # 'source' comes back with the numbers rather than being decided here:
        # psutil can be installed and still fail (AccessDenied, a process that
        # went away), and a readout that says psutil while showing the stdlib
        # fallback's fields is how you end up mis-reading rss_bytes: null.
        info = {'pid': os.getpid()}
        info.update(self._process_resources())
        info['gc'] = _gc_stats()
        info['tracemalloc'] = self._tracemalloc_stats()
        return info

    def _psutil_self(self):
        """The one long-lived handle on this process (see __init__)."""
        if self._proc_handle is None:
            self._proc_handle = psutil.Process()
        return self._proc_handle

    def _psutil_child(self, pid):
        """A long-lived handle on the logger subprocess, replaced when it is."""
        known_pid, handle = self._child_handle
        if handle is None or known_pid != pid:
            handle = psutil.Process(pid)
            self._child_handle = (pid, handle)
        return handle

    def _process_resources(self):
        if psutil is not None:
            try:
                proc = self._psutil_self()
                with proc.oneshot():
                    mem = proc.memory_info()
                    return {
                        'source': 'psutil',
                        'rss_bytes': mem.rss,
                        'vms_bytes': mem.vms,
                        # interval=None never blocks: it is the delta since
                        # *this handle's* previous call, so the poll cadence is
                        # the interval. Which is why the handle is kept — a
                        # psutil.Process built per poll has no previous call and
                        # answers 0.0 % every single time.
                        'cpu_percent': round(proc.cpu_percent(interval=None), 1),
                        'threads': proc.num_threads(),
                        'open_fds': _num_fds(proc),
                    }
            except Exception:
                pass
        return self._process_resources_stdlib()

    def _process_resources_stdlib(self):
        """psutil-free fallback: peak RSS from getrusage, CPU from process_time.

        Reports ``rss_bytes: None`` rather than guessing — getrusage can only
        give the *peak*, and quietly labelling a peak as current would make the
        one number people watch for a leak wrong in the safe-looking direction.
        """
        peak = None
        if resource is not None:
            try:
                raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                # macOS reports bytes, Linux kilobytes.
                peak = raw if sys.platform == 'darwin' else raw * 1024
            except Exception:
                peak = None
        now_wall, now_proc = time.monotonic(), time.process_time()
        with self._lock:
            wall_delta = now_wall - self._cpu_wall
            proc_delta = now_proc - self._cpu_proc
            self._cpu_wall, self._cpu_proc = now_wall, now_proc
        cpu = round(100.0 * proc_delta / wall_delta, 1) if wall_delta > 0 else 0.0
        return {
            'source': 'stdlib',
            'rss_bytes': None,
            'rss_peak_bytes': peak,
            'vms_bytes': None,
            'cpu_percent': cpu,
            'threads': threading.active_count(),
            'open_fds': _num_fds(None),
        }

    def _logger_process(self):
        """Resource use of the CDC logger subprocess, when one is running.

        A running session's serial traffic belongs to *that* process, not this
        one, so its bytes never reach the counters above. Its CPU and RSS are
        the closest thing the monitor can honestly show for a live capture.
        """
        st = _state()
        process = getattr(st, 'process', None) if st else None
        if process is None:
            return {'running': False, 'pid': None}
        try:
            running = process.poll() is None
        except Exception:
            return {'running': False, 'pid': None}
        info = {'running': running, 'pid': getattr(process, 'pid', None)}
        if running and psutil is not None and info['pid']:
            try:
                child = self._psutil_child(info['pid'])
                with child.oneshot():
                    info['rss_bytes'] = child.memory_info().rss
                    info['cpu_percent'] = round(child.cpu_percent(interval=None), 1)
            except Exception:
                pass
        return info

    def _tracemalloc_stats(self):
        import tracemalloc
        with self._lock:
            owner = self._tracemalloc_owner
        if not tracemalloc.is_tracing():
            return {'enabled': False, 'owner': owner, 'top': []}
        current, peak = tracemalloc.get_traced_memory()
        top = []
        try:
            for stat in tracemalloc.take_snapshot().statistics('lineno')[:TRACEMALLOC_TOP]:
                frame = stat.traceback[0]
                top.append({'file': frame.filename, 'line': frame.lineno,
                            'size_bytes': stat.size, 'count': stat.count})
        except Exception:
            pass
        return {'enabled': True, 'owner': owner, 'current_bytes': current,
                'peak_bytes': peak, 'top': top}


def _num_fds(proc):
    """Open file descriptors, psutil first and /dev/fd (or /proc) as fallback."""
    if proc is not None:
        try:
            return proc.num_fds()
        except Exception:
            pass
    for path in ('/proc/self/fd', '/dev/fd'):
        try:
            return len(os.listdir(path))
        except Exception:
            continue
    return None


def _gc_stats():
    """Collector counters — all of them O(1) reads of numbers gc already keeps.

    There is deliberately no total object count here. ``len(gc.get_objects())``
    is the only way to get one, and it walks the whole heap: measured at ~45 ms
    and ~2.5 MB of transient list for 300k tracked objects. Once a second, from
    inside the request handler, that is both a real slice of a core and a lie
    told to the panel two rows down — the 2.5 MB lands in tracemalloc's peak, so
    the monitor would be the biggest allocator on its own allocation table. RSS
    and the traced-memory figures already answer "is this process growing".
    """
    stats = gc.get_stats()
    return {
        'enabled': gc.isenabled(),
        'counts': list(gc.get_count()),
        'collections': [g.get('collections', 0) for g in stats],
        'collected': [g.get('collected', 0) for g in stats],
        'uncollectable': [g.get('uncollectable', 0) for g in stats],
        'garbage': len(gc.garbage),
    }


def _state():
    """src.state, or None when it is not importable (bare unit tests)."""
    try:
        import state
        return state
    except Exception:
        return None


def _session_owns_port():
    """True while the logger subprocess holds the serial port (Rule.md §2.35).

    The monitor reports this so a zero device-link readout reads as "the session
    owns the port", not "the link is broken".
    """
    st = _state()
    process = getattr(st, 'process', None) if st else None
    try:
        return process is not None and process.poll() is None
    except Exception:
        return False


def _mem_monitor_flag():
    """True when the process was started with ``--mem-monitor``."""
    st = _state()
    return bool(getattr(getattr(st, 'args', None), 'mem_monitor', False))


def _link_connected():
    """Whether the idle-time control link currently holds the port open.

    Read straight off the attribute rather than through ``DeviceLink.connected``:
    that property takes the link's own lock, and ``DeviceLink.command()`` holds
    that lock for the whole of an exchange — including ``connect_to_device()``,
    which can spend ``PROBE_TIMEOUT`` per candidate port. Going through the
    property would park this poll (and the request thread serving it) behind
    device I/O for seconds at a time, which is the monitor disturbing exactly
    what it is supposed to be watching. A lock-free read can only be one instant
    stale, and this is a status lamp.
    """
    try:
        import device_link
        port = device_link.link._serial
        return bool(port is not None and port.is_open)
    except Exception:
        return False




# One registry per process — the monitor is a singleton by construction.
registry = Registry()
