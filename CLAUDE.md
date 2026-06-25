# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Start Here

Before writing any code, read these two files in order:

1. **`Rule.md`** — Hard constraints, coding rules, and anti-patterns for this branch.
2. **`easyokapi-knowledge/EASY OKAPI.md`** — Architecture, file map, route table, data formats.

---

## Commands

```bash
# Install dependencies (Python 3.8 via pyenv; single cross-platform requirements.txt; requirements-dev.txt adds test-only deps)
pip install -r requirements.txt

# Run the app (default port 5099, alias easyokapi.com)
python main.py
python main.py --port 5099 --alias easyokapi.com
python main.py --verbose        # show HTTP logs + backend prints
python main.py --mem-monitor    # enable tracemalloc memory growth tracking

# Run tests (exclude venv)
pytest tests/ --ignore=venv
pytest tests/test_utils.py      # run a single test file
pytest tests/ -k "test_ping"    # run a single test by name
```

**Flask version is 1.1.4** — do not use APIs introduced after Flask 1.x (e.g., `app.json`, `current_app.ensure_sync`). Check Flask 1.x docs for compatibility.

---

## Project in One Line

Flask-based local desktop app that reads a PyBadge colorimeter over USB/HID and visualizes bio-sensor CSV data in a browser. Single-user, no sessions, no SocketIO, no cloud.

---

## Current Version: 1.2.3

---

## Architecture at a Glance

```
main.py (thin entry point)
  └── registers 5 Flask Blueprints from src/routes/
        ├── core_routes.py    — ping, index, shutdown, browse, JSON cal, report subjects
        ├── file_routes.py    — CSV/JSON CRUD, export, merge, report CRUD
        ├── hardware_routes.py — data-logger subprocess control (run/check/terminate/logs); CDC serial by default, HID keyboard fallback via device Left button
        ├── math_routes.py    — server-side regression API
        └── ai_routes.py      — AI assistant: chat, settings, activation

src/
  ├── state.py          ← global state singleton (process, paths, delimiter, PRODUCTION_MODE)
  ├── validators.py     ← @validate_json decorator for route input validation
  ├── math_ops.py       ← scipy/numpy regression (linear, poly, log, exp, Michaelis-Menten)
  ├── ai_assistant.py   ← Groq chat client, MCP tool engine, multilingual system prompts
  ├── ai_settings.py    ← AI settings persistence (ai_settings.json)
  ├── hwid.py           ← per-machine fingerprint (hardware-lock basis)
  ├── activation_pubkey.py ← embedded RS256 public key (verify-only)
  ├── activation.py     ← license gate: verify_token() = RS256 sig + hwid claim
  └── routes/           ← blueprint modules (see above)

static/script/
  ├── report.js         ← report generation + subject CRUD UI
  ├── user-guide.js     ← interactive spotlight user guide
  ├── tooltip.js        ← styled hover-hint component ([data-hint] → body-appended #okapi-tooltip; replaces native title=)
  └── ai-chat.js        ← floating AI chat widget (Groq-powered, 6 languages)

report/                 ← saved HTML reports, organized by subject subdirectory
ai_settings.json        ← AI assistant settings (auto-created on first run)
```

---

## Key Invariants

