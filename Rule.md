# Rule_online.md — AI Coding Rules for the `online` Branch

> **Branch purpose**: This branch hosts the **production web application** deployed on **Heroku** at [https://www.easyokapi.cbbiotec.vn/](https://www.easyokapi.cbbiotec.vn/). It is a **multi-user, server-hosted** version — users access it through their browser with no local installation.

---

## 1. Project Identity

| Field | Value |
|---|---|
| **App name** | Easy OKAPI |
| **Domain** | Colorimeter data visualization for bio-sensor experiments |
| **Framework** | Flask (Python 3.12.11) + Jinja2 templates |
| **Real-time** | Flask-SocketIO with eventlet async mode |
| **Deployment** | Heroku (`Procfile`: `gunicorn -k eventlet --workers 1 main:app`) |
| **Runtime** | `runtime.txt` → `python-3.12.11` |
| **Live URL** | `https://www.easyokapi.cbbiotec.vn/` |

---

## 2. Critical Rules for AI Coding

### 2.0 Mandatory First Step: Read EASY OKAPI.md

- **BEFORE executing any commands like `ls -R` or `find` to explore the codebase**, you **MUST** read `easyokapi-knowledge/EASY OKAPI.md` first.
- This document holds the full functional summary, architecture, codebase maps, and directory structure of the project. Prioritizing reading this prevents wasting tokens on excessive directory listings and codebase guessing.

### 2.1 Data Storage — NEVER Use Local Filesystem for User Data

- All user CSV and JSON data must go through `get_user_data()` → in-memory `USER_DATA` dict.
- **Never** use `open()`, `os.path`, or `Path` to read/write user files on the server filesystem.
- Default sample data (`csv/multi.csv`, `csv/single.csv`, `json/exp_kinetics.json`, `json/exp_point.json`) is loaded into memory on first request via `init_user_data()`.

### 2.2 Multi-User Session Isolation

- Every route that accesses user data **must** call `get_user_data()` (which internally calls `get_user_id()` to get the session-bound `user_id`).
- Never use global variables to store per-user state outside of `USER_DATA`.
- Use `user_csv_lock` for thread-safe CSV export operations.

### 2.3 Static Files & Build

- **Development source** is in `static/script/` (JS) and `static/style.css` (CSS).
- **Production serves from `static/dist/`**. The Flask app is set to `static_folder='static/dist'`.
- After modifying any JS or CSS, you **must** run `npm run build` before deploying.
- **Never** edit files in `static/dist/` directly — they are generated artifacts.
- The `index.html` template references scripts via `{{ url_for('static', ...) }}` which resolves to `static/dist/`.

### 2.4 No HID / No Local Hardware

- This branch has **no HID logging** functionality. Do not add USB/serial device communication code.
- The `/api/current_output` endpoint returns `{"exists": False}`.
- Any references to `log_hid_data.py`, `script_monitor.py`, `browser_mgt.py`, or `send_command.py` are **not present** on this branch.

### 2.5 Google Drive Integration

- OAuth uses encrypted credentials (`credentials.enc`) decrypted with `GOOGLE_ENCRYPTION_KEY`.
- Session recovery logic handles cross-site cookie drops by encoding `user_id` in the OAuth `state` parameter.
- Google Drive operations are in `src/google_drive_service.py`; UI logic in `static/script/drive-integration.js`.
- Drive mode states: `guest` (default, uses sample data) → `connected` (uses Drive-synced data).

### 2.6 Real-Time Updates

- The app uses **Flask-SocketIO** with **eventlet** for real-time UI updates.
- After any CRUD operation on user files, emit the corresponding socket event:
  - CSV changes: `socketio.emit('update_csv')`
  - JSON changes: `socketio.emit('update_json', {'mode': mode})`
- The Heroku Procfile uses `-k eventlet --workers 1` — **only 1 worker** is allowed with SocketIO.

### 2.7 Frontend Conventions

- **Global state** lives in `AppState` object (defined in `index.js`).
- Use utility short-hands from `short-hands.js` (`$id`, `$text`, `$hidden`, `$toggleClass`, `fetchJSON`).
- SweetAlert2 (`Swal`) is used for dialogs and confirmations (loaded via CDN in `index.html`).
- Chart.js is used for plotting (loaded via CDN).
- MathJax is used for rendering mathematical equations.
- **Light/dark theme** is toggled via `body.light` / `body.dark` classes.
- Three measurement modes: `kinetics`, `point`, `calibrate`. Mode switching triggers `switchingModes()` and `switchingCalModes()`.
- "Source" terminology is used (not "sensor") for data sources.
- **Point-mode reference unit**: the "Set reference point to export" input (`#exp-json-time-value`) is entered in the currently-selected `#time-unit`; its label and value rescale whenever `#time-unit` changes (`refreshExpTimeValueForUnit` in `init.js`). Estimates use the selected unit, but **exports always convert the reference point to minutes** (`generatePointData` in `data-handling.js`) so calibration files stay in minutes (`TimeUnit: minute`).

### 2.8 Security & Production

- `ProxyFix` is applied for HTTPS behind Heroku's proxy.
- Session cookies are configured: `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_SAMESITE='Lax'`, `SESSION_COOKIE_HTTPONLY=True`.
- Max upload size: 16MB (`MAX_CONTENT_LENGTH`).
- CSV content is validated against strict regex patterns before saving.
- JSON content is validated as parseable before saving.
- File names are sanitized with `werkzeug.utils.secure_filename`.
- `measMode` parameter in `/export_data` must be validated as `kinetics` or `point` before use.
- `mode` parameter in `/get_json_content` must be validated as `kinetics` or `point`.
- `threshold_val` in `/export_cal_coefs` must be converted with try/except and clamped to [0, 1].
- `/export_report_excel` enforces `len(items) <= 500` and `len(title) <= 255`.

### 2.9 Frontend XSS Prevention

- **Never** insert server-provided strings (filenames, subject names, JSON keys/values) into `innerHTML` or HTML attribute values via template literals without escaping.
- Use `_escHtml(s)` (defined in `navigation.js` and `data-handling.js`) for HTML text context and HTML attribute values.
- Use `JSON.stringify(value)` to pass string arguments inside `onclick="func(…)"` attributes — this is the safe pattern for table row buttons.
- Prefer `textContent` over `innerHTML` whenever the content is plain text (no intentional markup).
- Build complex DOM nodes with `document.createElement` + `textContent` instead of `innerHTML` template strings when user-controlled data is involved.

---

### 2.10 AI Assistant — Groq Cloud LLM

- The AI assistant uses **Groq API** (`https://api.groq.com`) — never Ollama or a local LLM.
- `GROQ_API_KEY` and `AI_MODEL` are read from environment variables via `src/config.py` (`Config.GROQ_API_KEY`, `Config.AI_MODEL`).
- Default model: `openai/gpt-oss-20b` (GPT-OSS reasoning model). Override via `AI_MODEL` env var on Heroku.
  - GPT-OSS models spend completion tokens on reasoning; `_groq_chat` sets `reasoning_effort="low"` and a larger `max_tokens` for any `openai/gpt-oss*` model so answers aren't truncated. Reasoning is returned in a separate field, not `content`.
- Settings are stored **per-session** in Flask `session['ai_settings']` via `src/ai_settings.py`. No file-based persistence.
- The AI blueprint is `ai_bp` in `src/routes/ai_routes.py`, mounted at `/ai/*`.
- Routes: `GET /ai/status`, `GET|POST /ai/settings`, `POST /ai/chat`, `GET /ai/guides`.
- **No pull_model/pull_status routes** — model management is handled by Groq, not the app.
- Chat uses **SSE streaming** (`text/event-stream`). The generator in `chat_stream()` emits `{"type": "chunk"|"guide"|"error", ...}` events; the final event is `[DONE]`.
- Tool execution uses `user_data` from `get_user_data()` (in-memory per-session CSV/JSON store). Never reads from local filesystem.
- `get_hardware_status` tool is **absent** from the online TOOLS list (no hardware in online).
- `trigger_custom_steps` valid CSS IDs match the online UI — no hardware IDs (`#run-script-btn`, `#log-hid-data`, etc.).
- `guide_training.json` and `guide_translations/*.json` are committed to the repo (gitignored by `*.json`, but explicitly un-ignored in `.gitignore`).
- Conversation history is **client-side only** (`AI.messages` array in `ai-chat.js`).
- Supported languages: `en`, `vi`, `zh`, `fr`, `ja`, `ru`. Active language sent per request as `language` field.
- `ai-chat.js` in production is built to `static/dist/ai-chat.min.js` via `npm run build`. `OkapiAI` is in `MANUAL_RESERVED_NAMES` in `build.js`.

---

### 2.11 Concentration Unit + CSV↔JSON Identity

- **Concentration unit (`# ConcenUnit`)**: the unit a concentration is expressed in — the `# Concentration:` metadata of a raw timeseries CSV, or the `Concentration` column of a calibration CSV. One of **`ng/µL`, `nM`, `%`** (`CONCEN_UNITS` in `src/file_path.py`, the single source of truth — injected into the page as the `CONCEN_UNITS` JS const). A **label only**: switching units never converts the recorded numbers. `get_concen_unit(meta)` returns the documented default `ng/µL` when the line is absent.
- **No persisted default, no migration** (online specifics): the `#concen-unit` dropdown (Data Display section) defaults to `ng/µL` each session and reflects the loaded file (`getMetaConcenUnit`/`syncConcenUnitDropdown`); there is no settings store. Storage is in-memory (`user_data['csv']`/`['json'][mode]`), so an absent `ConcenUnit` is simply **defaulted at read time** — the line is materialized only when the user edits the unit (Edit-File metadata **dropdown**, built from `CONCEN_UNITS`) or exports. **Do not** back-fill stored content on `get_csv`/`get_json_cal` (avoids needless Firebase/Drive writes).
- **Export**: `data_routes.export_data` reads `concenUnit` and threads it into `write_metadata` + `is_metadata_consistent`; appending a different unit to an existing calibration file is rejected with a `Concentration unit mismatch` error. `export_cal_coefs` records the curve's identity — `for_meas` (Measurement), `meas_unit`, `concen_unit` — into the JSON.
- **CSV↔JSON identity matching**: a measurement CSV is paired with a calibration JSON only when they share **Measurement + Unit + ConcenUnit**. `file_path.build_csv_identity_from_store` / `build_json_identity_from_store` return `{name: {measurement, unit, concen_unit}}` from the in-memory stores; `get_csv` / `get_json_cal` return them as `files_identity` and the index injects `FILE_IDENTITY` / `CAL_JSON_IDENTITY`. Both tables show an inline `Measurement·Unit·ConcenUnit` badge (`.file-identity`); when a counterpart is selected, a non-matching row's **Select button is disabled** (`navigation.js` `_selectDisableAttrs`), and `selectFile` raises an explicit mismatch error as a backstop. Measurement/Unit are **wildcards when absent** on either side (legacy JSONs stay usable; `NONE`/blank normalized via `_norm_identity_value` / `_normIdent`); ConcenUnit is always enforced (absent ⇒ ng/µL).
- Report derived-concentration lines and the calibrate chart axis use the actual unit (`_reportConcenUnit` / `getMetaConcenUnit`), not a hardcoded `ng/µL`.
- **Build note**: all of the above edits live in `static/script/` source; run `npm run build` so `static/dist/*.min.js` (+ `style.min.css`) reflect them before a production deploy.

---

## 3. Autonomous Documentation Updates

- **Self-Reflection Request**: Upon completing any significant task, feature implementation, or architectural change before returning control to the user, you **MUST** evaluate if updates are required for `Rule.md` or `easyokapi-knowledge/EASY OKAPI.md`.
- **Functional updates**: If your changes introduce new files, routes, dependencies, or alter the architectural flow, you MUST proactively edit `easyokapi-knowledge/EASY OKAPI.md`.
- **Behavioral updates**: If your task establishes new strict coding patterns, behavioral constraints, or anti-patterns, you MUST proactively edit `Rule.md`.
