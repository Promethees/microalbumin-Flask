document.getElementById("year").textContent = new Date().getFullYear();

// Reflect the currently-loaded file's concentration unit in the #concen-unit
// dropdown. Falls back to ng/µL for legacy files (online keeps no user default).
function syncConcenUnitDropdown() {
    const sel = document.getElementById('concen-unit');
    if (!sel) return;
    const meta = (typeof AppState !== 'undefined') ? AppState.metaData : null;
    const fromMeta = meta && meta['ConcenUnit'] && String(meta['ConcenUnit']).trim();
    sel.value = fromMeta || 'ng/µL';
}

// User changed the concentration unit: re-render the display so labels pick up
// the new unit and use it as the unit for the next calibration export. Label
// change only — it does not rewrite the loaded file.
function onConcenUnitChange() {
    if (typeof toggleMode === 'function') toggleMode();
}

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
// The icon is an emoji drawn with `content:` and is hidden from assistive
// technology, so the control's accessible name has to state the mode itself —
// otherwise the button reads the same in all three states (4.1.2).
function _syncToggleIcon(savedPref) {
    const btn = document.getElementById('toggleButton');
    const mode = savedPref === null ? 'auto' : savedPref;
    btn.dataset.themeMode = mode;

    const container = document.getElementById('toggleContainer');
    if (!container) return;
    const label = {
        light: window.t ? window.t('a11y.theme_light', 'Theme: light. Activate to switch to dark.')
            : 'Theme: light. Activate to switch to dark.',
        dark: window.t ? window.t('a11y.theme_dark', 'Theme: dark. Activate to follow the system.')
            : 'Theme: dark. Activate to follow the system.',
        auto: window.t ? window.t('a11y.theme_auto', 'Theme: system. Activate to switch to light.')
            : 'Theme: system. Activate to switch to light.'
    }[mode];
    if (label) container.setAttribute('aria-label', label);
}

// On startup: apply saved preference or fall back to system preference.
(function initTheme() {
    const saved = localStorage.getItem('theme'); // 'light' | 'dark' | null
    const isDark = saved !== null ? saved === 'dark' : _systemDark.matches;
    _applyTheme(isDark);
    _syncToggleIcon(saved);
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
    toggleMode();
});


document.getElementById('filter-source').addEventListener('change', function () {
    const numSourcesSelect = document.getElementById('num-sources-section');
    const splitBySource = document.getElementById('split-source-section');
    updateDirectory(true);
    AppState.responseData = null;
    AppState.globalAnalysis = null;
    AppState.globalEstimatedValue = null;
    document.getElementById('est-val-error').innerHTML = '';
    document.getElementById('est-val-exp').innerHTML = '';
    document.getElementById('exp-json-time-value').value = '';
    if (this.checked) {
        numSourcesSelect.classList.remove('hidden');
        fetchJSON('/get_num_sources?request=true')
            .then(response => {
                const select = document.getElementById('num-sources');
                select.innerHTML = ''; // clear existing options (optional)
                response.num_sources.forEach(num => {
                    select.add(new Option(num, num));
                });
                AppState.numSources = response.num_sources[0] || 1;
            })
            .catch(error => console.error("Error fetching num sources:", error));
    } else {
        numSourcesSelect.classList.add('hidden');
    }

    if (AppState.currentMeasurementMode !== "calibrate") {
        const selectElement = document.getElementById('exp-json-source');
        // Optional: Clear previous options except "ALL"
        selectElement.innerHTML = '<option value="ALL">ALL</option>';
        for (let i = 1; i <= AppState.numSources; i++) {
            const option = document.createElement('option');
            option.value = i;
            option.textContent = i;
            selectElement.appendChild(option);
        }
    }
});

document.getElementById('num-sources').addEventListener('change', function () {
    AppState.numSources = parseInt(this.value);
    console.log("Number of sources set to:", AppState.numSources);
    updateDirectory(true);
    updateMultiSourceExportOptions();
    deselectFile();
});

document.getElementById('range-value-start').addEventListener('input', validateRangeInput);
document.getElementById('range-value-end').addEventListener('input', validateRangeInput);

document.getElementById('save-file').addEventListener('input', function () {
    validateFileName('save-file');
});
document.getElementById('save-json-file').addEventListener('input', function () {
    validateFileName('save-json-file');
});

