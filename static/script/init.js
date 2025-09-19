// const delimiter = "{{ delimiter }}";
document.getElementById("year").textContent = new Date().getFullYear();

let serverAvailable = true;
let logInterval, updateInterval, serverCheckInterval;

document.getElementById('toggleContainer').addEventListener('click', function() {
    if (document.body.classList.contains('light')) {
        document.body.classList.remove('light');
        document.body.classList.add('dark');
        document.getElementById('toggleButton').classList.add('active');
        AppState.lightDisplay = false;
        toggleMode();
    } else {
        document.body.classList.remove('dark');
        document.body.classList.add('light');
        document.getElementById('toggleButton').classList.remove('active');
        AppState.lightDisplay = true;
        toggleMode();
    }
});

document.getElementById('shutdown-btn').addEventListener('click', function() {
    terminateScript();
    const confirmationMessage = "{{ production_mode }}" === "True"
        ? 'WARNING: Production mode. This will terminate the server process and close the terminal. Continue?'
        : 'Are you sure you want to shutdown the server?';
    
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

document.getElementById('multi-source').addEventListener('change', function() {
    const numSourcesSelect = document.getElementById('num-sources-section');
    const splitByBlanked = document.getElementById('split-mode-section');
    const splitBySensor = document.getElementById('split-sensor-section');
    deselectFile();
    deselectFile("#json-table");
    AppState.responseData = null;
    AppState.globalAnalysis = null;
    AppState.blankedChart = null;
    AppState.nonBlankedChart = null;
    if (this.checked) {
        numSourcesSelect.classList.remove('hidden');
        splitByBlanked.classList.add('hidden');
        splitBySensor.classList.remove('hidden');
        AppState.multiSource = true;
        AppState.numSources = parseInt(document.getElementById('num-sources').value);
        document.getElementById('concentration-reader-section').classList.add('hidden');
    } else {
        numSourcesSelect.classList.add('hidden');
        splitByBlanked.classList.remove('hidden');
        splitBySensor.classList.add('hidden');
        AppState.multiSource = false;
        AppState.numSources = 1;
        document.getElementById('concentration-reader-section').classList.remove('hidden');
    }

    if (AppState.currentMeasurementMode !== "calibrate") {
        if (AppState.multiSource) {
            $("#select-exp-blank-type-meas").addClass("hidden");
            $("#select-sensor-to-export").removeClass("hidden");
            const selectElement = document.getElementById('exp-json-sensor');
            // Optional: Clear previous options except "ALL"
            selectElement.innerHTML = '<option value="ALL">ALL</option>';
            for (let i = 1; i <= AppState.numSources; i++) {
                const option = document.createElement('option');
                option.value = i;
                option.textContent = i;
                selectElement.appendChild(option);
            }
        } else {
            $("#select-exp-blank-type-meas").removeClass("hidden");
            $("#select-sensor-to-export").addClass("hidden");
            document.getElementById('exp-json-sensor').innerHTML = '<option value="ALL">ALL</option>';
        }
    }
});

document.getElementById('num-sources').addEventListener('change', function() {
    AppState.numSources = parseInt(this.value);
    console.log("Number of sources set to:", AppState.numSources);
});

const sameDirCheckbox = document.getElementById("same-dir-as-data");
const saveDirInput = document.getElementById("save-dir");

sameDirCheckbox.addEventListener("change", function() {
    // Enable if unchecked, disable if checked
    saveDirInput.disabled = this.checked;
});

document.getElementById('base-name').addEventListener('input', function() {
    validateFileName('base-name');
});
document.getElementById('save-file').addEventListener('input', function() {
    validateFileName('save-file');
});
document.getElementById('save-json-file').addEventListener('input', function() {
    validateFileName('save-json-file');
});

document.getElementById('base-dir').addEventListener('input', function() {
    validatePathName('base-dir');
});
saveDirInput.addEventListener('input', function() {
    validatePathName('save-dir');
});

const expPoint = document.getElementById('exp-json-time-value');
expPoint.addEventListener('change', function() {
    const estValError = document.getElementById('est-val-error');
    const estValExp = document.getElementById('est-val-exp');
    const currExpBlankType = document.getElementById('exp-json-blank-type').value;
    const currExpTimePoint = $("#exp-json-time-value").val();
    AppState.globalEstimatedValue = getEstimatedValue(AppState.responseData, currExpTimePoint * 60, currExpBlankType);
    console.log("Estimated value is ", AppState.globalEstimatedValue);
    if (!AppState.globalEstimatedValue) {
        estValError.textContent = 'Error: Reference point is outside the range of the data or not set!';
        estValExp.textContent = '';
    } else {
        estValError.textContent = '';
        if (AppState.globalAnalysis && AppState.globalAnalysis.meas_unit !== "NONE")
            estValExp.textContent = `Estimated ${AppState.globalAnalysis.meas} value at ${currExpTimePoint} minute is ${AppState.globalEstimatedValue.toFixed(4)}${AppState.globalAnalysis.meas_unit}`;
        else 
            estValExp.textContent = `Estimated ${AppState.globalAnalysis.meas} value at ${currExpTimePoint} minute is ${AppState.globalEstimatedValue.toFixed(4)}`;
    }
});

function validateFileName(inputId) {
    const input = document.getElementById(inputId);
    const errorElement = document.getElementById(`${inputId}-error`);
    const fileName = input.value.trim();
    
    // Reset state
    errorElement.textContent = '';
    input.classList.remove('invalid', 'valid');
    
    const illegalChars = /[\\/:*?"<>|\0]/g;
    if (illegalChars.test(fileName)) {
        errorElement.textContent = 'File name cannot contain: \\ / : * ? " < > |';
        input.classList.add('invalid');
        return false;
    }
    
    const reservedNames = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i;
    if (reservedNames.test(fileName)) {
        errorElement.textContent = 'Reserved system name (CON, PRN, AUX, etc.)';
        input.classList.add('invalid');
        return false;
    }
    
    if (fileName !== input.value) {
        errorElement.textContent = 'No leading/trailing spaces';
        input.classList.add('invalid');
        return false;
    }
    
    if (fileName.startsWith('.') || fileName.endsWith('.')) {
        errorElement.textContent = 'Cannot start/end with period';
        input.classList.add('invalid');
        return false;
    }
    
    if (fileName.length > 255) {
        errorElement.textContent = 'Max 255 characters';
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
    errorElement.textContent = '';
    input.classList.remove('invalid', 'valid');
    
    if (path === '') {
        errorElement.textContent = 'Path cannot be empty';
        input.classList.add('invalid');
        return false;
    }

    // Check for invalid characters (platform-specific)
    let invalidChars;
    if (path.includes('\\')) {
        // Windows path
        invalidChars = /[*?"<>|\0]/g;
        if (/:/.test(path) && !/^[a-zA-Z]:\\/.test(path)) {
        errorElement.textContent = 'Windows paths must start with drive letter (e.g., C:\\)';
        input.classList.add('invalid');
        return false;
        }
    } else {
        // Unix-like path
        invalidChars = /[\0]/g;
        if (!path.startsWith('/')) {
        errorElement.textContent = 'Unix paths must start with /';
        input.classList.add('invalid');
        return false;
        }
    }

    if (invalidChars.test(path)) {
        errorElement.textContent = `Path contains invalid characters`;
        input.classList.add('invalid');
        return false;
    }

    // Check for reserved names in path components
    const reservedNames = /(^|\/|\\)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$|\\|\/)/i;
    if (reservedNames.test(path)) {
        errorElement.textContent = 'Path contains reserved system names';
        input.classList.add('invalid');
        return false;
    }

    // Check for relative path components
    if (/\.\.($|[\\/])/.test(path)) {
        errorElement.textContent = 'Relative paths (..) are not allowed';
        input.classList.add('invalid');
        return false;
    }

    // Check for trailing slash
    if (/[\\/]$/.test(path)) {
        errorElement.textContent = 'Path should not end with a slash';
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
    errorElement.textContent = '';

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
            errorElement.textContent = 'Interval value is less than zero!';
            timeout.classList.add('invalid');
            interval.classList.add('invalid');
            return false;
        }
    }

    // Case 3: Only one input is provided
    if ((timeoutValue === '' && intervalValue !== '') || (timeoutValue !== '' && intervalValue === '')) {
        errorElement.textContent = 'Please have both of these metrics values or give BOTH blank or check Infinite checkbox';
        timeout.classList.add('invalid');
        interval.classList.add('invalid');
        return false;
    }

    // Case 4: Both inputs provided, compare converted values
    const timeoutSec = parseFloat(timeoutValue) * getTimeUnitMultiplier(timeoutUnit);
    const intervalSec = parseFloat(intervalValue) * getTimeUnitMultiplier(intervalUnit);

    // Check if inputs are valid numbers and interval is less than timeout
    if (isNaN(timeoutSec) || isNaN(intervalSec) || timeoutSec <= 0 || intervalSec < 0) {
        errorElement.textContent = 'Invalid inputs or Timeout/Interval value is less than 0';
        timeout.classList.add('invalid');
        interval.classList.add('invalid');
        return false;
    }

    if (intervalSec >= timeoutSec) {
        errorElement.textContent = 'Interval must be smaller than Timeout! Please adjust your values';
        timeout.classList.add('invalid');
        interval.classList.add('invalid');
        return false;
    }
    
    timeout.classList.add('valid');
    interval.classList.add('valid');
    return true;
}

// Event listener to toggle timeout input disabled state
document.getElementById('inf-timeout').addEventListener('change', function() {
    document.getElementById('timeout').value = '';
    document.getElementById('timeout').disabled = this.checked;
    document.getElementById('timeout-unit').disabled = this.checked;                
});

document.addEventListener("DOMContentLoaded", () => {
        const mainDirSection = document.querySelector("#main-content .section"); // Main Directory section
        const topLeftDirSection = document.querySelector("#top-left-dir-section");  // Top-left Directory section

        const mainDirInput = document.getElementById("directory");
        const topDirInput = document.getElementById("directory-top");

        const parentDirMain = document.getElementById("parent-dir");
        const childDirMain = document.getElementById("child-dirs");
        const parentDirTop = document.getElementById("parent-dir-top");
        const childDirTop = document.getElementById("child-dirs-top");

        // Hide top-left on load
        topLeftDirSection.style.display = "none";

        // Keep inputs synced both ways
        mainDirInput.addEventListener("input", () => {
            topDirInput.value = mainDirInput.value;
        });
        topDirInput.addEventListener("input", () => {
            mainDirInput.value = topDirInput.value;
        });

        // Observer to toggle top-left visibility
        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    // Main visible → hide top-left
                    topLeftDirSection.style.display = "none";
                } else {
                    // Main scrolled away → show top-left
                    topLeftDirSection.style.display = "block";
                    parentDirTop.innerHTML = parentDirMain.innerHTML;
                    childDirTop.innerHTML = childDirMain.innerHTML;
                }
            });
        }, { threshold: 0 });

        observer.observe(mainDirSection);
    });