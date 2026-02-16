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

## 2. Architecture Overview

### 2.1 Backend (`main.py` — single entry point, ~1078 lines)

The Flask app is organized into **regions** by the JS consumer:

| Region | Routes | Consumer |
|---|---|---|
| Region 1 | `/ping`, `/clear_cache`, `/`, `/get_csv`, `/get_json_cal` | `index.js` |
| Region 2 | `/get_json_content`, `/get_headers`, `/api/current_output` | `navigation.js` |
| Region 2.5 | `/auth/google/*`, `/drive/*` (13 endpoints) | `drive-integration.js` |
| Region 3 | `/edit_file`, `/delete_file`, `/copy_file`, `/upload_file`, `/merge_csv` | `edit-file.js` |
| (unlabelled) | `/get_num_sources`, `/get_data`, `/get_file_content`, `/export_data`, `/export_cal_coefs` | `data-handling.js`, `data-display.js` |

**Key architectural decisions on the online branch:**

- **No filesystem access**: All user data (CSV and JSON) is stored **in-memory** in a per-session `USER_DATA` dictionary (`src/user_data.py`). There is no reading/writing to the server's local filesystem for user files.
- **Session-based multi-user**: Each user gets a unique `user_id` via Flask `session`. User data is isolated in `USER_DATA[uid]`.
- **Google Drive integration**: Users can connect Google Drive via OAuth 2.0 to persist their data. OAuth credentials are encrypted (`credentials.enc`).
- **No HID logging**: The `hid-logging.js` and `log_hid_data.py` scripts do **not** exist on this branch. HID device interaction is disabled — the online version cannot communicate with local USB devices.
- **Static files served from `static/dist/`**: The Flask app is configured with `static_folder='static/dist'` to serve minified/obfuscated assets.
- **`PRODUCTION_MODE = True`** is hardcoded.

### 2.2 Backend Modules (`src/`)

| Module | Purpose |
|---|---|
| `user_data.py` | In-memory per-session storage (`USER_DATA` dict), session management, Drive state helpers |
| `google_drive_service.py` | OAuth 2.0 flow, Drive CRUD operations (folders, files), session-to-Drive sync |
| `config.py` | Configuration class (`Config`): secret keys, Google API settings, file size limits |
| `export_data.py` | CSV metadata parsing, header writing, export utilities with thread locks (`user_csv_lock`) |
| `export_cal_json.py` | Standard curve coefficient processing, JSON export for calibration data |
| `file_merge.py` | Merging CSV contents from two files |
| `file_path.py` | File path utilities |
| `get_next_filename.py` | Auto-naming duplicates (e.g., `file_1.csv`, `file_2.csv`) |
| `mode.py` | Returns available measurement modes: `kinetics`, `point`, `calibrate` |
| `quantity.py` | Returns available quantity options for kinetics analysis |
| `range.py` | Returns display range input configuration |

### 2.3 Frontend (`static/script/` — 11 JS files)

| File | Responsibility |
|---|---|
| `short-hands.js` | DOM utility helpers (`$id`, `$text`, `$hidden`, `fetchJSON`, etc.) |
| `init.js` | Page initialization, event listeners, mode/filter setup, socket.io connection |
| `index.js` | `AppState` global state object, mode switching logic, directory updates, `checkServerStatus` |
| `navigation.js` | File table population (CSV and JSON), directory browsing, `browseSavingLocation` |
| `data-handling.js` | File select/deselect/delete/copy/upload/download, data fetching, export logic |
| `data-display.js` | Chart rendering orchestration, multi-source handling, calibration routines, analysis formatting |
| `generate-chart.js` | Chart.js chart creation, dataset construction, annotations, scales |
| `calculate.js` | Math: regression (linear, polynomial, logarithmic, exponential, Michaelis-Menten), kinetics quantities, R² |
| `edit-file.js` | SweetAlert2-based file editor modal (CSV and JSON), column operations, JSON graphic UI |
| `drive-integration.js` | Google Drive OAuth UI, folder selection, sync/load operations, auto-sync on close |
| `user-guide.js` | Interactive step-by-step user guide with spotlight overlay |

