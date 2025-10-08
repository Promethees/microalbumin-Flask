function initDefaultState() {
    $("#point-json-exp-section").addClass("hidden");
    $("#cal-json-exp-section").addClass("hidden");
    $("#select-quantity-section").addClass("hidden");
    $("#derived-concentration-section").addClass("hidden");
    $("#blank-derived-concentration-section").addClass("hidden");
    $("#non-blank-derived-concentration-section").addClass("hidden");
    $("#set-exp-point-section").addClass("hidden");
    $("#select-regress-algo").addClass("hidden");
    $("#select-time-point").addClass("hidden");
    $("#export-coef").addClass("hidden");
    $("#select-exp-blank-type-cal").addClass("hidden");
    $("#terminate-script-btn").removeClass('blinking');
    $("#go-to-btn").removeClass('blinking');
}

const AppState = {
    blankedChart: null,
    nonBlankedChart: null,
    myChart: null,
    scriptRunning: false,
    currentMeasurementMode: "kinetics",
    currentFile: null,
    prevFile: null, 
    currentJSON: null,
    currentJSONcontent: null,
    refCalPoint: null,
    globalAnalysis: null,
    json_msg: 'When fit_type: \n',
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
        'rgba(44, 136, 115, 1)'
    ],
    quantity_input: temp_quantity_input,

    reset: function() {
        this.blankedChart = null;
        this.nonBlankedChart = null;
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

// Append to json_msg
AppState.json_msg += '  + linear: concentration = quantity_json[0]*quantity_value + quantity_json[1]\n';
AppState.json_msg += '  + polynomial: concentration = quantity_json[0]*quantity_value^2 + quantity_json[1]*quantity_value + quantity_json[2]\n';
AppState.json_msg += '  + logarithmic: concentration = quantity_json[0]*loge(quantity_value + quantity_json[1]) + quantity_json[2]\n';
AppState.json_msg += '  + exponential: concentration = quantity_json[0]*e^(quantity_value * quantity_json[1]) + quantity_json[2]\n';
AppState.json_msg += '  + Michaelis-Menten: concentration = (quantity_json[0] * quantity_value) / (quantity_json[1] - quantity_value)\n';

const input = document.getElementById("window-size");


const descriptions = {
      polynomial: {
        title: "Polynomial Function (Second Degree)",
        math: "\\[ [S] = ax^2 + bx + c \\]",
        text: "A second-degree polynomial function, also known as a quadratic function, has the form \\( ax^2 + bx + c \\), where \\( a \\neq 0 \\), \\( [S] \\) is <span class=\"sel-quantity\">Substrate Concentration</span>, \\( x \\) is <span class=\"sel-quantity\" id=\"selected-quantity\"></span>."
      },
      linear: {
        title: "Linear Function",
        math: "\\[ [S] = ax + b \\]",
        text: "A linear function represents a straight line with slope \\( a \\) and y-intercept \\( b \\). It models relationships with a constant rate of change, where \\( [S] \\) is <span class=\"sel-quantity\">Substrate Concentration</span>, \\( x \\) is <span class=\"sel-quantity\" id=\"selected-quantity\"></span>."
      },
      logarithmic: {
        title: "Logarithmic Function",
        math: "\\[ [S] = a \\ln(x + b) + c \\]",
        text: "A logarithmic function, based on the natural logarithm, grows slowly for large \\( x \\). It’s used to model phenomena like growth rates or data with diminishing returns, where \\( [S] \\) is <span class=\"sel-quantity\">Substrate Concentration</span>, \\( x \\) is <span class=\"sel-quantity\" id=\"selected-quantity\"></span>, \\( a \\) scales the curve and \\( b \\), \\( c \\) shifts it along the coordinates."
      },
      exponential: {
        title: "Exponential Function",
        math: "\\[ [S] = a e^{bx} + c \\]",
        text: "An exponential function grows or decays rapidly based on the exponent \\( bx \\). It’s used for processes like population growth or radioactive decay, where \\( [S] \\) is <span class=\"sel-quantity\">Substrate Concentration</span>, \\( x \\) is <span class=\"sel-quantity\" id=\"selected-quantity\"></span>, \\( a \\) is the initial value, \\( b \\) determines the rate, while \\( c \\) shifts it."
      },
      'Michaelis-Menten': {
        title: "Michaelis-Menten Function",
        math: "\\[ [S] = \\frac{K_m x}{V_{\\max} - x} \\]",
        text: "The Michaelis-Menten function models enzyme kinetics, where \\( x \\) is <span class=\"sel-quantity\" id=\"selected-quantity\"></span>, \\( V_{\\max} \\) is the maximum rate, \\( [S] \\) is <span class=\"sel-quantity\">Substrate Concentration</span>, and \\( K_m \\) is the substrate concentration at half \\( V_{\\max} \\)."
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
                $("#log-display").append("Client-side cache cleared.\n");
                // Optionally reload the page to ensure fresh content
                window.location.reload(true); // true forces reload from server, bypassing cache
            } else {
                $("#log-display").append(`Error clearing cache: ${response.message}\n`);
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            console.log("Clear cache AJAX error:", textStatus, errorThrown);
            $("#log-display").append("Error: Failed to clear cache\n");
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
            (parentResponse.parent.split(delimiter).pop() ? 
                `<div onclick="updateDirectory('${parentResponse.parent}', true)" ondblclick="browseDirectory(true)">${parentResponse.parent.split(delimiter).pop()}</div>` : 
                '<div>No parent directory</div>') : 
            '<div>No parent directory</div>';
        $("#parent-dir").html(parentHtml);

        $.get('/get_children', function(childResponse) {
            console.log("Child directories:", childResponse.children);
            const sortedChildren = childResponse.children.sort((a, b) => a.localeCompare(b));
            // Update the child directories display
            let childHtml = sortedChildren.length > 0 ? 
                sortedChildren.map(dir => 
                    `<div onclick="updateDirectory('${dir}', true)" ondblclick="browseDirectory(true)">${dir.split(delimiter).pop()}</div>`
                ).join('') : 
                '<div>No child directories</div>';
            $("#child-dirs").html(childHtml);
        }).fail(function(jqXHR, textStatus, errorThrown) {
            console.log("Error fetching child directories:", textStatus, errorThrown);
            $("#error-message").text("Error fetching child directories").show();
        });
    }).fail(function(jqXHR, textStatus, errorThrown) {
        console.log("Error fetching parent directory:", textStatus, errorThrown);
        $("#error-message").text("Error fetching parent directory").show();
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
        const currentDir = $("#directory").val();
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
            $("#data-display-section").removeClass("hidden");
        } else {
            $("#data-display-section").addClass("hidden");
        }

        if (!AppState.currentJSON) {
            // $("#select-quantity-section").addClass("hidden");
            $("#derived-concentration-section").addClass("hidden");
            $("#blank-derived-concentration-section").addClass("hidden");
            $("#non-blank-derived-concentration-section").addClass("hidden");
        }


    }, 500);

    // Initialize measurement method listener
    $("#measurement-mode").on("change", function() {
        const mode = $(this).val();
        AppState.currentMeasurementMode = mode;
        const currentDir = $("#directory").val();
        if (currentDir) {
            updateDirectory(currentDir, true);
        }
        AppState.currentJSON = null;
        AppState.currentJSONcontent = null;
        AppState.currentFile = null;
        $("#json-display").text("");
        
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
        
    });

    $("#cal-json-exp-section").on("change", function() {
        AppState.currentFile = null;
    });

    $("#cal-mode-select").on("change", function() {
        if ($("#cal-mode-select").val() === "kinetics") {
            calKineticsBehaviour();
        } else {
            calPointBehaviour();
        }
    });

    if (AppState.currentFile) {
        $("#data-display-section").removeClass("hidden");
    } else {
        $('#data-display-section').addClass("hidden");
    }

    bindButtonToString("#go-to-exp-btn", AppState.processedExpPath);
    bindButtonToString("#go-to-btn", AppState.processedHidPath, false);

    const select = document.getElementById("exp-json-regress-algo");
    const selected = select.value;
    const desc = descriptions[selected];  
    document.getElementById("func-desc").innerHTML = `
        <h2>${desc.title}</h2>
        <p>${desc.math}</p>
        <p>${desc.text}</p>
      `;
      MathJax.typeset();
    if ($("#cal-mode-select").val() === "kinetics") {
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
    $("#window-size-section").removeClass("hidden");
    $("#select-quantity-section").addClass("hidden");
    $("#point-json-exp-section").addClass("hidden");
    $("#cal-json-sel-section").removeClass("hidden");
    $("#kinetics-lines").removeClass("hidden");
    $("#cal-json-exp-section").addClass("hidden");
    $("#range-value-start").val("1000").prop("disabled", false);
    $("#range-value-end").val("1000").prop("disabled", false);
    $("#json-display").removeClass("hidden");
    $("#export-analysis").removeClass("hidden");
    $("#set-exp-point-section").addClass("hidden");
    $("#select-exp-blank-type").removeClass("hidden");
    $("#range-display").removeClass("hidden");
    if (!AppState.multiSource)
        $("#concentration-reader-section").removeClass("hidden");
    $("#select-time-point").addClass("hidden");
    $("#select-regress-algo").addClass("hidden");
    $("#export-coef").addClass("hidden");
    $("#log-hid-data").removeClass("hidden");
    $("#select-exp-blank-type-meas").removeClass("hidden");
    $("#select-exp-blank-type-cal").addClass("hidden");
    $("#func-desc").addClass("hidden");
    $("#sensor-options").removeClass("hidden");
    $("#normalize-mode-section").removeClass("hidden");
}

