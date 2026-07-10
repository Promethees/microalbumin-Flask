document.getElementById("year").textContent = new Date().getFullYear();

let serverAvailable = true;
let logInterval, updateInterval, serverCheckInterval;

const _systemDark = window.matchMedia('(prefers-color-scheme: dark)');

// Apply a theme ('light' | 'dark') to the document and sync toggle UI.
function _applyTheme(isDark) {
    document.body.classList.toggle('dark', isDark);
    document.body.classList.toggle('light', !isDark);
    document.getElementById('toggleButton').classList.toggle('active', isDark);
    if (typeof AppState !== 'undefined') AppState.lightDisplay = !isDark;
}

// Update the toggle icon to reflect the current effective mode + whether it's auto.
function _syncToggleIcon(savedPref) {
    const btn = document.getElementById('toggleButton');
    if (savedPref === null) {
        btn.dataset.themeMode = 'auto';
    } else {
        btn.dataset.themeMode = savedPref;
    }
}

// Save a single key/value to the server-side user_settings.json (fire-and-forget).
function saveUserSetting(key, value) {
    fetch('/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value })
    }).catch(() => {});
}

// On startup: apply saved localStorage preference → server preference → system default.
(function initTheme() {
    const saved = localStorage.getItem('theme'); // 'light' | 'dark' | null
    let isDark, iconPref;
    if (saved !== null) {
        isDark = saved === 'dark';
        iconPref = saved;
    } else if (typeof USER_SETTINGS !== 'undefined' && USER_SETTINGS.theme !== 'auto') {
        isDark = USER_SETTINGS.theme === 'dark';
        iconPref = USER_SETTINGS.theme;
        localStorage.setItem('theme', USER_SETTINGS.theme);
    } else {
        isDark = _systemDark.matches;
        iconPref = null;
    }
    _applyTheme(isDark);
    _syncToggleIcon(iconPref);
})();

// Follow system changes only when the user hasn't set a manual preference.
_systemDark.addEventListener('change', function (e) {
    if (localStorage.getItem('theme') === null) {
        _applyTheme(e.matches);
        _syncToggleIcon(null);
        toggleMode();
    }
});

// Toggle cycles: light → dark → auto (system) → light → …
document.getElementById('toggleContainer').addEventListener('click', function () {
    const current = document.getElementById('toggleButton').dataset.themeMode || 'light';
    let next;
    if (current === 'light') {
        next = 'dark';
    } else if (current === 'dark') {
        next = 'auto';
    } else {
        next = 'light';
    }

    if (next === 'auto') {
        localStorage.removeItem('theme');
        _applyTheme(_systemDark.matches);
    } else {
        localStorage.setItem('theme', next);
        _applyTheme(next === 'dark');
    }
    _syncToggleIcon(next === 'auto' ? null : next);
    saveUserSetting('theme', next);
    toggleMode();
});

document.getElementById('shutdown-btn').addEventListener('click', function () {
    terminateScript();
    const confirmationMessage = "{{ production_mode }}" === "True"
        ? 'WARNING: Production mode. This will terminate the server process and close the terminal. Continue?'
        : 'Are you sure you want to shutdown the program?';

    if (confirm(confirmationMessage)) {
        // Determine the current mode
        fetch('/shutdown', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ mode: AppState.lightDisplay ? 'light' : 'dark' }) // Send mode to server
        })
            .then(response => response.text())
            .then(html => {
                document.open();
                document.write(html);
                document.close();
            })
            .catch(error => {
                console.error('Error:', error);
                window.location.href = '/goodbye';
            });
    }
});

// Repopulate the #num-sources dropdown for the given folder. No-op unless the
// "Filter by number of sources" checkbox is on. Preserves the current selection
// when the new folder still offers that count; otherwise falls back to the
// smallest available count. Returns a Promise that resolves once AppState.numSources
// reflects the new folder, so callers can render the file table afterwards.
function refreshNumSourcesOptions(path) {
    const filterCheckbox = document.getElementById('filter-source');
    if (!filterCheckbox || !filterCheckbox.checked) return Promise.resolve();
    const dir = path || AppState.currentDirectory;
    return new Promise((resolve) => {
        $.get('/get_num_sources?path=' + encodeURIComponent(dir), { request: true }, function (response) {
            const select = document.getElementById('num-sources');
            const counts = (response && response.num_sources) || [];
            const previous = AppState.numSources;
            select.innerHTML = ''; // clear existing options
            counts.forEach(num => select.add(new Option(num, num)));
            // Keep the previous choice if the new folder still supports it.
            const keep = counts.includes(previous) ? previous : (counts[0] || 1);
            select.value = String(keep);
            AppState.numSources = keep;
            resolve();
        }).fail(function () { resolve(); });
    });
}

// Rebuild the per-source export checkbox group from the current
// AppState.numSources. Skipped in calibrate mode, which has no source export.
function rebuildExportSourceOptions() {
    if (AppState.currentMeasurementMode === "calibrate") return;
    updateMultiSourceExportOptions();
}

document.getElementById('filter-source').addEventListener('change', function () {
    const numSourcesSelect = document.getElementById('num-sources-section');
    deselectFile();
    deselectFile("#json-table");
    AppState.responseData = null;
    AppState.globalAnalysis = null;
    AppState.globalEstimatedValue = null;
    document.getElementById('est-val-error').innerHTML = '';
    document.getElementById('est-val-exp').innerHTML = '';
    document.getElementById('exp-json-time-value').value = '';
    if (this.checked) {
        numSourcesSelect.classList.remove('hidden');
        // Populate the dropdown for the current folder, then render with the
        // resolved source count so the file table and export options match it.
        refreshNumSourcesOptions(AppState.currentDirectory).then(() => {
            updateDirectory(AppState.currentDirectory, true);
            rebuildExportSourceOptions();
        });
    } else {
        numSourcesSelect.classList.add('hidden');
        updateDirectory(AppState.currentDirectory, true);
        rebuildExportSourceOptions();
    }
});

document.getElementById('num-sources').addEventListener('change', function () {
    AppState.numSources = parseInt(this.value);
    updateDirectory(AppState.currentDirectory, true);
    updateMultiSourceExportOptions();
    deselectFile();
});

const sameDirCheckbox = document.getElementById("same-dir-as-data");

sameDirCheckbox.addEventListener("change", function () {
    const subfolderRow = document.getElementById("exp-subfolder-row");
    if (subfolderRow) subfolderRow.style.display = this.checked ? "none" : "flex";
    if (this.checked) {
        AppState.exportPath = AppState.currentDirectory;
    }
});

document.getElementById('range-value-start').addEventListener('input', validateRangeInput);
document.getElementById('range-value-end').addEventListener('input', validateRangeInput);

document.getElementById('base-name').addEventListener('input', function () {
    validateFileName('base-name');
});
document.getElementById('save-file').addEventListener('input', function () {
    validateFileName('save-file');
});
document.getElementById('save-json-file').addEventListener('input', function () {
    validateFileName('save-json-file');
});

// base-dir is now a hidden field managed by JS; no user-input validation needed.

const expPoint = document.getElementById('exp-json-time-value');
expPoint.addEventListener('change', updatePointEstimate);
// The export-source checkboxes (#exp-source-checkboxes) re-estimate via their own
// change handlers (onExpSourceAllToggle / onExpSourceItemToggle) attached when the
// group is (re)built in updateMultiSourceExportOptions().

// Currently-selected time unit for the point-mode reference input. Reading the
// select value directly (rather than getTimeUnitValue, which returns null when
// the element is hidden) keeps the conversion working in every mode.
function getExpTimeUnit() {
    const el = document.getElementById('time-unit');
    return (el && el.value) ? el.value : 'seconds';
}

// Update the unit label shown beside #exp-json-time-value to match #time-unit.
function refreshExpTimeUnitLabel() {
    const label = document.getElementById('exp-json-time-unit-label');
    if (label) label.textContent = ` ${getExpTimeUnit().slice(0, -1)}. `;
}

// Remember the active unit so a unit change can rescale the entered value to the
// same absolute time (e.g. 5 minutes -> 300 seconds).
let prevExpTimeUnit = getExpTimeUnit();

function refreshExpTimeValueForUnit() {
    const newUnit = getExpTimeUnit();
    const expInput = document.getElementById('exp-json-time-value');
    const oldVal = parseFloat(expInput.value);
    if (!isNaN(oldVal) && newUnit !== prevExpTimeUnit) {
        const seconds = oldVal * getTimeUnitMultiplier(prevExpTimeUnit);
        const converted = seconds / getTimeUnitMultiplier(newUnit);
        // Trim floating-point noise without forcing trailing zeros.
        expInput.value = parseFloat(converted.toFixed(6));
    }
    prevExpTimeUnit = newUnit;
    refreshExpTimeUnitLabel();
    // Only re-estimate when a reference point is actually set, so merely
    // switching units on an empty field doesn't raise a "not set" error.
    if (!isNaN(parseFloat(expInput.value))) updatePointEstimate();
}

