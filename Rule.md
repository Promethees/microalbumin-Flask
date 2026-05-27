# Rule_main.md — AI Coding Rules for the `main` Branch

> **Branch purpose**: This branch runs as a **single-user, local desktop application**. Users launch it on their own machine (Mac or Windows) — the Flask server opens a browser tab automatically and communicates with a **PyBadge colorimeter** over USB HID/serial.

---

## 1. Project Identity

| Field | Value |
|---|---|
| **App name** | Easy OKAPI |
| **Domain** | Colorimeter data visualization for bio-sensor experiments |
| **Framework** | Flask 1.1.4 (Python 3.x via pyenv) |
| **Real-time** | No SocketIO. Standard request/response only |
| **Deployment** | Local machine — auto-launches browser via `browser_mgt.py` |
| **Default port** | `5099` (configurable via `--port`) |
| **Domain alias** | `easyokapi.com` mapped to `127.0.0.1` via hosts file (configurable via `--alias`) |
| **Installers** | `.dmg` (Mac), `.exe` (Windows), or batch/command scripts |

---

## 2. Critical Rules for AI Coding

### 2.0 Mandatory First Step: Read EASY OKAPI.md

- **BEFORE executing any commands like `ls -R` or `find` to explore the codebase**, you **MUST** read `easyokapi-knowledge/EASY OKAPI.md` first.
- This document holds the summary, architecture, codebase map, and exact roadmap of the project. Prioritizing reading this prevents wasting tokens on excessive directory listings and codebase guessing.

### 2.1 Data Storage — Always Use Local Filesystem

- **All CSV and JSON operations use `os.path`, `open()`, `Path`, `glob`, `shutil`, `pandas`.**
- There is **no** in-memory `USER_DATA` dict, no session-based storage.
- Files are read from and written to the user's local disk directly.
- The current browsed directory is tracked in `file_path.py`'s global `current_directory`, always within `DATA_ROOT` (`data/`).
- Modifications to files (`edit_file`, `delete_file`, `copy_file`) operate directly on the filesystem.

### 2.2 Single-User — No Session Isolation

- There is only one user. No Flask `session` for user differentiation.
- Global variables (`process`, `monitor_thread`, `current_directory`) are shared.
- File locks (`filelock.FileLock`) are used for concurrent access to export files, not for multi-user isolation.

### 2.3 HID Logging — PyBadge Communication

- The application communicates with a physical **PyBadge** (Adafruit) colorimeter via USB.
- **Mac**: Uses `hidapi` library directly (`log_hid_data.py`)
- **Windows**: Uses `pyusb` (`log_hid_data_pyusb.py`, invoked via `venv/Scripts/python.exe`)
- **Serial commands** are sent via `send_command.py` using `pyserial` before spawning the HID logger as a subprocess.
- HID logging is **disabled in calibrate mode**.
- The subprocess writes to `log/script_logs.txt`, which is monitored for errors.
- The PyBadge VID/PID: `0x239A` / `0x800B` (HID) or `0x8034` (serial)

### 2.4 Static Files — No Build Step

- Source JS and CSS are served directly from `static/`.
- **No obfuscation, no minification, no `build.js`, no `npm run build`.**
- There is no `static/dist/` directory.
- `app = Flask(__name__, static_folder='static')` — JS files are referenced directly.

### 2.5 No Google Drive

- There is **no** Google Drive integration, no OAuth, no `credentials.enc`.
- No `drive-integration.js` on this branch.
- No `src/google_drive_service.py`, no `src/user_data.py`, no `src/config.py`.

### 2.6 Data Folder Management