### 2.4 Templates (`templates/`)

| File | Purpose |
|---|---|
| `index.html` | Main SPA template (~419 lines). Jinja2-rendered with server-side data. Contains all UI sections. |
| `goodbye.html` | Displayed on shutdown (not used in online version) |

---

## 3. Build & Deployment Pipeline

### 3.1 Build Process (`npm run build` → `node build.js`)

The build script performs:
1. **Copy static assets** (images, fonts) to `static/dist/`
2. **Obfuscate + minify JS** using `javascript-obfuscator` + `terser` → output as `*.min.js` in `static/dist/`
3. **Minify CSS** using `clean-css` → output as `*.min.css` in `static/dist/`

> The obfuscator auto-detects reserved function names from HTML `onclick` attributes, `data-action` attributes, and inline `<script>` blocks to avoid breaking references.

### 3.2 Heroku Deployment

```bash
# Build is triggered automatically via heroku-postbuild
npm run build

# Deploy
git push heroku online:main
```

- `Procfile`: `web: gunicorn -k eventlet --workers 1 main:app`
- `runtime.txt`: `python-3.12.11`
- `package.json` includes `"heroku-postbuild": "npm run build"` to run obfuscation on deploy

### 3.3 Environment Variables Required

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session encryption |
| `GOOGLE_ENCRYPTION_KEY` | Decrypts `credentials.enc` for Google Drive OAuth |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL (defaults to `http://localhost:5003/auth/google/callback`) |

---

## 4. Critical Rules for AI Coding

### 4.1 Data Storage — NEVER Use Local Filesystem for User Data

- All user CSV and JSON data must go through `get_user_data()` → in-memory `USER_DATA` dict.
- **Never** use `open()`, `os.path`, or `Path` to read/write user files on the server filesystem.
- Default sample data (`csv/multi.csv`, `csv/single.csv`, `json/exp_kinetics.json`, `json/exp_point.json`) is loaded into memory on first request via `init_user_data()`.

### 4.2 Multi-User Session Isolation

- Every route that accesses user data **must** call `get_user_data()` (which internally calls `get_user_id()` to get the session-bound `user_id`).
- Never use global variables to store per-user state outside of `USER_DATA`.
- Use `user_csv_lock` for thread-safe CSV export operations.

### 4.3 Static Files & Build

- **Development source** is in `static/script/` (JS) and `static/style.css` (CSS).
- **Production serves from `static/dist/`**. The Flask app is set to `static_folder='static/dist'`.
- After modifying any JS or CSS, you **must** run `npm run build` before deploying.
- **Never** edit files in `static/dist/` directly — they are generated artifacts.
- The `index.html` template references scripts via `{{ url_for('static', ...) }}` which resolves to `static/dist/`.

### 4.4 No HID / No Local Hardware

- This branch has **no HID logging** functionality. Do not add USB/serial device communication code.
- The `/api/current_output` endpoint returns `{"exists": False}`.
- Any references to `log_hid_data.py`, `script_monitor.py`, `browser_mgt.py`, or `send_command.py` are **not present** on this branch.

### 4.5 Google Drive Integration

- OAuth uses encrypted credentials (`credentials.enc`) decrypted with `GOOGLE_ENCRYPTION_KEY`.
- Session recovery logic handles cross-site cookie drops by encoding `user_id` in the OAuth `state` parameter.
- Google Drive operations are in `src/google_drive_service.py`; UI logic in `static/script/drive-integration.js`.
- Drive mode states: `guest` (default, uses sample data) → `connected` (uses Drive-synced data).

### 4.6 Real-Time Updates

- The app uses **Flask-SocketIO** with **eventlet** for real-time UI updates.
- After any CRUD operation on user files, emit the corresponding socket event:
  - CSV changes: `socketio.emit('update_csv')`
  - JSON changes: `socketio.emit('update_json', {'mode': mode})`
