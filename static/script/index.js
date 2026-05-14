function initDefaultState() {
    [
        'point-json-exp-section',
        'cal-json-exp-section',
        'select-quantity-section',
        'derived-concentration-section',
        'set-exp-point-section',
        'select-regress-algo',
        'select-time-point',
        'export-coef'
    ].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });

    ['terminate-script-btn', 'go-to-btn'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.remove('blinking');
    });
}

const AppState = {
    myChart: null,
    scriptRunning: false,
    currentMeasurementMode: modeDiv.getAttribute('data-value'),
    currentFile: null,
    prevFile: null,
    currentJSON: null,
    currentJSONcontent: null,
    refCalPoint: null,
    globalAnalysis: null,
    prevDropdownEntries: null,
    exp_json_content: null,
    currentDirectory: DATA_ROOT,
    exportPath: DATA_ROOT,
    processedExpPath: DATA_ROOT,
    processedHidPath: DATA_ROOT,
    jsonPath: JSON_ROOT,
    chartInstances: {},
    responseData: null,
    metaData: null,
    lightDisplay: true,
    globalEstimatedValue: null,
    multiSource: false,
    numSources: 1,
    plotColors: [
        'rgb(75, 192, 192)',
        'rgb(255, 99, 132)',
        'rgba(190, 136, 9, 1)',
        'rgb(54, 162, 235)',
        'rgb(153, 102, 255)',
        'rgba(139, 144, 75, 1)',
        'rgba(228, 87, 246, 1)',
        'rgba(44, 136, 115, 1)',
        'rgba(255, 159, 64, 1)',
        'rgba(199, 199, 199, 1)',
        'rgba(83, 102, 255, 1)',
        'rgba(255, 102, 178, 1)',
        'rgba(60, 179, 113, 1)',
        'rgba(255, 140, 0, 1)',
        'rgba(100, 149, 237, 1)',
        'rgba(216, 191, 216, 1)'
    ],
    quantity_input: temp_quantity_input,
    report_root_path: REPORT_ROOT,

    currentReportSubject: null,
    reset: function () {
        this.myChart = null;
        this.scriptRunning = false;
        this.currentMeasurementMode = "kinetics";
        this.currentFile = null;
        this.currentJSON = null;
        this.currentJSONcontent = null;
        this.refCalPoint = null;
        this.globalAnalysis = null;
        this.prevDropdownEntries = null;
        this.currentReportSubject = null;
        this.exp_json_content = null;
        this.responseData = null;
        this.metaData = null;
        this.globalEstimatedValue = null;
        this.currentDirectory = DATA_ROOT;
        this.exportPath = DATA_ROOT;
        this.multiSource = false;
        this.numSources = 1;
        if (this.chartInstances) {
            Object.keys(this.chartInstances).forEach(key => delete this.chartInstances[key]);
        }
        terminateScript();
    }
};

// Set initial checkbox states and toggle quantity visibility based on passed isFullDisplay
const fullDisplayCheckboxes = document.querySelectorAll('input[id^="full-display-"]');
fullDisplayCheckboxes.forEach(cb => cb.checked = isFullDisplay);
const quantityLabels = document.querySelectorAll('label[id^="quantity-checkboxes-"]');
quantityLabels.forEach(ql => {
    if (isFullDisplay) {
        ql.classList.remove('hidden');
    } else {
        ql.classList.add('hidden');
    }
});

const input = document.getElementById("window-size");


