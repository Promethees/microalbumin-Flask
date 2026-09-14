# `devtools/` — the developer performance monitor

A live readout of what the EasyOKAPI process is doing: memory, CPU, threads,
file descriptors, garbage collection, allocation hot spots, per-route HTTP
latency, the colorimeter's control link, and the SSE live-session stream.

It is a **developer tool**. It is not part of what a user receives, it is not
translated, it has no user settings, and it never touches the serial port.

---

## Launching it

```bash
./setup-3-run.command --monitor
```

or, running `main.py` directly:

```bash
python main.py --monitor
python main.py --monitor --port 5099 --alias easyokapi.com
python main.py --monitor --mem-monitor --verbose      # composes with the others
```

Then open:

```
http://easyokapi.com:5099/__dev/monitor
```

(or `http://127.0.0.1:<port>/__dev/monitor` — the page is served by the same app,
so whatever host/port the app is on works). `setup-3-run.command` prints the URL
in a **DEVELOPER MODE** banner when it sees the flag, and `main.py` prints it
again once the monitor has actually attached.

Endpoints:

| Route | Method | Purpose |
|---|---|---|
| `/__dev/monitor` and `/__dev/monitor/` | GET | The page |
| `/__dev/monitor/metrics` | GET | The whole readout as JSON — the page polls this once a second; `curl` it for a scriptable snapshot |
| `/__dev/monitor/memory` | GET | The memory-escalation series and its trend. `?window=<sec>` narrows it, `?points=<n>` caps the buckets |
| `/__dev/monitor/control` | POST | `{"action": "reset" \| "trace_on" \| "trace_off" \| "memory_clear"}` |
| `/__dev/monitor/assets/<file>` | GET | The page's own CSS/JS |

**Every one of them answers 404 unless the monitor is attached** — not 403. A
normal run must look like a build that never had these routes, not like one that
is hiding them.

---

## What it measures

### Process

| Field | Unit | How to read it |
|---|---|---|
| `rss_bytes` | bytes | Resident set size — physical memory actually held. The number to watch for a leak: a sawtooth is healthy, a staircase is not. |
| `rss_peak_bytes` | bytes | Only present on the psutil-free fallback, where the *current* RSS is unavailable. It is a high-water mark and never comes down. |
| `vms_bytes` | bytes | Virtual size. Large and mostly uninteresting on macOS; a jump usually means a new mapping (a library, a big file), not new memory use. |
| `cpu_percent` | % of one core | Since the previous poll, so it is a rate and not an average over uptime. >100 % is legitimate with several busy threads. |
| `threads` | count | Baseline is roughly: Flask + the browser-opener + the token/revocation/uninstall/cleanup threads + the device link's reaper. Steady growth is a thread leak. |
| `open_fds` | count | Open file descriptors. Watch this while opening and closing reading sessions — a serial port or a log file that is not being released shows up here first. |
| `pid` | — | This process. Useful for `lsof -p` / `sample`. |
| `gc.collections` | count per generation | `[gen0, gen1, gen2]`. Gen-2 collections are the expensive ones. |
| `gc.uncollectable`, `gc.garbage` | count | **Defects, not readings.** Anything above zero is a reference cycle the collector gave up on. The page paints them in `--danger`. |

There is deliberately **no total object count**. `len(gc.get_objects())` is the
only way to get one and it walks the entire heap: measured at ~45 ms and ~2.5 MB
of transient list for 300k tracked objects. Once a second that is a real slice of
a core spent inside the request handler — and the 2.5 MB lands in tracemalloc's
peak, so the monitor would be the biggest allocator on its own allocation table.
RSS and the traced-memory figures already answer "is this process growing".

### Memory over time (the escalation chart)

A chart of resident memory for the whole run, with a verdict attached. This is
the panel to look at when the question is "is this thing leaking".

**It is sampled server-side, on its own thread** (`devmon-memory-sampler`, one
`memory_info()` every `MEMORY_SAMPLE_SEC` = 5 s, kept for four hours in a
bounded ring). That costs a thread the page-driven alternative would not, and it
buys the only thing that makes the panel worth having: the series covers the
hours nobody had the tab open. A chart that starts when you open it cannot tell
you what happened overnight.

The history **survives "Reset counters"** — the counters answer "what has
happened since I pressed reset", the history answers "has this process been
growing", and throwing the second away to ask the first is how you lose the
climb you were hunting. `Clear history` is a separate button.

