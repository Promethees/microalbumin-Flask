# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Start Here

Before writing any code, read these two files in order:

1. **`Rule.md`** — Hard constraints, coding rules, and anti-patterns for this branch.
2. **`easyokapi-knowledge/EASY OKAPI.md`** — Architecture, file map, route table, data formats.

---

## Commands

```bash
# Install dependencies (Python 3.8 via pyenv; single cross-platform requirements.txt; requirements-dev.txt adds test-only deps)
pip install -r requirements.txt

# Run the app (default port 5099, alias easyokapi.com)
python main.py
python main.py --port 5099 --alias easyokapi.com
python main.py --verbose        # show HTTP logs + backend prints
python main.py --mem-monitor    # enable tracemalloc memory growth tracking

# Run tests (exclude venv)
pytest tests/ --ignore=venv
pytest tests/test_utils.py      # run a single test file
pytest tests/ -k "test_ping"    # run a single test by name
```

**Flask version is 1.1.4** — do not use APIs introduced after Flask 1.x (e.g., `app.json`, `current_app.ensure_sync`). Check Flask 1.x docs for compatibility.

---

## Project in One Line

Flask-based local desktop app that reads a PyBadge colorimeter over USB/HID and visualizes bio-sensor CSV data in a browser. Single-user, no sessions, no SocketIO, no cloud.

---

## Current Version: 1.4.1

---

## Architecture at a Glance

```
main.py (thin entry point)
  └── registers 8 Flask Blueprints from src/routes/
        ├── core_routes.py    — ping, index, shutdown, browse, JSON cal, report subjects
        ├── file_routes.py    — CSV/JSON CRUD, export, merge, edit locks, manual folder/CSV creation
        ├── report_routes.py  — report subject/item CRUD + Excel report export
        ├── hardware_routes.py — data-logger subprocess control (run/pause/resume/check/terminate/logs/stream_session); CDC serial by default, HID keyboard fallback via device Left button; virtual-controller routes (device/state, device/button, device/channels)
        ├── math_routes.py    — server-side regression API
        ├── ai_routes.py      — AI assistant: chat, settings, activation
        ├── music_routes.py   — background music: radio catalogue, YouTube link resolve, play queue (metadata only)
        └── update_routes.py  — auto-update: check, apply (SSE), finalize (shutdown for relaunch)

src/
  ├── state.py          ← global state singleton (process, paths, delimiter, PRODUCTION_MODE)
  ├── i18n.py           ← UI translation catalogs (ui_translations/<lang>.json, 6 languages)
  ├── validators.py     ← @validate_json decorator for route input validation
  ├── security.py       ← request-origin guard (CSRF + DNS-rebinding) on state-changing methods; init_request_guard(app)
  ├── live_stream.py    ← SSE tail of a live reading session (log + active CSV, by byte offset)
  ├── device_link.py    ← idle-time CDC control link (virtual controller: STATE?/BTN:/CHANNELS:)
  ├── math_ops.py       ← scipy/numpy regression (linear, poly, log, exp, Michaelis-Menten)
  ├── ai_assistant.py   ← Groq chat client, MCP tool engine, multilingual system prompts
  ├── music.py          ← radio catalogue + cached TCP connectivity probe + YouTube link parsing/oEmbed naming
  ├── music_queue.py    ← persisted YouTube play queue (music_queue.json)
  ├── user_settings.py  ← user preferences + SUPPORTED_LANGUAGES registry (the 6 UI/AI-chat languages)
  ├── ai_feedback.py    ← answer 👍/👎 log (ai_feedback.jsonl) + learned guide-matcher weights (ai_guide_weights.json)
  ├── hwid.py           ← per-machine fingerprint (hardware-lock basis)
  ├── activation_pubkey.py ← embedded RS256 public key (verify-only)
  ├── activation.py     ← license gate: verify_token() = RS256 sig + hwid claim
  └── routes/           ← blueprint modules (see above)

static/script/
  ├── report.js         ← report generation + subject CRUD UI
  ├── user-guide.js     ← interactive spotlight user guide
  ├── tooltip.js        ← styled hover-hint component ([data-hint] → body-appended #okapi-tooltip; replaces native title=)
  ├── live-stream.js    ← SSE live-session client (rows + log pushed; the old polls are the fallback)
  ├── i18n.js           ← UI translation applier (t() + applyTranslations over [data-i18n*]; UI_STRINGS injected)
  ├── ai-chat.js        ← floating AI chat widget (Groq-powered, 6 languages)
  ├── music.js          ← floating music widget (bottom-left 🎧): radio stations + YouTube queue, online-only
  ├── device-control.js ← virtual controller panel (device keypad + per-screen button labels)
  └── cdc-logging.js    ← reading-session UI: run/pause/stop, session timer, start-up notice, and the
                           session strip (#session-strip — the live chart-recorder trace, Rule §2.33)

static/fonts/           ← self-hosted type: plex.css (instrument) + classic.css (classic); no Google Fonts request
static/style.css        ← design tokens (:root + body.dark) then all UI styling — Rule §2.33

ui_translations/        ← UI translation catalogs: en.json (baseline) + vi/zh/fr/ja/ru (key→string)

report/                 ← saved HTML reports, organized by subject subdirectory
user_settings.json      ← user preferences incl. AI prefs (ui_language, ai_feedback_enabled)
```

