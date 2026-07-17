# Plan: Ship EasyOKAPI as a No-Source Frozen Binary (PyInstaller)

Status: **FEATURE-COMPLETE** (pending cutover) — P1–P4 all implemented. P1 validated on
CI; P2 unit-tested; P3a green on CI; P3b (mac/win/linux frozen installers) + P4 (online
`/api/download?kind=bundle`) implemented, validated as far as possible without a real
frozen build. Remaining: flip `ENCODE_SOURCE=true` to exercise the frozen pipeline
end-to-end on CI, sign/notarize, and the source→frozen cutover.

## Progress log

**P4 (server: per-platform bundle download) — done (`online` branch):**
- `GET /api/download?kind=bundle&platform=mac|win|linux` resolves the release's
  `EasyOKAPI-bundle-{mac|win|linux}.{tar.gz|zip}` asset (`download_service.get_bundle_asset()`)
  and 302-redirects to its public download URL; the desktop swap updater follows it. The
  source-tarball path and `/api/version` are unchanged. py_compile-clean; committed on
  `online` (not yet pushed).

**P1 (backend freeze) — code complete, validated on v1.1.12:**
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

**P2 (binary-swap updater) — client side code complete:**
- `update_service.download_and_apply()` branches on `sys.frozen`. Frozen path:
  `_download_and_stage_bundle()` streams the platform onedir archive
  (`?platform=&kind=bundle`) into app-data, extracts + verifies it, and records a
  `_pending_update.txt` marker; `apply_pending_swap_and_exit()` (called by
  `/update/finalize`) spawns a detached PowerShell/`sh` helper that waits for the
  port to free, swaps `EasyOKAPI/` for the staged dir (rollback on failure), and
  relaunches. No `pip` step. Source path unchanged (tarball + pip + `os.execv`).
- `tests/test_update_binary_swap.py`: 14 tests (347 total pass). The live swap +
  relaunch is exercised by the per-OS CI smoke test (P3), not locally.
- **Still needs the server (P4):** `/api/download?kind=bundle` must vend a NEW
  onedir-bundle artifact (`EasyOKAPI-bundle-{mac|win|linux}.{tar.gz|zip}`), distinct
  from the existing installer assets (`.dmg`/`.exe`/installer `.tar.gz`). CI (P3)
  builds + publishes it.

**P3b (installers embed the binary + migrate old installs) — done (all 3 platforms):**
- Vendor bundling fix (`tools/fetch_vendor.py` + CI smoke assert) so the freeze ships
  `static/vendor/`.
- **macOS:** `run-frozen.scpt` → `launch-frozen.sh` (+ `migrate-frozen.sh`), packaged by
  `build-dmg-frozen.sh` → `EasyOKAPI_v<ver>_mac.dmg`.
