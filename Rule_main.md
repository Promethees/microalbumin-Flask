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

## 2. Architecture Overview

### 2.1 Backend (`main.py` — single entry point, ~1132 lines)

| Region | Routes | Consumer |
|---|---|---|
| Region 1 | `/ping`, `/clear_cache`, `/clear_logs`, `/`, `/shutdown`, `/browse`, `/browse_export`, `/get_parents`, `/get_children`, `/get_json_cal` | `index.js` |
| Region 2 | `/get_json_content`, `/get_csv_headers`, `/api/current_output` | `navigation.js` |
| Region 3 | `/run_script`, `/check_status`, `/terminate_script`, `/get_logs` | `hid-logging.js` |
| Region 4 | `/edit_file`, `/delete_file`, `/copy_file`, `/merge_csv`, `/remove_columns`, `/get_num_sources`, `/get_data`, `/get_file_content`, `/export_data`, `/export_cal_coefs` | `data-handling.js`, `edit-file.js`, `data-display.js` |

**Key architectural decisions on the main branch:**

- **Filesystem-based data storage**: All CSV and JSON files are read from and written to the **local filesystem** using `os`, `pathlib`, `shutil`, `csv`, and `pandas`.
- **Single-user process**: No sessions, no `USER_DATA` dict, no Google Drive. One global `current_directory` tracks the browsed path.
- **HID device communication**: The PyBadge colorimeter sends measurement data via USB HID. `log_hid_data.py` (Mac/`hidapi`) and `log_hid_data_pyusb.py` (Windows/`pyusb`) capture the data stream and write CSV files. Controlled via `send_command.py` (serial protocol).
- **Auto-browser launch**: `browser_mgt.py` opens the default browser after server starts. On shutdown, the process group is terminated.
- **Static files served from `static/`**: No build step, no obfuscation. `static_folder='static'`.
- **`PRODUCTION_MODE = True`** controls shutdown behavior (kill process group vs. Werkzeug shutdown).

### 2.2 Backend Modules (`src/`)

| Module | Purpose |
|---|---|
| `file_path.py` | Filesystem directory browsing: `get_directory`, `browse_directory`, `get_parent_directory`, `get_child_directories` |
| `file.py` | File operations: `get_file_list` (glob), `get_dynamic_data` (parse CSV/JSON from disk), `merge_csv_files`, `replace_empty` |
| `file_operations.py` | `remove_csv_columns` — removes columns from CSV files on disk, renumbers `Value:` columns |
| `measure.py` | `sort_csv_file` — sorts calibration CSV data on disk by concentration |
| `browser_mgt.py` | `open_browser`, `close_port`, `cleanup`, `ensure_host_mapping` — browser/process lifecycle |
| `script_monitor.py` | `check_log_for_errors` — scans `log/script_logs.txt` for PyBadge errors |
| `send_command.py` | `connect_to_device` (find PyBadge via serial), `send_command_and_wait_ack` (serial protocol) |
| `export_data.py` | CSV metadata parsing, header writing, sort by concentration |
| `export_cal_json.py` | Standard curve coefficient processing, JSON export for calibration data |
| `get_next_filename.py` | Auto-naming duplicates (e.g., `file_1.csv`) |
| `mode.py` | Returns available measurement modes: `kinetics`, `point`, `calibrate` |
| `quantity.py` | Returns available quantity options for kinetics analysis |
| `range.py` | Returns display range input configuration |

### 2.3 HID Data Collection (`log_hid_data.py`)

The `HIDDataCollector` class:
1. Discovers the PyBadge (`VID=0x239A`, `PID=0x800B`) via `hidapi`
2. Reads 8-byte HID keyboard reports and decodes them to characters
3. Parses incoming data as metadata lines (`#Key: Value`), CSV headers (`Timestamp,Value:1,...`), and data rows
4. Writes output to auto-named CSV files in the specified `--base-dir`
5. Manages session boundaries (`END_SESSION` markers)

