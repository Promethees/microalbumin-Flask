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

### 2.3 Data Logging — PyBadge Communication

- The application communicates with a physical **PyBadge** (Adafruit) colorimeter via USB.
- **Default transport is CDC (USB serial)**, not HID. `/run_script` spawns **`log_cdc_data.py`** as a subprocess that **owns the single serial port for the whole session**: it connects (`send_command.connect_to_device`), sends `1` / `TIMEOUT:x` / `INTERVAL:x`, waits for the device ACKs, then reads the data stream on the **same** connection. Flask must **not** also open the port — one owner only.
  - **Anti-pattern**: do not open the serial port in the Flask process (e.g. to send commands or "0") while the CDC logger subprocess is running — the OS allows a single owner and the second open will fail.
  - Same `python` interpreter for Mac/Windows (`sys.executable`, or the Windows `venv/Scripts/python.exe`); **no `sudo`/admin** — CDC serial needs no elevated privileges and no `libusbK` driver.
- **HID keyboard is the zero-software fallback only**, triggered by the device's **Left button** (firmware `serial_manager.serial_talking(start_by_host=False)` → `transport="hid"`). The device "types" CSV as keystrokes into whatever text field has focus (e.g. a text editor) — there is **no host-side HID capture script**; the old `log_hid_data.py` / `log_hid_data_pyusb.py` (and the `hidapi`/`pyusb`/`libusbK` stack) have been removed. The host app's automated flow only uses CDC.
- Firmware transport switch lives in `open_colorimeter_firmware/src/serial_manager.py` (`_write()` routes to `usb_cdc.data` for CDC or the HID `layout` for the fallback). The device boot must enable `usb_cdc.data` **and** leave HID keyboard on (`boot_for_CDC.py` does both — `usb_cdc.enable(data=True)` plus the default HID keyboard).
- CDC delivers exact bytes, so `log_cdc_data.py` parses **clean text** (`# Measurement:`, `Timestamp,Value:1`) — unlike the HID path, which had to undo keyboard up-casing/modifier-stripping (`3 MEASUREMENT:` etc.).
- Because CDC is a reliable byte stream, the old **missed-read / resend** machinery has been removed entirely (no `max_resend_attempts` setting, no `check_log_for_missed_read`, no resend state). `check_status` reports `running` / `success` (session completed, log has "New session started") / `failure`.
- **Session-end sentinels (device → host):** the firmware ends a host (CDC) session by streaming one of two text sentinels, parsed by `log_cdc_data.py` (`is_end_session` / `is_stopped` → `_finish_session`, which logs the sentinel verbatim):
  - `SESSION TIMEOUT` — the configured timeout elapsed.
  - `SESSION STOPPED` — the user pressed the device's **Left button** mid-session (firmware `serial_manager.serial_talking()` emits it when `transport == "cdc" and not start_by_host`; the host's own `0`-command stop passes `start_by_host=True` and does **not** emit it). Both repos are kept in lockstep — adding/renaming a sentinel means editing **`open_colorimeter_firmware/src/serial_manager.py` on every branch (`main`, `open-plus`, `open-uv`)** and the host parser + `script_monitor.check_log_for_end_reason` together.
  - The reason flows to the UI announcement: `check_log_for_end_reason()` → `check_status` message, mirrored by the `cdc-logging.js` `fetchLogs` regex; the popup reads "Session ended due to timeout." vs "Session stopped manually on the device." **Anti-pattern**: do not hardcode the timeout wording in `resetUIAfterCompletion` — it must use the backend's reason-aware message so whichever poller wins the race shows the correct cause.