**Reading the chart.** Each plotted point is a bucket, drawn as a band from the
bucket's minimum to its maximum with the average as a line through it. The band
is the whole point:

* **Wide band, flat bottom** — a busy app. Peaks move with whatever it is doing;
  the memory is being reused.
* **Bottom rising with the top** — a leak. Something is being kept.

The dashed second line is the traced Python heap, drawn only while allocation
tracing is on. It is normally far below RSS; when the two rise together the
growth is Python objects and the allocation table above will name the line.

**The two numbers.**

| Field | Unit | How to read it |
|---|---|---|
| `slope_mb_per_hour` | MB/h | Least-squares fit over every sample. Shown because it is what you would compute by eye — but **not** what the verdict reads. |
| `floor_rise_mb` | MB | Lowest RSS in the last quarter minus the lowest in the first. **The gate.** |
| `floor_slope_mb_per_hour` | MB/h | The fit over the low-water mark of each of eight slices. Grades how fast. |
| `recent_floor_slope_mb_per_hour` | MB/h | The same fit over the most recent half. Answers "is it *still* going". |

The raw slope is not the verdict's basis, because on an oscillating series it
mostly measures which phase the window happened to end in: a sawtooth between
80 and 90 MB reports +6 MB/h or −9 MB/h depending on where you cut it, with the
floor sitting still the whole time.

So the gate is `floor_rise_mb` — a comparison of two minima, immune to phase —
and the slopes only grade what it caught. A fitted floor slope cannot be the
gate either: a triangle wave whose period does not divide the window aliases
against the slice boundaries and produces a confident +12 MB/h out of nothing.

A one-time step (opening a large CSV) raises the floor permanently, so
`climbing` additionally requires the floor to be **still** rising over the most
recent half. A step that has finished reads `rising` and settles to `steady` as
the window rolls past it.

**The verdict is a heuristic and says so.** The thresholds live in one block at
the top of `metrics.py` (`MEMORY_RISE_WARN_MB_H` 5, `MEMORY_RISE_BAD_MB_H` 20,
`MEMORY_FLOOR_RISE_MB` 2) and are shipped in the JSON so the page can show what
it applied:

| Verdict | Rule | Painted |
|---|---|---|
| `warming_up` | fewer than `MEMORY_MIN_SAMPLES` (24 ≈ 2 min) | plain |
| `steady` | floor rise under `MEMORY_FLOOR_RISE_MB` | `--go` |
| `rising` | floor rise over it | `--warn` |
| `climbing` | floor rise over it, floor slope over `MEMORY_RISE_BAD_MB_H`, **and** still rising over the last half | `--danger` |

Validated against ten synthetic series — flat, sawtooth, two triangle waves, a
single tall spike, a fast leak, a slow leak, a step with and without noise, and
a falling series — in `tests/test_devtools_monitor.py`.

**The first two minutes are charted but not judged.** A fresh interpreter is not
in steady state — it compiles templates, loads the i18n catalogs and fills its
file-metadata caches on first use — and that ramp is memory genuinely being
kept, so no measurement of it can come back clean. Caught on a live run: RSS
climbed 66.9 → 73.3 MB over the first 190 s of a freshly started app and the
verdict read `climbing`. Samples inside `MEMORY_WARMUP_SEC` (120 s) are excluded
from the verdict and still drawn on the chart, so the ramp stays visible and
stops being an accusation. A leak that outlives the warm-up is caught normally.
`verdict_samples` and `verdict_span_sec` report what the verdict actually used.

The same caveat applies later in a run, and cannot be automated away: the first
time you open a feature, its caches fill and the floor steps up. That is a
`rising`, and it is correct. Widen the window, or exercise the feature twice and
watch whether the floor moves again.

**The gate sets a sensitivity floor**: a leak slower than `MEMORY_FLOOR_RISE_MB`
(2 MB) *per window* reads `steady`. That is the intended trade — it is what
stops normal jitter crying wolf — and it is why the window selector goes out to
four hours. A 0.5 MB/h leak is invisible at 30 minutes and obvious at four.

Calibrate them against your own baseline before trusting them. On this machine
an idle app under a 1 Hz poll sat flat at ~76 MB for the whole run, so anything
above a couple of MB/h is worth a longer window; a machine that runs long
sessions with large CSVs will have a different normal.

**Without psutil there is no chart.** The stdlib fallback can only give
`ru_maxrss`, a high-water mark that never comes down — charting it would draw a
monotonic climb on a perfectly healthy process and the verdict would read
`climbing` for ever. The series stays empty and the panel says why.