document.getElementById('time-unit').addEventListener('change', refreshExpTimeValueForUnit);
refreshExpTimeUnitLabel();

function isNullOrArrayOfNull(value) {
    if (value === null) return true; // case 1: value is null
    if (Array.isArray(value)) {
        return value.every(item => item === null); // case 2: all items null
    }
    return false; // anything else
}

function updatePointEstimate() {
    const estValError = document.getElementById('est-val-error');
    const estValExp = document.getElementById('est-val-exp');
    const currExpTimePoint = getValFloat("exp-json-time-value");
    const timeUnit = getExpTimeUnit();
    const timeUnitLabel = timeUnit.slice(0, -1);
    // Raw data is in seconds; convert the user-entered reference point from the
    // selected #time-unit to seconds before estimating.
    const currExpTimeSeconds = currExpTimePoint * getTimeUnitMultiplier(timeUnit);

    // Estimate every source's value (the export step later picks the selected
    // subset via getSelectedExportSources()), so globalEstimatedValue is always
    // a per-source array indexed 0..numSources-1.
    AppState.globalEstimatedValue = [];
    for (let i = 1; i <= AppState.numSources; i++) {
        AppState.globalEstimatedValue.push(
            getEstimatedValue(AppState.responseData, currExpTimeSeconds, i)
        );
    }

    if (isNullOrArrayOfNull(AppState.globalEstimatedValue)) {
        estValError.innerHTML = '<span style="color:red">Error: Reference point is outside the range of the data or not set!</span>';
        estValExp.innerHTML = '';
    } else {
        estValError.innerHTML = '';
        estValExp.innerHTML = `Estimated values at ${currExpTimePoint} ${timeUnitLabel} are: ${AppState.globalEstimatedValue
                .map((v, i) => `<span style="color:${AppState.plotColors[i]}">[#S${i + 1}] ${v.toFixed(4)} ${AppState.globalAnalysis.meas_unit}</span>`)
                .join(", ")
            }`;
    }
}

function validateRangeInput() {
    const startInput = document.getElementById('range-value-start');
    const endInput = document.getElementById('range-value-end');
    const errorElement = document.getElementById('range-value-error');

    const startValue = parseFloat(startInput.value);
    const endValue = parseFloat(endInput.value);

    // Reset state
    errorElement.innerHTML = '';
    startInput.classList.remove('invalid', 'valid');
    endInput.classList.remove('invalid', 'valid');
    if (isNaN(startValue) || isNaN(endValue)) {
        errorElement.innerHTML = '<br/>Both values must be numbers<br/>';
        startInput.classList.add('invalid');
        endInput.classList.add('invalid');
        return false;
    }
    if (startValue < 0 || endValue < 0) {
        errorElement.innerHTML = '<br/>Values must be non-negative<br/>';
        startInput.classList.add('invalid');
        endInput.classList.add('invalid');
        return false;
    }
    if (startValue >= endValue) {
        errorElement.innerHTML = '<br/>Start value must be less than End value<br/>';
        startInput.classList.add('invalid');
        endInput.classList.add('invalid');
        return false;
    }

    startInput.classList.add('valid');
    endInput.classList.add('valid');
    return true;
}

function validateFileName(inputId) {
    const input = document.getElementById(inputId);
    const errorElement = document.getElementById(`${inputId}-error`);
    const fileName = input.value.trim();

    // Reset state
    errorElement.innerHTML = '';
    input.classList.remove('invalid', 'valid');

    const illegalChars = /[\\/:*?"<>|\0]/g;
    if (illegalChars.test(fileName)) {
        errorElement.innerHTML = 'File name cannot contain: \\ / : * ? " < > |<br/>';
        input.classList.add('invalid');
        return false;
    }

    const reservedNames = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i;
    if (reservedNames.test(fileName)) {
        errorElement.innerHTML = 'Reserved system name (CON, PRN, AUX, etc.)<br/>';
        input.classList.add('invalid');
        return false;
    }

    if (fileName !== input.value) {
        errorElement.innerHTML = 'No leading/trailing spaces<br/>';
        input.classList.add('invalid');
        return false;
    }

    if (fileName.startsWith('.') || fileName.endsWith('.')) {
        errorElement.innerHTML = 'Cannot start/end with period<br/>';
        input.classList.add('invalid');
        return false;
    }

    if (fileName.length > 255) {
        errorElement.innerHTML = 'Max 255 characters<br/>';
        input.classList.add('invalid');
        return false;
    }

    input.classList.add('valid');
    return true;
}

function validateTimeoutInterval() {
    const infTimeout = document.getElementById('inf-timeout');
    const timeoutInput = document.getElementById('timeout');
    const timeoutUnit = document.getElementById('timeout-unit').value;
    const intervalInput = document.getElementById('interval');
    const intervalUnit = document.getElementById('interval-unit').value;
    const errorElement = document.getElementById(`timeout-interval-error`);
    const timeout = document.getElementById(`timeout`);
    const interval = document.getElementById(`interval`);
    errorElement.innerHTML = '';

    // Disable timeout input when Infinity is checked
    timeoutInput.disabled = infTimeout.checked;

    // Get input values
    const timeoutValue = timeoutInput.value.trim();
    const intervalValue = intervalInput.value.trim();

    // Remove outer edge
    timeout.classList.remove('invalid', 'valid');
    interval.classList.remove('invalid', 'valid');

    // Validation logic
    // Case 1: Both inputs are empty
    if (timeoutValue === '' && intervalValue === '') {
        timeout.classList.add('valid');
        interval.classList.add('valid');
        return true;
    }

    // Case 2: Infinity is checked
    if (infTimeout.checked) {
        if (intervalValue === '' || parseFloat(intervalValue) >= 0) {
            timeout.classList.add('valid');
            interval.classList.add('valid');
            return true;
        }
        else {
            errorElement.innerHTML = 'Interval value is less than zero!<br/>';
            timeout.classList.add('invalid');
            interval.classList.add('invalid');
            return false;
        }
    }

    // Case 3: Only one input is provided
    if ((timeoutValue === '' && intervalValue !== '') || (timeoutValue !== '' && intervalValue === '')) {
        errorElement.innerHTML = 'Please have both of these metrics values or give BOTH blank or check Infinite checkbox<br/>';
        timeout.classList.add('invalid');
        interval.classList.add('invalid');
        return false;
    }

    // Case 4: Both inputs provided, compare converted values
    const timeoutSec = parseFloat(timeoutValue) * getTimeUnitMultiplier(timeoutUnit);
    const intervalSec = parseFloat(intervalValue) * getTimeUnitMultiplier(intervalUnit);

    // Check if inputs are valid numbers and interval is less than timeout
    if (isNaN(timeoutSec) || isNaN(intervalSec) || timeoutSec <= 0 || intervalSec < 0) {
        errorElement.innerHTML = 'Invalid inputs or Timeout/Interval value is less than 0<br/>';
        timeout.classList.add('invalid');
        interval.classList.add('invalid');
        return false;
    }

    if (intervalSec >= timeoutSec) {
        errorElement.innerHTML = 'Interval must be smaller than Timeout! Please adjust your values<br/>';
        timeout.classList.add('invalid');
        interval.classList.add('invalid');
        return false;
    }

    timeout.classList.add('valid');
    interval.classList.add('valid');
    return true;
}

function validateWindowSize(window_size) {
    // Validate window size
    if (window_size < 3) {
        $showText("wd-size-error", "Window size must be greater than 3.");
        return;
    }

    if (!Number.isInteger(parseInt(window_size, 10)) || window_size === '' || isNaN(window_size)) {
        $showText("wd-size-error", "Window size must be an integer.");
        return;
    }

    // Clear error message if input is valid
    $hidden(["wd-size-error"], false);
}

// Event listener to toggle timeout input disabled state
document.getElementById('inf-timeout').addEventListener('change', function () {
    document.getElementById('timeout').value = '';
    document.getElementById('timeout').disabled = this.checked;
    document.getElementById('timeout-unit').disabled = this.checked;
});

document.addEventListener("DOMContentLoaded", () => {
    const mainDirSection = document.querySelector("#main-directory-section");
    const topLeftDirSection = document.querySelector("#top-left-dir-section");

    if (topLeftDirSection) topLeftDirSection.style.display = "none";

    if (mainDirSection && topLeftDirSection) {
        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    topLeftDirSection.style.display = "none";
                } else {
                    topLeftDirSection.style.display = "block";
                    const mainList = document.getElementById("data-folder-list");
                    const topList = document.getElementById("data-folder-list-top");
                    if (mainList && topList) topList.innerHTML = mainList.innerHTML;
                }
            });
        }, { threshold: 0 });
        observer.observe(mainDirSection);
    }
});

const modeDiv = document.getElementById('measurement-mode');
const modeButtons = modeDiv.querySelectorAll('button[data-mode]');

if (modeButtons.length > 0) {
    // After a restart, force kinetics regardless of the saved default_mode so the
    // app always comes up in the default display (see RESET_DISPLAY in index.html).
    const forceKinetics = (typeof RESET_DISPLAY !== 'undefined') && RESET_DISPLAY;
    const preferredMode = forceKinetics
        ? 'kinetics'
        : ((typeof USER_SETTINGS !== 'undefined') ? USER_SETTINGS.default_mode : null);
    const defaultBtn = preferredMode
        ? (Array.from(modeButtons).find(b => b.getAttribute('data-mode') === preferredMode) || modeButtons[0])
        : modeButtons[0];
    selectButton(defaultBtn, modeButtons, modeDiv);
}

const _wsInput = document.getElementById('window-size');
if (_wsInput && typeof USER_SETTINGS !== 'undefined') {
    _wsInput.value = USER_SETTINGS.default_window_size;
}

// Seed the concentration-unit dropdown from the user's default (no file is
// loaded yet at this point; selecting a file later re-syncs it to that file's
// recorded unit via syncConcenUnitDropdown()).
const _concenSel = document.getElementById('concen-unit');
if (_concenSel && typeof USER_SETTINGS !== 'undefined' && USER_SETTINGS.default_concentration_unit) {
    _concenSel.value = USER_SETTINGS.default_concentration_unit;
}

// Reflect the currently-loaded file's concentration unit in the dropdown. Falls
// back to the user default (then ng/µL) when the file predates # ConcenUnit.
function syncConcenUnitDropdown() {
    const sel = document.getElementById('concen-unit');
    if (!sel) return;
    const meta = (typeof AppState !== 'undefined') ? AppState.metaData : null;
    const fromMeta = meta && meta['ConcenUnit'] && String(meta['ConcenUnit']).trim();
    const fallback = (typeof USER_SETTINGS !== 'undefined' && USER_SETTINGS.default_concentration_unit) || 'ng/µL';
    sel.value = fromMeta || fallback;
}

if (typeof USER_SETTINGS !== 'undefined') {
    const _chartEl = document.getElementById('chart-container');
    if (_chartEl) _chartEl.style.maxHeight = (USER_SETTINGS.chart_height || 600) + 'px';
    const _normEl = document.getElementById('normalize-mode');
    if (_normEl && USER_SETTINGS.default_normalize) _normEl.checked = true;
    const _splitEl = document.getElementById('split-source');
    if (_splitEl && USER_SETTINGS.default_split_sources) _splitEl.checked = true;
    if (USER_SETTINGS.range_expanded_default) {
        const _rc = document.getElementById('range-collapse');
        const _rv = document.getElementById('range-chevron');
        if (_rc) _rc.classList.remove('collapsed');
        if (_rv) _rv.classList.remove('collapsed-chevron');
    }
    if (USER_SETTINGS.export_expanded_default) {
        const _ec = document.getElementById('export-analysis-collapse');
        const _ev = document.getElementById('export-analysis-chevron');
        if (_ec) _ec.classList.remove('collapsed');
        if (_ev) _ev.classList.remove('collapsed-chevron');
    }
    const _logEl = document.getElementById('log-display');
    if (_logEl) _logEl.style.maxHeight = (USER_SETTINGS.log_display_height || 300) + 'px';
    if (USER_SETTINGS.log_section_collapsed) {
        const _lc = document.getElementById('cdc-collapse');
        const _lv = document.getElementById('cdc-chevron');
        if (_lc) _lc.classList.add('collapsed');
        if (_lv) _lv.classList.add('collapsed-chevron');
    }
    const _notifyEl = document.getElementById('notify-me');
    if (_notifyEl) _notifyEl.checked = USER_SETTINGS.default_notify !== false;
    if (USER_SETTINGS.default_inf_timeout) {
        const _itEl = document.getElementById('inf-timeout');
        if (_itEl) {
            _itEl.checked = true;
            const _toEl = document.getElementById('timeout');
            const _tuEl = document.getElementById('timeout-unit');
            if (_toEl) _toEl.disabled = true;
            if (_tuEl) _tuEl.disabled = true;
        }
    }
    if (USER_SETTINGS.default_timeout != null) {
        const _toEl = document.getElementById('timeout');
        if (_toEl && !_toEl.disabled) _toEl.value = USER_SETTINGS.default_timeout;
    }
    const _tuEl = document.getElementById('timeout-unit');
    if (_tuEl && USER_SETTINGS.default_timeout_unit) _tuEl.value = USER_SETTINGS.default_timeout_unit;
    if (USER_SETTINGS.default_interval != null) {
        const _ivEl = document.getElementById('interval');
        if (_ivEl) _ivEl.value = USER_SETTINGS.default_interval;
    }
    const _iuEl = document.getElementById('interval-unit');
    if (_iuEl && USER_SETTINGS.default_interval_unit) _iuEl.value = USER_SETTINGS.default_interval_unit;
}

function selectButton(selectedButton, allButtons, div) {
    div.setAttribute('data-value', selectedButton.getAttribute('data-mode'));
    allButtons.forEach(button => {
        button.classList.remove('selected');
    });
    selectedButton.classList.add('selected');
}

const calDiv = document.getElementById('cal-mode-select');
const calButtons = calDiv.querySelectorAll('button[data-mode]');

if (calButtons.length > 0) {
    selectButton(calButtons[0], calButtons, calDiv);
}

// Defaults must stay in sync with user_settings.py:DEFAULTS
const SETTINGS_DEFAULTS = {
    theme: 'auto',
    ui_language: 'en',
    time_tag_format: 'iso',
    default_mode: 'kinetics',
    default_window_size: 4,
    default_subfolder: null,
    file_table_height: 240,
    file_sort_order: 'date_desc',
    max_csv_rows: 0,
    max_json_rows: 0,
    event_log_retention_days: 30,
    chart_height: 600,
    default_normalize: false,
    default_split_sources: false,
    range_expanded_default: false,
    export_expanded_default: false,
    log_display_height: 300,
    log_section_collapsed: false,
    default_notify: true,
    default_inf_timeout: false,
    default_timeout: null,
    default_timeout_unit: 'seconds',
    default_interval: null,
    default_interval_unit: 'seconds',
    merge_directory_picker: false,
    disable_popups: false,
    default_concentration_unit: 'ng/µL',
    ai_feedback_enabled: true,
    y_axis_scale_mode: 'auto',
    y_axis_custom_min: 0.0,
    y_axis_custom_max: 0.6,
};

function _buildSettingsHTML(s, folders, aiStats) {
    const subfolderOptions = folders.map(f =>
        `<option value="${f.name}" ${s.default_subfolder === f.name ? 'selected' : ''}>${f.name}</option>`
    ).join('');

    const row = (label, helpText, inputHtml) => `
        <label class="sm-row">
            <span class="sm-label">${label}</span>
            ${helpText ? `<span class="sm-help">${helpText}</span>` : ''}
            ${inputHtml}
        </label>`;

    const sel = (id, opts) =>
        `<select id="${id}" class="swal2-input">${opts}</select>`;
    const num = (id, min, val, step = '') =>
        `<input id="${id}" type="number" min="${min}" class="swal2-input" value="${val}"${step ? ` step="${step}"` : ''}>`;
    const rowCheck = (label, id, val) => `
        <label class="sm-row sm-row--check">
            <input type="checkbox" id="${id}" ${val ? 'checked' : ''}>
            <span class="sm-label">${label}</span>
        </label>`;
    const rowLimit = (label, inputId, checkId, val, checkLabel = 'Show all') => {
        const isAll = val === 0;
        return `
        <div class="sm-row">
            <div class="sm-limit-header">
                <span class="sm-label">${label}</span>
                <label class="sm-show-all-label">
                    <input type="checkbox" id="${checkId}" ${isAll ? 'checked' : ''}
                        onchange="const i=document.getElementById('${inputId}');i.disabled=this.checked;if(!this.checked&&!i.value)i.value=50;">
                    ${checkLabel}
                </label>
            </div>
            <input id="${inputId}" type="number" min="1" class="swal2-input"
                value="${isAll ? '' : val}" ${isAll ? 'disabled' : ''}>
        </div>`;
    };

    return `<div id="settings-modal-body">
        <div class="sm-section">
            <p class="sm-section-title">${t('settings.section.general', 'General')}</p>
            ${row(t('settings.language', 'Language'), t('settings.language.help', 'Language for the app interface'), sel('swal-ui-language',
                `<option value="en" ${(s.ui_language||'en')==='en'?'selected':''}>English</option>
                 <option value="vi" ${s.ui_language==='vi'?'selected':''}>Tiếng Việt</option>
                 <option value="zh" ${s.ui_language==='zh'?'selected':''}>中文 (简体)</option>
                 <option value="fr" ${s.ui_language==='fr'?'selected':''}>Français</option>
                 <option value="ja" ${s.ui_language==='ja'?'selected':''}>日本語</option>
                 <option value="ru" ${s.ui_language==='ru'?'selected':''}>Русский</option>`))}
            ${rowCheck(t('settings.disable_popups', 'Disable popups'), 'swal-disable-popups', s.disable_popups)}
            ${row(t('settings.time_format', 'Date / time format'), t('settings.time_format.help', 'Used for file modified-date tags'), sel('swal-time-format',
                `<option value="iso"       ${(s.time_tag_format||'iso')==='iso'?'selected':''}>YYYY-MM-DD HH:MM</option>
                 <option value="iso_sec"   ${s.time_tag_format==='iso_sec'?'selected':''}>YYYY-MM-DD HH:MM:SS</option>
                 <option value="us"        ${s.time_tag_format==='us'?'selected':''}>MM/DD/YYYY hh:MM AM/PM</option>
                 <option value="eu"        ${s.time_tag_format==='eu'?'selected':''}>DD/MM/YYYY HH:MM</option>
                 <option value="date_only" ${s.time_tag_format==='date_only'?'selected':''}>YYYY-MM-DD (date only)</option>`))}
        </div>
        <div class="sm-section">
            <p class="sm-section-title">${t('settings.section.appearance', 'Appearance')}</p>
            ${row('Theme', '', sel('swal-theme',
                `<option value="light" ${s.theme==='light'?'selected':''}>Light</option>
                 <option value="dark" ${s.theme==='dark'?'selected':''}>Dark</option>
                 <option value="auto" ${s.theme==='auto'?'selected':''}>Auto (system)</option>`))}
            ${row('File &amp; JSON table height', 'Scroll-area max-height in px (min 80)', num('swal-table-height', 80, s.file_table_height || 240))}
        </div>
        <div class="sm-section">
            <p class="sm-section-title">${t('settings.section.measurement', 'Measurement')}</p>
            ${row('Default mode', '', sel('swal-mode',
                `<option value="kinetics" ${s.default_mode==='kinetics'?'selected':''}>Kinetics</option>
                 <option value="point" ${s.default_mode==='point'?'selected':''}>Point</option>
                 <option value="calibrate" ${s.default_mode==='calibrate'?'selected':''}>Calibrate</option>`))}
            ${row('Default window size', 'Minimum 2', num('swal-window-size', 2, s.default_window_size || 4))}
            ${row('Default concentration unit', 'Unit selected for new calibration exports', sel('swal-concen-unit',
                (typeof CONCEN_UNITS !== 'undefined' ? CONCEN_UNITS : ['ng/µL', 'nM', '%', 'CFU', 'OD600'])
                    .map(u => `<option value="${u}" ${(s.default_concentration_unit||'ng/µL')===u?'selected':''}>${u}</option>`).join('')))}
            ${row('Default subfolder', '', sel('swal-subfolder',
                `<option value="" ${!s.default_subfolder?'selected':''}>(none)</option>${subfolderOptions}`))}
        </div>
        <div class="sm-section">
            <p class="sm-section-title">${t('settings.section.file_selection', 'File Selection')}</p>
            ${row('Default file sort order', 'Initial order of the File Selection table', sel('swal-file-sort',
                `<option value="date_desc" ${(s.file_sort_order||'date_desc')==='date_desc'?'selected':''}>Modified date (newest first)</option>
                 <option value="date_asc"  ${s.file_sort_order==='date_asc'?'selected':''}>Modified date (oldest first)</option>
                 <option value="name_asc"  ${s.file_sort_order==='name_asc'?'selected':''}>Name (A → Z)</option>
                 <option value="name_desc" ${s.file_sort_order==='name_desc'?'selected':''}>Name (Z → A)</option>`))}
            ${rowLimit('Max CSV files shown', 'swal-max-csv', 'swal-max-csv-all', s.max_csv_rows || 0)}
            ${rowLimit('Max calibration JSON files shown', 'swal-max-json', 'swal-max-json-all', s.max_json_rows || 0)}
            ${rowCheck('Pick merge files from a folder browser', 'swal-merge-picker', s.merge_directory_picker)}
        </div>
        <div class="sm-section">
            <p class="sm-section-title">${t('settings.section.activity_log', 'Activity Log')}</p>
            ${rowLimit('Log retention (days)', 'swal-retention-days', 'swal-retention-forever', s.event_log_retention_days === 0 ? 0 : (s.event_log_retention_days ?? 30), 'Keep forever')}
        </div>
        <div class="sm-section sm-section--full">
            <p class="sm-section-title">${t('settings.section.colorimeter_reading', 'Colorimeter Reading')}</p>
            <div class="sm-fields-grid">
                ${row('Log display height', 'px (min 100)', num('swal-log-height', 100, s.log_display_height || 300))}
                ${rowCheck('Collapsed by default', 'swal-log-collapsed', s.log_section_collapsed)}
                ${rowCheck('Notify when done by default', 'swal-log-notify', s.default_notify !== false)}
                ${rowCheck('Infinite timeout by default', 'swal-log-inf-timeout', s.default_inf_timeout)}
                ${row('Default timeout', '', num('swal-log-timeout', 0, s.default_timeout ?? '', 'any'))}
                ${row('Default timeout unit', '', sel('swal-log-timeout-unit',
                    `<option value="seconds" ${(s.default_timeout_unit||'seconds')==='seconds'?'selected':''}>seconds</option>
                     <option value="minutes" ${s.default_timeout_unit==='minutes'?'selected':''}>minutes</option>
                     <option value="hours"   ${s.default_timeout_unit==='hours'?'selected':''}>hours</option>`))}
                ${row('Default interval', '', num('swal-log-interval', 0, s.default_interval ?? '', 'any'))}
                ${row('Default interval unit', '', sel('swal-log-interval-unit',
                    `<option value="seconds" ${(s.default_interval_unit||'seconds')==='seconds'?'selected':''}>seconds</option>
                     <option value="minutes" ${s.default_interval_unit==='minutes'?'selected':''}>minutes</option>
                     <option value="hours"   ${s.default_interval_unit==='hours'?'selected':''}>hours</option>`))}
            </div>
        </div>
        <div class="sm-section sm-section--full">
            <p class="sm-section-title">${t('settings.section.data_display', 'Data Display')}</p>
            <div class="sm-fields-grid">
                ${row('Data Display section max height', 'px (min 200)', num('swal-chart-height', 200, s.chart_height || 600))}
                ${rowCheck('Normalize data by default', 'swal-normalize', s.default_normalize)}
                ${rowCheck('Split by sources by default', 'swal-split-sources', s.default_split_sources)}
                ${rowCheck('Expand time range panel by default', 'swal-range-expanded', s.range_expanded_default)}
                ${rowCheck('Expand export panel by default', 'swal-export-expanded', s.export_expanded_default)}
                ${row('Vertical axis scale', 'Auto fits to data; Custom pins a fixed range',
                    `<select id="swal-yaxis-mode" class="swal2-input" onchange="const c=this.value==='custom';document.getElementById('swal-yaxis-min').disabled=!c;document.getElementById('swal-yaxis-max').disabled=!c;">
                        <option value="auto"   ${(s.y_axis_scale_mode||'auto')==='auto'?'selected':''}>Auto</option>
                        <option value="custom" ${s.y_axis_scale_mode==='custom'?'selected':''}>Custom</option>
                     </select>`)}
                ${row('Vertical axis min', 'Used only when scale is Custom',
                    `<input id="swal-yaxis-min" type="number" step="any" class="swal2-input" value="${s.y_axis_custom_min ?? 0}" ${(s.y_axis_scale_mode||'auto')!=='custom'?'disabled':''}>`)}
                ${row('Vertical axis max', 'Used only when scale is Custom',
                    `<input id="swal-yaxis-max" type="number" step="any" class="swal2-input" value="${s.y_axis_custom_max ?? 0.6}" ${(s.y_axis_scale_mode||'auto')!=='custom'?'disabled':''}>`)}
            </div>
        </div>
        ${(typeof IS_FROZEN !== 'undefined' && IS_FROZEN) ? `
        <div class="sm-section sm-section--full">
            <p class="sm-section-title">${t('settings.section.data_folder', 'Data folder location')}</p>
            <p class="sm-help" style="margin-bottom:6px;">
                Your measurements, calibration curves and reports are stored here.
                Choosing a new location moves your data into an <b>EasyOKAPI</b>
                folder there and switches to it. (The default Documents folder, if
                you ever move away from it, is kept as a backup.) EasyOKAPI must
                restart afterwards.
            </p>
            <div class="sm-row">
                <span class="sm-label">Current folder</span>
                <input id="swal-data-root-current" type="text" class="swal2-input" readonly
                    value="${(typeof DATA_ROOT_INFO !== 'undefined' && DATA_ROOT_INFO) ? DATA_ROOT_INFO.current : ''}">
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px;">
                <button type="button" onclick="changeDataRootFromSettings()"
                    style="font-size:0.8em;padding:4px 12px;border-radius:6px;border:1px solid #d1d5db;background:transparent;cursor:pointer;">
                    Choose folder…
                </button>
                ${(typeof DATA_ROOT_INFO !== 'undefined' && DATA_ROOT_INFO && DATA_ROOT_INFO.is_custom) ? `
                <button type="button" onclick="resetDataRootFromSettings()"
                    style="font-size:0.8em;padding:4px 12px;border-radius:6px;border:1px solid #d1d5db;background:transparent;cursor:pointer;">
                    Reset to default
                </button>` : ''}
            </div>
            <p id="swal-data-root-status" style="font-size:0.8em;color:#888;margin-top:5px;min-height:1.2em;"></p>
        </div>` : ''}
        <div class="sm-section sm-section--full">
            <p class="sm-section-title">${t('settings.section.ai_assistant', 'AI Assistant')}</p>
            ${rowCheck(t('settings.ai_feedback_enabled', 'Collect answer feedback &amp; learn'), 'swal-ai-feedback-enabled', s.ai_feedback_enabled !== false)}
            <p class="sm-help" style="margin-top:2px;">${t('settings.ai_feedback.help', 'Rate AI answers with 👍/👎. Ratings stay on this machine and tune guide matching.')}</p>
            <p id="swal-ai-feedback-summary" class="sm-help" style="margin-top:6px;">${
                t('settings.ai_feedback.summary', '{n} ratings · {m} guides tuned')
                    .replace('{n}', (aiStats && aiStats.ratings) || 0)
                    .replace('{m}', (aiStats && aiStats.guides_tuned) || 0)
            }</p>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px;">
                <button type="button" onclick="exportAiFeedback()"
                    style="font-size:0.8em;padding:4px 12px;border-radius:6px;border:1px solid #d1d5db;background:transparent;cursor:pointer;">
                    ${t('settings.ai_feedback.export', 'Export feedback')}
                </button>
                <button type="button" onclick="resetAiFeedback()"
                    style="font-size:0.8em;padding:4px 12px;border-radius:6px;border:1px solid #d1d5db;background:transparent;cursor:pointer;">
                    ${t('settings.ai_feedback.reset', 'Reset learning')}
                </button>
            </div>
            <p id="swal-ai-feedback-status" style="font-size:0.8em;color:#888;margin-top:5px;min-height:1.2em;"></p>
        </div>
        <div class="sm-section">
            <p class="sm-section-title">${t('settings.section.about', 'About')}</p>
            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
                <span style="font-size:0.85em">Version: <b>v${typeof APP_VERSION !== 'undefined' ? APP_VERSION : '?'}</b></span>
                <button type="button" onclick="checkForUpdateFromSettings()"
                    style="font-size:0.8em;padding:4px 12px;border-radius:6px;border:1px solid #d1d5db;background:transparent;cursor:pointer;">
                    ↺ Check for updates
                </button>
            </div>
            <p id="swal-update-status" style="font-size:0.8em;color:#888;margin-top:5px;min-height:1.2em;"></p>
        </div>
    </div>`;
}

function _readSettingsForm() {
    return {
        theme: document.getElementById('swal-theme').value,
        ui_language: document.getElementById('swal-ui-language').value,
        time_tag_format: document.getElementById('swal-time-format').value,
        file_table_height: Math.max(80, parseInt(document.getElementById('swal-table-height').value, 10) || 240),
        file_sort_order: document.getElementById('swal-file-sort').value,
        default_mode: document.getElementById('swal-mode').value,
        default_window_size: Math.max(2, parseInt(document.getElementById('swal-window-size').value, 10) || 4),
        default_concentration_unit: document.getElementById('swal-concen-unit').value,
        default_subfolder: document.getElementById('swal-subfolder').value || null,
        max_csv_rows: document.getElementById('swal-max-csv-all').checked ? 0 : Math.max(1, parseInt(document.getElementById('swal-max-csv').value, 10) || 1),
        max_json_rows: document.getElementById('swal-max-json-all').checked ? 0 : Math.max(1, parseInt(document.getElementById('swal-max-json').value, 10) || 1),
        event_log_retention_days: document.getElementById('swal-retention-forever').checked ? 0 : Math.max(1, parseInt(document.getElementById('swal-retention-days').value, 10) || 1),
        chart_height: Math.max(200, parseInt(document.getElementById('swal-chart-height').value, 10) || 600),
        default_normalize: document.getElementById('swal-normalize').checked,
        default_split_sources: document.getElementById('swal-split-sources').checked,
        range_expanded_default: document.getElementById('swal-range-expanded').checked,
        export_expanded_default: document.getElementById('swal-export-expanded').checked,
        log_display_height: Math.max(100, parseInt(document.getElementById('swal-log-height').value, 10) || 300),
        log_section_collapsed: document.getElementById('swal-log-collapsed').checked,
        default_notify: document.getElementById('swal-log-notify').checked,
        default_inf_timeout: document.getElementById('swal-log-inf-timeout').checked,
        default_timeout: document.getElementById('swal-log-timeout').value === '' ? null : parseFloat(document.getElementById('swal-log-timeout').value),
        default_timeout_unit: document.getElementById('swal-log-timeout-unit').value,
        default_interval: document.getElementById('swal-log-interval').value === '' ? null : parseFloat(document.getElementById('swal-log-interval').value),
        default_interval_unit: document.getElementById('swal-log-interval-unit').value,
        merge_directory_picker: document.getElementById('swal-merge-picker').checked,
        disable_popups: document.getElementById('swal-disable-popups').checked,
        ai_feedback_enabled: document.getElementById('swal-ai-feedback-enabled').checked,
        y_axis_scale_mode: document.getElementById('swal-yaxis-mode').value,
        y_axis_custom_min: parseFloat(document.getElementById('swal-yaxis-min').value) || 0,
        y_axis_custom_max: parseFloat(document.getElementById('swal-yaxis-max').value) || 0.6,
    };
}

function _fillSettingsForm(s) {
    document.getElementById('swal-theme').value = s.theme;
    document.getElementById('swal-ui-language').value = s.ui_language || 'en';
    document.getElementById('swal-time-format').value = s.time_tag_format || 'iso';
    document.getElementById('swal-table-height').value = s.file_table_height || 240;
    document.getElementById('swal-file-sort').value = s.file_sort_order || 'date_desc';
    document.getElementById('swal-mode').value = s.default_mode;
    document.getElementById('swal-window-size').value = s.default_window_size || 4;
    document.getElementById('swal-concen-unit').value = s.default_concentration_unit || 'ng/µL';
    document.getElementById('swal-subfolder').value = s.default_subfolder || '';
    const csvAll = (s.max_csv_rows || 0) === 0;
    document.getElementById('swal-max-csv-all').checked = csvAll;
    document.getElementById('swal-max-csv').disabled = csvAll;
    document.getElementById('swal-max-csv').value = csvAll ? '' : s.max_csv_rows;
    const jsonAll = (s.max_json_rows || 0) === 0;
    document.getElementById('swal-max-json-all').checked = jsonAll;
    document.getElementById('swal-max-json').disabled = jsonAll;
    document.getElementById('swal-max-json').value = jsonAll ? '' : s.max_json_rows;
    const retForever = (s.event_log_retention_days ?? 30) === 0;
    document.getElementById('swal-retention-forever').checked = retForever;
    document.getElementById('swal-retention-days').disabled = retForever;
    document.getElementById('swal-retention-days').value = retForever ? '' : (s.event_log_retention_days ?? 30);
    document.getElementById('swal-chart-height').value = s.chart_height || 600;
    document.getElementById('swal-normalize').checked = !!s.default_normalize;
    document.getElementById('swal-split-sources').checked = !!s.default_split_sources;
    document.getElementById('swal-range-expanded').checked = !!s.range_expanded_default;
    document.getElementById('swal-export-expanded').checked = !!s.export_expanded_default;
    document.getElementById('swal-log-height').value = s.log_display_height || 300;
    document.getElementById('swal-log-collapsed').checked = !!s.log_section_collapsed;
    document.getElementById('swal-log-notify').checked = s.default_notify !== false;
    document.getElementById('swal-log-inf-timeout').checked = !!s.default_inf_timeout;
    document.getElementById('swal-log-timeout').value = s.default_timeout ?? '';
    document.getElementById('swal-log-timeout-unit').value = s.default_timeout_unit || 'seconds';
    document.getElementById('swal-log-interval').value = s.default_interval ?? '';
    document.getElementById('swal-log-interval-unit').value = s.default_interval_unit || 'seconds';
    document.getElementById('swal-merge-picker').checked = !!s.merge_directory_picker;
    document.getElementById('swal-disable-popups').checked = !!s.disable_popups;
    document.getElementById('swal-ai-feedback-enabled').checked = s.ai_feedback_enabled !== false;
    const yMode = s.y_axis_scale_mode || 'auto';
    document.getElementById('swal-yaxis-mode').value = yMode;
    const yMinEl = document.getElementById('swal-yaxis-min');
    const yMaxEl = document.getElementById('swal-yaxis-max');
    yMinEl.value = s.y_axis_custom_min ?? 0;
    yMaxEl.value = s.y_axis_custom_max ?? 0.6;
    yMinEl.disabled = yMode !== 'custom';
    yMaxEl.disabled = yMode !== 'custom';
}

document.getElementById('settingsBtn').addEventListener('click', async function () {
    const [settingsRes, foldersRes, aiStatsRes] = await Promise.all([
        fetch('/settings').then(r => r.json()).catch(() => null),
        fetch('/get_data_folders').then(r => r.json()).catch(() => []),
        fetch('/ai/feedback/stats').then(r => r.json()).catch(() => null)
    ]);

    const s = (settingsRes && settingsRes.settings) ? settingsRes.settings : (typeof USER_SETTINGS !== 'undefined' ? { ...USER_SETTINGS } : {});
    const folders = (foldersRes && Array.isArray(foldersRes.folders)) ? foldersRes.folders : [];

    const prevUiLang = s.ui_language || 'en';
    const { value: formValues, isConfirmed } = await Swal.fire({
        title: t('settings.title', 'App Settings'),
        width: 'min(92vw, 680px)',
        html: _buildSettingsHTML(s, folders, aiStatsRes),
        showCancelButton: true,
        confirmButtonText: t('common.save', 'Save'),
        cancelButtonText: t('common.cancel', 'Cancel'),
        showDenyButton: true,
        denyButtonText: t('settings.revert_defaults', 'Revert to defaults'),
        returnInputValueOnDeny: false,
        preDeny: () => {
            _fillSettingsForm(SETTINGS_DEFAULTS);
            return false; // keep modal open
        },
        preConfirm: _readSettingsForm,
    });

    if (!isConfirmed || !formValues) return;

    const ok = await fetch('/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formValues)
    }).then(r => r.ok).catch(() => false);

    if (!ok) {
        Swal.fire(t('common.error_title', 'Error'), t('settings.save_failed', 'Could not save settings.'), 'error');
        return;
    }

    logEvent('settings', 'save', formValues);

    // Update the live USER_SETTINGS object
    Object.assign(USER_SETTINGS, formValues);

    // The UI language is applied by re-rendering the page in the new language
    // (the server injects the matching catalog on the next load). Reload now so
    // every static label and dynamic dialog comes up consistently translated.
    if ((formValues.ui_language || 'en') !== prevUiLang) {
        window.location.reload();
        return;
    }

    // Apply "Disable popups" by mirroring it onto the hidden #no-swal-checkbox
    // that the rest of the app reads via getBtnChecked("no-swal-checkbox").
    const noSwalEl = document.getElementById('no-swal-checkbox');
    if (noSwalEl) noSwalEl.checked = !!formValues.disable_popups;

    // Apply theme
    if (formValues.theme === 'auto') {
        localStorage.removeItem('theme');
        _applyTheme(_systemDark.matches);
        _syncToggleIcon(null);
    } else {
        localStorage.setItem('theme', formValues.theme);
        _applyTheme(formValues.theme === 'dark');
        _syncToggleIcon(formValues.theme);
    }

    // Apply table height immediately via CSS variable
    document.documentElement.style.setProperty('--file-table-height', formValues.file_table_height + 'px');

    // Apply window size
    const wsInput = document.getElementById('window-size');
    if (wsInput) wsInput.value = formValues.default_window_size;

    // Apply mode
    const allModeBtns = modeDiv.querySelectorAll('button[data-mode]');
    const targetBtn = Array.from(allModeBtns).find(b => b.getAttribute('data-mode') === formValues.default_mode);
    if (targetBtn) selectButton(targetBtn, allModeBtns, modeDiv);

    // Apply chart height
    const chartEl = document.getElementById('chart-container');
    if (chartEl) chartEl.style.maxHeight = (formValues.chart_height || 600) + 'px';

    // Apply normalize (live; does not retrigger a plot redraw on its own)
    const normEl = document.getElementById('normalize-mode');
    if (normEl) normEl.checked = !!formValues.default_normalize;

    // Apply log display height
    const logEl = document.getElementById('log-display');
    if (logEl) logEl.style.maxHeight = (formValues.log_display_height || 300) + 'px';

    // Apply notify default
    const notifyEl = document.getElementById('notify-me');
    if (notifyEl) notifyEl.checked = formValues.default_notify !== false;

    // Apply default file sort order so the re-render below reflects the new choice
    if (formValues.file_sort_order) AppState.fileSortOrder = formValues.file_sort_order;

    // Re-render file tables with updated row limits / sort order (if a folder is loaded)
    if (typeof updateDirectory === 'function' && AppState.currentDirectory) {
        updateDirectory(AppState.currentDirectory, false);
    }

    // Redraw the plot so a changed vertical-axis scale (Auto ↔ Custom) applies
    // immediately to the currently displayed chart. findYDimension reads the
    // live USER_SETTINGS at draw time, so a re-plot is all that's needed.
    if (AppState.currentFile && typeof toggleMode === 'function') {
        toggleMode();
    }

    // Notify the user the settings were saved (unless popups are disabled).
    if (!getBtnChecked("no-swal-checkbox")) {
        Swal.fire(t('settings.saved_title', 'Settings saved'), t('settings.saved_text', 'Your configurations have been updated.'), 'success');
    }
})

// ── Auto-update ───────────────────────────────────────────────────────────────

let _updateInfo = null;
let _updateCheckInterval = null;
let _bannerWidthObserver = null;

// Cap the banner to the CBBiotec heading width so it never widens the flex-group.
// Reads htbio.offsetWidth live — but only clamps when the heading is actually laid
// out (width > 0). If the banner is shown while #title is still display:none
// (htbio.offsetWidth === 0, e.g. an update check resolves before the user clicks
// "Get Started"), clamping to 0px would collapse the banner to nothing. In that
// case we leave it uncapped; the ResizeObserver below re-applies the real cap the
// moment the heading gains a size.
function _applyBannerWidthCap() {
    const banner = document.getElementById('update-banner');
    if (!banner || banner.classList.contains('hidden')) return;
    const htbio = document.getElementById('htbio');
    const w = htbio ? htbio.offsetWidth : 0;
    if (w > 0) {
        banner.style.maxWidth = w + 'px';
    } else {
        banner.style.removeProperty('max-width');
    }
}

// Recompute the cap whenever the heading's box changes — including the
// display:none → visible transition (offsetWidth 0 → real), which is what makes
// the banner reliable regardless of when the update check resolves.
function _ensureBannerWidthObserver() {
    if (_bannerWidthObserver || typeof ResizeObserver === 'undefined') return;
    const htbio = document.getElementById('htbio');
    if (!htbio) return;
    _bannerWidthObserver = new ResizeObserver(() => _applyBannerWidthCap());
    _bannerWidthObserver.observe(htbio);
}

function _showUpdateBanner(version) {
    const banner = document.getElementById('update-banner');
    const vspan = document.getElementById('update-banner-version');
    const badge = document.getElementById('app-version-badge');
    const isSemver = /^v?\d+\.\d+/.test(version);
    const vLabel = isSemver ? ' · ' + (version.startsWith('v') ? version : 'v' + version) : '';
    if (vspan) vspan.textContent = vLabel;
    if (banner) {
        banner.classList.remove('hidden');
        _ensureBannerWidthObserver();
        _applyBannerWidthCap();
    }
    if (badge) {
        badge.classList.add('app-version-badge--update');
        badge.setAttribute('data-hint', isSemver
            ? `Update available: v${version.replace(/^v/, '')} — click to update`
            : 'Update available — click to update');
    }
}

function _dismissBanner(e) {
    e.stopPropagation();
    document.getElementById('update-banner').classList.add('hidden');
    const badge = document.getElementById('app-version-badge');
    if (!badge || !_updateInfo) return;
    // Same version (re-download scenario): restore badge to default — no pending upgrade
    // Different version (newer online): keep amber badge as a persistent reminder
    const sameVersion = _updateInfo.latest === _updateInfo.current;
    if (sameVersion) {
        badge.classList.remove('app-version-badge--update');
        badge.setAttribute('data-hint', 'Check for updates');
    }
}

// Resolves to true when the update server was reached (status 'success'),
// false on any network/unreachable/error response so callers can retry.
function checkForUpdate(silent = true) {
    return fetch('/update/check')
        .then(r => r.json())
        .then(data => {
            if (!data || data.status !== 'success') {
                if (!silent) {
                    Swal.fire('Update check failed',
                        (data && data.message) || 'Could not reach the update server.',
                        'warning');
                }
                return false;
            }
            _updateInfo = data;
            if (data.update_available) {
                _showUpdateBanner(data.latest);
            } else if (!silent) {
                Swal.fire({
                    title: 'Up to date',
                    text: `You are running the latest version (v${data.current}).`,
                    icon: 'info',
                    confirmButtonText: 'OK',
                });
            }
            return true;
        })
        .catch(() => {
            if (!silent) {
                Swal.fire('Update check failed', 'Could not reach the update server.', 'warning');
            }
            return false;
        });
}

// Run the silent startup check, retrying with backoff while the update server is
// unreachable (common right after first launch, before networking/activation settles).
// Stops retrying once a check succeeds; thereafter a slow periodic re-check keeps the
// banner accurate for updates published while the app stays open.
function scheduleStartupUpdateCheck() {
    const RETRY_DELAYS = [4000, 8000, 15000, 30000]; // ms; attempts at ~4s, 12s, 27s, 57s
    const PERIODIC_MS = 30 * 60 * 1000;              // re-check every 30 min once reachable

    const startPeriodic = (ms) => {
        if (_updateCheckInterval) clearInterval(_updateCheckInterval);
        _updateCheckInterval = setInterval(() => {
            checkForUpdate(true).then(reached => {
                // Once reachable, settle into the slow steady-state cadence.
                if (reached && ms !== PERIODIC_MS) startPeriodic(PERIODIC_MS);
            });
        }, ms);
    };

    let attempt = 0;
    const tryOnce = () => {
        checkForUpdate(true).then(reached => {
            if (reached) {
                startPeriodic(PERIODIC_MS);
            } else if (attempt < RETRY_DELAYS.length) {
                setTimeout(tryOnce, RETRY_DELAYS[attempt++]);
            } else {
                // Stop fast retries but keep a slow background loop so the banner
                // can still appear if the server becomes reachable later.
                startPeriodic(60 * 1000);
            }
        });
    };
    setTimeout(tryOnce, RETRY_DELAYS[attempt++]);
}

// ── Data folder relocation (frozen builds) ───────────────────────────────────
// Two-step, deferred-commit flow. `body` is either {path:<parent>} or {reset:true}.
// Step 1 (POST /data_root) only VALIDATES the choice and reports whether committing
// would move or copy — nothing is moved yet. We confirm with the user, then step 2
// (POST /data_root/restart, _commitDataRoot) does the actual move and relaunches.
// So a Cancel leaves the data exactly where it was — no revert needed.
function _postDataRoot(body, statusEl) {
    Swal.fire({
        title: 'Checking folder…',
        allowOutsideClick: false,
        allowEscapeKey: false,
        didOpen: () => Swal.showLoading(),
    });
    return fetch('/data_root', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    })
        .then(r => r.json().then(d => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
            if (!ok || !d || d.status !== 'success') {
                const msg = (d && d.message) || 'Could not change the data folder.';
                if (statusEl && statusEl.isConnected) statusEl.textContent = msg;
                else Swal.fire('Could not change the data folder', msg, 'error');
                return false;
            }
            Swal.close();
            Swal.fire({
                title: 'Change data folder?',
                html: `Your data will be ${d.moved ? 'moved' : 'copied'} to:<br><b>${d.path}</b><br><br>` +
                    'EasyOKAPI will restart to use the new location and reload ' +
                    'automatically when it comes back up. Nothing changes if you cancel.',
                icon: 'question',
                showCancelButton: true,
                confirmButtonText: 'Restart now',
                cancelButtonText: 'Cancel',
            }).then(res => {
                // Confirm commits the move + relaunch; cancel is a true no-op.
                if (res.isConfirmed) _commitDataRoot(body);
            });
            return true;
        })
        .catch(() => {
            if (statusEl && statusEl.isConnected) statusEl.textContent = 'Could not reach the server.';
            else Swal.fire('Error', 'Could not reach the server.', 'error');
            return false;
        });
}

// Step 2: commit the (already-validated) change and relaunch. Re-sends the original
// {path}/{reset} body to /data_root/restart, which moves the data, then serves the
// restarting page (polls /ping, reloads the tab once the fresh instance is up). A
// committed-move failure comes back as JSON instead of the HTML page.
function _commitDataRoot(body) {
    Swal.fire({
        title: 'Moving data…',
        html: 'This can take a moment for large data folders.',
        allowOutsideClick: false,
        allowEscapeKey: false,
        didOpen: () => Swal.showLoading(),
    });
    logEvent('settings', 'data_root', body);
    fetch('/data_root/restart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ mode: AppState.lightDisplay ? 'light' : 'dark' }, body))
    })
        .then(async r => {
            const ct = r.headers.get('content-type') || '';
            if (r.ok && ct.includes('text/html')) {
                const html = await r.text();
                document.open(); document.write(html); document.close();
                return;
            }
            const d = await r.json().catch(() => null);
            Swal.fire('Could not change the data folder',
                (d && d.message) || 'Please try again.', 'error');
        })
        .catch(() => Swal.fire('Error', 'Could not reach the server.', 'error'));
}

// Folder navigator dialog. Resolves to the absolute path the user selects, or
// null if cancelled. Data will be moved into an EasyOKAPI subfolder of it.
async function pickDataRootFolder(startPath) {
    let cur = startPath || '';

    async function load(p) {
        const url = '/browse_dirs' + (p ? ('?path=' + encodeURIComponent(p)) : '');
        return fetch(url).then(r => r.json()).catch(() => null);
    }

    function rowsHtml(data) {
        if (data.is_drives) {
            return data.dirs.map(d =>
                `<div class="fb-item" data-path="${d.path.replace(/"/g, '&quot;')}">🖴 ${d.name}</div>`
            ).join('') || '<div class="fb-empty">No drives found.</div>';
        }
        if (!data.dirs.length) return '<div class="fb-empty">No sub-folders here.</div>';
        return data.dirs.map(d =>
            `<div class="fb-item" data-path="${d.path.replace(/"/g, '&quot;')}">📁 ${d.name}</div>`
        ).join('');
    }

    function render(popup, data) {
        cur = data.path || '';
        popup.querySelector('#fb-path').textContent = data.is_drives ? 'Select a drive' : (cur || '/');
        popup.querySelector('#fb-list').innerHTML = rowsHtml(data);
        const upBtn = popup.querySelector('#fb-up');
        upBtn.dataset.parent = (data.parent == null ? '' : data.parent);
        upBtn.disabled = (data.parent == null);
        upBtn.style.opacity = upBtn.disabled ? '0.4' : '1';
        // Selecting is meaningful only inside a real folder (not the drive list).
        const confirmBtn = Swal.getConfirmButton();
        if (confirmBtn) confirmBtn.style.display = data.is_drives ? 'none' : '';
        popup.querySelectorAll('.fb-item').forEach(el => {
            el.addEventListener('click', async () => {
                const next = await load(el.dataset.path);
                if (next && next.status === 'success') render(popup, next);
            });
        });
    }

    const result = await Swal.fire({
        title: 'Change folder',
        width: 'min(92vw, 560px)',
        html: `
            <style>
              .fb-item{padding:6px 8px;border-radius:6px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
              .fb-item:hover{background:rgba(99,102,241,0.15);}
              .fb-empty{padding:10px;color:#888;text-align:center;}
            </style>
            <div style="text-align:left;font-size:0.85em;">
              <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;">
                <button type="button" id="fb-up" class="swal2-styled"
                    style="margin:0;padding:4px 10px;font-size:0.9em;background:#6366f1;">⬆ Up</button>
                <span id="fb-path" style="word-break:break-all;color:#555;"></span>
              </div>
              <div id="fb-list" style="max-height:48vh;overflow:auto;border:1px solid #d1d5db;border-radius:8px;padding:4px;"></div>
              <p style="margin:8px 0 0;color:#888;">An <b>EasyOKAPI</b> folder will be created inside the selected folder.</p>
            </div>`,
        showCancelButton: true,
        confirmButtonText: 'Select this folder',
        cancelButtonText: 'Cancel',
        didOpen: async () => {
            const popup = Swal.getPopup();
            popup.querySelector('#fb-up').addEventListener('click', async (e) => {
                const parent = e.currentTarget.dataset.parent || '';
                const next = await load(parent);
                if (next && next.status === 'success') render(popup, next);
            });
            Swal.showLoading();
            const data = await load(cur);
            Swal.hideLoading();
            if (data && data.status === 'success') render(popup, data);
            else popup.querySelector('#fb-list').innerHTML = '<div class="fb-empty">Could not open this folder.</div>';
        },
        preConfirm: () => cur || null,
    });

    return result.isConfirmed ? (result.value || null) : null;
}