**Serial command protocol** (`send_command.py`):
- `1\n` → start measurement (`ACK_START`)
- `0\n` → stop measurement (`ACK_STOP`)
- `TIMEOUT:<secs>\n` → set timeout (`ACK_TIMEOUT`)
- `INTERVAL:<secs>\n` → set interval (`ACK_INTERVAL`)

### 2.4 Frontend (`static/script/` — 11 JS files)

| File | Responsibility |
|---|---|
| `short-hands.js` | DOM utility helpers (`$id`, `$text`, `$hidden`, etc.) |
| `init.js` | Page initialization, event listeners, mode/filter setup |
| `index.js` | `AppState` global state, mode switching, directory updates, `checkServerStatus` |
| `navigation.js` | File table population (CSV and JSON), **directory browsing** (parent/child navigation) |
| `hid-logging.js` | **PyBadge control UI**: `runScript`, `terminateScript`, `checkScriptStatus`, log display |
| `data-handling.js` | File select/deselect/delete/copy/upload/download, data fetching, export logic |
| `data-display.js` | Chart rendering orchestration, multi-source handling, calibration routines |
| `generate-chart.js` | Chart.js chart creation, dataset construction, annotations |
| `calculate.js` | Math: regression (linear, polynomial, logarithmic, exponential, Michaelis-Menten), R² |
| `edit-file.js` | SweetAlert2-based file editor modal (CSV and JSON), column operations |
| `user-guide.js` | Interactive step-by-step user guide with spotlight overlay |

### 2.5 Templates (`templates/`)

| File | Purpose |
|---|---|
| `index.html` | Main SPA template. Jinja2-rendered with server-side data (directory, file list, mode, etc.) |
| `goodbye.html` | Displayed on `/shutdown` — shows farewell screen before process termination |

---

## 3. Installation & Startup

### 3.1 Mac

```bash
# Option A: Installer (.dmg)
# → install-tools-clone-repo → install-venv → run

# Option B: Scripts
./setup-1-install-pyenv.command   # Install homebrew, pyenv, python
./setup-2-install-venv.command    # Install dependencies to venv/
./setup-3-run.command             # Start the application
```

### 3.2 Windows

Requires `libusbK` driver installed via Zadig for PyBadge HID access.

```cmd
:: Scripts (run as Administrator, one by one)
startwindow-1-git.bat
startwindow-2-pyenv.bat
startwindow-3-python.bat
startwindow-4-venv-run.bat
```

### 3.3 Direct Python

```bash
python main.py --port 5099 --alias easyokapi.com
```

### 3.4 Dependencies (`requirements.txt`)

```
flask==1.1.4
pandas==1.3.5
hidapi==0.14.0
hid==1.0.7
markupsafe==2.0.1
filelock==3.16.1
pyserial==3.5
```

> **Note**: No SocketIO, eventlet, gunicorn, or Google API libraries — those are `online` branch only.

### 3.5 Environment Variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session encryption (from `.env`) |

---

## 4. Critical Rules for AI Coding

### 4.1 Data Storage — Always Use Local Filesystem

- **All CSV and JSON operations use `os.path`, `open()`, `Path`, `glob`, `shutil`, `pandas`.**
- There is **no** in-memory `USER_DATA` dict, no session-based storage.
- Files are read from and written to the user's local disk directly.
- The current browsed directory is tracked in `file_path.py`'s global `current_directory`.
- Modifications to files (`edit_file`, `delete_file`, `copy_file`) operate directly on the filesystem.

### 4.2 Single-User — No Session Isolation

- There is only one user. No Flask `session` for user differentiation.
- Global variables (`process`, `monitor_thread`, `current_directory`) are shared.
- File locks (`filelock.FileLock`) are used for concurrent access to export files, not for multi-user isolation.

### 4.3 HID Logging — PyBadge Communication