### Allocations (tracemalloc)

`tracemalloc.current_bytes` / `peak_bytes` and a **top-12 table of allocation
sites** (`file:line`, size, block count), sorted by size.

Read it as "which line is holding the most memory *right now*", not "which line
allocated the most" — freed allocations leave the table.

* Tracing is started with one frame per allocation (`TRACEMALLOC_FRAMES = 1`):
  the table names a line, and deeper tracebacks multiply the cost without
  changing which line is at the top.
* **It coexists with `--mem-monitor`.** That flag's thread calls
  `tracemalloc.start()` too, and CPython's `start()` is a no-op while tracing is
  already on, so the two cannot fight. The monitor **only ever stops tracing it
  started itself**: with `--mem-monitor` running, the `owner` reads `external`
  and `trace_off` deliberately does nothing, because MemGuard is reading that
  tracing and a dev page's button must not blank its growth report for the rest
  of the run. (Attaching no longer races it either — tracing starts off.) Drop
  `--mem-monitor` if you want the switch back.
* **Tracing starts off.** Click **Tracing: off** to turn it on; the allocation
  table fills from the next poll. It is the one genuinely expensive thing here —
  a frame capture on every allocation, and a `take_snapshot()` per poll that
  copies every traced block. Measured on this app: `/__dev/monitor/metrics`
  answers in **14.5 ms** with tracing off and **246 ms** with it on, so a 1 Hz
  page with tracing left on spends about a quarter of a core inside a request
  handler for as long as the tab is open. Turn it on to hunt an allocation, turn
  it off to measure anything else.

### HTTP

Totals (`total`, `errors`, `in_flight`) plus one row per route: `count`,
`errors`, `mean_ms`, `p95_ms`, `max_ms`. Latency is a bounded ring of the last
256 observations per route (`SAMPLE_WINDOW`), so p95 tracks recent behaviour
rather than the whole run, and nothing grows without limit.

* An **error** is any response with status ≥ 400, plus any request whose view
  raised.
* The monitor's own routes are **not** counted. The page polls once a second, so
  counting itself would make the busiest route in every readout the readout.
* The timing hook is registered after the request-origin guard and the licence
  gates (that is simply when `attach_monitor` runs), so a request one of *those*
  rejects never starts the clock. It is still counted, with no latency sample —
  a wall of blocked POSTs is exactly what you would want to see.

### Device link (PyBadge over USB CDC)

| Field | Unit | How to read it |
|---|---|---|
| `port` | path | The port the control link last opened, e.g. `/dev/cu.usbmodem1401`. |
| `session_owns_port` | bool | True while the logger subprocess holds the port (Rule.md §2.35). **Read this first**: a flat device readout during a session is correct, not broken. |
| `link_connected` | bool | Whether `device_link.link` is holding the port open right now. It is reaped after `IDLE_TIMEOUT`. |
| `bytes_in` | bytes | Payload framed by `send_command.LineReader`. A *floor*: the framer strips `\r` and trailing whitespace before the wrapper can see it. |
| `bytes_out` | bytes | Host commands written over the control link, `+1` for the newline. The PING probe's own 5 bytes are deliberately excluded — a probe that could not open the port never wrote them, and from outside `_probe` the two cases are indistinguishable. |
| `lines_in` | count | Complete lines framed. |
| `lines_per_sec` | lines/s | Over the window still in the ring, so an idle link decays to zero instead of averaging over uptime. |
| `read_calls` / `read_timeouts` | count | A read that framed no complete line within `PORT_TIMEOUT` (0.15 s). Normal on an idle link; pathological *during* an exchange. |
| `malformed_lines` | count | Lines containing U+FFFD — a byte that failed UTF-8 decoding, i.e. framing damage rather than a device message. Above zero is a defect. |
| `replies_matched` / `lines_unmatched` | count | Lines the exchange accepted vs. everything else it saw: device banners, console noise, the tail of an earlier session. `lines_unmatched` is *derived* (`lines_in − replies_matched`), because the drop happens inside `_exchange_locked`'s own loop. |
| `connects` / `connect_failures` / `closes` | count | Port opens, failed opens, and closes. A climbing `closes` with a climbing `connects` is the idle reaper doing its job; a climbing `connect_failures` is a device that is gone. |
| `ping_probe` | ms + counts | Round-trip of one `PING` against one candidate port — the probe that tells the CDC *data* endpoint from the byte-identical console one (Rule.md §2.28). `errors` counts probes that did not answer, which for a two-port board is normal for one of the two. |
| `command` | ms + counts | One host command round-trip (`STATE?`, `MENU?`, `BTN:…`). `errors` is the no-reply timeout — the number to watch when a device stops answering. |
| `logger` | — | The CDC logger **subprocess**: `pid`, `running`, and (with psutil) its `cpu_percent` and `rss_bytes`. |