---

## Key Invariants

- **Global state lives in `src/state.py`**, not in `main.py` globals anymore.
- **All routes are in blueprints** — do not add routes directly to `main.py`.
- **`@validate_json`** from `validators.py` must be used on any POST route that accepts JSON.
- **Regression math runs server-side** via `math_ops.py` + `/calculate_coef_and_rsquared` and `/calculate_kinetics_quantities` endpoints. JS `calculate.js` still handles client-side preview rendering. Two coefficient-driven helpers reuse the same 5 fit models: **`/calculate_concentration`** (`math_ops.evaluate_curve`) evaluates a curve at one measured `x` → concentration for the **Quick concentration** calculator (no CSV needed), and **`/export_cal_excel_formula`** (`src/excel_formula.py`) emits paste-ready Excel formulas from the coefficients. Keep all three model implementations (`math_ops` fit funcs, `evaluate_curve`, `excel_formula`) in lockstep.
- **Point-mode Turn axis**: a raw series file's X column is `Timestamp` (elapsed seconds) **or** `Turn` (a 1,2,3… index for point mode); a Turn file has no Timestamp column. Schema `CSV_SCHEMA_TIMESERIES_TURN` in `file_path.py`. `file.get_dynamic_data()` renames the `Turn` key → `Timestamp` on read and returns `x_axis:'turn'` so the whole `"Timestamp"`-keyed pipeline is unchanged and the client relabels the chart axis / reference input. CDC capture picks the axis via the **Record as Turns** checkbox (persisted `cdc_axis` setting) → `/run_script` `axis` → `log_cdc_data.py --axis` → firmware `AXIS:turn|time` (`open_colorimeter_firmware/src/serial_manager.py`, in lockstep). Convert an existing Timestamp file in the CSV editor via **Timestamps → Turns** (`/convert_timestamp_to_turn`). In point mode with Turn on, a **Run mode** choice (persisted `cdc_run_mode` setting) offers **Automatic** (interval run) or **Manual** — device idles and records one Turn per **Measure now** press (`POST /measure_point` drops `log/measure_trigger.txt`, the logger sends firmware `MEASURE`; start chunk adds `MANUAL:1`). **Turn calibration**: because a Turn file has no time, each recorded Turn is treated as one concentration standard — a point-mode Turn file hides the time-point controls and shows a per-Turn concentration table (`applyTurnCalUI`/`exportTurnCal`), exporting a `Concentration,Value` calibration CSV (schema `CSV_SCHEMA_POINT_CAL_TURN`, no TimePoint); the resulting calibration JSON records `x_axis:'turn'` and omits `time`/`time-unit`, and deriving reads each Turn's value straight through the fit (`processTurnDerive`). See **Rule.md §2.27**.
- **CDC port selection is by probe, not by first match**: a PyBadge booted with `console=True, data=True` exposes **two** serial ports that are byte-identical in USB metadata (vid/pid/description/hwid/serial/interface), so `send_command.connect_to_device()` sends `PING` to each vid/pid candidate and keeps the one answering `ACK_PING` or `ERR_UNKNOWN` (the latter for firmware predating `PING`). Taking the first match landed on the console/REPL port ~half the time — the "device not responding" bug. `boot_for_CDC.py` ships `console=False` on every firmware branch as the primary defence. The port timeout is `PORT_TIMEOUT = 0.15` s (so `/measure_point` triggers are picked up fast), which makes `readline()` unsafe — all reads go through `send_command.LineReader`. Firmware bounds every CDC write (`_write_cdc`, `CDC_WRITE_TIMEOUT`/`CDC_WRITE_DEADLINE`) so a stalled host can't freeze the device. Firmware loop period is a flat ~0.174 s regardless of channel count — it is not the bottleneck. See **Rule.md §2.28**.
- **Pause/Resume a live reading**: an automatic capture (Timestamp or auto-Turn) can be held without ending it — `POST /pause_reading` / `POST /resume_reading` drop `log/control_trigger.txt` holding the desired state, the logger forwards `PAUSE`/`RESUME` to the device (`ACK_PAUSE`/`ACK_RESUME`), and the firmware freezes its session clock so timestamps stay continuous and the timeout doesn't burn. The logger also drops rows while paused, so the feature degrades gracefully against firmware predating the command (timestamps then gap). Two UI entry points: the inline **Pause reading** button on the reading-panel button line and the floating `#reading-control-fab` — a session transport that leads with a breathing dot + `RECORDING`/`PAUSED` readout, then Pause/Resume + Stop — which appears when that line scrolls out of view (at that scroll position the timer widget is off-screen too, so the bar is the only live-state indicator). Manual point-mode runs get **Measure now** instead. See **Rule.md §2.29**.
- **A live session is pushed, not polled**: while a run is in progress the browser holds `GET /stream_session` open and the server pushes `meta` / `rows` / `log` / `end` events (`src/live_stream.py` tails the log and the active CSV — path from `log/current_output.txt` — by byte offset; `static/script/live-stream.js` consumes them). This replaced a 500 ms `/get_data` chart poll that reparsed and rebuilt the whole file twice a second and a 2 s `/get_logs` poll that re-read the whole log and counted `Received:` matches by regex; manual point mode's **Measure now** now re-arms when its row lands instead of up to 2 s later. Both polls survive as the automatic fallback, gated on `liveStreamCarrying()`. `/check_status` keeps sole ownership of *why* a run ended. Opt out with the `live_stream_enabled` setting. See **Rule.md §2.31**.
- **Background music is metadata-only and online-only**: two sources in one bottom-left 🎧 widget (`static/script/music.js`), and **no audio passes through Flask** in either. *Radio* — the browser's `<audio>` connects straight to free listener-supported **https** streams from the `src/music.py` catalogue. *YouTube* — the user pastes links (there is deliberately **no search**: `search.list` burns 100 of 10,000 daily quota units, so one key shipped in the app would die instantly), `music.parse_youtube_ref()` validates them against an allow-listed host set and the keyless **oEmbed** endpoint names them, and playback belongs to YouTube's IFrame player in a **visible** ≥200 px video pane as its terms require. Never extract, download, proxy or cache the media (no `yt-dlp`-style path) — that is the anti-pattern the whole design exists to avoid. **Spotify is impossible for free** (Web Playback SDK needs Premium + OAuth) and should not be re-attempted. The queue lives in `music_queue.json` (`src/music_queue.py`) rather than `localStorage`, which a restart clears (§2.20). Widget mounts only when `music_enabled` is on *and* both `navigator.onLine` and the server probe say online; it unmounts on `offline`. Settings: `music_enabled` (default **off**), `music_source`, `music_station`, `music_volume`, `music_loop_mode` (`off`/`one`/`all`), `music_shuffle`. See **Rule.md §2.32 / §2.32.1**.
- **One design system, tokens first**: every colour/font/radius/shadow comes from the token block at the top of `static/style.css` (`:root` light, `body.dark` re-stepped for graphite) — never a raw hex or a gradient in a rule. `--accent` is bromophenol blue, derived from the **assay**, because the device has **no selectable wavelength** (a TSL2591 per active mux channel; the host only ever learns Measurement / Unit / Concentration / ConcenUnit + `Value:N`) — so no UI names or colour-codes an nm value, and a "channel" is a **source**. Two materials: chrome is flat + hairline-bounded (`--r-flat` fields, `--r-press` pressables, no glass, no hover lift), data surfaces get the space. Type is self-hosted **IBM Plex** — Sans for prose, **Mono with tabular figures for every measured value / field / axis tick**, Condensed uppercase for panel labels. Multi-source series are ordered, so they wear the **sequential ramp** `--ramp-1..10` via `sourceRamp(n)` (`index.js`; `AppState.plotColors` is a getter over it), never a cycled rainbow. The signature is the **session strip** (`#session-strip`, `drawSessionStrip()` in `cdc-logging.js`): a fixed chart-recorder trace of the live run, one line per source, that *is* the recording indicator — it greys and freezes on pause and reads `AppState.responseData` rather than fetching anything. It carries state + elapsed + next + latest/rows, so the top-right `#session-timer` widget is now mounted **only** when the strip is off; `tickSessionTimer()` still computes the clocks once and writes both. Setting: `session_strip_enabled`. See **Rule.md §2.33**.
- **The redesign is switchable**: `ui_style` (default `instrument`, App Settings → General) picks the visual language; **`classic`** restores the previous look through a `body.ui-classic` override layer in `style.css` — **generated** by `tools/gen_classic_style.py` as a declaration-level diff of v1.3.11's sheet (a token override alone cannot work: the redesign rewrote ~519 literals *inside* rules, and a custom property does not override a concrete declaration) (indigo/purple gradients, blurred cards, 12px radius, Inter/Outfit, the 16-colour series palette, pill toggle, orb splash) — not a second stylesheet. The class is stamped on `<body>` by the index render (no flash); `isClassicUI()` in `index.js` reads the class and gates the two JS differences (`sourceRamp()` → `CLASSIC_PLOT_COLORS`, `stripEnabled()` → false, so the timer widget returns). Bug fixes made during the redesign are shared by both styles, never flagged. See **Rule.md §2.34**.
- **Virtual controller — the device's keypad, on screen**: a collapsed-by-default panel (`static/script/device-control.js`, `#device-control-section`) that shows what the device is doing and works its eight buttons from the app. `src/device_link.py` opens the CDC port **only while no reading session is running**, so the one-owner rule of Rule §2.28/§2.29 still holds: every route (`GET /device/state`, `POST /device/button`, `POST /device/channels`) answers **409** while `state.process` is alive, and `/run_script` closes the link before spawning the logger. The firmware answers `STATE?` with a one-line `key=value;` snapshot — not JSON, because the board guards every screen allocation against MemoryError — with an identical field list on all four firmware branches (fields a build lacks are sent empty, never omitted). The panel's real job is **labelling**: `menu` saves in Settings, opens the menu in Measure, dismisses a message, and the keypad cannot say which, so `DEVICE_BUTTON_FUNCTIONS` mirrors the firmware's mode handlers and buttons with no effect stay visible but dimmed. Where builds genuinely differ the firmware says so in `caps` (`channels`, `selsensor`, `uvchannel`) and the client branches on that, never on a version. **`BTN:left` in MEASURE is refused** — it would start the HID keyboard fallback and type readings into whatever window has focus on the host. **Active channels** (open-extra) are set with `CHANNELS:0,3` → `Colorimeter.set_active_channels()`, which rebuilds sensors, gain/itime cycles, blanks (dropping `is_blanked`) and the measure screen; refused mid-session because the channel count *is* the column count, and **runtime-only** because CircuitPython mounts its own filesystem read-only. Settings: `device_control_enabled` (default on), `device_state_poll_ms` (default 1500). See **Rule.md §2.35**.
- **Report system**: Reports are HTML files saved to `report/<subject>/`. CRUD via `/save_report`, `/export_to_report`, `/get_report_subjects`, `/get_report_items`, `/delete_report_subject`, `/copy_report_subject`, `/rename_report_subject`.
- **Startup progress reporter**: `main.py` writes `pct label\n` to a FIFO (`/tmp/easyokapi_progress.pipe` on Mac) so launch scripts can show a progress bar.
- **CLI flags**: `--port`, `--alias`, `--verbose` / `-v`, `--mem-monitor`, `--no-browser` (suppress the startup browser-open tab; passed automatically by restart relaunches so the one-shot reset-display marker isn't stolen by a second tab — see Rule.md §2.20).
- **User-guide translations**: Step text for the interactive user guide lives in `guide_translations/<lang>.json` (one file per language: `en` is the baseline in `guide_training.json`; `vi`, `zh`, `fr`, `ja`, `ru` are in `guide_translations/`). Each file contains guide topics as objects with `id`, `steps` (array of strings), and `queries` (keyword list for AI matching). When adding or editing guide steps, update both `guide_training.json` (EN) and all language files in `guide_translations/`.
- **UI localization (i18n)**: the interface is translatable into the same 6 languages as the AI chat (`en`/`vi`/`zh`/`fr`/`ja`/`ru`), selected via the **`ui_language`** user setting (App Settings → General). Catalogs are flat key→string JSON in `ui_translations/<lang>.json` (`en.json` is the English baseline; missing keys fall back to English), resolved from `state.bundle_dir` by `src/i18n.py`. `core_routes.index()` injects `UI_LANG`/`UI_STRINGS`; `static/script/i18n.js` applies them to `[data-i18n*]` elements and exposes `t(key, fallback)` for dynamic strings. **Technical terms stay in English** (mode names, units, Absorbance, maxRate, rSquared, CSV/JSON/Excel, brand names). Adding a UI string means adding its key to **all six** catalogs in lockstep. See **Rule.md §2.22**.
- **AI answer feedback + learned matcher weights**: each assistant answer carries a 👍/👎 (`/ai/feedback` → `src/ai_feedback.py`). Ratings append to `ai_feedback.jsonl`; a rating on a **locally matched guide** also tunes that guide's coefficient in `ai_guide_weights.json`, which `ai_assistant._match_guide_example` folds into the score (👍 raises + reinforces query vocabulary, 👎 suppresses). LLM answers are logged only (Groq can't be retrained). Both files live in `state.script_dir`, are gitignored, and are preserved across updates. App Settings → **AI Assistant** adds an `ai_feedback_enabled` opt-out, **Export feedback** (`/ai/feedback/export`) and **Reset learning** (`/ai/feedback/reset`); when off, the row is hidden, the route no-ops, and learned weights are ignored. See **Rule.md §2.13**.
- **Tests live in `tests/`** — `test_utils.py`, `test_core_logic.py`, `test_data_processing.py`, `test_app.py`, `test_hwid.py`, `test_activation.py`, `test_i18n.py`, `test_live_stream.py`, `test_music.py`, `test_ai_guide_matching.py`, `test_ai_feedback.py`, `test_ai_robustness.py` (deterministic dev/proxy parity, truncation notice, empty-reply retry), `test_device_link.py`. Run with `pytest tests/ --ignore=venv`.
- **Hardware-locked activation** (frozen builds): a permanent license token is bound to one machine via an `hwid` claim (`src/hwid.py`) and RS256-signed by the server (`ACTIVATION_PRIVATE_KEY`), verified offline with the embedded public key (`src/activation_pubkey.py`). Copying `activation.json`/the install folder to another machine fails the check. The Windows installer PowerShell mirrors the `hwid` recipe byte-for-byte — keep them in lockstep. Server side lives on the `online` branch (`license_machines` seat table, `/api/activate` binding). See **Rule.md §2.17**.
- **Uninstaller delivery across updates**: `Uninstall.exe` lives *inside* the directory the in-app update swaps, so the updater used to carry the old one across — meaning an updated install kept its original uninstaller forever and no uninstaller fix could reach existing users. The Windows bundle now ships an `Uninstall.exe` (CI compiles `setup-frozen.nsi` with **`/DUNINSTALLER_ONLY`** — a payload-free silent stub — and runs it *before* zipping the bundle), and `_WIN_SWAP_PS1` prefers the bundled copy, falling back to carrying the old one across. Note an updater's fixes always land **one cycle late** (the *old* `update_service.py` drives the swap that installs the new build). On posix the uninstaller sits one level *above* the swapped dir (`/opt/EasyOKAPI/uninstall.sh`, `…/Contents/Resources/uninstall.command`), so it survived the swap but was never *updated*: both bundles now ship their uninstaller inside the onedir and `_build_posix_swap_script` copies it up into the parent after swapping (best-effort — `/opt` is root-owned while the app runs as the user). See **Rule.md §2.25**.
- **Update scratch files are swept on startup**: the binary swap writes helpers into the data root (`_update_swap.ps1`, `_update_coordinator.ps1`, `_update_swap_result.txt`, `_update_staging/`, posix `_update_*_swap.sh`) and then *exits* so the detached helper can run, so it can never clean up after itself — every update used to leave a growing pile in the user's `EasyOKAPI` folder. `update_service.cleanup_stale_artifacts()` runs from a `main.py` daemon thread on startup and no-ops while a swap is pending retry. See **Rule.md §2.26**.
- **Seat release on uninstall**: a seat is held until explicitly released, so every uninstaller calls **`POST /api/license/release`** (online branch) before deleting anything — otherwise a removed install holds the license cap forever and the user's next machine is refused. There is no web session at uninstall time, so the machine's own permanent token authenticates the call and its `hwid` claim names the one seat it may free (`_release_license_seat` in `installer-mac/uninstall.command` + `installer-linux/uninstall.sh`, `release-seat.ps1` in `installer-win/setup-frozen.nsi`, `activation.release_machine()` in Python). Best-effort and idempotent — never blocks an uninstall. A **revoked** seat or **banned** account is refused, so freeing a seat can't escape the kill-switch. macOS frozen (drag-to-Trash) has no hook — those users deactivate from their account. See **Rule.md §2.17**.
- **Admin license revocation + account ban** (frozen builds): an admin can deactivate a customer's license server-side even though the permanent token still verifies offline. Two strengths: **Revoke** disables a per-machine seat (`revoked` flag on `license_machines`); **Ban** disables a whole account (`banned` flag on `users`) — blocking web sign-in, download, activation, and app usage on every machine. Server (`online`): shared-secret `POST /api/admin/revoke` + `POST /api/admin/ban` (both by email, send a notification email) + `GET /api/admin/lookup` (+ `/api/admin/users`) + `POST /api/admin/machines/remove` (`{email, hwid|all}` — frees a seat the customer cannot free themselves, e.g. a dead machine or an uninstall by a build predating the seat release; refuses a **revoked** seat with 409 unless `force`, since deleting the row would let that machine re-activate unrevoked and escape the kill-switch), and `POST /api/license/check` (the client poll). A revoked seat or banned account fails the AI-proxy / auto-update machine check immediately; a banned account makes `/api/license/check` reply `revoked` + code `account_banned`. Client (`src/activation.py`): `check_revocation()` polls `/api/license/check` and caches the verdict in `license_status.json`; `license_state()` returns `active` / `revoked` (sticky) / `banned` (sticky; from the `account_banned` code) / `needs_recheck` (grace lapsed offline → reverify gate). `main.py` `_enforce_license` gate serves `license_blocked.html` (revoked) / `license_banned.html` (banned) / `license_reverify.html`. Grace window via `LICENSE_GRACE_SECONDS` (default 7d), poll interval via `LICENSE_CHECK_INTERVAL` (default 6h). The local admin console lives on the secret `offline` branch (`admin/`).

