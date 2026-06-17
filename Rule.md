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
- Route `POST /browse` is **stateless**: validates path is within `data_root_path` or `report_root_path`, returns files, and never writes to backend state. Removed routes: `/get_parents`, `/get_children`.
- Template variables passed from `index()`: `data_root`, `report_root`, `json_root` (replaces `directory`).
- JS constants: `DATA_ROOT`, `REPORT_ROOT`, `JSON_ROOT` (replaces `rootPath`). Defined inline in `index.html` before external scripts are loaded.
- Path delimiter: `\\` on Windows, `/` on Mac/Linux.
- Hidden directories (starting with `.` or `_`) are filtered out.
- **Anti-pattern**: Do **not** restore `get_directory()`, `browse_directory()`, `get_parent_directory()`, or `current_directory` global in `file_path.py` — these have been permanently removed.
- `/run_script` payload uses `subfolder` (folder name only, no slashes) instead of `base_dir`; backend constructs `data/<subfolder>` and creates it if needed.
- Route `POST /move_file` (`filename`, `path`, `dest_path`; form-encoded) moves a CSV data file between data subfolders. Both `path` and `dest_path` must validate inside `data_root`; `filename` must be a bare name (no `/`, `\`, `..`); same-folder moves are rejected; a name clash in the destination is auto-incremented via `get_next_filename` so a move **never** clobbers an existing file. Blocked (`423 LOCKED`) while the HID process runs. Frontend: `moveFile()` in `data-handling.js` (Move button `#move-file-btn`, enabled/disabled alongside `#copy-file-btn`) shows a SweetAlert2 folder-select dialog (data root + subfolders, excluding the current folder). CSV-only: it bails in `report` mode.

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
- Settings are stored in `ai_settings.json` at the project root via `src/ai_settings.py`.
- All chat calls go through `src/ai_assistant.py` using the `requests` library.
- The AI blueprint is `ai_bp` in `src/routes/ai_routes.py`, mounted at `/ai/*`.
- Supported languages: `en`, `vi`, `zh`, `fr`, `ja`, `ru`. System prompts for all 6 are embedded in `ai_assistant.py`.
- `ai_settings.json` stores `preferred_languages` as a **JSON array** (e.g. `["en","vi"]`). Old single-string `preferred_language` keys are migrated to an array transparently by `ai_settings.load()` and `ai_settings.save()`. Never write the singular key in new code.
- `AI.activeLang` in `ai-chat.js` tracks the currently active language and cycles through `preferred_languages` via the header button. Chat requests send `AI.activeLang`, not the full preference list.
- MCP tools (`TOOLS` list in `ai_assistant.py`) give the LLM access to live app state: file list, CSV content, calibration JSON, hardware status, and built-in help docs.
- Conversation history is **client-side only** (stored in `ai-chat.js` `AI.messages` array) — the backend is stateless, consistent with the single-user no-session rule.
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
- **The installers do NOT choose the data location.** They always lay the data root at the default
  (the app creates it on first run). The Windows installer's finish-page "Open my EasyOKAPI data
  folder" option was removed (the folder may not exist yet at end of install). Relocation is an
  in-app action only.
- **Relocation COPIES, it does not move.** `data_root.set_data_root(parent_dir)` copies the *whole*
  current root into an **`EasyOKAPI` subfolder of the chosen folder** (`<parent>/EasyOKAPI`), points
  the app there, and **leaves the original in place** as a fallback. The copy skips the `.dataroot`
  pointer and transient `_update*` artifacts (`_copy_ignore`). `reset_to_default()` copies back to
  `state.default_data_root` and clears the pointer. Both go through `_relocate(target)` →
  `_validate_target` (absolute; not a file; not inside `bundle_dir`; not equal to / inside the
  current root; parent writable).
- **The location lives in a `.dataroot` pointer file, NOT in `user_settings.json`.**
  `user_settings.json` lives *inside* the data root, so it cannot record where the data root is
  (chicken-and-egg). The pointer is a one-line file holding the absolute path, kept at the
  **default** location (`state.default_data_root`, deterministic per OS). `state._read_dataroot_override()`
  reads it at import; `data_root._write_pointer()` writes/clears it. The default folder is always
  created (to hold the pointer) even when the live data is elsewhere.
- **Resolution is import-time**, so changing the root **requires an app restart**. `POST /data_root`
  returns `restart_required: true`; the UI then offers **Quit now** (via the existing `POST /shutdown`).
- **The folder is picked with an in-app browser, not a typed path.** `GET /browse_dirs?path=` lists a
  directory's non-hidden subfolders (and Windows drives via `?path=::drives`) for the SweetAlert
  navigator (`pickDataRootFolder` in `init.js`); the server then appends `EasyOKAPI`.
- `GET /data_root` returns `{current, default, is_custom}`, injected into `index.html` as
  `DATA_ROOT_INFO` (with `IS_FROZEN`); the settings modal hides the section for source builds.
  `POST /data_root` (`{path}` to relocate, or `{reset:true}`) is frozen-only, `@423 LOCKED` while the
  data-collection process runs.
- **Anti-patterns**: do **not** store the data-root path in `user_settings.json`; do **not** point
  the data root inside `bundle_dir` (read-only assets); do **not** *move/delete* the original on
  relocation (it is a copy — keep the source); do **not** auto-restart (`os.execv`) from the settings
  route — restart-on-exit is reserved for the update path (§2.15); do **not** add a data-location
  chooser back to the installers.

---

## 3. Autonomous Documentation Updates

- **Self-Reflection Request**: Upon completing any significant task, feature implementation, or architectural change before returning control to the user, you **MUST** evaluate if updates are required for `Rule.md` or `easyokapi-knowledge/EASY OKAPI.md`.
- **Functional updates**: If your changes introduce new files, routes, dependencies, or alter the architectural flow, you MUST proactively edit `easyokapi-knowledge/EASY OKAPI.md`.
- **Behavioral updates**: If your task establishes new strict coding patterns, behavioral constraints, or anti-patterns, you MUST proactively edit `Rule.md`.
