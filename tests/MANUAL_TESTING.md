# Manual Test Checklist — Easy OKAPI

What the automated suite (`pytest tests/ --ignore=venv`) cannot reach: real
hardware, real browsers, and anything whose only assertion is "it looks right".
Connect a physical PyBadge before starting sections 3 and 4.

Run against both interface styles where the check is visual — App Settings →
General → **Interface style**: `instrument` (default) and `classic`.

---

## 1. Environment & startup
- [ ] **Launch:** `python main.py`. Flask starts and a browser tab opens at `http://easyokapi.com:5099` (default port **5099**; `--port` overrides).
- [ ] **`--no-browser`:** no tab opens, server still serves.
- [ ] **First-run prompt:** splash appears; "Get Started" loads the dashboard.
- [ ] **Shutdown:** the Shutdown button terminates the backend and shows `goodbye.html` — in **both** interface styles (instrument = flat panel + parked trace + hairline countdown; classic = orb/glass card + countdown ring). Tab closes after the countdown.
- [ ] **Restart display reset:** relocate the data folder (or apply an update) and restart. The app comes back in **kinetics** mode with fresh per-view state; `theme` and AI prefs survive.

## 2. Data folders & paths
- [ ] **Subfolder picker:** create, rename, delete a data subfolder; the file table follows.
- [ ] **Browse:** step into a child folder and back out via the navigation blocks.
- [ ] **Confinement:** typing a path outside the data root is refused.
- [ ] **Identity search:** the file search filters on name / measurement / unit / concentration positionally, AND-ed — not just filename.
- [ ] **Sortable columns:** click each header; the Modified Date column sorts by real date, not string.
- [ ] **Data root relocation:** App Settings → change the data folder. The preview reports move-vs-copy; **Cancel** changes nothing; **Restart now** commits and the tab reloads itself once the new instance answers.

## 3. Reading a session (PyBadge over CDC)
- [ ] **Start:** enter a Base Name, Timeout and Interval, click Start reading. The start-up notice appears before the device is reached; rows land after.
- [ ] **Two ports:** with a board exposing both console and data CDC ports, the run still connects (the `PING` probe picks the right one). Repeat 3–4 times — this used to fail ~half the time.
- [ ] **Session strip:** the chart-recorder trace appears on the first row, one line per source, and carries state + elapsed + next + latest/rows. With `session_strip_enabled` off, the top-right `#session-timer` widget mounts instead — and never both.
- [ ] **Pause / Resume:** pause mid-run. The strip greys and freezes, the timeout stops burning, and on resume the timestamps are **continuous** (no gap). Test from both the inline button and the floating `#reading-control-fab` (scroll the button line out of view to raise it).
- [ ] **Stop:** the process stops and the port is released — confirm by opening the virtual controller straight afterwards.
- [ ] **Turn axis:** tick **Record as Turns**. The CSV's first column is `Turn` with no `Timestamp`, and the chart relabels its X axis.
- [ ] **Manual point mode:** point mode + Turns + Run mode **Manual**. The device idles; each **Measure now** records exactly one Turn, and the button re-arms as soon as the row lands (not seconds later).
- [ ] **Live stream vs fallback:** with `live_stream_enabled` on, `/stream_session` stays open and rows/log arrive pushed. Turn it off — the `/get_data` + `/get_logs` polls take over and the run still displays.
- [ ] **Session end reasons:** let a run hit its timeout, and separately stop one from the device's Left button. The completion message names the right reason each time.
- [ ] **No device:** Start reading with nothing plugged in → "Device not found", button reverts.
- [ ] **Unplug mid-run:** the run ends cleanly rather than hanging.

## 4. Virtual controller
- [ ] **Refused during a session:** with a run in progress every `/device/*` route answers **409** and the panel says so.
- [ ] **Keypad:** each of the eight keys does on screen what it does on the board. Buttons with no effect on the current screen are visible but dimmed.
- [ ] **`BTN:left` in MEASURE is refused** — it would start the HID keyboard fallback and type readings into whatever host window has focus.
- [ ] **Long labels:** a label too long for its key scrolls on a loop; hover pauses it and the tooltip carries the whole string.
- [ ] **Menu bar:** the entries match the device's own menu (including its calibration keys). Clicking one runs the firmware's handler.
- [ ] **Concentration form:** appears **only** while the device is on its Concentration screen. Setting a value commits it the way the keypad's save does; Unknown is a value, not a blank.
- [ ] **Settings form:** timeout + interval round-trip; a null timeout means no timeout.
- [ ] **Screen integrity:** after `MENU:`, `CONC:` and `TIMING:`, the device's screen is drawn **whole** — no missing letters (the regression that forced these into the main loop).
- [ ] **Active channels:** change them; sensors, gain/itime cycles, blanks and the measure screen all rebuild, and the column count follows. Power-cycle → `configuration.json` is restored (runtime-only, expected).
- [ ] **Persisted config:** save channels / UV channel / calibration to the CIRCUITPY drive. The device reloads and comes back running them.
- [ ] **Link switch:** untick `device_link_enabled`; the poll stops and the port is released (a serial monitor can now open it).

## 5. Files
- [ ] Select / deselect, copy, move, rename, delete a CSV.
- [ ] **Editor:** modify values and save; floats like `1.23456` round-trip.
- [ ] **Cross-tab edit lock:** open the same file in the editor in two tabs. The second gets "being edited in another tab" (423). Close the first — the second can open it. Kill a tab without closing the modal; the lock goes stale after ~120 s.
- [ ] **Merge:** merge several CSVs; every source survives.
- [ ] **Timestamps → Turns** conversion in the editor produces a Turn file with no Timestamp column.

