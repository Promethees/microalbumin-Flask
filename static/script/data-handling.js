const _escHtml = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

async function selectFile(fileName, button, tableSelector = "#file-table") {
    if (typeof window.showSpinner === 'function') window.showSpinner();
    try {
        // Disable the clicked button temporarily to prevent rapid clicks
        button.disabled = true;
        setTimeout(() => button.disabled = false, 1000);

        // Clear previous selection and highlight the current row
        const table = document.querySelector(tableSelector);
        if (!table) return;
        table.querySelectorAll("tr").forEach(row => row.classList.remove("selected"));
        const closestTr = button.closest("tr");
        if (closestTr) closestTr.classList.add("selected");

        if (tableSelector === "#file-table") {
            if (AppState.currentMeasurementMode === 'report') {
                AppState.currentReportSubject = fileName;
                updateFileDisplay(fileName);
            } else {
                AppState.prevFile = AppState.currentFile;
                AppState.currentFile = fileName;
                clearConcentrationValues();

                $id("copy-file-btn").disabled = false;
                $id("download-file-btn").disabled = false;

                // Reset range values
                $id("range-value-start").value = 0;
                $id("range-value-end").value = 1000;
                $id("range-value-start").disabled = false;
                $id("range-value-end").disabled = false;

                $hidden(["data-display-section"], false);

                // Check all quantity-checkbox elements
                document.querySelectorAll(".quantity-checkbox").forEach(cb => cb.checked = true);

                await processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);
            }
        }
        else if (tableSelector === "#json-table") {
            AppState.currentJSON = fileName;

            $id("copy-json-btn").disabled = false;
            $id("download-json-btn").disabled = false;
            $hidden(["right-deselect-btn", "json-display", "top-right"], false);

            await new Promise((resolve) => {
                fetchJSONContent(AppState.currentJSON, async (JSON_content) => {
                    if (!JSON_content) {
                        resolve();
                        return;
                    }
                    try {
                        const display = $id("json-display");
                        display.innerHTML = ""; // clear previous content

                        const fitType = JSON_content.fit_type || "N/A";
                        const measFor = JSON_content.for_meas || "N/A";
                        const mode = AppState.currentMeasurementMode || "N/A";

                        const labelCoefficients = (coefs) => {
                            if (coefs && typeof coefs === 'object' && !Array.isArray(coefs)) {
                                return Object.entries(coefs)
                                    .filter(([key]) => key !== '__proto__' && key !== 'constructor' && key !== 'prototype') 
                                    .map(([k, v]) => `${k} = ${v}`)
                                    .join(', ');
                            }
                            return '—';
                        }

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
                            thead.innerHTML = AppState.currentMeasurementMode === "kinetics" ? `
                                <tr>
                                    <th>Parameter</th>
                                    <th>Fit Coefficients</th>
                                </tr>
                            ` : `
                                <tr>
                                    <th>Parameter</th>
                                    <th>Values</th>
                                </tr>
                            `;
                            const tbody = document.createElement("tbody");

                            for (const [key, value] of Object.entries(json)) {
                                if (["fit_type", "for_meas"].includes(key)) continue;
                                const tr = document.createElement("tr");
                                const tdKey = document.createElement("td");
                                tdKey.textContent = key;
                                const tdVal = document.createElement("td");
                                if (AppState.currentMeasurementMode === "kinetics") {
                                    tdVal.textContent = labelCoefficients(value?.fit_coef);
                                } else if (key === "fit_coef") {
                                    tdVal.textContent = labelCoefficients(value);
                                } else {
                                    tdVal.textContent = String(value ?? '');
                                }
                                tr.appendChild(tdKey);
                                tr.appendChild(tdVal);
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
                                const th = document.createElement("th");
                                th.style.width = "30%";
                                th.textContent = key;
                                const td = document.createElement("td");
                                td.textContent = String(value ?? '');
                                tr.appendChild(th);
                                tr.appendChild(td);
                                tbody.appendChild(tr);
                            }

                            const heading = document.createElement("h4");
                            heading.textContent = "Fit Information";
                            heading.style.margin = "0px 0px 1px 0px";

                            table.appendChild(tbody);

                            display.appendChild(heading);
                            display.appendChild(table);
                        };

                        const infoData = {
                            "Current Mode": mode,
                            "Fit Type": fitType,
                            "Formula": getFormula(fitType),
                            "[S]": "Initial Substance Concentration",
                            "q (per minute)": "<em>Quantity value</em> is either <strong>maxRate, Slope, Saturation, Time to Sat</strong>, whichever is set by user.",
                            "Measurement For": measFor
                        };

                        buildCoefTable(JSON_content);
                        display.appendChild(document.createElement("br"));
                        buildInfoTable(infoData);

                        if (window.MathJax) await MathJax.typesetPromise();

                        AppState.currentJSONcontent = JSON_content;

                        if (AppState.currentFile) {
                            await processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);
                        }
                    } finally {
                        resolve();
                    }
                });
            });
        }

        // Smoothly scroll to section and blink
        scrollWhenVisible("data-display-section", 1000);
        blinkingItem("chart-container", 3000);
    } finally {
        if (typeof window.hideSpinner === 'function') window.hideSpinner();
    }
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

    const filePath = tableSelector === "#file-table" ? csvPath : currentFile;

    const formData = new URLSearchParams();
    formData.append('filepath', filePath);
    formData.append('filename', currentFile);
    formData.append('mode', AppState.currentMeasurementMode);
    formData.append('tabletype', tableSelector);

    fetch('/copy_file', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData
    })
        .then(response => response.json())
        .then(response => {
            if (response.status === 'success') {
                if (getBtnChecked("no-swal-checkbox")) {
                    console.log("File copied successfully:", response.message);
                    if (tableSelector === "#file-table") {
                        updateFileTable(response.files);
                    } else if (tableSelector === "#json-table") {
                        updateJSONTable(response.files);
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
        })
        .catch(error => {
            // Handle AJAX errors (network/server issues)
            let message = 'Unexpected error: ' + error.message;

            // Note: fetch doesn't throw on 4xx/5xx, but our fetchJSON might or we can check response.ok
            // Since I'm using raw fetch here to match the specific error handling logic:
            console.error("Copy file error:", error);

            Swal.fire({
                title: 'Error!',
                text: message,
                icon: 'error',
                confirmButtonText: 'OK'
            });
        });
}

function uploadFile(tableSelector = "#file-table") {
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = tableSelector === "#json-table" ? ".json" : ".csv";

    fileInput.onchange = function (event) {
        const file = event.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append("file", file);
        formData.append("mode", AppState.currentMeasurementMode || "");
        formData.append("tabletype", tableSelector);

        if (typeof window.showSpinner === 'function') window.showSpinner();

        fetch("/upload_file", {
            method: "POST",
            body: formData
        })
            .then(response => response.json())
            .then(response => {
                if (typeof window.hideSpinner === 'function') window.hideSpinner();

                if (response.status === "success") {
                    if (getBtnChecked("no-swal-checkbox")) {
                        console.log("File uploaded successfully:", response.message);
                        return; // Exit if no popup is needed
                    }
                    Swal.fire({
                        title: "Success!",
                        text: response.message,
                        icon: "success",
                        timer: 2000,
                        showConfirmButton: false
                    })
                } else {
                    Swal.fire({
                        title: "Error!",
                        text: response.message || "An unknown error occurred while uploading the file.",
                        icon: "error",
                        confirmButtonText: "OK"
                    });
                }
            })
            .catch(error => {
                if (typeof window.hideSpinner === 'function') window.hideSpinner();
                Swal.fire({
                    title: "Upload Failed",
                    text: error.message,
                    icon: "error",
                    confirmButtonText: "OK"
                });
            });
    };

    fileInput.click(); // Trigger file chooser dialog
}

function downloadFile(tableSelector = "#file-table") {
    const currentFile = tableSelector === "#file-table" ? AppState.currentFile : AppState.currentJSON;

    if (!currentFile) {
        Swal.fire({
            title: 'Error!',
            text: 'No file selected to download.',
            icon: 'error',
            confirmButtonText: 'OK'
        });
        return;
    }

    const fileType = tableSelector === "#file-table" ? "csv" : "json";

    if (typeof window.showSpinner === 'function') window.showSpinner();

    fetch(`/get_file_content?file=${encodeURIComponent(currentFile)}&type=${encodeURIComponent(fileType)}&mode=${encodeURIComponent(AppState.currentMeasurementMode)}`)
        .then(response => response.json())
        .then(response => {
            if (typeof window.hideSpinner === 'function') window.hideSpinner();

            if (response.status === 'success' && response.content) {
                const content = response.content;
                const isJSON = currentFile.toLowerCase().endsWith(".json");

                // Create blob and trigger download
                const blob = new Blob([content], {
                    type: isJSON ? 'application/json' : 'text/csv'
                });

                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = currentFile;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);

                Swal.fire({
                    title: 'Success!',
                    text: `${currentFile} fetched successfully. Preparing for download`,
                    icon: 'success',
                    timer: 1500,
                    showConfirmButton: false
                });
            } else {
                Swal.fire({
                    title: 'Error!',
                    text: response.message || 'Failed to retrieve file content.',
                    icon: 'error',
                    confirmButtonText: 'OK'
                });
            }
        })
        .catch(error => {
            if (typeof window.hideSpinner === 'function') window.hideSpinner();
            Swal.fire({
                title: 'Error!',
                text: error.message || 'Unexpected error occurred while fetching the file.',
                icon: 'error',
                confirmButtonText: 'OK'
            });
        });
}

function processDataDisplay(fileName, jsonFileContent = null) {
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

        // Hide canvas
        if ($id("plot-canvas"))
            $id("plot-canvas").style.display = "none";

        AppState.currentFile = null;

        // Clear analysis text fields
        $text("plot-analysis", "");

        updateFileDisplay(AppState.currentFile);
        $disable(["copy-file-btn", "download-file-btn"], true);
        $hidden(["data-display-section"], true);

    } else if (tableSelector === "#json-table") {
        AppState.currentJSON = null;
        AppState.currentJSONcontent = null;

        $hidden(["json-display", "top-right"], true);
        $text("json-display", "");
        processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);

        // Hide all JSON-related sections
        [
            "select-quantity-section",
            "derived-concentration-section",
            "point-json-exp-section"
        ].forEach(id => $toggleClass(id, "hidden", true));

        $disable(["copy-json-btn", "download-json-btn"], true);
        $toggleClass("right-deselect-btn", "hidden", true);
    }
}

