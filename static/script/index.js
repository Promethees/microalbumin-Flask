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
    processedExpPath: getNativePath(rootPath, 'export_data'),
    processedHidPath: getNativePath(rootPath, 'data'),
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

    reset: function() {
        this.myChart = null;
        this.scriptRunning = false;
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

function bindButtonToString(buttonId = "#go-to-exp-btn", pathStr=AppState.processedExpPath, changeToCalibrate=true) {
    $(buttonId).off('click').on('click', function() {
        console.log(`${buttonId} clicked, using path:`, pathStr);
        updateDirectory(pathStr, true, changeToCalibrate);
    });
}

function clearCache() {
    $.ajax({
        url: '/clear_cache',
        type: 'POST',
        success: function(response) {
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
        error: function(jqXHR, textStatus, errorThrown) {
            console.log("Clear cache AJAX error:", textStatus, errorThrown);
            $append("log-display", "Error: Failed to clear cache\n");
        }
    });
}

function checkServerStatus() {
    $.get('/ping')
        .done(function() {
            if (!serverAvailable) {
                console.log('Server is back up, resuming polling...');
                serverAvailable = true;
            }
        })
        .fail(function() {
            if (serverAvailable) {
                console.log('Server is down, pausing polling, clearing cache and resetting state...');
                clearCache();
                serverAvailable = false;
                AppState.reset();
            }
        });
}

$(document).ready(function() {
    AppState.reset();

    // When server is Down, reset global variables
    serverCheckInterval = setInterval(checkServerStatus, 5000);

    initDefaultState();
    $.get('/get_parents', function(parentResponse) {
        console.log("Parent directory:", parentResponse.parent);
        let parentHtml = parentResponse.parent ? 
            (parentResponse.parent.split(DELIMITER).pop() ? 
                `<div onclick="updateDirectory('${parentResponse.parent}', true)" ondblclick="browseDirectory(true)">${parentResponse.parent.split(DELIMITER).pop()}</div>` : 
                '<div>No parent directory</div>') : 
            '<div>No parent directory</div>';
        document.getElementById("parent-dir").innerHTML = parentHtml;

        $.get('/get_children', function(childResponse) {
            console.log("Child directories:", childResponse.children);
            const sortedChildren = childResponse.children.sort((a, b) => a.localeCompare(b));
            // Update the child directories display
            let childHtml = sortedChildren.length > 0 ? 
                sortedChildren.map(dir => 
                    `<div onclick="updateDirectory('${dir}', true)" ondblclick="browseDirectory(true)">${dir.split(DELIMITER).pop()}</div>`
                ).join('') : 
                '<div>No child directories</div>';
            document.getElementById("child-dirs").innerHTML = childHtml;
        }).fail(function(jqXHR, textStatus, errorThrown) {
            console.log("Error fetching child directories:", textStatus, errorThrown);
            $showText("error-message", "Error fetching child directories");
        });
    }).fail(function(jqXHR, textStatus, errorThrown) {
        console.log("Error fetching parent directory:", textStatus, errorThrown);
        $showText("error-message", "Error fetching parent directory");
    });

    // Poll logs every 2 seconds if script is running
    logInterval = setInterval(function() {
        if (!serverAvailable) return;
        if (AppState.scriptRunning) {
            fetchLogs();
        }
    }, 2000);

    // Periodically update file table every 0.5 seconds
    updateInterval = setInterval(function() {
        if (!serverAvailable) return;
        const currentDir = document.getElementById("directory").value;
        if (currentDir) {
            updateDirectory(currentDir, false);
        }

        if (AppState.currentFile) {
            if (AppState.currentFile !== AppState.prevFile) {
                if (AppState.scriptRunning) {
                    // Nullify previous file so that graphics can be redrawn
                    AppState.prevFile = null;
                    drawMeasurementChart();
                } else {
                    AppState.prevFile = AppState.currentFile;
                }
            }
            $hidden(["data-display-section"], false);
        } else {
            $hidden(["data-display-section"]);
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
        'sensor-options',
        'normalize-mode-section',
        'select-sensor-to-export',
        'split-sensor-section',
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
        'sensor-options',
        'normalize-mode-section',
        'select-sensor-to-export',
        'split-sensor-section'
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
        'split-sensor-section',
        'log-hid-data',
        'window-size-section',
        'sensor-options',
        'normalize-mode-section',
        'select-sensor-to-export',
        'sensor-options',
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

function updateDirectory(path, deselect, changeToCalibrate=false) {
    if (AppState.currentMeasurementMode !== "calibrate") {
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
    if(changeToCalibrate) {
        selectButton(modeButtons[2], modeButtons, modeDiv);
        AppState.currentMeasurementMode = "calibrate";
        AppState.currentFile = null;
        calModeBehaviour();
    }
    // console.log("Updating directory to:", path);
    $.post('/browse', {path: path}, function(response) {
        if (response.status === 'success') {
            document.getElementById("directory").value = response.path;
            document.getElementById("directory-top").value = response.path;
            if (getBtnChecked("same-dir-as-data")) {
                document.getElementById("save-dir").value = response.path;
                validatePathName('save-dir');
            }
            if (getBtnChecked("save-same-dir")) {
                document.getElementById("base-dir").value = response.path;
                validatePathName('base-dir');
            }
            $hidden(["error-message"]);
            updateFileTable(response.files, deselect);
            if (deselect) {
                deselectFile();
            }
        } else {
            $showText("error-message", response.message);
        }
    }).fail(function(jqXHR, textStatus, errorThrown) {
        console.log("AJAX error:", textStatus, errorThrown);
        $showText("error-message", "Error updating directory")
    });
    $.get('/get_json_cal', {mode: AppState.currentMeasurementMode, numSources: AppState.numSources}, 
        function(response) {
            updateJSONTable(response.files);
        }).fail(function(jqXHR, textStatus, errorThrown) {
            console.log("AJAX error fetching JSON files:", textStatus, errorThrown);
            $showText("error-message", "Error fetching JSON files")
        });
}

function drawMeasurementChart() {
    fetchData(AppState.currentFile, AppState.currentJSONcontent);
    document.getElementById("cal-time-unit").textContent = getTimeUnitValue().slice(0, -1); 
}

function updateMultiSourceExportOptions() {
    const selectElement = document.getElementById('exp-json-sensor');
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
    const currentDir = document.getElementById("directory").value;
    AppState.currentMeasurementMode = mode;
    if (currentDir) {
        updateDirectory(currentDir, true);
    }
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
    deselectFile();
}