- HID logging is **disabled in calibrate mode**.
- The subprocess writes to `log/script_logs.txt`, which is monitored for errors (`script_monitor.check_log_for_errors` / `check_log_for_session_start`).
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
- **Reserved folder name `root`**: `src/file_path.py` exports `RESERVED_ARCHIVE_FOLDER = "root"` and `is_reserved_data_folder_name(name)` (case-insensitive, trims whitespace). `data/root/` is the staging folder the installers use to hold loose data-root files during the uninstall/reinstall archive cycle (see §2.16), so a user **cannot** create a subfolder called `root`. The check is enforced server-side in `/run_script` (subfolder) and `/rename_data_folder` (new_name), and client-side in `hid-logging.js` (new-folder input) and `navigation.js` (`isReservedDataFolderName`, rename validator). The JS constant `RESERVED_DATA_FOLDER` mirrors the Python constant — keep the two in sync.
- `src/state.py` tracks `data_root_path`, `report_root_path`, `json_root_path` (all auto-created on startup).
- Route `GET /get_data_folders` returns `[{"name": "...", "path": "..."}, ...]`.
- Route `POST /rename_data_folder` (`{path, new_name}`) renames a subfolder in place via `os.rename`. The source `path` must validate inside `data_root` and not be the root itself; `new_name` must be a bare folder name (rejects `..`, `/`, `\`, `\x00`, and any `.`/`_` prefix so the result stays visible in the picker — `get_data_subfolders()` hides those). Returns the new absolute `path` so the frontend can re-point the active directory when the renamed folder was selected. Blocked (`423 LOCKED`) while the HID collection process is running, mirroring `/delete_data_folder`. Frontend: `renameDataFolder(name, path)` in `navigation.js`, triggered by the pencil button on each `.folder-item`.
- Route `POST /browse` is **stateless** (never writes backend state): validates path is within `data_root_path` or `report_root_path`, returns files. Removed routes: `/get_parents`, `/get_children`. **Exception — on-disk ConcenUnit back-fill**: for a path inside the data root it first calls `file.ensure_concen_unit_in_dir()` to insert a `# ConcenUnit: ng/µL` line into legacy CSVs lacking it (idempotent, best-effort; see Rule.md §2.10). This is the only filesystem write `/browse` performs and is confined to the data root.
- Template variables passed from `index()`: `data_root`, `report_root`, `json_root` (replaces `directory`).
- JS constants: `DATA_ROOT`, `REPORT_ROOT`, `JSON_ROOT` (replaces `rootPath`). Defined inline in `index.html` before external scripts are loaded.
- Path delimiter: `\\` on Windows, `/` on Mac/Linux.
- Hidden directories (starting with `.` or `_`) are filtered out.
- **Anti-pattern**: Do **not** restore `get_directory()`, `browse_directory()`, `get_parent_directory()`, or `current_directory` global in `file_path.py` — these have been permanently removed.
- `/run_script` payload uses `subfolder` (folder name only, no slashes) instead of `base_dir`; backend constructs `data/<subfolder>` and creates it if needed.
- Route `POST /move_file` (`filename`, `path`, `dest_path`; form-encoded) moves a CSV data file between data subfolders. Both `path` and `dest_path` must validate inside `data_root`; `filename` must be a bare name (no `/`, `\`, `..`); same-folder moves are rejected; a name clash in the destination is auto-incremented via `get_next_filename` so a move **never** clobbers an existing file. Blocked (`423 LOCKED`) while the HID process runs. Frontend: `moveFile()` in `data-handling.js` (Move button `#move-file-btn`, enabled/disabled alongside `#copy-file-btn`) shows a SweetAlert2 folder-select dialog (data root + subfolders, excluding the current folder). CSV-only: it bails in `report` mode.
- Route `POST /export_to_report` copies a measurement file **out of the data tree into a report subject** (`report/<subject>/`). The source (`file_path`) must therefore be confined to the **DATA root** (`validate_in_data_root` / `DATA_ROOT`), **not** the report root — relative paths resolve against `DATA_ROOT`; a source outside it is rejected `403`. **Anti-pattern**: do not anchor this source check on `state.report_root_path` — the frontend (`exportToReport()` in `report.js`) sends a path under `data/`, so anchoring on the report root makes every export 403 (this regressed once and only surfaced visibly after a data-folder relocation).

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
- **Concentration unit (`# ConcenUnit`)**: the unit a concentration is expressed in — the `# Concentration:` value of a raw timeseries file, or the `Concentration` column of a calibration file. One of **`ng/µL` (micro sign), `nM`, or `%`** — exactly these three (`CONCEN_UNITS` in `src/file_path.py`, the single source of truth, injected into the page as the `CONCEN_UNITS` JS const + validated in `user_settings._VALID_CONCEN_UNITS`); a **label only** — switching units never converts the recorded numbers. Constants + the `get_concen_unit(meta)` fallback helper live in `src/file_path.py` (`CONCEN_UNITS`, `DEFAULT_CONCEN_UNIT`). The user's preferred default for **new exports** is the `default_concentration_unit` user setting; the frontend `#concen-unit` dropdown (Data Display section, options rendered from `concen_units`) reflects the loaded file's unit and selects the unit for the next calibration export (`getMetaConcenUnit` in `data-display.js`). In the **Edit File** metadata table, `ConcenUnit` is edited via a **`<select>` of `CONCEN_UNITS`** (not free text) so an invalid unit can't be typed — `collectTableContent` reads the select's value; keep the JS `CONCEN_UNITS` injection in lockstep with the Python list.
  - **Backward compatibility — absent ⇒ ng/µL**: older files predate this line. When `ConcenUnit` is missing it is assumed to be `ng/µL`. The line is **back-filled onto disk when a data folder is selected**: `POST /browse` (data-root paths only) calls `file.ensure_concen_unit_in_dir()`, which inserts `# ConcenUnit: ng/µL` into the metadata block of every recognized CSV (timeseries / kinetics-cal / point-cal) lacking it. Idempotent, best-effort, and it **always writes `ng/µL`** (never the user's preferred default) so it can never mislabel existing data.
  - **Export consistency guard (required)**: `export_data.is_metadata_consistent()` compares the target file's `ConcenUnit` (defaulting an absent one to `ng/µL`) against the export's unit — you **cannot** append `nM` rows to a file recorded as `ng/µL`, or vice versa. `/export_data` returns a clear `Concentration unit mismatch` error; pick a different file or unit. `write_metadata()` emits the `# ConcenUnit:` line for new calibration files.
  - **Anti-pattern — single-entry export fields must stay in the `@validate_json` schema**: `/export_data` supports two payload shapes — a **batch** (`entries: [...]`, used when >1 source is exported) and a **single entry** (the row's `con`/`maxrate`/`slope`/`sat`/`timeSat`/`estValue`/`timePoint` at the top level, used for exactly one source). The single-entry path reads those values from `validated_data`, but `@validate_json` **drops any key not declared in its schema**, so every one of those fields must remain declared (permissive `((str,int,float),'NONE',False)`) or a one-source export silently writes a row of all `NONE` (the batch path is unaffected because list items pass through untouched). Covered by `test_export_data_single_source_*`.
  - **CDC mandate**: a host-initiated CDC session must send all **four** metadata lines (`Measurement`, `Unit`, `Concentration`, `ConcenUnit`) before the data header — `log_cdc_data.handle_main_header()` gates on `len(metadata) == 4`. The firmware (`open_colorimeter_firmware`, separate repo) is updated in lockstep to always emit `# ConcenUnit:`; an old 3-line firmware session is rejected by design. **Anti-pattern**: do not relax the gate back to 3 or migrate the *live* file from the `#concen-unit` dropdown (legacy files are migrated only via `/browse`).
- **CSV↔JSON identity matching (calibration pairing)**: a measurement CSV (kinetics/point) is paired with a **calibration JSON** to derive concentration; the pair must share the same **Measurement + Unit + ConcenUnit**.
  - **JSON identity**: calibration JSONs store `for_meas` (Measurement), `meas_unit`, `concen_unit` (written by `/export_cal_coefs`; the JS caller sends `measUnit`=`getMetaUnit(metaData)` + `concenUnit`=`#concen-unit`). These keys are plain JSON, so they are editable in the Edit-File **text** editor and shown in the JSON Fit-Information panel. In the Edit-File **graphic** editor (the default for the JSON table), `concen_unit` is rendered as a **`<select>` of `CONCEN_UNITS`** via the `configs` map in `edit-file.js` (the same mechanism as `fit_type`); a legacy value outside the catalog is preserved as an extra option. `meas_unit` stays free text (measurement units aren't a fixed catalog). Keep the `CONCEN_UNITS` injection in lockstep with the Python list.
    - **Legacy back-fill**: a JSON predating this feature has neither key. `file.ensure_cal_units_in_dir()` writes the defaults onto disk for every non-`*.meta.json` calibration JSON missing them — `meas_unit` → `"NONE"`, `concen_unit` → `ng/µL` — as the list is fetched (`/get_json_cal`, and the index kinetics first paint). Idempotent, best-effort, mirroring the CSV `ensure_concen_unit_in_dir`. The `"NONE"` placeholder is **normalized back to a wildcard** (`None`) by `build_json_identity` / `_norm_identity_value` (Python) and `_normIdent` (`navigation.js`), so a back-filled curve still pairs with any measurement unit while keeping ConcenUnit enforced.
  - **Identity surfaced per file**: `file.build_csv_identity()` / `build_json_identity()` return `{name: {measurement, unit, concen_unit}}` (CSV `unit` = `# Unit` for timeseries / `# MeasUnit` for calibration, mirroring `getMetaUnit`; concen defaults ng/µL). `/browse` returns `files_identity`, `/get_json_cal` returns `files_identity`, and the index route injects `FILE_IDENTITY` / `CAL_JSON_IDENTITY`. Both tables show an inline `Measurement·Unit·ConcenUnit` badge (`.file-identity`), rendered in **both** the Jinja first paint and `navigation.js` (`_identityBadge`) — keep in lockstep (Rule §2.21).
  - **Match rule** (`identityMatch` in `navigation.js`): Measurement and Unit are **wildcards when absent on either side** (legacy JSONs stay usable); ConcenUnit is **always enforced** (absent ⇒ ng/µL). Applies in **kinetics/point** mode only.
  - **UX**: when a counterpart is selected, non-matching rows in the other table keep their badge but their **Select button is disabled** with a reason tooltip (`_selectDisableAttrs`); selecting/deselecting re-renders the counterpart table to refresh disabling. `selectFile` also raises an explicit `Swal` mismatch error as a backstop if a disabled button is bypassed. **Anti-pattern**: do not enforce a missing Measurement/Unit as a hard mismatch (it would orphan legacy JSONs — they are wildcards); do not skip the `selectFile` backstop (the disabled button alone is not authoritative).
  - **Re-validate on edit** (`revalidateActivePairing` in `data-handling.js`): the selection-time backstops only fire when a file is *picked*. Editing a file's metadata while a CSV **and** a calibration JSON are both selected can misalign a previously-matched pair without any re-selection, so the now-mismatched curve would keep being applied. After a successful `/edit_file` the handler reloads the edited file, refreshes the identity maps (`updateDirectory` / `updateJSONTable`), then calls `revalidateActivePairing()`, which compares the **authoritative loaded data** — `csvIdentityFromMeta(AppState.metaData)` vs `jsonIdentityFromContent(AppState.currentJSONcontent)`, not the table maps (which may lag) — and on a clash **unpairs the curve** (`deselectFile('#json-table')`, clearing any derived concentration) with a warning, suppressing the routine success toast. **Anti-pattern**: do not re-validate against `AppState.fileIdentity`/`jsonIdentity` straight after an edit (stale until refetched); use the loaded `metaData`/`currentJSONcontent`.
  - **Identity-aware search** (`filterTable` in `navigation.js`): the CSV (`#file-search`) and calibration-JSON (`#json-search`) search boxes use **space-separated positional filters**, all AND-ed (set intersection): position 1 = **name**, 2 = **measurement**, 3 = **unit**, 4 = **ConcenUnit**. `parseSearchQuery` tokenizes the query (quoted values allowed for spaces, e.g. `std "Total Protein" AU nM`); a bare `-` or empty `""` **skips** that position, and extra tokens past the fourth are ignored. `_identityFieldMatch` tests each active filter as a **case-insensitive substring** against the row's identity from `AppState.fileIdentity` / `jsonIdentity` (absent ConcenUnit defaults to `ng/µL`; absent Measurement/Unit match only an unset filter, so a measurement filter hides files that don't declare it). The name cell holds the identity badge, so the badge text is stripped before name matching and identity is read from `AppState`, never scraped from the DOM. Field filters are **ignored** for the report-subject folder listing (which reuses `#file-table` without identity). **Anti-pattern**: do not parse the badge text out of the cell for filtering — look identity up from `AppState`.
- **Point-mode reference unit**: the "Set reference point to export" input (`#exp-json-time-value`) is entered in the currently-selected `#time-unit`; its label and value rescale whenever `#time-unit` changes (`refreshExpTimeValueForUnit` in `init.js`). Estimates use the selected unit, but **exports always convert the reference point to minutes** (`generatePointData` in `data-handling.js`) so calibration files stay in minutes (`TimeUnit: minute`).

### 2.11 OS-Specific Behavior

- **Path delimiters**: `\\\\` for Windows, `/` for Mac/Linux (set in `main.py` global).
- **Data logging**: Single cross-platform path `log_cdc_data.py` (CDC serial, no `sudo`/admin, no `hidapi`/`pyusb`/`libusbK`). The device's Left-button HID-keyboard fallback needs no host script — it types into any focused text field.
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
- Desktop instances authenticate via `activation.json` (permanent license token, **hardware-locked** — see §2.17) and proxy requests through the online Heroku server, sending their `hwid` with each proxy call.
- **AI entitlement is split by build type** (`_get_api_mode()` / `_dev_key()` in `src/routes/ai_routes.py`): an **installed/frozen build** (`state.IS_FROZEN`) requires a valid activation token — the `.env` `GROQ_API_KEY` bypass is **ignored** there, so a token is genuinely mandatory and dropping a `.env` beside the binary cannot unlock the AI. A **source run** (`python main.py` / `setup-3-run.command`) needs no token: `GROQ_API_KEY` in `.env` enables `dev` mode (and the transient proxy-error fallback) directly. The frozen rule lives only in `_dev_key()` — both mode selection and the proxy fallback consult it, so do not re-derive it elsewhere. **Anti-pattern**: never honour a local Groq key in a frozen build.
- AI-assistant preferences live in **`user_settings.json`** via `src/user_settings.py` (`ui_language`, `ai_feedback_enabled`) — **not** in a separate `ai_settings.json`. `user_settings.py` also owns **`SUPPORTED_LANGUAGES`**, the single source of truth for the six UI/AI-chat languages, imported by `i18n.py` and `routes/ai_routes.py`. The old `src/ai_settings.py` (its `load()`/`save()`/`ai_settings.json` persistence was dead — nothing wrote or read the file — and it held only that one constant) was **deleted**; the constant moved into `user_settings.py`. **Anti-pattern**: do not recreate `ai_settings.py` or `ai_settings.json` — add per-user AI prefs to `user_settings.py`. (Legacy `ai_settings.json` files stay in `update_service._PRESERVE` only so an old install's copy is never clobbered on update.)
- All chat calls go through `src/ai_assistant.py` using the `requests` library.
- The AI blueprint is `ai_bp` in `src/routes/ai_routes.py`, mounted at `/ai/*`.
- Supported languages: `en`, `vi`, `zh`, `fr`, `ja`, `ru`. System prompts for all 6 are embedded in `ai_assistant.py`.
- `AI.activeLang` in `ai-chat.js` tracks the currently active language, selected via the header button; chat requests send `AI.activeLang` (chat language is independent of `ui_language`).
- **Server-side rate limit + payload caps are the authoritative guard on `/ai/chat`** (`routes/ai_routes.py`). The browser limiter (15/60s in `ai-chat.js`) is UX only — it is bypassable and every accepted call spends a paid Groq/proxy request. The route trims the forwarded history to the newest `_MAX_MESSAGES` turns, rejects an over-cap payload with **413** (`_MAX_MSG_CHARS` per message, `_MAX_TOTAL_CHARS` summed), and refuses more than `_RATE_MAX` requests per `_RATE_WINDOW`s with **429** + a `Retry-After` header — all **before** any upstream call, and the size gate runs before the limiter records a hit. One process-wide sliding window (deque under a lock) suffices because the app is single-user. `/ai/match` caps its query to `_MAX_MSG_CHARS` (the local difflib matcher). The 413/429 messages are localized via `_localized()`. **Anti-pattern**: do not rely on the client limiter alone, and do not call the proxy/Groq before the size + rate checks.
- MCP tools (`TOOLS` list in `ai_assistant.py`) give the LLM access to live app state: file list, CSV content, calibration JSON, hardware status, and built-in help docs.
- **LLM-supplied file paths are untrusted and must be confined to their root.** A tool argument that names a file (`read_csv_file` → `validate_in_data_root`; `read_calibration_file` → `validate_in_json_root` + `os.path.basename` on the filename + `mode` pinned to `{kinetics, point}`) is chosen by the model, so it is an injection surface. `json/` sits directly inside `state.script_dir` next to `activation.json` (the license token), `.env`, and `user_settings.json`; an unvalidated `..` in the filename/mode reaches those and returns them to the model/proxy. **Anti-pattern**: do not `os.path.join(root, mode, filename)` a tool-supplied path without a root check — mirror `read_csv_file`, which always did.
- **Streaming**: `chat_stream` (the dev/local-Groq path) uses `_groq_chat_stream`, which sets `stream=True` and yields content deltas live as `{"type":"chunk"}` SSE events (the frontend renders them token-by-token). Tool calls are reassembled from their streamed argument fragments (accumulated per `tool_call.index`) so the tool-calling loop is unchanged. The guide-launched confirmation is emitted only when the model streamed no prose that turn (`streamed_any`), to avoid duplicating its message. The production path (`proxy_chat_stream`) relays whatever the online server streams.
- **Deterministic no-LLM turns run once, for BOTH paths, in the route.** Greeting (`_is_greeting`→`_GREETING_RESPONSE`), out-of-scope refusal (`_is_out_of_scope`→`_OUT_OF_SCOPE`), and the report quick/full clarification flow are produced by `ai_assistant.deterministic_events(messages, language, ui_context)` — a pure function returning a list of SSE event dicts, or `None` to fall through to the model. `/ai/chat` calls it **after the rate-limit/payload gate but before dispatching** to either `proxy_chat_stream` or `chat_stream`, so an activated (proxy) user gets exactly the source-run behaviour instead of depending on the `online` server to re-implement it — and no upstream call is spent on a turn the model never needed. `chat_stream` also calls `deterministic_events` first (idempotent) so it stays correct when invoked directly (dev fallback, tests). **Anti-pattern**: do not re-inline greeting/out-of-scope/report-clarify branches into `chat_stream` only — that path is skipped for activated users, so the behaviour would silently diverge; keep them in `deterministic_events` so the route applies them to both.
- **Truncation is flagged, not silent; an empty reply is retried, not dead-ended.** `_groq_chat_stream` records `finish_reason` on its `("result", …)`. When a plain-text answer stops for `"length"` (hit `_MAX_COMPLETION_TOKENS`), `chat_stream` appends the localized `_TRUNCATION_NOTICE` so a rare over-budget reply reads as continuable rather than cut off mid-word. When the model returns **no prose and no tool call**, `chat_stream` retries the turn **once with tools disabled** (`empty_retry_used` latch — a tool-less ask reliably yields text) before giving up quietly (the client shows its own `_EMPTY_REPLY` fallback). **Mirror both on the `online` proxy**, which controls its own `max_tokens` and loop. **Anti-pattern**: do not return silently on an empty completion, and do not let a `length` cut-off reach the user unlabelled.
- **Tool schemas carry NO `enum` constraint — validate permissively in `_run_tool` instead.** Groq validates tool-call arguments against the JSON schema server-side, so an `enum` turns any out-of-set value the model picks into a hard 400 (`tool_use_failed`) *before* `_run_tool` runs — the single biggest source of "failed to call a function" on the small Llama models (e.g. `get_help_topic` with `topic="about"` for "what is this software about"). The valid values stay in each parameter's `description` (so the model still knows them), but enforcement moves into `_run_tool`, which normalizes/falls back: unknown `topic` → nearest key or the `overview` doc; bad `workflow` → `general`; out-of-range `position` → `bottom`; `mode` must still be `kinetics`/`point` (also a path-safety check). **Anti-pattern**: do not add `enum` (or other hard `required`/format constraints the model can violate) to a tool schema — describe the allowed values and validate in `_run_tool`. Completion budget is `_MAX_COMPLETION_TOKENS` (2048, up from 1024/500) so neither a long tool-call argument list nor a full multi-mode coefficient explanation is truncated into malformed JSON or a mid-sentence cut-off. The system prompts also carry an ANSWER-DIRECTLY rule telling the model to answer general/conceptual questions from its own knowledge and reserve tools for live data or an explicit guide — cutting redundant tool calls. **Mirror all of this on the `online` proxy server**, which has its own TOOLS/prompt copy; the desktop dev path is fixed here but the activated build calls the proxy.
- **Invalid tool call is recoverable, not an error to show the user.** Small Llama models sometimes emit a tool call Groq rejects with a **400** (`tool_use_failed` / "did not match schema" / "Failed to call a function") — typically on short, ambiguous prompts ("what is this software about" → `get_help_topic` with an out-of-enum `topic`). `_map_groq_error` tags these via `_TOOL_FAILURE_MARKERS` as the stable code `tool_call_failed`; `chat_stream` then **retries the same turn once with tools disabled** (`active_tools=None`, `tools_enabled` latch) so the model answers in plain text instead of leaking `failed_generation`. The frontend (`ai-chat.js`) renders the `tool_call_failed` code — **and any raw Groq tool-failure string** from the proxy path, matched by `_isToolFailure()` — as the friendly localized `_TOOL_FALLBACK` line. The dev path truly recovers (retry); the proxy path can only render nicely here — the same retry belongs on the `online` server. **Anti-pattern**: do not surface a raw `tool_use_failed`/`failed_generation` string to the user, and do not treat an invalid tool call as fatal without the tools-off retry.
- **Report quick/full clarification is language-independent.** `_needs_report_clarification` recognises "report" in all six languages (`_REPORT_WORDS`) and `_get_pending_report_type` identifies the prior clarify turn by **exact match** against `_REPORT_CLARIFY_PROMPTS.values()` (`_is_report_clarify_prompt`), not by substring-matching the English phrase "quick report"/"full report" — the localized prompts never contain those, so the old check silently failed for vi/zh/fr/ja/ru. Quick/full answers are matched against the multilingual `_QUICK_KWS`/`_FULL_KWS` sets. **Anti-pattern**: do not gate this flow on English substrings of a string that is emitted localized.
- **Guide steps can point INTO a SweetAlert2 dialog.** A step whose `target` references a `.swal2-*` selector is a *dialog step* (`UserGuide._isSwalStep`). SweetAlert2's `.swal2-container` sits at `z-index: 2147483000` — ~2.1 billion above the guide's normal `~10000` layer — so `positionSpotlight` lifts the **spotlight** (`2147483646`) and **tooltip** (`2147483647`) above it and swaps the full-page dark curtain for a bright ring (`.user-guide-spotlight-swal` — the pulse keyframes re-apply the curtain, so the class also `animation: none`s them); the **overlay stays low (`9998`)** so Swal's own backdrop does the dimming (elevating it would darken the dialog). A dialog step **advances when the dialog closes** (confirm OR cancel), not on a click — the click that confirms also removes the highlighted element — via `_watchSwalClose`, which polls `document.body.contains(element)` on the specific found element (a follow-up "success" toast is a different element, so it doesn't falsely keep the step alive). `attachInteractionHandler` early-returns for dialog steps so the normal click/blur handler can't double-advance. The `/save-range` slash command (`ai-chat.js` `_runSaveRangeGuide`) is the reference flow: step 1 `#save-range-btn` (interactive) opens the "Save Range to CSV" dialog, step 2 `.swal2-input` is the dialog step. **Anti-patterns**: do not attach the normal interaction handler to a dialog step (double-advance); do not elevate the guide overlay for a dialog step (it darkens the dialog); do not drive advancement off a click on a `.swal2-confirm`/input (the element is torn out on close — watch for close instead). **To let the AI author dialog flows**, the `.swal2-*` selectors and an example must be added to `trigger_custom_steps` on both the desktop tool schema and the `online` proxy (not yet done — the current demo is the local slash command).
- Conversation history is **client-side only** (stored in `ai-chat.js` `AI.messages` array) — the backend is stateless, consistent with the single-user no-session rule.
- **Edit-and-resend**: user messages that are LLM queries are rendered editable (`_addEditableUserMsg`, hover-pencil → inline textarea → Save & resend / Cancel). Saving truncates `AI.messages` at that message's index and re-sends the new text through `_sendToLLM`, so every reply after the edited turn is discarded — matching ChatGPT-style edits. The `msgIndex` stored on the bubble is the message's position in `AI.messages`; this stays valid because the history is only ever appended to or truncated from the end (never shifted from the front). Slash-command/guide echoes use the plain `_addMsg('user', …)` and are **not** editable. Editing is blocked while a reply is streaming (`AI.currentAbort`). The edit-UI strings live as per-language maps keyed by `AI.activeLang` (`_EDIT_HINT`/`_EDIT_SAVE`/`_EDIT_CANCEL`), like the rest of the chat widget — they are **not** `ui_translations` keys (chat language is independent of `ui_language`). **Anti-pattern**: do not make guide/slash echoes editable, and do not key the edit off a DOM position — use the stored `msgIndex` into `AI.messages`.
- **New conversation**: a header **+** button (`#okapi-ai-new-btn`) → `OkapiAI.newChat()` starts a fresh chat — clears `AI.messages`, resets `AI.lastAction`, wipes the on-screen messages, and re-shows the welcome. It confirms first via `Swal` when a visible conversation exists (translated `_NEW_CHAT_CONFIRM_*` maps; falls through to an immediate reset when `Swal` is absent or the chat is empty). This is the discoverable button form of the `/clear` slash command (which still only empties history).
- **Answer feedback + learned matcher weights** (`src/ai_feedback.py`, `/ai/feedback`): every assistant answer gets a 👍/👎 row (`_attachFeedback` in `ai-chat.js`); 👎 reveals an optional comment box (Send / Skip both record the down-vote). All ratings are appended to `ai_feedback.jsonl`. When the rated answer was a **locally matched guide** (`source == "guide"` with a `guide_id` from `/ai/match`), the rating also tunes a per-guide coefficient in `ai_guide_weights.json` (`{guide_id: {weight, terms}}`): a 👍 raises `weight` (+`_UP_STEP`) and appends the query's content words to `terms`; a 👎 lowers it (−`_DOWN_STEP`), clamped to `[_MIN_WEIGHT, _MAX_WEIGHT]`. `_match_guide_example` adds `learned_terms` as extra keywords **before** the 0.1 baseline gate and `learned_bonus` to the score **after** it — so a 👍 makes similar queries match more confidently and ~5 👎 push even a strong, mode-boosted match below the launch threshold, while a positive weight can **never** make a zero-keyword (unrelated) guide fire. **LLM answers are logged only** — Groq is a third-party model that can't be retrained here, so they carry no `guide_id` and move no weight. Feedback on slash-command/button-launched guides is intentionally **not** offered (those are deterministic, not matched — reinforcing them would pollute the signal). Both files live in `state.script_dir` (alongside `ai_settings.json`), are gitignored, and are in `update_service._PRESERVE`. The feedback-UI strings are per-`AI.activeLang` maps (`_FB_*`), not `ui_translations`. **Anti-patterns**: do not apply `learned_bonus` before the baseline keyword gate (a 👍 would let a guide hijack unrelated queries); do not attempt to "improve" the LLM from feedback (Groq can't be retrained); do not log feedback to a path outside `state.script_dir`.
- **Feedback management + opt-out**: App Settings → **AI Assistant** exposes an `ai_feedback_enabled` user setting (default on), an **Export feedback** button (`GET /ai/feedback/export` → zip of both files) and **Reset learning** (`POST /ai/feedback/reset` → deletes both files); `GET /ai/feedback/stats` feeds the summary line. When the toggle is **off**, `_attachFeedback` hides the 👍/👎 row, `POST /ai/feedback` no-ops (`{recorded:false}`), and `_match_guide_example` ignores all learned weights — gated by `ai_feedback.is_enabled()`, read **once per match** (never in the per-guide loop). The two files are **already preserved/archived** outside this feature — in-app updates keep them via `_PRESERVE`, and the Windows uninstaller's data-folder backup ZIP includes them — so do **not** add a separate uninstall/update hook for them. **Anti-pattern**: do not call `is_enabled()` inside the per-guide scoring loop (one `user_settings.load()` per example per query).
- **Anti-pattern**: Do not add Ollama, local model pulls, or `pull_model`/`pull_status` routes — the app no longer uses a local model server.

### 2.15 Auto-Update — In-Place Code Update

- Auto-update is handled by `src/update_service.py` and `src/routes/update_routes.py` (`update_bp`, mounted at `/update/*`).
- **Version check**: `GET /update/check` calls `GET <AI_SERVICE_URL>/api/version` (unauthenticated or with Bearer token) and returns `{current, latest, update_available, release_notes}`.
- **Apply update**: `POST /update/apply` streams SSE events `{pct, label}` while downloading the zip via `GET <AI_SERVICE_URL>/api/download` (requires `Authorization: Bearer <license_token>` plus an `X-Machine-Id` header — the server hardware-checks the token, see §2.17), extracts it in-place over `state.script_dir`, then restarts the process.
- **Preserved paths**: `data/`, `report/`, `json/`, `log/`, `activation.json`, `ai_settings.json`, `user_settings.json`, `.env` are **never overwritten** by an update zip — they contain user data and credentials.
- **Zip convention**: The update zip may have a single top-level directory prefix (GitHub archive convention). `update_service._shared_prefix()` detects and strips it automatically.
- **Updates install dependencies**: `download_and_apply()` only overwrites source files — it does **not** rebuild the venv. So after `_apply_tarball()` it runs `_install_requirements()` (`pip install -r requirements.txt` via `sys.executable`, idempotent) so an update that adds a new package doesn't relaunch into an `ImportError`. A pip failure raises, so the caller reports the update as failed instead of relaunching a broken app. The in-app update is otherwise **not** responsible for venv corruption — it never touches `venv/` (gitignored, absent from the tarball) and never deletes files; a broken venv comes from the *installer* rebuild racing a locked, still-running instance (see the venv-health rules below).
- **Process restart**: `restart_after_delay()` uses `os.execv` on Mac/Linux (atomic in-place image replacement). On Windows it spawns a **detached PowerShell relauncher** (`_restart_windows()` / `_build_windows_relaunch_script()`) that waits for the dev-server port to be released, starts a fresh hidden instance, and shows a dialog if the app never comes back up — and only then frees the port via `os._exit(0)`.
- **Windows restart anti-pattern**: Do **not** revert to spawning the new instance *before* `os._exit(0)` on Windows. The old code raced the dying process for port `5099`, failed to bind (`app.run` → `sys.exit(1)`), and — being launched `-WindowStyle Hidden` — died with no visible window, bricking the app until the stray process was killed. The relaunch must happen only after the old process has freed the port.
- **Windows relaunch argument quoting**: The app installs to `C:\Program Files\EasyOKAPI` (path contains a space). `Start-Process -ArgumentList` joins its elements with spaces and does **not** quote elements that contain spaces, so each child argument must be embedded in double quotes (`_ps_arg()` produces a PowerShell literal like `'"C:\Program Files\...\main.py"'`). Passing a bare path makes Python receive a split argv (`C:\Program`), fail to find the script, and — being hidden — die silently so the app never comes back. `-FilePath` and `-WorkingDirectory` are single-value params and use plain single-quoting (`_ps_quote()`); only `-ArgumentList` needs `_ps_arg()`. This mirrors `launcher.ps1` (`-ArgumentList "`"$app`""`).
- **Windows relaunch port probe**: `_build_windows_relaunch_script()` probes the port with a .NET `TcpClient` connect to `127.0.0.1:<port>` (`Test-Listening`), **not** `Get-NetTCPConnection`. That cmdlet lives in the NetTCPIP module which is absent on some Windows builds; the old code's fallback there (`Start-Sleep -Seconds 3`) re-introduced the port race. Do **not** probe with "can I bind a `TcpListener`?" — `SO_REUSEADDR` lets a bind succeed while the dying process still holds the port, so only "can I connect?" reliably means "still listening".
- **Hidden-launch crash logging**: `launcher.ps1` starts Python `-WindowStyle Hidden -RedirectStandardError "$ScriptDir\code\log\launch_stderr.txt"`. Without the redirect, a startup traceback (broken venv, missing wheel, AV quarantine, elevation issue) is lost and the app silently "never starts" with no clue. The launcher creates the `log/` dir before launch because `state.py` only makes it *after* Python has imported far enough to run. Keep the redirect on any change to the launch `Start-Process`.
- **Stop the running app before touching its venv**: A live EasyOKAPI instance keeps its venv `python.exe`/DLLs open, so an in-place reinstall can only *partially* delete the venv (`pyvenv.cfg` vanishes, `python.exe` is stuck) and `pip install` into it fails with `[WinError 5] Access is denied` — the install then ships broken. `startwindow-4-venv.bat` therefore stops any `python.exe`/`pythonw.exe` whose `ExecutablePath` starts with the install root (`%~dp0`) and sleeps ~2s before rebuilding. The same requirements install succeeds into a writable, *unlocked* path (e.g. TEMP), which is the tell that a lock — not a bad package — is the cause. **Anti-pattern**: do not `rmdir` or `pip install` over a venv that a running instance may still hold open.
- **Venv health is verified, not assumed**: A venv `python.exe` aborts immediately with `No pyvenv.cfg file` if `pyvenv.cfg` is missing, so the app's hidden process dies before `main.py` runs. Two guards exist and must stay: (1) `launcher.ps1` preflight (at `p -eq 61`) refuses to launch unless `code\venv\pyvenv.cfg`, the venv `python.exe`, **and** `code\venv\Lib\site-packages\flask` all exist — otherwise it shows "Python environment is incomplete or corrupted. Please reinstall." (2) `startwindow-4-venv.bat` rebuilds the venv when `pyvenv.cfg` is absent (not just when `python.exe` is — a half-built venv used to survive reinstall), checks the exit code of **every** `ensurepip`/`pip install` step (`if errorlevel 1 → exit /b 1`), and ends with `python -c "import flask, pandas, requests, scipy, groq"` so a partial install aborts the installer instead of shipping a broken app. **Anti-pattern**: do not gate venv rebuild on `python.exe` existence alone, and never run a `pip install` without checking `errorlevel`.
- **Port cleanup is OS-aware**: `browser_mgt.close_port()` dispatches to `lsof`+`kill` on Unix and `netstat -ano`+`taskkill` on Windows. Do not assume `lsof`/`kill` exist on Windows (they don't — the old single-path version silently no-op'd there).
- **UI**: A version badge (`#app-version-badge`) in the top-left header gets an amber pulsing dot when an update is found. Clicking it opens a SweetAlert2 modal with release notes and an "Update Now" button. A progress bar modal shows SSE download/apply progress.
- **Anti-pattern**: Do not call `restart_after_delay()` from any code path other than the update apply route — it hard-exits the server process.

---

### 2.16 Data-Archive Layout (Uninstall / Reinstall)

- The **installers** (`installer-win/setup.nsi`, `installer-mac/setup.sh` + `uninstall.command`, `installer-linux/install.sh` + `uninstall.sh`) preserve `data/`, `json/`, `report/` across an uninstall/update by copying them to a persistent backup (`EasyOKAPI_data` in Documents/home) and restoring on the next install. The in-app auto-update (`update_service.py`) does **not** archive — it preserves data in place — so this layout logic lives **only** in the installers, not in `update_service.py`.
- **`data/` is normalized to a purely subfolder-based tree in the archive.** On backup, loose files sitting directly in the data root are moved into a `data/root/` staging folder ("normalize"); on restore, `data/root/`'s contents are moved back up to the data root and the folder is removed ("restore"/dissolve). This keeps the archived `data/` tree uniform so it round-trips cleanly. `json/` and `report/` are **not** normalized (they are already subfolder-organized).
- The staging folder name (`root`) is the reserved folder name from §2.6 — the app forbids creating a real `data/root/` so the staging folder never collides with user data.
- **Implementation is inline in each installer (no shared Python helper)** — at Windows restore time no Python interpreter exists yet (the venv is built in a later step), so the logic must be installer-native. Windows uses a small PowerShell script written to `$PLUGINSDIR\archive.ps1` (the `WriteArchiveHelper` / `RunArchive` NSIS macros, mirroring the `stop-easyokapi.ps1` file-not-inline pattern); Mac/Linux use shell `_archive_stash_root` / `_archive_unstash_root` functions (`find -maxdepth 1 -type f`).
- **Anti-pattern**: Do not normalize the *live* install's `data/` directory — only the backup copy (on archive) and the restored copy (on restore), so a failed install never mutates the user's working data. Do not add normalization to `json/` or `report/`.

---

### 2.17 Hardware-Locked Activation

- A **permanent activation token is bound to one machine**, so copying `activation.json` (or the whole install folder) to another computer must not unlock the app. Three layers enforce this; do not weaken any in isolation:
  1. **Fingerprint** — `src/hwid.py` `get_hwid()` returns `SHA-256("easyokapi-hwid-v1|<os>|<raw-id>")` where `<raw-id>` is the Windows `MachineGuid` / macOS `IOPlatformUUID` / Linux `/etc/machine-id`. **The Windows installer's PowerShell (`installer-win/setup-frozen.nsi`) reproduces this recipe byte-for-byte** — if you change the salt (`_HWID_VERSION`), the `win` branch, or the canonical string, update that PowerShell or first-launch verification breaks. Read `MachineGuid` from the **64-bit** registry view on both sides.
  2. **Asymmetric signing** — permanent tokens are **RS256**. The server signs with `ACTIVATION_PRIVATE_KEY` (env, never committed); the client embeds only the public half (`src/activation_pubkey.py`). `activation.verify_token()` verifies the signature offline **and** checks the `hwid` claim equals `get_hwid()`. The client must never hold a secret that can mint tokens — keep the private key off the client.
  3. **Server enforcement** — `license_machines` (`(user_id, hwid)`, seat cap `MAX_MACHINES_PER_LICENSE`, default 1). `/api/activate` binds; `/api/download`, `/ai/proxy/chat`, `/api/version` re-check the presented `X-Machine-Id` / `hwid` against the token and seat. Transfer is `POST /api/account/machines/deactivate`.
- **Backward compatibility**: legacy HS256 tokens (no `hwid`) are grandfathered by `verify_token()` while `_ALLOW_LEGACY_HS256` is `True`. An HS256 token that *claims* an `hwid` is treated as tampering and rejected. Flip the flag to `False` once every install has re-activated.
- **Dependencies**: offline verification needs `PyJWT[crypto]` + `cryptography` (in `requirements.txt`, bundled via `easyokapi.spec` hidden imports). Dev/source builds are never gated (`needs_activation()` is False unless `sys.frozen`), and `verify_token()` falls back to claim-only checks when the libs are absent so developers are never blocked.
- **Anti-pattern**: do not check the `hwid` claim without also verifying the RS256 signature (a hand-written token could then fake any `hwid`); do not embed the private key in the client; do not let the two hwid recipes (Python vs PowerShell) drift.

---

### 2.18 Windows Elevation & Running-Instance Guard (Frozen Build)

- **`EasyOKAPI.exe` must NOT force elevation.** Do **not** set `uac_admin=True` in `easyokapi.spec`. An unsigned PyInstaller EXE that embeds a `requireAdministrator` manifest matches Windows Defender's ML heuristic for droppers and gets flagged as **`Trojan.Win32C!ml`** (a false positive that blocks the install). The app runs at the user's normal (medium) integrity. The §1 "no admin" rule stands for the frozen build too. *(If per-machine elevation is ever truly needed, it has to come together with Authenticode code-signing — see below — not a bare manifest on an unsigned binary.)*
- **Installer/uninstaller still elevate** via NSIS `RequestExecutionLevel admin` (they need to write the hosts file, Program Files, etc.). That is unrelated to the app's own integrity level.
- **Code-signing / AV note**: the EXE and NSIS installer are currently **unsigned**, so `!ml` false positives can recur intermittently regardless of the manifest. The durable fix is Authenticode signing (an EV cert gives near-instant Defender/SmartScreen reputation) plus a false-positive submission to Microsoft. Until then, avoid changes that raise the heuristic score (no `requireAdministrator` manifest, no UPX — `upx=False` already, keep onedir).
- **In-app update swap elevates on-demand, NOT via a manifest.** The frozen install lives under `%PROGRAMFILES%` (admin-only) but the app runs non-elevated, so the binary-swap updater (`update_service._spawn_windows_swapper`) cannot replace the install dir itself. It writes two scripts and spawns a **non-elevated coordinator** (`_build_windows_coordinator_script`) that: waits for the app's port to free → launches an **elevated helper** (`_build_windows_swap_script`, run via `Start-Process -Verb RunAs` = one UAC prompt) that does ONLY the `Move-Item` swap + `icacls /reset` and writes an `OK`/`FAIL:` result file → then, back in the non-elevated coordinator, relaunches the app and clears the pending-swap marker. All steps log to `<script_dir>\log\update_swap.txt`.
  - **Anti-pattern — relaunching from the elevated context**: the app must be relaunched by the **non-elevated** coordinator, never by the elevated helper. A child of the elevated process inherits admin integrity, so it would write the user data dir (`Documents\EasyOKAPI`) as admin and break later non-elevated writes.
  - **Anti-pattern — clearing the pending marker before the swap is confirmed**: `apply_pending_swap_and_exit()` must NOT clear `_pending_update.txt` on Windows; only the coordinator clears it *after* the elevated helper reports `OK`. Clearing it unconditionally orphans the staged bundle when the swap fails / UAC is declined — the silent "update runs to 100% but reopens on the old version" bug.
  - **Anti-pattern — spawning the coordinator via bare `'powershell'`**: a frozen PyInstaller process can run with a **stripped/sanitised `PATH`** that omits System32, so `subprocess.Popen(['powershell', ...])` raises `FileNotFoundError` and the swap coordinator never launches (the scripts get written, but no swap and no `update_swap.txt`). Always resolve the absolute interpreter via `update_service._powershell_exe()` (`%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`, falling back to bare `powershell` only if absent) for every Python-side `Popen` of PowerShell — both `_spawn_windows_swapper` and `_restart_windows`. (Inside an already-running PS script, bare `powershell` is fine.)
  - **Anti-pattern — swallowing the swap-handoff exception**: `update_routes._delayed_shutdown()` must NOT discard a failure from `apply_pending_swap_and_exit()` with a bare `except: pass`. A spawn/handoff failure used to vanish (app fell through to a normal shutdown, reopened on the old version, no trace). Record it via `_log_swap_failure()` to `update_swap.txt` before falling through to the SIGTERM shutdown.
  - **Anti-pattern — `DETACHED_PROCESS` when spawning the coordinator/relauncher** (the real root cause of the "update never applies" bug): `powershell.exe` is a console application. `CreateProcess` with `DETACHED_PROCESS` (`0x8`) gives the child **no console**, so the PowerShell host fails to initialise and the process **exits before running a single line** — `Popen` still returns a valid PID, so nothing raises and nothing logs; the scripts are written but no swap and no `update_swap.txt` ever appear. Spawn the detached coordinator with **`CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`** only (NO `DETACHED_PROCESS`). `CREATE_NO_WINDOW` runs it hidden *with* a console, and the child still outlives the exiting app. Same rule for `_restart_windows`. Empirically: any flag set containing `DETACHED_PROCESS` → child never runs; `CREATE_NO_WINDOW` / `CREATE_NEW_CONSOLE` / no-flags → child runs. (Unix uses `start_new_session=True`, which has no console concept and is fine.)
  - **Anti-pattern — running the coordinator with the install dir as its cwd**: the `Popen` in `_spawn_windows_swapper` MUST pass `cwd=state.script_dir` (the data dir). The coordinator inherits the app's cwd — the install dir (`$live`, set by the launcher's `-WorkingDirectory`) — and stays alive (waiting on the elevated swap) during the move. Windows cannot rename a directory that is a running process's current directory, so the elevated `Move-Item $live $old` fails and the new build ends up **nested inside the old install** (`EasyOKAPI\EasyOKAPI`). Never let any still-running helper hold `$live` as its cwd.
  - **Anti-pattern — the elevated swap script without `$ErrorActionPreference = 'Stop'`**: PowerShell cmdlet errors (`Move-Item`, `Remove-Item`, …) are **non-terminating** by default, so a `try/catch` does NOT catch them. Without `Stop`, a failed "move `$live` aside" falls straight through to "move `$new` in" — and since `$live` still exists, `Move-Item` **nests** the new build inside it and the script still writes `OK` (a false success that also clears the marker). The swap helper must set `$ErrorActionPreference = 'Stop'` so a failed move is terminating → caught → rolled back → reported `FAIL` → marker kept for retry. Keep only the two directory moves fatal; wrap the Uninstall-copy / `.old` cleanup / `icacls` as best-effort so they can't turn an applied swap into a false failure (or trigger a rollback over the new install). Guard with `if (Test-Path $live) { throw }` before the second move so nesting can never happen.
  - This transient `RunAs` is allowed; it does **not** violate the "no `requireAdministrator` on `EasyOKAPI.exe`" rule above — the EXE itself still ships with no elevation manifest.
- **The installer and uninstaller refuse to touch a running instance.** Both the install-side overwrite guard and the `Section "Uninstall"` in `setup-frozen.nsi` write a `detect-easyokapi.ps1` (exit 1 = running, 0 = clear) with **two independent fail-safe signals**: (1) any `EasyOKAPI.exe` from `Get-CimInstance Win32_Process` whose `ExecutablePath` starts with the install dir — or whose path is unreadable — counts as running; (2) a **file-lock test** (`[System.IO.File]::Open($exe,'Open','ReadWrite','None')` throws ⇒ exe is in use). The lock test is the definitive, integrity-independent "can I delete these files" check. Keep both detectors identical.
  - **Anti-pattern — trailing backslash in the passed path**: do **not** pass the install dir as a quoted argument ending in a backslash (`... detect-easyokapi.ps1" "$INSTDIR\"`). On the Windows command line `\"` is an escaped quote, so `"C:\…\EasyOKAPI\"` is mangled, `$args[0]` no longer matches `ExecutablePath`, the `StartsWith` fails, and the check silently reports "not running" → destructive `RMDir` against a locked folder. **Bake `$INSTDIR` into the script** via `FileWrite $9 "$$r = '$INSTDIR'$\r$\n"` (single-quoted; backslashes/spaces are literal in a PS single-quoted string) and invoke the script with **no path argument**.
  - **Anti-pattern**: do not gate the process match on `-and $_.ExecutablePath` (drops processes whose path is unreadable → false "not running").
- **The uninstall is cancellable.** `Section "Uninstall"` opens with a `MB_YESNO` confirmation (No → `Quit`, nothing removed), and the running-instance prompt's Cancel also `Quit`s. Keep an explicit, non-destructive bail-out path before any deletion.

---

### 2.19 User-Selectable Data Root

- The writable data root (`state.script_dir`) holds every user artifact (`data/`, `json/`,
  `report/`, `log/`, plus `user_settings.json`, `activation.json`, `ai_settings.json`, `.env`,
  markers). In a **frozen build** the user may relocate it from **App Settings** onto another drive
  or a shared folder. The default stays `<Documents>/EasyOKAPI` (win/mac) / `~/EasyOKAPI` (linux).
  **Source/dev runs always use the project root and ignore all of this.**
- **The Windows installer lets the user choose the data location.** `setup-frozen.nsi` adds a custom
  themed **Data Folder** page (`DataFolderPage`/`DataFolderPageLeave`) after the Directory page, so
  `$INSTDIR` is known for validation. The user picks a *parent* folder (`$DataParent`, default
  `$DOCUMENTS`); the data root is `$DataParent\EasyOKAPI`. When the choice is non-default the Install
  section writes the `$DOCUMENTS\.easyokapi_dataroot` pointer the app reads on launch; when it's the
  default it deletes any stale pointer. The page **rejects** `$INSTDIR` / anything under Program Files
  (mirrors the in-app safeguard). Relocation afterwards is an in-app action.
- **The Windows uninstaller is pointer-aware.** `setup-frozen.nsi`'s `Section "Uninstall"` reads
  `$DOCUMENTS\.easyokapi_dataroot` and acts on the **relocated** folder when it exists (prompt, backup
  ZIP, removal); on removal it also wipes the default folder + both `_data` siblings + the pointer
  file, so a leftover copy from an in-app relocation never lingers. Because the pointer is a sibling
  it still works when the default folder is gone. (The mac/linux uninstall scripts are source-build
  only and do not touch the frozen data folder.)
- **Relocation MOVES, except away from the default (which copies).** `data_root.set_data_root(parent_dir)`
  copies the *whole* current root into an **`EasyOKAPI` subfolder of the chosen folder**
  (`<parent>/EasyOKAPI`) and points the app there. The copy skips the `.dataroot` pointer and transient
  `_update*` artifacts (`_copy_ignore`). After the copy + pointer write, the **original is deleted (a
  move)** — *unless* it is `state.default_data_root`, which is kept as a fallback (a "copy"). So
  relocating an already-relocated folder, or `reset_to_default()` (custom → default), removes the old
  custom folder; relocating away from the default keeps it. `_relocate(target)` returns
  `(path, moved)`; `POST /data_root` surfaces `moved` so the UI says "moved" vs "copied". Both callers
  go through `_relocate` → `_validate_target` (absolute; not a file; not inside `bundle_dir` — i.e. the
  EasyOKAPI program folder; not equal to / inside the current root; parent writable). The pointer is
  written **before** the source is removed, so an interrupted move never aims the pointer at a deleted
  folder.
- **The location lives in a `.easyokapi_dataroot` pointer file, NOT in `user_settings.json`.**
  `user_settings.json` lives *inside* the data root, so it cannot record where the data root is
  (chicken-and-egg). The pointer is a one-line file holding the absolute path, kept **beside** the
  default folder — i.e. in its parent (`<Documents>`/`<home>`, deterministic per OS), **not inside
  it**. Keeping it outside means the pointer (and the link to the relocated data) **survives the user
  deleting the now-empty default folder**, so both the app and the uninstaller can still find the real
  data. On Windows the parent is exactly NSIS's `$DOCUMENTS`, so the uninstaller reads the same file.
  `state._read_dataroot_override()` reads it at import; `data_root._write_pointer()` writes/clears it;
  `state._dataroot_pointer_path()` is the single source of truth for its location.
- **The move is deferred-commit, in two steps.** Resolution is import-time, so changing the root
  **requires an app restart** — and nothing is moved until the user accepts that restart. **Step 1**
  `POST /data_root` is a **dry run**: `data_root.preview_data_root(parent)` / `preview_reset()` validate
  the choice and return `{path, moved, restart_required: true}` **without touching the filesystem**. The
  UI confirms, offering **Restart now** / **Cancel**. **Step 2 — Restart now** re-sends the same body to
  `POST /data_root/restart`, which is where the copy/move actually happens (`set_data_root` /
  `reset_to_default`), then relaunches the app in place via `update_service.restart_after_delay()`
  (mac/linux `os.execv`; Windows detached relauncher) and serves `restarting.html` — a page that polls
  `/ping` and reloads the tab once the fresh instance rebinds the same port, so the new data location
  takes effect with no manual relaunch. **Cancel** is a true no-op: since nothing was committed, the
  data stays exactly where it was (no revert needed).
- **The folder is picked with an in-app browser, not a typed path.** `GET /browse_dirs?path=` lists a
  directory's non-hidden subfolders (and Windows drives via `?path=::drives`) for the SweetAlert
  navigator (`pickDataRootFolder` in `init.js`); the server then appends `EasyOKAPI`.
- `GET /data_root` returns `{current, default, is_custom}`, injected into `index.html` as
  `DATA_ROOT_INFO` (with `IS_FROZEN`); the settings modal hides the section for source builds.
  `POST /data_root` (`{path}` to relocate, or `{reset:true}`) is frozen-only, `@423 LOCKED` while the
  data-collection process runs; it **previews only** and returns `{path, moved, restart_required}`.
  `POST /data_root/restart` (same `{path}`/`{reset:true}` body + `mode`) commits the move and relaunches,
  serving `restarting.html` on success (or a JSON error on a commit failure); it carries the same
  frozen + `@423 LOCKED` guards.
- **Anti-patterns**: do **not** store the data-root path in `user_settings.json`; do **not** point
  the data root inside `bundle_dir` / the EasyOKAPI program folder (read-only, elevated — rejected
  both in `_validate_target` and on the installer's Data Folder page); do **not** delete the **default**
  folder on relocation (only a *non-default* source is removed — the default is the fallback); do
  **not** write the pointer *after* removing the source (write it first); do **not** move data in
  `POST /data_root` — it is a **dry run** (preview only) so a cancel needs no revert; the actual move
  and the relaunch are confined to `POST /data_root/restart`.

### 2.20 Default Display on Restart

- A **restart** (`POST /data_root/restart` relocation, or `POST /update/finalize` after an applied
  update) must bring the app back up in the **default display** — kinetics mode with fresh per-view UI
  state — not the previous tab's saved `localStorage` layout. The restart reloads the same browser
  origin (same tab for the data-root in-place relaunch, a new tab for the manual post-update relaunch),
  so client-only `localStorage` survives the process restart by itself; resetting requires a signal that
  also survives it.
- **Mechanism**: the restart routes call `state.mark_reset_display_pending()` *before* triggering the
  relaunch. This writes a one-shot sentinel (`state._RESET_DISPLAY_MARKER`) in **`default_data_root`** —
  the stable folder where the `.dataroot` pointer lives, **not** `script_dir` — because a relocation
  restart changes `script_dir`, and the new process must still find the flag. The next `index` render
  calls `state.consume_reset_display_pending()` (reads **and deletes** the sentinel) and passes
  `reset_display` to the template. `index.html` exposes it as `const RESET_DISPLAY`; when true it drops
  per-view `localStorage` keys (keeping genuine cross-session prefs: `theme`, `okapi_ai_lang`,
  `okapi_ai_first_run`) **before** `init.js` runs, and `init.js` forces the kinetics mode button
  regardless of `USER_SETTINGS.default_mode`.
- **One-shot vs. the auto-opened tab (race)**: because the sentinel is consumed on the **first** index
  render, only **one** tab may load `/` during a restart. The in-place relaunch (`update_service.restart_after_delay`
  → `os.execv` / `_restart_windows`) re-runs `main.py`, which would normally auto-open a **second**
  browser tab. That tab would race the user's existing tab (reloading itself from `restarting.html`) for
  the marker; whichever lost would come up with `reset_display=false` — leaving the `#measurement-mode`
  button on the saved `default_mode` instead of kinetics. The relaunch therefore passes `--no-browser`
  (`update_service._relaunch_argv()`) so the fresh instance does **not** open a tab — the user's reloading
  tab is the sole marker consumer.
- **`AppState.reset()` mirrors the button**: `AppState.reset()` in `index.js` sets `currentMeasurementMode`
  from the selected `#measurement-mode` button's `data-value` (fallback `"kinetics"`), **not** a hard-coded
  `"kinetics"`. init.js sets that button before `reset()` runs (on `$(document).ready` and on server-down
  recovery), so the internal mode and the button highlight can never desync. Do **not** reintroduce a
  hard-coded mode in `reset()` — it silently diverges from the button whenever `default_mode` ≠ kinetics.
- **`switchingModes` runs on load**: `$(document).ready` calls `switchingModes(_initialMode, { silent: true })`
  **after** `initDefaultState()` so the selected mode's **section layout** (and, for report mode, the report
  directory) is realized on load — previously that ran only on a button click, so a non-kinetics `default_mode`
  came up with the kinetics layout. It must run after `initDefaultState()` (which hides sections point/calibrate
  need shown), and the `default_subfolder` auto-select is skipped in report mode (it would override the report
  directory). The `{ silent: true }` flag suppresses the `mode/switch` analytics event — this is the default
  layout, not a user-initiated switch; pass it for any non-interactive `switchingModes` call.
- **Anti-patterns**: do **not** put the sentinel in `script_dir` (lost across a relocation restart); do
  **not** make the reset a client-only flag (`sessionStorage`/query param) — it will not survive the
  manual post-update relaunch into a fresh tab; the flag is **one-shot** (consumed on first render) so a
  plain refresh keeps the user's layout — do not leave it set; do **not** clear `theme` (it would lose
  the user's chosen mode on every restart — it is preserved and re-derived from `USER_SETTINGS.theme`); do
  **not** let an in-place relaunch auto-open a browser tab (it races the user's tab for the one-shot
  marker — pass `--no-browser`).

### 2.21 Folder/file tables: Modified Date + Sortable Columns

- **All three folder/file tables** show a **Modified** column (last-modified date) and support
  click-to-sort on the **name** and **Modified** column headers: the CSV **File Selection** table
  (`#file-table`), the **calibration-JSON** table (`#json-table`), and the **report-subject folder**
  table (`#file-table` in report mode). Sort order is one of `name_asc` / `name_desc` / `date_asc` /
  `date_desc`; the **single shared** default is the `file_sort_order` user setting (default
  `date_desc`), persisted via `POST /settings` (helper `_applySortOrder()` in `navigation.js`) and
  re-applied on load. Sorting one table changes the shared order for all of them.
- **Date metadata is server-supplied.** `src/file.py` exposes `build_meta(directory, names, …)`
  (stats arbitrary names — used for report subject **directories**) and `get_file_meta(directory,
  fileType, …)` (globs files, delegates to `build_meta`). Each returns a `{name: {mtime, display}}`
  map. Routes that feed a table must also return its meta: index → `file_meta` + `cal_json_meta`
  (embedded as `FILE_META` / `CAL_JSON_META` consts); `/browse` → `files_meta`; `/get_json_cal` →
  `files_meta`; `/get_report_subjects` → `subjects_meta`. `mtime` (epoch) drives client-side date
  sorting; `display` is the cell text. JS keeps per-table maps on `AppState`
  (`fileMeta`/`jsonMeta`/`reportMeta`) refreshed from those responses.
- **The `display` time tag is formatted server-side** from the `time_tag_format` user setting
  (App Settings → General; `iso`/`iso_sec`/`us`/`eu`/`date_only`, default `iso`) via
  `TIME_TAG_FORMATS` in `file.py`. **Every** route that builds meta must pass the setting
  (`time_format=…`) so a format change re-renders live. Do not format the tag client-side — it would
  diverge from the first server paint, and `mtime` (not `display`) remains the sort key so changing
  the format never reorders rows.
- **Dual render — keep them in lockstep.** Each table is rendered **twice**: server-side Jinja in
  `index.html` (first paint, File Selection + calibration-JSON) and client-side render helpers in
  `navigation.js` (`renderFileRows` / `renderJsonRows` / `renderReportRows`, every refresh / re-sort).
  Both must produce the **same** column layout (name, Modified, then 3 action columns → empty/`+more`
  rows use `colspan="5"`) and the same clickable header markup (`sort{File,Json,Report}Table('name'|'date')`
  with the `.sort-arrow` indicator). The report-subject table is JS-only (report mode can never be the
  initial server render) so it has no Jinja half.
- **`filterFiles` still operates on plain name strings** — do not change `files`/`response.files` to
  carry dicts (it also feeds `deleteDataFolder`'s confirmation list). Sorting reads dates from the
  per-table `AppState.*Meta` maps, keyed by name, instead.
- **`updateJSONTable(undefined)` self-refetches.** Called with no argument (post-copy/edit refreshes)
  it re-fetches `/get_json_cal` for the current mode to get fresh files **and** meta; called with a
  list it renders directly. Do not pass a bare list expecting it to also refresh dates.
- **Anti-pattern**: do not sort or compute dates only on the client from `localStorage`/guesswork;
  do not give each table its own sort setting (the preference is intentionally shared via
  `file_sort_order`).

### 2.22 UI Localization (i18n)

- The whole UI is translatable into the **same 6 languages as the AI chat** (`en`, `vi`,
  `zh`, `fr`, `ja`, `ru`). The active language is the **`ui_language`** user setting
  (App Settings → General; default `en`), independent of the AI chat's own language.
- **Catalogs**: flat **key → string** JSON files in `ui_translations/<lang>.json`, shipped
  beside the app and resolved from **`state.bundle_dir`** (the read-only program folder — **not**
  `state.script_dir`, the writable data root), mirroring `ai_assistant.py`'s
  `guide_translations/`. `en.json` is the **baseline source of truth**; a non-English file is
  overlaid onto English, so any **missing key falls back to English**. Loading is best-effort and
  cached (`src/i18n.py` `load_catalog(lang)` / `normalize_lang(lang)`); a missing/broken file never
  raises into a request.
- **Server injection**: `core_routes.index()` computes `ui_lang` + `ui_strings` from the setting and
  injects them into `index.html` as `const UI_LANG` / `const UI_STRINGS`. `<html lang="{{ ui_lang }}">`.
- **Client applier** (`static/script/i18n.js`, loaded right after `short-hands.js`, before all other
  app scripts): exposes `window.t(key, fallback)` for dynamic strings and `window.applyTranslations(root)`
  which translates tagged elements on `DOMContentLoaded`. Attribute contract on elements:
  `data-i18n` → `textContent`, `data-i18n-html` → `innerHTML`, `data-i18n-hint` → `data-hint`,
  `data-i18n-ph` → `placeholder`, `data-i18n-aria` → `aria-label`. **The English text stays in place
  in the HTML as the fallback** — a missing catalog or source build still reads correctly.
- **Dynamic strings** (`Swal.fire(...)`, JS-built tables) use `t('key', 'English literal')`. The
  literal is the fallback, so an un-migrated dialog keeps working in English; migrate incrementally.
  `navigation.js` table re-renders (`renderFileRows`/`renderJsonRows`/`renderReportRows` + the header
  builders) must use `t()` so the JS re-render and the Jinja first paint stay in lockstep (Rule §2.21);
  `t` is global and loaded before `navigation.js`.
- **Changing the language reloads the page** (`init.js` settings save): the server re-renders with the
  matching catalog, so every static label and dynamic dialog comes up consistently translated — there
  is never a half-translated state and no live two-language switching.
- **Keep technical terms in English** in every catalog: mode names (`kinetics`/`point`/`calibrate`/`report`),
  units (`seconds`/`minutes`/`nM`/`ng/µL`), `Absorbance`, `maxRate`, `rSquared`, `Slope`, `Sat`, `Blank`,
  `ConcenUnit`, `CSV`/`JSON`/`Excel`, and brand names (`Easy OKAPI`/`EasyOKAPI`/`CBBiotec`/`CBB`/`PyBadge`).
- **Anti-patterns**: do **not** resolve the catalog dir from `state.script_dir` (it's the writable data
  root, not where the shipped catalogs live — use `state.bundle_dir`); do **not** add a UI string without
  giving it a key in **`en.json` and all five** `vi/zh/fr/ja/ru` files (keep them in lockstep — covered by
  `tests/test_i18n.py`, which fails on key drift); do **not** strip the in-place English text when adding a
  `data-i18n*` attribute (it is the fallback); do **not** translate the technical terms above.

### 2.23 Excel Export — Native Calibration Charts

- **Calibration fit charts must export as native, editable Excel charts, not baked-in PNGs.** A PNG
  freezes the axis text into pixels, so the user can't rename axes when they edit the workbook. The
  `/export_report_excel` route (`file_routes.py`) renders calibration "standards points + fit curve"
  charts as openpyxl `ScatterChart`s (`_add_native_scatter_chart`): two series — standards as
  markers (`Marker` + `graphicalProperties.line.noFill`), fit as a smooth line (`smooth=True`,
  `Marker('none')`) — with `chart.title` / `x_axis.title` / `y_axis.title` as live Excel objects.
  **You must set `x_axis.delete = False` and `y_axis.delete = False`** or openpyxl hides the axis
  titles entirely.
- **Data contract**: the client (`report.js`) sends each calibration chart as a `chart_series` entry
  (`{ label, title, algo, xLabel, yLabel, points:[{x,y}], fit:[{x,y}] }`) built by
  `buildScatterSeries()`, not as a `chart_images` base64 PNG. The backend prefers `chart_series` and
  falls back to embedding `chart_images` only when `chart_series` is absent (back-compat + non-calibration
  time-series snapshots). Keep both client export paths in lockstep — the per-view `generateReportExcelFromCurrent`
  **and** the multi-file report-console `finalizeReportExcel`.
- **Axis-label boxes**: both export dialogs expose editable, auto-filled X/Y label boxes (the
  `generateReport` SweetAlert `#swal-xlabel`/`#swal-ylabel`, and the console `#console-xlabel`/`#console-ylabel`).
  **X defaults to the concentration-unit-aware `Concentration (<unit>)`** (`_concenAxisLabel()` →
  `getMetaConcenUnit()`, the post-§2.10 `# ConcenUnit` schema — ng/µL, nM, %), matching the live chart
  (`generate-chart.js`) and the report's derived-concentration lines. `_concenAxisLabel()` is the **single
  source** for every calibration chart's X-axis — the native Excel `chart_series`, the PDF/PNG path
  (`renderCalibrationChartImage` via its `xLabel` arg, and the inline kinetics-cal canvases) — so do not
  reintroduce a bare-`Concentration` axis in any of them. The single-file `generateReport`
  dialog **pre-fills** the exact unit from `AppState.metaData`; the multi-file console box is left **blank =
  "auto" per file** (each chart uses its own file's `config.metadata` unit), because different files in one
  report can carry different units. **Y left blank means "auto" — each chart uses its own metric/measurement
  label** (`niceMetric` / `measLabel`). A non-blank box overrides every chart in that export. **Anti-pattern**:
  do not hardcode the X label to bare `Concentration` (it drops the unit — the obsolete pre-ConcenUnit
  assumption); do not force a single file's unit onto the multi-file console export.
- **Helper columns must stay visible.** Each native chart's X/Y values are written to off-to-the-right
  columns (col AA onward via the per-sheet `_chart_helper_col` cursor). Do **not** hide these columns or
  move the data to a hidden sheet — Excel does not plot data in hidden cells, which would blank the chart.
- **It is a category-axis `LineChart`, both series markers-only, on the FULL merged grid.** The standards+fit rows
  are merged and **sorted** by concentration (~157 rows); helper cols `conc` (AA), `std_y` (AB), `fit_y` (AC). Both
  series are **markers only** (no lines). Why this shape: the 150 *uniform* fit rows fill the category axis so a
  standard's row index ≈ its value position (proportional-looking, like the old shared-X scatter), **and** the
  X-axis labels come from the `conc` column which we write **only on the standard rows** — so the axis shows the
  measured **concentration-table values** and never the fit's generated Xs. (A value-axis scatter cannot do this:
  Sheets either drops a series or auto-picks round ticks like 50/200 — not the table values.) **Anti-pattern**: do
  not label the fit rows in `conc`; do not put all 150 fit Xs on the axis. Covered by `tests/test_report_excel.py`.
- **Labels = the standard concentrations.** `conc` carries each standard's concentration on its own row, blank
  elsewhere; both series share it as the `cat` reference. (`_nice_axis_ticks` is retained as a utility but the axis
  is **not** clamped — the labels are the actual table values, not a nice-number series, and Sheets ignores
  `majorUnit`/`number_format=';;;'` on this chart anyway.) Google Sheets may still thin a dense set of labels, but
  they are always concentration-table values. **Anti-pattern**: do not blank the labels or relabel with round ticks.
- **Series carry explicit numeric caches.** Series are built from the raw `XYSeries` class with
  `val = NumDataSource(numRef=NumRef(f=…, numCache=NumData(...)))` and `cat = AxDataSource(numRef=NumRef(…))` —
  each reference embeds a `<numCache>` of its values. openpyxl's `Series` factory writes *bare* refs with no cache:
  Excel recomputes them on open, but **Google Sheets does not** — a cache-less ref is read as text/empty and the
  series is dropped. **Anti-pattern**: do not fall back to the `Series(values, …)` factory.
- **Fit resolution.** `buildCalibrationRegressionLine` (and the inline regline loops in `report.js`) sample the
  curve at **150 points** so it reads as a smooth line in Excel and a smooth dotted trace in Google Sheets
  (which draws the fit as markers). All five generators share the `/ 149` + `j < 150` pattern — keep them in step.
- **Helper values must be written as numbers, not text.** The standards `points` arrive from the client as
  *strings* (parsed out of the CSV); `_add_native_scatter_chart` coerces every `x`/`std_y`/`fit_y`
  to `float` (`_num()`, skipping non-numeric like `'NONE'`) before writing. A string cell makes Excel (a)
  refuse to plot it on the scatter — the green "number stored as text" marker — and (b) ignore the user's
  locale decimal separator. Write the bare `float` with **no explicit `number_format`** so the cell stays
  General and Excel renders the decimals per the user's own regional settings. **Anti-pattern**: do not write
  `p.get('x')` verbatim, and do not pin a decimal format on the helper cells. Covered by `tests/test_report_excel.py`.
- **Standards = blue diamonds, fit = red X-marks — markers only, and the fit must not be a native trendline.**
  The standards are blue **diamonds** (`Marker('diamond', size=8)`), the fit the 150-point sampling as red
  **X-marks** (`Marker('x', size=4)`); **neither series has a line** (`LineProperties.noFill = True`). Markers only
  on this category LineChart: the standards are sparse and never on adjacent rows (so nothing joins them), and the
  dense X-marks trace the curve, clearly distinct from the diamonds. Do
  **not** use an OOXML `Trendline` either: the chart plots **metric-vs-concentration** while the app fits
  **concentration-vs-metric** and *inverts* it (`buildCalibrationRegressionLine` — so a `logarithmic` fit draws
  an exponential curve, `exponential` a logarithmic one, `polynomial` a √-shape), meaning a native trendline
  would recompute the *wrong* functional family with its *own* coefficients, and **Michaelis-Menten has no
  native trendline type at all**. Markers show the app's true fitted curve everywhere with no per-algo casing.

---

## 3. Autonomous Documentation Updates

- **Self-Reflection Request**: Upon completing any significant task, feature implementation, or architectural change before returning control to the user, you **MUST** evaluate if updates are required for `Rule.md` or `easyokapi-knowledge/EASY OKAPI.md`.
- **Functional updates**: If your changes introduce new files, routes, dependencies, or alter the architectural flow, you MUST proactively edit `easyokapi-knowledge/EASY OKAPI.md`.
- **Behavioral updates**: If your task establishes new strict coding patterns, behavioral constraints, or anti-patterns, you MUST proactively edit `Rule.md`.
