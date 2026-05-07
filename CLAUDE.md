# CLAUDE.md — Easy OKAPI (main branch)

## Start Here

Before writing any code, read these two files in order:

1. **`Rule.md`** — Hard constraints, coding rules, and anti-patterns for this branch.
2. **`easyokapi-knowledge/EASY OKAPI.md`** — Architecture, file map, route table, data formats.

---

## Project in One Line

Flask-based local desktop app that reads a PyBadge colorimeter over USB/HID and visualizes bio-sensor CSV data in a browser. Single-user, no sessions, no SocketIO, no cloud.

---

## Current Version: 1.0.4

---

## Architecture at a Glance

```
main.py (197 lines, thin entry point)
  └── registers 4 Flask Blueprints from src/routes/
        ├── core_routes.py    — ping, index, shutdown, browse, JSON cal, report subjects
        ├── file_routes.py    — CSV/JSON CRUD, export, merge, report CRUD
        ├── hardware_routes.py — HID subprocess control (run/check/terminate/logs)
        └── math_routes.py    — server-side regression API

src/
  ├── state.py          ← global state singleton (process, paths, delimiter, PRODUCTION_MODE)
  ├── validators.py     ← @validate_json decorator for route input validation
  ├── math_ops.py       ← scipy/numpy regression (linear, poly, log, exp, Michaelis-Menten)
  └── routes/           ← blueprint modules (see above)

static/script/
  ├── report.js         ← report generation + subject CRUD UI
  └── user-guide.js     ← interactive spotlight user guide

report/                 ← saved HTML reports, organized by subject subdirectory
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

---

## Documentation Update Rule

After any significant change, update:
- `Rule.md` if you introduce new behavioral constraints or anti-patterns.
- `easyokapi-knowledge/EASY OKAPI.md` if you add files, routes, modules, or change architecture.
- `CLAUDE.md` (this file) if the at-a-glance summary above becomes stale.
