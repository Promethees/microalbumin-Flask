# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Start Here

Before writing any code, read these two files in order:

1. **`Rule.md`** — Hard constraints, coding rules, and anti-patterns for this branch.
2. **`easyokapi-knowledge/EASY OKAPI.md`** — Architecture, file map, route table, data formats.

---

## Commands

```bash
# Install dependencies (Python 3.8 via pyenv; Mac uses requirements.txt, Windows uses requirements-win.txt)
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

## Current Version: 1.0.8

---

## Architecture at a Glance

```
main.py (thin entry point)
  └── registers 5 Flask Blueprints from src/routes/
        ├── core_routes.py    — ping, index, shutdown, browse, JSON cal, report subjects
        ├── file_routes.py    — CSV/JSON CRUD, export, merge, report CRUD
        ├── hardware_routes.py — HID subprocess control (run/check/terminate/logs)
        ├── math_routes.py    — server-side regression API
        └── ai_routes.py      — AI assistant: chat, settings, Ollama status, model pull

src/
  ├── state.py          ← global state singleton (process, paths, delimiter, PRODUCTION_MODE)
  ├── validators.py     ← @validate_json decorator for route input validation
  ├── math_ops.py       ← scipy/numpy regression (linear, poly, log, exp, Michaelis-Menten)
  ├── ai_assistant.py   ← Ollama client, MCP tool engine, multilingual system prompts
  ├── ai_settings.py    ← AI settings persistence (ai_settings.json)
  └── routes/           ← blueprint modules (see above)

static/script/
  ├── report.js         ← report generation + subject CRUD UI
  ├── user-guide.js     ← interactive spotlight user guide
  └── ai-chat.js        ← floating AI chat widget (Ollama-powered, 6 languages)

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
- **CLI flags**: `--port`, `--alias`, `--verbose` / `-v`, `--mem-monitor`.
- **User-guide translations**: Step text for the interactive user guide lives in `guide_translations/<lang>.json` (one file per language: `en` is the baseline in `guide_training.json`; `vi`, `zh`, `fr`, `ja`, `ru` are in `guide_translations/`). Each file contains guide topics as objects with `id`, `steps` (array of strings), and `queries` (keyword list for AI matching). When adding or editing guide steps, update both `guide_training.json` (EN) and all language files in `guide_translations/`.
- **Tests live in `tests/`** — `test_utils.py`, `test_core_logic.py`, `test_data_processing.py`, `test_app.py`. Run with `pytest tests/ --ignore=venv`.

---

## Documentation Update Rule

After any significant change, update:
- `Rule.md` if you introduce new behavioral constraints or anti-patterns.
- `easyokapi-knowledge/EASY OKAPI.md` if you add files, routes, modules, or change architecture.
- `CLAUDE.md` (this file) if the at-a-glance summary above becomes stale.