- **Windows:** `setup-frozen.nsi` (bundles the onedir, migrates `$INSTDIR\code\` data →
  `%LOCALAPPDATA%\EasyOKAPI`) → `EasyOKAPI_Setup_<ver>_frozen.exe`.
- **Linux:** `build-tarball-frozen.sh` + `install-frozen.sh` (migrates `/opt/EasyOKAPI`
  data → `~/.local/share/EasyOKAPI`, CDC udev rule, desktop entry) + `run-frozen.sh`.
- All additive + `ENCODE_SOURCE`-gated; the source installers are untouched. Each
  migrates an old source install's `data/json/report/log` + settings, then replaces it.
  Validated as far as possible locally (`bash -n`, YAML parse, the AppleScript applet
  compiles); the DMG/NSIS builds + install flow are validated on CI / real machines.
- **Follow-ups:** macOS notarization of the embedded onedir; Windows exe code-signing;
  an eventual cutover that gates the *source* installer steps off.

**P3a (CI freeze + smoke + bundle artifacts) — done:**
- `.github/workflows/main.yml`: each `build-*` job, gated by `ENCODE_SOURCE` (repo var,
  default `false`), now also freezes the onedir via `tools/package.py --encode`,
  smoke-tests `/ping`, and uploads `EasyOKAPI-bundle-{mac|win|linux}.{tar.gz|zip}`;
  the `release` job publishes them. Additive — the source installers still build, so
  unsetting the flag changes nothing. YAML validated.
- **To activate:** set the repository variable `ENCODE_SOURCE=true` (Settings → Secrets
  and variables → Actions → Variables). The next push runs the freeze + smoke on clean
  mac/win/linux runners — the first real validation of P1's PyInstaller spec.
- **P3b (installer embedding + migration) pending** — deferred until the freeze is green.

**What changed vs the original plan (v1.1.6 → v1.1.12):**
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
- **`static/vendor/`** (jQuery, Chart.js, SweetAlert2, numeric.js, MathJax + WOFF
  fonts) is git-ignored and normally fetched by the installer at runtime, so it is
  absent on a clean CI checkout. `tools/package.py` calls `tools/fetch_vendor.py`
  **before** PyInstaller to populate it, or the frozen UI ships without its JS/fonts.
  The CI smoke test asserts `/static/vendor/jquery-3.6.0.min.js` is served, so a
  missing vendor tree fails the build instead of shipping a broken UI.

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
| `src/update_service.py` | Branch on `sys.frozen`: frozen → download+stage the platform onedir bundle and swap via a detached helper; source → unchanged tarball+pip flow (kept, with its tests). `_sync_version_file`/`_install_requirements` run in source mode only. | ✅ done (P2) |
| `src/routes/update_routes.py` | `finalize` hands a frozen build off to `apply_pending_swap_and_exit()` (detached swap+relaunch); source build falls through to the normal SIGTERM shutdown. | ✅ done (P2) |
| `src/browser_mgt.py` | Verify host-mapping / `sudo open` paths hold under frozen. | ⏳ P3 |

---

## 8. In-app update for binaries (P2 — client side DONE)

`update_service.download_and_apply()` branches on `sys.frozen`:

**Frozen build (implemented):**
- `GET /api/version` unchanged — version compare uses the running binary's
  compiled `state.APP_VERSION` (no `state.py` on disk, no regex read).
- `GET /api/download?platform={mac|win|linux}&kind=bundle` → the platform **onedir
  bundle archive** (`.zip` on Windows, `.tar.gz` else), expanding to a single
  top-level `EasyOKAPI/` dir (exe + `_internal/`).
- Apply = `_download_and_stage_bundle()`: stream archive into the writable app-data
  dir, extract to `_update_staging/`, verify (exe + `_internal/` present), and write
  a `_pending_update.txt` marker. **No `pip` step** (deps are inside the binary).
- Swap = `apply_pending_swap_and_exit()`, triggered by `/update/finalize`: spawn a
  **detached** OS-shell helper (PowerShell on Windows, `sh` on POSIX) that waits for
  the port to free, moves `EasyOKAPI/` → `EasyOKAPI.old`, moves the staged dir into
  place (rollback on failure), relaunches the new exe, then deletes `.old`. The app
  then `os._exit()`s to free the port and unlock the install dir. A running process
  can't replace its own loaded files in place (esp. Windows), so the move is done by
  the external helper after exit — generalizing the existing `_restart_windows`
  detached-relauncher pattern.
- Covered by `tests/test_update_binary_swap.py` (platform mapping, extract/verify,
  pending marker, branch selection, script builders). The live swap+relaunch is
  validated by the per-OS CI smoke test (P3), not locally.

**Source build (unchanged):** tarball overwrite + `_install_requirements` +
`_sync_version_file` + `os.execv` restart, with its existing tests intact.

**Server-side change (P4) — ✅ done on the `online` branch** (commit `feat(download):
serve per-platform onedir bundle…`): `GET /api/download?kind=bundle&platform=mac|win|linux`
now resolves the release's `EasyOKAPI-bundle-{mac|win|linux}.{tar.gz|zip}` asset via the
new `download_service.get_bundle_asset()` and 302-redirects to its public download URL
(the desktop client follows the redirect; cross-host redirect drops the bearer token, which
is fine for a public release asset). The default source-tarball path and `/api/version` are
unchanged. CI (P3a) already publishes those bundle assets to each release.

---

## 9. Installer changes — P3b (PENDING; deferred until the freeze is green)

Rewriting three platform installers on top of a freeze that has never run on CI is
high-risk and untestable locally, so it is sequenced **after** P3a proves the freeze.

### macOS (`installer-mac/`) — ✅ done (additive, gated)
New files (the source `build-dmg.sh` / `setup.sh` / `launch.sh` are untouched):
- `run-frozen.scpt` — applet that just launches the embedded binary (no token
  prompt, no sudo, no setup).
- `launch-frozen.sh` — runs migration then `exec EasyOKAPI/EasyOKAPI --alias 127.0.0.1`
  (loopback avoids the `/etc/hosts` edit that needed sudo). No pyenv/venv.
- `migrate-frozen.sh` — one-time copy of `data/json/report/log` + settings from an old
  source install — `/Applications/EasyOKAPI/code`, or `/Applications/microalbumin-Flask`
  from before the install-path rename — into the app-data dir, then removes the old
  install (marker-guarded, best-effort). Note the source install's `/Applications/EasyOKAPI`
  folder is a different path from this build's `/Applications/EasyOKAPI.app`.
- `build-dmg-frozen.sh` — embeds `dist/EasyOKAPI/` into `EasyOKAPI.app/Contents/Resources/`
  and produces `EasyOKAPI_v<ver>_mac.dmg`. CI `build-macos` runs it + uploads the DMG when
  `ENCODE_SOURCE=true`.
- **Caveat (notarization):** an unsigned/un-notarized frozen binary trips Gatekeeper
  ("developer cannot be verified"). `build-dmg-frozen.sh` does `codesign --deep` when
  `SIGNING_IDENTITY` is set; full notarization of the embedded onedir is a follow-up
  (see `SIGNING.md`). Until then users right-click→Open or `xattr -dr com.apple.quarantine`.

### Windows (`installer-win/`) — ✅ done (additive, gated)
New file (source `setup.nsi` untouched):
- `setup-frozen.nsi` — minimal NSIS that bundles the onedir via `File /r dist\EasyOKAPI\*`,
  shortcuts to `EasyOKAPI.exe --port 5099 --alias 127.0.0.1` (loopback avoids the
  hosts-file edit), and migrates `data/json/report/log` + settings from an old
  `$INSTDIR\code\` source install into `%LOCALAPPDATA%\EasyOKAPI` (marker-guarded). No
  token page / download / git / pyenv / venv. CI `build-windows` compiles it + uploads
  `EasyOKAPI_Setup_<ver>_frozen.exe` when `ENCODE_SOURCE=true`. (Code-signing the exe is
  a follow-up.)

### Linux (`installer-linux/`) — ✅ done (additive, gated)
New files (source `install.sh` / `build-tarball.sh` untouched):
- `build-tarball-frozen.sh` — packages `dist/EasyOKAPI/` + installer/runner into
  `EasyOKAPI_linux_v<ver>_frozen.tar.gz`.
- `install-frozen.sh` (sudo) — migrates old `/opt/EasyOKAPI` source data into
  `~/.local/share/EasyOKAPI`, installs the onedir to `/opt/EasyOKAPI`, adds a **CDC**
  udev rule (`tty`, vendor 239a, MODE 0666 — replaces the old HID hidraw rule) so the
  serial port is user-accessible, and a desktop entry that runs the binary (no sudo,
  no pkexec). No apt deps / pyenv / venv / vendor fetch.
- `run-frozen.sh` — execs the binary. CI `build-linux` builds the tarball + uploads it
  when `ENCODE_SOURCE=true`.

**Note:** the frozen installer steps are additive — the source DMG/EXE/tarball still
build. A later cutover can gate the source steps off (and drop the `AUTH_BASE_URL`
requirement, which the frozen path doesn't need) once the frozen installers are trusted.

All three: **gated by `ENCODE_SOURCE`.** `false` ⇒ keep today's source flow untouched.
**Migration (§11.5):** the encoded installer detects an old source-based install and
replaces it (preserving the user's data/json/report/log by relocating to app-data).

---

## 10. CI changes (`.github/workflows/main.yml`) — P3a (DONE)

Implemented, gated by the `ENCODE_SOURCE` repo variable (default `false`, so the
existing source pipeline is untouched until opt-in):
- `setup` job resolves `ENCODE_SOURCE` (`vars.ENCODE_SOURCE || 'false'`) into an
  `encode_source` output the build jobs branch on.
- Each `build-{macos,windows,linux}` job, when `encode_source == 'true'`, additionally:
  sets up Python 3.8, `pip install -r requirements.txt -r requirements-build.txt`,
  runs `python tools/package.py --encode` (PyInstaller onedir), **smoke-tests** the
  binary (launch headless with `--alias 127.0.0.1`, poll `/ping`, assert 200 — surfaces
  missing hidden imports / datas), archives the onedir to
  `EasyOKAPI-bundle-{mac|win|linux}.{tar.gz|zip}`, and uploads it as an artifact.
- `release` job downloads those bundle artifacts (gated) into `dist/` so the existing
  `gh release upload dist/*` publishes them alongside the installers — these are what
  the in-app swap updater (P2) and the server (P4) consume.

These steps are **additive**: the source installers (DMG/EXE/tarball) still build, so
nothing regresses when `ENCODE_SOURCE` is unset. P3b then makes those installers embed
the binary.

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
   `--cdc-logger` re-entry; collector log-dir fix. ✅ **done (v1.1.12), pending a clean
   CI/non-iCloud freeze + smoke test.**
2. **P2 — Updater:** ✅ **done (client side).** `update_service` branches frozen→
   bundle download+stage+detached swap / source→unchanged; `/update/finalize` drives
   the swap; `/api/download?platform=&kind=bundle` contract defined; version from the
   running binary. 14 new tests. Live swap awaits the CI build (P3); server vending
   the bundle artifact is P4.
3. **P3 — Installers + CI:**
   - **P3a (CI freeze + smoke + bundle artifacts):** ✅ **done.** `main.yml` builds the
     PyInstaller onedir per OS, smoke-tests `/ping`, and publishes the
     `EasyOKAPI-bundle-*` update artifacts — gated by `ENCODE_SOURCE` (repo var, default
     `false`). Set the repo variable to `true` to validate the freeze on clean runners
     (this is the keystone that was blocked locally by iCloud).
   - **P3b (installer embedding + migration):** ✅ done — mac/win/linux frozen installers
     embed the onedir, migrate old source-install data to app-data, and build in CI
     (gated). Source installers untouched. Follow-ups: signing/notarization; source-step
     cutover.
4. **P4 — Server + cutover:** ✅ done — online-branch `/api/download` resolves
   `?kind=bundle&platform=` to the per-platform bundle asset (302 redirect) via
   `get_bundle_asset()`. Remaining cutover items: publish/point users at the frozen
   installers, sign/notarize, and gate the source steps off when ready.

Docs to update on completion (per `CLAUDE.md`): `Rule.md`,
`easyokapi-knowledge/EASY OKAPI.md`, `CLAUDE.md`, `BUILD_MAC.md`.