const descriptions = {
    polynomial: {
        title: "Polynomial Function (Second Degree)",
        math: "\\[ [S] = ax^2 + bx + c \\]",
        text: "A second-degree polynomial function, also known as a quadratic function, has the form \\( ax^2 + bx + c \\), where \\( a \\neq 0 \\), \\( [S] \\) is <span class=\"sel-quantity\">Initial Analyte Concentration</span>, \\( x \\) is <span class=\"sel-quantity\" id=\"selected-quantity\"></span>."
    },
    linear: {
        title: "Linear Function",
        math: "\\[ [S] = ax + b \\]",
        text: "A linear function represents a straight line with slope \\( a \\) and y-intercept \\( b \\). It models relationships with a constant rate of change, where \\( [S] \\) is <span class=\"sel-quantity\">Initial Analyte Concentration</span>, \\( x \\) is <span class=\"sel-quantity\" id=\"selected-quantity\"></span>."
    },
    logarithmic: {
        title: "Logarithmic Function",
        math: "\\[ [S] = a \\ln(x + b) + c \\]",
        text: "A logarithmic function, based on the natural logarithm, grows slowly for large \\( x \\). It’s used to model phenomena like growth rates or data with diminishing returns, where \\( [S] \\) is <span class=\"sel-quantity\">Initial Analyte Concentration</span>, \\( x \\) is <span class=\"sel-quantity\" id=\"selected-quantity\"></span>, \\( a \\) scales the curve and \\( b \\), \\( c \\) shifts it along the coordinates."
    },
    exponential: {
        title: "Exponential Function",
        math: "\\[ [S] = a e^{bx} + c \\]",
        text: "An exponential function grows or decays rapidly based on the exponent \\( bx \\). It’s used for processes like population growth or radioactive decay, where \\( [S] \\) is <span class=\"sel-quantity\">Initial Analyte Concentration</span>, \\( x \\) is <span class=\"sel-quantity\" id=\"selected-quantity\"></span>, \\( a \\) is the initial value, \\( b \\) determines the rate, while \\( c \\) shifts it."
    },
    'Michaelis-Menten': {
        title: "Michaelis-Menten Function",
        math: "\\[ [S] = \\frac{K_m x}{V_{\\max} - x} \\]",
        text: "The Michaelis-Menten function models enzyme kinetics, where \\( x \\) is <span class=\"sel-quantity\" id=\"selected-quantity\"></span>, \\( V_{\\max} \\) is the maximum rate, \\( [S] \\) is <span class=\"sel-quantity\">Initial Analyte Concentration</span>, and \\( K_m \\) is the analyte concentration at half \\( V_{\\max} \\)."
    }
};

input.addEventListener("keydown", function (e) {
    // Allow: ArrowUp, ArrowDown, Tab, etc.
    if (
        ["ArrowUp", "ArrowDown", "Tab"].includes(e.key)
    ) return;

    // Prevent all other key presses
    e.preventDefault();
});

function bindButtonToString(buttonId = "#go-to-exp-btn", pathStr = AppState.processedExpPath, changeToCalibrate = true) {
    $(buttonId).off('click').on('click', function () {
        console.log(`${buttonId} clicked, using path:`, pathStr);
        updateDirectory(pathStr, true, changeToCalibrate);
    });
}

function clearCache() {
    $.ajax({
        url: '/clear_cache',
        type: 'POST',
        success: function (response) {
            if (response.status === 'success' && response.action === 'clear_storage') {
                // Clear localStorage and sessionStorage
                localStorage.clear();
                sessionStorage.clear();
                $append("log-display", "Client-side cache cleared.\n");
                // Optionally reload the page to ensure fresh content
                window.location.reload(true); // true forces reload from server, bypassing cache
            } else {
                $append("log-display", `Error clearing cache: ${response.message}\n`);
            }
        },
        error: function (jqXHR, textStatus, errorThrown) {
            console.log("Clear cache AJAX error:", textStatus, errorThrown);
            $append("log-display", "Error: Failed to clear cache\n");
        }
    });
}

function checkServerStatus() {
    $.get('/ping')
        .done(function () {
            if (!serverAvailable) {
                console.log('Server is back up, resuming polling...');
                serverAvailable = true;
            }
        })
        .fail(function () {
            if (serverAvailable) {
                console.log('Server is down, pausing polling, clearing cache and resetting state...');
                clearCache();
                serverAvailable = false;
                AppState.reset();
            }
        });
}