async function changeDataRootFromSettings() {
    const statusEl = document.getElementById('swal-data-root-status');
    const start = (typeof DATA_ROOT_INFO !== 'undefined' && DATA_ROOT_INFO) ? DATA_ROOT_INFO.current : '';
    const chosen = await pickDataRootFolder(start);
    if (!chosen) return;
    _postDataRoot({ path: chosen }, statusEl);
}

function resetDataRootFromSettings() {
    const statusEl = document.getElementById('swal-data-root-status');
    _postDataRoot({ reset: true }, statusEl);
}

// Download the AI feedback log + learned weights as a zip (user-controlled archive).
function exportAiFeedback() {
    const a = document.createElement('a');
    a.href = '/ai/feedback/export';
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
    const statusEl = document.getElementById('swal-ai-feedback-status');
    if (statusEl) statusEl.textContent = t('settings.ai_feedback.export_done', 'Archive downloaded.');
}

// Reset learning: clear the rating log + learned guide weights on this machine.
async function resetAiFeedback() {
    const res = await Swal.fire({
        title: t('settings.ai_feedback.reset_confirm_title', 'Reset AI learning?'),
        text: t('settings.ai_feedback.reset_confirm_text', 'This deletes all ratings and learned guide weights on this machine. This cannot be undone.'),
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: t('settings.ai_feedback.reset', 'Reset learning'),
        cancelButtonText: t('common.cancel', 'Cancel'),
        confirmButtonColor: '#d33',
    });
    if (!res.isConfirmed) return;
    const statusEl = document.getElementById('swal-ai-feedback-status');
    const ok = await fetch('/ai/feedback/reset', { method: 'POST' }).then(r => r.ok).catch(() => false);
    if (ok) {
        const summary = document.getElementById('swal-ai-feedback-summary');
        if (summary) summary.textContent = t('settings.ai_feedback.summary', '{n} ratings · {m} guides tuned')
            .replace('{n}', 0).replace('{m}', 0);
        if (statusEl) statusEl.textContent = t('settings.ai_feedback.reset_done', 'AI feedback and learned weights cleared.');
    } else if (statusEl) {
        statusEl.textContent = t('settings.save_failed', 'Could not save settings.');
    }
}

