const _escHtml = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
const _escAttr = s => _escHtml(String(s));
const _esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, "\\'");

// ── File identity (Measurement / Unit / ConcenUnit) — badge + CSV↔JSON match ──
// A measurement CSV is paired with a calibration JSON to derive concentration; the
// pair must share the same Measurement, Unit and ConcenUnit. Identity is recorded
// per file (CSV metadata / JSON for_meas+meas_unit+concen_unit) and surfaced both as
// a badge in the tables and as a gate on the Select buttons.
const DEFAULT_CONCEN_UNIT_JS = 'ng/µL';

// Normalize an identity value: blank or the "NONE" placeholder → null (a wildcard
// when matching); else the trimmed string. Mirrors _norm_identity_value in file_path.py.
function _normIdent(v) {
    if (v === undefined || v === null) return null;
    const s = String(v).trim();
    if (s === '' || s.toUpperCase() === 'NONE') return null;
    return s;
}

// Normalize the loaded CSV's metadata into an identity object. `axis`
// ('turn'/'time') is the loaded file's X axis (point mode); it gates pairing
// against a calibration curve of the same kind.
function csvIdentityFromMeta(meta) {
    if (!meta) return null;
    const calMode = (typeof AppState !== 'undefined') && AppState.currentMeasurementMode === 'calibrate';
    const unit = calMode ? meta['MeasUnit'] : (meta['Unit'] || meta['MeasUnit']);
    return {
        measurement: _normIdent(meta['Measurement']),
        unit: _normIdent(unit),
        concen_unit: (meta['ConcenUnit'] && String(meta['ConcenUnit']).trim()) || DEFAULT_CONCEN_UNIT_JS,
        axis: (typeof AppState !== 'undefined' && AppState.xAxis) ? AppState.xAxis : null,
    };
}

// Normalize a calibration JSON's content into an identity object. `axis`:
// 'turn' for a turn-based point curve (`x_axis:'turn'`), 'time' for a time-based
// point curve (`time`/`time-unit`), null for kinetics/legacy (a wildcard).
function jsonIdentityFromContent(json) {
    if (!json) return null;
    let axis = null;
    if (json['x_axis'] === 'turn') axis = 'turn';
    else if (json['time-unit'] !== undefined || json['time'] !== undefined) axis = 'time';
    return {
        measurement: _normIdent(json['for_meas']),
        unit: _normIdent(json['meas_unit']),
        concen_unit: (json['concen_unit'] && String(json['concen_unit']).trim()) || DEFAULT_CONCEN_UNIT_JS,
        axis: axis,
    };
}

// Compare a CSV identity with a JSON identity. Measurement/Unit/axis are wildcards
// when absent on either side (legacy JSONs); ConcenUnit is always enforced
// (absent → ng/µL). `axis` blocks pairing a Turn data file with a time-series
// calibration and vice versa.
// Returns {ok, reason} with reason ∈ 'meas' | 'unit' | 'concen' | 'axis' | null.
function identityMatch(csvId, jsonId) {
    if (!csvId || !jsonId) return { ok: true, reason: null };
    if (csvId.measurement && jsonId.measurement && csvId.measurement !== jsonId.measurement)
        return { ok: false, reason: 'meas' };
    if (csvId.unit && jsonId.unit && csvId.unit !== jsonId.unit)
        return { ok: false, reason: 'unit' };
    const cuA = csvId.concen_unit || DEFAULT_CONCEN_UNIT_JS;
    const cuB = jsonId.concen_unit || DEFAULT_CONCEN_UNIT_JS;
    if (cuA !== cuB) return { ok: false, reason: 'concen' };
    if (csvId.axis && jsonId.axis && csvId.axis !== jsonId.axis)
        return { ok: false, reason: 'axis' };
    return { ok: true, reason: null };
}

function identityMismatchLabel(reason) {
    return reason === 'meas' ? 'Measurement'
        : reason === 'unit' ? 'Unit'
        : reason === 'axis' ? 'Turn vs time-series'
        : 'Concentration unit';
}

