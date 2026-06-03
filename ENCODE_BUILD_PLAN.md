# Plan: Ship EasyOKAPI as a No-Source Frozen Binary (PyInstaller)

Status: **IN PROGRESS** — decisions resolved (see §11); P1 code complete & validated
on **v1.1.8**; P2–P4 pending.

## Progress log

**P1 (backend freeze) — code complete, validated on v1.1.8:**
- `.env` / `.env.example` `ENCODE_SOURCE` flag; `tools/package.py`; `easyokapi.spec`
  (onedir); `requirements-build.txt` (pyinstaller 6.11.1).
- `src/state.py` frozen-aware `bundle_dir` (assets, `sys._MEIPASS`) vs `script_dir`
  (writable per-user app-data, e.g. `~/Library/Application Support/EasyOKAPI`), with
  first-run `json/` seeding. Writable working folders: **`data/`, `json/`, `report/`,
  `log/`** (the four the user owns; identical to `update_service._PRESERVE`).
- Path consumers repointed: `activation.py` (writable `activation.json`),
  `ai_assistant.py` (bundled guide files), `ai_routes.py` (writable `.env`),
  `file_path.py` (writable `DATA_ROOT`), `main.py` (Flask static/template from bundle).
- `main.py` `--cdc-logger` re-entrant dispatch; `hardware_routes.py` launches the
  collector by re-invoking the binary (`sys.executable --cdc-logger`) when frozen, or
  `log_cdc_data.py` in dev; `log_cdc_data.py` writes its log + output marker to the
  writable `state.script_dir/log`.
- **Validated:** 333/333 tests pass; dev import OK; frozen-path simulation passes
  (correct bundle/app-data split, writable dirs created, JSON seeded); `--cdc-logger`
  dispatch enters logger mode and exits without starting Flask.
- **Blocked (environment, not code):** a full local PyInstaller freeze cannot complete
  here because the repo lives under iCloud-synced `~/Desktop/Documents`; the venv's
  site-packages are `dataless` (cloud-evicted) and PyInstaller's reads time out
  (`Errno 60`). **Remedy:** build on a non-synced path (clone to `~/build/...` or
  `/tmp`) or rely on CI (clean runners) — the real production build target.

**What changed vs the original plan (v1.1.6 → v1.1.7):**
- **HID is gone.** The "Run" flow moved to the CDC serial collector
  (`log_cdc_data.py`); the HID logger scripts were removed (`log_hid_data*.py`).
  CDC needs **no elevated privileges**, so the original `src/privilege.py` sudo
  priming + keepalive and the `sudo -n … --hid-logger` launch are **dropped
  entirely** (decision §11.4 is now moot). The re-entrant pattern survives but as a
  plain `--cdc-logger` mode with no sudo.
- **`log/` is now an explicit writable folder** alongside `data/`, `json/`, `report/`.
- The in-app updater (`src/update_service.py`) is **still source-tarball based**
  (downloads `.tar.gz`, overwrites `.py`, runs `pip install`, `os.execv`). This is
  incompatible with a no-source frozen binary and is the core of P2.

---


## 1. Goal

Distribute the app the way a proprietary desktop program does: **no `.py` source on
the user's machine.** The user sees only:

- the application binary (opaque), and
- four writable working folders: `data/`, `json/`, `report/`, `log/`.

Everything else (Python interpreter, Flask, all our modules, `templates/`, `static/`,
`guide_training.json`, etc.) is bundled **inside** the frozen binary and never written
to disk in readable form.

Build tool: **PyInstaller** (chosen). A `.env` boolean toggles encoded-build vs.
plain-source dev mode.

Scope: **Python backend only** (§5). Front-end JavaScript is intentionally left as-is.

