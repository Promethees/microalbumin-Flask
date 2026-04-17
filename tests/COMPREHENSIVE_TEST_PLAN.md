# Comprehensive Test Plan - Easy OKAPI

This document provides an extensive suite of test cases to ensure the stability, accuracy, and reliability of the Easy OKAPI application.

## 1. Core Functional Tests (Manual)

### 1.1 Application Lifecycle
| Test Case ID | Description | Expected Result |
| :--- | :--- | :--- |
| **SYS-01** | Cold start via `main.py` | Browser opens automatically; Splash screen appears. |
| **SYS-02** | Shutdown button click | Server terminates; PID is released; Browser shows "Goodbye". |
| **SYS-03** | Page refresh state | Browsed path and current chart selection (stored in LocalStorage) persist. |

### 1.2 Hardware Interfacing (PyBadge)
| Test Case ID | Description | Expected Result |
| :--- | :--- | :--- |
| **HW-01** | Connect device mid-session | Dashboard should allow "Start reading" once device is detected. |
| **HW-02** | Disconnect mid-read | Log display should show "Device not found"; Button should revert to "Start reading". |
| **HW-03** | Infinite timeout read | Script runs until "Stop reading" is manually clicked (~1000+ points). |
| **HW-04** | Short interval (0.5s) | Data arrives at high frequency without UI stuttering. |

### 1.3 Data & File Management
| Test Case ID | Description | Expected Result |
| :--- | :--- | :--- |
| **FILE-01** | Large CSV load (5000+ rows) | Chart renders within < 2 seconds. |
| **FILE-02** | Merge 5+ files | Resulting CSV has all 5 sources correctly interleaved or grouped. |
| **FILE-03** | Delete active file | UI resets "No file selected" state cleanly. |
| **FILE-04** | Edit values to float | Values like `1.23456` are correctly saved and re-plotted. |

---

## 2. Mathematical Stability Tests (Math API)

### 2.1 Regression Edge Cases
| Test Case ID | Scenario | Expected Backend Behavior |
| :--- | :--- | :--- |
| **MATH-01** | Single Data Point | Return `slope: 0`, `rSquared: 0`, `coefficients: null`. |
| **MATH-02** | Zero Gradient (Horizontal) | `slope: 0`, `rSquared: 1` (perfect fit for 0 change). |
| **MATH-03** | Vertical Line (Identical X) | Graceful error/return 0 (avoid ZeroDivisionError). |
| **MATH-04** | Negative Values in Log | Backend `math_ops` should return 0/graceful failure. |
| **MATH-05** | MM with X > Vmax | MM formula should avoid infinite loops or `NaN` in coefficients. |

### 2.2 Numerical Precision
- [ ] **Cross-Verification:** Compare Python Scipy results against known Excel/Matlab linear regression outputs for a 10-point dataset.
- [ ] **R² Thresholding:** Verify that sliding windows with R² < 0.90 are correctly excluded from "maxRate" identification.

---

## 3. API Robustness & Security (Validation)

### 3.1 Type Coercion & Blocking
| Endpoint | Payload Injection | Expected Status |
| :--- | :--- | :--- |
| `/run_script` | `{"timeout_sec": "abc"}` (bad type) | `400 Bad Request: Invalid value` |
| `/export_data`| `{"newFile": "not-bool"}` | `400 Bad Request` |
| `/remove_columns`| `{"columns": 123}` (expected list) | `400 Bad Request` |
| `/ping` | GET request | `200 Success` |

### 3.2 Path Traversal Prevention
- [ ] **Dot-Dot-Slash Test:** Attempt to browse to `../../` outside the project root. Verify paths are normalized or blocked if they exceed user permission levels.

---

## 4. UI & UX Edge Cases

### 4.1 UI Stress Tests
- [ ] **Double Click:** Rapidly double-click "Start reading" or "Export Data". Verify backend logic prevents spawning multiple subprocesses.
- [ ] **Window Resize:** Shrink browser to 400px width. Verify the mobile-friendly styles (or button shrinking) kick in.
- [ ] **Popup Spam:** Disable popups in Options and verify regression errors are logged to the console instead of SweetAlert.

### 4.2 LocalStorage Integrity
- [ ] **Corrupt Storage:** Manually set `con-value-read-source-0` to a string in devtools. Verify the dashboard doesn't crash on reload.

---

## 5. Automated Verification (Backend)

### 5.1 Pytest Suite
Run the following from the root directory:
```bash
# Run all unit tests
pytest 

# Run tests with coverage report
pytest --cov=src
```

### 5.2 Specific API Mocks
- [ ] **Connect Mock Device:** Use a mock serial script to simulate PyBadge responses and test the `hardware_routes.py` without hardware.