---

## Documentation Update Rule

After any significant change, update:
- `Rule.md` if you introduce new behavioral constraints or anti-patterns.
- `easyokapi-knowledge/EASY OKAPI.md` if you add files, routes, modules, or change architecture.
- `CLAUDE.md` (this file) if the at-a-glance summary above becomes stale.

---

## Settings Coverage Rule

Whenever a new feature introduces a user-facing behaviour that could reasonably vary per machine or per preference, ask: **should this be a user setting?**

Checklist to run mentally for every new feature:
- Does it have a hardcoded value a user might want to change (size, count, threshold, default state)?
- Does it default a UI element to a particular state (collapsed/expanded, mode, sort order)?
- Does it control how much data is shown or how the layout behaves?

If any answer is yes, add the setting to `src/user_settings.py` (`DEFAULTS` + validation in `save()`), expose it in the settings modal in `static/script/init.js` (`SETTINGS_DEFAULTS` + form field), apply it on page load (via `USER_SETTINGS` in `index.html` or `init.js`), and add backend tests in `tests/test_user_settings.py`.

**Anti-pattern**: do not hardcode UI dimensions, row limits, default states, or feature flags directly in CSS or JS when a user might reasonably want a different value on their machine.

**i18n coverage**: any new user-facing string (label, heading, button, tooltip, placeholder, or `Swal.fire` text) must get a translation key in **all six** `ui_translations/<lang>.json` catalogs and be wired via `data-i18n*` (static HTML) or `t('key', 'English')` (dynamic JS) — keep technical terms in English. See **Rule.md §2.22**.