function deleteFile(fileName, button, tableSelector = "#file-table") {
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

            const formData = new URLSearchParams();
            formData.append('filename', fileName);
            formData.append('tabletype', tableSelector);

            fetch('/delete_file', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData
            })
                .then(response => response.json())
                .then(handleResponse)
                .catch(handleError);
        } else if (tableSelector === "#json-table") {
            if (AppState.currentJSON === fileName) {
                deselectFile(tableSelector);
            }

            console.log("Deleting JSON file:", fileName, "from table:", tableSelector);

            const formData = new URLSearchParams();
            formData.append('filename', fileName);
            formData.append('mode', AppState.currentMeasurementMode);
            formData.append('tabletype', tableSelector);
            formData.append('numSources', AppState.numSources);

            fetch('/delete_file', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData
            })
                .then(response => response.json())
                .then(handleResponse)
                .catch(handleError);
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

    const handleError = (error) => {
        console.error("Delete file error:", error);
        Swal.fire({
            title: 'Error!',
            text: error.message || 'An unexpected error occurred while deleting the file',
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
}

function settingDerivedCon() {
    let derived_section = null;
    let derived_con_text = null;
    derived_section = [];
    derived_con_text = [];
    for (let i = 0; i < AppState.numSources; i++) {
        derived_section.push(document.getElementById(`derived-concentration-section-source-${i}`));
        derived_con_text.push(document.getElementById(`der-con-value-source-${i}`));
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
    try {
        return await fetchJSON(`/get_data?file=${encodeURIComponent(filename)}`);
    } catch (error) {
        // Create a custom error object with all the details
        const enhancedError = new Error(`Fetch failed for ${filename}: ${error.message}`);
        enhancedError.filename = filename;
        enhancedError.directory = csvPath;
        throw enhancedError;
    }
};

function processResponse(response, jsonFile) {
    if (!response.data || response.data.length === 0) {
        handleEmptyData();
        return null;
    }

    // Store response data
    AppState.responseData = response.data;
    AppState.metaData = response.metadata;
    AppState.numSources = response.num_sources || 1;

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
    const derivedSettings = settingDerivedCon();
    if (derivedSettings) {
        updateDerivedSections(derivedSettings);
    }

    if (AppState.currentMeasurementMode === "kinetics" && jsonFile) {
        processKineticsMode(jsonFile);
    }
};

function updateDerivedSections({ derived_section, derived_con_text }) {
    if (Array.isArray(derived_section)) {
        derived_section.forEach(section => section.classList.remove("hidden"));
        $hidden(["select-quantity-section"], AppState.currentMeasurementMode !== "kinetics");
        derived_con_text.forEach(section => section.classList.add("blinking"));
    } else {
        $hidden(["select-quantity-section"], true);
        derived_section.forEach(section => section.classList.add("hidden"));
    }
};

function processKineticsMode(jsonFile) {
    const conQuantityInput = document.getElementById('regressed-quantity').value;
    const analysisExtraction = calculateKineticValue(conQuantityInput);

    if (analysisExtraction !== null) {
        updateConcentrationDisplay(analysisExtraction, jsonFile, conQuantityInput);
    }
};

function calculateKineticValue(quantity) {
    const kineticCalculations = {
        maxrate: val => Array.isArray(val) ? val.map(v => parseFloat(v) * 60) : parseFloat(val) * 60,
        slope: val => Array.isArray(val) ? val.map(v => parseFloat(v) * 60) : parseFloat(val) * 60,
        sat: val => Array.isArray(val) ? val.map(v => parseFloat(v)) : parseFloat(val),
        time_to_sat: val => Array.isArray(val) ? val.map(v => parseFloat(v) / 60) : parseFloat(val) / 60
    };

    const val = getKineticValue(quantity);
    return val !== null && kineticCalculations[quantity]
        ? kineticCalculations[quantity](val)
        : null;
};

function updateConcentrationDisplay(analysisExtraction, jsonFile, conQuantityInput) {
    const { derived_con_text } = settingDerivedCon();
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
        element.textContent = calculatedCon;
    } catch (error) {
        console.error("Error computing derived concentration:", error);
        const span = document.createElement('span');
        span.style.color = 'red';
        span.textContent = error.message;
        element.innerHTML = '';
        element.appendChild(span);
    }
};

function handleEmptyData() {
    $hidden(["plot-canvas"]);
    const plotAnalysis = document.getElementById("plot-analysis");
    if (plotAnalysis)
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

function getKineticValue(property) {
    const analysis = AppState.globalAnalysis;
    let values = [];
    analysis.sources.forEach(source => {
        values.push(source[property]);
    });
    return values.length > 0 ? values : null;
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
    let sourceIndex;

    if (derived_con_text && derived_con_text.id.includes("source-")) {
        sourceIndex = parseInt(derived_con_text.id.split("source-")[1]) + 1;
    }
    const estValueRead = getEstimatedValue(AppState.responseData, AppState.refCalPoint * getTimeUnitMultiplier(getTimeUnitValue()), sourceIndex).toFixed(4);
    if (estValueRead) {
        const unitPrinted = (AppState.metaData["Unit"] || "").toLowerCase() === "none" ? "" : AppState.metaData["Unit"];
        // Target the specific source message container
        const msgDivId = `est-value-msg-source-${sourceIndex - 1}`;
        const msgDiv = document.getElementById(msgDivId);
        if (msgDiv) {
            msgDiv.textContent = `The estimated ${AppState.globalAnalysis.meas} value read from source-${sourceIndex} is ${estValueRead}${unitPrinted}.`;
        }
    }
    try {
        calculated_con = computeFit(parseFloat(estValueRead), jsonFile["fit_type"], jsonFile["fit_coef"]).toFixed(4);
        derived_con_text.textContent = calculated_con;
    } catch (error) {
        console.error("Error computing derived concentration:", error);
        const span = document.createElement('span');
        span.style.color = 'red';
        span.textContent = error.message;
        derived_con_text.innerHTML = '';
        derived_con_text.appendChild(span);
    }
}

function handleCalibrationMode() {
    if (calDiv.getAttribute('data-value') === "kinetics") {
        $hidden(["select-quantity-section"], false);
    }
    $hidden(["derived-concentration-section"]);
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
        updateMultiSourceExportOptions();
        if (AppState.currentMeasurementMode === "point" && jsonFile) {
            updateRefCalPoint(jsonFile);
            document.getElementById("add-json-section").textContent = "";
        }

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
            const derived_con_texts = settingDerivedCon().derived_con_text;
            const derived_con_section = settingDerivedCon().derived_section;
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
    if (typeof updateReportChartsTheme === 'function') updateReportChartsTheme();
}

function exportData() {
    // Validate file name and path
    if (!validateFileName("save-file")) {
        return;
    }

    // Validate concentration values
    if (!validateConcentration()) {
        return;
    }
    const saveFile = document.getElementById("save-file").value.trim() || "results";

    // Bind button to export path
    bindButtonToString("#go-to-exp-btn", AppState.processedExpPath);

    // Export data based on measurement mode
    const analysisData = generateAnalysisData();
    if (!analysisData) {
        return;
    }

    sendExportDataToSources(AppState.processedExpPath, saveFile, analysisData);
}

// Validate concentration values based on source mode
function validateConcentration() {
    const sourceValue = document.getElementById("exp-json-source").value;
    if (sourceValue === "ALL") {
        for (let i = 0; i < AppState.numSources; i++) {
            const inputId = `con-value-read-source-${i}`;
            if (!document.getElementById(inputId).value) {
                alert(`Please enter a concentration value for source-${i + 1}`);
                blinkingItem(inputId, 5000);
                return false;
            }
        }
    } else {
        const sourceIndex = getValInt("exp-json-source") - 1;
        const inputId = `con-value-read-source-${sourceIndex}`;
        if (!document.getElementById(inputId).value) {
            alert(`Please enter a concentration value for source-${sourceIndex + 1}`);
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
    const sourceValue = document.getElementById("exp-json-source").value;
    if (sourceValue === "ALL") {
        return Array.from({ length: AppState.numSources }, (_, i) => ({
            maxrate: AppState.globalAnalysis.sources[i].maxrate * getTimeUnitMultiplier('minutes'),
            slope: AppState.globalAnalysis.sources[i].slope * getTimeUnitMultiplier('minutes'),
            saturationValue: AppState.globalAnalysis.sources[i].sat,
            timeToSaturation: AppState.globalAnalysis.sources[i].time_to_sat / getTimeUnitMultiplier('minutes'),
            measurement: AppState.globalAnalysis.meas,
            measUnit: AppState.globalAnalysis.meas_unit
        }));
    } else {
        const exportSource = getValInt("exp-json-source") - 1;
        return [{
            maxrate: AppState.globalAnalysis.sources[exportSource].maxrate * getTimeUnitMultiplier('minutes'),
            slope: AppState.globalAnalysis.sources[exportSource].slope * getTimeUnitMultiplier('minutes'),
            saturationValue: AppState.globalAnalysis.sources[exportSource].sat,
            timeToSaturation: AppState.globalAnalysis.sources[exportSource].time_to_sat / getTimeUnitMultiplier('minutes'),
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

    const sourceValue = document.getElementById("exp-json-source").value;
    if (sourceValue === "ALL") {
        return Array.from({ length: AppState.numSources }, (_, i) => ({
            estValue: AppState.globalEstimatedValue[i].toFixed(4),
            timePoint: currExpTimePoint,
            measurement: AppState.globalAnalysis.meas,
            measUnit: AppState.globalAnalysis.meas_unit
        }));
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
// Send export data to sources
function sendExportDataToSources(processedExpPath, saveFile, analysisData) {
    const commonData = {
        save_dir: processedExpPath,
        save_file: saveFile,
        measMode: AppState.currentMeasurementMode,
        meas: analysisData[0]?.measurement || "NONE",  // Assume same for all; fallback to "NONE"
        measUnit: analysisData[0]?.measUnit || "NONE"  // Assume same for all; fallback to "NONE"
    };

    let payload;
    let isBatch = false;

    const sourceValue = document.getElementById("exp-json-source").value;
    if (sourceValue === "ALL") {
        isBatch = true;
        const entries = analysisData.map((data, i) => prepareExportEntry(data, `con-value-read-source-${i}`, "MIXED"));
        if (entries.length === 0) {
            alert("No analysis data available to export.");
            return;
        }
        payload = { ...commonData, newFile: true, entries };
    } else {
        const sourceIndex = getValInt("exp-json-source") - 1;
        const entry = prepareExportEntry(analysisData[0], `con-value-read-source-${sourceIndex}`, "MIXED");
        if (!entry) {
            alert("No analysis data available to export.");
            return;
        }
        payload = { ...commonData, ...entry, newFile: true };
    }

    sendExportPayload(payload, isBatch);
}

// Helper to prepare a single export entry
function prepareExportEntry(analysisData, conInputId) {
    if (!analysisData) return null;

    const concentration = document.getElementById(conInputId)?.value || "NONE";

    return {
        maxrate: (analysisData.maxrate === "--" || !analysisData.maxrate) ? "NONE" : analysisData.maxrate,
        slope: (analysisData.slope === "--" || !analysisData.slope) ? "NONE" : analysisData.slope,
        sat: (analysisData.saturationValue === "--" || !analysisData.saturationValue) ? "NONE" : analysisData.saturationValue,
        timeSat: (analysisData.timeToSaturation === "--" || !analysisData.timeToSaturation) ? "NONE" : analysisData.timeToSaturation,
        con: concentration,
        estValue: analysisData.estValue ? analysisData.estValue : "NONE",
        timePoint: analysisData.timePoint || "NONE"
    };
}

// Helper to send the payload (single or batch)
function sendExportPayload(payload, isBatch) {
    console.log(`Sending ${isBatch ? 'batch' : 'single'} export data:`, payload);
    $.ajax({
        url: '/export_data',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(payload),
        success: function (response) {
            if (response.status === 'success') {
                alert(`Success: ${response.message}!`);
            } else {
                alert(`Error: ${response.message}`);
            }
        },
        error: function (jqXHR, textStatus, errorThrown) {
            console.log("AJAX error:", textStatus, errorThrown);
            alert("Error exporting data");
        }
    });
}

function sendExportData(saveDir, saveFile, analysisData, concentration, newFile = true) {
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
            success: function (response) {
                if (response.status === 'success') {
                    alert(`Success: ${response.message}!`);
                } else {
                    alert(`Error: ${response.message}`);
                }
            },
            error: function (jqXHR, textStatus, errorThrown) {
                console.log("AJAX error:", textStatus, errorThrown);
                alert("Error exporting data");
            }
        });
    } else {
        alert("Error! No analysis data available to export.");
    }
}

function exportJSONCoef() {
    if (!validateFileName("save-json-file")) {
        return; // Stop if validation fails
    }

    const selectElement = document.getElementById('regressed-quantity');
    if (calDiv.getAttribute('data-value') === "point" && (!document.getElementById("regressed-time-point").value)) {
        alert("Please set time point to regress data from");
        return null;
    } else {
        if (AppState.exp_json_content) {
            const data = {
                fit_type: document.getElementById("exp-json-regress-algo").value,
                for_meas: AppState.exp_json_content.meas,
                coef_content: AppState.exp_json_content.analysis,
                time: document.getElementById("regressed-time-point").value,
                file_name: document.getElementById("save-json-file").value,
                cal_mode: calDiv.getAttribute('data-value'),
                cal_params: Array.from(selectElement.options).map(option => { return option.dataset.original }),
                threshold_val: getValFloat("threshold-value"),
                numSources: AppState.numSources,
                regress_algo: document.getElementById("exp-json-regress-algo").value
            }
            $.ajax({
                url: '/export_cal_coefs',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify(data),
                success: function (response) {
                    if (response.status === 'success') {
                        alert(`Success: ${response.message}!`);
                    } else {
                        alert(`Error: ${response.message}`);
                    }
                },
                error: function (jqXHR, textStatus, errorThrown) {
                    console.log("AJAX error:", textStatus, errorThrown);
                    alert("Error exporting data");
                }
            });
        } else {
            alert("Error! No analysis data available to export.");
        }
    }
}

function showMergeModal() {
    if (AppState.currentMeasurementMode === "report") {
        return showMergeSubjectsModal();
    }
    const table = document.getElementById("file-table");
    const rows = table.querySelectorAll("tr");
    const files = [];
    rows.forEach((row, index) => {
        if (index === 0) return;
        const cell = row.querySelector("td");
        if (cell && cell.textContent.trim().endsWith(".csv")) {
            files.push(cell.textContent.trim());
        }
    });

    if (files.length < 2) {
        Swal.fire({
            title: 'Not enough files',
            text: 'You need at least two CSV files to merge.',
            icon: 'info'
        });
        return;
    }

    let fileOptions = files.map(f => `<option value="${_escHtml(f)}">${_escHtml(f)}</option>`).join('');

    Swal.fire({
        title: 'Merge CSV Files',
        html: `
            <div style="text-align: left; display: flex; flex-direction: column; gap: 10px;">
                <label for="swal-file1">First File:</label>
                <select id="swal-file1" class="swal2-input" style="margin: 0; width: 100%;">
                    ${fileOptions}
                </select>
                <label for="swal-file2">Second File:</label>
                <select id="swal-file2" class="swal2-input" style="margin: 0; width: 100%;">
                    ${fileOptions}
                </select>
                <label for="swal-output">Output Name:</label>
                <input id="swal-output" class="swal2-input" style="margin: 0; width: 100%;" placeholder="merged_output">
            </div>
        `,
        focusConfirm: false,
        showCancelButton: true,
        confirmButtonText: 'Merge',
        didOpen: () => {
            const file1Select = document.getElementById('swal-file1');
            const file2Select = document.getElementById('swal-file2');
            const outputInput = document.getElementById('swal-output');

            const updateDefaultOutput = () => {
                const f1 = file1Select.value.replace('.csv', '');
                const f2 = file2Select.value.replace('.csv', '');
                outputInput.value = `${f1}_${f2}_merged`;
            };

            file1Select.addEventListener('change', updateDefaultOutput);
            file2Select.addEventListener('change', updateDefaultOutput);

            if (AppState.currentFile && files.includes(AppState.currentFile)) {
                file1Select.value = AppState.currentFile;
            }
            updateDefaultOutput();
        },
        preConfirm: () => {
            const file1 = document.getElementById('swal-file1').value;
            const file2 = document.getElementById('swal-file2').value;
            const output_name = document.getElementById('swal-output').value;

            if (file1 === file2) {
                Swal.showValidationMessage('Please select two different files');
                return false;
            }
            if (!output_name) {
                Swal.showValidationMessage('Please enter an output name');
                return false;
            }

            return { file1, file2, output_name };
        }
    }).then((result) => {
        if (result.isConfirmed) {
            const { file1, file2, output_name } = result.value;

            const formData = new URLSearchParams();
            formData.append('file1', file1);
            formData.append('file2', file2);
            formData.append('output_name', output_name);

            fetch('/merge_csv', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData
            })
                .then(response => response.json())
                .then(response => {
                    if (response.status === 'success') {
                        Swal.fire({
                            title: 'Success!',
                            text: response.message,
                            icon: 'success',
                            timer: 2000,
                            showConfirmButton: false
                        });
                    } else {
                        Swal.fire({
                            title: 'Error!',
                            text: response.message,
                            icon: 'error'
                        });
                    }
                })
                .catch(error => {
                    Swal.fire({
                        title: 'Error!',
                        text: error.message || 'Failed to merge files',
                        icon: 'error'
                    });
                });
        }
    });
}

// ── Report Subject CRUD ──────────────────────────────────────────────────────

async function refreshReportSubjects() {
    const res = await fetch('/get_report_subjects');
    const data = await res.json();
    if (data.status === 'success') {
        updateReportTable(data.subjects || []);
    } else {
        console.warn("Failed to refresh report subjects:", data.message);
    }
}

async function editReportSubject(subjectName, button) {
    const { value: result } = await Swal.fire({
        title: `Edit Subject: "${subjectName}"`,
        html: `
            <div style="text-align:left; margin-bottom:14px;">
                <label style="display:block; margin-bottom:4px; font-size:0.85rem; color:#666;">Rename to</label>
                <input id="swal-rename-input" class="swal2-input" value="${_escHtml(subjectName)}" style="width:90%; margin:0;">
            </div>
            <div style="text-align:left; margin-bottom:6px; display:flex; align-items:baseline; gap:8px;">
                <span style="font-weight:600; font-size:0.9rem;">Items</span>
                <span style="font-size:0.75rem; color:#94a3b8;">drag ⠿ to reorder · ✕ to remove</span>
            </div>
            <div id="swal-items-container" style="max-height:320px; overflow-y:auto; border:1px solid #e2e8f0; border-radius:6px; padding:8px; background:#fafafa;">
                <p style="color:#94a3b8; margin:8px 0; text-align:center;">Loading items…</p>
            </div>
        `,
        width: '680px',
        showCancelButton: true,
        confirmButtonText: 'Save',
        cancelButtonText: 'Cancel',
        focusConfirm: false,
        didOpen: async () => {
            const container = document.getElementById('swal-items-container');
            await loadEditSwalItems(subjectName, container);
            initSortableCards(container);
        },
        preConfirm: () => {
            const newName = document.getElementById('swal-rename-input').value.trim();
            const order = Array.from(
                document.querySelectorAll('#swal-items-container [data-item-filename]')
            ).map(el => el.dataset.itemFilename);
            return { newName, order };
        }
    });

    if (!result) return;

    const { newName, order } = result;
    try {
        if (order.length > 0) {
            await fetch('/save_report_item_order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ subject: subjectName, order })
            });
        }
        const effectiveName = newName && newName !== subjectName ? newName : subjectName;
        if (newName && newName !== subjectName) {
            const resp = await fetch('/rename_report_subject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ old_subject: subjectName, new_subject: newName })
            });
            const data = await resp.json();
            if (data.status !== 'success') throw new Error(data.message || 'Rename failed');
            if (AppState.currentReportSubject === subjectName) {
                AppState.currentReportSubject = newName;
            }
        }
        await refreshReportSubjects();
        if (AppState.currentReportSubject === effectiveName) {
            loadReportItems(effectiveName);
        }
    } catch (e) {
        Swal.fire('Error', e.message, 'error');
    }
}

async function loadEditSwalItems(subjectName, container) {
    try {
        const res = await fetch(`/get_report_items?subject=${encodeURIComponent(subjectName)}`);
        const data = await res.json();
        if (data.status !== 'success') throw new Error(data.message);

        const dataFiles = data.items.filter(i => i.filename.toLowerCase().endsWith('.csv'));
        if (dataFiles.length === 0) {
            container.innerHTML = '<p style="color:#94a3b8; margin:8px 0; text-align:center;">No CSV items in this subject.</p>';
            return;
        }

        container.innerHTML = '';
        for (const item of dataFiles) {
            const safeId = `swal-card-${item.filename.replace(/[^a-z0-9]/gi, '_')}`;
            const card = document.createElement('div');
            card.className = 'report-item-card';
            card.id = safeId;
            card.draggable = true;
            card.dataset.itemFilename = item.filename;
            card.dataset.filename = item.filename;
            card.dataset.subject = subjectName;
            card.style.cssText = 'margin-bottom:6px; padding:8px 10px; background:#fff; border:1px solid #e2e8f0; border-radius:6px; transition: background 0.15s;';
            const cardRow = document.createElement('div');
            cardRow.style.cssText = 'display:flex; align-items:center; gap:8px;';
            const dragHandle = document.createElement('span');
            dragHandle.className = 'drag-handle';
            dragHandle.title = 'Drag to reorder';
            dragHandle.style.cssText = 'cursor:grab; color:#94a3b8; font-size:1.1rem; user-select:none; flex-shrink:0;';
            dragHandle.textContent = '⠿';
            const nameSpan = document.createElement('span');
            nameSpan.style.cssText = 'flex:1; font-size:0.9rem; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
            nameSpan.title = item.filename;
            nameSpan.textContent = item.filename;
            const modeSpan = document.createElement('span');
            modeSpan.style.cssText = 'font-size:0.75rem; color:#6366f1; background:#eef2ff; padding:1px 7px; border-radius:8px; flex-shrink:0;';
            modeSpan.textContent = item.metadata?.mode || 'Measurement';
            const removeBtn = document.createElement('button');
            removeBtn.dataset.cardId = safeId;
            removeBtn.dataset.filename = item.filename;
            removeBtn.title = 'Remove from subject';
            removeBtn.style.cssText = 'background:none; border:1px solid #fca5a5; cursor:pointer; color:#ef4444; font-size:0.75rem; padding:2px 8px; border-radius:4px; flex-shrink:0;';
            removeBtn.textContent = '✕';
            removeBtn.addEventListener('click', () => requestSwalItemDelete(removeBtn));
            cardRow.appendChild(dragHandle);
            cardRow.appendChild(nameSpan);
            cardRow.appendChild(modeSpan);
            cardRow.appendChild(removeBtn);
            const deleteConfirm = document.createElement('div');
            deleteConfirm.className = 'swal-delete-confirm';
            deleteConfirm.style.cssText = 'display:none; margin-top:6px; padding-top:6px; border-top:1px solid #fee2e2; text-align:right;';
            deleteConfirm.innerHTML = '<span style="font-size:0.8rem; color:#ef4444; margin-right:8px;">Remove this item from report folder?</span>';
            const confirmBtn = document.createElement('button');
            confirmBtn.style.cssText = 'background:#ef4444; color:#fff; border:none; cursor:pointer; padding:3px 12px; border-radius:4px; font-size:0.8rem; margin-right:4px;';
            confirmBtn.textContent = 'Confirm';
            confirmBtn.addEventListener('click', () => confirmSwalItemDelete(confirmBtn));
            const cancelBtn = document.createElement('button');
            cancelBtn.style.cssText = 'background:#e5e7eb; border:none; cursor:pointer; padding:3px 12px; border-radius:4px; font-size:0.8rem;';
            cancelBtn.textContent = 'Cancel';
            cancelBtn.addEventListener('click', () => cancelSwalItemDelete(cancelBtn));
            deleteConfirm.appendChild(confirmBtn);
            deleteConfirm.appendChild(cancelBtn);
            card.appendChild(cardRow);
            card.appendChild(deleteConfirm);
            container.appendChild(card);
        }
    } catch (e) {
        const errP = document.createElement('p');
        errP.style.cssText = 'color:#ef4444; margin:8px 0;';
        errP.textContent = `Error: ${e.message}`;
        container.innerHTML = '';
        container.appendChild(errP);
    }
}

function requestSwalItemDelete(btn) {
    const card = btn.closest('[data-item-filename]');
    if (!card) return;
    card.style.background = '#fff5f5';
    card.style.borderColor = '#fca5a5';
    card.querySelector('.swal-delete-confirm').style.display = 'block';
    btn.disabled = true;
}

function cancelSwalItemDelete(btn) {
    const card = btn.closest('[data-item-filename]');
    if (!card) return;
    card.style.background = '#fff';
    card.style.borderColor = '#e2e8f0';
    card.querySelector('.swal-delete-confirm').style.display = 'none';
    card.querySelector('button[title="Remove from subject"]').disabled = false;
}

async function confirmSwalItemDelete(btn) {
    const card = btn.closest('[data-item-filename]');
    if (!card) return;
    const filename = card.dataset.filename;
    const subject = card.dataset.subject;

    try {
        const response = await fetch('/delete_report_item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject, filename })
        });
        const data = await response.json();
        if (data.status !== 'success') throw new Error(data.message);

        card.remove();

        const config = window.ReportItemConfig?.[filename];
        if (config) {
            if (config.chart) config.chart.destroy();
            if (config.charts) Object.values(config.charts).forEach(c => c.destroy());
            delete window.ReportItemConfig[filename];
        }
        const consoleCard = document.querySelector(`#report-items-container [data-filename="${filename}"]`)
            ?.closest('.report-item-card');
        consoleCard?.remove();
        const consoleContainer = document.getElementById('report-items-container');
        if (consoleContainer && !consoleContainer.querySelector('.report-item-card')) {
            consoleContainer.innerHTML = '<p style="color:#666;">No items found in this subject folder.</p>';
        }
    } catch (e) {
        alert('Error: ' + e.message);
        cancelSwalItemDelete(btn);
    }
}

function deleteReportSubject(subjectName, button) {
    Swal.fire({
        title: 'Delete subject?',
        text: `This will permanently delete '${subjectName}' and all its items.`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        confirmButtonText: 'Yes, delete'
    }).then(async (result) => {
        if (!result.isConfirmed) return;
        try {
            const resp = await fetch('/delete_report_subject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ subject: subjectName })
            });
            const data = await resp.json();
            if (data.status !== 'success') throw new Error(data.message || 'Delete failed');

            if (AppState.currentReportSubject === subjectName) {
                AppState.currentReportSubject = null;
                document.getElementById('report-console-section')?.classList.add('hidden');
            }
            await refreshReportSubjects();
        } catch (e) {
            Swal.fire('Error', e.message, 'error');
        }
    });
}

async function copyReportSubject(subjectName) {
    try {
        const resp = await fetch('/copy_report_subject', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject: subjectName })
        });
        const data = await resp.json();
        if (data.status !== 'success') throw new Error(data.message || 'Copy failed');
        await refreshReportSubjects();
    } catch (e) {
        Swal.fire('Error', e.message, 'error');
    }
}