function pointModeBehaviour() {
    $("#window-size-section").addClass("hidden");
    $("#select-quantity-section").addClass("hidden"); 
    $("#point-json-exp-section").addClass("hidden");
    $("#cal-json-sel-section").removeClass("hidden");
    $("#kinetics-lines").addClass("hidden");
    $("#cal-json-exp-section").addClass("hidden");
    $("#range-value-start").val("1000").prop("disabled", false);
    $("#range-value-end").val("1000").prop("disabled", false);
    $("#json-display").removeClass("hidden");
    $("#export-analysis").removeClass("hidden");
    $("#set-exp-point-section").removeClass("hidden");
    $("#select-exp-blank-type").removeClass("hidden");
    $("#range-display").removeClass("hidden");
    if (!AppState.multiSource)
        $("#concentration-reader-section").removeClass("hidden");
    $("#select-time-point").addClass("hidden");
    $("#select-regress-algo").addClass("hidden");
    $("#export-coef").addClass("hidden");
    $("#log-hid-data").removeClass("hidden");
    $("#select-exp-blank-type-meas").removeClass("hidden");
    $("#select-exp-blank-type-cal").addClass("hidden");
    $("#func-desc").addClass("hidden");
    $("#sensor-options").removeClass("hidden");
    $("#normalize-mode-section").removeClass("hidden");
}

