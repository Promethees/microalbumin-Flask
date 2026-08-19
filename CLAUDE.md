# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

## Start Here

Before writing any code, read these two files in order:

1. **`Rule.md`** — hard constraints, coding rules, anti-patterns. It is the source of
   truth; this file is only an index into it.
2. **`easyokapi-knowledge/EASY OKAPI.md`** — architecture, file map, route table, data formats.

Every invariant below is a one-line reminder plus a `Rule.md §x` pointer. **Read the
rule before acting on the reminder** — the rationale is what stops the anti-pattern
recurring, and it lives in `Rule.md`, not here.

---

## Commands

```bash
# Install (Python 3.12.11 via pyenv; requirements-dev.txt adds test-only deps)
pip install -r requirements.txt -r requirements-dev.txt

# Run (default port 5099, alias easyokapi.com)
python main.py
python main.py --port 5099 --alias easyokapi.com
python main.py --verbose        # HTTP logs + backend prints
python main.py --mem-monitor    # tracemalloc growth tracking
python main.py --no-browser     # no startup tab (restart relaunches pass this — §2.20)

# Test
pytest tests/ --ignore=venv
pytest tests/test_utils.py
pytest tests/ -k "test_ping"
```

**Runtime: Python 3.12.11 + Flask 3.0.3** (same pins as `online`). Windows installs
**3.12.10** — 3.12.11 is security-only with no Windows binary installer. Flask-3 rules
that bite: `send_file(download_name=…)` (not `attachment_filename`), no route
registration after the first request, and an unconsumed `stream_with_context` response
corrupts the next request's context. **Rule.md §2.37**.

---

## Project in One Line

Flask-based local desktop app that reads a PyBadge colorimeter over USB/HID and
visualizes bio-sensor CSV data in a browser. Single-user, no sessions, no SocketIO,
no cloud.

**Current version: 1.5.1**

---

## Architecture at a Glance

```
main.py (thin entry point)
  └── registers 8 Flask Blueprints from src/routes/
        ├── core_routes.py     — ping, index, shutdown, browse, JSON cal, report subjects
        ├── file_routes.py     — CSV/JSON CRUD, export, merge, edit locks, manual folder/CSV creation
        ├── report_routes.py   — report subject/item CRUD + Excel report export
        ├── hardware_routes.py — reading-session control + virtual-controller + CIRCUITPY config routes
        ├── math_routes.py     — server-side regression API
        ├── ai_routes.py       — AI assistant: chat, settings, activation, feedback
        ├── music_routes.py    — background music: catalogue, link resolve, queue (metadata only)
        └── update_routes.py   — auto-update: check, apply (SSE), finalize

src/                       (34 modules — full table in EASY OKAPI.md §2.2)
  ├── state.py             ← global state singleton (process, paths, delimiter, PRODUCTION_MODE)
  ├── data_root.py         ← relocatable data root (.easyokapi_dataroot pointer)
  ├── validators.py        ← @validate_json decorator
  ├── security.py          ← request-origin guard (CSRF + DNS-rebinding)
  ├── i18n.py              ← UI translation catalogs (ui_translations/, 7 languages)
  ├── event_logger.py      ← /event_log sink → log/events/
  ├── live_stream.py       ← SSE tail of a live session (log + active CSV, by byte offset)
  ├── device_link.py       ← idle-time CDC control link (STATE?/BTN:/CHANNELS:/MENU?/CONC?/TIMING?)
  ├── device_config.py     ← read/write the device's configuration.json on its CIRCUITPY drive
  ├── sentinels.py         ← non-numeric value tokens (OVFL / NONE / INF)
  ├── math_ops.py          ← scipy/numpy regression (5 fit models)
  ├── excel_formula.py     ← paste-ready Excel formulas from the same 5 models
  ├── ai_assistant.py      ← Groq chat client, MCP tool engine, multilingual prompts
  ├── ai_feedback.py       ← 👍/👎 log + learned guide-matcher weights
  ├── music.py             ← radio catalogue + connectivity probe + YouTube link parsing
  ├── music_queue.py       ← persisted YouTube play queue (music_queue.json)
  ├── user_settings.py     ← preferences + SUPPORTED_LANGUAGES (the 7-language registry)
  ├── update_service.py    ← auto-update: source overwrite or frozen binary swap
  ├── hwid.py              ← per-machine fingerprint (hardware-lock basis)
  ├── activation.py        ← license gate: RS256 verify + hwid claim + revocation poll
  └── activation_pubkey.py ← embedded RS256 public key (verify-only)

static/script/             (21 files — full table in EASY OKAPI.md §2.4)
  ├── cdc-logging.js       ← reading session: run/pause/stop, timer, session strip (§2.33)
  ├── live-stream.js       ← SSE live-session client (polls are the fallback)
  ├── device-control.js    ← virtual controller panel
  ├── report.js            ← report generation + subject CRUD UI
  ├── i18n.js              ← t() + applyTranslations over [data-i18n*]
  ├── a11y.js              ← chart data tables, sortable headers, scrollable regions
  ├── ai-chat.js           ← floating AI chat widget
  ├── music.js             ← floating music widget (radio + YouTube, online-only)
  ├── user-guide.js        ← interactive spotlight user guide
  └── tooltip.js           ← [data-hint] hover hints (replaces native title=)

static/fonts/              ← self-hosted IBM Plex + classic.css; no Google Fonts request
static/style.css           ← design tokens (:root + body.dark), then all UI styling (§2.33)
ui_translations/           ← en.json baseline + vi/zh/fr/ja/ru/ko
guide_translations/        ← user-guide step text per language (en baseline = guide_training.json)
report/                    ← saved HTML reports, by subject subdirectory
user_settings.json         ← user preferences (ui_language, ui_style, ai_feedback_enabled, …)
```