> **Why the logger gets its own row.** A running session's serial traffic is read
> by `log_cdc_data.py` in a **separate process**, which has its own interpreter
> and never executes the monitor's wrappers. Its bytes therefore cannot appear in
> the counters above, and pretending otherwise would be a lie. Its CPU and RSS
> are the closest honest substitute.

### Live stream (SSE)

`clients_active`, `clients_total`, `frames`, `bytes_pushed`, and the last byte
offset of each tail (`last_log_offset`, `last_csv_offset`, `last_csv_path`).

`clients_active` returning to zero after a tab closes is the thing worth
checking: a browser that goes away *closes* the generator rather than returning
from it, so the counter is bracketed in a `finally`.

---

## Safety: the monitor never owns the serial port

Rule.md §2.28 / §2.31 / §2.35: **the serial port has exactly one owner.** During
a run that is the logger subprocess; while idle it is `device_link.link`.

This package therefore:

* never calls `serial.Serial(...)`, `connect_to_device()`, `_probe()` or any
  `DeviceLink` operation;
* never writes a byte to the device, not even a `PING`;
* has no metric that would require asking the device anything — which is why
  "firmware version" and "device uptime" are absent from the readout, even
  though `STATE?` would report them.

Every device number in the monitor is a byte some *other* caller already moved.
The wrappers only add them up. If you are tempted to add a metric that needs a
command, the answer is no: read it from the virtual-controller panel, which is
the component that legitimately owns the port while idle.

---

## How it stays out of the app

* **One package.** Everything is under `devtools/`. Nothing was added to `src/`,
  `src/routes/`, `templates/`, `static/`, `ui_translations/` or
  `user_settings.py`.
* **One block in `main.py`.** A `--monitor` argparse flag and one guarded block
  that does `from devtools import attach_monitor` *inside* the flag, wrapped so
  that a missing or broken `devtools/` logs a warning and the app starts
  normally. There is no top-level import — a shipped build has no `devtools/` at
  all and must start exactly as before.
* **No production instrumentation.** The device, serial and stream metrics come
  from wrappers that `devtools/hooks.py` installs on
  `src/send_command.py`, `src/device_link.py` and `src/live_stream.py` **at
  attach time**, and removes on detach. There is **no** counter call, no hook and
  no no-op shim anywhere in `src/`. With the flag absent, those modules are
  byte-for-byte what they were and the cost is exactly zero.
* **Refused when frozen.** `attach_monitor()` returns False and prints a warning
  if `sys.frozen` or `state.IS_FROZEN` is set, so even a bundle that somehow
  contained this package would not serve the page.

### Exemptions, stated explicitly

* **i18n (Rule.md §2.22) does not apply here.** The seven-catalog rule exists for
  the user-facing app; this page has one audience and stays in English. Do not
  add `data-i18n` attributes, `t()` calls, or keys to `ui_translations/`.
* **The Settings Coverage Rule does not apply here.** Do not add a
  `user_settings.py` key for anything in this package — the poll interval and the
  tracing switch are controls on the page itself, and a preference that only a
  developer can reach does not belong in a user's `user_settings.json`.
* **The design rules (Rule.md §2.33) DO apply.** `devtools/static/monitor.css`
  contains no hex literal and no gradient: the page links `static/style.css` for
  the token block and resolves every colour, font and radius through `var(--…)`.
  Keep it that way.

---

## Accepted limitations

Known, deliberate, and not worth the complexity of fixing in a dev tool:

* **A 404's path is not kept.** Every unrouted request shares one `(unmatched)`
  row with an empty `rule`. The path is caller-chosen text — any page the
  developer happens to be visiting can issue a cross-origin `GET` to
  `http://127.0.0.1:<port>/<anything>`, since the origin guard covers unsafe
  methods only — and this page renders these strings inside the app's own
  origin. Keeping one bounded row is also what stops 404 spam growing the table.
  Use `--verbose` if you need to see which paths were missed.
