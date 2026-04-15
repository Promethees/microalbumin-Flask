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
    currentMeasurementMode: modeDiv.getAttribute('data-value'),
    currentFile: null,
    prevFile: null,
    currentJSON: null,
    currentJSONcontent: null,
    refCalPoint: null,
    globalAnalysis: null,
    prevDropdownEntries: null,
    exp_json_content: null,
    processedExpPath: getNativePath(csvPath),
    jsonPath: getNativePath(rootPath, 'json'),
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
        'rgba(44, 136, 115, 1)'
    ],
    quantity_input: temp_quantity_input,

    reset: function () {
        this.myChart = null;
        this.currentMeasurementMode = "kinetics";
        this.currentFile = null;
        this.currentJSON = null;
        this.currentJSONcontent = null;
        this.refCalPoint = null;
        this.globalAnalysis = null;
        this.prevDropdownEntries = null;
        this.exp_json_content = null;
        this.responseData = null;
        this.metaData = null;
        this.globalEstimatedValue = null;
        this.multiSource = false;
        this.numSources = 1;
        if (this.chartInstances) {
            Object.keys(this.chartInstances).forEach(key => delete this.chartInstances[key]);
        }
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
        text: "The Michaelis-Menten function models enzyme kinetics, where \\( x \\) is <span class=\"sel-quantity\" id=\"selected-quantity\"></span>, \\( V_{\\max} \\) is the maximum rate, \\( [S] \\) is <span class=\"sel-quantity\">initial Analyte Concentration</span>, and \\( K_m \\) is the analyte concentration at half \\( V_{\\max} \\)."
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

const clickHandlers = new Map();

function bindButtonToString(buttonId = "#go-to-exp-btn", pathStr = AppState.processedExpPath, changeToCalibrate = true) {
    const selector = buttonId.startsWith('#') ? buttonId.slice(1) : buttonId;
    const el = document.getElementById(selector);
    if (!el) return;

    if (clickHandlers.has(el)) {
        el.removeEventListener('click', clickHandlers.get(el));
    }

    const handler = function () {
        console.log(`${buttonId} clicked, using path:`, pathStr);
        updateDirectory(true, changeToCalibrate);
    };

    el.addEventListener('click', handler);
    clickHandlers.set(el, handler);
}

async function clearCache() {
    try {
        const response = await fetchJSON('/clear_cache', { method: 'POST' });
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
    } catch (error) {
        console.log("Clear cache error:", error);
        $append("log-display", "Error: Failed to clear cache\n");
    }
}

async function checkServerStatus() {
    try {
        await fetchJSON('/ping');
        if (!serverAvailable) {
            console.log('Server is back up, resuming polling...');
            serverAvailable = true;
        }
    } catch (error) {
        if (serverAvailable) {
            console.log('Server is down, pausing polling, clearing cache and resetting state...');
            clearCache();
            serverAvailable = false;
            AppState.reset();
        }
    }
}

window.addEventListener('load', function () {
    AppState.reset();

    // When server is Down, reset global variables
    serverCheckInterval = setInterval(checkServerStatus, 5000);

    initDefaultState();

    // Polling removed in favor of event-driven updates (SocketIO and selectFile)

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

    bindButtonToString("#go-to-exp-btn", AppState.processedExpPath);

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
        'func-desc'
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
    ];

    $hidden(addHidden, true);
    $hidden(removeHidden, false);
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
        'func-desc'
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
        'split-source-section'
    ];

    $hidden(addHidden, true);
    $hidden(removeHidden, false);
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
        'num-sources-section'
    ];

    const removeHidden = [
        'cal-json-exp-section',
        'select-regress-algo',
        'export-coef',
        'func-desc'
    ];

    $hidden(addHidden, true);
    $hidden(removeHidden, false);

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

async function updateDirectory(deselect, changeToCalibrate = false) {
    if (AppState.currentMeasurementMode !== "calibrate") {
        calDiv.setAttribute('data-value', `${AppState.currentMeasurementMode}`);
        calButtons.forEach(button => {
            if (button.getAttribute('data-mode') === AppState.currentMeasurementMode) {
                button.classList.add('selected');
            } else {
                button.classList.remove('selected');
            }
        });
    }

    if (changeToCalibrate) {
        selectButton(modeButtons[2], modeButtons, modeDiv);
        AppState.currentMeasurementMode = "calibrate";
        AppState.currentFile = null;
        calModeBehaviour();
    }

    // Always fetch CSV files to update the table for the current mode
    try {
        const csvResponse = await fetchJSON('/get_csv?request=true');
        console.log("CSV files updated:", csvResponse.files);
        updateFileTable(csvResponse.files, deselect);
    } catch (error) {
        console.error("Error fetching CSV files:", error);
        $showText("error-message", "Error fetching CSV files");
    }

    // Always fetch relevant JSON calibration files for the current mode
    if (AppState.currentMeasurementMode !== "calibrate") {
        try {
            const jsonResponse = await fetchJSON(`/get_json_cal?mode=${encodeURIComponent(AppState.currentMeasurementMode)}&numSources=${encodeURIComponent(AppState.numSources)}`);
            updateJSONTable(jsonResponse.files);
        } catch (error) {
            console.error("Error fetching JSON files:", error);
            $showText("error-message", "Error fetching JSON files");
        }
    }
}

function drawMeasurementChart() {
    fetchData(AppState.currentFile, AppState.currentJSONcontent);
    document.getElementById("cal-time-unit").textContent = getTimeUnitValue().slice(0, -1);
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
    AppState.currentMeasurementMode = mode;
    updateDirectory(true);
    AppState.currentJSON = null;
    AppState.currentJSONcontent = null;
    AppState.currentFile = null;
    document.getElementById("json-display").textContent = "";
    $hidden(["right-deselect-btn"]);

    if (mode === "kinetics") {
        kineticsModeBehaviour();
    } else if (mode === "point") {
        pointModeBehaviour();
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
    updateDirectory(true);
}