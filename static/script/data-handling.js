async function selectFile(fileName, button, tableSelector = "#file-table") {
    logEvent('file', 'select', { name: fileName, table: tableSelector });
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
                $id("copy-file-btn").disabled = false;
                updateFileDisplay(fileName);
                return; // Skip standard measurement data processing for subject folders
            }

            // Backstop the table's disabled buttons: a data file may only be paired
            // with a calibration curve of matching Measurement/Unit/ConcenUnit.
            if (['kinetics', 'point'].includes(AppState.currentMeasurementMode)
                && AppState.currentJSON && AppState.currentJSONcontent) {
                const csvId = (AppState.fileIdentity && AppState.fileIdentity[fileName]) || null;
                const jsonId = jsonIdentityFromContent(AppState.currentJSONcontent);
                const m = identityMatch(csvId, jsonId);
                if (!m.ok) {
                    if (closestTr) closestTr.classList.remove('selected');
                    // The rows were changed by hand; let the next poll redraw them
                    // from state so the real selection is lit again.
                    if (typeof _invalidateTable === 'function') _invalidateTable(tableSelector.replace('#', ''));
                    Swal.fire({
                        title: `${identityMismatchLabel(m.reason)} mismatch`,
                        text: identityClashText(csvId, jsonId, m.reason),
                        icon: 'error', confirmButtonText: 'OK'
                    });
                    return;
                }
            }

            AppState.prevFile = AppState.currentFile;
            $hidden(["data-display-section"], false);
            AppState.currentFile = fileName;
            clearConcentrationValues();
            clearCustomLabels();
            clearCustomColors();

            $id("copy-file-btn").disabled = false;
            if ($id("move-file-btn")) $id("move-file-btn").disabled = false;

            // Reset every control in the data-display section to its default so
            // the previous file's analysis choices don't carry over.
            resetDataDisplayDefaults();

            await processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);

            // Refresh the calibration-JSON table so non-matching curves are disabled
            // against the just-selected data file.
            if (typeof renderJsonRows === 'function') renderJsonRows(AppState.jsonNames);
        }
        else if (tableSelector === "#json-table") {
            // Backstop: only pair a calibration curve with a loaded data file whose
            // Measurement/Unit/ConcenUnit match.
            if (['kinetics', 'point'].includes(AppState.currentMeasurementMode)
                && AppState.currentFile && AppState.metaData) {
                const csvId = csvIdentityFromMeta(AppState.metaData);
                const jsonId = (AppState.jsonIdentity && AppState.jsonIdentity[fileName]) || null;
                const m = identityMatch(csvId, jsonId);
                if (!m.ok) {
                    if (closestTr) closestTr.classList.remove('selected');
                    // The rows were changed by hand; let the next poll redraw them
                    // from state so the real selection is lit again.
                    if (typeof _invalidateTable === 'function') _invalidateTable(tableSelector.replace('#', ''));
                    Swal.fire({
                        title: `${identityMismatchLabel(m.reason)} mismatch`,
                        text: identityClashText(csvId, jsonId, m.reason),
                        icon: 'error', confirmButtonText: 'OK'
                    });
                    return;
                }
            }

            AppState.currentJSON = fileName;

            $id("copy-json-btn").disabled = false;
            $hidden(["right-deselect-btn", "json-display", "top-right"], false);

            await new Promise((resolve) => {
                fetchJSON(AppState.currentJSON, async (JSON_content) => {
                    if (!JSON_content) {
                        resolve();
                        return; // Handle case where fetchJSON returns null/undefined
                    }
                    try {
                        const display = $id("json-display");
                        display.innerHTML = ""; // clear previous content

                        const fitType = JSON_content.fit_type || "N/A";
                        const measFor = JSON_content.for_meas || "N/A";
                        const measUnitFor = JSON_content.meas_unit || "—";
                        const concenUnitFor = JSON_content.concen_unit || "ng/µL";
                        const mode = AppState.currentMeasurementMode || "N/A";

                        const labelCoefficients = (coefs) => {
                            if (coefs && typeof coefs === 'object' && !Array.isArray(coefs)) {
                                return Object.entries(coefs)
                                    .filter(([key]) => key !== '__proto__' && key !== 'constructor' && key !== 'prototype')
                                    .map(([k, v]) => `${_escHtml(k)} = ${_escHtml(v)}`)
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
                        const getFormula = (type) => formulas[String(type).toLowerCase()] || "No formula available for this fit type.";

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
                                if (["fit_type", "for_meas", "meas_unit", "concen_unit", "x_axis"].includes(key)) continue;
                                const tr = document.createElement("tr");
                                tr.innerHTML = AppState.currentMeasurementMode === "kinetics" ? `
                                    <td>${_escHtml(key)}</td>
                                    <td>${labelCoefficients(value?.fit_coef)}</td>
                                ` : key === "fit_coef" ? `
                                    <td>${_escHtml(key)}</td>
                                    <td>${labelCoefficients(value)}</td>
                                ` : `
                                    <td>${_escHtml(key)}</td>
                                    <td>${_escHtml(value)}</td>
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

                        const isPointMode = String(mode).toLowerCase() === "point";
                        const qLabel = isPointMode ? "q" : "q (per minute)";
                        const qDesc = isPointMode
                            ? "<em>Measurement value</em> at the referenced time point."
                            : "<em>Quantity value</em> is either <strong>maxRate, Slope, Saturation, Time to Sat</strong>, whichever is set by user.";

                        const infoData = {
                            "Current Mode": mode,
                            // File-derived values are escaped here; qDesc and the
                            // formula are our own markup (Rule.md §2.39).
                            "Fit Type": _escHtml(fitType),
                            "Formula": getFormula(fitType),
                            "[S]": "Initial Substance Concentration",
                            [qLabel]: qDesc,
                            "Measurement For": _escHtml(measFor),
                            "Measurement Unit": _escHtml(measUnitFor),
                            "Concentration Unit": _escHtml(concenUnitFor)
                        };

                        buildCoefTable(JSON_content);
                        display.appendChild(document.createElement("br"));
                        buildInfoTable(infoData);

                        if (window.MathJax) await MathJax.typesetPromise();

                        AppState.currentJSONcontent = JSON_content;

                        if (AppState.currentFile) {
                            await processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);
                        }

                        // Refresh the data-file table so non-matching files are disabled
                        // against the just-selected calibration curve.
                        if (typeof renderFileRows === 'function') renderFileRows(AppState.fileNames);
                    } finally {
                        resolve();
                    }
                });
            });
        }

        // Smoothly scroll to section and blink
        scrollWhenVisible("data-display-section", 10000);
        blinkingItem("chart-container", 3000);
    } finally {
        if (typeof window.hideSpinner === 'function') window.hideSpinner();
    }
}

function copyFile(tableSelector = "#file-table") {
    if (tableSelector === "#file-table" && AppState.currentMeasurementMode === 'report') {
        if (AppState.currentReportSubject) copyReportSubject(AppState.currentReportSubject);
        return;
    }

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

    logEvent('file', 'copy', { name: currentFile });
    $.ajax({
        url: '/copy_file',
        method: 'POST',
        data: {
            path: AppState.currentDirectory,
            filename: currentFile,
            mode: AppState.currentMeasurementMode,
            tabletype: tableSelector
        },
        success: function (response) {
            if (response.status === 'success') {
                if (getBtnChecked("no-swal-checkbox")) {
                    if (tableSelector === "#file-table") {
                        updateDirectory(AppState.currentDirectory);
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
                        updateDirectory(AppState.currentDirectory);
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
        error: function (xhr, status, error) {
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

// Move the selected CSV data file to another data subfolder (or the data root).
// CSV-only — the report-mode file table holds subjects, not movable data files.
async function moveFile() {
    if (AppState.currentMeasurementMode === 'report') return;

    const currentFile = AppState.currentFile;
    if (!currentFile) {
        Swal.fire({ title: 'Error!', text: 'No file selected to move.', icon: 'error', confirmButtonText: 'OK' });
        return;
    }

    // Build the destination dropdown from the available data folders, excluding
    // the folder the file already lives in.
    let folders = [];
    try {
        const res = await fetch('/get_data_folders');
        const data = await res.json();
        folders = data.folders || [];
    } catch (e) { /* still offer the data root below */ }

    const norm = p => (p || '').replace(/\\\\/g, '\\');
    const current = norm(AppState.currentDirectory);
    const options = {};
    if (typeof DATA_ROOT !== 'undefined' && norm(DATA_ROOT) !== current) {
        options[DATA_ROOT] = '— data root —';
    }
    folders.forEach(f => { if (norm(f.path) !== current) options[f.path] = f.name; });

    if (Object.keys(options).length === 0) {
        Swal.fire({ title: 'No destination', text: 'There is no other data folder to move this file to. Create a folder first.', icon: 'info', confirmButtonText: 'OK' });
        return;
    }

    const { value: destPath } = await Swal.fire({
        title: `Move "${currentFile}"`,
        input: 'select',
        inputOptions: options,
        inputPlaceholder: 'Select destination folder',
        showCancelButton: true,
        confirmButtonText: 'Move',
        inputValidator: (v) => (!v ? 'Please choose a destination folder.' : null)
    });
    if (!destPath) return;

    logEvent('file', 'move', { name: currentFile, dest: destPath });
    if (typeof window.showSpinner === 'function') window.showSpinner();
    $.ajax({
        url: '/move_file',
        method: 'POST',
        data: { path: AppState.currentDirectory, dest_path: destPath, filename: currentFile },
        success: function (response) {
            if (response.status === 'success') {
                deselectFile('#file-table');
                updateDirectory(AppState.currentDirectory);
                if (getBtnChecked('no-swal-checkbox')) {
                } else {
                    Swal.fire({ title: 'Moved!', text: response.message, icon: 'success', timer: 2000, showConfirmButton: false });
                }
            } else {
                Swal.fire({ title: 'Error!', text: response.message || 'An unknown error occurred while moving the file.', icon: 'error', confirmButtonText: 'OK' });
            }
        },
        error: function (xhr, status, error) {
            let message;
            if (xhr.status === 423) message = 'File operation is locked because a process is currently running.';
            else if (xhr.status === 404) message = 'The file or destination folder was not found.';
            else if (xhr.status === 403) message = 'Permission denied. Please check your file permissions.';
            else if (xhr.status === 400) message = 'Invalid request. Please check the input data.';
            else message = 'Unexpected error: ' + (xhr.responseJSON?.message || error);
            Swal.fire({ title: 'Error!', text: message, icon: 'error', confirmButtonText: 'OK' });
        },
        complete: function () { if (typeof window.hideSpinner === 'function') window.hideSpinner(); }
    });
}

async function processDataDisplay(fileName, jsonFileContent = null) {
    logEvent('data', 'display', { file: fileName });
    await fetchData(fileName, jsonFileContent);
    updateFileDisplay(fileName);
    // #func-desc mirrors #exp-json-regress-algo plus the selected quantity /
    // endpoint time. Selecting another file resets both controls
    // (resetDataDisplayDefaults) and repopulates #regressed-time-point inside
    // fetchData, so the description has to be re-rendered here — after the await,
    // never before it — or calibrate mode keeps showing the previous file's fit
    // title and endpoint label.
    if (AppState.currentMeasurementMode === "calibrate"
        && typeof updateRegressionDescription === 'function') {
        updateRegressionDescription();
    }
}


function deselectFile(tableSelector = "#file-table") {
    // Remove "selected" class from all rows
    document.querySelectorAll(`${tableSelector} tr`).forEach(tr => tr.classList.remove("selected"));

    if (tableSelector === "#file-table") {
        AppState.responseData = null;
        AppState.xAxis = 'time';
        destroyCharts();

        // Hide canvas
        if ($id("plot-canvas"))
            $id("plot-canvas").style.display = "none";

        AppState.currentFile = null;
        if (AppState.currentMeasurementMode === 'report') {
            AppState.currentReportSubject = null;
            if (typeof clearReportSubject === 'function') clearReportSubject();
        }

        // Clear analysis text fields
        $text("plot-analysis", "");

        updateFileDisplay(AppState.currentFile);
        $disable(["copy-file-btn", "move-file-btn"], true);
        $hidden(["data-display-section"]);

        // No data file selected → clear any disabling on the calibration-JSON table.
        if (typeof renderJsonRows === 'function') renderJsonRows(AppState.jsonNames);

    } else if (tableSelector === "#json-table") {
        AppState.currentJSON = null;
        AppState.currentJSONcontent = null;

        $hidden(["json-display", "top-right"], true);
        $text("json-display", "");
        processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);

        // No calibration curve selected → clear any disabling on the data-file table.
        if (typeof renderFileRows === 'function') renderFileRows(AppState.fileNames);

        // Hide all JSON-related sections
        [
            "select-quantity-section",
            "derived-concentration-section",
            "point-json-exp-section"
        ].forEach(id => $toggleClass(id, "hidden", true));

        $disable(["copy-json-btn"], true);
        $toggleClass("right-deselect-btn", "hidden", true);
    }
}

// Re-check the active CSV↔JSON pairing against the freshly-loaded data, e.g. after
// a metadata edit. Selection-time backstops (selectFile) only run when a file is
// picked; editing either file's identity (Measurement / Unit / ConcenUnit) can
// misalign a previously-matched pair while both stay selected. When that happens the
// calibration curve must no longer be applied, so this unpairs it (deselects the
// JSON, clearing any derived concentration) and tells the user. Uses the authoritative
// loaded data — AppState.metaData (CSV) and AppState.currentJSONcontent (JSON) — not
// the table identity maps, which may lag an edit. Returns true if it unpaired.
function revalidateActivePairing() {
    if (!['kinetics', 'point'].includes(AppState.currentMeasurementMode)) return false;
    if (!AppState.currentFile || !AppState.currentJSON) return false;
    if (!AppState.metaData || !AppState.currentJSONcontent) return false;
    const csvId = csvIdentityFromMeta(AppState.metaData);
    const jsonId = jsonIdentityFromContent(AppState.currentJSONcontent);
    const m = identityMatch(csvId, jsonId);
    if (m.ok) return false;
    const curve = AppState.currentJSON;
    deselectFile('#json-table');   // unpair: clears currentJSON + any derived concentration
    Swal.fire({
        title: `${identityMismatchLabel(m.reason)} mismatch`,
        html: `${_escHtml(identityClashText(csvId, jsonId, m.reason))}<br><br>` +
            `The calibration curve <b>${_escHtml(curve)}</b> no longer matches the data file and has been unpaired.`,
        icon: 'warning', confirmButtonText: 'OK'
    });
    return true;
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
            logEvent('file', 'delete', { name: fileName, table: tableSelector });
            $(button).closest("tr").remove();
            // If the delete fails the listing is unchanged, so without this the
            // removed row would never come back until a reload.
            if (typeof _invalidateTable === 'function') _invalidateTable(tableSelector.replace('#', ''));

            // Update the AppState
            if (tableSelector === "#file-table") {
                if (AppState.currentFile === fileName) {
                    deselectFile(tableSelector);
                }

                $.post('/delete_file', {
                    filename: fileName,
                    path: AppState.currentDirectory,
                    tabletype: tableSelector
                }, handleResponse).fail(handleError);
            } else if (tableSelector === "#json-table") {
                if (AppState.currentJSON === fileName) {
                    deselectFile(tableSelector);
                }

                $.post('/delete_file', {
                    filename: fileName,
                    mode: AppState.currentMeasurementMode,
                    tabletype: tableSelector,
                    numSources: AppState.numSources
                }, handleResponse).fail(handleError);
            }
        };

        const handleResponse = (response) => {
            if (response.status === 'success') {
                if (skipConfirmation) {
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
                customClass: { confirmButton: 'swal-danger' },
                confirmButtonText: 'Yes, delete it!'
            }).then((result) => {
                if (result.isConfirmed) {
                    proceedDelete();
                }
            });
        }
    });
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
    return await $.get('/get_data', {
        file: `${AppState.currentDirectory}${DELIMITER}${filename}`
    }).fail((xhr, status, errorThrown) => {
        // Create a custom error object with all the details
        const enhancedError = new Error(`Fetch failed for ${filename}`);
        enhancedError.xhr = xhr;
        enhancedError.status = status;
        enhancedError.errorThrown = errorThrown;
        enhancedError.filename = filename;

        throw enhancedError;
    });
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
    // Point-mode Turn files stream a 1,2,3… turn index instead of a Timestamp.
    // The server normalizes the key to "Timestamp" and flags x_axis so the chart
    // axis / reference input relabel to "Turn" (see get_dynamic_data).
    AppState.xAxis = response.x_axis || 'time';

    // Reflect the loaded file's concentration unit in the #concen-unit dropdown
    // (post-migration / post-CDC every file carries # ConcenUnit; legacy files
    // fall back to the documented default).
    if (typeof syncConcenUnitDropdown === 'function') {
        syncConcenUnitDropdown();
    }

    // Hide split-source when there is only one Value column — splitting is meaningless
    if (AppState.currentMeasurementMode !== 'calibrate') {
        const isSingle = AppState.numSources === 1;
        $hidden(['split-source-section'], isSingle);
        if (isSingle) {
            const splitCheckbox = document.getElementById('split-source');
            if (splitCheckbox) splitCheckbox.checked = false;
        }
    }

    // Update plot
    updatePlotBasedOnMode(jsonFile);

    // Process based on measurement mode
    if (AppState.currentMeasurementMode !== "calibrate") {
        if (jsonFile)
            handleNonCalibrationMode(jsonFile);
    } else {
        handleCalibrationMode();
    }

    // Point-mode Turn files build a calibration per-Turn (no time reference), so
    // swap in the per-Turn concentration table for the time-point controls.
    if (AppState.currentMeasurementMode === "point") {
        applyTurnCalUI();
    }

    return response;
};

function handleNonCalibrationMode(jsonFile) {
    // Turn files derive a concentration per Turn (processTurnDerive renders the
    // per-Turn table), so the per-source derived-concentration sections do not
    // apply and must not be un-hidden (Rule §2.27).
    if (AppState.currentMeasurementMode === "point" && AppState.xAxis === 'turn') return;

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
        element.innerHTML = `${calculatedCon}`;
    } catch (error) {
        console.error("Error computing derived concentration:", error);
        element.innerHTML = `<span style="color: red;">${error.message}</span>`;
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
        console.error("📡 XHR Object:", error.xhr);
        console.error("📊 Status:", error.status);
        console.error("❌ Error Thrown:", error.errorThrown);

        // Log response text if available
        if (error.xhr.responseText) {
            console.error("📄 Response Text:", error.xhr.responseText);
        }

        // Log response headers if available
        if (error.xhr.getAllResponseHeaders) {
            console.error("📋 Response Headers:", error.xhr.getAllResponseHeaders());
        }

        // Log status code and text
        console.error("🔢 Status Code:", error.xhr.status);
        console.error("📝 Status Text:", error.xhr.statusText);
    }

    if (error.filename) {
        console.error("📁 Requested Filename:", error.filename);
    }

    if (error.directory) {
        console.error("📂 Directory:", error.directory);
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

    // Turn files carry a unitless 1,2,3… index, so the reference point IS the
    // turn number — no time-unit conversion applies.
    if (AppState.xAxis === 'turn') {
        AppState.refCalPoint = jsonTimePoint;
        document.getElementById("cal-point").textContent = AppState.refCalPoint;
        return;
    }

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
    // Turn X axis: refCalPoint is the raw turn index (no time-unit scaling).
    const lookupPoint = AppState.xAxis === 'turn'
        ? AppState.refCalPoint
        : AppState.refCalPoint * getTimeUnitMultiplier(getTimeUnitValue());
    const est = getEstimatedValue(AppState.responseData, lookupPoint, sourceIndex);
    // null when this source has no valid reading near the reference point
    // (out of range, or only OVFL/NONE there) — say so instead of throwing,
    // which used to abort the whole mode update for every later source.
    if (est == null || !isFinite(est)) {
        const msgDiv = document.getElementById(`est-value-msg-source-${sourceIndex - 1}`);
        if (msgDiv) msgDiv.textContent = t('point.no_estimate', 'No valid reading near the reference point for source-{s}.').replace('{s}', sourceIndex);
        if (derived_con_text) derived_con_text.textContent = '—';
        return;
    }
    const estValueRead = est.toFixed(4);
    if (estValueRead) {
        const unitPrinted = (AppState.metaData["Unit"] || "").toLowerCase() === "none" ? "" : AppState.metaData["Unit"];
        // Target the specific source message container
        const msgDivId = `est-value-msg-source-${sourceIndex - 1}`;
        const msgDiv = document.getElementById(msgDivId);
        if (msgDiv) {
            msgDiv.innerHTML = `The estimated ${_escHtml(AppState.globalAnalysis.meas)} value read from source-${sourceIndex} is ${estValueRead}${_escHtml(unitPrinted)}.`;
        }
    }
    try {
        calculated_con = computeFit(parseFloat(estValueRead), jsonFile["fit_type"], jsonFile["fit_coef"]).toFixed(4);
        derived_con_text.innerHTML = `${calculated_con}`;
    } catch (error) {
        console.error("Error computing derived concentration:", error);
        derived_con_text.innerHTML = `<span style="color: red;">$${error.message}</span>`;
    }
}

// Derive a concentration for every Turn using a turn-based calibration curve
// (no time reference — each Turn's value maps straight through the fit; Rule
// §2.27). Renders a Turn × source table into #add-json-section.
function processTurnDerive(jsonFile) {
    $hidden(["point-json-exp-section"], false);
    const container = document.getElementById('add-json-section');
    if (!container) return;
    const rows = AppState.responseData || [];
    const n = AppState.numSources || 1;
    const concenUnit = (typeof getMetaConcenUnit === 'function') ? getMetaConcenUnit(AppState.metaData) : 'ng/µL';
    const conLabel = t('export.turn_col_concen', 'Concentration');

    let html = `<div style="overflow-x:auto;"><table class="turn-cal-table"><thead><tr><th>${t('export.turn_col_turn', 'Turn')}</th>`;
    for (let s = 1; s <= n; s++) {
        html += `<th>${n > 1 ? 'Value:' + s + ' → ' : ''}${conLabel} (${_escHtml(concenUnit)})</th>`;
    }
    html += `</tr></thead><tbody>`;
    rows.forEach(row => {
        html += `<tr><td>${row['Timestamp']}</td>`;
        for (let s = 1; s <= n; s++) {
            const val = row['Value:' + s];
            let cell = '—';
            if (measNumber(val) !== null) {
                try {
                    cell = computeFit(parseFloat(val), jsonFile["fit_type"], jsonFile["fit_coef"]).toFixed(4);
                } catch (e) {
                    cell = '<span style="color:red;">err</span>';
                }
            }
            html += `<td>${cell}</td>`;
        }
        html += `</tr>`;
    });
    html += `</tbody></table></div>`;
    container.innerHTML = html;
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
            if (isTurnPointCal()) {
                // Turn-based curve: no TimePoint column, so every row is a
                // standard — fit Concentration vs Value directly (Rule §2.27).
                $hidden(['select-time-point'], true);
                AppState.exp_json_content = updatePlot(AppState.responseData, "Concentration", "Value");
            } else {
                $hidden(['select-time-point'], false);
                const uniqueTimePoints = getUniqueColumnEntries(AppState.responseData, 'TimePoint');
                AppState.prevDropdownEntries = populateDropdown(uniqueTimePoints);
                const timePoint = document.getElementById("regressed-time-point").value;
                const processingData = AppState.responseData.filter(row =>
                    !timePoint || parseFloat(row["TimePoint"]) === parseFloat(timePoint)
                );
                AppState.exp_json_content = updatePlot(processingData, "Concentration", "Value");
            }
        }
    } else {
        updateMultiSourceExportOptions();
        // A turn-based calibration curve (built from a Turn file) has no time
        // reference — it derives a concentration from every Turn's value
        // directly, not at one reference point (Rule §2.27).
        const turnDerive = !!(jsonFile && jsonFile["x_axis"] === 'turn');
        if (AppState.currentMeasurementMode === "point" && jsonFile) {
            $hidden(['ref-point-line'], turnDerive);
            if (!turnDerive) updateRefCalPoint(jsonFile);
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
            if (turnDerive) {
                processTurnDerive(jsonFile);
            } else {
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
}

async function toggleMode() {

    // To redraw the chart when mode is toggled, new file is selected, or JSON is changed
    if (AppState.currentFile) {
        if (AppState.currentMeasurementMode !== "calibrate") {
            validateWindowSize(getValInt("window-size"));
            drawMeasurementChart();
        } else await fetchData(AppState.currentFile, AppState.currentJSONcontent);
    }
    // Awaited above on purpose: the calibrate reload repopulates
    // #regressed-time-point, and #func-desc mirrors that control's value.
    updateRegressionDescription();
    if (typeof updateReportChartsTheme === 'function') updateReportChartsTheme();
}

async function refreshReportSubjects() {
    const res = await fetch('/get_report_subjects');
    const data = await res.json();
    if (data.status === 'success') {
        AppState.reportMeta = data.subjects_meta || {};
        updateReportTable(data.subjects || []);
    } else {
        console.warn("Failed to refresh report subjects:", data.message);
    }
}

async function editReportSubject(subjectName, button) {
    const _isDark = document.body.classList.contains('dark');
    const { value: result } = await Swal.fire({
        // titleText, not title: a subject name may hold < or " (Rule.md §2.39).
        titleText: `Edit Subject: "${subjectName}"`,
        html: `
            <div style="text-align:left; margin-bottom:14px;">
                <label style="display:block; margin-bottom:4px; font-size:0.85rem; color:#666;">Rename to</label>
                <input id="swal-rename-input" class="swal2-input" value="${_attr(subjectName)}" style="width:90%; margin:0;">
            </div>
            <div style="text-align:left; margin-bottom:6px; display:flex; align-items:baseline; gap:8px;">
                <span style="font-weight:600; font-size:0.9rem;">Items</span>
                <span style="font-size:0.75rem; color:#94a3b8;">drag ⠿ to reorder · ✕ to remove</span>
            </div>
            <div id="swal-items-container" style="max-height:320px; overflow-y:auto; border:1px solid ${_isDark ? '#374151' : '#e2e8f0'}; border-radius:6px; padding:8px; background:${_isDark ? '#111827' : '#fafafa'};">
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
        // Reload the Init Preview console if this subject is currently open
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

        const isDark = document.body.classList.contains('dark');
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
            card.style.cssText = `margin-bottom:6px; padding:8px 10px; background:${isDark ? '#1f2937' : '#fff'}; border:1px solid ${isDark ? '#374151' : '#e2e8f0'}; border-radius:6px; transition: background 0.15s; color:${isDark ? '#f3f4f6' : 'inherit'};`;
            card.innerHTML = `
                <div style="display:flex; align-items:center; gap:8px;">
                    <span class="drag-handle" data-hint="Drag to reorder" style="cursor:grab; color:#94a3b8; font-size:1.1rem; user-select:none; flex-shrink:0;">⠿</span>
                    <span style="flex:1; font-size:0.9rem; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" data-hint="${_attr(item.filename)}">${_escHtml(item.filename)}</span>
                    <span style="font-size:0.75rem; color:${isDark ? '#a5b4fc' : '#6366f1'}; background:${isDark ? '#312e81' : '#eef2ff'}; padding:1px 7px; border-radius:8px; flex-shrink:0;">${_escHtml(item.metadata.mode || 'Measurement')}</span>
                    <button data-card-id="${_attr(safeId)}" data-filename="${_attr(item.filename)}" data-hint="Remove from subject" onclick="requestSwalItemDelete(this)" style="background:none; border:1px solid #fca5a5; cursor:pointer; color:#ef4444; font-size:0.75rem; padding:2px 8px; border-radius:4px; flex-shrink:0;">✕</button>
                </div>
                <div class="swal-delete-confirm" style="display:none; margin-top:6px; padding-top:6px; border-top:1px solid ${isDark ? '#7f1d1d' : '#fee2e2'}; text-align:right;">
                    <span style="font-size:0.8rem; color:#ef4444; margin-right:8px;">Remove this item from report folder?</span>
                    <button onclick="confirmSwalItemDelete(this)" style="background:#ef4444; color:#fff; border:none; cursor:pointer; padding:3px 12px; border-radius:4px; font-size:0.8rem; margin-right:4px;">Confirm</button>
                    <button onclick="cancelSwalItemDelete(this)" style="${isDark ? 'background:#374151; color:#d1d5db;' : 'background:#e5e7eb;'} border:none; cursor:pointer; padding:3px 12px; border-radius:4px; font-size:0.8rem;">Cancel</button>
                </div>
            `;
            container.appendChild(card);
        }
    } catch (e) {
        container.innerHTML = `<p style="color:#ef4444; margin:8px 0;">Error: ${_escHtml(e.message)}</p>`;
    }
}

function requestSwalItemDelete(btn) {
    const card = btn.closest('[data-item-filename]');
    if (!card) return;
    const isDark = document.body.classList.contains('dark');
    card.style.background = isDark ? '#450a0a' : '#fff5f5';
    card.style.borderColor = '#fca5a5';
    card.querySelector('.swal-delete-confirm').style.display = 'block';
    btn.disabled = true;
}

function cancelSwalItemDelete(btn) {
    const card = btn.closest('[data-item-filename]');
    if (!card) return;
    const isDark = document.body.classList.contains('dark');
    card.style.background = isDark ? '#1f2937' : '#fff';
    card.style.borderColor = isDark ? '#374151' : '#e2e8f0';
    card.querySelector('.swal-delete-confirm').style.display = 'none';
    card.querySelector('button[data-hint="Remove from subject"]').disabled = false;
}

// POST /delete_report_item and throw on a non-success reply. Shared by the
// report table delete (below) and the report console delete (report.js).
async function requestDeleteReportItem(subject, filename) {
    const response = await fetch('/delete_report_item', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject, filename })
    });
    const data = await response.json();
    if (data.status !== 'success') throw new Error(data.message);
    return data;
}

async function confirmSwalItemDelete(btn) {
    const card = btn.closest('[data-item-filename]');
    if (!card) return;
    const filename = card.dataset.filename;
    const subject = card.dataset.subject;
    const cardId = card.id;

    try {
        await requestDeleteReportItem(subject, filename);

        card.remove();

        // Also remove from the Init Preview console if it's currently loaded
        const config = window.ReportItemConfig?.[filename];
        if (config) {
            if (config.chart) config.chart.destroy();
            if (config.pointChart) config.pointChart.destroy();
            if (config.charts) Object.values(config.charts).forEach(c => c.destroy());
            delete window.ReportItemConfig[filename];
        }
        const consoleCard = document.querySelector(`#report-items-container [data-filename="${CSS.escape(filename)}"]`)
            ?.closest('.report-item-card');
        consoleCard?.remove();
        const consoleContainer = document.getElementById('report-items-container');
        if (consoleContainer && !consoleContainer.querySelector('.report-item-card')) {
            consoleContainer.innerHTML = '<p style="color:#666;">No items found in this subject folder.</p>';
        }
    } catch (e) {
        Swal.fire({ title: 'Error!', text: e.message, icon: 'error', confirmButtonText: 'OK' });
        cancelSwalItemDelete(btn);
    }
}

function deleteReportSubject(subjectName, button) {
    Swal.fire({
        title: 'Delete subject?',
        text: `This will permanently delete '${subjectName}' and all its items.`,
        icon: 'warning',
        showCancelButton: true,
        customClass: { confirmButton: 'swal-danger' },
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

function showMergeModal() {
    if (AppState.currentMeasurementMode === "report") {
        return showMergeSubjectsModal();
    }

    // Optional first step (App Settings → "Pick merge files from a folder browser"):
    // browse a folder and tick the files to merge before ordering them.
    if (typeof USER_SETTINGS !== 'undefined' && USER_SETTINGS.merge_directory_picker) {
        return showMergeDirectoryPicker();
    }

    return showMergeSortModal(null);
}

// Step 1 (optional): browse the data subfolders as an accordion and tick CSV
// files to merge. Every subfolder is listed and independently expandable, so
// files can be gathered from several folders at once — selections persist no
// matter which folders are open. On "Next" the picked files are handed to
// showMergeSortModal() for ordering, exactly as if the rows were added by hand.
function showMergeDirectoryPicker() {
    // key = `${folderPath}|||${fileName}` → { folderPath, fileName }
    const selected = new Map();
    const _key = (folderPath, fileName) => `${folderPath}|||${fileName}`;

    Swal.fire({
        title: 'Select Files to Merge',
        width: 540,
        html: `
            <div style="text-align:left; display:flex; flex-direction:column; gap:8px;">
                <div style="font-size:0.82rem; color:#666;">Expand any folders and tick the files to merge — you can pick from several folders at once.</div>
                <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
                    <div id="merge-pick-count" style="font-size:0.8rem; color:#666;">0 files selected</div>
                    <button type="button" id="merge-pick-toggle-all"
                        style="background:none; border:1px solid #2980b9; color:#2980b9; border-radius:4px; padding:3px 10px; cursor:pointer; font-size:0.8rem; white-space:nowrap;">Select all</button>
                </div>
                <div id="merge-pick-accordion" style="border:1px solid #ddd; border-radius:6px; max-height:340px; overflow-y:auto;">
                    <div style="color:#888; font-size:0.85rem; padding:8px;">Loading…</div>
                </div>
            </div>
        `,
        focusConfirm: false,
        showCancelButton: true,
        confirmButtonText: 'Next',
        didOpen: async () => {
            const acc = document.getElementById('merge-pick-accordion');
            const countEl = document.getElementById('merge-pick-count');
            const toggleBtn = document.getElementById('merge-pick-toggle-all');

            const updateTotal = () => {
                const n = selected.size;
                countEl.textContent = `${n} file${n === 1 ? '' : 's'} selected`;
                if (toggleBtn) toggleBtn.textContent = n > 0 ? 'Deselect all' : 'Select all';
            };

            const updateBadge = (group) => {
                const path = group.dataset.path;
                let c = 0;
                selected.forEach(v => { if (v.folderPath === path) c++; });
                group.querySelector('.merge-folder-badge').textContent = c ? `${c} selected` : '';
            };

            // Keep a folder's "Select all in this folder" checkbox in sync with its
            // individual file checkboxes (checked when all are ticked, indeterminate
            // when only some are).
            const syncFolderAllCb = (body) => {
                const allCb = body.querySelector('.merge-folder-all-cb');
                if (!allCb) return;
                const total = body.querySelectorAll('.merge-pick-cb').length;
                const checked = body.querySelectorAll('.merge-pick-cb:checked').length;
                allCb.checked = total > 0 && checked === total;
                allCb.indeterminate = checked > 0 && checked < total;
            };

            // Fetch data subfolders
            let folders = [];
            try {
                const res = await fetch('/get_data_folders');
                const data = await res.json();
                folders = data.folders || [];
            } catch (e) { }

            // Include the data root itself so CSV files sitting directly in it
            // (not only in subfolders) can be picked for merging.
            if (typeof DATA_ROOT !== 'undefined' && DATA_ROOT) {
                folders = [{ name: 'Main data folder', path: DATA_ROOT }, ...folders];
            }

            if (!folders.length) {
                acc.innerHTML = '<div style="color:#888; font-size:0.85rem; padding:8px;">No folders found.</div>';
                return;
            }
            acc.innerHTML = '';

            // Lazily fetch + render a folder's CSV files the first time it opens.
            const loadBody = async (group) => {
                if (group.dataset.loaded === '1') return;
                const body = group.querySelector('.merge-folder-body');
                const path = group.dataset.path;
                body.innerHTML = '<div style="color:#888; font-size:0.82rem; padding:4px;">Loading…</div>';
                let csvFiles = [];
                try {
                    const fd = new FormData();
                    fd.append('path', path);
                    const res = await fetch('/browse', { method: 'POST', body: fd });
                    const data = await res.json();
                    csvFiles = (data.files || []).filter(f => f.endsWith('.csv'));
                } catch (e) {
                    body.innerHTML = '<div style="color:#e74c3c; font-size:0.82rem; padding:4px;">Error loading files.</div>';
                    return;
                }
                group.dataset.loaded = '1';
                if (!csvFiles.length) {
                    body.innerHTML = '<div style="color:#888; font-size:0.82rem; padding:4px;">No CSV files.</div>';
                    return;
                }
                const allRow = `
                    <label style="display:flex; align-items:center; gap:8px; padding:3px 4px; cursor:pointer; font-size:0.82rem; font-weight:600; color:#2980b9; border-bottom:1px solid #eee; margin-bottom:2px;">
                        <input type="checkbox" class="merge-folder-all-cb">
                        <span>Select all in this folder</span>
                    </label>`;
                body.innerHTML = allRow + csvFiles.map(f => `
                    <label style="display:flex; align-items:center; gap:8px; padding:3px 4px; cursor:pointer; font-size:0.85rem;">
                        <input type="checkbox" class="merge-pick-cb" data-file="${_attr(f)}"
                            ${selected.has(_key(path, f)) ? 'checked' : ''}>
                        <span>${_escHtml(f)}</span>
                    </label>
                `).join('');
                syncFolderAllCb(body);
            };

            folders.forEach(f => {
                const group = document.createElement('div');
                group.className = 'merge-folder-group';
                group.dataset.path = f.path;
                group.dataset.loaded = '';
                group.style.borderBottom = '1px solid #eee';

                const head = document.createElement('button');
                head.type = 'button';
                head.className = 'merge-folder-head';
                head.style.cssText = 'display:flex; align-items:center; gap:8px; width:100%; background:none; border:none; padding:8px 10px; cursor:pointer; font-size:0.88rem; text-align:left;';

                const caret = document.createElement('span');
                caret.className = 'merge-folder-caret';
                caret.textContent = '▶';
                caret.style.cssText = 'font-size:0.7rem;';

                const name = document.createElement('span');
                name.style.flex = '1';
                name.textContent = f.name;

                const badge = document.createElement('span');
                badge.className = 'merge-folder-badge';
                badge.style.cssText = 'font-size:0.75rem; color:#2980b9;';

                head.append(caret, name, badge);

                const body = document.createElement('div');
                body.className = 'merge-folder-body';
                body.style.cssText = 'display:none; padding:2px 10px 8px 26px;';

                head.addEventListener('click', async () => {
                    const isOpen = body.style.display !== 'none';
                    body.style.display = isOpen ? 'none' : 'block';
                    caret.textContent = isOpen ? '▶' : '▼';
                    if (!isOpen) await loadBody(group);
                });

                body.addEventListener('change', (e) => {
                    // Per-folder "Select all in this folder" toggle.
                    if (e.target.classList.contains('merge-folder-all-cb')) {
                        const check = e.target.checked;
                        body.querySelectorAll('.merge-pick-cb').forEach(cb => {
                            cb.checked = check;
                            const fileName = cb.getAttribute('data-file');
                            const key = _key(f.path, fileName);
                            if (check) selected.set(key, { folderPath: f.path, fileName });
                            else selected.delete(key);
                        });
                        e.target.indeterminate = false;
                        updateBadge(group);
                        updateTotal();
                        return;
                    }
                    if (!e.target.classList.contains('merge-pick-cb')) return;
                    const fileName = e.target.getAttribute('data-file');
                    const key = _key(f.path, fileName);
                    if (e.target.checked) selected.set(key, { folderPath: f.path, fileName });
                    else selected.delete(key);
                    syncFolderAllCb(body);
                    updateBadge(group);
                    updateTotal();
                });

                group.append(head, body);
                acc.appendChild(group);

                // Auto-expand the folder the user is currently in.
                if (AppState.currentDirectory && f.path === AppState.currentDirectory) {
                    head.click();
                }
            });

            // Select all / Deselect all across every folder. When nothing is
            // selected it loads each folder's files and ticks them all; otherwise
            // it clears the selection (no need to load collapsed folders).
            if (toggleBtn) {
                toggleBtn.addEventListener('click', async () => {
                    const check = selected.size === 0;
                    toggleBtn.disabled = true;
                    const groups = acc.querySelectorAll('.merge-folder-group');
                    if (check) {
                        for (const group of groups) {
                            await loadBody(group);
                            const path = group.dataset.path;
                            const body = group.querySelector('.merge-folder-body');
                            group.querySelectorAll('.merge-pick-cb').forEach(cb => {
                                cb.checked = true;
                                const fileName = cb.getAttribute('data-file');
                                selected.set(_key(path, fileName), { folderPath: path, fileName });
                            });
                            syncFolderAllCb(body);
                            updateBadge(group);
                        }
                    } else {
                        selected.clear();
                        acc.querySelectorAll('.merge-pick-cb').forEach(cb => { cb.checked = false; });
                        acc.querySelectorAll('.merge-folder-body').forEach(syncFolderAllCb);
                        groups.forEach(updateBadge);
                    }
                    toggleBtn.disabled = false;
                    updateTotal();
                });
            }

            updateTotal();
        },
        preConfirm: () => {
            if (selected.size < 2) {
                Swal.showValidationMessage('Please select at least two files to merge');
                return false;
            }
            return Array.from(selected.values());
        }
    }).then((result) => {
        if (!result.isConfirmed) return;
        showMergeSortModal(result.value);
    });
}

// Step 2 (or the only step when the picker is disabled): order the files and
// choose the output. `preselected` is null (start with two empty rows) or an
// array of { folderPath, fileName } to pre-populate one row each.
function showMergeSortModal(preselected) {
    // Bare row — folder/file selects are populated async in didOpen
    const makeFileRow = () => `
        <div class="merge-file-row" style="display:grid; grid-template-columns:30px 1fr 30px; gap:5px; align-items:center; padding:7px 8px; border:1px solid #ddd; border-radius:6px; margin-bottom:6px;">
            <div style="display:flex; flex-direction:column; gap:3px; align-items:center;">
                <button type="button" class="merge-up-btn" data-hint="Move up"
                    style="background:none; border:1px solid #bbb; border-radius:3px; width:24px; height:20px; cursor:pointer; font-size:0.6rem; padding:0; line-height:1;">▲</button>
                <button type="button" class="merge-dn-btn" data-hint="Move down"
                    style="background:none; border:1px solid #bbb; border-radius:3px; width:24px; height:20px; cursor:pointer; font-size:0.6rem; padding:0; line-height:1;">▼</button>
            </div>
            <div style="display:flex; flex-direction:column; gap:4px;">
                <select class="merge-folder-select swal2-input" style="margin:0; font-size:0.8rem; height:30px; width:100%; box-sizing:border-box;"></select>
                <select class="merge-file-select swal2-input" style="margin:0; width:100%; box-sizing:border-box;"></select>
            </div>
            <button type="button" class="merge-remove-btn" data-hint="Remove"
                style="display:none; background:#e74c3c; color:#fff; border:none; border-radius:4px; width:26px; height:26px; cursor:pointer; font-size:0.8rem; padding:0; align-self:center;">✕</button>
        </div>`;

    // One row per pre-selected file (from the folder picker), else two empty rows.
    const initRowsData = (Array.isArray(preselected) && preselected.length >= 2)
        ? preselected
        : [null, null];

    Swal.fire({
        title: 'Merge CSV Files',
        width: 520,
        html: `
            <div style="text-align:left; display:flex; flex-direction:column; gap:6px;">
                <div id="merge-file-list">${initRowsData.map(() => makeFileRow()).join('')}</div>
                <button type="button" id="merge-add-btn"
                    style="background:#2980b9; color:#fff; border:none; border-radius:4px; padding:7px; cursor:pointer; width:100%; font-size:0.9rem;">+ Add File</button>
                <label style="margin-top:2px; font-size:0.85rem;">Output Name:</label>
                <input id="swal-output" class="swal2-input" style="margin:0; width:100%;" placeholder="merged_output">
                <label style="font-size:0.85rem;">Output Folder:</label>
                <select id="merge-output-folder" class="swal2-input" style="margin:0; width:100%; font-size:0.85rem; height:34px;"></select>
            </div>
        `,
        focusConfirm: false,
        showCancelButton: true,
        confirmButtonText: 'Merge',
        didOpen: async () => {
            const list = document.getElementById('merge-file-list');
            const outputInput = document.getElementById('swal-output');
            const outputFolderSel = document.getElementById('merge-output-folder');

            // Fetch data subfolders once
            const loadingOpt = '<option value="">Loading…</option>';
            outputFolderSel.innerHTML = loadingOpt;
            list.querySelectorAll('.merge-folder-select').forEach(s => { s.innerHTML = loadingOpt; });

            let folderOpts = '';
            try {
                const res = await fetch('/get_data_folders');
                const data = await res.json();
                let folders = data.folders || [];
                // Include the data root itself so files sitting directly in it are
                // selectable as a merge source and as the output folder.
                if (typeof DATA_ROOT !== 'undefined' && DATA_ROOT) {
                    folders = [{ name: 'Main data folder', path: DATA_ROOT }, ...folders];
                }
                folderOpts = folders.map(f =>
                    `<option value="${_attr(f.path)}">${_escHtml(f.name)}</option>`
                ).join('');
            } catch (e) { }

            // Populate output folder selector
            outputFolderSel.innerHTML = folderOpts || '<option value="">No folders found</option>';
            if (AppState.currentDirectory) outputFolderSel.value = AppState.currentDirectory;

            // Fetch CSV files for a row from its selected folder
            const loadFilesForRow = async (row, preselectFile = null) => {
                const folderSel = row.querySelector('.merge-folder-select');
                const fileSel = row.querySelector('.merge-file-select');
                const folderPath = folderSel.value;
                if (!folderPath) {
                    fileSel.innerHTML = '<option value="">Select a folder first</option>';
                    return;
                }
                fileSel.innerHTML = '<option value="">Loading…</option>';
                try {
                    const fd = new FormData();
                    fd.append('path', folderPath);
                    const res = await fetch('/browse', { method: 'POST', body: fd });
                    const data = await res.json();
                    const csvFiles = (data.files || []).filter(f => f.endsWith('.csv'));
                    if (csvFiles.length === 0) {
                        fileSel.innerHTML = '<option value="">No CSV files in folder</option>';
                    } else {
                        fileSel.innerHTML = csvFiles.map(f =>
                            `<option value="${_attr(f)}">${_escHtml(f)}</option>`
                        ).join('');
                        if (preselectFile && csvFiles.includes(preselectFile)) {
                            fileSel.value = preselectFile;
                        }
                    }
                } catch (e) {
                    fileSel.innerHTML = '<option value="">Error loading files</option>';
                }
                updateDefaultOutput();
            };

            const updateRemoveBtns = () => {
                const btns = list.querySelectorAll('.merge-remove-btn');
                btns.forEach(btn => { btn.style.display = btns.length > 2 ? 'block' : 'none'; });
            };

            const updateOrderBtns = () => {
                const fileRows = list.querySelectorAll('.merge-file-row');
                fileRows.forEach((row, i) => {
                    row.querySelector('.merge-up-btn').disabled = (i === 0);
                    row.querySelector('.merge-dn-btn').disabled = (i === fileRows.length - 1);
                });
            };

            const updateDefaultOutput = () => {
                const names = Array.from(list.querySelectorAll('.merge-file-select'))
                    .map(s => s.value.replace('.csv', '')).filter(Boolean);
                if (!names.length) return;
                outputInput.value = names.length <= 3
                    ? names.join('_') + '_merged'
                    : `${names[0]}_${names.length}_files_merged`;
            };

            // Set initial button states before async fetches so they don't flash visible
            updateRemoveBtns();
            updateOrderBtns();

            // Populate folder selects in initial rows, then load files. When the
            // folder picker supplied files, pre-point each row at its file;
            // otherwise default to the current directory (first row → current file).
            const initRows = list.querySelectorAll('.merge-file-row');
            for (let i = 0; i < initRows.length; i++) {
                const row = initRows[i];
                const data = initRowsData[i];
                row.querySelector('.merge-folder-select').innerHTML = folderOpts;
                if (data) {
                    row.querySelector('.merge-folder-select').value = data.folderPath;
                    await loadFilesForRow(row, data.fileName);
                } else {
                    if (AppState.currentDirectory) row.querySelector('.merge-folder-select').value = AppState.currentDirectory;
                    await loadFilesForRow(row, i === 0 ? AppState.currentFile : null);
                }
            }

            // Event delegation: folder change reloads file list; file change updates output name
            list.addEventListener('change', async (e) => {
                if (e.target.classList.contains('merge-folder-select')) {
                    await loadFilesForRow(e.target.closest('.merge-file-row'));
                } else if (e.target.classList.contains('merge-file-select')) {
                    updateDefaultOutput();
                }
            });

            // Event delegation: reorder (▲/▼) and remove (✕)
            list.addEventListener('click', (e) => {
                const row = e.target.closest('.merge-file-row');
                if (!row) return;
                if (e.target.classList.contains('merge-remove-btn')) {
                    row.remove();
                    updateRemoveBtns();
                    updateOrderBtns();
                    updateDefaultOutput();
                } else if (e.target.classList.contains('merge-up-btn')) {
                    const prev = row.previousElementSibling;
                    if (prev) list.insertBefore(row, prev);
                    updateOrderBtns();
                    updateDefaultOutput();
                } else if (e.target.classList.contains('merge-dn-btn')) {
                    const next = row.nextElementSibling;
                    if (next) list.insertBefore(next, row);
                    updateOrderBtns();
                    updateDefaultOutput();
                }
            });

            // Add File button
            document.getElementById('merge-add-btn').addEventListener('click', async () => {
                const tmp = document.createElement('div');
                tmp.innerHTML = makeFileRow();
                const newRow = tmp.firstElementChild;
                list.appendChild(newRow);
                newRow.querySelector('.merge-folder-select').innerHTML = folderOpts;
                if (AppState.currentDirectory) newRow.querySelector('.merge-folder-select').value = AppState.currentDirectory;
                updateRemoveBtns();
                updateOrderBtns();
                await loadFilesForRow(newRow);
            });

            updateRemoveBtns();
            updateOrderBtns();
        },
        preConfirm: () => {
            const list = document.getElementById('merge-file-list');
            const fileRows = list.querySelectorAll('.merge-file-row');
            const folderPaths = Array.from(fileRows).map(r => r.querySelector('.merge-folder-select').value);
            const fileNames = Array.from(fileRows).map(r => r.querySelector('.merge-file-select').value);
            const output_name = document.getElementById('swal-output').value.trim();
            const output_path = document.getElementById('merge-output-folder').value;

            if (fileNames.some(f => !f)) {
                Swal.showValidationMessage('Please select a valid file for each slot');
                return false;
            }
            const keys = folderPaths.map((fp, i) => `${fp}|||${fileNames[i]}`);
            if (new Set(keys).size < keys.length) {
                Swal.showValidationMessage('Please select different files for each slot');
                return false;
            }
            if (!output_name) {
                Swal.showValidationMessage('Please enter an output name');
                return false;
            }
            if (!output_path) {
                Swal.showValidationMessage('Please select an output folder');
                return false;
            }
            return { folderPaths, fileNames, output_name, output_path };
        }
    }).then((result) => {
        if (!result.isConfirmed) return;
        const { folderPaths, fileNames, output_name, output_path } = result.value;

        $.ajax({
            url: '/merge_csv',
            method: 'POST',
            traditional: true,
            data: { folder_paths: folderPaths, file_names: fileNames, output_name, output_path },
            success: function (response) {
                if (response.status === 'success') {
                    if (getBtnChecked("no-swal-checkbox")) {
                        updateDirectory(output_path);
                        return;
                    }
                    Swal.fire({
                        title: 'Success!',
                        text: response.message,
                        icon: 'success',
                        timer: 2000,
                        showConfirmButton: false
                    }).then(() => {
                        updateDirectory(output_path);
                    });
                } else {
                    Swal.fire({ title: 'Error!', text: response.message, icon: 'error' });
                }
            },
            error: function (xhr) {
                Swal.fire({ title: 'Error!', text: xhr.responseJSON?.message || 'Failed to merge files', icon: 'error' });
            }
        });
    });
}

function showMergeSubjectsModal() {
    // Read subjects from current table
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

    const options = subjects.map(s => `<option value="${_attr(s)}">${_escHtml(s)}</option>`).join('');
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
                <div style="font-size:0.8rem; color:#666;">
                    Items will be copied into the new subject (sources are kept).
                </div>
            </div>
        `,
        showCancelButton: true,
        confirmButtonText: 'Merge',
        didOpen: () => {
            const s1 = document.getElementById('swal-sub1');
            const s2 = document.getElementById('swal-sub2');
            const out = document.getElementById('swal-sub-out');
            const updateDefault = () => {
                out.value = `${s1.value}_${s2.value}_merged`;
            };
            s1.addEventListener('change', updateDefault);
            s2.addEventListener('change', updateDefault);
            updateDefault();
        },
        preConfirm: () => {
            const s1 = document.getElementById('swal-sub1').value;
            const s2 = document.getElementById('swal-sub2').value;
            const out = document.getElementById('swal-sub-out').value.trim();
            if (s1 === s2) {
                Swal.showValidationMessage('Please select two different subjects');
                return false;
            }
            if (!out) {
                Swal.showValidationMessage('Please enter a new subject name');
                return false;
            }
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

function exportData() {
    // Validate file name and path
    if (!validateFileName("save-file")) {
        return;
    }

    const saveFile = document.getElementById("save-file").value.trim() || "results";

    // Turn files build the whole calibration curve from one file: each Turn is a
    // standard with its own concentration (Rule §2.27). It has its own per-Turn
    // validation and payload shape, so it bypasses the source-based flow.
    if (isTurnRawFile()) {
        exportTurnCal(resolveExportPath(), saveFile);
        return;
    }

    // Validate concentration values
    if (!validateConcentration()) {
        return;
    }

    const processedExpPath = resolveExportPath();

    // Export data based on measurement mode
    const analysisData = generateAnalysisData();
    if (!analysisData) {
        return;
    }

    sendExportDataToSources(processedExpPath, saveFile, analysisData);
}

// Lightweight, non-blocking warning toast for field-level validation that
// already has inline feedback (e.g. a blinking input) — avoids a heavy modal.
function warnToast(message) {
    Swal.fire({
        toast: true,
        position: 'top-end',
        icon: 'warning',
        title: message,
        showConfirmButton: false,
        timer: 3000,
        timerProgressBar: true
    });
}

// Validate concentration values for the selected export sources
function validateConcentration() {
    const selected = getSelectedExportSources();
    if (selected.length === 0) {
        warnToast('Please select at least one source to export.');
        return false;
    }
    for (const src of selected) {
        const inputId = `con-value-read-source-${src - 1}`;
        if (!document.getElementById(inputId).value) {
            warnToast(`Please enter a concentration value for source-${src}.`);
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
    Swal.fire({ title: 'Error!', text: 'Invalid measurement mode.', icon: 'error', confirmButtonText: 'OK' });
    return null;
}

// Generate kinetics mode data for the selected export sources (in display order)
function generateKineticsData() {
    return getSelectedExportSources().map(src => {
        const i = src - 1;
        return {
            maxrate: AppState.globalAnalysis.sources[i].maxrate * getTimeUnitMultiplier('minutes'),
            slope: AppState.globalAnalysis.sources[i].slope * getTimeUnitMultiplier('minutes'),
            saturationValue: AppState.globalAnalysis.sources[i].sat,
            timeToSaturation: AppState.globalAnalysis.sources[i].time_to_sat / getTimeUnitMultiplier('minutes'),
            measurement: AppState.globalAnalysis.meas,
            measUnit: AppState.globalAnalysis.meas_unit
        };
    });
}

// Generate point mode data
function generatePointData() {
    const currExpTimePoint = getValFloat("exp-json-time-value");
    if (!currExpTimePoint || isNullOrArrayOfNull(AppState.globalEstimatedValue)) {
        Swal.fire({ title: 'Time point required', text: 'Please set the reference time point to export data or ensure time point is within the recorded time range.', icon: 'warning', confirmButtonText: 'OK' });
        return null;
    }

    // The reference point is entered in the selected #time-unit, but exported
    // calibration files always record the time point in minutes.
    const timeUnit = (typeof getExpTimeUnit === 'function') ? getExpTimeUnit() : 'minutes';
    const timePointMinutes = currExpTimePoint * getTimeUnitMultiplier(timeUnit) / getTimeUnitMultiplier('minutes');

    // globalEstimatedValue is always a per-source array (see updatePointEstimate);
    // pick the selected sources in display order. A source can still be null
    // when only the others have a reading near the reference point — refuse
    // the export and name it, rather than throwing on .toFixed (§2.10).
    const sources = getSelectedExportSources();
    const missing = sources.filter(src => {
        const v = AppState.globalEstimatedValue[src - 1];
        return v == null || !isFinite(v);
    });
    if (missing.length) {
        Swal.fire({
            title: t('export.no_estimate_title', 'No reading at the reference point'),
            text: t('export.no_estimate_src', 'No valid reading near the reference point for source: {s}. Deselect it or choose another reference point.').replace('{s}', missing.join(', ')),
            icon: 'warning',
            confirmButtonText: 'OK'
        });
        return null;
    }
    return sources.map(src => {
        const i = src - 1;
        return {
            estValue: AppState.globalEstimatedValue[i].toFixed(4),
            timePoint: timePointMinutes,
            measurement: AppState.globalAnalysis.meas,
            measUnit: AppState.globalAnalysis.meas_unit
        };
    });
}

// ── Turn-based point calibration (Rule §2.27) ────────────────────────────────
// A point-mode Turn file records each standard as one Turn. Instead of reading a
// value at a reference time, the user assigns a concentration to every Turn; the
// (Concentration, Value) pairs across turns ARE the calibration curve. There is
// no time reference, so the "Set reference point"/"Select time point" controls
// are replaced by a per-Turn concentration table.

// True when the loaded raw measurement file is a point-mode Turn file.
function isTurnRawFile() {
    return AppState.currentMeasurementMode === 'point' && AppState.xAxis === 'turn';
}

// True when a calibration CSV loaded in calibrate/point mode is turn-based
// (Concentration,Value — no TimePoint column).
function isTurnPointCal() {
    return AppState.currentMeasurementMode === 'calibrate'
        && calDiv.getAttribute('data-value') === 'point'
        && Array.isArray(AppState.responseData) && AppState.responseData.length > 0
        && !('TimePoint' in AppState.responseData[0]);
}

// Swap the point-mode export UI between the time-reference control and the
// per-Turn concentration table, based on the loaded file's X axis.
function applyTurnCalUI() {
    const turn = isTurnRawFile();
    $hidden(['set-exp-point-section'], turn);
    $hidden(['turn-cal-section'], !turn);
    // A Turn file has no time axis, so the whole Display-range section (its only
    // remaining control in point mode is the Time unit selector) does not apply;
    // a time-series point file keeps it for the reference point / chart axis.
    $hidden(['range-display'], turn);
    if (turn) {
        // A Turn file has no time, so these time-point controls do not apply.
        $hidden(['select-time-point'], true);
        renderTurnCalTable();
    }
}

// Render one row per Turn: [Turn #] [Value:1 .. Value:N] [Concentration]. The
// concentration is shared across sources (each Turn is one standard), so it is a
// single input per Turn; every source's value is shown so the user can see what
// each selected source contributes. Concentration inputs persist per Turn in
// localStorage, keyed by file name.
function renderTurnCalTable() {
    const table = document.getElementById('turn-cal-table');
    if (!table) return;
    const rows = AppState.responseData || [];
    const n = AppState.numSources || 1;
    const concenUnit = (typeof getMetaConcenUnit === 'function') ? getMetaConcenUnit(AppState.metaData) : 'ng/µL';
    const fileKey = AppState.currentFile || 'turn-cal';
    // Same test as the export: a sentinel (OVFL/INF) is shown as a dash, since
    // the export skips it and a concentration typed against it would be lost.
    const isVal = v => measNumber(v) !== null;

    let html = `<thead><tr><th>${t('export.turn_col_turn', 'Turn')}</th>`;
    for (let s = 1; s <= n; s++) {
        html += `<th>${n > 1 ? 'Value:' + s : t('export.turn_col_value', 'Value')}</th>`;
    }
    html += `<th>${t('export.turn_col_concen', 'Concentration')} (${_escHtml(concenUnit)})</th></tr></thead><tbody>`;
    rows.forEach((row) => {
        const turn = row['Timestamp'];  // Turn index (renamed to Timestamp on read)
        const storeKey = `turn-con-${fileKey}-${turn}`;
        const saved = localStorage.getItem(storeKey) || '';
        html += `<tr><td>${turn}</td>`;
        for (let s = 1; s <= n; s++) {
            const v = row['Value:' + s];
            html += `<td>${isVal(v) ? v : '—'}</td>`;
        }
        html += `<td><input type="number" class="turn-con-input" data-turn="${turn}"
                 value="${saved}" min="0" style="width:8ch;"
                 onchange="localStorage.setItem('${storeKey}', this.value)"></td></tr>`;
    });
    html += '</tbody>';
    table.innerHTML = html;
}

// Build and send turn-based point calibration files (Concentration,Value). The
// concentration is shared per Turn; each selected source (from "Select Sources
// to export") is written as its own calibration curve — one file per source,
// name suffixed with the source index when more than one is selected (Rule §2.27).
function exportTurnCal(processedExpPath, saveFile) {
    const rows = AppState.responseData || [];
    const conByTurn = {};
    document.querySelectorAll('#turn-cal-table .turn-con-input').forEach(inp => {
        conByTurn[inp.getAttribute('data-turn')] = (inp.value || '').trim();
    });

    const selected = (typeof getSelectedExportSources === 'function') ? getSelectedExportSources() : [1];
    if (!selected.length) {
        Swal.fire({
            title: t('display.no_sources_selected', 'No sources selected'),
            text: t('display.select_source_to_export', 'Please select at least one source to export.'),
            icon: 'warning', confirmButtonText: t('common.ok', 'OK')
        });
        return;
    }

    // A standard's Value must be a number: OVFL / INF / inf / NONE are skipped
    // like an empty cell (measNumber, Rule.md §2.10) — exported, they made the
    // file fail CSV_SCHEMA_POINT_CAL_TURN on the editor's Save.
    const isVal = v => measNumber(v) !== null;
    const jobs = selected.map(src => {
        const entries = [];
        rows.forEach(row => {
            const con = conByTurn[String(row['Timestamp'])];
            const val = row['Value:' + src];
            if (!con || !isVal(val)) return;  // skip turns lacking a concentration or value
            entries.push({ con: con, estValue: val });
        });
        return { src, entries };
    });

    const short = jobs.filter(j => j.entries.length < 2).map(j => j.src);
    if (short.length) {
        Swal.fire({
            title: t('export.turn_need_points_title', 'Not enough points'),
            text: t('export.turn_need_points_src', 'Each selected source needs at least two Turns with a concentration assigned. Not enough for source: {s}.').replace('{s}', short.join(', ')),
            icon: 'warning', confirmButtonText: t('common.ok', 'OK')
        });
        return;
    }

    const multi = selected.length > 1;
    const common = {
        save_dir: processedExpPath,
        measMode: 'point',
        xAxis: 'turn',
        newFile: true,
        meas: (AppState.globalAnalysis && AppState.globalAnalysis.meas) || (AppState.metaData && AppState.metaData.Measurement) || 'NONE',
        measUnit: (AppState.globalAnalysis && AppState.globalAnalysis.meas_unit) || 'NONE',
        concenUnit: (typeof getMetaConcenUnit === 'function' ? getMetaConcenUnit(AppState.metaData) : 'ng/µL')
    };

    const requests = jobs.map(j => {
        const fname = multi ? `${saveFile}_source${j.src}` : saveFile;
        return $.ajax({
            url: '/export_data', type: 'POST', contentType: 'application/json',
            data: JSON.stringify({ ...common, save_file: fname, entries: j.entries })
        }).then(resp => ({ src: j.src, resp }), () => ({ src: j.src, resp: { status: 'error', message: 'request failed' } }));
    });

    Promise.all(requests).then(results => {
        const fail = results.filter(r => !r.resp || r.resp.status !== 'success');
        if (fail.length === 0) {
            Swal.fire({
                title: 'Exported!',
                text: multi
                    ? t('export.turn_exported_multi', 'Exported {n} calibration files (one per source) to {f} folder.')
                        .replace('{n}', String(results.length)).replace('{f}', exportFolderLabel(processedExpPath))
                    : `Data exported to ${exportFolderLabel(processedExpPath)} folder.`,
                icon: 'success', timer: 2600, showConfirmButton: false
            });
        } else {
            Swal.fire({
                title: t('common.error', 'Error!'),
                text: fail.map(f => `source ${f.src}: ${(f.resp && f.resp.message) || 'failed'}`).join('; '),
                icon: 'error', confirmButtonText: t('common.ok', 'OK')
            });
        }
    });
}

// Resolve the export directory from the "same directory" checkbox / subfolder picker.
function resolveExportPath() {
    if (getBtnChecked("same-dir-as-data")) {
        return AppState.currentDirectory || DATA_ROOT;
    }
    const subSel = document.getElementById('exp-subfolder-select');
    if (subSel && subSel.value) {
        const opt = subSel.options[subSel.selectedIndex];
        return (opt && opt.dataset.path) ? opt.dataset.path : (AppState.exportPath || DATA_ROOT);
    }
    return AppState.exportPath || DATA_ROOT;
}

// Send export data to sources
// Send export data to sources
function sendExportDataToSources(processedExpPath, saveFile, analysisData) {
    const commonData = {
        save_dir: processedExpPath,
        save_file: saveFile,
        measMode: AppState.currentMeasurementMode,
        meas: analysisData[0]?.measurement || "NONE",  // Assume same for all; fallback to "NONE"
        measUnit: analysisData[0]?.measUnit || "NONE",  // Assume same for all; fallback to "NONE"
        // Unit for the Concentration column, resolved from the loaded file's
        // metadata (# ConcenUnit); the Data Display dropdown was removed.
        concenUnit: (typeof getMetaConcenUnit === 'function' ? getMetaConcenUnit(AppState.metaData) : "ng/µL")
    };

    let payload;
    let isBatch = false;

    // analysisData is produced in the same order as the selected sources, so
    // entry N pairs with selected source N (and its concentration input).
    const selected = getSelectedExportSources();
    if (selected.length === 0) {
        Swal.fire({ title: 'No sources selected', text: 'Please select at least one source to export.', icon: 'warning', confirmButtonText: 'OK' });
        return;
    }
    if (selected.length > 1) {
        isBatch = true;
        const entries = analysisData.map((data, idx) => prepareExportEntry(data, `con-value-read-source-${selected[idx] - 1}`));
        if (entries.length === 0) {
            Swal.fire({ title: 'Nothing to export', text: 'No analysis data available to export.', icon: 'warning', confirmButtonText: 'OK' });
            return;
        }
        payload = { ...commonData, newFile: true, entries };
    } else {
        const entry = prepareExportEntry(analysisData[0], `con-value-read-source-${selected[0] - 1}`);
        if (!entry) {
            Swal.fire({ title: 'Nothing to export', text: 'No analysis data available to export.', icon: 'warning', confirmButtonText: 'OK' });
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

// Return a short, user-friendly folder label for an export directory
// (relative to the data root) instead of the full filesystem path.
function exportFolderLabel(dirPath) {
    if (!dirPath) return 'the selected folder';
    const stripTrailing = (p) => String(p).replace(/[\\/]+$/, '');
    const d = stripTrailing(dirPath);
    if (typeof DATA_ROOT !== 'undefined' && DATA_ROOT) {
        const root = stripTrailing(DATA_ROOT);
        if (d === root) return 'the data root';
        if (d.startsWith(root + DELIMITER)) {
            return `"${d.slice(root.length + DELIMITER.length)}"`;
        }
    }
    // Fallback: just the last path segment
    const parts = d.split(/[\\/]+/);
    return `"${parts[parts.length - 1] || d}"`;
}

// Helper to send the payload (single or batch)
function sendExportPayload(payload, isBatch) {
    $.ajax({
        url: '/export_data',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(payload),
        success: function (response) {
            if (response.status === 'success') {
                Swal.fire({
                    title: 'Exported!',
                    text: `Data exported to ${exportFolderLabel(payload.save_dir)} folder.`,
                    icon: 'success',
                    timer: 2500,
                    showConfirmButton: false
                });
            } else {
                Swal.fire({ title: 'Error!', text: response.message, icon: 'error', confirmButtonText: 'OK' });
            }
        },
        error: function (jqXHR, textStatus, errorThrown) {
            console.error("AJAX error:", textStatus, errorThrown);
            Swal.fire({ title: 'Error!', text: 'Error exporting data.', icon: 'error', confirmButtonText: 'OK' });
        }
    });
}

// ── Export subfolder handlers ────────────────────────────────────────────────

function onExpSubfolderChange(select) {
    const opt = select.options[select.selectedIndex];
    AppState.exportPath = opt ? (opt.dataset.path || DATA_ROOT) : DATA_ROOT;
}

function onJsonExportModeChange() {
    const mode = document.querySelector('input[name="json-export-mode"]:checked')?.value || 'new';
    const newRow = document.getElementById('json-new-row');
    const overwriteRow = document.getElementById('json-overwrite-row');
    if (newRow) newRow.style.display = mode === 'new' ? 'block' : 'none';
    if (overwriteRow) overwriteRow.style.display = mode === 'overwrite' ? 'flex' : 'none';
    if (mode === 'overwrite') loadExistingJsonFiles();
}

async function loadExistingJsonFiles() {
    const calMode = calDiv.getAttribute('data-value') || 'kinetics';
    try {
        const res = await fetch(`/get_json_cal?mode=${encodeURIComponent(calMode)}`);
        const data = await res.json();
        const files = data.files || [];
        const sel = document.getElementById('json-overwrite-select');
        if (!sel) return;
        const prev = sel.value;
        sel.innerHTML = '<option value="">— select a calibrate file —</option>';
        files.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f;
            opt.textContent = f;
            sel.appendChild(opt);
        });
        if (prev) sel.value = prev;
    } catch (e) {
        console.error('loadExistingJsonFiles error:', e);
    }
}

// ── New CSV file (manual creation, no reading run) ───────────────────────────
// Create an empty template CSV for the current mode in the selected data folder.
// kinetics/point → a Timestamp,Value:1..N timeseries; calibrate → a calibration
// table for the current calibrate sub-mode. The file has the correct metadata +
// header and no data rows, so it opens straight in the editor for manual entry.
async function createCsvFile() {
    const mode = AppState.currentMeasurementMode;
    if (mode === 'report') return;  // report mode has no CSV data files
    const targetDir = AppState.currentDirectory || DATA_ROOT;
    const isCalibrate = mode === 'calibrate';
    const calMode = (typeof calDiv !== 'undefined' && calDiv)
        ? (calDiv.getAttribute('data-value') || 'kinetics') : 'kinetics';

    const rowStyle = 'display:block; margin-top:8px; text-align:left; font-size:0.9em;';
    const sourcesHtml = isCalibrate ? ''
        : `<label style="${rowStyle}">${t('newcsv.sources_label', 'Number of sources')}: <input id="newcsv-sources" type="number" min="1" max="50" value="${AppState.numSources || 1}" style="width:6em; padding:3px 5px;"></label>`;
    const linesHtml = `<label style="${rowStyle}">${t('newcsv.lines_label', 'Number of lines')}: <input id="newcsv-lines" type="number" min="0" max="100000" value="0" style="width:6em; padding:3px 5px;"></label>`;
    // Point calibration can be time-series (…,TimePoint) or Turn-based
    // (Concentration,Value — each Turn is one standard, Rule §2.27).
    const axisHtml = (isCalibrate && calMode === 'point')
        ? `<label style="${rowStyle}">${t('newcsv.point_axis_label', 'Point calibration table')}:
             <select id="newcsv-cal-axis" style="padding:3px 5px;">
               <option value="time">${t('newcsv.axis_time', 'Time-series (Concentration, Value, TimePoint)')}</option>
               <option value="turn">${t('newcsv.axis_turn', 'Turn (Concentration, Value)')}</option>
             </select></label>`
        : '';
    const noteHtml = isCalibrate
        ? `<p style="margin:10px 2px 0; font-size:0.85em; color:#6b7280; text-align:left;">${t('newcsv.calibrate_note', 'Creates an empty calibration table for the current calibrate sub-mode')} (${_escHtml(calMode)}).</p>`
        : '';

    const result = await Swal.fire({
        title: t('newcsv.title', 'New CSV file'),
        html: `<input id="newcsv-name" class="swal2-input" placeholder="${t('newcsv.name_label', 'File name')}" autocomplete="off" style="width:100%; box-sizing:border-box; margin-left:0; margin-right:0;">${sourcesHtml}${linesHtml}${axisHtml}${noteHtml}`,
        showCancelButton: true,
        confirmButtonText: t('common.create', 'Create'),
        cancelButtonText: t('common.cancel', 'Cancel'),
        focusConfirm: false,
        didOpen: () => { const el = document.getElementById('newcsv-name'); if (el) el.focus(); },
        preConfirm: () => {
            const name = (document.getElementById('newcsv-name').value || '').trim();
            if (!name) { Swal.showValidationMessage(t('newcsv.name_required', 'File name is required')); return false; }
            if (/[\\/]|\.\./.test(name)) { Swal.showValidationMessage('Name cannot contain slashes or "..".'); return false; }
            const srcEl = document.getElementById('newcsv-sources');
            const n = srcEl ? Math.max(1, Math.min(50, parseInt(srcEl.value, 10) || 1)) : 1;
            const linesEl = document.getElementById('newcsv-lines');
            const lines = linesEl ? Math.max(0, Math.min(100000, parseInt(linesEl.value, 10) || 0)) : 0;
            const axisEl = document.getElementById('newcsv-cal-axis');
            const calAxis = axisEl ? axisEl.value : 'time';
            return { name, n, lines, calAxis };
        }
    });
    if (!result.isConfirmed || !result.value) return;
    const { name, n, lines, calAxis } = result.value;

    try {
        if (typeof window.showSpinner === 'function') window.showSpinner();
        const response = await fetch('/create_csv_file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode, cal_mode: calMode, cal_axis: calAxis, filename: name, path: targetDir, num_sources: n, num_lines: lines })
        });
        const data = await response.json();
        if (data.status !== 'success') throw new Error(data.message || 'Create failed');

        if (typeof logEvent === 'function') logEvent('file', 'create_csv', { mode, filename: data.filename });
        if (typeof updateDirectory === 'function') await updateDirectory(targetDir, true);
        if (typeof blinkingItem === 'function') blinkingItem('file-selection', 4000);
        if (!getBtnChecked("no-swal-checkbox")) {
            Swal.fire({
                title: t('newcsv.created', 'File created'),
                text: data.message || `Created ${data.filename}.`,
                icon: 'success', timer: 2500, showConfirmButton: false
            });
        }
    } catch (e) {
        Swal.fire(t('common.error', 'Error'), e.message, 'error');
    } finally {
        if (typeof window.hideSpinner === 'function') window.hideSpinner();
    }
}

// ── JSON coefficient export ──────────────────────────────────────────────────

function exportJSONCoef() {
    const exportMode = document.querySelector('input[name="json-export-mode"]:checked')?.value || 'new';

    if (exportMode === 'new' && !validateFileName("save-json-file")) {
        return;
    }

    const selectElement = document.getElementById('regressed-quantity');
    const turnCal = isTurnPointCal();
    if (calDiv.getAttribute('data-value') === "point" && !turnCal && (!document.getElementById("regressed-time-point").value)) {
        Swal.fire({ title: 'Time point required', text: 'Please set time point to regress data from.', icon: 'warning', confirmButtonText: 'OK' });
        return null;
    }

    if (!AppState.exp_json_content) {
        Swal.fire({ title: 'Nothing to export', text: 'No analysis data available to export.', icon: 'warning', confirmButtonText: 'OK' });
        return;
    }

    let fileName;
    if (exportMode === 'overwrite') {
        const sel = document.getElementById('json-overwrite-select');
        fileName = sel ? sel.value : '';
        if (!fileName) {
            Swal.fire({ title: 'No file selected', text: 'Please select an existing calibrate file to overwrite.', icon: 'warning', confirmButtonText: 'OK' });
            return;
        }
        // Strip .json extension so backend adds it consistently
        if (fileName.toLowerCase().endsWith('.json')) {
            fileName = fileName.slice(0, -5);
        }
    } else {
        fileName = document.getElementById("save-json-file").value;
    }

    const data = {
        fit_type: document.getElementById("exp-json-regress-algo").value,
        for_meas: AppState.exp_json_content.meas,
        measUnit: (typeof getMetaUnit === 'function' ? getMetaUnit(AppState.metaData) : (AppState.metaData && AppState.metaData['MeasUnit'])) || 'NONE',
        concenUnit: (typeof getMetaConcenUnit === 'function' ? getMetaConcenUnit(AppState.metaData) : 'ng/µL'),
        coef_content: AppState.exp_json_content.analysis,
        time: turnCal ? null : (document.getElementById("regressed-time-point").value || null),
        // A turn-based point curve records no time reference (Rule §2.27).
        x_axis: turnCal ? 'turn' : 'time',
        file_name: fileName,
        cal_mode: calDiv.getAttribute('data-value'),
        cal_params: Array.from(selectElement.options).map(option => option.dataset.original),
        threshold_val: getValFloat("threshold-value"),
        numSources: AppState.numSources,
        regress_algo: document.getElementById("exp-json-regress-algo").value
    };

    $.ajax({
        url: '/export_cal_coefs',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function (response) {
            if (response.status === 'success') {
                Swal.fire({
                    title: 'Exported!',
                    text: `Calibration data exported to the "${data.cal_mode}" calibrate folder.`,
                    icon: 'success',
                    timer: 2500,
                    showConfirmButton: false
                });
                if (exportMode === 'overwrite') loadExistingJsonFiles();
            } else {
                Swal.fire({ title: 'Error!', text: response.message, icon: 'error', confirmButtonText: 'OK' });
            }
        },
        error: function (jqXHR, textStatus, errorThrown) {
            console.error("AJAX error:", textStatus, errorThrown);
            Swal.fire({ title: 'Error!', text: 'Error exporting data.', icon: 'error', confirmButtonText: 'OK' });
        }
    });
}

// ── Excel formula export ─────────────────────────────────────────────────────
// Turn the fitted standard-curve coefficients into ready-to-paste Excel formulas
// (one per source) that map a measured quantity cell to the derived
// concentration. Sibling of exportJSONCoef — same coefficient content, no file
// written; results are shown in a copyable dialog.
function exportExcelFormula() {
    const selectElement = document.getElementById('regressed-quantity');
    if (calDiv.getAttribute('data-value') === "point" && !isTurnPointCal() && (!document.getElementById("regressed-time-point").value)) {
        Swal.fire({ title: 'Time point required', text: 'Please set time point to regress data from.', icon: 'warning', confirmButtonText: t('common.ok', 'OK') });
        return;
    }
    if (!AppState.exp_json_content) {
        Swal.fire({ title: 'Nothing to export', text: 'No analysis data available to build a formula.', icon: 'warning', confirmButtonText: t('common.ok', 'OK') });
        return;
    }

    const payload = {
        regress_algo: document.getElementById("exp-json-regress-algo").value,
        coef_content: AppState.exp_json_content.analysis,
        cal_params: Array.from(selectElement.options).map(o => o.dataset.original),
        threshold_val: getValFloat("threshold-value"),
        cell: 'A1'
    };

    $.ajax({
        url: '/export_cal_excel_formula',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(payload),
        success: function (resp) {
            if (resp.status === 'success') {
                showExcelFormulaDialog(resp);
            } else {
                Swal.fire({ title: t('common.error', 'Error!'), text: resp.message, icon: 'error', confirmButtonText: t('common.ok', 'OK') });
            }
        },
        error: function () {
            Swal.fire({ title: t('common.error', 'Error!'), text: 'Error building Excel formula.', icon: 'error', confirmButtonText: t('common.ok', 'OK') });
        }
    });
}

function showExcelFormulaDialog(resp) {
    const multi = resp.formulas.length > 1;
    const rows = resp.formulas.map((f, i) => {
        const label = f.label ? _escHtml(String(f.label)) : (multi ? ('Source ' + (i + 1)) : t('excelf.formula', 'Formula'));
        if (!f.formula) {
            return `<div style="margin:6px 0; text-align:left;"><b>${label}</b>: <span style="color:#b91c1c;">${t('excelf.no_fit', 'no usable fit')}</span></div>`;
        }
        const id = 'excelf-input-' + i;
        return `<div style="margin:8px 0; text-align:left;"><b>${label}</b>
            <div style="display:flex; gap:6px; margin-top:3px;">
              <input id="${id}" readonly value="${_escHtml(f.formula)}" style="flex:1; font-family:monospace; padding:4px 6px; box-sizing:border-box;">
              <button type="button" onclick="_copyExcelFormula('${id}', this)">${t('excelf.copy', 'Copy')}</button>
            </div></div>`;
    }).join('');
    Swal.fire({
        title: t('excelf.title', 'Excel formula'),
        html: `<p style="text-align:left; font-size:0.88em; color:#6b7280; margin:0 0 8px;">${t('excelf.paste_hint', 'Paste into a spreadsheet cell. Replace A1 with the cell holding your measured quantity — the result is the concentration.')}</p>${rows}`,
        width: 640,
        confirmButtonText: t('common.close', 'Close')
    });
}

function _copyExcelFormula(id, btn) {
    const el = document.getElementById(id);
    if (!el) return;
    el.focus();
    el.select();
    const done = () => {
        const orig = btn.textContent;
        btn.textContent = t('excelf.copied', 'Copied!');
        setTimeout(() => { btn.textContent = orig; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(el.value).then(done).catch(() => { try { document.execCommand('copy'); done(); } catch (e) { } });
    } else {
        try { document.execCommand('copy'); done(); } catch (e) { }
    }
}

function requireSelectedFile() {
    if (AppState.currentFile) return true;
    Swal.fire({ icon: 'warning', title: 'No file selected', text: 'Select a data file first.' });
    return false;
}

// Shared prompt-and-save flow for the range/normalize CSV extraction buttons:
// prompt for a filename, POST the current file/dir plus `extraBody` to
// `endpoint`, then report the outcome and refresh the directory listing.
// Callers must run requireSelectedFile() first (their labels read the file name).
async function promptAndSaveCsv({ title, inputLabel, defaultName, endpoint, extraBody = {} }) {
    const { value: saveName } = await Swal.fire({
        title,
        input: 'text',
        inputLabel,
        inputPlaceholder: 'filename (without .csv)',
        inputValue: defaultName,
        showCancelButton: true,
        inputValidator: v => (!v || !v.trim()) ? 'Filename is required' : null
    });
    if (!saveName) return;

    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file: AppState.currentDirectory + DELIMITER + AppState.currentFile,
                save_name: saveName.trim(),
                save_dir: AppState.currentDirectory,
                ...extraBody
            })
        });
        const data = await res.json();
        if (data.status === 'success') {
            Swal.fire({ icon: 'success', title: 'Saved', text: `${data.count} rows saved to ${data.path}` });
            updateDirectory(AppState.currentDirectory);
        } else {
            Swal.fire({ icon: 'error', title: 'Save failed', text: data.message });
        }
    } catch (e) {
        Swal.fire({ icon: 'error', title: 'Error', text: 'Request failed.' });
    }
}

async function saveRangeCsv() {
    if (!requireSelectedFile()) return;

    const unit = getTimeUnitValue() || 'seconds';
    const rangeStart = getValFloat('range-value-start');
    const rangeEnd = getValFloat('range-value-end');
    const unitLabel = unit.slice(0, -1);
    const stem = AppState.currentFile.replace(/\.csv$/i, '');
    const multiplier = getTimeUnitMultiplier(unit);

    await promptAndSaveCsv({
        title: 'Save Range to CSV',
        inputLabel: `Rows from ${rangeStart} to ${rangeEnd} ${unitLabel} — save as:`,
        defaultName: `${stem}_range_${rangeStart}-${rangeEnd}`,
        endpoint: '/save_range_csv',
        extraBody: { range_start: rangeStart * multiplier, range_end: rangeEnd * multiplier }
    });
}

async function saveNormalizedCsv() {
    if (!requireSelectedFile()) return;

    const stem = AppState.currentFile.replace(/\.csv$/i, '');
    await promptAndSaveCsv({
        title: 'Save Normalized Data',
        inputLabel: 'Every column minus its own minimum (blank removed) — save as:',
        defaultName: `${stem}_normalized`,
        endpoint: '/save_normalized_csv',
        extraBody: { source_index: null }
    });
}

async function saveNormalizedCsvForSource(sourceIndex) {
    if (!requireSelectedFile()) return;

    const stem = AppState.currentFile.replace(/\.csv$/i, '');
    await promptAndSaveCsv({
        title: `Save Normalized Data — Source ${sourceIndex + 1}`,
        inputLabel: `Source ${sourceIndex + 1} minus its minimum (blank removed) — save as:`,
        defaultName: `${stem}_norm_s${sourceIndex + 1}`,
        endpoint: '/save_normalized_csv',
        extraBody: { source_index: sourceIndex }
    });
}

async function saveLinearityRangeCsvForSource(sourceIndex, linearXMin, linearXMax) {
    if (!requireSelectedFile()) return;

    const unit = getTimeUnitValue() || 'seconds';
    const timeLabel = unit.slice(0, -1);
    const conversionFactor = getTimeUnitMultiplier('seconds') / getTimeUnitMultiplier(unit);
    const startDisp = (parseFloat(linearXMin) * conversionFactor).toFixed(2);
    const endDisp = (parseFloat(linearXMax) * conversionFactor).toFixed(2);
    const stem = AppState.currentFile.replace(/\.csv$/i, '');

    await promptAndSaveCsv({
        title: `Save Linearity Range — Source ${sourceIndex + 1}`,
        inputLabel: `Rows from ${startDisp} to ${endDisp} ${timeLabel} — save as:`,
        defaultName: `${stem}_linear_s${sourceIndex + 1}`,
        endpoint: '/save_range_csv',
        extraBody: { range_start: parseFloat(linearXMin), range_end: parseFloat(linearXMax) }
    });
}