- The application communicates with a physical **PyBadge** (Adafruit) colorimeter via USB.
- **Mac**: Uses `hidapi` library directly (`log_hid_data.py`)
- **Windows**: Uses `pyusb` (`log_hid_data_pyusb.py`, invoked via `venv/Scripts/python.exe`)
- **Serial commands** are sent via `send_command.py` using `pyserial` before spawning the HID logger as a subprocess.
- HID logging is **disabled in calibrate mode**.
- The subprocess writes to `log/script_logs.txt`, which is monitored for errors.
- The PyBadge VID/PID: `0x239A` / `0x800B` (HID) or `0x8034` (serial)

### 4.4 Static Files — No Build Step

- Source JS and CSS are served directly from `static/`.
- **No obfuscation, no minification, no `build.js`, no `npm run build`.**
- There is no `static/dist/` directory.
- `app = Flask(__name__, static_folder='static')` — JS files are referenced directly.

### 4.5 No Google Drive

- There is **no** Google Drive integration, no OAuth, no `credentials.enc`.
- No `drive-integration.js` on this branch.
- No `src/google_drive_service.py`, no `src/user_data.py`, no `src/config.py`.

### 4.6 Directory Browsing

- Users browse their **local filesystem** via the UI.
- Routes: `/browse`, `/get_parents`, `/get_children`, `/browse_export`
- The server navigates directories using `file_path.py`'s `browse_directory`, `get_parent_directory`, `get_child_directories`.
- Path delimiter: `\\\\` on Windows, `/` on Mac/Linux.
- Hidden directories (starting with `.` or `_`) are filtered out.

### 4.7 Shutdown Endpoint

- `POST /shutdown` terminates the Flask server process after a 5-second delay.
- Renders `goodbye.html` before termination.
- `cleanup()` in `browser_mgt.py` runs via `atexit`: kills subprocess, closes port.

### 4.8 No Real-Time (No SocketIO)

- Unlike the `online` branch, there is **no Flask-SocketIO, no eventlet**.
- All communication is standard HTTP request/response or AJAX (`$.ajax` / `fetch`).
- After file modifications, the frontend must **manually refresh** data by re-fetching from the API.

### 4.9 Frontend Conventions

- **Global state** lives in `AppState` object (defined in `index.js`).
- Uses `short-hands.js` utility functions (`$id`, `$text`, `$hidden`, etc.).
- SweetAlert2 (`Swal`) for dialogs, Chart.js for plotting, MathJax for equations.
- Three measurement modes: `kinetics`, `point`, `calibrate`.
- "Source" terminology (not "sensor") for data sources.
- Light/dark theme toggling.
- `checkServerStatus()` polls `/ping` every second — shows "Server not running" notice if the server is down.

### 4.10 CSV Data Format

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
- Calibration CSVs use: `Concentration,maxRate,Slope,Sat,TimeToSat` (kinetics) or `Concentration,Value,TimePoint` (point).
- Multi-source files have multiple `Value:` columns (`Value:1`, `Value:2`, etc.).

### 4.11 OS-Specific Behavior

- **Path delimiters**: `\\\\` for Windows, `/` for Mac/Linux (set in `main.py` global).
- **HID logging**: Different scripts for Mac (`log_hid_data.py` with `sudo`) vs. Windows (`log_hid_data_pyusb.py`).
- **Process termination**: Windows uses `process.terminate()`, Mac uses `os.killpg(SIGTERM)`.
- **Hosts file**: Windows at `C:\Windows\System32\drivers\etc\hosts`, Mac at `/etc/hosts`.

---

## 5. Directory Structure (Main Branch)