function checkForUpdateFromSettings() {
    const statusEl = document.getElementById('swal-update-status');
    if (statusEl) statusEl.textContent = 'Checking…';

    function _availableLabel(v) {
        return /^v?\d+\.\d+/.test(v) ? 'v' + v.replace(/^v/, '') + ' is available' : 'Update available';
    }

    if (_updateInfo && _updateInfo.update_available) {
        if (statusEl) statusEl.innerHTML =
            `<span style="color:#f59e0b;font-weight:600">↑ ${_availableLabel(_updateInfo.latest)}.</span> ` +
            `<a href="#" onclick="Swal.close();setTimeout(showUpdateModal,200);return false" style="color:#f59e0b">Update Now →</a>`;
        return;
    }

    fetch('/update/check')
        .then(r => r.json())
        .then(data => {
            if (!data || data.status !== 'success') {
                if (statusEl) statusEl.textContent = (data && data.message) || 'Could not reach the update server.';
                return;
            }
            _updateInfo = data;
            if (data.update_available) {
                _showUpdateBanner(data.latest);
                if (statusEl) statusEl.innerHTML =
                    `<span style="color:#f59e0b;font-weight:600">↑ ${_availableLabel(data.latest)}.</span> ` +
                    `<a href="#" onclick="Swal.close();setTimeout(showUpdateModal,200);return false" style="color:#f59e0b">Update Now →</a>`;
            } else {
                if (statusEl) statusEl.innerHTML =
                    `<span style="color:#22c55e">✓ v${data.current} is the latest version.</span>`;
            }
        })
        .catch(() => {
            if (statusEl) statusEl.textContent = 'Could not reach the update server.';
        });
}

