const _escHtml = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const _esc = s => _escHtml(String(s)).replace(/"/g, '&quot;').replace(/'/g, "\\'");

// Folder name reserved by the data-archive feature (mirrors RESERVED_ARCHIVE_FOLDER
// in src/file_path.py). Loose files at the data root are stashed under
// data/<this>/ when the app is uninstalled/updated, so a user subfolder of this
// name would collide. Folder create/rename forbid it (case-insensitive).
const RESERVED_DATA_FOLDER = 'root';
function isReservedDataFolderName(name) {
    return (name || '').trim().toLowerCase() === RESERVED_DATA_FOLDER;
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
        _populateFolderSelect('cdc-subfolder-select', folders, true);
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
                     onclick="selectDataFolder('${_esc(f.name)}', this.dataset.path)"
                     data-hint="${_escHtml(f.path)}"><span class="folder-item-name">${_escHtml(f.name)}</span><button type="button" class="folder-item-rename" data-hint="Rename folder" onclick="event.stopPropagation(); renameDataFolder('${_esc(f.name)}', this.closest('.folder-item').dataset.path)"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg></button><button type="button" class="folder-item-delete" data-hint="Delete folder" onclick="event.stopPropagation(); deleteDataFolder('${_esc(f.name)}', this.closest('.folder-item').dataset.path)"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg></button></div>`;
    }).join('');
}

// Delete a data subfolder (and its contents) after confirmation. Refreshes the
// folder lists and, if the deleted folder was the active directory, falls back
// to the data root.
async function deleteDataFolder(name, path) {
    // Fetch the CSV files in the folder so the confirmation can list what will be removed.
    let files = [];
    try {
        const res = await fetch('/browse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: 'path=' + encodeURIComponent(path)
        });
        const d = await res.json();
        if (d.status === 'success') files = d.files || [];
    } catch (e) { /* fall back to a generic confirmation if listing fails */ }

    const fileListHtml = files.length
        ? `<p style="margin:8px 0 4px;">The following ${files.length} CSV file${files.length > 1 ? 's' : ''} will be permanently deleted:</p>
           <ul style="text-align:left; max-height:160px; overflow:auto; margin:0; padding:6px 6px 6px 22px; border:1px solid #e5e7eb; border-radius:6px; font-size:0.85em;">
               ${files.map(f => `<li>${_escHtml(f)}</li>`).join('')}
           </ul>`
        : `<p style="margin:8px 0;">This folder contains no CSV files.</p>`;

    const result = await Swal.fire({
        title: 'Delete folder?',
        html: `<div style="text-align:left;">Delete <b>"${_escHtml(name)}"</b>? This cannot be undone.${fileListHtml}</div>`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Delete',
        confirmButtonColor: '#ef4444'
    });
    if (!result.isConfirmed) return;

    try {
        if (typeof window.showSpinner === 'function') window.showSpinner();
        const response = await fetch('/delete_data_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
        });
        const data = await response.json();
        if (data.status !== 'success') throw new Error(data.message || 'Delete failed');

        const wasCurrent = AppState.currentDirectory &&
            (AppState.currentDirectory === path ||
             AppState.currentDirectory.replace(/\\\\/g, '\\') === path);
        await loadDataFolders();
        if (wasCurrent && typeof DATA_ROOT !== 'undefined') {
            await updateDirectory(DATA_ROOT, true);
        }

        if (getBtnChecked("no-swal-checkbox")) {
            console.log("Folder deleted successfully:", data.message);
        } else {
            Swal.fire('Folder deleted', data.message || `Deleted "${name}".`, 'success');
        }
    } catch (e) {
        Swal.fire('Error', e.message, 'error');
    } finally {
        if (typeof window.hideSpinner === 'function') window.hideSpinner();
    }
}

// Rename a data subfolder via a prompt. Refreshes the folder lists and, if the
// renamed folder was the active directory, re-points it to the new path.
async function renameDataFolder(name, path) {
    const result = await Swal.fire({
        title: 'Rename folder',
        input: 'text',
        inputValue: name,
        inputLabel: 'New folder name',
        showCancelButton: true,
        confirmButtonText: 'Rename',
        inputValidator: (value) => {
            const v = (value || '').trim();
            if (!v) return 'Folder name is required';
            if (/[\\/]|\.\./.test(v)) return 'Name cannot contain slashes or "..".';
            if (v.startsWith('.') || v.startsWith('_')) return 'Name cannot start with "." or "_".';
            if (isReservedDataFolderName(v)) return `"${RESERVED_DATA_FOLDER}" is a reserved folder name.`;
            return null;
        }
    });
    if (!result.isConfirmed) return;
    const newName = result.value.trim();
    if (newName === name) return;

    try {
        if (typeof window.showSpinner === 'function') window.showSpinner();
        const response = await fetch('/rename_data_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, new_name: newName })
        });
        const data = await response.json();
        if (data.status !== 'success') throw new Error(data.message || 'Rename failed');

        const wasCurrent = AppState.currentDirectory &&
            (AppState.currentDirectory === path ||
             AppState.currentDirectory.replace(/\\\\/g, '\\') === path);
        await loadDataFolders();
        if (wasCurrent && data.path) {
            await updateDirectory(data.path, true);
            if (typeof saveUserSetting === 'function') saveUserSetting('default_subfolder', newName);
        }

        if (getBtnChecked("no-swal-checkbox")) {
            console.log("Folder renamed successfully:", data.message);
        } else {
            Swal.fire('Folder renamed', data.message || `Renamed "${name}" to "${newName}".`, 'success');
        }
    } catch (e) {
        Swal.fire('Error', e.message, 'error');
    } finally {
        if (typeof window.hideSpinner === 'function') window.hideSpinner();
    }
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
    // Re-derive the available source counts for the newly selected folder before
    // rendering, so #num-sources (and the file table) reflect the new data.
    if (typeof refreshNumSourcesOptions === 'function') {
        await refreshNumSourcesOptions(path);
    }
    await updateDirectory(path, true);
    if (typeof window.hideSpinner === 'function') window.hideSpinner();
    if (typeof saveUserSetting === 'function') saveUserSetting('default_subfolder', name);
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
            const filePath = AppState.currentDirectory + DELIMITER + fileName;

            let response;
            try {
                response = await fetch('/get_headers?file=' + encodeURIComponent(filePath));
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

            if (!data.headers) {
                return false;
            }

            const isMeasHeader = checkMeasHeader(data.headers);

            if (AppState.currentMeasurementMode === "kinetics" || AppState.currentMeasurementMode === "point") {
                return isMeasHeader;
            }

            if (AppState.currentMeasurementMode === "calibrate") {
                const cal_type = calDiv.getAttribute('data-value');
                const expected = cal_type === "kinetics" ? cal_headers_kinetics : cal_headers_point;
                return arraysEqual(data.headers, expected);
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

function buildMeasHeaders() {
    const headers = ["Timestamp"];
    for (let i = 1; i <= AppState.numSources; i++) {
        headers.push(`Value:${i}`);
    }
    return headers;
}

function checkMeasHeader(headers) {
    if (getBtnChecked("filter-source")) {
        const expectedHeaders = buildMeasHeaders();
        return arraysEqual(headers, expectedHeaders);
    } else {
        const meas_headers = /^\s*Timestamp\s*Value:\d+(?:\s*Value:\d+)*\s*$/;
        const headerString = headers.join('');
        return meas_headers.test(headerString);
    }
}

function arraysEqual(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
}

function updateJSONTable(files) {
    let html = '<tr><th>Calibrated JSON</th><th colspan="3">Action</th></tr>';
    if (files && files.length > 0) {
        const limit = (typeof USER_SETTINGS !== 'undefined' && USER_SETTINGS.max_json_rows > 0) ? USER_SETTINGS.max_json_rows : Infinity;
        const shown = files.slice(0, limit);
        shown.forEach(file => {
            const isSelected = file === AppState.currentJSON ? ' class="selected"' : '';
            html += `<tr${isSelected}><td>${_escHtml(file)}</td><td><button onclick="selectFile('${_esc(file)}', this, '#json-table')">✅ Select</button></td><td><button onclick="deleteFile('${_esc(file)}', this, '#json-table')">❌ Delete</button></td><td><button onclick="editFile('${_esc(file)}', this, '#json-table')">✏️ Edit</button></td></tr>`;
        });
        if (files.length > shown.length) {
            html += `<tr><td colspan="4" style="text-align:center;color:#888;font-style:italic;padding:4px;">+${files.length - shown.length} more — adjust limit in Settings ⚙️</td></tr>`;
        }
    } else {
        html += '<tr><td colspan="2">No Calibrated JSON is available.</td></tr>';
    }
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
        subjects.forEach(subject => {
            const isSelected = subject === AppState.currentReportSubject ? ' class="selected"' : '';
            html += `<tr${isSelected}><td>${_escHtml(subject)}</td><td><button onclick="selectFile('${_esc(subject)}', this)">📁 Select Subject</button></td><td><button onclick="deleteReportSubject('${_esc(subject)}', this)">❌ Delete</button></td><td><button onclick="editReportSubject('${_esc(subject)}', this)">✏️ Edit</button></td></tr>`;
        });
    } else {
        html += '<tr><td colspan="4">No report subjects found.</td></tr>';
    }
    document.getElementById("file-table").innerHTML = html;
    const searchInput = document.getElementById('file-search');
    if (searchInput && searchInput.value) {
        filterTable('file-table', searchInput.value);
    }
}

function updateFileTable(files, deselect) {
    let html = '<tr><th>File Name</th><th colspan="3">Action</th></tr>';

    return filterFiles(files).then((filteredFiles) => {
        if (filteredFiles && filteredFiles.length > 0) {
            const limit = (typeof USER_SETTINGS !== 'undefined' && USER_SETTINGS.max_csv_rows > 0) ? USER_SETTINGS.max_csv_rows : Infinity;
            const shown = filteredFiles.slice(0, limit);
            shown.forEach(file => {
                const isSelected = file === AppState.currentFile ? ' class="selected"' : '';
                html += `<tr${isSelected}><td>${_escHtml(file)}</td><td><button onclick="selectFile('${_esc(file)}', this)">✅ Select</button></td><td><button onclick="deleteFile('${_esc(file)}', this)">❌ Delete</button></td><td><button onclick="editFile('${_esc(file)}', this)">✏️ Edit</button></td></tr>`;
            });
            if (filteredFiles.length > shown.length) {
                html += `<tr><td colspan="4" style="text-align:center;color:#888;font-style:italic;padding:4px;">+${filteredFiles.length - shown.length} more — adjust limit in Settings ⚙️</td></tr>`;
            }
        } else {
            html += '<tr><td colspan="4">No CSV files found in the directory.</td></tr>';
        }
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

function updateFileDisplay(curFile) {
    const displayElement = document.getElementById('selected-file-display');
    if (curFile) {
        displayElement.textContent = `Selected File: ${curFile}`;
        if (AppState.currentMeasurementMode === 'report') {
            onReportFolderSelected(curFile);
        }
    } else {
        displayElement.textContent = `No file selected`;
    }
}


function fetchJSON(jsonFile, callback) {
    $.get('/get_json_content', {
        json_name: jsonFile,
        mode: AppState.currentMeasurementMode,
        numSources: AppState.numSources
    }, function (response) {
        callback(response.json);
    }).fail(function (xhr, status, error) {
        console.error("fetchJSON failed:", error);
        callback(null);
    });
}

// Poll /api/current_output until the backend has finished writing the marker.
// While a reading session is starting, current_output.txt may not exist yet
// (HTTP 404) or may be present but empty (HTTP 204) — both mean "still writing".
// Only a 200 with exists:true and a filename counts as ready. Returns the parsed
// payload once ready, or null after `retries` attempts (~retries * intervalMs ms).
async function fetchCurrentOutputUntilReady({ retries = 20, intervalMs = 250 } = {}) {
    for (let attempt = 0; attempt < retries; attempt++) {
        try {
            const response = await fetch('/api/current_output');
            if (response.status === 200) {
                const data = await response.json();
                if (data && data.exists && data.filename) return data;
            }
            // 204 (empty marker) / 404 (not created yet) / other -> backend not done; retry
        } catch (_) {
            // transient network/server hiccup -> retry
        }
        await new Promise(resolve => setTimeout(resolve, intervalMs));
    }
    return null; // gave up: marker never became ready
}

async function browseSavingLocation(changeToCalibrate = false, button = null, path = "") {
    // Temporarily disable the button to prevent multiple clicks
    $(button).prop("disabled", true);
    setTimeout(() => {
        $(button).prop("disabled", false);
    }, 1000); // Re-enable the button after 1 second
    if (button.id === "go-to-exp-btn") {
        blinkingItem("cal-mode-select", 5000);
        blinkingItem("measurement-mode", 5000);
        blinkingItem("file-selection", 5000);
        const dirPath = AppState.exportPath;
        await updateDirectory(dirPath, true, changeToCalibrate);
    } else {
        // Keep the loading circle up for the whole "View live data" attempt: the
        // marker fetch may need to be retried while the backend is still writing
        // current_output.txt, and the target CSV may take a moment to appear in
        // the refreshed table. selectFile() manages the spinner for its own render.
        if (typeof window.showSpinner === 'function') window.showSpinner();
        try {
            // Wait until the backend has finished writing the marker file.
            const data = await fetchCurrentOutputUntilReady();

            if (data) {
                // Use server-provided directory (with trailing separator if needed)
                const dirPath = data.dir || data.dir_with_sep;
                const fileName = data.filename;

                await updateDirectory(dirPath, true, changeToCalibrate);

                // The table is repopulated asynchronously and, while reading, the
                // target CSV may not be listed on the first refresh. Retry locating
                // the row for a short window so the spinner stays up until the file
                // is actually selectable.
                let cell = null;
                for (let attempt = 0; attempt < 10 && !cell; attempt++) {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    const cells = document.querySelectorAll("#file-table tr td");
                    cell = Array.from(cells).find(td => td.textContent.trim() === fileName);
                }

                if (cell) {
                    const row = cell.closest("tr");
                    const btn = row.querySelector("button");
                    // Pass the button if present, otherwise the cell, so selectFile
                    // can still find the row to highlight.
                    await selectFile(fileName, btn || cell, "#file-table");
                } else {
                    console.warn(`File "${fileName}" not found in #file-table.`);
                    blinkingItem("file-selection", 5000);
                }
            } else {
                // Marker never became ready (e.g. backend still initialising the
                // CSV, or no reading session) -> fall back to original behavior.
                console.warn("current_output marker not ready; falling back.");
                await updateDirectory(path, true, changeToCalibrate);
                blinkingItem("file-selection", 5000);
            }
        } catch (err) {
            console.error("Error fetching current_output:", err);
            await updateDirectory(path, true, changeToCalibrate);
        } finally {
            if (typeof window.hideSpinner === 'function') window.hideSpinner();
        }
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

    // Scroll so the element's centre aligns with the viewport's centre, then keep
    // re-asserting that alignment for a short window. This defeats the race where a
    // one-shot smooth scroll is invalidated mid-flight by concurrent reflows — the
    // 500ms live-update loop (updateDirectory + drawMeasurementChart) and async
    // Chart.js canvas resizes shift content above the target after the scroll's
    // destination offset was computed, leaving the section off-screen.
    //
    // The first assertion is smooth for feel; follow-up corrections are instant and
    // only fire when the element has actually drifted past `tolerance`, so a settled
    // page produces no jitter.
    const TOLERANCE_PX = 24;        // distance from viewport centre treated as "centred"
    const CORRECT_EVERY_MS = 150;   // how often to re-check during the guard window
    const SMOOTH_SETTLE_MS = 450;   // let the smooth animation finish before correcting
    const GUARD_FOR_MS = 1400;      // span ~2-3 live-update ticks plus the chart draw

    const isCentred = () => {
        const rect = target.getBoundingClientRect();
        const targetCentre = rect.top + rect.height / 2;
        return Math.abs(targetCentre - window.innerHeight / 2) <= TOLERANCE_PX;
    };

    const scrollToElement = () => {
        // Double rAF ensures Chart.js (and any other rAF-deferred renderers) have
        // committed their layout before scrollIntoView reads element positions.
        requestAnimationFrame(() => requestAnimationFrame(() => {
            target.scrollIntoView({ behavior: "smooth", block: "center" });

            const deadline = performance.now() + GUARD_FOR_MS;
            const reassert = () => {
                if (!isVisible(target)) return;     // navigated away / re-hidden
                if (!isCentred()) {
                    // Reflow pushed it away — snap back instantly (no animation to
                    // restart, so it can't be invalidated the same way).
                    target.scrollIntoView({ behavior: "auto", block: "center" });
                }
                if (performance.now() < deadline) {
                    setTimeout(reassert, CORRECT_EVERY_MS);
                }
            };
            setTimeout(reassert, SMOOTH_SETTLE_MS);
        }));
    };

    // If already visible, scroll now; pending layout work is handled by the
    // deferred measurement and the re-assert guard above.
    if (isVisible(target)) {
        scrollToElement();
        return;
    }

    // Poll every 100ms until element becomes visible, but cancel after `duration` ms
    // to prevent stale intervals from firing in a later session or context.
    const interval = setInterval(() => {
        if (isVisible(target)) {
            scrollToElement();
            clearInterval(interval);
        }
    }, 100);
    setTimeout(() => clearInterval(interval), duration);
}