```
microalbumin-Flask/
├── main.py                     # Flask app entry point (all routes)
├── main_code.py                # (Legacy/backup copy of main.py)
├── log_hid_data.py             # HID data collection (Mac, hidapi)
├── log_hid_data_pyusb.py       # HID data collection (Windows, pyusb)
├── requirements.txt            # Python dependencies
├── requirements-win.txt        # Windows-specific dependencies
├── .python-version             # Python version for pyenv
├── .env                        # Environment variables (SECRET_KEY)
├── .gitignore
├── LICENSE                     # MIT License
├── generate-tree.sh            # Directory tree generator script
├── setup-1-install-pyenv.command  # Mac installer step 1
├── setup-2-install-venv.command   # Mac installer step 2
├── setup-3-run.command            # Mac run script
├── startwindow-1-git.bat      # Windows installer step 1
├── startwindow-2-pyenv.bat     # Windows installer step 2
├── startwindow-3-python.bat    # Windows installer step 3
├── startwindow-4-venv-run.bat  # Windows installer step 4
├── installer-mac/              # Mac .dmg installer assets
├── installer-win/              # Windows .exe installer assets
├── src/
│   ├── file_path.py            # Filesystem directory browsing
│   ├── file.py                 # File listing, data parsing, CSV merge
│   ├── file_operations.py      # Column removal from CSVs
│   ├── measure.py              # CSV sorting by concentration
│   ├── browser_mgt.py          # Browser auto-launch, port cleanup
│   ├── script_monitor.py       # Log file error detection
│   ├── send_command.py         # PyBadge serial communication
│   ├── export_data.py          # CSV export utilities
│   ├── export_cal_json.py      # Calibration JSON export
│   ├── get_next_filename.py    # Auto-naming for duplicates
│   ├── mode.py                 # Measurement mode definitions
│   ├── quantity.py             # Quantity input definitions
│   └── range.py                # Display range definitions
├── static/
│   ├── style.css               # Source CSS (served directly)
│   ├── done.mp3                # Completion sound effect
│   ├── ht-logo.jpeg, ht.ico    # App icons/logos
│   ├── okapi.png, cbb.png      # Brand images
│   └── script/                 # Source JS (served directly)
│       ├── short-hands.js
│       ├── init.js
│       ├── index.js
│       ├── navigation.js
│       ├── hid-logging.js      # PyBadge HID control UI
│       ├── data-handling.js
│       ├── data-display.js
│       ├── generate-chart.js
│       ├── calculate.js
│       ├── edit-file.js
│       └── user-guide.js
├── templates/
│   ├── index.html              # Main SPA template
│   └── goodbye.html            # Shutdown farewell page
├── json/                       # Standard curve JSON files
│   └── kinetics/               # Kinetics calibration JSONs
├── log/                        # Script logs directory
│   └── script_logs.txt
├── sample_data/                # Sample measurement CSV files (11 files)
└── images/                     # README screenshots
```

---

## 6. Key Differences from `online` Branch (Summary)

| Aspect | `main` branch | `online` branch |
|---|---|---|
| Data storage | Local filesystem (`os`, `open`, `Path`) | In-memory `USER_DATA` dict |
| Directory browsing | OS filesystem navigation | N/A (upload-based) |
| HID logging | Enabled (PyBadge USB) | Disabled |
| Users | Single user, no sessions | Multi-user with Flask sessions |
| Google Drive | Not present | Integrated (OAuth 2.0) |
| Static serving | From `static/` (source) | From `static/dist/` (obfuscated) |
| Build step | Not required | Required (`npm run build`) |
| Deployment | Local machine | Heroku |
| Real-time | No SocketIO | Flask-SocketIO with eventlet |
| Flask version | 1.1.4 | Latest (with SocketIO support) |
| Shutdown endpoint | Present (`/shutdown`) | Not applicable |
| `PRODUCTION_MODE` | `True` (controls kill behavior) | `True` (always) |
| `static_folder` | `'static'` | `'static/dist'` |
| Browser auto-launch | Yes (`browser_mgt.py`) | No |
| Sound effects | `done.mp3` | N/A |
| Installers | `.dmg` / `.exe` / batch scripts | N/A |