* **`bytes_in` is a floor.** `LineReader` strips `\r` and trailing whitespace
  before the wrapper can see the line, so a few bytes per line go uncounted, and
  whatever `LineReader.drain()` discards never passes through `read_lines()` at
  all. The counter answers "is the link carrying traffic", not "how many bytes
  crossed the wire".
* **A running session's serial traffic is invisible**, because it belongs to
  another process. The logger's pid/CPU/RSS stand in for it.
* **The blueprint cannot be unregistered.** Flask has no API for it, so
  `detach_monitor()` leaves the rules in place and relies on the blueprint's
  `before_request` to 404 them. Only tests ever detach.
* **The launcher's banner is cosmetic.** `setup-3-run.command` prints the URL
  from its own reading of `--port`/`--alias`; it cannot know whether
  `attach_monitor()` succeeded. `main.py` prints the URL again when it actually
  did, and that is the authoritative line.
* **`in_flight` can read one high for an instant** on a request rejected by a
  gate registered before ours: the count is opened in `after_request` and closed
  in the same call, so a concurrent poll can catch it mid-pair.

---

## Excluded from the shipped build

`devtools/` is tracked in git on `main` — it is a developer tool, not a secret —
but it never leaves the repository in a distributed artifact:

* **Frozen build:** `'devtools'` is listed in `excludes` in **`easyokapi.spec`**.
* **Source tarball:** `/devtools export-ignore` in **`.gitattributes`**, which is
  what `git archive` (run by `tools/package.py --source`) honours.
* **`tools/package.py`** copies extra files by name, one at a time, never by
  glob — so nothing here can reach a bundle through `_bundle_extra_files`.

### Keeping the exclusion intact when you add files

Both exclusions are **per-package, not per-file**, so a new module, template or
asset under `devtools/` is covered automatically. What would break it:

1. **Adding a `devtools` name to `hiddenimports` in `easyokapi.spec`.** A
   hiddenimport overrides an exclude. Don't.
2. **Importing `devtools` from anything under `src/`, `main.py` (outside the
   flag block), or a template.** PyInstaller follows real imports; an
   unconditional one would pull the package in and fail the build against the
   exclude. The dependency arrow points one way: `devtools` imports from `src`,
   never the reverse.
3. **Moving the package**, e.g. to `src/devtools/`. It would then be inside a
   `pathex` root the analysis walks, and the `.gitattributes` path would no
   longer match.
4. **Adding a glob to `_bundle_extra_files` in `tools/package.py`.**

`tests/test_devtools_monitor.py` asserts (1) — the `excludes` entry is present
and no `hiddenimports` entry names `devtools` — (2), by walking `src/`,
`templates/` and `static/` for any mention of the package, and the
`.gitattributes` line. (3) and (4) are not machine-checked: moving the package or
adding a glob to `_bundle_extra_files` is caught in review, not by the suite.

---

## Dependencies

`psutil` is in **`requirements-dev.txt` only** — never `requirements.txt`. When
it is absent the monitor degrades to stdlib metrics:

| With psutil | Without |
|---|---|
| current RSS | `rss_bytes: null` + `rss_peak_bytes` from `resource.getrusage` |
| VMS | `null` |
| CPU % from the OS | CPU % derived from `time.process_time()` between polls |
| thread count from the OS | `threading.active_count()` |
| `num_fds()` | a listing of `/proc/self/fd` or `/dev/fd` |
| logger subprocess CPU/RSS | omitted (PID and liveness still reported) |

The fallback deliberately reports `rss_bytes: null` rather than passing the
*peak* off as the current value — that would make the one number people watch
for a leak wrong in the reassuring direction.

---

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Public surface: `attach_monitor`, `detach_monitor`, `is_enabled`, `is_frozen`, `monitor_url`, `MONITOR_PREFIX` |
| `monitor.py` | Attach/detach, the frozen refusal, the per-request timing hooks |
| `metrics.py` | The counter registry (bounded, lock-guarded) and the process sampler |
| `hooks.py` | Attach-time wrappers on `send_command` / `device_link` / `live_stream`, and their exact removal |
| `routes.py` | The `/__dev/monitor` blueprint, 404-gated on `is_enabled()` |
| `templates/devtools_monitor.html` | The page |
| `static/monitor.css` | Page styling — tokens only |
| `static/monitor.js` | Poll + repaint |

Tests: `tests/test_devtools_monitor.py`.