// Human sentence describing the clash, naming both sides' values.
function identityClashText(csvId, jsonId, reason) {
    if (reason === 'axis') {
        // The one clash that isn't about a metadata value — it is about the kind
        // of measurement. Explain WHY the two cannot be paired.
        return (csvId.axis === 'turn')
            ? "This is a Turn data file — each reading is a discrete turn, with no time axis. "
              + "The chosen calibration curve was built for time-series data: it derives a concentration "
              + "from the signal at a fixed time point, which a Turn file simply does not have. "
              + "Pick a Turn-based calibration curve (one built from Turn standards) instead."
            : "This is a time-series data file recorded over time. The chosen calibration curve is "
              + "Turn-based — each standard is a single turn with no time reference — so it cannot read a "
              + "value at a time point from this file. Pick a time-based calibration curve instead.";
    }
    const field = reason === 'meas' ? 'measurement' : reason === 'unit' ? 'unit' : 'concentration unit';
    const a = reason === 'meas' ? csvId.measurement : reason === 'unit' ? csvId.unit : csvId.concen_unit;
    const b = reason === 'meas' ? jsonId.measurement : reason === 'unit' ? jsonId.unit : jsonId.concen_unit;
    return `The data file's ${field} (${a || '—'}) does not match the calibration curve's ${field} (${b || '—'}). Pick a matching file.`;
}

// Muted identity badge appended after a filename (escaped): Measurement·Unit·ConcenUnit.
function _identityBadge(id) {
    if (!id) return '';
    const parts = [id.measurement || '—', id.unit || '—', id.concen_unit || DEFAULT_CONCEN_UNIT_JS];
    return ` <span class="file-identity">${_escHtml(parts.join('·'))}</span>`;
}

// Disabled Select-button attributes for a row whose identity doesn't match the
// loaded counterpart (tagged with __kind); '' when it matches or none is loaded.
function _selectDisableAttrs(rowId, counterpart) {
    if (!counterpart) return '';
    const m = (counterpart.__kind === 'csv')
        ? identityMatch(counterpart, rowId)   // selected is CSV, row is a JSON
        : identityMatch(rowId, counterpart);  // selected is JSON, row is a CSV
    if (m.ok) return '';
    const msg = (m.reason === 'axis')
        ? "Turn and time-series don't mix: a time calibration derives concentration from the signal at a fixed time point, which a Turn file has no axis for; a Turn calibration expects discrete turns, not a time-series. Pair a Turn file with a Turn calibration, and a time-series file with a time calibration."
        : identityMismatchLabel(m.reason) + ' differs from the selected file — cannot pair';
    return ` disabled title="${_escAttr(msg)}" data-hint="${_escAttr(msg)}"`;
}

// Identity of the loaded counterpart, only in kinetics/point mode (pairing is
// meaningless in calibrate/report). Returns {..., __kind} or null.
function _csvCounterpartForJsonTable() {
    if (typeof AppState === 'undefined') return null;
    if (!['kinetics', 'point'].includes(AppState.currentMeasurementMode)) return null;
    if (!AppState.currentFile || !AppState.metaData) return null;
    const id = csvIdentityFromMeta(AppState.metaData);
    if (id) id.__kind = 'csv';
    return id;
}

function _jsonCounterpartForFileTable() {
    if (typeof AppState === 'undefined') return null;
    if (!['kinetics', 'point'].includes(AppState.currentMeasurementMode)) return null;
    if (!AppState.currentJSON || !AppState.currentJSONcontent) return null;
    const id = jsonIdentityFromContent(AppState.currentJSONcontent);
    if (id) id.__kind = 'json';
    return id;
}

// ── Data-folder collapse toggle ──────────────────────────────────────────────