- The Heroku Procfile uses `-k eventlet --workers 1` — **only 1 worker** is allowed with SocketIO.

### 4.7 Frontend Conventions

- **Global state** lives in `AppState` object (defined in `index.js`).
- Use utility short-hands from `short-hands.js` (`$id`, `$text`, `$hidden`, `$toggleClass`, `fetchJSON`).
- SweetAlert2 (`Swal`) is used for dialogs and confirmations (loaded via CDN in `index.html`).
- Chart.js is used for plotting (loaded via CDN).
- MathJax is used for rendering mathematical equations.
- **Light/dark theme** is toggled via `body.light` / `body.dark` classes.
- Three measurement modes: `kinetics`, `point`, `calibrate`. Mode switching triggers `switchingModes()` and `switchingCalModes()`.
- "Source" terminology is used (not "sensor") for data sources.

### 4.8 Security & Production

- `ProxyFix` is applied for HTTPS behind Heroku's proxy.
- Session cookies are configured: `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_SAMESITE='Lax'`, `SESSION_COOKIE_HTTPONLY=True`.
- Max upload size: 16MB (`MAX_CONTENT_LENGTH`).
- CSV content is validated against strict regex patterns before saving.
- JSON content is validated as parseable before saving.
- File names are sanitized with `werkzeug.utils.secure_filename`.

---

## 5. Directory Structure (Online Branch)

```
microalbumin-Flask/
├── main.py                     # Flask app entry point (all routes)
├── Procfile                    # Heroku process config
├── runtime.txt                 # Python version for Heroku
├── requirements.txt            # Python dependencies
├── package.json                # Node.js build config
├── build.js                    # Obfuscation + minification build script
├── credentials.enc             # Encrypted Google OAuth credentials
├── .env                        # Environment variables (local dev)
├── .gitignore
├── src/
│   ├── config.py               # App configuration
│   ├── user_data.py            # In-memory per-session data store
│   ├── google_drive_service.py # Google Drive API integration
│   ├── export_data.py          # CSV export utilities
│   ├── export_cal_json.py      # Calibration JSON export
│   ├── file_merge.py           # CSV merge logic
│   ├── file_path.py            # Path utilities
│   ├── get_next_filename.py    # Auto-naming for duplicates
│   ├── mode.py                 # Measurement mode definitions
│   ├── quantity.py             # Quantity input definitions
│   └── range.py                # Display range definitions
├── static/
│   ├── style.css               # Source CSS (development)
│   ├── script/                 # Source JS (development)
│   │   ├── short-hands.js
│   │   ├── init.js
│   │   ├── index.js
│   │   ├── navigation.js
│   │   ├── data-handling.js
│   │   ├── data-display.js
│   │   ├── generate-chart.js
│   │   ├── calculate.js
│   │   ├── edit-file.js
│   │   ├── drive-integration.js
│   │   └── user-guide.js
│   └── dist/                   # Built/minified assets (auto-generated)
├── templates/
│   ├── index.html              # Main SPA template
│   └── goodbye.html
├── csv/                        # Default sample CSV data
├── json/                       # Default sample JSON data
└── images/                     # README screenshots
```

---

## 6. Key Differences from `main` Branch (Summary)

| Aspect | `online` branch | `main` branch (expected) |
|---|---|---|
| Data storage | In-memory `USER_DATA` dict | Local filesystem |
| Directory browsing | N/A (upload-based) | OS directory picker |
| HID logging | Disabled | Enabled (PyBadge USB) |
| Users | Multi-user with sessions | Single user |
| Google Drive | Integrated (OAuth 2.0) | Not needed |
| Static serving | From `static/dist/` (obfuscated) | From `static/` (source) |
| Build step | Required (`npm run build`) | Not required |
| Deployment | Heroku | Local machine |
| `static_folder` | `'static/dist'` | `'static'` |
| Shutdown endpoint | Not applicable | Present |
| `PRODUCTION_MODE` | `True` | `False` |