$(document).ready(function () {
    AppState.reset();

    // When server is Down, reset global variables
    serverCheckInterval = setInterval(checkServerStatus, 5000);

    initDefaultState();

    // Apply button text shrinking on page load
    setTimeout(() => shrinkAllButtonsToFit(), 100);

    // Load data subfolders into the picker and selects
    loadDataFolders();

    // Poll logs every 2 seconds if script is running
    logInterval = setInterval(function () {
        if (!serverAvailable) return;
        if (AppState.scriptRunning) {
            fetchLogs();
        }
    }, 2000);

    // Periodically update file table every 0.5 seconds
    updateInterval = setInterval(function () {
        if (!serverAvailable) return;
        updateDirectory(AppState.currentDirectory, false);

        if (AppState.currentFile) {
            if (AppState.currentFile !== AppState.prevFile) {
                if (AppState.scriptRunning) {
                    // console.log("Live update: Nullifying prevFile to force redraw");
                    // Nullify previous file so that graphics can be redrawn
                    AppState.prevFile = null;
                    drawMeasurementChart();
                } else {
                    AppState.prevFile = AppState.currentFile;
                }
            }
        }

        if (!AppState.currentJSON) {
            $hidden(["derived-concentration-section"]);
        }


    }, 500);

    // Add click event to each button
    modeButtons.forEach(mode => {
        mode.addEventListener('click', () => {
            selectButton(mode, modeButtons, modeDiv);
            switchingModes(modeDiv.getAttribute('data-value'));
            if (modeDiv.getAttribute('data-value') === "calibrate") {
                $hidden(["num-sources-section"]);
            }
            deselectFile();
            deselectFile("#json-table");
        });
    });

    document.getElementById("cal-json-exp-section").addEventListener("change", () => {
        AppState.currentFile = null;
    });

    calButtons.forEach(cal => {
        cal.addEventListener('click', () => {
            selectButton(cal, calButtons, calDiv);
            switchingCalModes(calDiv.getAttribute('data-value'));
            deselectFile();
        })
    })

    document.getElementById('data-display-section')
        .classList.toggle('hidden', !AppState.currentFile);

    // bindButtonToString("#go-to-exp-btn", AppState.processedExpPath);
    // bindButtonToString("#go-to-btn", AppState.processedHidPath, false);

    // Initialize dynamic widths for range inputs
    ['range-value-start', 'range-value-end'].forEach(id => {
        const el = document.getElementById(id);
        if (el && typeof adjustInputWidth === 'function') {
            adjustInputWidth(el);
        }
    });

    const select = document.getElementById("exp-json-regress-algo");
    const selected = select.value;
    const desc = descriptions[selected];
    document.getElementById("func-desc").innerHTML = `
        <h2>${desc.title}</h2>
        <p>${desc.math}</p>
        <p>${desc.text}</p>
      `;
    MathJax.typeset();
    if (calDiv.getAttribute('data-value') === "kinetics") {
        const sel_quant = document.querySelector("#regressed-quantity");
        document.querySelector("#selected-quantity").textContent = sel_quant.options[sel_quant.selectedIndex].dataset.original;
    } else {
        const sel_time = document.querySelector("#regressed-time-point");
        if (sel_time.value) {
            document.querySelector("#selected-quantity").textContent = "Endpoint Value at " + sel_time.value + " minute";
        } else {
            document.querySelector("#selected-quantity").textContent = "Endpoint Value";
        }
    }

    // Re-apply button text shrinking on window resize
    window.addEventListener('resize', () => {
        clearTimeout(window.resizeTimer);
        window.resizeTimer = setTimeout(() => shrinkAllButtonsToFit(), 250);
    });
});

function kineticsModeBehaviour() {
    const addHidden = [
        'select-quantity-section',
        'point-json-exp-section',
        'cal-json-exp-section',
        'set-exp-point-section',
        'select-time-point',
        'select-regress-algo',
        'export-coef',
        'func-desc',
        'report-console-section'
    ];

    const removeHidden = [
        'window-size-section',
        'cal-json-sel-section',
        'kinetics-lines',
        'json-display',
        'export-analysis',
        'range-display',
        'log-hid-data',
        'source-options',
        'normalize-mode-section',
        'select-source-to-export',
        'split-source-section',
        'top-left-dir-section',
        'main-directory-section',
    ];

    $hidden(addHidden, true);
    $hidden(removeHidden, false);
    const header = document.getElementById("file-selection-header");
    if (header) header.innerText = "File Selection";
    const tableHeader = document.getElementById("file-table-header-name");
    if (tableHeader) tableHeader.innerText = "File Name";
    const searchInput = document.getElementById("file-search");
    if (searchInput) searchInput.placeholder = "Search CSV files...";
}