function showUpdateModal() {
    if (!_updateInfo) {
        checkForUpdate(false);
        return;
    }
    if (!_updateInfo.update_available) {
        Swal.fire({
            title: 'Up to date',
            text: `You are running the latest version (v${_updateInfo.current}).`,
            icon: 'info',
            confirmButtonText: 'OK',
        });
        return;
    }
    const _latestIsSemver = /^v?\d+\.\d+/.test(_updateInfo.latest);
    const _latestLabel = _latestIsSemver
        ? 'v' + _updateInfo.latest.replace(/^v/, '')
        : null;
    const notes = _updateInfo.release_notes
        ? `<p style="text-align:left;font-size:0.85em;margin-top:8px;white-space:pre-wrap">${_updateInfo.release_notes}</p>`
        : '';
    Swal.fire({
        title: _latestLabel ? `Update available: ${_latestLabel}` : 'Update available',
        html: `<p>Current version: <b>v${_updateInfo.current}</b></p>
               ${_latestLabel ? `<p>Latest version: <b>${_latestLabel}</b></p>` : ''}
               ${notes}
               <p style="font-size:0.82em;color:#888;margin-top:8px">
                 After the update is applied, EasyOKAPI will close so you can relaunch it.</p>`,
        icon: 'info',
        showCancelButton: true,
        confirmButtonText: 'Update Now',
        cancelButtonText: 'Later',
        confirmButtonColor: '#f59e0b',
    }).then(result => {
        if (result.isConfirmed) _applyUpdate();
    });
}

