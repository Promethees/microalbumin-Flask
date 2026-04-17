# Manual Test Checklist - Easy OKAPI

This checklist outlines the steps required to manually verify the core features of the Easy OKAPI application. Ensure the physical PyBadge device is connected where applicable.

## 1. Environment & Startup
- [ ] **Server Launch:** Run `python main.py`. Verify Flask starts and the browser automatically opens to `http://127.0.0.1:5000`.
- [ ] **First-run Prompt:** Ensure the splash screen appears. Click "Get Started" and verify the main dashboard loads.
- [ ] **Shutdown:** Click "Shutdown Server" in the top right. Verify the backend process terminates and a "Goodbye" page is shown.

## 2. Directory & Path Management
- [ ] **Manual Path Edit:** Type a valid path into the "Directory" input. Verify the file table updates automatically.
- [ ] **Browse Path Button:** Click "Browse Path". Verify the native directory picker opens (via browser API).
- [ ] **Navigation Blocks:** 
    - [ ] Click a folder in "Go forward" to descend.
    - [ ] Click the folder in "Go back" to ascend.
- [ ] **Persistent States:** Refresh the page. Verify the browsed directory is remembered (if handled by local storage).

## 3. Hardware Interfacing (PyBadge)
- [ ] **Connection:** Connect PyBadge via USB.
- [ ] **Start Reading:** 
    - [ ] Enter a "Base Name".
    - [ ] Set a "Timeout" and "Interval".
    - [ ] Click "Start reading". Verify the "Stop reading" button enables and the log display begins showing HID data.
- [ ] **Live View:** Click "View live data" while a script is running. Verify the chart updates as new lines are appended to the CSV.
- [ ] **Termination:** Click "Stop reading". Verify the process stops and the device is released.
- [ ] **Error Handling:** Try to "Start reading" without a device connected. Verify a "Device not found" popup appears.

## 4. File Operations
- [ ] **CSV Table:**
    - [ ] **Select:** Toggle "✅ Select" on a CSV. Verify the "Data Display" section appears.
    - [ ] **Copy:** Select a file, click "Copy". Verify a duplicate file appears in the list.
    - [ ] **Delete:** Click "❌ Delete". Confirm the popup. Verify the file is removed from the list.
    - [ ] **Edit:** Click "✏️ Edit". Verify values can be modified and saved.
- [ ] **Merge Files:** Select multiple CSVs and click "Merge Files". Verify the combined CSV contains data from all sources.

## 5. Data Analysis & Visualization
- [ ] **Chart Interaction:** 
    - [ ] Verify the Chart.js plot renders data points correctly.
    - [ ] Hover over points to see tooltips.
- [ ] **Range Selection:** 
    - [ ] Modify "From" and "To" time values. Verify the chart zooms/clips to the selected range.
- [ ] **Regression Algorithms:** 
    - [ ] Switch between Linear, Polynomial, etc.
    - [ ] Verify the R² values and Coefficients table update at the bottom of the chart.
    - [ ] (Kinetics Only) Change "Window Size". Verify the "maxRate" line shifts.
- [ ] **Normalization:** Toggle "Normalize Data (remove Blank)". Verify Y-axis values reset relative to the minimum.
- [ ] **Split Sources:** Toggle "Split by Sources". Verify one chart section per "Value:n" column is generated.

## 6. Exporting Results
- [ ] **Data Export:** Click "Export Data to Calibrate". Verify a new file is created in the saving directory containing regressed slopes/intercepts.
- [ ] **Coefficient Export:** Click "Export Calibrated Coefs". Verify a `.json` file is created in the `json/kinetics` or `json/point` directory.
- [ ] **JSON Management:** Verify the "Calibrated JSON" table shows the newly exported coefficients.

## 7. Input Validation (New Feature)
- [ ] **Malformed Payloads:** (Requires Dev Tools/API Client) Send a POST request to `/export_data` with a string instead of a number for `threshold_val`. Verify the server returns a `400 Bad Request` with an "Invalid value" message.
- [ ] **Missing Fields:** Send a request to `/run_script` without `base_name`. Verify the validator returns a "Missing required field" error.

## 8. UX & UI
- [ ] **Dark Mode:** Toggle the theme button in the top left. Verify colors switch between light/dark themes.
- [ ] **User Guide:** Click "User Guide". Verify the slide-out panel contains the instruction manual.
- [ ] **Responsive Buttons:** Resize the browser window. Verify button text shrinks to fit without overflowing.