- Users are **restricted to the `data/` directory** (project root). Free filesystem browsing is no longer allowed.
- A **subfolder picker** UI lists immediate subdirectories of `data/` with search and sort by name.
- `src/file_path.py` exports `DATA_ROOT` constant, `validate_in_data_root(path)`, and `get_data_subfolders()`. There is **no mutable `current_directory` state** — the backend is stateless; directory tracking is owned by the frontend.
- `src/state.py` tracks `data_root_path`, `report_root_path`, `json_root_path` (all auto-created on startup).
- Route `GET /get_data_folders` returns `[{"name": "...", "path": "..."}, ...]`.
- Route `POST /browse` is **stateless**: validates path is within `data_root_path` or `report_root_path`, returns files, and never writes to backend state. Removed routes: `/get_parents`, `/get_children`.
- Template variables passed from `index()`: `data_root`, `report_root`, `json_root` (replaces `directory`).
- JS constants: `DATA_ROOT`, `REPORT_ROOT`, `JSON_ROOT` (replaces `rootPath`). Defined inline in `index.html` before external scripts are loaded.
- Path delimiter: `\\` on Windows, `/` on Mac/Linux.
- Hidden directories (starting with `.` or `_`) are filtered out.
- **Anti-pattern**: Do **not** restore `get_directory()`, `browse_directory()`, `get_parent_directory()`, or `current_directory` global in `file_path.py` — these have been permanently removed.
- `/run_script` payload uses `subfolder` (folder name only, no slashes) instead of `base_dir`; backend constructs `data/<subfolder>` and creates it if needed.

### 2.7 Shutdown Endpoint

- `POST /shutdown` terminates the Flask server process after a 5-second delay.
- Renders `goodbye.html` before termination.
- `cleanup()` in `browser_mgt.py` runs via `atexit`: kills subprocess, closes port.

### 2.8 No Real-Time (No SocketIO)

- Unlike the `online` branch, there is **no Flask-SocketIO, no eventlet**.
- All communication is standard HTTP request/response or AJAX (`$.ajax` / `fetch`).
- After file modifications, the frontend must **manually refresh** data by re-fetching from the API.

### 2.9 Frontend Conventions

- **Global state** lives in `AppState` object (defined in `index.js`).
- Uses `short-hands.js` utility functions (`$id`, `$text`, `$hidden`, etc.).
- SweetAlert2 (`Swal`) for dialogs, Chart.js for plotting, MathJax for equations.
- Three measurement modes: `kinetics`, `point`, `calibrate`.
- "Source" terminology (not "sensor") for data sources.
- Light/dark theme toggling.
- `checkServerStatus()` polls `/ping` every second — shows "Server not running" notice if the server is down.

### 2.10 CSV Data Format

CSV files follow this structure:
```
# Measurement: Absorbance
# MeasUnit: abs
# TimeUnit: s
# MeasMode: kinetics
Timestamp,Value:1,Value:2,...
0,0.123,0.456,...
```
- Metadata lines start with `#` and contain `Key: Value` pairs.
- Required metadata: `Measurement`, `MeasUnit`, `TimeUnit`, `MeasMode`.
- Data header starts with `Timestamp` followed by `Value:n` columns (for measurement data).
- Calibration CSVs use: `Concentration,maxRate,Slope,Sat,Time To Sat` (kinetics) or `Concentration,Value,TimePoint` (point).
- Multi-source files have multiple `Value:` columns (`Value:1`, `Value:2`, etc.).

### 2.11 OS-Specific Behavior

- **Path delimiters**: `\\\\` for Windows, `/` for Mac/Linux (set in `main.py` global).
- **HID logging**: Different scripts for Mac (`log_hid_data.py` with `sudo`) vs. Windows (`log_hid_data_pyusb.py`).
- **Process termination**: Windows uses `process.terminate()`, Mac uses `os.killpg(SIGTERM)`.
- **Hosts file**: Windows at `C:\Windows\System32\drivers\etc\hosts`, Mac at `/etc/hosts`.

---

### 2.12 User Settings — Persistent Preferences