---

## Key Invariants

**Structure**
- Global state lives in `src/state.py`, never in `main.py` globals.
- All routes go in blueprints under `src/routes/`. Never add one to `main.py`.
- `@validate_json` (from `validators.py`) is mandatory on every POST route that accepts
  JSON. Documented exemption: `/download_event_logs` (GET+POST, validates inline).
- Tests live in `tests/` (38 files). CI runs the whole suite on 3.12 before any build.

**Math — three implementations, one behaviour**
- Regression runs **server-side** in `math_ops.py`. The same 5 fit models are also
  implemented in `math_ops.evaluate_curve()` (`/calculate_concentration`, the Quick
  concentration calculator) and `src/excel_formula.py` (`/export_cal_excel_formula`).
  **Change one, change all three.** `calculate.js` only renders the preview.

**Hardware — the serial port has exactly one owner**
- **CDC port selection is by `PING` probe, not first match.** A PyBadge exposes two
  byte-identical serial ports; taking the first landed on the REPL ~half the time.
  `PORT_TIMEOUT = 0.15 s` makes `readline()` unsafe — use `send_command.LineReader`.
  **§2.28**
- **Turn axis:** a raw file's X column is `Timestamp` *or* `Turn`, never both. Turn files
  drive point-mode calibration (each Turn is one concentration standard) and manual
  **Measure now** capture. Firmware `AXIS:` is in lockstep. **§2.27**
- **Pause/Resume** holds a run without ending it — the firmware freezes its session
  clock, so timestamps stay continuous. **§2.29**
- **A live session is pushed, not polled** — `GET /stream_session` (SSE). The old
  `/get_data` + `/get_logs` polls survive as the fallback, gated on
  `liveStreamCarrying()`. `/check_status` keeps sole ownership of *why* a run ended.
  Setting: `live_stream_enabled`. **§2.31**