function _applyUpdate() {
    let progressHtml = `
        <div style="text-align:left">
            <p id="upd-label" style="font-size:0.9em;margin-bottom:6px">Starting...</p>
            <div style="background:#e5e7eb;border-radius:6px;overflow:hidden;height:14px">
                <div id="upd-bar" style="background:#f59e0b;height:100%;width:0%;transition:width 0.3s"></div>
            </div>
            <p id="upd-pct" style="font-size:0.75em;color:#888;margin-top:4px">0%</p>
        </div>`;

    Swal.fire({
        title: 'Updating Easy OKAPI...',
        html: progressHtml,
        allowOutsideClick: false,
        allowEscapeKey: false,
        showConfirmButton: false,
        didOpen: () => {
            const es = new EventSource('/update/apply');
            // EventSource only supports GET; we use a POST fetch + manual SSE parse instead.
            es.close();

            fetch('/update/apply', { method: 'POST' }).then(resp => {
                const reader = resp.body.getReader();
                const decoder = new TextDecoder();
                let buf = '';

                function readChunk() {
                    reader.read().then(({ done, value }) => {
                        if (done) return;
                        buf += decoder.decode(value, { stream: true });
                        const lines = buf.split('\n');
                        buf = lines.pop();
                        lines.forEach(line => {
                            if (!line.startsWith('data: ')) return;
                            const raw = line.slice(6).trim();
                            if (raw === '[DONE]') return;
                            try {
                                const evt = JSON.parse(raw);
                                const bar = document.getElementById('upd-bar');
                                const lbl = document.getElementById('upd-label');
                                const pct = document.getElementById('upd-pct');
                                if (bar) bar.style.width = (evt.pct || 0) + '%';
                                if (lbl) lbl.textContent = evt.label || '';
                                if (pct) pct.textContent = (evt.pct || 0) + '%';
                                if (evt.done) {
                                    // Auto-restart is unreliable, so finalize by shutting the
                                    // server down and showing a "please relaunch" page that
                                    // closes this tab (mirrors the shutdown flow).
                                    const mode = AppState.lightDisplay ? 'light' : 'dark';
                                    fetch('/update/finalize', {
                                        method: 'POST',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ mode }),
                                    })
                                        .then(resp => resp.text())
                                        .then(html => {
                                            document.open();
                                            document.write(html);
                                            document.close();
                                        })
                                        .catch(() => { window.location.href = '/goodbye'; });
                                }
                                if (evt.error) {
                                    Swal.fire('Update failed', evt.label, 'error');
                                }
                            } catch (_) {}
                        });
                        readChunk();
                    }).catch(err => {
                        // A mid-stream network drop otherwise rejects silently
                        // and leaves the progress modal frozen.
                        Swal.fire('Update failed', String(err), 'error');
                    });
                }
                readChunk();
            }).catch(err => {
                Swal.fire('Update failed', String(err), 'error');
            });
        },
    });
}

// Wire up the version badge click
document.addEventListener('DOMContentLoaded', function () {
    const badge = document.getElementById('app-version-badge');
    if (badge) badge.addEventListener('click', showUpdateModal);
    // Silent background check, retried with backoff while the update server is
    // unreachable so the banner still appears on first startup once it responds.
    scheduleStartupUpdateCheck();
});