- User UI preferences are stored in `user_settings.json` at the project root via `src/user_settings.py`.
- Supported keys: `theme` (`"light"|"dark"|"auto"`), `default_mode` (`"kinetics"|"point"|"calibrate"`), `default_window_size` (int ≥ 2), `default_subfolder` (str or null), `event_log_retention_days` (int ≥ 0, 0 = keep forever, default 30).
- `user_settings.json` is **gitignored** (contains per-machine preferences, not project config).
- Routes: `GET /settings` returns current settings; `POST /settings` accepts a partial update (any subset of keys).
- The settings object is injected into `index.html` as the `USER_SETTINGS` JS constant (alongside `DATA_ROOT`, `DELIMITER`, etc.).
- **Anti-pattern**: Do not add new per-machine state to `state.py` globals — use `user_settings.py` for anything user-configurable.

### 2.14 Event Logging — User Interaction Tracing

- Logs are stored under `log/events/YYYY-MM-DD/HH-MM-SS.jsonl`: one date folder per calendar day, one JSONL file per app launch within that day (name = session start time).
- Module-level `_SESSION_DATE` / `_SESSION_START` constants are set once at import time so all events in one process go to the same file.
- Each entry: `{"ts": "YYYY-MM-DDTHH:MM:SS", "type": "...", "action": "...", "details": {...}}`.
- `append(type, action, details=None)` — writes one JSONL line to the current session file.
- `read_all()` — reads all events across all date folders and sessions, oldest first.
- `cleanup_old_logs()` — removes date folders older than `event_log_retention_days`; called automatically on every session start (index route).
- Routes: `GET /event_log` returns all events; `POST /event_log` (`{type, action, details?}`) appends one entry.
- Frontend: `logEvent(type, action, details)` in `static/script/event-tracker.js` (loaded first) — fire-and-forget `fetch`, never blocks the UI.
- Tracked events: `session:start` (page load), `mode:switch`, `file:select/delete/copy`, `data:display`, `hardware:start/stop`, `report:generate`, `settings:save`.
- **Anti-pattern**: Do not `await` log calls or show errors to the user when logging fails — logging is always best-effort.

### 2.13 AI Assistant — Groq Cloud LLM

- The AI assistant uses **Groq** (cloud API) — no local model server required.
- Desktop instances authenticate via `activation.json` (permanent license token) and proxy requests through the online Heroku server. Developers can bypass this by setting `GROQ_API_KEY` in `.env`.
- Settings are stored in `ai_settings.json` at the project root via `src/ai_settings.py`.
- All chat calls go through `src/ai_assistant.py` using the `requests` library.
- The AI blueprint is `ai_bp` in `src/routes/ai_routes.py`, mounted at `/ai/*`.
- Supported languages: `en`, `vi`, `zh`, `fr`, `ja`, `ru`. System prompts for all 6 are embedded in `ai_assistant.py`.
- `ai_settings.json` stores `preferred_languages` as a **JSON array** (e.g. `["en","vi"]`). Old single-string `preferred_language` keys are migrated to an array transparently by `ai_settings.load()` and `ai_settings.save()`. Never write the singular key in new code.
- `AI.activeLang` in `ai-chat.js` tracks the currently active language and cycles through `preferred_languages` via the header button. Chat requests send `AI.activeLang`, not the full preference list.
- MCP tools (`TOOLS` list in `ai_assistant.py`) give the LLM access to live app state: file list, CSV content, calibration JSON, hardware status, and built-in help docs.
- Conversation history is **client-side only** (stored in `ai-chat.js` `AI.messages` array) — the backend is stateless, consistent with the single-user no-session rule.
- **Anti-pattern**: Do not add Ollama, local model pulls, or `pull_model`/`pull_status` routes — the app no longer uses a local model server.

---

## 3. Autonomous Documentation Updates

- **Self-Reflection Request**: Upon completing any significant task, feature implementation, or architectural change before returning control to the user, you **MUST** evaluate if updates are required for `Rule.md` or `easyokapi-knowledge/EASY OKAPI.md`.
- **Functional updates**: If your changes introduce new files, routes, dependencies, or alter the architectural flow, you MUST proactively edit `easyokapi-knowledge/EASY OKAPI.md`.
- **Behavioral updates**: If your task establishes new strict coding patterns, behavioral constraints, or anti-patterns, you MUST proactively edit `Rule.md`.