- **Virtual controller** (`device_link.py` + `device-control.js`): opens the port **only
  while no session runs** — every `/device/*` route answers **409** while
  `state.process` is alive, and `/run_script` closes the link first. Branch on the
  firmware's `caps` list, never on a version. `BTN:left` in MEASURE is refused (it would
  start the HID fallback and type into the host). Screen-touching setters (`MENU:`,
  `CONC:`, `TIMING:`) are queued and applied from the firmware's main loop. Channel
  changes are runtime-only unless written to CIRCUITPY via `device_config.py`. **§2.35**

**Design**
- **Tokens first.** Every colour/font/radius/shadow comes from the token block at the
  top of `static/style.css` — never a raw hex or a gradient in a rule. Multi-source
  series use the sequential ramp `sourceRamp(n)`, never a cycled rainbow. The **session
  strip** is the recording indicator and reads `AppState.responseData` rather than
  fetching. Setting: `session_strip_enabled`. **§2.33**
- **The redesign is switchable.** `ui_style` = `instrument` (default) or `classic`;
  classic is a **generated** override layer in `style.css` (`tools/gen_classic_style.py`),
  not a second stylesheet. `isClassicUI()` gates the two JS differences. Standalone
  pages branch server-side instead. Bug fixes are shared by both styles. **§2.34**

**Content**
- **UI localization:** 7 languages (`en`/`vi`/`zh`/`fr`/`ja`/`ru`/`ko`), one registry —
  `SUPPORTED_LANGUAGES` in `user_settings.py`. Catalogs are flat key→string JSON in
  `ui_translations/<lang>.json`; missing keys fall back to English. Adding a UI string
  means adding its key to **all seven** in lockstep. Technical terms stay in English.
  **§2.22**
- **User-guide translations:** `guide_training.json` (EN baseline) +
  `guide_translations/<lang>.json` for the other six. Edit a step → edit all seven.
- **AI answer feedback:** 👍/👎 → `ai_feedback.jsonl`; a rating on a **locally matched
  guide** also tunes `ai_guide_weights.json`, which the matcher folds into its score.
  LLM answers are logged only. Opt-out: `ai_feedback_enabled`. **§2.13**
- **Background music is metadata-only and online-only** — no audio passes through Flask,
  in either source. Never extract, download, proxy or cache the media; that
  (`yt-dlp`-style) is the anti-pattern the whole design exists to avoid. There is
  deliberately no YouTube search (quota), and Spotify is impossible for free — do not
  re-attempt either. Default **off**. **§2.32**
- **Report system:** HTML files under `report/<subject>/`, CRUD via `report_routes.py`.

**Distribution & licensing**
- **Hardware-locked activation:** an RS256-signed permanent token carries an `hwid`
  claim, verified offline. Copying the install folder to another machine fails. The
  Windows installer PowerShell mirrors the `hwid` recipe **byte-for-byte** — keep them
  in lockstep. **§2.17**
- **Revocation + ban:** `check_revocation()` polls `/api/license/check` and caches the
  verdict; `license_state()` returns `active` / `revoked` / `banned` (both sticky) /
  `needs_recheck`. `main.py` `_enforce_license` serves the matching page. Grace via
  `LICENSE_GRACE_SECONDS` (7d), poll via `LICENSE_CHECK_INTERVAL` (6h). Server side is
  on `online`; the admin console is on the secret `offline` branch.
  `check_revocation_detailed()` also reports **why** a check failed — `no_internet` /
  `dns_failure` / `service_down` / `no_token` / `unknown` — so the reverify page says
  whether the machine's network or our service is at fault, apologises, and offers a
  pre-filled report to the developer. **§2.17**
- **Service endpoints fail over:** one deployment answers on several names, so
  `activation.service_request()` walks `service_bases()` (last-known-good →
  `AI_SERVICE_URL` → `FALLBACK_SERVICE_URLS`) and skips any base that errors *or*
  answers with something that is not our API — a parked domain returns a valid
  HTML 404. The winner is cached in `service_endpoint.json`. Streaming callers
  (update download, AI proxy) use `service_base()`. **§2.17**
