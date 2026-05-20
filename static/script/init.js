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

document.getElementById('filter-source').addEventListener('change', function () {
    const numSourcesSelect = document.getElementById('num-sources-section');
    const splitBySource = document.getElementById('split-source-section');
    updateDirectory(AppState.currentDirectory, true);
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
        $.get('/get_num_sources?path=' + AppState.currentDirectory, { request: true }, function (response) {
            const select = document.getElementById('num-sources');
            select.innerHTML = ''; // clear existing options (optional)
            response.num_sources.forEach(num => {
                select.add(new Option(num, num));
            });
            AppState.numSources = response.num_sources[0] || 1;
        });
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
const expSource = document.getElementById('exp-json-source');
expSource.addEventListener('change', updatePointEstimate);

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

    console.log("response Data is", AppState.responseData);

    if (document.getElementById("exp-json-source").value === "ALL") {
        AppState.globalEstimatedValue = [];
        for (let i = 1; i <= AppState.numSources; i++) {
            AppState.globalEstimatedValue.push(
                getEstimatedValue(AppState.responseData, currExpTimePoint * 60, i)
            );
        }
    } else {
        const sourceIndex = getValInt("exp-json-source");
        AppState.globalEstimatedValue = getEstimatedValue(AppState.responseData, currExpTimePoint * 60, sourceIndex);
    }

    console.log("Estimated value is ", AppState.globalEstimatedValue);

    if (isNullOrArrayOfNull(AppState.globalEstimatedValue)) {
        estValError.innerHTML = '<span style="color:red">Error: Reference point is outside the range of the data or not set!</span>';
        estValExp.innerHTML = '';
    } else {
        estValError.innerHTML = '';
        if (Array.isArray(AppState.globalEstimatedValue)) {
            estValExp.innerHTML = `Estimated values at ${currExpTimePoint} minute are: ${AppState.globalEstimatedValue
                    .map((v, i) => `<span style="color:${AppState.plotColors[i]}">[#S${i + 1}] ${v.toFixed(4)} ${AppState.globalAnalysis.meas_unit}</span>`)
                    .join(", ")
                }`;
        } else {
            if (AppState.globalAnalysis && AppState.globalAnalysis.meas_unit !== "NONE")
                estValExp.innerHTML = `Estimated ${AppState.globalAnalysis.meas} value at ${currExpTimePoint} minute is <span style="color:${AppState.plotColors[0]}">${AppState.globalEstimatedValue.toFixed(4)}${AppState.globalAnalysis.meas_unit}</span>`;
            else
                estValExp.innerHTML = `Estimated ${AppState.globalAnalysis.meas} value at ${currExpTimePoint} minute is ${AppState.globalEstimatedValue.toFixed(4)}`;
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

// Initialize by selecting the first button (or adjust logic as needed)
if (modeButtons.length > 0) {
    selectButton(modeButtons[0], modeButtons, modeDiv);
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