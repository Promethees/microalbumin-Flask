# Codebase & Functional Flow (Main Branch)

This file serves as the primary orientation for any AI agent or developer regarding the **Main** branch of the `microalbumin-Flask` project. **Before writing code, study the relationships and file structures documented here.**

## 1. Project Overview
The `main` branch contains the **Local Desktop/Web Application** (Easy OKAPI) — version **1.1.16**.
It is a Flask-based web application meant to run locally on a user's machine (Windows or Mac). It communicates with a physical colorimeter device (powered by a PyBadge with CircuitPython) over a USB CDC serial connection (with an HID-keyboard fallback the device triggers via its Left button). 

The application provides a Web GUI (via Flask templates and vanilla JavaScript) for users to:
1. Log raw measurement data directly from the PyBadge into local `.csv` files.
2. Browse local directories to view recorded `.csv` data.
3. Conduct analysis and generate Standard Curves based on measurement modes (`kinetics`, `point`, `calibrate`).
4. Perform local file operations (copy, edit, delete `.csv` and `.json` standard curve files).
5. Generate, save, and manage HTML analysis reports organized by subject.

## 2. Architecture Overview

```mermaid
graph TD
    Device((PyBadge/Colorimeter)) -->|USB CDC serial| Logger[[log_cdc_data.py]]
    Device -. HID keyboard fallback Left-button: types into any text field .-> Editor[Text editor]
    Logger -->|Logs to CSV via Subprocess| FileSys[(Local Filesystem)]
    
    UI[Frontend HTML/JS] -->|AJAX HTTP| API(Flask Blueprints)
    
    API --> Main[[main.py]]
    
    Main --> CoreBP[[routes/core_routes.py]]
    Main --> FileBP[[routes/file_routes.py]]
    Main --> HardBP[[routes/hardware_routes.py]]
    Main --> MathBP[[routes/math_routes.py]]

    CoreBP --> State[[src/state.py]]
    FileBP --> State
    HardBP --> State
    MathBP --> MathOps[[src/math_ops.py]]

    FileBP --> FileSys
    CoreBP --> PathMgmt[[src/file_path.py]]
    HardBP --> Hardware[[src/send_command.py]]
    Hardware --> Device
    Main -->|Dispatches Subprocess| Logger
```

### 2.1 Backend (`main.py` — 197-line thin entry point)

`main.py` handles only: imports, startup progress reporting, CLI argument parsing, blueprint registration, browser launch, atexit cleanup, signal handlers, and `app.run()`.

**All routes live in Flask blueprints under `src/routes/`:**

| Blueprint | File | Routes | Frontend Consumer |
|---|---|---|---|
| `core_bp` | `core_routes.py` | `/ping`, `/clear_cache`, `/clear_logs`, `/`, `/shutdown`, `/browse`, `/browse_export`, `/get_data_folders`, `/get_json_cal`, `/get_report_subjects`, `/settings` (GET+POST), `/data_root` (GET+POST, POST = preview), `/data_root/restart` (POST, commit+relaunch), `/browse_dirs` (GET), `/event_log` (GET+POST), `/list_event_log_files` (GET), `/download_event_logs` (GET all / POST selected, max 5) | `index.js`, `navigation.js`, `report.js`, `init.js`, `event-tracker.js`, `bug-report.js` |
| `file_bp` | `file_routes.py` | `/get_json_content`, `/get_csv_headers`, `/api/current_output`, `/edit_file`, `/delete_file`, `/copy_file`, `/merge_csv`, `/remove_columns`, `/get_num_sources`, `/get_data`, `/get_file_content`, `/export_data`, `/export_cal_coefs`, `/get_calibration_json_list`, `/delete_data_folder`, `/rename_data_folder`, `/move_file`, `/save_report`, `/export_to_report`, `/get_report_items`, `/delete_report_subject`, `/copy_report_subject`, `/rename_report_subject` | `navigation.js`, `data-handling.js`, `edit-file.js`, `data-display.js`, `report.js` |
| `hardware_bp` | `hardware_routes.py` | `/run_script`, `/check_status`, `/terminate_script`, `/get_logs` | `hid-logging.js` |
| `math_bp` | `math_routes.py` | `/calculate_coef_and_rsquared`, `/calculate_kinetics_quantities` | `calculate.js`, `data-display.js` |
| `ai_bp` | `ai_routes.py` | `/ai/status`, `/ai/chat`, `/ai/settings` (GET+POST), `/ai/activate`, `/ai/guides` | `ai-chat.js` |
| `update_bp` | `update_routes.py` | `/update/check` (GET), `/update/apply` (POST — SSE stream) | `init.js` |