function reportModeBehaviour() {
    const addHidden = [
        'point-json-exp-section',
        'cal-json-exp-section',
        'select-quantity-section',
        'derived-concentration-section',
        'set-exp-point-section',
        'select-regress-algo',
        'select-time-point',
        'export-coef',
        'window-size-section',
        'cal-json-sel-section',
        'kinetics-lines',
        'json-display',
        'export-analysis',
        'range-display',
        'log-hid-data',
        'source-options',
        'normalize-mode-section',
        'select-source-to-export',
        'split-source-section',
        'data-display-section',
        'num-sources-section',
        'top-left-dir-section',
        'main-directory-section'
    ];

    const removeHidden = [
        'report-console-section',
        'file-selection'
    ];

    $hidden(addHidden, true);
    $hidden(removeHidden, false);

    // Reposition/Focus folder browser
    document.getElementById("file-selection").classList.remove('hidden');
    document.getElementById("report-console-section").classList.add('hidden');

    // Update Header
    document.getElementById("file-selection-header").innerText = "Folder Selection";
    document.getElementById("file-search").placeholder = "Search subject folders...";
}

function pointModeBehaviour() {
    const addHidden = [
        'window-size-section',
        'select-quantity-section',
        'point-json-exp-section',
        'kinetics-lines',
        'cal-json-exp-section',
        'select-time-point',
        'select-regress-algo',
        'export-coef',
        'func-desc',
        'report-console-section'
    ];

    const removeHidden = [
        'cal-json-sel-section',
        'json-display',
        'export-analysis',
        'set-exp-point-section',
        'range-display',
        'log-hid-data',
        'source-options',
        'normalize-mode-section',
        'select-source-to-export',
        'split-source-section',
        'top-left-dir-section',
        'main-directory-section'
    ];

    $hidden(addHidden, true);
    $hidden(removeHidden, false);
    const header = document.getElementById("file-selection-header");
    if (header) header.innerText = "File Selection";
    const tableHeader = document.getElementById("file-table-header-name");
    if (tableHeader) tableHeader.innerText = "File Name";
    const searchInput = document.getElementById("file-search");
    if (searchInput) searchInput.placeholder = "Search CSV files...";
}




function calModeBehaviour() {
    const addHidden = [
        'point-json-exp-section',
        'cal-json-sel-section',
        'kinetics-lines',
        'json-display',
        'export-analysis',
        'range-display',
        'full-display-section',
        'split-source-section',
        'log-hid-data',
        'window-size-section',
        'source-options',
        'normalize-mode-section',
        'select-source-to-export',
        'source-options',
        'num-sources-section',
        'report-console-section'
    ];

    const removeHidden = [
        'cal-json-exp-section',
        'select-regress-algo',
        'export-coef',
        'func-desc',
        'top-left-dir-section',
        'main-directory-section'
    ];

    $hidden(addHidden, true);
    $hidden(removeHidden, false);
    const header = document.getElementById("file-selection-header");
    if (header) header.innerText = "File Selection";
    const tableHeader = document.getElementById("file-table-header-name");
    if (tableHeader) tableHeader.innerText = "File Name";
    const searchInput = document.getElementById("file-search");
    if (searchInput) searchInput.placeholder = "Search CSV files...";

    // Configure range input
    const rangeValue = document.getElementById('range-value');
    if (rangeValue) {
        rangeValue.value = '';
        rangeValue.disabled = true;
        rangeValue.placeholder = 'Disabled in Calibration mode';
    }

    // Conditional behavior
    if (calDiv.getAttribute('data-value') === 'kinetics') calKineticsBehaviour();
    else calPointBehaviour();

    terminateScript();

    AppState.numSources = 1;

    document.getElementById('filter-source').checked = false;
    document.getElementById('normalize-mode').checked = false;
}


function calKineticsBehaviour() {
    document.getElementById('select-quantity-section')?.classList.remove('hidden');
    document.getElementById('select-time-point')?.classList.add('hidden');
}

function calPointBehaviour() {
    document.getElementById('select-quantity-section')?.classList.add('hidden');
    document.getElementById('select-time-point')?.classList.remove('hidden');
}

