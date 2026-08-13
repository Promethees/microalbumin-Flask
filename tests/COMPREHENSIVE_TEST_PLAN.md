# Comprehensive Test Plan — Easy OKAPI

Edge cases, adversarial inputs and numerical stability. The feature-by-feature
walkthrough lives in [`MANUAL_TESTING.md`](MANUAL_TESTING.md); this document does
not repeat it.

---

## 1. Automated suite

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ --ignore=venv          # 37 test files
pytest tests/test_math_ops.py        # one file
pytest tests/ -k "test_ping"         # one test by name
```

CI (`.github/workflows/main.yml`) runs the **whole** suite on Python 3.12 with
`PYTHONPATH=.:src` before any platform build, and fails the build if
`legal/EULA.txt` / `.rtf` are stale against `legal/EULA.md`.

`pytest-cov` is **not** a dependency — `pytest --cov=src` will not work until it
is added to `requirements-dev.txt`.

| Area | Files |
|---|---|
| Routes / app | `test_app.py`, `test_core_logic.py`, `test_data_processing.py`, `test_utils.py` |
| Validation & security | `test_validators.py`, `test_security.py`, `test_accessibility.py` |
| Math & export | `test_math_ops.py`, `test_excel_formula.py`, `test_report_excel.py` |
| Hardware | `test_send_command.py`, `test_device_link.py`, `test_reconnect.py`, `test_live_stream.py`, `test_sentinels.py` |
| Settings & data root | `test_user_settings.py`, `test_data_root.py`, `test_reset_display.py`, `test_event_logger.py`, `test_i18n.py` |
| Licensing | `test_hwid.py`, `test_activation*.py` (4), `test_license_revocation.py` |
| Updates | `test_update_service.py`, `test_update_routes.py`, `test_update_binary_swap.py` |
| AI | `test_ai_*.py` (6) |
| Music | `test_music.py` |

---

## 2. Mathematical stability

### 2.1 Regression edge cases
| ID | Scenario | Expected backend behaviour |
|---|---|---|
| **MATH-01** | Single data point | `slope: 0`, `rSquared: 0`, `coefficients: null` |
| **MATH-02** | Zero gradient (horizontal) | `slope: 0`, `rSquared: 1` |
| **MATH-03** | Identical X values (vertical) | Graceful return, never `ZeroDivisionError` |
| **MATH-04** | Negative values into a log fit | Graceful failure, no `nan` in the response |
| **MATH-05** | Michaelis-Menten with X > Vmax | No infinite loop, no `nan` coefficients |
| **MATH-06** | Fewer points than the model has parameters | Refused with a message, not a `curve_fit` crash |
| **MATH-07** | A column containing `OVFL` / `NONE` / `INF` | Sentinel never reaches `float()`; row handling per `src/sentinels.py` |

### 2.2 Three-way model agreement
The same five models are implemented in three places. They must agree, and a
change to one is a change to all three:

| Implementation | Used by |
|---|---|
| `math_ops.py` fit functions | Fitting a curve from a CSV |
| `math_ops.evaluate_curve()` | `/calculate_concentration` — the Quick concentration calculator |
| `src/excel_formula.py` | `/export_cal_excel_formula` — paste-ready Excel formulas |

- [ ] For each of linear, polynomial, logarithmic, exponential and Michaelis-Menten: fit a curve, evaluate it at a test X through `evaluate_curve`, and evaluate the exported Excel formula at the same X. All three agree to display precision.

### 2.3 Numerical precision
- [ ] Cross-verify a 10-point linear regression against Excel or MATLAB.
- [ ] Sliding windows with R² < 0.90 are excluded from `maxRate` identification.

---

## 3. API robustness & security

### 3.1 Type coercion & rejection
| Endpoint | Payload | Expected |
|---|---|---|
| `/run_script` | `{"timeout_sec": "abc"}` | `400` — `Invalid value` |
| `/export_data` | `{"newFile": "not-bool"}` | `400` |
| `/remove_columns` | `{"columns": 123}` (list expected) | `400` |
| any `@validate_json` route | bare array `[1,2,3]` or a scalar | `400`, **never 500** |
| `/shutdown` | malformed body | `400` **and the app still running** |
| `/update/finalize` | malformed body | `400`, no side effects, app still running |
| `/ping` | GET | `200` |

`@validate_json` is mandatory on every JSON-parsing POST route
(`src/validators.py`). `/download_event_logs` is the one documented exemption —
it is GET+POST and validates its body inline.

### 3.2 Path traversal
- [ ] `../../` in any filename or directory parameter is blocked by `validate_in_data_root` / `validate_in_allowed_roots`, not merely normalised.
- [ ] A symlink inside the data root pointing outside it is refused.
- [ ] The reserved `data/root/` name cannot be created by a user.

### 3.3 Request-origin guard
- [ ] A state-changing request carrying a foreign `Origin`/`Referer` is refused (`src/security.py` — CSRF + DNS rebinding).
- [ ] A request to a hostname other than the bound alias/localhost is refused.

### 3.4 Licensing
- [ ] A token whose `hwid` claim does not match this machine fails verification offline.
- [ ] A tampered token body fails the RS256 signature check.
- [ ] A revoked seat, a banned account, and a lapsed grace window each land on their own page and cannot be cleared by going offline.

---

## 4. Concurrency & resource ownership

The serial port has exactly one owner. These are the ways that used to break:

- [ ] **Double-click Start reading** → one subprocess, not two.
- [ ] `/device/*` during a session → **409**, and `/run_script` closes the control link before spawning the logger.
- [ ] Two browser tabs editing one file → the second gets **423**; a dead tab's lock goes stale after ~120 s.
- [ ] An unconsumed `stream_with_context` response must not corrupt the next request's context (Flask 3 — Rule §2.37). Open `/stream_session`, abandon it, and issue a normal request.
- [ ] No route is registered after the first request (Flask 3 forbids it).

---

## 5. UI & storage edge cases

- [ ] **400 px width:** nothing overflows; the session strip and chart still read.
- [ ] **Browser zoom:** section headings do not shrink below their level.
- [ ] **Corrupt `localStorage`:** set `con-value-read-source-0` to a string in devtools; the dashboard survives a reload.
- [ ] **Popups disabled** in Options: regression errors go to the console, not SweetAlert.
- [ ] **Large CSV** (5000+ rows) renders in under ~2 s.
- [ ] **Long run** (~1000+ points, no timeout) — the session strip and chart stay responsive.
- [ ] **Short interval** (0.5 s) — rows arrive without UI stutter. Note the firmware loop is a flat ~0.174 s regardless of channel count, so it is not the limit.

---

## 6. Hardware simulation (no device)

- [ ] A mock serial script standing in for the PyBadge exercises `hardware_routes.py` end to end (`tests/test_send_command.py`, `test_reconnect.py`, `test_device_link.py` are the existing harnesses).
- [ ] The two-identical-CDC-ports case is covered by a mock that answers `PING` on only one port — the probe must pick that one (`connect_to_device()`).
- [ ] A mock that answers nothing must time out rather than block, given `PORT_TIMEOUT = 0.15 s` and `LineReader` (never `readline()`).
