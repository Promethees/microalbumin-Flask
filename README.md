# Easy OKAPI — desktop application

![Latest release](https://img.shields.io/badge/latest-1.5.0-blue)
![Python](https://img.shields.io/badge/python-3.12.11-blue)
![Flask](https://img.shields.io/badge/flask-3.0.3-blue)

A local Flask app that reads a **PyBadge colorimeter** over USB serial (CDC) and
visualises bio-sensor CSV data in your browser. Single user, no cloud, no account
needed to run it. Inspired by the
[IORodeo Open Colorimeter](https://iorodeo.com/products/open-colorimeter).

This is the `main` branch — the desktop app. The hosted web application lives on
the [`online` branch](https://www.easysensorkit.cbbiotec.vn/).

---

## Install

Builds are distributed from <https://www.easysensorkit.cbbiotec.vn/> — sign in,
then download the installer for your platform. Installation is token-gated; the
token comes from your account page, or email
[Minh Thong](mailto:tqmthong@gmail.com).

Activation is **hardware-locked**: the licence binds to one machine, so copying
an install folder to another computer will not unlock it.

> **Path constraint:** the install path must not contain special characters
> (e.g. Vietnamese diacritics `ạ ô ệ`). This bites on Windows in particular.

### macOS

Mount `EasyOKAPI_v<ver>.dmg` and drag the **EasyOKAPI folder** to `/Applications`
(the whole folder, not the bare `.app` — the app needs somewhere to put its code).
First launch runs the setup dialogs. To remove it, use `uninstall.command` from
the DMG or the install folder.

If Gatekeeper blocks the app, install from Terminal instead:

```bash
sudo bash /Applications/EasyOKAPI/EasyOKAPI.app/Contents/Resources/setup.sh <token>
```

### Windows

Run `EasyOKAPI_Setup_<ver>.exe`, paste your token when prompted, and launch from
the **Easy OKAPI** desktop icon. Uninstall with `Uninstall.exe` in the install
folder, or from Add/Remove Programs.

**No USB driver needed** — the PyBadge's CDC serial port is enumerated
automatically by Windows 10/11. No `libusbK`, no Zadig.

### Linux

```bash
./setup.sh --token <token>     # or --no-gui for a headless install
./uninstall.sh
```

`setup.sh` with no arguments opens a Tk window. Screen-reader users should prefer
the non-graphical route — see [`docs/accessibility/INSTALLERS.md`](docs/accessibility/INSTALLERS.md).

### From source (development)

```bash
pyenv install 3.12.11 && pyenv local 3.12.11
pip install -r requirements.txt          # + requirements-dev.txt for the tests
python main.py                           # http://easyokapi.com:5099
```

| Flag | Effect |
|---|---|
| `--port 5099` | Listen port (default 5099) |
| `--alias easyokapi.com` | Hostname alias |
| `--verbose` / `-v` | Show HTTP logs + backend prints |
| `--mem-monitor` | tracemalloc memory-growth tracking |
| `--no-browser` | Don't open a startup browser tab |

Tests: `pytest tests/ --ignore=venv`

Per-platform helper scripts also exist for a scripted source install —
`setup-1-install-pyenv.command` → `setup-2-install-venv.command` →
`setup-3-run.command` on macOS, and `startwindow-1-git.bat` →
`-2-pyenv` → `-3-python` → `-4-venv-run` **one at a time, as Administrator** on
Windows.

---

## Features

### Four measurement modes

`kinetics` · `point` · `calibrate` · `report` — switched from the mode selector;
each shows only the controls that apply to it.

### Reading from the device

Capture data sent by the PyBadge over USB serial. The host log is written to
`log/script_logs.txt`. Disabled in `calibrate` mode.

- **Timestamp or Turn axis.** Timestamp records elapsed seconds; **Record as Turns**
  records a 1,2,3… index instead — one row per point, which is what point-mode
  standards want.
- **Automatic or Manual run.** Automatic reads on an interval; Manual idles the
  device and records one Turn per **Measure now** press.
- **Pause / Resume** holds a run without ending it — the device freezes its
  session clock, so timestamps stay continuous and the timeout doesn't burn.
- **Live session strip.** A chart-recorder trace of the run in progress, pushed
  over SSE rather than polled.

<div align="center"><img src="/images/logHID.png" width="600"></div>

### Virtual controller

The device's eight-button keypad, on screen — drawn as the board's own face, with
each key labelled by **what it does on the device's current screen**. Reads the
device's menu, concentration and timing screens, and can set active multiplexer
channels. Available only while no reading session is running (the serial port has
exactly one owner).

### Browsing and file management

Browse the data folder, select a CSV to visualise, and copy / move / rename /
delete / merge / edit files in place. Search filters on file *identity* — name,
measurement, unit, concentration — not just filename.

<div align="center"><img src="/images/browse.png" width="600"></div>
<div align="center"><img src="/images/fileselection.png" width="600"></div>

### Analysis and display

- **Full Display** toggles `maxRate` (maximum reaction velocity), `Linear`
  (average speed along the reaction stage) and `Sat` (value at saturation).
- **Display Range** changes the plotted window and its unit.
- **Window size** sets the group size for local slopes (min 3, max half the
  file's row count). Kinetics only.

<div align="center"><img src="/images/meas.png" width="600"></div>
<div align="center"><img src="/images/displayrange.png" width="600"></div>

### Standard curves and calibration

Five fit models — linear, polynomial, logarithmic, exponential, Michaelis-Menten
— computed **server-side** in `src/math_ops.py`. In `calibrate` mode:

- **Kinetics calibration** fits against `maxRate`, `Linear` slope, `Sat`, or time
  to saturation.
- **Point calibration** fits against a chosen time point.
- **Turn calibration** treats each recorded Turn as one concentration standard.

<div align="center"><img src="/images/calKinetics.png" width="600"></div>
<div align="center"><img src="/images/calPoint.png" width="600"></div>

Coefficients export to a calibration JSON, to **Excel with a native chart**, or as
**paste-ready Excel formulas**. The **Quick concentration** calculator evaluates a
saved curve at one measured value with no CSV involved.

<div align="center"><img src="/images/exportC.png" width="600"></div>

### Multiple sources

Filter files by how many data sources they carry, plot them together on a
sequential colour ramp, and export all sources or just one.

<div align="center"><img src="/images/multi-meas-display.png" width="600"></div>
<div align="center"><img src="/images/exp-multi.png" width="600"></div>

### Reports

Generate HTML reports organised by subject under `report/<subject>/`, with Excel
export.

### Also in the app

| | |
|---|---|
| **AI assistant** | Groq-backed chat widget with an interactive spotlight user guide |
| **7 languages** | English, Tiếng Việt, 中文, Français, 日本語, Русский, 한국어 |
| **Two interface styles** | `instrument` (default) and `classic` |
| **Accessibility** | WCAG 2.2 Level AA — a published conformance claim |
| **Auto-update** | In-app check and apply, no reinstall |
| **Background music** | Optional radio / YouTube widget, online only, off by default |

---

## Repository layout

```
microalbumin-Flask/
├── main.py                  # Thin entry point — registers 8 blueprints, nothing else
├── log_cdc_data.py          # The host-side data logger (spawned as a subprocess)
├── src/
│   ├── state.py             # Global state singleton
│   ├── routes/              # All routes: core, file, report, hardware, math, ai, music, update
│   ├── math_ops.py          # Server-side regression (scipy/numpy)
│   ├── device_link.py       # Idle-time CDC control link (virtual controller)
│   ├── live_stream.py       # SSE tail of a live reading session
│   ├── ai_assistant.py      # Groq chat client + guide matcher
│   ├── activation.py        # Hardware-locked licence gate
│   └── update_service.py    # Auto-update: source overwrite or frozen binary swap
├── static/
│   ├── style.css            # Design tokens, then all UI styling
│   ├── fonts/               # Self-hosted IBM Plex — no Google Fonts request
│   └── script/              # 21 JS files, vanilla — no build step
├── templates/               # index.html + the standalone pages
├── ui_translations/         # UI catalogs, en.json is the baseline
├── guide_translations/      # User-guide step text per language
├── tests/                   # 37 pytest files
├── installer-mac/           # .dmg builders + SIGNING.md
├── installer-win/           # NSIS installers
├── installer-linux/         # setup.sh / uninstall.sh + tarball builders
├── tools/                   # package.py (PyInstaller freeze), gen_classic_style.py
├── legal/                   # EULA, Privacy Notice — rendered into the installers
└── docs/                    # publishing/ (code signing), accessibility/
```

User data (`data/`, `json/`, `log/`, `report/`) lives in a relocatable data root,
not necessarily beside the program — see `src/data_root.py`.

---

## Documentation

| Document | For |
|---|---|
| [`Rule.md`](Rule.md) | Hard constraints, coding rules, anti-patterns. Read before changing anything. |
| [`CLAUDE.md`](CLAUDE.md) | Orientation for AI coding agents |
| [`easyokapi-knowledge/EASY OKAPI.md`](easyokapi-knowledge/EASY%20OKAPI.md) | Architecture, file map, route table, data formats |
| [`ENCODE_BUILD_PLAN.md`](ENCODE_BUILD_PLAN.md) | The no-source frozen-binary build |
| [`BUILD_MAC.md`](BUILD_MAC.md) | Building the macOS DMGs |
| [`installer-mac/SIGNING.md`](installer-mac/SIGNING.md) | Codesigning + notarisation |
| [`docs/publishing/`](docs/publishing/) | Developer ID and Authenticode identity |
| [`docs/accessibility/INSTALLERS.md`](docs/accessibility/INSTALLERS.md) | Installing with assistive technology |

---

## Notes

- CSV `Timestamp` values are in **seconds**.
- The directory-picker API can only step to immediate parent/child directories at
  a time; type the path into the text box to jump.

## Licence

Easy OKAPI is proprietary software licensed under the
[End User License Agreement](legal/EULA.md). Data handling is described in the
[Privacy Notice](legal/PRIVACY.md). Publisher: Center for Bioscience and
Biotechnology (CBBiotec), University of Science, VNU-HCM.