* **Filesystem-based data storage**: All CSV and JSON files are read/written to the local filesystem.
* **Auto-browser launch**: `browser_mgt.py` opens the default browser on server init — suppressed by `--no-browser` (set on restart relaunches so a second tab doesn't steal the one-shot reset-display marker).
* **Single-user process**: No isolation, no sessions, straight port serving.
* **Startup progress reporter**: Writes `pct label\n` lines to `/tmp/easyokapi_progress.pipe` (Mac) or `%TEMP%\easyokapi_progress.txt` (Windows) for launch-script progress bars.
* **CLI flags**: `--port` (default 5099), `--alias` (default `easyokapi.com`), `--verbose` / `-v`, `--mem-monitor`, `--no-browser` (skip the startup browser tab; auto-applied by restart relaunches).

### 2.2 Backend Modules (`src/`)

| Module | Purpose |
|---|---|
| `state.py` | **Global state singleton**: `process`, `monitor_thread`, `args`, `script_dir`, `default_data_root` (where the `.dataroot` pointer lives — see `data_root.py`), `log_file`, `json_root_path`, `report_root_path`, `os_name`, `delimiter`, `PRODUCTION_MODE`, `IS_FROZEN`. Also `mark_reset_display_pending()` / `consume_reset_display_pending()` — a one-shot sentinel (`_RESET_DISPLAY_MARKER`, in `default_data_root` so it survives a relocation restart) set before a restart and consumed on the next index render so the app comes up in the default display (kinetics mode, fresh UI state) — see Rule.md §2.20 |
| `validators.py` | `@validate_json(schema)` decorator — validates and coerces JSON request payloads; injects `validated_data` kwarg into route handlers |
| `math_ops.py` | Server-side regression: `calculate_coef_and_rsquared`, `calculate_kinetics_quantities`, `map_duplicates`, `get_rsquared_threshold` — uses `scipy.optimize.curve_fit` and `numpy` |
| `file_path.py` | Data-folder constants and helpers: `DATA_ROOT`, `validate_in_data_root(path)`, `get_data_subfolders()`, `is_multi_value_timeseries_csv_header()`, `RESERVED_ARCHIVE_FOLDER` (`"root"`) + `is_reserved_data_folder_name(name)` (the `data/root/` archive staging folder is reserved — see Rule.md §2.16). CSV schema utilities: `parse_csv_metadata(lines)` (canonical `# Key: Value` parser), `detect_csv_schema(header_line)` (returns `CSV_SCHEMA_TIMESERIES / KINETICS_CAL / POINT_CAL`). No mutable state. |
| `file.py` | File operations: `get_file_list` (glob), `_read_csv_raw` (shared CSV reader: returns meta lines + headers + rows), `get_dynamic_data` (parse CSV/JSON from disk), `merge_csv_files`, `replace_empty` |
| `file_operations.py` | `remove_csv_columns` — removes columns from CSV files on disk, renumbers `Value:` columns |
| `measure.py` | `sort_csv_file` — sorts calibration CSV data on disk by concentration |
| `browser_mgt.py` | `open_browser`, `close_port`, `cleanup`, `ensure_host_mapping` — browser/process lifecycle |
| `script_monitor.py` | `check_log_for_errors` — scans `log/script_logs.txt` for PyBadge errors |
| `send_command.py` | `connect_to_device` (find PyBadge via serial), `send_command_and_wait_ack` (serial protocol) |
| `ai_assistant.py` | Groq chat (`_groq_chat`, `chat_stream`), MCP tool engine, multilingual system prompts, `proxy_chat_stream()` for desktop proxy mode |
| `ai_settings.py` | Load/save `ai_settings.json`; language defaults; `SUPPORTED_LANGUAGES` catalog; strips obsolete keys on read |
| `user_settings.py` | Load/save `user_settings.json`; user UI preferences: `theme`, `default_mode`, `default_window_size`, `default_subfolder`, `event_log_retention_days`, `merge_directory_picker` (opt-in folder-browser step for the merge dialog), … |
| `data_root.py` | User-selectable data root (frozen builds, Rule.md §2.19): `get_info()` → `{current, default, is_custom}`, `set_data_root(parent)` → `(path, moved)` (copies the whole root into `<parent>/EasyOKAPI`, writes the pointer, then **moves** = removes the original **unless** it is the default, which is kept as a fallback), `reset_to_default()` → `(path, moved)`, plus dry-run previews `preview_data_root(parent)` / `preview_reset()` → `(target, moved)` that validate **without** touching the filesystem (the move is deferred until the user accepts the restart). The `.easyokapi_dataroot` pointer lives **beside** the default folder (`state._dataroot_pointer_path()`, i.e. in `<Documents>`/`<home>`) so it survives the default folder being deleted; resolution is in `state._read_dataroot_override()` (import-time, so a change needs an app restart). `POST /data_root` previews; `POST /data_root/restart` commits the move then relaunches in place via `update_service.restart_after_delay()` and serves `restarting.html`, which polls `/ping` and reloads the tab once the new instance is up. A data root inside `bundle_dir` (the EasyOKAPI program folder) is rejected. The folder is chosen via the `/browse_dirs` navigator. The Windows installer (`setup-frozen.nsi`) Data Folder page lets the user pick the location at install time, and the uninstaller reads the same pointer. |
| `event_logger.py` | Append/read user interaction events; logs go to `log/events/YYYY-MM-DD/HH-MM-SS.jsonl` (one file per app launch per day); `cleanup_old_logs()` removes date folders older than `event_log_retention_days` |
| `hwid.py` | Stable per-machine fingerprint `get_hwid()` (SHA-256 of an OS machine id); basis of the hardware lock. Recipe mirrored by the Windows installer PowerShell |
| `activation_pubkey.py` | Embedded RS256 public key (`ACTIVATION_PUBLIC_KEY_PEM`) for verifying permanent tokens offline |
| `activation.py` | Reads/writes `activation.json`; `get_license_token()`, `AI_SERVICE_URL`; `verify_token()` = RS256 signature + `hwid`-claim check; `is_activated()`/`needs_activation()` gate; `get_hwid()`; `_ALLOW_LEGACY_HS256` grandfather toggle |
| `update_service.py` | Auto-update: `check_for_update()` (calls `/api/version`, compares against the running `state.APP_VERSION`). `download_and_apply(progress_cb)` branches on `sys.frozen`: **source build** downloads a `.py` tarball via `/api/download`, overwrites files in place (preserving user data), `_install_requirements()`, then `restart_after_delay()` (Unix: `os.execv`; Windows: detached PowerShell relauncher that waits for the port to free, then relaunches hidden). **Frozen build** (no `.py` on disk) downloads the platform onedir bundle via `/api/download?platform=&kind=bundle`, stages + verifies it in app-data, and `apply_pending_swap_and_exit()` (driven by `/update/finalize`) spawns a detached PowerShell/`sh` helper that waits for the port, swaps the install dir (rollback on failure), and relaunches the new binary — no pip step. Windows PowerShell spawns resolve the absolute interpreter via `_powershell_exe()` (`%SystemRoot%\System32\…\powershell.exe`) so a stripped frozen `PATH` can't fail the spawn, and use `CREATE_NO_WINDOW \| CREATE_NEW_PROCESS_GROUP` (NOT `DETACHED_PROCESS`, which leaves the console-app `powershell.exe` with no console so it exits before running — see Rule.md §2.18); a handoff failure is logged to `log\update_swap.txt` by `update_routes._delayed_shutdown` rather than swallowed. The coordinator is spawned with `cwd=state.script_dir` (NOT the install dir — a running process holding `$live` as its cwd blocks the rename), and the elevated swap script sets `$ErrorActionPreference='Stop'` so a failed move rolls back instead of nesting the new build inside the old one — see Rule.md §2.18 |
| `export_data.py` | CSV metadata parsing, header writing, sort by concentration |
| `export_cal_json.py` | Standard curve coefficient processing, JSON export for calibration data |
| `get_next_filename.py` | Auto-naming duplicates (e.g., `file_1.csv`) |
| `mode.py` | Returns available measurement modes: `kinetics`, `point`, `calibrate` |
| `quantity.py` | Returns available quantity options for kinetics analysis |
| `range.py` | Returns display range input configuration |
| `routes/__init__.py` | Empty package marker |

### 2.3 Data Collection (`log_cdc_data.py` — the only host logger)
**CDC / USB serial:** `log_cdc_data.py` is spawned by `/run_script` and owns the single serial port for the whole session — it connects, sends `1`/`TIMEOUT:x`/`INTERVAL:x`, waits for ACKs, then reads clean UTF-8 data lines on the same connection and writes the CSV (+ `log/current_output.txt`). No `sudo`/admin, no keycode decoding, no `hidapi`/`pyusb`/`libusbK`, cross-platform. On SIGINT/SIGTERM it sends `0` so the device leaves talking mode.

**Zero-software fallback (HID keyboard):** triggered by the device's **Left button** only — the firmware "types" the CSV via keyboard emulation into whatever text field has focus (e.g. a text editor). There is no host-side HID capture script. The app's automated flow does not use HID.

Firmware transport switch: `open_colorimeter_firmware/src/serial_manager.py` — host-initiated sessions use `transport="cdc"` (`usb_cdc.data`), button-initiated use `transport="hid"`.

### 2.4 Frontend (`static/script/` — 15 JS files)

| File | Responsibility |
|---|---|
| `event-tracker.js` | `logEvent(type, action, details)` — fire-and-forget POST to `/event_log`; loaded before all other scripts |
| `short-hands.js` | DOM utility helpers (`$id`, `$text`, `$hidden`, etc.) |
| `init.js` | Page initialization, event listeners, mode/filter setup |
| `index.js` | `AppState` global state, mode switching, directory updates, `checkServerStatus` |
| `navigation.js` | File table population (CSV and JSON), **data subfolder picker** (`loadDataFolders`, `selectDataFolder`, `filterDataFolderList`, `updateFolderListSelection`, `renameDataFolder`, `deleteDataFolder`) |
| `hid-logging.js` | **PyBadge control UI**: `runScript`, `terminateScript`, `checkScriptStatus`, log display |
| `data-handling.js` | File select/deselect/delete/copy/move, data fetching, export logic |
| `data-display.js` | Chart rendering orchestration, multi-source handling, calibration routines |
| `generate-chart.js` | Chart.js chart creation, dataset construction, annotations |
| `calculate.js` | Math: regression (linear, polynomial, logarithmic, exponential, Michaelis-Menten), R²; calls `/calculate_coef_and_rsquared` for server-side computation |
| `edit-file.js` | SweetAlert2-based file editor modal (CSV and JSON), column operations |
| `report.js` | Report generation (`generateReport`), subject CRUD UI (create/rename/copy/delete subjects, export to subject, view items) |
| `user-guide.js` | Interactive step-by-step user guide with spotlight overlay |
| `ai-chat.js` | Floating AI chat widget: panel toggle, multilingual language selector, settings panel, model download progress, conversation history |
| `bug-report.js` | "Report a Bug" button (left column, below Options): SweetAlert flow — (1) attach logs? (2) pick up to 5 `log/events/` files (`/list_event_log_files`), (3) name the zip. `POST /download_event_logs` bundles the chosen files and downloads the zip to the machine, then a `mailto:` draft to `state.MAINTAINER_EMAIL` opens with an instruction to attach that downloaded zip manually (mailto: cannot pre-attach files). "No, just email" opens a plain `mailto:` with no attachment. |

### 2.5 Templates (`templates/`)

| File | Purpose |
|---|---|
| `index.html` | Main SPA template. Jinja2-rendered with server-side data: `data_root`, `report_root`, `json_root` path constants (instead of `directory`), plus file list, mode, quantity, delimiter, etc. Also `reset_display` → `const RESET_DISPLAY`: when true (first load after a restart) it drops per-view `localStorage` UI state (keeping `theme`/`okapi_ai_lang`/`okapi_ai_first_run`) before `init.js` runs, which then forces kinetics mode — the default display — see Rule.md §2.20. |
| `goodbye.html` | Displayed on `/shutdown` — shows farewell screen before process termination |

---

## 3. Report System

Reports are generated as standalone HTML files and organized under `report/<subject>/`.

| Route | Method | Purpose |
|---|---|---|
| `/get_report_subjects` | GET | List subject subdirectories in `report/` |
| `/save_report` | POST | Save HTML report to `report/<filename>/` |
| `/export_to_report` | POST | Copy a report HTML file into a named subject folder |
| `/get_report_items` | GET | List HTML files within a subject folder |
| `/delete_report_subject` | POST | Delete a subject folder and all its reports |
| `/copy_report_subject` | POST | Duplicate a subject folder |
| `/rename_report_subject` | POST | Rename a subject folder |

---

## 4. Math API

Regression is computed **server-side** via `math_ops.py` (scipy + numpy), exposed as REST endpoints. The JS client calls these for calibration and kinetics analysis.

| Route | Method | Payload | Returns |
|---|---|---|---|
| `/calculate_coef_and_rsquared` | POST | `{x, y, regress_algo}` | `{slope, rSquared, coefficients}` |
| `/calculate_kinetics_quantities` | POST | `{XColumn, YColumn, window_size}` | kinetics analysis object |

Supported algorithms: `linear`, `polynomial`, `logarithmic`, `exponential`, `Michaelis-Menten`.

---

## 5. AI Assistant

### 5.1 Overview
A floating chat widget (bottom-right corner) powered by **Groq** (cloud LLM API). No local model download is required. The `GROQ_API_KEY` lives only on the online server (Heroku config var); desktop instances authenticate via a locally stored activation token rather than holding the key directly. Settings are persisted in `ai_settings.json` at the project root.

### 5.2 Supported Languages
English (en), Vietnamese (vi), Chinese Simplified (zh), French (fr), Japanese (ja), Russian (ru).

### 5.3 Default Model
`llama-3.1-8b-instant` (Groq). Override with `AI_MODEL` environment variable.

### 5.4 MCP Tools (available to the LLM — main branch only)
| Tool | Description |
|---|---|
| `get_app_context` | Current directory, CSV/JSON file lists, data-logger subprocess status |
| `read_csv_file` | Read a CSV file (metadata + first N rows) |
| `read_calibration_file` | Read a JSON calibration file from `json/<mode>/` |
| `get_hardware_status` | PyBadge subprocess running/stopped |
| `get_help_topic` | Built-in docs for a feature topic |
| `trigger_guide` | Launch a full preset workflow guide |
| `trigger_custom_steps` | Launch a focused spotlight guide for specific UI elements |

### 5.5 Routes (main branch)
| Route | Method | Purpose |
|---|---|---|
| `/ai/status` | GET | API readiness, activation state, settings |
| `/ai/chat` | POST | Send messages → SSE stream (proxied or dev-direct) |
| `/ai/activate` | POST | Exchange Easy OKAPI download token for local activation token |
| `/ai/settings` | GET | Return current settings |
| `/ai/settings` | POST | Update settings (language, enabled) |
| `/ai/guides` | GET | Return guide examples for a given language |

### 5.6 Settings file (`ai_settings.json`)
```json
{
  "enabled": true,
  "preferred_languages": ["en", "vi"],
  "first_run_shown": false
}
```
`preferred_languages` is an array of 1–6 language codes. The in-app language button cycles through the selected languages. Files that still contain the obsolete `preferred_language` string key are silently migrated on read by `ai_settings.py`.

### 5.7 Activation file (`activation.json`)
```json
{
  "license_token": "<permanent JWT>"
}
```
Written to the project root during installation or via the in-app activation form. Read by `src/activation.py`. If absent and no `GROQ_API_KEY` is set in `.env`, the AI widget shows "Not activated" and requests a token.

### 5.8 Setup flow for new users
**Option A — During installation (recommended):**
- Mac: `setup-2-install-venv.command` / `installer-mac/install-venv.command` prompt for language preferences, then ask for the Easy OKAPI download token and call `POST /api/activate` on the server. `activation.json` is written automatically.
- Windows: `startwindow-4-venv-run.bat` does the same via `curl` + Python JSON parsing.

**Option B — After installation, from inside the app:**
1. Click the **🤖 AI Assistant** button (bottom-right of the page).
2. If "Not activated" is shown, paste the Easy OKAPI download token from `easyokapi.cbbiotec.vn` into the activation input and click **Activate**.
3. The app calls `POST /ai/activate`, which exchanges the token with the server and writes `activation.json` locally.

**Developer mode (no activation required):**
Set `GROQ_API_KEY` in `.env`. The app detects this and calls Groq directly, bypassing the proxy. Never ship `.env` with a real key.

---

## 6. Installation & Startup

### 5.1 Mac
```bash
# Option A: Installer (.dmg)
# Option B: Scripts
./setup-1-install-pyenv.command   # Install homebrew, pyenv, python
./setup-2-install-venv.command    # Install dependencies to venv/
./setup-3-run.command             # Start the application
```

### 5.2 Windows
Uses the PyBadge CDC serial port (no `libusbK`/Zadig driver needed).
```cmd
startwindow-1-git.bat
startwindow-2-pyenv.bat
startwindow-3-python.bat
startwindow-4-venv-run.bat
```

### 5.3 Direct Python
```bash
python main.py --port 5099 --alias easyokapi.com
python main.py --verbose          # show HTTP logs + backend prints
python main.py --mem-monitor      # enable tracemalloc memory growth tracking
```

---

## 6. Directory Structure (Main Branch)

```
microalbumin-Flask/
├── CLAUDE.md                   # Claude Code entry point
├── Rule.md                     # AI coding rules
├── main.py                     # Flask app entry point (197 lines, blueprint registration only)
├── log_cdc_data.py             # CDC (USB serial) data collection — the only host logger
├── requirements.txt            # Python runtime dependencies (all platforms)
├── requirements-dev.txt        # Test-only dependencies (pytest)
├── setup-*.command             # Mac utility startup scripts
├── startwindow-*.bat           # Windows utility startup scripts
├── installer-mac/              # Mac .dmg installer assets
├── installer-win/              # Windows .exe installer assets
├── src/
│   ├── state.py                # Global state singleton
│   ├── data_root.py            # User-selectable data root (.dataroot pointer)
│   ├── validators.py           # @validate_json decorator
│   ├── math_ops.py             # Server-side regression (scipy/numpy)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── core_routes.py      # Core + browse + report subjects
│   │   ├── file_routes.py      # CSV/JSON CRUD + report CRUD
│   │   ├── hardware_routes.py  # Data-logger subprocess control (CDC default)
│   │   └── math_routes.py      # Regression math API
│   ├── browser_mgt.py
│   ├── export_cal_json.py
│   ├── export_data.py
│   ├── file.py
│   ├── file_operations.py
│   ├── file_path.py
│   ├── get_next_filename.py
│   ├── measure.py
│   ├── mode.py
│   ├── quantity.py
│   ├── range.py
│   ├── script_monitor.py
│   └── send_command.py
├── static/
│   ├── style.css
│   └── script/
│       ├── calculate.js
│       ├── data-display.js
│       ├── data-handling.js
│       ├── edit-file.js
│       ├── generate-chart.js
│       ├── hid-logging.js
│       ├── index.js
│       ├── init.js
│       ├── navigation.js
│       ├── report.js           # Report generation + subject CRUD
│       ├── short-hands.js
│       ├── user-guide.js       # Interactive user guide
│       └── ai-chat.js          # Floating AI chat widget
├── templates/
│   ├── index.html
│   └── goodbye.html
├── data/                       # All user CSV data (auto-created); browsing restricted to here
│   ├── <subfolder>/            # User-named subfolders (created on data run or manually)
│   └── root/                   # RESERVED: installer archive staging for loose data-root files (Rule.md §2.16); users cannot create this name
├── json/                       # Standard curve JSON files
├── log/                        # Script logs directory
├── report/                     # Saved HTML reports (by subject subdirectory)
├── ai_settings.json            # AI assistant settings (auto-created)
├── user_settings.json          # User UI preferences (auto-created, gitignored)
└── sample_data/
```

---

## 6. RAG User Guide Subsystem

A local Retrieval-Augmented Generation pipeline is planned to replace the current keyword-based few-shot injection for the AI-driven user guide. Full architecture, data-flow diagrams, component map, and phased implementation plan are in:

**`easyokapi-knowledge/RAG-USER-GUIDE.md`**

Current state: keyword scan in `_match_guide_example()` (`src/ai_assistant.py:25`) reading `guide_training.json`. Planned replacement: semantic vector search via ChromaDB with a cloud-compatible embedding model, implemented in `src/rag_guide.py` (not yet created).

---

## 7. AI Proxy Architecture

The `GROQ_API_KEY` never ships inside the desktop app package. It lives only as a Heroku config var on the online server. Desktop instances access Groq through a two-phase token mechanism.

### 7.1 Token Lifecycle

```
User logs in at easyokapi.cbbiotec.vn
           │
           ▼
  ┌─────────────────────────────────┐
  │  Download token  (30-min JWT)   │  purpose: "app_download"
  │  {"sub":"42", "exp": now+1800}  │  signed with SECRET_KEY
  └────────────────┬────────────────┘
                   │
       ┌───────────┴────────────┐
       │  hits /api/download    │  gets app tarball from GitHub
       │  hits /api/activate    │  exchanges for permanent token
       │    {token, hwid}       │  ← client also sends its machine fingerprint
       └───────────┬────────────┘
                   │  server: validates sig + exp, checks User DB,
                   │          binds hwid in license_machines (seat cap),
                   │          signs RS256 token with ACTIVATION_PRIVATE_KEY
                   ▼
  ┌─────────────────────────────────┐
  │  Activation token  (permanent)  │  RS256, exp stripped, + "hwid" claim
  │  {"sub":"42", "hwid":"<sha>"}   │  written to activation.json
  └────────────────┬────────────────┘
                   │  stored on disk, never in URLs
                   ▼
  App startup → activation.verify_token():
                   │  RS256 sig verified with EMBEDDED public key (offline),
                   │  "hwid" claim must equal this machine's fingerprint
                   ▼
  Desktop app → POST /ai/proxy/chat {messages, license_token, hwid}
                   │  server: validates RS256 sig (no exp check),
                   │          User.query.get(sub) → is_verified ✓,
                   │          confirms hwid matches a bound seat,
                   │          calls Groq with server-side API key
                   ▼
  Streaming SSE response back to desktop app
```

**Hardware locking (v1.1.12+).** A permanent activation token is bound to exactly
one machine, so copying `activation.json` (or the whole install folder) to another
computer does not work:

- **Fingerprint** — `src/hwid.py` derives a stable SHA-256 fingerprint from an
  OS machine id (Windows `MachineGuid`, macOS `IOPlatformUUID`, Linux
  `/etc/machine-id`). The Windows installer's PowerShell reproduces this recipe
  byte-for-byte so the token it requests at install time matches what the app
  computes at first launch. **Keep the two in lockstep.**
- **Asymmetric signing** — permanent tokens are **RS256**, signed server-side with
  `ACTIVATION_PRIVATE_KEY`; the client embeds only the public half
  (`src/activation_pubkey.py`). The client can therefore verify a token offline
  but can never mint one, so a hand-edited token fails the signature check.
- **Server enforcement** — `license_machines` records `(user_id, hwid)` with a
  seat cap (`MAX_MACHINES_PER_LICENSE`, default 1). `/api/download`,
  `/ai/proxy/chat`, and `/api/version` re-check the presented `X-Machine-Id` /
  `hwid` against the token and the bound seat. Transfer via
  `POST /api/account/machines/deactivate`.
- **Backward compatibility** — legacy HS256 tokens (no `hwid`) are still accepted
  (grandfathered) until every install has re-activated; flip
  `_ALLOW_LEGACY_HS256` in `src/activation.py` to enforce strictly.

### 7.2 Files Involved

**Main branch (desktop app):**

| File | Role |
|---|---|
| `src/hwid.py` | Stable per-machine fingerprint (`get_hwid()`); recipe mirrored by the Windows installer's PowerShell |
| `src/activation_pubkey.py` | Embedded RS256 **public** key (verify-only) for offline token verification |
| `src/activation.py` | Reads/writes `activation.json`; `verify_token()` checks RS256 sig + `hwid` claim; `is_activated()`/`needs_activation()`; `get_hwid()`; `_ALLOW_LEGACY_HS256` toggle |
| `src/routes/ai_routes.py` | `_get_api_mode()` selects proxy vs dev-direct; `POST /ai/activate` sends `{token, hwid}` to the server and saves the returned token |
| `src/ai_assistant.py` | `proxy_chat_stream()` — POST to `/ai/proxy/chat` with `license_token` + `hwid` |
| `src/update_service.py` | `_auth_headers()` adds `X-Machine-Id` to `/api/version` and `/api/download` calls |
| `activation.json` | Permanent activation token stored in the per-user data dir (gitignored) |
| `keys/` | Local working copies of the keypair; **private key is gitignored**, lives in the server's `ACTIVATION_PRIVATE_KEY` env |
| `.env` | Dev-only `GROQ_API_KEY` override; commented out in production packages |

**Online branch (Heroku server):**

| File | Role |
|---|---|
| `src/download_service.py` | `issue_activation_token(payload, hwid)` — RS256-signs (or legacy HS256 fallback), adds `hwid`; `validate_activation_token()` — RS256-then-HS256, no expiry check; `_activation_private_key()`/`_activation_public_key()` |
| `src/account.py` | `LicenseMachine` model — the `(user_id, hwid)` seat table |
| `src/routes/account_routes.py` | `POST /api/activate` binds `hwid` (seat cap) and issues the locked token; `/api/download` machine-checks the Bearer token; `GET /api/account/machines` + `POST .../deactivate` (transfer); `GET /api/activation-pubkey` |
| `src/routes/ai_routes.py` | `POST /ai/proxy/chat` — validates the token, confirms the `hwid` matches a bound seat, calls Groq, streams SSE |

### 7.3 API Mode Selection (main branch)

`_get_api_mode()` in `src/routes/ai_routes.py` returns the active mode on every request:

```
activation.json present?  →  mode = 'proxy'  (credential = license_token)
       ↓ no
GROQ_API_KEY in .env?     →  mode = 'dev'    (credential = api_key, calls Groq directly)
       ↓ no
                          →  mode = None      (AI widget shows "Not activated")
```

Proxy mode always takes priority over dev mode when both are present.

### 7.4 Security Properties

| Property | How it is achieved |
|---|---|
| `GROQ_API_KEY` never leaves Heroku | Only read from `Config.GROQ_API_KEY` inside `/ai/proxy/chat` |
| Activation requires a live account | `/api/activate` and `/ai/proxy/chat` both call `User.query.get()` + `is_verified` check |
| Stolen download URL has 30-min window | `validate_download_token` enforces `exp` on `/api/activate`; permanent token is issued server-side |
| Permanent token can be revoked | Deleting or un-verifying the user account blocks `/ai/proxy/chat` on the next request |
| Token not exposed in URLs | Activation token travels in POST body only; never in query strings or server logs |

---

## 8. Key Differences from `online` Branch (Summary)

| Aspect | `main` branch | `online` branch |
|---|---|---|
| Data storage | Local filesystem (`os`, `open`, `Path`) | In-memory `USER_DATA` dict |
| Directory browsing | OS filesystem navigation | N/A (upload-based) |
| Data logging | Enabled (PyBadge USB CDC serial) | Disabled |
| Users | Single user, no sessions | Multi-user with Flask sessions |
| Google Drive | Not present | Integrated (OAuth 2.0) |
| Static serving | From `static/` (source) | From `static/dist/` (obfuscated) |
| Build step | Not required | Required (`npm run build`) |
| Deployment | Local machine | Heroku |
| Real-time | No SocketIO | Flask-SocketIO with eventlet |
| Flask version | 1.1.4 | Latest (with SocketIO support) |
| Shutdown endpoint | Present (`/shutdown`) | Not applicable |
| `PRODUCTION_MODE` | `True` (in `state.py`) | `True` (always) |
| Browser auto-launch | Yes (`browser_mgt.py`) | No |
| Installers | `.dmg` / `.exe` / batch scripts | N/A |
| Route organization | Flask blueprints in `src/routes/` | Monolithic `main.py` |
| Math computation | Server-side (`math_ops.py`, scipy) | Client-side JS only |
| AI backend | Groq via proxy (`activation.json`) | Groq direct (`GROQ_API_KEY` on Heroku) |
| AI key location | Never on client; proxied via Heroku | Heroku config var only |