function toggleFolderList(collapseId, chevronId) {
    const collapse = document.getElementById(collapseId);
    const chevron = document.getElementById(chevronId);
    if (!collapse) return;
    const isNowCollapsed = collapse.classList.toggle('collapsed');
    if (chevron) chevron.classList.toggle('collapsed-chevron', isNowCollapsed);
}

// ── Data-folder picker ──────────────────────────────────────────────────────

async function loadDataFolders() {
    try {
        const res = await fetch('/get_data_folders');
        const data = await res.json();
        const folders = data.folders || [];
        _renderFolderList('data-folder-list', folders);
        _renderFolderList('data-folder-list-top', folders);
        _populateFolderSelect('hid-subfolder-select', folders, true);
        _populateFolderSelect('exp-subfolder-select', folders, false);
    } catch (e) {
        console.error('loadDataFolders error:', e);
    }
}

function _renderFolderList(containerId, folders) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const currentDir = AppState.currentDirectory || '';
    if (folders.length === 0) {
        container.innerHTML = '<div style="color:#999; padding:6px;">No subfolders in data/ yet.</div>';
        return;
    }
    container.innerHTML = folders.map(f => {
        const isSelected = currentDir && (currentDir === f.path || currentDir.replace(/\\\\/g, '\\') === f.path);
        return `<div class="folder-item${isSelected ? ' selected' : ''}"
                     data-path="${_esc(f.path)}"
                     data-name="${_esc(f.name.toLowerCase())}"
                     onclick="selectDataFolder('${_esc(f.name)}', '${_esc(f.path)}')"
                     data-hint="${_escHtml(f.path)}">${_escHtml(f.name)}</div>`;
    }).join('');
}

function _populateFolderSelect(selectId, folders, includeRootOption) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const prev = sel.value;
    if (includeRootOption) {
        sel.innerHTML = '<option value="">— data root (no subfolder) —</option>';
    } else {
        sel.innerHTML = '<option value="" data-path="">— data root —</option>';
    }
    folders.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f.name;
        opt.dataset.path = f.path;
        opt.textContent = f.name;
        sel.appendChild(opt);
    });
    if (prev) sel.value = prev;
}

async function selectDataFolder(name, path) {
    if (typeof window.showSpinner === 'function') window.showSpinner();
    await updateDirectory(path, true);
    if (typeof window.hideSpinner === 'function') window.hideSpinner();
    blinkingItem("file-selection", 5000);
    scrollWhenVisible('file-selection');
}

function updateFolderListSelection(path) {
    ['data-folder-list', 'data-folder-list-top'].forEach(id => {
        const container = document.getElementById(id);
        if (!container) return;
        container.querySelectorAll('div[data-path]').forEach(el => {
            const elPath = el.dataset.path.replace(/\\\\/g, '\\');
            el.classList.toggle('selected', elPath === path || el.dataset.path === path);
        });
    });
}

function filterDataFolderList(listId, query) {
    const container = document.getElementById(listId);
    if (!container) return;
    const lq = query.toLowerCase();
    container.querySelectorAll('div[data-name]').forEach(el => {
        el.style.display = el.dataset.name.includes(lq) ? '' : 'none';
    });
}

// Keep browseDirectory as an alias so any existing callers still work.
function browseDirectory(blinkItem = false) {
    loadDataFolders();
    if (blinkItem) blinkingItem("file-selection", 5000);
}