**Exception — the data-root location**: the user-selectable data folder (frozen builds) is **not** a `user_settings.py` key, because `user_settings.json` lives *inside* the data root (chicken-and-egg). It is stored in a `.easyokapi_dataroot` pointer file beside the default location and managed by `src/data_root.py` + `/data_root` (GET/POST). The Windows installer (`setup-frozen.nsi`) also lets the user choose this folder at install time (writing the same pointer). Relocating **moves** a non-default folder (the default is kept as a fallback copy); the data folder may not be the EasyOKAPI program folder. The move is deferred-commit: `POST /data_root` only **previews** the change (validates, reports move-vs-copy) and the UI confirms, offering **Restart now** (`/data_root/restart` commits the move, then relaunches in place via `update_service.restart_after_delay()` and serves `restarting.html`, which auto-reloads the tab once the new instance is up) or **Cancel** (a no-op — nothing was moved). See **Rule.md §2.19**.

**Default display on restart**: any restart (data-folder relocation or applied update) brings the app back up in the **default display** — kinetics mode, fresh per-view UI state — rather than restoring the previous tab's `localStorage` layout. The restart routes call `state.mark_reset_display_pending()` (a one-shot sentinel in `default_data_root` that survives the process restart); the next index render consumes it and passes `reset_display` → `const RESET_DISPLAY` to `index.html`, which clears per-view `localStorage` (keeping `theme`/AI prefs) before `init.js` forces kinetics mode. See **Rule.md §2.20**.