- **Global state lives in `src/state.py`**, not in `main.py` globals anymore.
- **All routes are in blueprints** — do not add routes directly to `main.py`.
- **`@validate_json`** from `validators.py` must be used on any POST route that accepts JSON.
- **Regression math runs server-side** via `math_ops.py` + `/calculate_coef_and_rsquared` and `/calculate_kinetics_quantities` endpoints. JS `calculate.js` still handles client-side preview rendering.
- **Report system**: Reports are HTML files saved to `report/<subject>/`. CRUD via `/save_report`, `/export_to_report`, `/get_report_subjects`, `/get_report_items`, `/delete_report_subject`, `/copy_report_subject`, `/rename_report_subject`.
- **Startup progress reporter**: `main.py` writes `pct label\n` to a FIFO (`/tmp/easyokapi_progress.pipe` on Mac) so launch scripts can show a progress bar.
- **CLI flags**: `--port`, `--alias`, `--verbose` / `-v`, `--mem-monitor`, `--no-browser` (suppress the startup browser-open tab; passed automatically by restart relaunches so the one-shot reset-display marker isn't stolen by a second tab — see Rule.md §2.20).
- **User-guide translations**: Step text for the interactive user guide lives in `guide_translations/<lang>.json` (one file per language: `en` is the baseline in `guide_training.json`; `vi`, `zh`, `fr`, `ja`, `ru` are in `guide_translations/`). Each file contains guide topics as objects with `id`, `steps` (array of strings), and `queries` (keyword list for AI matching). When adding or editing guide steps, update both `guide_training.json` (EN) and all language files in `guide_translations/`.
- **Tests live in `tests/`** — `test_utils.py`, `test_core_logic.py`, `test_data_processing.py`, `test_app.py`, `test_hwid.py`, `test_activation.py`. Run with `pytest tests/ --ignore=venv`.
- **Hardware-locked activation** (frozen builds): a permanent license token is bound to one machine via an `hwid` claim (`src/hwid.py`) and RS256-signed by the server (`ACTIVATION_PRIVATE_KEY`), verified offline with the embedded public key (`src/activation_pubkey.py`). Copying `activation.json`/the install folder to another machine fails the check. The Windows installer PowerShell mirrors the `hwid` recipe byte-for-byte — keep them in lockstep. Server side lives on the `online` branch (`license_machines` seat table, `/api/activate` binding). See **Rule.md §2.17**.
- **Admin license revocation + account ban** (frozen builds): an admin can deactivate a customer's license server-side even though the permanent token still verifies offline. Two strengths: **Revoke** disables a per-machine seat (`revoked` flag on `license_machines`); **Ban** disables a whole account (`banned` flag on `users`) — blocking web sign-in, download, activation, and app usage on every machine. Server (`online`): shared-secret `POST /api/admin/revoke` + `POST /api/admin/ban` (both by email, send a notification email) + `GET /api/admin/lookup` (+ `/api/admin/users`), and `POST /api/license/check` (the client poll). A revoked seat or banned account fails the AI-proxy / auto-update machine check immediately; a banned account makes `/api/license/check` reply `revoked` + code `account_banned`. Client (`src/activation.py`): `check_revocation()` polls `/api/license/check` and caches the verdict in `license_status.json`; `license_state()` returns `active` / `revoked` (sticky) / `banned` (sticky; from the `account_banned` code) / `needs_recheck` (grace lapsed offline → reverify gate). `main.py` `_enforce_license` gate serves `license_blocked.html` (revoked) / `license_banned.html` (banned) / `license_reverify.html`. Grace window via `LICENSE_GRACE_SECONDS` (default 7d), poll interval via `LICENSE_CHECK_INTERVAL` (default 6h). The local admin console lives on the secret `offline` branch (`admin/`).

---

## Documentation Update Rule

After any significant change, update:
- `Rule.md` if you introduce new behavioral constraints or anti-patterns.
- `easyokapi-knowledge/EASY OKAPI.md` if you add files, routes, modules, or change architecture.
- `CLAUDE.md` (this file) if the at-a-glance summary above becomes stale.

---

## Settings Coverage Rule

Whenever a new feature introduces a user-facing behaviour that could reasonably vary per machine or per preference, ask: **should this be a user setting?**

Checklist to run mentally for every new feature:
- Does it have a hardcoded value a user might want to change (size, count, threshold, default state)?
- Does it default a UI element to a particular state (collapsed/expanded, mode, sort order)?
- Does it control how much data is shown or how the layout behaves?

If any answer is yes, add the setting to `src/user_settings.py` (`DEFAULTS` + validation in `save()`), expose it in the settings modal in `static/script/init.js` (`SETTINGS_DEFAULTS` + form field), apply it on page load (via `USER_SETTINGS` in `index.html` or `init.js`), and add backend tests in `tests/test_user_settings.py`.

**Anti-pattern**: do not hardcode UI dimensions, row limits, default states, or feature flags directly in CSS or JS when a user might reasonably want a different value on their machine.

**Exception — the data-root location**: the user-selectable data folder (frozen builds) is **not** a `user_settings.py` key, because `user_settings.json` lives *inside* the data root (chicken-and-egg). It is stored in a `.easyokapi_dataroot` pointer file beside the default location and managed by `src/data_root.py` + `/data_root` (GET/POST). The Windows installer (`setup-frozen.nsi`) also lets the user choose this folder at install time (writing the same pointer). Relocating **moves** a non-default folder (the default is kept as a fallback copy); the data folder may not be the EasyOKAPI program folder. The move is deferred-commit: `POST /data_root` only **previews** the change (validates, reports move-vs-copy) and the UI confirms, offering **Restart now** (`/data_root/restart` commits the move, then relaunches in place via `update_service.restart_after_delay()` and serves `restarting.html`, which auto-reloads the tab once the new instance is up) or **Cancel** (a no-op — nothing was moved). See **Rule.md §2.19**.

**Default display on restart**: any restart (data-folder relocation or applied update) brings the app back up in the **default display** — kinetics mode, fresh per-view UI state — rather than restoring the previous tab's `localStorage` layout. The restart routes call `state.mark_reset_display_pending()` (a one-shot sentinel in `default_data_root` that survives the process restart); the next index render consumes it and passes `reset_display` → `const RESET_DISPLAY` to `index.html`, which clears per-view `localStorage` (keeping `theme`/AI prefs) before `init.js` forces kinetics mode. See **Rule.md §2.20**.