async function filterFiles(files) {
    const checks = await Promise.all(
        files.map(async (fileName) => {
            let response;
            try {
                response = await fetch('/get_headers?file=' + encodeURIComponent(fileName));
            } catch (networkErr) {
                console.warn(`Network error for ${fileName}:`, networkErr);
                return false;
            }

            let data;
            try {
                data = await response.json();
            } catch (jsonErr) {
                console.warn(`Invalid JSON for ${fileName}:`, jsonErr);
                return false;
            }

            if (!response.ok) {
                const friendlyMsg = data.error ?? `Server error ${response.status}`;
                console.info(`Header check failed (${response.status}) for ${fileName}: ${friendlyMsg}`);
                return { error: friendlyMsg };
            }

            const cal_headers_kinetics = ["Concentration", "maxRate", "Slope", "Sat", "Time To Sat"];
            const cal_headers_point = ["Concentration", "Value", "TimePoint"];
            // Turn-based point calibration: each Turn is a standard, no TimePoint column.
            const cal_headers_point_turn = ["Concentration", "Value"];

            if (!data.headers) {
                return false;
            }

            const isMeasHeader = checkMeasHeader(data.headers);

            if (AppState.currentMeasurementMode === "kinetics" || AppState.currentMeasurementMode === "point") {
                return isMeasHeader;
            }

            if (AppState.currentMeasurementMode === "calibrate") {
                const cal_type = calDiv.getAttribute('data-value');
                if (cal_type === "kinetics") {
                    return arraysEqual(data.headers, cal_headers_kinetics);
                }
                // Point calibration accepts both the time-based (…,TimePoint) and
                // turn-based (Concentration,Value) tables.
                return arraysEqual(data.headers, cal_headers_point)
                    || arraysEqual(data.headers, cal_headers_point_turn);
            }

            if (AppState.currentMeasurementMode === "report") {
                return true;
            }

            return false;
        })
    );

    const filteredFiles = files.filter((_, idx) => {
        const result = checks[idx];
        return result === true;
    });

    return filteredFiles;
}

function checkMeasHeader(headers) {
    // The X column is Timestamp, or — point mode only — a Turn index. Kinetics
    // never reads Turn files, so they stay filtered out there.
    const allowTurn = AppState.currentMeasurementMode === 'point';
    const xOk = headers[0] === 'Timestamp' || (allowTurn && headers[0] === 'Turn');
    if (!xOk) return false;

    const valueHeaders = headers.slice(1);
    if (getBtnChecked("filter-source")) {
        const expectedValues = [];
        for (let i = 1; i <= AppState.numSources; i++) expectedValues.push(`Value:${i}`);
        return arraysEqual(valueHeaders, expectedValues);
    }
    // At least one Value:N column, nothing else.
    return valueHeaders.length > 0 && valueHeaders.every(h => /^\s*Value:\d+\s*$/.test(h));
}

function arraysEqual(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
}

function updateJSONTable(files) {
    if (files) AppState.jsonNames = files.slice();
    let html = '<tr><th>Calibrated JSON</th><th colspan="3">Action</th></tr>';
    if (files && files.length > 0) {
        const counterpart = _csvCounterpartForJsonTable();  // loaded CSV (kinetics/point)
        files.slice().sort((a, b) => a.localeCompare(b)).forEach(file => {
            const isSelected = file === AppState.currentJSON ? ' class="selected"' : '';
            const ef = _escAttr(file);
            const et = _escHtml(file);
            const badge = _identityBadge(AppState.jsonIdentity && AppState.jsonIdentity[file]);
            const disableAttrs = _selectDisableAttrs(AppState.jsonIdentity && AppState.jsonIdentity[file], counterpart);
            html += `<tr${isSelected}><td>${et}${badge}</td><td><button${disableAttrs} onclick="selectFile(${_escAttr(JSON.stringify(file))}, this, '#json-table')">✅ Select</button></td><td><button onclick="deleteFile(${_escAttr(JSON.stringify(file))}, this, '#json-table')">❌ Delete</button></td><td><button onclick="editFile(${_escAttr(JSON.stringify(file))}, this, '#json-table')">✏️ Edit</button></td></tr>`;
        })
    } else {
        html += '<tr><td colspan="2">No Calibrated JSON is available.</td></tr>';
    }
    // The rows land now, so any skeleton the fetch put up has done its job.
    window.hideSkeleton?.('json-table');
    document.getElementById("json-table").innerHTML = html;
    const searchInput = document.getElementById('json-search');
    if (searchInput && searchInput.value) {
        filterTable('json-table', searchInput.value);
    }
}

