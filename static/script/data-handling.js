function selectFile(fileName, button, tableSelector = "#file-table") {
    // Disable the clicked button temporarily to prevent rapid clicks
    button.disabled = true;
    setTimeout(() => button.disabled = false, 1000);

    // Clear previous selection and highlight the current row
    const table = document.querySelector(tableSelector);
    table.querySelectorAll("tr").forEach(row => row.classList.remove("selected"));
    button.closest("tr").classList.add("selected");

    if (tableSelector === "#file-table") {
        AppState.prevFile = AppState.currentFile;
        AppState.currentFile = fileName;
        clearConcentrationValues();

        $id("copy-file-btn").disabled = false;
        $id("split-mode").checked = false;

        // Hide both canvases
        ["blanked-canvas", "non-blanked-canvas"].forEach(id => {
            const el = $id(id);
            if (el) el.style.display = "none";
        });

        // Reset range values
        $id("range-value-start").value = 0;
        $id("range-value-end").value = 1000;
        $id("range-value-start").disabled = false;
        $id("range-value-end").disabled = false;

        // Check all quantity-checkbox elements
        document.querySelectorAll(".quantity-checkbox").forEach(cb => cb.checked = true);

        processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);
    } 
    else if (tableSelector === "#json-table") {
        AppState.currentJSON = fileName;

        $id("copy-json-btn").disabled = false;
        $hidden(["right-deselect-btn"], false);

        fetchJSON(AppState.currentJSON, (JSON_content, JSON_path) => {
            const display = $id("json-display");
            display.innerHTML = ""; // clear previous content

            const fitType = JSON_content.fit_type || "N/A";
            const measFor = JSON_content.for_meas || "N/A";
            const blankType = JSON_content.for_blank_type || "N/A";
            const mode = AppState.currentMeasurementMode || "N/A";
            const isMenten = fitType.toLowerCase().includes("menten");

            const labelCoefficients = (coefs) => {
                if (!Array.isArray(coefs) || coefs.length === 0) return "—";
                return isMenten
                    ? `Vmax = ${coefs[0]}, Km = ${coefs[1]}`
                    : coefs.map((v, i) => `${String.fromCharCode(97 + i)} = ${v}`).join(", ");
            };

            const formulas = {
                linear: "\\( [S] = a q + b \\)",
                polynomial: "\\( [S] = a q^2 + b q + c \\)",
                logarithmic: "\\( [S] = a \\ln(q + b) + c \\)",
                exponential: "\\( [S] = a e^{q b} + c \\)",
                "michaelis-menten": "\\( [S] = \\dfrac{K_m q}{V_{max} - q} \\)"
            };
            const getFormula = (type) => formulas[type.toLowerCase()] || "No formula available for this fit type.";

            // --- Build tables dynamically ---
            const buildCoefTable = (json) => {
                const table = document.createElement("table");
                table.border = "1";
                table.cellPadding = "1";
                table.cellSpacing = "0";
                table.className = "table";
                table.style = "width:100%; text-align:left; margin-top: 0px; margin-bottom: 1px;";

                const thead = document.createElement("thead");
                thead.innerHTML = `
                    <tr>
                        <th>Parameter</th>
                        <th>Fit Coefficients</th>
                    </tr>
                `;
                const tbody = document.createElement("tbody");

                for (const [key, value] of Object.entries(json)) {
                    if (["fit_type", "for_meas", "for_blank_type"].includes(key)) continue;
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td>${key}</td>
                        <td>${labelCoefficients(value?.fit_coef)}</td>
                    `;
                    tbody.appendChild(tr);
                }

                const heading = document.createElement("h4");
                heading.textContent = "Fitting Coefficients";
                heading.style.margin = "0px 0px 1px 0px";

                table.appendChild(thead);
                table.appendChild(tbody);

                display.appendChild(heading);
                display.appendChild(table);
            };

            const buildInfoTable = (info) => {
                const table = document.createElement("table");
                table.border = "1";
                table.cellPadding = "1";
                table.cellSpacing = "0";
                table.className = "table";
                table.style = "width:100%; text-align:left; margin-top: 0px; margin-bottom: 0px;";

                const tbody = document.createElement("tbody");
                for (const [key, value] of Object.entries(info)) {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `<th style="width:30%;">${key}</th><td>${value}</td>`;
                    tbody.appendChild(tr);
                }

                const heading = document.createElement("h4");
                heading.textContent = "Fit Information";
                heading.style.margin = "0px 0px 1px 0px";

                table.appendChild(tbody);

                display.appendChild(heading);
                display.appendChild(table);
            };

            // --- Build info data ---
            const infoData = {
                "Current Mode": mode,
                "Fit Type": fitType,
                "Formula": getFormula(fitType),
                "[S]": "Substrate Concentration",
                "q": "<em>Quantity value</em> is either <strong>maxRate, Slope, Saturation, Time to Sat</strong>, whichever is set by user.",
                "Measurement For": measFor,
                "Blank Type": blankType
            };

            // Render tables
            buildCoefTable(JSON_content);
            display.appendChild(document.createElement("br"));
            buildInfoTable(infoData);

            // Render math if available
            if (window.MathJax) MathJax.typesetPromise();

            // Update state
            AppState.currentJSONcontent = JSON_content;

            // Display data if file selected
            if (AppState.currentFile) {
                processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);
            }
        });
    }

    // Smoothly scroll to section and blink
    scrollWhenVisible("data-display-section", 1000);
    blinkingItem("chart-container", 3000);
}

function copyFile(tableSelector = "#file-table") {
    const currentFile = tableSelector === "#file-table" ? AppState.currentFile : AppState.currentJSON;

    if (!currentFile) {
        Swal.fire({
            title: 'Error!',
            text: 'No file selected to copy.',
            icon: 'error',
            confirmButtonText: 'OK'
        });
        return;
    }

    const filePath = tableSelector === "#file-table" ? document.getElementById("directory").value : currentFile;

    $.ajax({
        url: '/copy_file',
        method: 'POST',
        data: {
            filepath: filePath,
            filename: currentFile,
            mode: AppState.currentMeasurementMode,
            tabletype: tableSelector,
            isMultiSource: AppState.multiSource,
        },
        success: function(response) {
            if (response.status === 'success') {
                if (getBtnChecked("no-swal-checkbox")) {
                    console.log("File copied successfully:", response.message);
                    if (tableSelector === "#file-table") {
                        updateDirectory(document.getElementById("directory").value);
                    } else if (tableSelector === "#json-table") {
                        updateJSONTable();
                    }
                    return; // Exit if no popup is needed
                }
                // Show success message using SweetAlert2
                Swal.fire({
                    title: 'Success!',
                    text: response.message,
                    icon: 'success',
                    timer: 2000,
                    showConfirmButton: false
                }).then(() => {
                    if (tableSelector === "#file-table") {
                        updateDirectory(document.getElementById("directory").value);
                    } else if (tableSelector === "#json-table") {
                        updateJSONTable();
                    }
                });
            } else {
                // Handle expected error responses from backend
                Swal.fire({
                    title: 'Error!',
                    text: response.message || 'An unknown error occurred while copying the file.',
                    icon: 'error',
                    confirmButtonText: 'OK'
                });
            }
        },
        error: function(xhr, status, error) {
            // Handle AJAX errors (network/server issues)
            let message;
            if (xhr.status === 423) { // HTTPStatus.LOCKED
                message = 'File operation is locked because a process is currently running.';
            } else if (xhr.status === 404) {
                message = 'The file you are trying to copy was not found.';
            } else if (xhr.status === 403) {
                message = 'Permission denied. Please check your file permissions.';
            } else if (xhr.status === 400) {
                message = 'Invalid request. Please check the input data.';
            } else {
                message = 'Unexpected error: ' + (xhr.responseJSON?.message || error);
            }

            Swal.fire({
                title: 'Error!',
                text: message,
                icon: 'error',
                confirmButtonText: 'OK'
            });
        }
    });
}

function processDataDisplay(fileName, jsonFileContent=null) {
    // Proceed with fetching and displaying data
    fetchData(fileName, jsonFileContent);
    updateFileDisplay(fileName);
}


function deselectFile(tableSelector = "#file-table") {
    // Remove "selected" class from all rows
    document.querySelectorAll(`${tableSelector} tr`).forEach(tr => tr.classList.remove("selected"));

    if (tableSelector === "#file-table") {
        AppState.responseData = null;
        destroyCharts();

        // Hide canvases
        ["plot-canvas", "blanked-canvas", "non-blanked-canvas"].forEach(id => {
            const el = $id(id);
            if (el) el.style.display = "none";
        });

        AppState.currentFile = null;

        // Clear analysis text fields
        ["plot-analysis", "blanked-analysis", "non-blanked-analysis"].forEach(id => $text(id, ""));

        updateFileDisplay(AppState.currentFile);
        $disable(["copy-file-btn"], true);

    } else if (tableSelector === "#json-table") {
        AppState.currentJSON = null;
        AppState.currentJSONcontent = null;

        $text("json-display", "");
        processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);

        // Hide all JSON-related sections
        [
            "select-quantity-section",
            "derived-concentration-section",
            "blank-derived-concentration-section",
            "non-blank-derived-concentration-section",
            "point-json-exp-section"
        ].forEach(id => $toggleClass(id, "hidden", true));

        $disable(["copy-json-btn"], true);
        $toggleClass("right-deselect-btn", "hidden", true);
    }
}

function deleteFile(fileName, button, tableSelector = "#file-table") {
    // Check if script is running
    checkScriptStatus().then((isRunning) => {
        if (isRunning || AppState.scriptRunning) {
            Swal.fire({
                title: 'Error!',
                text: 'Cannot delete files while the data collection process is running. Stop the process and try again.',
                icon: 'error',
                confirmButtonText: 'OK'
            }).then(() => {
                blinkingItem('terminate-script-btn', 5000);
            });
            return;
        }

        const skipConfirmation = getBtnChecked("no-swal-checkbox");

        const proceedDelete = () => {
            // Remove the file from the table
            $(button).closest("tr").remove();
            console.log("Deleting file:", fileName, "from table:", tableSelector);

            // Update the AppState
            if (tableSelector === "#file-table") {
                if (AppState.currentFile === fileName) {
                    deselectFile(tableSelector);
                }

                $.post('/delete_file', { 
                    filename: fileName, 
                    path: document.getElementById("directory").value, 
                    tabletype: tableSelector 
                }, handleResponse).fail(handleError);
            } else if (tableSelector === "#json-table") {
                if (AppState.currentJSON === fileName) {
                    deselectFile(tableSelector);
                }

                console.log("Deleting JSON file:", fileName, "from table:", tableSelector);

                $.post('/delete_file', { 
                    filename: fileName, 
                    mode: AppState.currentMeasurementMode, 
                    tabletype: tableSelector,
                    isMultiSource: AppState.multiSource,
                    numSources: AppState.numSources
                }, handleResponse).fail(handleError);
            }
        };

        const handleResponse = (response) => {
            if (response.status === 'success') {
                if (skipConfirmation) {
                    console.log("File deleted successfully:", response.message);
                    return; // Exit if no popup is needed   
                }
                Swal.fire({
                    title: 'Deleted!',
                    text: response.message,
                    icon: 'success',
                    timer: 2000,
                showConfirmButton: false
                });
            } else {
                Swal.fire({
                    title: 'Error!',
                    text: response.message,
                    icon: 'error',
                    confirmButtonText: 'OK'
                }).then(() => {
                    blinkingItem('terminate-script-btn', 5000);
                });
            }
        };

        const handleError = (jqXHR) => {
            let errorMessage = 'An unexpected error occurred while deleting the file';
            if (jqXHR.status === 400) {
                errorMessage = jqXHR.responseJSON?.message || 'Invalid request';
            } else if (jqXHR.status === 403) {
                errorMessage = jqXHR.responseJSON?.message || 'Permission denied while deleting the file';
            } else if (jqXHR.status === 404) {
                errorMessage = jqXHR.responseJSON?.message || 'File not found';
            } else if (jqXHR.status === 423) {
                errorMessage = jqXHR.responseJSON?.message || 'File is currently being used by the data collection process. Stop the process and try again.';
            }
            Swal.fire({
                title: 'Error!',
                text: errorMessage,
                icon: 'error',
                confirmButtonText: 'OK'
            }).then(() => {
                blinkingItem('terminate-script-btn', 5000);
            });
        };

        if (skipConfirmation) {
            proceedDelete();
        } else {
            // Show confirmation dialog using SweetAlert2
            Swal.fire({
                title: 'Are you sure?',
                text: `Do you want to delete ${fileName}? This action cannot be undone.`,
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#d33',
                cancelButtonColor: '#3085d6',
                confirmButtonText: 'Yes, delete it!'
            }).then((result) => {
                if (result.isConfirmed) {
                    proceedDelete();
                }
            });
        }
    });
}

function settingDerivedCon(jsonFile) {
    let derived_section = null;
    let derived_con_text = null;
    switch(jsonFile["for_blank_type"]) {
        case "MIXED":
            derived_section = [];
            derived_con_text = [];
            if (AppState.multiSource) {
                for (let i = 0; i < AppState.numSources; i++) {
                    derived_section.push(document.getElementById(`derived-concentration-section-source-${i}`));
                    derived_con_text.push(document.getElementById(`der-con-value-source-${i}`));
                }
            }
            else { 
                if (!getBtnChecked("split-mode")) {
                    derived_section = document.getElementById('derived-concentration-section');
                    derived_con_text = document.getElementById('der-con-value');
                }
            }
            break;
        case "BLANKED":
            if (getBtnChecked("split-mode")) {
                derived_section = document.getElementById('blank-derived-concentration-section');
                derived_con_text = document.getElementById('blank-der-con-value');
            }
            break;
        case "NON-BLANKED":
            if (getBtnChecked("split-mode")) {
                derived_section = document.getElementById('non-blank-derived-concentration-section');
                derived_con_text = document.getElementById('non-blank-der-con-value');
            }
            break;
    }
    return {
        derived_section: derived_section,
        derived_con_text: derived_con_text
    }
}

// Triggered only after entries is changed, used in Point calibration mode
function populateDropdown(entries, dropdownId = 'regressed-time-point') {
    if (AppState.prevDropdownEntries && arraysEqual(AppState.prevDropdownEntries, entries)) {
        return AppState.prevDropdownEntries;
    }
    const select = document.getElementById(dropdownId);
    // Store current selection
    const currentSelection = select.value;
    while (select.options.length > 1) {
        select.remove(1);
    }

    entries.forEach(entry => {
        const option = document.createElement('option');
        option.value = entry;
        option.textContent = entry;
        select.appendChild(option);
    });

    // Restore selection if it still exists in the new data
    if (currentSelection && entries.includes(currentSelection)) {
        select.value = currentSelection;
    } else {
        select.value = ''; // Reset to default if previous selection is gone
    }
    return entries.sort((a, b) => Number(b) - Number(a));
}

const fetchData = async (filename, jsonFile) => {
    try {
        const response = await fetchDataFromServer(filename);
        return processResponse(response, jsonFile);
    } catch (error) {
        handleFetchError(error, filename);
        return null;
    }
};

const fetchDataFromServer = async (filename) => {
    const directory = document.getElementById("directory").value;
    
    return await $.get('/get_data', {
        file: `${directory}${DELIMITER}${filename}`
    }).fail((xhr, status, errorThrown) => {
        // Create a custom error object with all the details
        const enhancedError = new Error(`Fetch failed for ${filename}`);
        enhancedError.xhr = xhr;
        enhancedError.status = status;
        enhancedError.errorThrown = errorThrown;
        enhancedError.filename = filename;
        enhancedError.directory = directory;
        
        throw enhancedError;
    });
};

function processResponse (response, jsonFile) {
    if (!response.data || response.data.length === 0) {
        handleEmptyData();
        return null;
    }

    // Store response data
    AppState.responseData = response.data;
    AppState.metaData = response.metadata;

    // Update plot
    updatePlotBasedOnMode(jsonFile);

    // Process based on measurement mode
    if (AppState.currentMeasurementMode !== "calibrate") {
        if (jsonFile)
            handleNonCalibrationMode(jsonFile);
    } else {
        handleCalibrationMode();
    }

    return response;
};

function handleNonCalibrationMode(jsonFile) {
    toggleConValueTextbox();
    
    const derivedSettings = settingDerivedCon(jsonFile);
    if (derivedSettings) {
        updateDerivedSections(derivedSettings);
    }

    if (AppState.currentMeasurementMode === "kinetics" && jsonFile) {
        processKineticsMode(jsonFile);
    }
};

function updateDerivedSections ({ derived_section, derived_con_text }) {
    if (AppState.multiSource) {
        handleMultiSource(derived_section, derived_con_text);
    } else {
        handleSingleSource(derived_section, derived_con_text);
    }
};

function handleMultiSource(derived_section, derived_con_text) {
    if (Array.isArray(derived_section)) {
        derived_section.forEach(section => section.classList.remove("hidden"));
        $hidden(["select-quantity-section"], AppState.currentMeasurementMode !== "kinetics");
        derived_con_text.forEach(section => section.classList.add("blinking"));
    } else {
        $hidden(["select-quantity-section"], true);
        derived_section.forEach(section => section.classList.add("hidden"));
    }
};

function handleSingleSource(derived_section, derived_con_text) {
    if (derived_section) {
        derived_section.classList.remove("hidden");
        $hidden(["select-quantity-section"], AppState.currentMeasurementMode !== "kinetics");
        derived_con_text.classList.add("blinking");
    } else {
        $hidden([
            "select-quantity-section",
            "derived-concentration-section",
            "blank-derived-concentration-section",
            "non-blank-derived-concentration-section"
        ]);
    }
};

function processKineticsMode(jsonFile) {
    const conQuantityInput = document.getElementById('regressed-quantity').value;
    const blankType = jsonFile["for_blank_type"];
    const analysisExtraction = calculateKineticValue(conQuantityInput, blankType);

    if (analysisExtraction !== null) {
        updateConcentrationDisplay(analysisExtraction, jsonFile, conQuantityInput);
    }
};

function calculateKineticValue(quantity, blankType) {
    const kineticCalculations = {
        maxrate: val => Array.isArray(val) ? val.map(v => parseFloat(v) * 60) : parseFloat(val) * 60,
        slope: val => Array.isArray(val) ? val.map(v => parseFloat(v) * 60) : parseFloat(val) * 60,
        sat: val => Array.isArray(val) ? val.map(v => parseFloat(v)) : parseFloat(val),
        time_to_sat: val => Array.isArray(val) ? val.map(v => parseFloat(v) / 60) : parseFloat(val) / 60
    };

    const val = getKineticValue(quantity, blankType);
    return val !== null && kineticCalculations[quantity] 
        ? kineticCalculations[quantity](val) 
        : null;
};

function updateConcentrationDisplay(analysisExtraction, jsonFile, conQuantityInput) {
    const { derived_con_text } = settingDerivedCon(jsonFile);
    const coef = jsonFile[conQuantityInput]["fit_coef"];
    const fitType = jsonFile["fit_type"];

    if (Array.isArray(analysisExtraction) && Array.isArray(derived_con_text)) {
        analysisExtraction.forEach((val, idx) => {
            updateSingleConcentration(derived_con_text[idx], val, fitType, coef);
        });
    } else {
        updateSingleConcentration(derived_con_text, analysisExtraction, fitType, coef);
    }
};

function updateSingleConcentration(element, value, fitType, coef) {
    try {
        const calculatedCon = computeFit(value, fitType, coef).toFixed(4);
        element.innerHTML = `${calculatedCon}`;
    } catch (error) {
        console.error("Error computing derived concentration:", error);
        element.innerHTML = `<span style="color: red;">${error.message}</span>`;
    }
};

function handleEmptyData() {
    $hidden(["plot-canvas", "blanked-canvas", "non-blanked-canvas"]);
    const plotAnalysis = document.getElementById("plot-analysis");
    if (plotAnalysis )
        plotAnalysis.innerHTML = 
            `<span style="color: red;">No data available</span>`;
};

function handleFetchError(error) {
    console.group('🚨 Fetch Error Details');
    console.error("Failed to fetch data:", error.message);
    
    if (error.xhr) {
        console.log("📡 XHR Object:", error.xhr);
        console.log("📊 Status:", error.status);
        console.log("❌ Error Thrown:", error.errorThrown);
        
        // Log response text if available
        if (error.xhr.responseText) {
            console.log("📄 Response Text:", error.xhr.responseText);
        }
        
        // Log response headers if available
        if (error.xhr.getAllResponseHeaders) {
            console.log("📋 Response Headers:", error.xhr.getAllResponseHeaders());
        }
        
        // Log status code and text
        console.log("🔢 Status Code:", error.xhr.status);
        console.log("📝 Status Text:", error.xhr.statusText);
    }
    
    if (error.filename) {
        console.log("📁 Requested Filename:", error.filename);
    }
    
    if (error.directory) {
        console.log("📂 Directory:", error.directory);
    }
    
    console.groupEnd();
    
    // You can also add more specific error handling based on status
    if (error.status === 'error' && error.errorThrown) {
        console.warn("⚠️ Possible network or server error:", error.errorThrown);
    } else if (error.xhr && error.xhr.status >= 400 && error.xhr.status < 500) {
        console.warn("⚠️ Client error (4xx):", error.xhr.status);
    } else if (error.xhr && error.xhr.status >= 500) {
        console.error("💥 Server error (5xx):", error.xhr.status);
    }
}

function toggleConValueTextbox() {
    if (!AppState.multiSource) {
        // Process concentration value input
        const conValueInput = document.getElementById('con-value-read');
        const conValueFromFile = AppState.metaData["Concentration"] || "NONE";

        conValueInput.disabled = conValueFromFile.toLowerCase() !== "none";
        conValueInput.value = conValueFromFile !== "NONE" ? conValueFromFile : "";
    } 
    return; 
}

function getKineticValue(property, blankType, multi_source=AppState.multiSource) {
    const analysis = AppState.globalAnalysis;
    switch(blankType) {
        case "MIXED": 
            if (multi_source) {
                let values = [];
                analysis.sources.forEach(source => {
                    values.push(source[property]);
                });
                return values.length > 0 ? values : null;
            }
            return analysis ? analysis[property] : null;
        case "BLANKED": return analysis ? analysis[`${property}_blanked`] : null;
        case "NON-BLANKED": return analysis ? analysis[`${property}_non_blanked`] : null;
        default: return null;
    }
}

function updateRefCalPoint(jsonFile) {
    const jsonTimePoint = jsonFile["time"];
    const jsonTimeUnit = jsonFile["time-unit"];
    
    // Convert time units
    const conversionFactor = getTimeUnitMultiplier(jsonTimeUnit + "s") / getTimeUnitMultiplier(getTimeUnitValue());
    AppState.refCalPoint = jsonTimePoint * conversionFactor;
    document.getElementById("cal-point").textContent = AppState.refCalPoint;
}

function processPointMode(jsonFile, derived_con_text) {
    $hidden(["point-json-exp-section"], false);
    let blankTypeOrSourceIndex;

    if (derived_con_text && derived_con_text.id.includes("source-")) {
        blankTypeOrSourceIndex = parseInt(derived_con_text.id.split("source-")[1]) + 1;
    } else {
        blankTypeOrSourceIndex = jsonFile["for_blank_type"];
    }
    const estValueRead = getEstimatedValue(AppState.responseData, AppState.refCalPoint * getTimeUnitMultiplier(getTimeUnitValue()), blankTypeOrSourceIndex).toFixed(4);
    if (estValueRead) {
        const unitPrinted = (AppState.metaData["Unit"] || "").toLowerCase() === "none" ? "" : AppState.metaData["Unit"];
        if (derived_con_text && derived_con_text.id.includes("source-")) {
            $append("add-json-section", `The estimated ${AppState.globalAnalysis.meas} value read from source-${blankTypeOrSourceIndex} is ${estValueRead}${unitPrinted}.<br/>`);
        } else {
            $append("add-json-section", `The estimated ${AppState.globalAnalysis.meas} value read from data source is ${estValueRead}${unitPrinted}.`);
        }
    } else {
        $append("add-json-section", "");
    }
    try {
        calculated_con = computeFit(parseFloat(estValueRead), jsonFile["fit_type"], jsonFile["fit_coef"]).toFixed(4);
        derived_con_text.innerHTML = `${calculated_con}`;
    } catch (error) {
        console.error("Error computing derived concentration:", error);
        derived_con_text.innerHTML = `<span style="color: red;">$${error.message}</span>`;
    }
}

function handleCalibrationMode() {
    if (calDiv.getAttribute('data-value') === "kinetics") {
        $hidden(["select-quantity-section"], false);
    }
    $hidden(["derived-concentration-section", "blank-derived-concentration-section", "non-blank-derived-concentration-section"]);
}

function updatePlotBasedOnMode(jsonFile) {
    if (AppState.currentMeasurementMode === "calibrate") {
        const cal_type = calDiv.getAttribute('data-value');
        if (cal_type === "kinetics") {
            const quantity_obj = document.getElementById('regressed-quantity');
            AppState.exp_json_content = updatePlot(AppState.responseData, "Concentration", quantity_obj.selectedOptions[0].text
            );
        } else if (cal_type === "point") {
            const uniqueTimePoints = getUniqueColumnEntries(AppState.responseData, 'TimePoint');
            console.log("Give me uniqueTimePoints ", uniqueTimePoints);
            AppState.prevDropdownEntries = populateDropdown(uniqueTimePoints);
            const timePoint = document.getElementById("regressed-time-point").value;
            const processingData = AppState.responseData.filter(row => 
                !timePoint || parseFloat(row["TimePoint"]) === parseFloat(timePoint)
            );
            AppState.exp_json_content = updatePlot(processingData, "Concentration", "Value");
        }
    } else {
        if (AppState.currentMeasurementMode === "point" && jsonFile) {
            updateRefCalPoint(jsonFile);
            document.getElementById("add-json-section").textContent = "";
        }
        switch (AppState.numSources) {
            case 1:
                AppState.globalAnalysis = updatePlot(AppState.responseData);
                if (AppState.currentMeasurementMode === "point" && jsonFile) {
                    processPointMode(jsonFile, document.getElementById('der-con-value'));
                }
                return;

            default: 
                if (AppState.numSources > 1) {
                    const values = Array.from(
                        { length: AppState.numSources },
                        (_, i) => `Value:${i + 1}`
                    );

                    AppState.globalAnalysis = updatePlot(
                        AppState.responseData,
                        "Timestamp",
                        values
                    );

                    if (AppState.currentMeasurementMode === "point" && jsonFile) {
                        const derived_con_texts = settingDerivedCon(jsonFile).derived_con_text;
                        const derived_con_section = settingDerivedCon(jsonFile).derived_section;
                        if (derived_con_section && Array.isArray(derived_con_section)) {
                            derived_con_section.forEach(section => section.classList.remove("hidden"));
                        }
                        if (Array.isArray(derived_con_texts)) {
                            derived_con_texts.forEach((textElem) => {
                                processPointMode(jsonFile, textElem);
                            });
                        }
                    }
                }

            }
    }
}

function toggleMode() {

    // To redraw the chart when mode is toggled, new file is selected, or JSON is changed
    if (AppState.currentFile) {
        if (AppState.currentMeasurementMode !== "calibrate") {
            validateWindowSize(getValInt("window-size"));
            drawMeasurementChart();
        } else fetchData(AppState.currentFile, AppState.currentJSONcontent);
    }
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
}

function exportData() {
    // Validate file name and path
    if (!validateFileName("save-file") || !validatePathName("save-dir")) {
        return;
    }

    // Validate concentration values
    if (!validateConcentration()) {
        return;
    }

    // Set export path
    const processedExpPath = getBtnChecked("same-dir-as-data")
        ? (document.getElementById("directory").value.trim() || "")
        : (document.getElementById("save-dir").value.trim() || "");
    const saveFile = document.getElementById("save-file").value.trim() || "results";

    // Bind button to export path
    bindButtonToString("#go-to-exp-btn", processedExpPath);

    // Export data based on measurement mode
    const analysisData = generateAnalysisData();
    if (!analysisData) {
        return;
    }

    sendExportDataToSources(processedExpPath, saveFile, analysisData);
}

// Validate concentration values based on source mode
function validateConcentration() {
    if (AppState.multiSource) {
        const sensorValue = document.getElementById("exp-json-sensor").value;
        if (sensorValue === "ALL") {
            for (let i = 0; i < AppState.numSources; i++) {
                const inputId = `con-value-read-source-${i}`;
                if (!document.getElementById(inputId).value) {
                    alert(`Please enter a concentration value for source-${i + 1}`);
                    blinkingItem(inputId, 5000);
                    return false;
                }
            }
        } else {
            const sourceIndex = getValInt("exp-json-sensor") - 1;
            const inputId = `con-value-read-source-${sourceIndex}`;
            if (!document.getElementById(inputId).value) {
                alert(`Please enter a concentration value for source-${sourceIndex + 1}`);
                blinkingItem(inputId, 5000);
                return false;
            }
        }
    } else {
        const inputId = "con-value-read";
        if (!document.getElementById(inputId).value) {
            alert("Please enter a concentration value before exporting data.");
            blinkingItem(inputId, 5000);
            return false;
        }
    }
    return true;
}

// Generate analysis data based on measurement mode
function generateAnalysisData() {
    const mode = AppState.currentMeasurementMode;
    if (mode === "kinetics") {
        return generateKineticsData();
    } else if (mode === "point") {
        return generatePointData();
    }
    alert("Invalid measurement mode.");
    return null;
}

// Generate kinetics mode data
function generateKineticsData() {
    if (AppState.multiSource) {
        const sensorValue = document.getElementById("exp-json-sensor").value;
        if (sensorValue === "ALL") {
            return Array.from({ length: AppState.numSources }, (_, i) => ({
                maxrate: AppState.globalAnalysis.sources[i].maxrate * getTimeUnitMultiplier('minutes'),
                slope: AppState.globalAnalysis.sources[i].slope * getTimeUnitMultiplier('minutes'),
                saturationValue: AppState.globalAnalysis.sources[i].sat,
                timeToSaturation: AppState.globalAnalysis.sources[i].time_to_sat / getTimeUnitMultiplier('minutes'),
                measurement: AppState.globalAnalysis.meas,
                measUnit: AppState.globalAnalysis.meas_unit
            }));
        } else {
            const exportSensor = getValInt("exp-json-sensor") - 1;
            return [{
                maxrate: AppState.globalAnalysis.sources[exportSensor].maxrate * getTimeUnitMultiplier('minutes'),
                slope: AppState.globalAnalysis.sources[exportSensor].slope * getTimeUnitMultiplier('minutes'),
                saturationValue: AppState.globalAnalysis.sources[exportSensor].sat,
                timeToSaturation: AppState.globalAnalysis.sources[exportSensor].time_to_sat / getTimeUnitMultiplier('minutes'),
                measurement: AppState.globalAnalysis.meas,
                measUnit: AppState.globalAnalysis.meas_unit
            }];
        }
    } else {
        const blankType = document.getElementById("exp-json-blank-type").value;
        const splitMode = getBtnChecked("split-mode");
        const dataMap = {
            "MIXED": !splitMode && {
                maxrate: AppState.globalAnalysis.maxrate,
                slope: AppState.globalAnalysis.slope,
                saturationValue: AppState.globalAnalysis.sat,
                timeToSaturation: AppState.globalAnalysis.time_to_sat
            },
            "BLANKED": splitMode && {
                maxrate: AppState.globalAnalysis.maxrate_blanked,
                slope: AppState.globalAnalysis.slope_blanked,
                saturationValue: AppState.globalAnalysis.sat_blanked,
                timeToSaturation: AppState.globalAnalysis.time_to_sat_blanked
            },
            "NON-BLANKED": splitMode && {
                maxrate: AppState.globalAnalysis.maxrate_non_blanked,
                slope: AppState.globalAnalysis.slope_non_blanked,
                saturationValue: AppState.globalAnalysis.sat_non_blanked,
                timeToSaturation: AppState.globalAnalysis.time_to_sat_non_blanked
            }
        };

        const data = dataMap[blankType];
        if (!data) return null;

        return [{
            ...data,
            maxrate: data.maxrate * getTimeUnitMultiplier('minutes'),
            slope: data.slope * getTimeUnitMultiplier('minutes'),
            timeToSaturation: data.time_to_saturation / getTimeUnitMultiplier('minutes'),
            measurement: AppState.globalAnalysis.meas,
            measUnit: AppState.globalAnalysis.meas_unit
        }];
    }
}

// Generate point mode data
function generatePointData() {
    const currExpTimePoint = getValFloat("exp-json-time-value");
    if (!currExpTimePoint || isNullOrArrayOfNull(AppState.globalEstimatedValue)) {
        alert("Please set the reference time point to export data or ensure time point is within the recorded time range.");
        return null;
    }

    if (AppState.multiSource) {
        const sensorValue = document.getElementById("exp-json-sensor").value;
        if (sensorValue === "ALL") {
            return Array.from({ length: AppState.numSources }, (_, i) => ({
                estValue: AppState.globalEstimatedValue[i].toFixed(4),
                timePoint: currExpTimePoint,
                measurement: AppState.globalAnalysis.meas,
                measUnit: AppState.globalAnalysis.meas_unit
            }));
        } else {
            const sourceIndex = getValInt("exp-json-sensor") - 1;
            return [{
                estValue: AppState.globalEstimatedValue[sourceIndex].toFixed(4),
                timePoint: currExpTimePoint,
                measurement: AppState.globalAnalysis.meas,
                measUnit: AppState.globalAnalysis.meas_unit
            }];
        }
    } else {
        return [{
            estValue: AppState.globalEstimatedValue.toFixed(4),
            timePoint: currExpTimePoint,
            measurement: AppState.globalAnalysis.meas,
            measUnit: AppState.globalAnalysis.meas_unit
        }];
    }
}

// Send export data to sources
function sendExportDataToSources(processedExpPath, saveFile, analysisData) {
    const blankType = document.getElementById("exp-json-blank-type").value;
    if (AppState.multiSource) {
        const sensorValue = document.getElementById("exp-json-sensor").value;
        if (sensorValue === "ALL") {
            analysisData.forEach((data, i) => {
                const concentration = document.getElementById(`con-value-read-source-${i}`).value;
                sendExportData(processedExpPath, saveFile, data, concentration, "MIXED", i === 0);
            });
        } else {
            const sourceIndex = getValInt("exp-json-sensor") - 1;
            const concentration = document.getElementById(`con-value-read-source-${sourceIndex}`).value;
            sendExportData(processedExpPath, saveFile, analysisData[0], concentration, "MIXED");
        }
    } else {
        const concentration = document.getElementById("con-value-read").value;
        sendExportData(processedExpPath, saveFile, analysisData[0], concentration, blankType);
    }
}

function sendExportData(saveDir, saveFile, analysisData, concentration, blankedType, newFile=true) {
    console.log("analysisData is ", analysisData);
    if (analysisData) {
        const data = {
            save_dir: saveDir,
            save_file: saveFile,
            maxrate: (analysisData.maxrate === "--" || !analysisData.maxrate) ? "NONE" : analysisData.maxrate,
            slope: (analysisData.slope === "--" || !analysisData.slope) ? "NONE" : analysisData.slope,
            sat: (analysisData.saturationValue === "--" || !analysisData.saturationValue) ? "NONE" : analysisData.saturationValue,
            timeSat: (analysisData.timeToSaturation === "--" || !analysisData.timeToSaturation) ? "NONE" : analysisData.timeToSaturation,
            con: concentration,
            measUnit: analysisData.measUnit, 
            blanked: blankedType,
            newFile: newFile,
            measMode: AppState.currentMeasurementMode,
            meas: analysisData.measurement,
            estValue: analysisData.estValue ? analysisData.estValue : "NONE",
            timePoint: analysisData.timePoint
        };
        $.ajax({
            url: '/export_data',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data),
            success: function(response) {
                if (response.status === 'success') {
                    alert(`Success: ${response.message}!`);
                } else {
                    alert(`Error: ${response.message}`);
                }
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.log("AJAX error:", textStatus, errorThrown);
                alert("Error exporting data");
            }
        });
    } else {
        alert("No analysis data available to export. If you'd like to export Blank/NonBlank in kinetics mode, must enable Split mode, and vice versa!");
    }
}

function exportJSONCoef() {
    if (!validateFileName("save-json-file")) {
        return; // Stop if validation fails
    }
    
    const selectElement = document.getElementById('regressed-quantity');
    if (calDiv.getAttribute('data-value') === "point" && (!$document.getElementById("regressed-time-point").value)){
        alert("Please set time point to regress data from");
        return null;
    } else {
        if (AppState.exp_json_content) {
            const data = {
                fit_type: document.getElementById("exp-json-regress-algo").value,
                for_meas: AppState.exp_json_content.meas,
                for_blank_type: document.getElementById("exp-json-blank-type").value,
                coef_content: AppState.exp_json_content.analysis,
                time: document.getElementById("regressed-time-point").value,
                file_name: document.getElementById("save-json-file").value,
                cal_mode: calDiv.getAttribute('data-value'),
                cal_params: Array.from(selectElement.options).map(option => { return option.dataset.original }),
                threshold_val: getValFloat("threshold-value"),
                isMultiSource: AppState.multiSource,
                numSources: AppState.numSources
            }
            $.ajax({
                url: '/export_cal_coefs',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify(data),
                success: function(response) {
                    if (response.status === 'success') {
                        alert(`Success: ${response.message}!`);
                    } else {
                        alert(`Error: ${response.message}`);
                    }
                },
                error: function(jqXHR, textStatus, errorThrown) {
                    console.log("AJAX error:", textStatus, errorThrown);
                    alert("Error exporting data");
                }
            });
        } else {
            alert("No analysis data available to export. If you'd like to export Blank/NonBlank in kinetics mode, must enable Split mode, and vice versa!");
        }
    }
}