let isUpdatingDirectory = false;
function updateDirectory(path, deselect, changeToCalibrate = false) {
    if (isUpdatingDirectory && !deselect) {
        return Promise.resolve();
    }
    isUpdatingDirectory = true;

    if (AppState.currentMeasurementMode !== "calibrate" && AppState.currentMeasurementMode !== "report") {
        //Change #cal-mode-select in the background before switching to calibrate mode
        calDiv.setAttribute('data-value', `${AppState.currentMeasurementMode}`);
        calButtons.forEach(button => {
            if (button.getAttribute('data-mode') === AppState.currentMeasurementMode) {
                button.classList.add('selected');
            } else {
                button.classList.remove('selected');
            }
        })
    }
    if (changeToCalibrate) {
        selectButton(modeButtons[2], modeButtons, modeDiv);
        AppState.currentMeasurementMode = "calibrate";
        AppState.currentFile = null;
        calModeBehaviour();
    }

    const browsePromise = new Promise((resolve) => {
        $.post('/browse', { path: path }, function (response) {
            if (response.status === 'success') {
                AppState.currentDirectory = response.path;
                if (getBtnChecked("same-dir-as-data")) {
                    AppState.exportPath = response.path;
                }
                if (typeof updateFolderListSelection === 'function') {
                    updateFolderListSelection(response.path);
                }
                $hidden(["error-message"]);

                // updateFileTable returns a Promise
                if (AppState.currentMeasurementMode !== 'report') {
                    updateFileTable(response.files, deselect).then(resolve);
                } else {
                    resolve();
                }
                if (deselect) {
                    deselectFile();
                }
            } else {
                $showText("error-message", response.message);
                resolve();
            }
        }).fail(function (jqXHR, textStatus, errorThrown) {
            console.log("AJAX error:", textStatus, errorThrown);
            $showText("error-message", "Error updating directory");
            resolve();
        });
    });

    const jsonPromise = new Promise((resolve) => {
        if (AppState.currentMeasurementMode === 'report') {
            $.get('/get_report_subjects', function (response) {
                if (response.status === 'success') {
                    updateReportTable(response.subjects);
                }
                resolve();
            }).fail(resolve);
        } else {
            $.get('/get_json_cal', { mode: AppState.currentMeasurementMode, numSources: AppState.numSources },
                function (response) {
                    updateJSONTable(response.files);
                    resolve();
                }).fail(resolve);
        }
    });

    return Promise.all([browsePromise, jsonPromise]).finally(() => {
        isUpdatingDirectory = false;
    });
}

function drawMeasurementChart() {
    fetchData(AppState.currentFile, AppState.currentJSONcontent);
    document.getElementById("cal-time-unit").textContent = getTimeUnitValue().slice(0, -1);
}

function updateMultiSourceExportOptions() {
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

function switchingModes(mode) {
    const currentDir = AppState.currentDirectory;
    const prevMode = AppState.currentMeasurementMode;
    AppState.currentMeasurementMode = mode;
    if (mode !== 'report' && currentDir) {
        const targetDir = prevMode === 'report' ? DATA_ROOT : currentDir;
        updateDirectory(targetDir, true);
    }
    AppState.currentJSON = null;
    AppState.currentJSONcontent = null;
    AppState.currentFile = null;
    document.getElementById("json-display").textContent = "";
    $hidden(["right-deselect-btn"]);

    const mergeBtn = document.getElementById('merge-file-btn');
    if (mergeBtn) mergeBtn.textContent = mode === 'report' ? 'Merge Subjects' : 'Merge Files';

    if (mode !== 'report') {
        if (typeof clearReportSubject === 'function') clearReportSubject();
    }

    if (mode === "kinetics") {
        kineticsModeBehaviour();
    } else if (mode === "point") {
        pointModeBehaviour();
    } else if (mode === "report") {
        reportModeBehaviour();
        updateDirectory(AppState.report_root_path, true);
    } else {
        calModeBehaviour();
    }

    if (AppState.currentMeasurementMode !== "calibrate") {
        updateMultiSourceExportOptions();
    }
};

function switchingCalModes(mode) {
    if (mode === "point") {
        calPointBehaviour();
    } else {
        calKineticsBehaviour();
    }
    deselectFile();
}