function updateReportTable(subjects) {
    let html = '<tr><th id="file-table-header-name">Folder Name</th><th colspan="3">Action</th></tr>';
    document.getElementById("file-search").placeholder = "Search subject folders...";
    if (subjects && subjects.length > 0) {
        subjects.slice().sort((a, b) => a.localeCompare(b)).forEach(subject => {
            const isSelected = subject === AppState.currentReportSubject ? ' class="selected"' : '';
            const et = _escHtml(subject);
            html += `<tr${isSelected}><td>${et}</td><td><button onclick="selectFile(${_escAttr(JSON.stringify(subject))}, this)">📁 Select Subject</button></td><td><button onclick="deleteReportSubject(${_escAttr(JSON.stringify(subject))}, this)">❌ Delete</button></td><td><button onclick="editReportSubject(${_escAttr(JSON.stringify(subject))}, this)">✏️ Edit</button></td></tr>`;
        });
    } else {
        html += '<tr><td colspan="4">No report subjects found.</td></tr>';
    }
    // Report mode renders into the same table, so it clears the skeleton too.
    window.hideSkeleton?.('file-table');
    document.getElementById("file-table").innerHTML = html;
    const searchInput = document.getElementById('file-search');
    if (searchInput && searchInput.value) {
        filterTable('file-table', searchInput.value);
    }
}

function filterTable(tableId, query) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const trs = table.getElementsByTagName("tr");
    const lowerQuery = query.toLowerCase();
    for (let i = 1; i < trs.length; i++) {
        const tds = trs[i].getElementsByTagName("td");
        if (tds.length > 0) {
            const textValue = tds[0].textContent || tds[0].innerText;
            if (textValue.toLowerCase().indexOf(lowerQuery) > -1) {
                trs[i].style.display = "";
            } else {
                trs[i].style.display = "none";
            }
        }
    }
}

function updateFileTable(files, deselect = false) {
    // Nothing to render: drop any skeleton rather than leave it up forever.
    if (!files) window.hideSkeleton?.('file-table');
    if (files) AppState.fileNames = files.slice();
    let html = '<tr><th>File Name</th><th colspan="3">Action</th></tr>';
    if (files) {
        filterFiles(files).then((filteredFiles) => {
            const counterpart = _jsonCounterpartForFileTable();  // loaded JSON (kinetics/point)
            if (filteredFiles && filteredFiles.length > 0) {
                filteredFiles.slice().sort((a, b) => a.localeCompare(b)).forEach(file => {
                    const isSelected = file === AppState.currentFile ? ' class="selected"' : '';
                    const et = _escHtml(file);
                    const badge = _identityBadge(AppState.fileIdentity && AppState.fileIdentity[file]);
                    const disableAttrs = _selectDisableAttrs(AppState.fileIdentity && AppState.fileIdentity[file], counterpart);
                    html += `<tr${isSelected}><td>${et}${badge}</td><td><button${disableAttrs} onclick="selectFile(${_escAttr(JSON.stringify(file))}, this)">✅ Select</button></td><td><button onclick="deleteFile(${_escAttr(JSON.stringify(file))}, this)">❌ Delete</button></td><td><button onclick="editFile(${_escAttr(JSON.stringify(file))}, this)">✏️ Edit</button></td></tr>`;
                });
            } else {
                html += '<tr><td colspan="3">No CSV files is available.</td></tr>';
            }
            // Cleared here, not when the fetch resolves: filterFiles() makes
            // its own round trips, so the real rows only exist at this line.
            window.hideSkeleton?.('file-table');
            document.getElementById("file-table").innerHTML = html;
            const searchInput = document.getElementById('file-search');
            if (searchInput && searchInput.value) {
                filterTable('file-table', searchInput.value);
            }
            if (deselect) {
                AppState.currentFile = null;
                $toggleQueryClass("#file-table tr", "selected", false);
                updateFileDisplay(AppState.currentFile);
            }
        });
    }
}