const expPoint = document.getElementById('exp-json-time-value');
expPoint.addEventListener('change', updatePointEstimate);
const expSource = document.getElementById('exp-json-source');
expSource.addEventListener('change', updatePointEstimate);

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

    console.log("response Data is", AppState.responseData);

    if (document.getElementById("exp-json-source").value === "ALL") {
        AppState.globalEstimatedValue = [];
        for (let i = 1; i <= AppState.numSources; i++) {
            AppState.globalEstimatedValue.push(
                getEstimatedValue(AppState.responseData, currExpTimeSeconds, i)
            );
        }
    } else {
        const sourceIndex = getValInt("exp-json-source");
        AppState.globalEstimatedValue = getEstimatedValue(AppState.responseData, currExpTimeSeconds, sourceIndex);
    }

    console.log("Estimated value is ", AppState.globalEstimatedValue);

    if (isNullOrArrayOfNull(AppState.globalEstimatedValue)) {
        estValError.innerHTML = '<span style="color:red">Error: Reference point is outside the range of the data or not set!</span>';
        estValExp.innerHTML = '';
    } else {
        estValError.innerHTML = '';
        if (Array.isArray(AppState.globalEstimatedValue)) {
            estValExp.innerHTML = `Estimated values at ${currExpTimePoint} ${timeUnitLabel} are: ${AppState.globalEstimatedValue
                .map((v, i) => `<span style="color:${AppState.plotColors[i]}">[#S${i + 1}] ${v.toFixed(4)} ${AppState.globalAnalysis.meas_unit}</span>`)
                .join(", ")
                }`;
        } else {
            if (AppState.globalAnalysis && AppState.globalAnalysis.meas_unit !== "NONE")
                estValExp.innerHTML = `Estimated ${AppState.globalAnalysis.meas} value at ${currExpTimePoint} ${timeUnitLabel} is <span style="color:${AppState.plotColors[0]}">${AppState.globalEstimatedValue.toFixed(4)}${AppState.globalAnalysis.meas_unit}</span>`;
            else
                estValExp.innerHTML = `Estimated ${AppState.globalAnalysis.meas} value at ${currExpTimePoint} ${timeUnitLabel} is ${AppState.globalEstimatedValue.toFixed(4)}`;
        }
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

function validatePathName(inputId) {
    const input = document.getElementById(inputId);
    const errorElement = document.getElementById(`${inputId}-error`);
    const path = input.value.trim();

    // Reset state
    errorElement.innerHTML = '';
    input.classList.remove('invalid', 'valid');

    if (path === '') {
        errorElement.innerHTML = 'Path cannot be empty<br/>';
        input.classList.add('invalid');
        return false;
    }

    // Check for invalid characters (platform-specific)
    let invalidChars;
    if (path.includes('\\')) {
        // Windows path
        invalidChars = /[*?"<>|\0]/g;
        if (/:/.test(path) && !/^[a-zA-Z]:\\/.test(path)) {
            errorElement.innerHTML = 'Windows paths must start with drive letter (e.g., C:\\)<br/>';
            input.classList.add('invalid');
            return false;
        }
    } else {
        // Unix-like path
        invalidChars = /[\0]/g;
        if (!path.startsWith('/')) {
            errorElement.innerHTML = 'Unix paths must start with /<br/>';
            input.classList.add('invalid');
            return false;
        }
    }

    if (invalidChars.test(path)) {
        errorElement.innerHTML = `Path contains invalid characters<br/>`;
        input.classList.add('invalid');
        return false;
    }

    // Check for reserved names in path components
    const reservedNames = /(^|\/|\\)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$|\\|\/)/i;
    if (reservedNames.test(path)) {
        errorElement.innerHTML = 'Path contains reserved system names<br/>';
        input.classList.add('invalid');
        return false;
    }

    // Check for relative path components
    if (/\.\.($|[\\/])/.test(path)) {
        errorElement.innerHTML = 'Relative paths (..) are not allowed<br/>';
        input.classList.add('invalid');
        return false;
    }

    // Check for trailing slash
    if (/[\\/]$/.test(path)) {
        errorElement.innerHTML = 'Path should not end with a slash<br/>';
        input.classList.add('invalid');
        return false;
    }

    input.classList.add('valid');
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

const modeDiv = document.getElementById('measurement-mode');
const modeButtons = modeDiv.querySelectorAll('button[data-mode]');

// Initialize by selecting the first button (or adjust logic as needed)
if (modeButtons.length > 0) {
    selectButton(modeButtons[0], modeButtons, modeDiv);
}

function selectButton(selectedButton, allButtons, div) {
    div.setAttribute('data-value', selectedButton.getAttribute('data-mode'));
    allButtons.forEach(button => {
        button.classList.remove('selected');
        // The `selected` class is a colour change and nothing more; without
        // `aria-pressed` a screen reader cannot tell which mode is active
        // (WCAG 1.4.1 / 4.1.2).
        button.setAttribute('aria-pressed', 'false');
    });
    selectedButton.classList.add('selected');
    selectedButton.setAttribute('aria-pressed', 'true');
}

const calDiv = document.getElementById('cal-mode-select');
const calButtons = calDiv.querySelectorAll('button[data-mode]');

if (calButtons.length > 0) {
    selectButton(calButtons[0], calButtons, calDiv);
}

const socket = io();

socket.on('update_csv', function () {
    fetchJSON('/get_csv?request=true')
        .then(response => {
            console.log("CSV files updated via SocketIO:", response.files);
            AppState.fileIdentity = response.files_identity || {};
            updateFileTable(response.files, false);

            // Trigger redraw if we are currently viewing this file in live mode
            if (AppState.currentFile) {
                drawMeasurementChart();
            }
        })
        .catch(error => {
            console.error("Fetch error:", error);
            $showText("error-message", "Error fetching CSV files")
        });
});

socket.on('update_json', function (data) {
    if (data.mode === AppState.currentMeasurementMode) {
        fetchJSON(`/get_json_cal?mode=${encodeURIComponent(AppState.currentMeasurementMode)}&numSources=${encodeURIComponent(AppState.numSources)}`)
            .then(response => {
                AppState.jsonIdentity = response.files_identity || {};
                updateJSONTable(response.files, false);
            })
            .catch(error => {
                console.error("Fetch error fetching JSON files:", error);
                $showText("error-message", "Error fetching JSON files")
            });
    }
});