### Threat-model honesty
- **Python:** PyInstaller embeds **bytecode**, not plain source. A determined attacker
  can extract and decompile it. This stops casual inspection and copy-paste reuse (the
  stated goal — "source not revealed") but is not equivalent to native compilation. If
  you later want Claude-level opacity, the same packaging layer can swap PyInstaller →
  Nuitka with no change to installers/updater. This plan keeps that swap cheap.
- **JavaScript — out of scope (decided):** front-end JS cannot be hidden — the browser
  must download and run it, so it is always recoverable from DevTools/network.
  Obfuscation would add build complexity for only cosmetic friction, so the
  first-party `static/script/*.js` files and the inline `<script>` blocks in
  `templates/index.html` ship in their **original form**. PyInstaller still bundles
  `static/` and `templates/` into the binary (so they aren't loose files on disk), but
  they are served verbatim to the browser and are not treated as secret.

---

## 2. The `.env` flag

Add to `.env` (and document in `.env.example`):

```
# Build-time only. true => `package` produces a frozen, no-source binary.
# false => ship plain .py source (current behaviour, for dev/internal builds).
ENCODE_SOURCE=true
```

This is read by the **build/packaging script and CI**, never by the running app.
`.env` is already git-ignored (`*.env`) and already preserved across updates
(`update_service._PRESERVE`), so nothing leaks.

---

## 3. Current architecture (what we're replacing)

```
CI (main.yml) builds DMG/EXE/tarball  ──►  contains ONLY installer scripts
        │
        ▼  first run
setup.sh / launcher.ps1 / install.sh
   • install Homebrew/pyenv/Python 3.8
   • download SOURCE tarball from  AUTH_BASE_URL/api/download   ◄── plaintext .py
   • create venv, pip install -r requirements.txt
        │
        ▼  in-app update
update_service.download_and_apply()
   • download SOURCE tarball, overwrite .py files in place
   • re-run pip install, then os.execv restart
```

Source is plaintext at every stage. The whole "download `.py`" pipeline must change to
"ship/download a binary."

---

## 4. Target architecture

```
CI (main.yml)
   ├─ build-macos:   pyinstaller → EasyOKAPI (mach-o)  → wrap in DMG
   ├─ build-windows: pyinstaller → EasyOKAPI.exe       → wrap in NSIS installer
   └─ build-linux:   pyinstaller → EasyOKAPI (elf)     → wrap in tarball
        (each gated by ENCODE_SOURCE; false ⇒ today's source pipeline)
        │
        ▼ first run
installer
   • NO pyenv / venv / pip  (interpreter is inside the binary)
   • lay down binary in app dir
   • writable data/ json/ report/ log/ live in the per-user app-data dir,
     auto-created + seeded on first launch by state.py (not the installer)
        │
        ▼ in-app update
update_service.download_and_apply()
   • download NEW BINARY for this platform, atomic-replace the old one, relaunch
```

---

## 5. PyInstaller build

### 5.1 New files
- `tools/package.py` — single cross-platform entry point. Reads `ENCODE_SOURCE` from
  `.env`. If true → invokes PyInstaller with the spec below and emits the platform
  artifact. If false → falls back to today's "git archive the source" path. Keeps the
  freezer choice behind one function so Nuitka can be dropped in later.
- `easyokapi.spec` — PyInstaller onedir spec (reproducible).

### 5.2 What is bundled (`datas` in the spec)
- `templates/`, `static/`, `guide_training.json`, `guide_translations/*.json`,
  `sample_data/`, and the **default/seed** `json/` content (the live `json/` becomes a
  writable folder — see §6).

### 5.3 Hidden imports
- The re-entrant collector and its deps: `log_cdc_data`, `send_command`,
  `get_next_filename`, `serial`, `serial.tools.list_ports`.
- All `routes.*` blueprints (imported via string in dev path setup).
- scipy/numpy/pandas/groq/requests are picked up by PyInstaller's bundled hooks; the
  per-OS CI smoke test confirms.

### 5.4 onedir (chosen)
onedir wrapped inside the platform installer (DMG/app-bundle, NSIS dir, tarball).
Faster start than onefile and the Python guts stay in an opaque internal folder.

### 5.5 The data-collector subprocess (re-entrant, no sudo)
`hardware_routes.run_script` launches the CDC collector. After freezing there is no
`python`, no `venv`, and no `log_cdc_data.py` on disk, so the single binary plays both
roles:
- **Frozen:** `EasyOKAPI --cdc-logger --base-dir … --base-name …` — `sys.executable`
  *is* the app binary; `main.py` dispatches `log_cdc_data.main()` before Flask loads.
- **Dev:** `python log_cdc_data.py --base-dir … --base-name …` (unchanged).

CDC serial needs **no elevation** — no sudo prompt, no privileged helper. (This
replaced the old HID path, which did need `sudo` on macOS.)

---

## 6. Writable folders: `data/`, `json/`, `report/`, `log/`

These must live **outside** the read-only binary and survive updates.

- `state.py` resolves two roots: `bundle_dir` (read-only assets, `sys._MEIPASS` when
  frozen) and `script_dir` (writable per-user app-data when frozen, e.g.
  `~/Library/Application Support/EasyOKAPI`; `%LOCALAPPDATA%\EasyOKAPI` on Windows;
  `~/.local/share/EasyOKAPI` on Linux). In dev both equal the project root (unchanged).
- `data/`, `json/`, `report/`, `log/`, `user_settings.json`, `activation.json`, `.env`
  all hang off `script_dir`. Bundled read-only assets (`templates/`, `static/`,
  `guide_training.json`, `guide_translations/`) resolve from `bundle_dir`.
- On first run `state._seed_writable_from_bundle("json")` copies the bundled default
  JSONs into the writable `json/` only if it is missing/empty, then leaves it
  user-owned. `data/`, `report/`, `log/` auto-create empty.
- All four are already in `update_service._PRESERVE`, consistent with "user owns them."
- **Decided (§11.1):** per-user app-data dir, because data must be preserved across
  update / uninstall / recover — and `/Applications` is not reliably writable.

---

## 7. Code changes (app side)

| File | Change | Status |
|---|---|---|
| `main.py` | `--cdc-logger` dispatch branch at top (runs collector, exits) before Flask import; guard `sys.path.append('src')` under frozen; Flask static/template folders from `state.bundle_dir`. | ✅ done |
| `src/state.py` | Frozen-aware `bundle_dir` + `script_dir` (per-user app-data); writable `data/json/report/log`; first-run `json/` seed. | ✅ done |
| `src/file_path.py` | `DATA_ROOT` from `state.script_dir` (writable), not `__file__`. | ✅ done |
| `src/routes/hardware_routes.py` | Frozen: `sys.executable --cdc-logger`; dev: `log_cdc_data.py`. No sudo. | ✅ done |
| `log_cdc_data.py` | Log dir + `current_output.txt` marker under `state.script_dir/log`. | ✅ done |
| `src/activation.py` | `activation.json` under `state.script_dir`. | ✅ done |
| `src/ai_assistant.py` | Guide files from `state.bundle_dir`. | ✅ done |
| `src/routes/ai_routes.py` | `.env` from `state.script_dir`. | ✅ done |
| `src/update_service.py` | Rewrite to download+swap a **binary** (see §8). Remove `_apply_tarball`, `_install_requirements`, the `state.py` regex read in `_sync_version_file`. | ⏳ P2 |
| `src/browser_mgt.py` | Verify host-mapping / `sudo open` paths hold under frozen. | ⏳ P2 |

---

## 8. In-app update for binaries (P2)

Replace `update_service.download_and_apply()`:
- `GET /api/version` stays (returns latest version string).
- `GET /api/download?platform=mac|win|linux` now serves the **binary artifact** for
  the caller's OS (was: source tarball).
- Apply = download new binary to a temp path, verify, **atomic replace** the running
  binary/onedir, then relaunch. A running executable can't always overwrite itself
  (esp. Windows) → reuse the existing detached-relauncher pattern (`_restart_windows`)
  to swap-then-launch. Mac/Linux: replace then `os.execv`.
- `pip install` step is **deleted** (deps are inside the binary).
- Version source: read from a bundled `VERSION` marker / the running binary, not from
  a `state.py` regex (there is no `state.py` on disk when frozen).

**Server-side change required** (online branch, not this repo): `/api/download` must
vend per-platform binaries; `/api/version` stays as-is. The online branch currently
streams a GitHub **source** tarball via `fetch_github_release(tag)`, with
`download_service.get_release_asset(platform, tag)` already mapping mac→.dmg /
win→.exe / linux→.tar.gz — so the asset plumbing exists; `/api/download` just needs to
call it. Flagged for coordination (§11.3).

---

## 9. Installer changes (P3)

### macOS (`installer-mac/`)
- `setup.sh`: drop Homebrew/pyenv/Python/venv/pip and source-tarball download. Instead:
  place binary; the app self-creates per-user app-data dirs on first launch.
- `build-dmg.sh` / `main.yml build-macos`: run PyInstaller, drop the binary (or `.app`)
  into the DMG. Signing/notarization now signs a real Mach-O.

### Windows (`installer-win/`)
- `setup.nsi` / `startwindow-*.bat`: remove git-clone, pyenv, venv steps. NSIS installs
  `EasyOKAPI.exe` + the onedir `_internal/`.

### Linux (`installer-linux/`)
- `install*.sh` / `build-tarball.sh`: tarball ships the PyInstaller onedir, no venv.

All three: **gated by `ENCODE_SOURCE`.** `false` ⇒ keep today's source flow untouched.
**Migration (§11.5):** the encoded installer detects an old source-based install and
replaces it (preserving the user's data/json/report/log by relocating to app-data).

---

## 10. CI changes (`.github/workflows/main.yml`) (P3)

- Each `build-*` job: `pip install -r requirements-build.txt`, run `tools/package.py`,
  then wrap the artifact in the existing installer step.
- Add a **smoke test** per OS: launch the frozen binary headless, hit `/ping`, assert
  200 — PyInstaller breakages (missing hidden imports, datas) surface here.
- `release` job: upload the binaries to the GitHub release **and** ensure they reach the
  server backing `/api/download` (coordinate per §8).

---

## 11. Decisions (resolved)

1. **Writable-folder location:** per-user app-data dir — **chosen** (user data must be
   preserved after update / uninstall / recover).
2. **onedir vs onefile:** onedir — **chosen**.
3. **Server `/api/download`:** acknowledged — the online branch already has the
   per-platform asset plumbing (`download_service.get_release_asset`); P4 points
   `/api/download` at it.
4. **HID `sudo` on Mac:** **moot** — the run flow moved to CDC serial, which needs no
   privilege. `privilege.py` and the sudo priming are dropped.
5. **Migration cutover:** detect an old source-based install and replace it — **chosen**.

---

## 12. Phasing

1. **P1 — Backend freeze:** `.env`/`tools/package.py`/`easyokapi.spec`; state/path split;
   `--cdc-logger` re-entry; collector log-dir fix. ✅ **done (v1.1.8), pending a clean
   CI/non-iCloud freeze + smoke test.**
2. **P2 — Updater:** rewrite `update_service` for binary swap; define the
   `/api/download?platform=` contract; bundled version marker.
3. **P3 — Installers + CI:** rewire mac/win/linux installers and `main.yml`, gated by
   the flag, with per-OS smoke tests + old-install migration.
4. **P4 — Server + cutover:** online-branch `/api/download` vends binaries; migration
   release.

Docs to update on completion (per `CLAUDE.md`): `Rule.md`,
`easyokapi-knowledge/EASY OKAPI.md`, `CLAUDE.md`, `BUILD_MAC.md`.
