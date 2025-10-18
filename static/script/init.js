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
    AppState.globalEstimatedValue = null;
    document.getElementById('est-val-error').innerHTML = '';
    document.getElementById('est-val-exp').innerHTML = '';
    document.getElementById('exp-json-time-value').value = '';
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
        $hidden(["select-exp-blank-type-meas"], AppState.multiSource);
        $hidden(["select-sensor-to-export"], !AppState.multiSource);
        if (AppState.multiSource) {
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
            document.getElementById('exp-json-sensor').innerHTML = '<option value="ALL">ALL</option>';
        }
    }
});

document.getElementById('num-sources').addEventListener('change', function() {
    AppState.numSources = parseInt(this.value);
    console.log("Number of sources set to:", AppState.numSources);
    updateDirectory(true);
    updateMultiSourceExportOptions();
});

document.getElementById('range-value-start').addEventListener('input', validateRangeInput);
document.getElementById('range-value-end').addEventListener('input', validateRangeInput);

document.getElementById('save-file').addEventListener('input', function() {
    validateFileName('save-file');
});
document.getElementById('save-json-file').addEventListener('input', function() {
    validateFileName('save-json-file');
});

const expPoint = document.getElementById('exp-json-time-value');
expPoint.addEventListener('change', updatePointEstimate);
const expSensor = document.getElementById('exp-json-sensor');
expSensor.addEventListener('change', updatePointEstimate);

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
    const currExpBlankType = document.getElementById('exp-json-blank-type').value;
    const currExpTimePoint = getValFloat("exp-json-time-value");

    console.log("response Data is", AppState.responseData);

    if (AppState.multiSource) {
        if (document.getElementById("exp-json-sensor").value === "ALL") {
            AppState.globalEstimatedValue = [];
            for (let i = 1; i <= AppState.numSources; i++) {
                AppState.globalEstimatedValue.push(
                    getEstimatedValue(AppState.responseData, currExpTimePoint * 60, i)
                );
            }
        } else {
            const sourceIndex = getValInt("exp-json-sensor");
            AppState.globalEstimatedValue = getEstimatedValue(AppState.responseData, currExpTimePoint * 60, sourceIndex);
        }
    } else {
        AppState.globalEstimatedValue = getEstimatedValue(AppState.responseData, currExpTimePoint * 60, currExpBlankType);
    }

    console.log("Estimated value is ", AppState.globalEstimatedValue);

    if (isNullOrArrayOfNull(AppState.globalEstimatedValue)) {
        estValError.innerHTML = '<span style="color:red">Error: Reference point is outside the range of the data or not set!</span>';
        estValExp.innerHTML = '';
    } else {
        estValError.innerHTML = '';
        if (Array.isArray(AppState.globalEstimatedValue)) {
            estValExp.innerHTML = `Estimated values at ${currExpTimePoint} minute are: ${
                AppState.globalEstimatedValue
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
    });
    selectedButton.classList.add('selected');
}

const calDiv = document.getElementById('cal-mode-select');
const calButtons = calDiv.querySelectorAll('button[data-mode]');

if (calButtons.length > 0) {
    selectButton(calButtons[0], calButtons, calDiv);
}

const socket = io();

socket.on('update_csv', function() {
    $.get('/get_csv', {request: true}, function(response) {
        console.log("give me response files ", response.files);
        updateFileTable(response.files, deselect=false);
    }).fail(function(jqXHR, textStatus, errorThrown) {
        console.log("AJAX error:", textStatus, errorThrown);
        $showText("error-message", "Error fetching CSV files")
    });
});

socket.on('update_json', function(data) {
    if (data.mode === AppState.currentMeasurementMode) {
        $.get('/get_json_cal', {mode: AppState.currentMeasurementMode, isMultiSource: AppState.multiSource, numSources: AppState.numSources}, 
            function(response) {
                updateJSONTable(response.files, deselect=false);
            }).fail(function(jqXHR, textStatus, errorThrown) {
                console.log("AJAX error fetching JSON files:", textStatus, errorThrown);
                $showText("error-message", "Error fetching JSON files")
            });
    }
});