- **Seat release on uninstall:** every uninstaller calls `POST /api/license/release`
  before deleting anything, authenticated by the machine's own token. Best-effort and
  idempotent, never blocks an uninstall. A revoked seat or banned account is refused, so
  freeing a seat cannot escape the kill-switch. **§2.17**
- **Uninstaller delivery:** an updater's fixes always land **one cycle late** — the *old*
  `update_service.py` drives the swap that installs the new build. Both bundles now ship
  their own uninstaller inside the onedir. **§2.25**
- **Update scratch files are swept on startup, not on exit** — the swapping process
  exits so the detached helper can run, so it can never clean up after itself. **§2.26**
- **Frozen builds:** see `ENCODE_BUILD_PLAN.md` (feature-complete, cutover not taken).

**Misc**
- **Startup progress reporter:** `main.py` writes `pct label\n` to a FIFO
  (`/tmp/easyokapi_progress.pipe` on Mac) so launch scripts can show a progress bar.

---

## Documentation Update Rule

After any significant change, update:
- `Rule.md` if you introduce new behavioral constraints or anti-patterns.
- `easyokapi-knowledge/EASY OKAPI.md` if you add files, routes, modules, or change architecture.
- `CLAUDE.md` (this file) if the at-a-glance summary above becomes stale.
- `README.md` if the change is visible to a user installing or running the app.

Keep this file an **index**. New detail belongs in `Rule.md` with a one-line pointer here.

---

## Settings Coverage Rule

Whenever a new feature introduces a user-facing behaviour that could reasonably vary per machine or per preference, ask: **should this be a user setting?**

Checklist to run mentally for every new feature:
- Does it have a hardcoded value a user might want to change (size, count, threshold, default state)?
- Does it default a UI element to a particular state (collapsed/expanded, mode, sort order)?
- Does it control how much data is shown or how the layout behaves?

If any answer is yes, add the setting to `src/user_settings.py` (`DEFAULTS` + validation in `save()`), expose it in the settings modal in `static/script/init.js` (`SETTINGS_DEFAULTS` + form field), apply it on page load (via `USER_SETTINGS` in `index.html` or `init.js`), and add backend tests in `tests/test_user_settings.py`.

**Anti-pattern**: do not hardcode UI dimensions, row limits, default states, or feature flags directly in CSS or JS when a user might reasonably want a different value on their machine.

**i18n coverage**: any new user-facing string (label, heading, button, tooltip, placeholder, or `Swal.fire` text) must get a translation key in **all seven** `ui_translations/<lang>.json` catalogs and be wired via `data-i18n*` (static HTML) or `t('key', 'English')` (dynamic JS) — keep technical terms in English. See **Rule.md §2.22**.

**Exception — the data-root location**: the user-selectable data folder is **not** a `user_settings.py` key, because `user_settings.json` lives *inside* the data root (chicken-and-egg). It is stored in a `.easyokapi_dataroot` pointer file beside the default location and managed by `src/data_root.py` + `/data_root` (GET/POST). The Windows installer (`setup-frozen.nsi`) also lets the user choose this folder at install time. The move is **deferred-commit**: `POST /data_root` only previews (validates, reports move-vs-copy); **Restart now** (`/data_root/restart`) commits and relaunches, **Cancel** is a no-op. See **Rule.md §2.19**.

**Default display on restart**: any restart (data-folder relocation or applied update) brings the app back up in the **default display** — kinetics mode, fresh per-view UI state — not the previous tab's `localStorage` layout. The restart routes set a one-shot sentinel in `default_data_root` that survives the process restart; the next index render consumes it and passes `reset_display` → `RESET_DISPLAY` to `index.html`, which clears per-view `localStorage` (keeping `theme`/AI prefs) before `init.js` forces kinetics mode. See **Rule.md §2.20**.