function updateFileDisplay(curFile) {
    const displayElement = document.getElementById('selected-file-display');
    if (curFile) {
        displayElement.textContent = `Selected File: ${curFile}`;
        if (AppState.currentMeasurementMode === 'report') {
            if (typeof onReportFolderSelected === 'function') onReportFolderSelected(curFile);
        }
    } else {
        displayElement.innerHTML = `No file selected`;
    }
}

async function fetchJSONContent(jsonFile, callback) {
    try {
        const url = `/get_json_content?json_name=${encodeURIComponent(jsonFile)}&mode=${encodeURIComponent(AppState.currentMeasurementMode)}&numSources=${encodeURIComponent(AppState.numSources)}`;
        const data = await fetchJSON(url);
        callback(data.json);
    } catch (error) {
        console.error("Error fetching JSON content:", error);
        callback(null);
    }
}

function browseSavingLocation(deselect, changeToCalibrate = false, button = null) {
    // Temporarily disable the button to prevent multiple clicks
    if (button) button.disabled = true;
    setTimeout(() => {
        if (button) button.disabled = false;
    }, 1000); // Re-enable the button after 1 second
    deselectFile();
    deselectFile("#json-table");
    if (button?.id === "go-to-exp-btn") {
        blinkingItem("cal-mode-select", 5000);
        blinkingItem("measurement-mode", 5000);
        blinkingItem("file-selection", 5000);
        updateDirectory(deselect, changeToCalibrate);
    } else {
        fetch('/api/current_output')
            .then(response => {
                if (!response.ok) {
                    // no marker or server error -> fallback
                    return { exists: false };
                }
                return response.json();
            })
            .then(data => {
                if (data && data.exists) {
                    // Use server-provided directory (with trailing separator if needed)
                    const fileName = data.filename;

                    updateDirectory(deselect, changeToCalibrate);

                    // Wait for the table to refresh/populate, then select the row's button
                    setTimeout(() => {
                        // find a TD whose text exactly equals the filename
                        const cells = document.querySelectorAll("#file-table tr td");
                        const cell = Array.from(cells).find(td => td.textContent.trim() === fileName);

                        if (cell) {
                            const row = cell.closest("tr");
                            const btn = row.querySelector("button");

                            if (btn) {
                                selectFile(fileName, btn, "#file-table");
                            } else {
                                // fallback: pass the cell element so selectFile still finds the row to highlight
                                selectFile(fileName, cell, "#file-table");
                            }
                        } else {
                            console.warn(`File "${fileName}" not found in #file-table.`);
                        }
                    }, 500); // adjust delay if your table takes longer to populate
                } else {
                    // no recorded path -> fallback to original behavior
                    updateDirectory(deselect, changeToCalibrate);
                    blinkingItem("file-selection", 5000);
                }
            })
            .catch(err => {
                console.error("Error fetching current_output:", err);
                updateDirectory(deselect, changeToCalibrate);
            });
    }
}

function blinkingItem(id, timeOut = 5000) {
    const element = document.getElementById(id);
    if (!element) return;

    element.focus();
    element.classList.add('blinking');

    if (timeOut) {
        setTimeout(() => {
            element.classList.remove('blinking');
        }, timeOut);
    }
}

function scrollWhenVisible(elementId, duration = 500) {
    const target = document.getElementById(elementId);
    if (!target) return;

    // Helper to check if element is visible
    const isVisible = el =>
        el.offsetParent !== null && window.getComputedStyle(el).display !== "none";

    // Scroll smoothly to the element
    const scrollToElement = () => {
        const targetTop = target.getBoundingClientRect().top + window.scrollY;
        window.scrollTo({ top: targetTop, behavior: "smooth" });
    };

    // If visible, scroll immediately
    if (isVisible(target)) {
        scrollToElement();
        return;
    }

    // Poll every 100ms until element becomes visible
    const interval = setInterval(() => {
        if (isVisible(target)) {
            scrollToElement();
            clearInterval(interval);
        }
    }, 100);
}