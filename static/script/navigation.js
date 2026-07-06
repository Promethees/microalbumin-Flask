const _escHtml = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const _esc = s => _escHtml(String(s)).replace(/"/g, '&quot;').replace(/'/g, "\\'");
// Escape a string for use inside a double-quoted HTML attribute value.
const _attr = s => _escHtml(String(s)).replace(/"/g, '&quot;');

// Folder name reserved by the data-archive feature (mirrors RESERVED_ARCHIVE_FOLDER
// in src/file_path.py). Loose files at the data root are stashed under
// data/<this>/ when the app is uninstalled/updated, so a user subfolder of this
// name would collide. Folder create/rename forbid it (case-insensitive).
const RESERVED_DATA_FOLDER = 'root';
function isReservedDataFolderName(name) {
    return (name || '').trim().toLowerCase() === RESERVED_DATA_FOLDER;
}

// ── File identity (Measurement / Unit / ConcenUnit) — badge + CSV↔JSON match ──
// A measurement CSV is paired with a calibration JSON to derive concentration. The
// pair must share the same Measurement, Unit and ConcenUnit. Identity is recorded
// per file (CSV metadata / JSON for_meas+meas_unit+concen_unit) and surfaced both as
// a badge in the tables and as a gate on the Select buttons. See Rule.md §2.10.
const DEFAULT_CONCEN_UNIT_JS = 'ng/µL';

// Normalize an identity value: blank or the "NONE" placeholder → null (a wildcard
// when matching); else the trimmed string. Mirrors _norm_identity_value in file.py.
function _normIdent(v) {
    if (v === undefined || v === null) return null;
    const s = String(v).trim();
    if (s === '' || s.toUpperCase() === 'NONE') return null;
    return s;
}

// Normalize the loaded CSV's metadata into an identity object.
function csvIdentityFromMeta(meta) {
    if (!meta) return null;
    const calMode = (typeof AppState !== 'undefined') && AppState.currentMeasurementMode === 'calibrate';
    const unit = calMode ? meta['MeasUnit'] : (meta['Unit'] || meta['MeasUnit']);
    return {
        measurement: _normIdent(meta['Measurement']),
        unit: _normIdent(unit),
        concen_unit: (meta['ConcenUnit'] && String(meta['ConcenUnit']).trim()) || DEFAULT_CONCEN_UNIT_JS,
    };
}

// Normalize a calibration JSON's content into an identity object.
function jsonIdentityFromContent(json) {
    if (!json) return null;
    return {
        measurement: _normIdent(json['for_meas']),
        unit: _normIdent(json['meas_unit']),
        concen_unit: (json['concen_unit'] && String(json['concen_unit']).trim()) || DEFAULT_CONCEN_UNIT_JS,
    };
}

// Compare a CSV identity with a JSON identity. Measurement/Unit are wildcards when
// absent on either side (legacy JSONs); ConcenUnit is always enforced (absent → ng/µL).
// Returns {ok, reason} with reason ∈ 'meas' | 'unit' | 'concen' | null.
function identityMatch(csvId, jsonId) {
    if (!csvId || !jsonId) return { ok: true, reason: null };
    if (csvId.measurement && jsonId.measurement && csvId.measurement !== jsonId.measurement)
        return { ok: false, reason: 'meas' };
    if (csvId.unit && jsonId.unit && csvId.unit !== jsonId.unit)
        return { ok: false, reason: 'unit' };
    const cuA = csvId.concen_unit || DEFAULT_CONCEN_UNIT_JS;
    const cuB = jsonId.concen_unit || DEFAULT_CONCEN_UNIT_JS;
    if (cuA !== cuB) return { ok: false, reason: 'concen' };
    return { ok: true, reason: null };
}

// Short human reason for a disabled Select button / mismatch error.
function identityMismatchLabel(reason) {
    return reason === 'meas' ? 'Measurement' : reason === 'unit' ? 'Unit' : 'Concentration unit';
}

// Human sentence describing the clash, naming both sides' values.
function identityClashText(csvId, jsonId, reason) {
    const field = reason === 'meas' ? 'measurement' : reason === 'unit' ? 'unit' : 'concentration unit';
    const a = reason === 'meas' ? csvId.measurement : reason === 'unit' ? csvId.unit : csvId.concen_unit;
    const b = reason === 'meas' ? jsonId.measurement : reason === 'unit' ? jsonId.unit : jsonId.concen_unit;
    return `The data file's ${field} (${a || '—'}) does not match the calibration curve's ${field} (${b || '—'}). Pick a matching file.`;
}

// Build the muted identity badge appended after a filename (escaped). Shows
// Measurement·Unit·ConcenUnit, using "—" for an unknown Measurement/Unit.
function _identityBadge(id) {
    if (!id) return '';
    const parts = [id.measurement || '—', id.unit || '—', id.concen_unit || DEFAULT_CONCEN_UNIT_JS];
    return ` <span class="file-identity">${_escHtml(parts.join('·'))}</span>`;
}

// When `counterpart` (the loaded CSV or JSON identity, tagged with __kind) is set,
// return the disabled Select-button attributes for a row whose identity does not
// match; else ''. `rowId` is the identity of the row's file.
function _selectDisableAttrs(rowId, counterpart) {
    if (!counterpart) return '';
    const m = (counterpart.__kind === 'csv')
        ? identityMatch(counterpart, rowId)   // file selected is CSV, row is a JSON
        : identityMatch(rowId, counterpart);  // file selected is JSON, row is a CSV
    if (m.ok) return '';
    const msg = identityMismatchLabel(m.reason) + ' differs from the selected file — cannot pair';
    return ` disabled title="${_esc(msg)}" data-hint="${_esc(msg)}"`;
}

// The identity of the loaded counterpart, only in kinetics/point mode (pairing is
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

// Create a new, empty data subfolder without running a reading. Prompts for a
// name (same rules as rename), calls /create_data_folder, then refreshes the
// folder lists so the new folder is immediately selectable.
async function createDataFolder() {
    const result = await Swal.fire({
        title: t('newfolder.title', 'New folder'),
        input: 'text',
        inputLabel: t('newfolder.label', 'Folder name'),
        inputPlaceholder: t('ph.new_subfolder', 'New subfolder name'),
        showCancelButton: true,
        confirmButtonText: t('common.create', 'Create'),
        cancelButtonText: t('common.cancel', 'Cancel'),
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
    const name = result.value.trim();

    try {
        if (typeof window.showSpinner === 'function') window.showSpinner();
        const response = await fetch('/create_data_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await response.json();
        if (data.status !== 'success') throw new Error(data.message || 'Create failed');

        await loadDataFolders();
        if (typeof logEvent === 'function') logEvent('file', 'create_folder', { name });
        if (!getBtnChecked("no-swal-checkbox")) {
            Swal.fire(t('newfolder.created', 'Folder created'), data.message || `Created "${name}".`, 'success');
        }
    } catch (e) {
        Swal.fire(t('common.error', 'Error'), e.message, 'error');
    } finally {
        if (typeof window.hideSpinner === 'function') window.hideSpinner();
    }
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

        if (!getBtnChecked("no-swal-checkbox")) {
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

        if (!getBtnChecked("no-swal-checkbox")) {
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

// Header row for the calibration-JSON table (name + modified-date columns are
// click-to-sort). Matches the server-rendered markup in index.html.
function _jsonTableHeaderHtml() {
    return `<tr>
        <th class="sortable-th" onclick="sortJsonTable('name')" data-hint="${_attr(t('hint.sort_by_name','Click to sort by name'))}">${_escHtml(t('table.calibrated_json','Calibrated JSON'))}<span class="sort-arrow">${_fileSortArrow('name')}</span></th>
        <th class="sortable-th" onclick="sortJsonTable('date')" data-hint="${_attr(t('hint.sort_by_date','Click to sort by last modified date'))}">${_escHtml(t('table.modified','Modified'))}<span class="sort-arrow">${_fileSortArrow('date')}</span></th>
        <th colspan="3">${_escHtml(t('table.action','Action'))}</th>
    </tr>`;
}

// Render the calibration-JSON rows into #json-table, honouring the active sort
// order, the max-JSON-rows limit and the modified-date column (AppState.jsonMeta).
function renderJsonRows(files) {
    AppState.jsonNames = (files || []).slice();
    let html = _jsonTableHeaderHtml();
    if (files && files.length > 0) {
        const limit = (typeof USER_SETTINGS !== 'undefined' && USER_SETTINGS.max_json_rows > 0) ? USER_SETTINGS.max_json_rows : Infinity;
        const sorted = _sortNamesByMeta(files, AppState.jsonMeta);
        const shown = sorted.slice(0, limit);
        const counterpart = _csvCounterpartForJsonTable();  // loaded CSV (kinetics/point)
        shown.forEach(file => {
            const isSelected = file === AppState.currentJSON ? ' class="selected"' : '';
            const display = (AppState.jsonMeta[file] && AppState.jsonMeta[file].display) || '';
            const badge = _identityBadge(AppState.jsonIdentity && AppState.jsonIdentity[file]);
            const disableAttrs = _selectDisableAttrs(AppState.jsonIdentity && AppState.jsonIdentity[file], counterpart);
            html += `<tr${isSelected}><td>${_escHtml(file)}${badge}</td><td class="file-mtime">${_escHtml(display)}</td><td><button${disableAttrs} onclick="selectFile('${_esc(file)}', this, '#json-table')">${_escHtml(t('btn.select','✅ Select'))}</button></td><td><button onclick="deleteFile('${_esc(file)}', this, '#json-table')">${_escHtml(t('btn.delete','❌ Delete'))}</button></td><td><button onclick="editFile('${_esc(file)}', this, '#json-table')">${_escHtml(t('btn.edit','✏️ Edit'))}</button></td></tr>`;
        });
        if (sorted.length > shown.length) {
            html += `<tr><td colspan="5" style="text-align:center;color:#888;font-style:italic;padding:4px;">+${sorted.length - shown.length} ${_escHtml(t('table.more_adjust_limit','more — adjust limit in Settings ⚙️'))}</td></tr>`;
        }
    } else {
        html += `<tr><td colspan="5">${_escHtml(t('caljson.none_available','No Calibrated JSON is available.'))}</td></tr>`;
    }
    document.getElementById("json-table").innerHTML = html;
    const searchInput = document.getElementById('json-search');
    if (searchInput && searchInput.value) {
        filterTable('json-table', searchInput.value);
    }
}

// Render the calibration-JSON table. Called with the file list from /get_json_cal;
// when called with no argument (post-copy/edit refreshes) it re-fetches the current
// mode's list (and its date metadata) itself.
function updateJSONTable(files) {
    if (files === undefined) {
        const mode = AppState.currentMeasurementMode;
        return fetch(`/get_json_cal?mode=${encodeURIComponent(mode)}&numSources=${AppState.numSources}`)
            .then(r => r.json())
            .then(resp => {
                AppState.jsonMeta = resp.files_meta || {};
                AppState.jsonIdentity = resp.files_identity || {};
                renderJsonRows(resp.files || []);
            })
            .catch(() => { renderJsonRows([]); });
    }
    renderJsonRows(files);
    return Promise.resolve();
}

// Header row for the report-subject folder table (name + modified-date columns
// are click-to-sort).
function _reportTableHeaderHtml() {
    return `<tr>
        <th id="file-table-header-name" class="sortable-th" onclick="sortReportTable('name')" data-hint="${_attr(t('hint.sort_by_folder','Click to sort by folder name'))}">${_escHtml(t('table.folder_name','Folder Name'))}<span class="sort-arrow">${_fileSortArrow('name')}</span></th>
        <th class="sortable-th" onclick="sortReportTable('date')" data-hint="${_attr(t('hint.sort_by_date','Click to sort by last modified date'))}">${_escHtml(t('table.modified','Modified'))}<span class="sort-arrow">${_fileSortArrow('date')}</span></th>
        <th colspan="3">${_escHtml(t('table.action','Action'))}</th>
    </tr>`;
}

// Render the report-subject folder rows into #file-table, honouring the active
// sort order and the modified-date column (AppState.reportMeta).
function renderReportRows(subjects) {
    AppState.reportNames = (subjects || []).slice();
    let html = _reportTableHeaderHtml();
    if (subjects && subjects.length > 0) {
        const sorted = _sortNamesByMeta(subjects, AppState.reportMeta);
        sorted.forEach(subject => {
            const isSelected = subject === AppState.currentReportSubject ? ' class="selected"' : '';
            const display = (AppState.reportMeta[subject] && AppState.reportMeta[subject].display) || '';
            html += `<tr${isSelected}><td>${_escHtml(subject)}</td><td class="file-mtime">${_escHtml(display)}</td><td><button onclick="selectFile('${_esc(subject)}', this)">${_escHtml(t('btn.select_subject','📁 Select Subject'))}</button></td><td><button onclick="deleteReportSubject('${_esc(subject)}', this)">${_escHtml(t('btn.delete','❌ Delete'))}</button></td><td><button onclick="editReportSubject('${_esc(subject)}', this)">${_escHtml(t('btn.edit','✏️ Edit'))}</button></td></tr>`;
        });
    } else {
        html += `<tr><td colspan="5">${_escHtml(t('report.none_found','No report subjects found.'))}</td></tr>`;
    }
    document.getElementById("file-table").innerHTML = html;
    const searchInput = document.getElementById('file-search');
    if (searchInput && searchInput.value) {
        filterTable('file-table', searchInput.value);
    }
}

function updateReportTable(subjects) {
    document.getElementById("file-search").placeholder = t('ph.search_subject_folders', "Search subject folders...");
    renderReportRows(subjects);
}

// Return the ▲/▼ indicator for a column header given the active sort order,
// or '' when the table is not currently sorted by that column.
function _fileSortArrow(key) {
    const order = AppState.fileSortOrder || 'date_desc';
    if (!order.startsWith(key)) return '';
    return order.endsWith('asc') ? ' ▲' : ' ▼';
}

// Header row for the CSV File Selection table (name + modified-date columns are
// click-to-sort). Kept here so JS re-renders match the server-rendered markup.
function _fileTableHeaderHtml() {
    return `<tr>
        <th id="file-table-header-name" class="sortable-th" onclick="sortFileTable('name')" data-hint="${_attr(t('hint.sort_by_filename','Click to sort by file name'))}">${_escHtml(t('table.file_name','File Name'))}<span class="sort-arrow">${_fileSortArrow('name')}</span></th>
        <th id="file-table-header-date" class="sortable-th" onclick="sortFileTable('date')" data-hint="${_attr(t('hint.sort_by_date','Click to sort by last modified date'))}">${_escHtml(t('table.modified','Modified'))}<span class="sort-arrow">${_fileSortArrow('date')}</span></th>
        <th colspan="3">${_escHtml(t('table.action','Action'))}</th>
    </tr>`;
}

// Order names by the active sort order (AppState.fileSortOrder, shared by all
// folder/file tables), using mtime from the given meta map for date sorting
// (missing entries sort as oldest) and a case-insensitive comparison for name
// sorting.
function _sortNamesByMeta(names, meta) {
    const order = AppState.fileSortOrder || 'date_desc';
    const dir = order.endsWith('asc') ? 1 : -1;
    const byDate = order.startsWith('date');
    const m = meta || {};
    return names.slice().sort((a, b) => {
        let cmp;
        if (byDate) {
            cmp = ((m[a] && m[a].mtime) || 0) - ((m[b] && m[b].mtime) || 0);
        } else {
            cmp = a.toLowerCase().localeCompare(b.toLowerCase());
        }
        return cmp * dir;
    });
}

function _sortFileNames(names) {
    return _sortNamesByMeta(names, AppState.fileMeta);
}

// Toggle the shared sort order for a clicked column header: clicking the active
// column flips direction; switching columns starts descending (newest / Z-A
// first). Persisted as the new default (best-effort). Returns the new order so
// callers can re-render their table.
function _applySortOrder(key) {
    const order = AppState.fileSortOrder || 'date_desc';
    let dir = 'desc';
    if (order.startsWith(key)) {
        dir = order.endsWith('asc') ? 'desc' : 'asc';
    }
    AppState.fileSortOrder = `${key}_${dir}`;
    if (typeof USER_SETTINGS !== 'undefined') USER_SETTINGS.file_sort_order = AppState.fileSortOrder;
    if (typeof saveUserSetting === 'function') saveUserSetting('file_sort_order', AppState.fileSortOrder);
    return AppState.fileSortOrder;
}

// Render the CSV file rows (already passed through filterFiles) into #file-table,
// honouring the active sort order and the max-CSV-rows limit. Stores the rendered
// (filtered) names on AppState so a sort click can re-render without re-fetching.
function renderFileRows(names) {
    AppState.fileNames = (names || []).slice();
    let html = _fileTableHeaderHtml();
    if (names && names.length > 0) {
        const limit = (typeof USER_SETTINGS !== 'undefined' && USER_SETTINGS.max_csv_rows > 0) ? USER_SETTINGS.max_csv_rows : Infinity;
        const sorted = _sortFileNames(names);
        const shown = sorted.slice(0, limit);
        const counterpart = _jsonCounterpartForFileTable();  // loaded JSON (kinetics/point)
        shown.forEach(file => {
            const isSelected = file === AppState.currentFile ? ' class="selected"' : '';
            const display = (AppState.fileMeta[file] && AppState.fileMeta[file].display) || '';
            const badge = _identityBadge(AppState.fileIdentity && AppState.fileIdentity[file]);
            const disableAttrs = _selectDisableAttrs(AppState.fileIdentity && AppState.fileIdentity[file], counterpart);
            html += `<tr${isSelected}><td>${_escHtml(file)}${badge}</td><td class="file-mtime">${_escHtml(display)}</td><td><button${disableAttrs} onclick="selectFile('${_esc(file)}', this)">${_escHtml(t('btn.select','✅ Select'))}</button></td><td><button onclick="deleteFile('${_esc(file)}', this)">${_escHtml(t('btn.delete','❌ Delete'))}</button></td><td><button onclick="editFile('${_esc(file)}', this)">${_escHtml(t('btn.edit','✏️ Edit'))}</button></td></tr>`;
        });
        if (sorted.length > shown.length) {
            html += `<tr><td colspan="5" style="text-align:center;color:#888;font-style:italic;padding:4px;">+${sorted.length - shown.length} ${_escHtml(t('table.more_adjust_limit','more — adjust limit in Settings ⚙️'))}</td></tr>`;
        }
    } else {
        html += `<tr><td colspan="5">${_escHtml(t('files.none_found','No CSV files found in the directory.'))}</td></tr>`;
    }
    document.getElementById("file-table").innerHTML = html;
    const searchInput = document.getElementById('file-search');
    if (searchInput && searchInput.value) {
        filterTable('file-table', searchInput.value);
    }
}

// Re-sort the File Selection table when a column header is clicked.
function sortFileTable(key) {
    _applySortOrder(key);
    renderFileRows(AppState.fileNames);
}

// Re-sort the calibration-JSON table when a column header is clicked.
function sortJsonTable(key) {
    _applySortOrder(key);
    renderJsonRows(AppState.jsonNames);
}

// Re-sort the report-subject folder table when a column header is clicked.
function sortReportTable(key) {
    _applySortOrder(key);
    renderReportRows(AppState.reportNames);
}

function updateFileTable(files, deselect) {
    return filterFiles(files).then((filteredFiles) => {
        renderFileRows(filteredFiles || []);
        if (deselect) {
            AppState.currentFile = null;
            $toggleQueryClass("#file-table tr", "selected", false);
            updateFileDisplay(AppState.currentFile);
        }
    });
}

// Parse a file/JSON search query into positional, space-separated filters. The
// positions are, in order: name, measurement, unit, ConcenUnit — all AND-ed
// (set intersection) so each extra token narrows the result. A position is
// skipped (no filter) with a bare `-` or empty quotes `""`; values containing
// spaces must be quoted, e.g. `std "Total Protein" AU nM`. Extra tokens beyond
// the four positions are ignored. All matching is case-insensitive substring
// matching (see _identityFieldMatch / filterTable).
function parseSearchQuery(query) {
    const fields = { measurement: null, unit: null, concen_unit: null };
    let name = '';
    const ORDER = ['name', 'measurement', 'unit', 'concen_unit'];
    const tokens = (query || '').match(/"[^"]*"|\S+/g) || [];
    for (let i = 0; i < tokens.length && i < ORDER.length; i++) {
        const val = tokens[i].replace(/^"|"$/g, '').trim();
        if (val === '' || val === '-') continue;  // skipped position
        if (ORDER[i] === 'name') name = val.toLowerCase();
        else fields[ORDER[i]] = val.toLowerCase();
    }
    return { freeText: name, fields };
}

// True when a file's identity satisfies every active field filter (case-insensitive
// substring). An absent ConcenUnit defaults to ng/µL (the documented default);
// absent/wildcard Measurement·Unit (null) match only when no filter is set for them,
// so a `-meas X` filter hides files that don't declare that field.
function _identityFieldMatch(id, fields) {
    const ident = id || {};
    for (const key of ['measurement', 'unit', 'concen_unit']) {
        const q = fields[key];
        if (q === null) continue;
        let val = ident[key];
        if (key === 'concen_unit' && (val === undefined || val === null || val === '')) {
            val = 'ng/µL';
        }
        val = (val === undefined || val === null) ? '' : String(val);
        if (val.toLowerCase().indexOf(q) === -1) return false;
    }
    return true;
}

// Filter a file/JSON table's rows by the search box. Matches the file name and,
// for the identity-bearing CSV/JSON tables, the `-meas`/`-unit`/`-concen` field
// filters (see parseSearchQuery). The name cell also holds the identity badge, so
// the badge text is stripped before name matching, and identity is looked up from
// AppState rather than scraped from the DOM. Field filters do not apply to the
// report-subject folder listing (which reuses #file-table without identity).
function filterTable(tableId, query) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const { freeText, fields } = parseSearchQuery(query);
    const hasFieldFilter = fields.measurement !== null || fields.unit !== null || fields.concen_unit !== null;
    const isReport = (typeof AppState !== 'undefined' && AppState.currentMeasurementMode === 'report');
    const identityMap = (tableId === 'file-table' && !isReport) ? (AppState.fileIdentity || {})
        : tableId === 'json-table' ? (AppState.jsonIdentity || {})
            : null;
    const trs = table.getElementsByTagName("tr");
    for (let i = 1; i < trs.length; i++) {
        const tds = trs[i].getElementsByTagName("td");
        if (tds.length === 0) continue;
        // The name cell also holds the identity badge span; strip it for name matching.
        const nameCell = tds[0];
        const badgeEl = nameCell.querySelector ? nameCell.querySelector('.file-identity') : null;
        let name = (nameCell.textContent || nameCell.innerText || '');
        if (badgeEl) name = name.replace(badgeEl.textContent || '', '');
        name = name.trim();

        let show = !freeText || name.toLowerCase().indexOf(freeText) > -1;
        // Field filters only make sense for the identity-bearing tables; for other
        // tables (e.g. folders) they are ignored rather than hiding everything.
        if (show && hasFieldFilter && identityMap) {
            show = _identityFieldMatch(identityMap[name], fields);
        }
        trs[i].style.display = show ? "" : "none";
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
                //
                // The name cell holds the filename PLUS an identity badge span
                // (.file-identity, e.g. "Absorbance·—·%"), so its textContent is
                // never equal to the bare filename — strip the badge before
                // matching, mirroring filterTable(). A live CSV always carries
                // metadata, so an exact-text match here would always miss and the
                // file would never get selected.
                let cell = null;
                for (let attempt = 0; attempt < 10 && !cell; attempt++) {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    const nameCells = document.querySelectorAll("#file-table tr td:first-child");
                    cell = Array.from(nameCells).find(td => {
                        const badge = td.querySelector ? td.querySelector('.file-identity') : null;
                        let name = td.textContent || '';
                        if (badge) name = name.replace(badge.textContent || '', '');
                        return name.trim() === fileName;
                    });
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