function showMergeSubjectsModal() {
    const table = document.getElementById("file-table");
    const rows = table.querySelectorAll("tr");
    const subjects = [];
    rows.forEach((row, index) => {
        if (index === 0) return;
        const cell = row.querySelector("td");
        if (cell && cell.textContent.trim()) subjects.push(cell.textContent.trim());
    });

    if (subjects.length < 2) {
        Swal.fire('Not enough subjects', 'You need at least two subjects to merge.', 'info');
        return;
    }

    const options = subjects.map(s => `<option value="${_escHtml(s)}">${_escHtml(s)}</option>`).join('');
    Swal.fire({
        title: 'Merge Report Subjects',
        html: `
            <div style="text-align:left; display:flex; flex-direction:column; gap:10px;">
                <label>First Subject:</label>
                <select id="swal-sub1" class="swal2-input" style="margin:0; width:100%;">${options}</select>
                <label>Second Subject:</label>
                <select id="swal-sub2" class="swal2-input" style="margin:0; width:100%;">${options}</select>
                <label>New Subject Name:</label>
                <input id="swal-sub-out" class="swal2-input" style="margin:0; width:100%;" placeholder="merged_subject">
                <div style="font-size:0.8rem; color:#666;">Items will be copied into the new subject (sources are kept).</div>
            </div>
        `,
        showCancelButton: true,
        confirmButtonText: 'Merge',
        didOpen: () => {
            const s1 = document.getElementById('swal-sub1');
            const s2 = document.getElementById('swal-sub2');
            const out = document.getElementById('swal-sub-out');
            const updateDefault = () => { out.value = `${s1.value}_${s2.value}_merged`; };
            s1.addEventListener('change', updateDefault);
            s2.addEventListener('change', updateDefault);
            updateDefault();
        },
        preConfirm: () => {
            const s1 = document.getElementById('swal-sub1').value;
            const s2 = document.getElementById('swal-sub2').value;
            const out = document.getElementById('swal-sub-out').value.trim();
            if (s1 === s2) { Swal.showValidationMessage('Please select two different subjects'); return false; }
            if (!out) { Swal.showValidationMessage('Please enter a new subject name'); return false; }
            return { s1, s2, out };
        }
    }).then(async (result) => {
        if (!result.isConfirmed) return;
        const { s1, s2, out } = result.value;
        try {
            const resp = await fetch('/merge_report_subjects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ subjects: [s1, s2], output_subject: out })
            });
            const data = await resp.json();
            if (data.status !== 'success') throw new Error(data.message || 'Merge failed');
            await refreshReportSubjects();
        } catch (e) {
            Swal.fire('Error', e.message, 'error');
        }
    });
}