## 6. Analysis & charts
- [ ] Plot renders; hover tooltips show the right values.
- [ ] **Display range** clips the chart and updates the unit.
- [ ] **Window size** (kinetics only) shifts the `maxRate` line; min 3, max half the row count is enforced.
- [ ] **Regression models:** switch through linear, polynomial, logarithmic, exponential, Michaelis-Menten. R² and the coefficient table update, and the fitted curve is drawn.
- [ ] **Normalize (remove blank)** re-bases the Y axis.
- [ ] **Split by sources** produces one section per `Value:n` column, coloured by the sequential ramp (`--ramp-1..10`), not a cycled rainbow.
- [ ] **Sentinel tokens:** a CSV carrying `OVFL`, `NONE` or `INF` in a value column loads without poisoning the fit, the JSON export, or an Excel cell.
- [ ] **Unitless measurement:** the Y axis falls back to the measurement name rather than printing an empty unit.

## 7. Calibration & export
- [ ] **Kinetics calibration:** export coefficients against `maxRate` / `Linear` slope / `Sat` / time-to-saturation → JSON in `json/kinetics/`.
- [ ] **Point calibration:** export against a chosen time point → `json/point/`.
- [ ] **Turn calibration:** a Turn file shows the per-Turn concentration table (no time-point controls) and exports `Concentration,Value`; the resulting JSON records `x_axis:'turn'` and omits `time`.
- [ ] **Quick concentration:** evaluate a saved curve at one measured value — no CSV selected. The answer matches the same curve applied in the chart.
- [ ] **Excel formula export:** paste the emitted formula into Excel; it reproduces the app's number for the same input. Check **all five** models — `math_ops` fits, `evaluate_curve` and `excel_formula` must agree.
- [ ] **Excel calibration export:** the workbook opens with a **native** chart, not a pasted image.
- [ ] **Calibrated JSON table** lists the new file immediately.

## 8. Reports
- [ ] Create, rename, copy and delete a report subject.
- [ ] Export an analysis to a subject; the saved HTML opens standalone and renders its chart.
- [ ] Excel report export.

## 9. Localization & interface style
- [ ] Switch `ui_language` through **all seven** (en, vi, zh, fr, ja, ru, ko). No raw translation keys, no clipped buttons, no overflowing labels.
- [ ] Technical terms stay in English (mode names, units, Absorbance, maxRate, rSquared, CSV/JSON/Excel).
- [ ] A missing key falls back to English rather than showing the key.
- [ ] Switch `ui_style` between `instrument` and `classic`. No flash of the wrong style on load; charts use the matching palette; the session strip is off in classic and the timer widget returns.
- [ ] The Windows splash launcher follows the same setting.

## 10. Accessibility (WCAG 2.2 AA — a published claim)
- [ ] **Keyboard only:** reach and operate every control, including the skip link, the collapsibles, and an overflowing panel's scroll.
- [ ] **Screen reader:** errors are announced; each chart has a name and a data table carrying the same numbers.
- [ ] **Sortable headers** expose `aria-sort` and are operable as buttons.
- [ ] **Contrast** holds in both themes and both interface styles.
- [ ] **Reduced motion:** the session strip, splash and countdowns respect the opt-out.
- [ ] Installers: verify the non-graphical routes in [`docs/accessibility/INSTALLERS.md`](../docs/accessibility/INSTALLERS.md).

## 11. AI assistant
- [ ] Ask a navigation question; a matched guide launches the spotlight walkthrough.
- [ ] 👍/👎 an answer. A rated **local guide** match changes that guide's weight; **Reset learning** clears it; **Export feedback** downloads the log.
- [ ] With `ai_feedback_enabled` off, the rating row is hidden and the route no-ops.
- [ ] Not activated + no `GROQ_API_KEY` → the widget says "Not activated" instead of failing silently.

## 12. Music widget (online only)
- [ ] With `music_enabled` on and a connection, the 🎧 widget mounts; going offline unmounts it.
- [ ] Radio plays; the YouTube pane is **visible** and ≥200 px.
- [ ] Queue survives an app restart (it lives in `music_queue.json`, not `localStorage`).

## 13. Licensing & updates
- [ ] Activate with a valid token. Copy the install folder to a second machine → refused (hardware lock).
- [ ] Revoked seat → `license_blocked.html`; banned account → `license_banned.html`; grace lapsed offline → `license_reverify.html`.
- [ ] **Update:** apply an in-app update. Check the progress SSE, the relaunch, and that `data/`, `json/`, `report/` and `log/` survive.
- [ ] After the update, no `_update_*` scratch files are left in the data root.
- [ ] The uninstaller shipped with the **new** build is the one present after an update.
- [ ] Uninstall releases the licence seat (the next machine activates).

## 14. Input validation
- [ ] POST `/export_data` with a string where `threshold_val` expects a number → **400**, "Invalid value".
- [ ] POST `/run_script` with no `base_name` → "Missing required field".
- [ ] POST a bare JSON array to any `@validate_json` route → **400**, never a 500.
- [ ] POST `/shutdown` with a malformed body → **400** and the app is **still running** (validation must precede the SIGTERM thread).
- [ ] A state-changing request with a foreign `Origin` is refused by the request guard.
