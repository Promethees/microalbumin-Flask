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

## 3. Autonomous Documentation Updates

- **Self-Reflection Request**: Upon completing any significant task, feature implementation, or architectural change before returning control to the user, you **MUST** evaluate if updates are required for `Rule.md` or `easyokapi-knowledge/EASY OKAPI.md`.
- **Functional updates**: If your changes introduce new files, routes, dependencies, or alter the architectural flow, you MUST proactively edit `easyokapi-knowledge/EASY OKAPI.md`.
- **Behavioral updates**: If your task establishes new strict coding patterns, behavioral constraints, or anti-patterns, you MUST proactively edit `Rule.md`.