function calModeBehaviour() {
    $("#point-json-exp-section").addClass("hidden");
    $("#cal-json-sel-section").addClass("hidden");
    $("#kinetics-lines").addClass("hidden");
    $("#cal-json-exp-section").removeClass("hidden");
    $("#range-value").val("").prop("disabled", true).attr("placeholder", "Disabled in Calibration mode");
    $("#json-display").addClass("hidden");
    $("#export-analysis").addClass("hidden");
    $("#select-exp-blank-type").removeClass("hidden");
    $("#range-display").addClass("hidden");
    $("#concentration-reader-section").addClass("hidden");
    $("#full-display-section").addClass("hidden");
    $("#split-mode-section").removeClass("hidden");
    $("#split-sensor-section").addClass("hidden");
    $("#select-regress-algo").removeClass("hidden");
    $("#export-coef").removeClass("hidden");
    $("#log-hid-data").addClass("hidden");
    $("#select-exp-blank-type-meas").addClass("hidden");
    $("#select-exp-blank-type-cal").removeClass("hidden");
    $("#window-size-section").addClass("hidden");
    $("#func-desc").removeClass("hidden");
    if ($("#cal-mode-select").val() === "kinetics") {
            calKineticsBehaviour();
        } else {
            calPointBehaviour();
        }
    terminateScript(); 
    $("#selected-function").text($("#exp-json-regress-algo").val());
    $("#sensor-options").addClass("hidden");
    AppState.multiSource = false;
    AppState.numSources = 1;
    $("#multi-source").prop("checked", false);
    $("#normalize-mode-section").addClass("hidden");
    $("#normalize-mode").prop("checked", false);
}

function calKineticsBehaviour() {
    $("#select-quantity-section").removeClass("hidden");
    $("#select-time-point").addClass("hidden");
}

function calPointBehaviour() {
    $("#select-quantity-section").addClass("hidden");
    $("#select-time-point").removeClass("hidden");
}

function updateDirectory(path, deselect, changeToCalibrate=false) {
    if(changeToCalibrate) {
        $("#measurement-mode").val("calibrate");
        AppState.currentMeasurementMode = "calibrate";
        AppState.currentFile = null;
        calModeBehaviour();
    } else {
        if (AppState.currentMeasurementMode !== "calibrate") {
            //Change #cal-mode-select in the background before switching to calibrate mode
            $("#cal-mode-select").val(`${AppState.currentMeasurementMode}`); 
        }
    }
    // console.log("Updating directory to:", path);
    $.post('/browse', {path: path}, function(response) {
        if (response.status === 'success') {
            $("#directory").val(response.path);
            $("#directory-top").val(response.path);
            if ($("#same-dir-as-data").is(":checked")) {
                $("#save-dir").val(response.path);
                validatePathName('save-dir');
            }
            if ($("#save-same-dir").is(":checked")) {
                $("#base-dir").val(response.path);
                validatePathName('base-dir');
            }
            $("#error-message").hide();
            updateFileTable(response.files, deselect);
            if (deselect) {
                deselectFile();
            }
        } else {
            $("#error-message").text(response.message).show();
        }
    }).fail(function(jqXHR, textStatus, errorThrown) {
        console.log("AJAX error:", textStatus, errorThrown);
        $("#error-message").text("Error updating directory").show();
    });
    $.get('/get_json_cal', {mode: AppState.currentMeasurementMode, isMultiSource: AppState.multiSource, numSources: AppState.numSources}, 
        function(response) {
            updateJSONTable(response.files);
        }).fail(function(jqXHR, textStatus, errorThrown) {
            console.log("AJAX error fetching JSON files:", textStatus, errorThrown);
            $("#error-message").text("Error fetching JSON files").show();
        });
}

function drawMeasurementChart() {
    fetchData(AppState.currentFile, AppState.currentJSONcontent);
    $("#cal-time-unit").text(unit.slice(0, -1));
}

function updateMultiSourceExportOptions() {
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