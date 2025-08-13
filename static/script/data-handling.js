function selectFile(fileName, button, tableSelector = "#file-table") {   
    // Temporarily disable the button to prevent multiple clicks
    $(button).prop("disabled", true);
    setTimeout(() => {
        $(button).prop("disabled", false);
    }, 1000); // Re-enable the button after 1 second

    // Clear previous selection and highlight the current row
    $(`${tableSelector} tr`).removeClass("selected");
    $(button).closest("tr").addClass("selected");

    if (tableSelector === "#file-table") {
        AppState.prevFile = AppState.currentFile;
        AppState.currentFile = fileName;
        $("#split-mode").prop("checked", false);
        $("#blanked-canvas, #non-blanked-canvas").hide();
        $("#plot-canvas").show();
        $("#full-display").prop("checked", false);
        $("#quantity-checkboxes").addClass("hidden");
        $("#range-value").val(1000);
        $("#range-value").prop("disabled", false);
        $('.quantity-checkbox').each(function() {
            $(this).prop("checked", true);
        });
        processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);
    } else if (tableSelector === "#json-table") {
        AppState.currentJSON = fileName;
        fetchJSON(AppState.currentJSON, function(JSON_content, JSON_path) {
            $("#json-display").text(`Current mode is \"${AppState.currentMeasurementMode}\".\nJSON file read from ${JSON_path}\n`);
            if (AppState.currentMeasurementMode === "kinetics") {
                $("#json-display").append("Quantity value is either maxRate, Slope, Saturation, Time to Saturation, which ever is set by user.\n");
            } else if (AppState.currentMeasurementMode === "point") {
                 $("#json-display").append("Quantity value is the Absorbance value read from selected data file whose recorded time is the closest to the time set in this JSON.\n");
            }
            $("#json-display").append(`${AppState.json_msg}`);
            $("#json-display").append(JSON.stringify(JSON_content, null, 4));
            AppState.currentJSONcontent = JSON_content;
            if (AppState.currentFile) 
                processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);
        });
    }    
    // Smoothly scroll to the bottom of the page
    $("html, body").animate({ scrollTop: $(document).height() }, 1000);
    blinkingItem('#chart-container', 3000);
}

function processDataDisplay(fileName, jsonFileContent=null) {
    // Get user inputs
    let unit = $("#time-unit").val();
    let window_size = $("#window-size").val();

    // Validate window size
    if (window_size < 3) {
        $("#wd-size-error").text("Window size must be greater than 3.").show();
        return;
    }

    if (!Number.isInteger(parseInt(window_size, 10)) || window_size === '' || isNaN(window_size)) {
        $("#wd-size-error").text("Window size must be an integer.").show();
        return;
    }

    // Clear error message if input is valid
    $("#wd-size-error").hide();

    // Proceed with fetching and displaying data
    fetchData(unit, window_size, fileName, jsonFileContent);
    updateFileDisplay(fileName);
}


function deselectFile(tableSelector="#file-table") {
    $(`${tableSelector} tr`).removeClass("selected");
    if (tableSelector === "#file-table") {
        AppState.responseData = null;
        destroyCharts();
        $("#plot-canvas, #blanked-canvas, #non-blanked-canvas").hide();
        AppState.currentFile = null;
        $("#analysis-info").text("");
        updateFileDisplay(AppState.currentFile);
    } else if (tableSelector === "#json-table") {
        AppState.currentJSON = null;
        AppState.currentJSONcontent = null;
        $("#json-display").text("");
        processDataDisplay(AppState.currentFile, AppState.currentJSONcontent);
        $("#select-quantity-section").addClass("hidden");
        $("#derived-concentration-section").addClass("hidden");
        $("#blank-derived-concentration-section").addClass("hidden");
        $("#non-blank-derived-concentration-section").addClass("hidden");
        $("#point-json-exp-section").addClass("hidden");
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
                blinkingItem('#terminate-script-btn', 5000);
            });
            return;
        }

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
                        path: $("#directory").val(), 
                        tabletype: tableSelector 
                    }, function(response) {
                        if (response.status === 'success') {
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
                                blinkingItem('#terminate-script-btn', 5000);
                            });
                        }
                    }).fail(function(jqXHR) {
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
                            blinkingItem('#terminate-script-btn', 5000);
                        });
                    });
                } else if (tableSelector === "#json-table") {
                    if (AppState.currentJSON === fileName) {
                        deselectFile(tableSelector);
                    }

                    console.log("Deleting JSON file:", fileName, "from table:", tableSelector);

                    $.post('/delete_file', { 
                        filename: fileName, 
                        mode: AppState.currentMeasurementMode, 
                        tabletype: tableSelector 
                    }, function(response) {
                        if (response.status === 'success') {
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
                                blinkingItem('#terminate-script-btn', 5000);
                            });
                        }
                    }).fail(function(jqXHR) {
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
                            blinkingItem('#terminate-script-btn', 5000);
                        });
                    });
                }
            }
        });
    });
}

function settingDerivedCon(jsonFile) {
    let derived_section = null;
    let derived_con_text = null;
    switch(jsonFile["for_blank_type"]) {
        case "MIXED":
            if (!$("#split-mode").is(":checked")) {
                derived_section = document.getElementById('derived-concentration-section');
                derived_con_text = document.getElementById('der-con-value');
            }
            break;
        case "BLANKED":
            if ($("#split-mode").is(":checked")) {
                derived_section = document.getElementById('blank-derived-concentration-section');
                derived_con_text = document.getElementById('blank-der-con-value');
            }
            break;
        case "NON-BLANKED":
            if ($("#split-mode").is(":checked")) {
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

function fetchData(unit, window_size, filename, jsonFile) {
    const fullPath = $("#directory").val() + delimiter + filename;
    $.get('/get_data', {
        file: $("#directory").val() + delimiter + filename
    }, function(response) {
        if (response.data && response.data.length > 0) {
            let derivedConSettings = null;
            let derived_section = null;
            let derived_con_text = null;
            if (jsonFile && AppState.currentMeasurementMode !== "calibrate") {
                derivedConSettings = settingDerivedCon(jsonFile);
                derived_section = derivedConSettings.derived_section;
                derived_con_text = derivedConSettings.derived_con_text;
                // console.log("Derived section:", derived_section, "Derived concentration text:", derived_con_text);
                if (derived_section) {
                    derived_section.classList.remove("hidden");
                    if (AppState.currentMeasurementMode === "kinetics") {
                        $("#select-quantity-section").removeClass("hidden");
                    } else {
                        $("#select-quantity-section").addClass("hidden");
                    }
                    blinkingItem(derived_con_text, null);
                } else { // derived_section is null -> hide all
                    $("#select-quantity-section").addClass("hidden");
                    $("#derived-concentration-section").addClass("hidden");
                    $("#blank-derived-concentration-section").addClass("hidden");
                    $("#non-blank-derived-concentration-section").addClass("hidden");
                }
            }

            const isSplitMode = $("#split-mode").is(":checked");
            const isFullDisplay = $("#full-display").is(":checked");
            const displayRangeInput = document.getElementById('range-value');
            const fullDisplayCheckbox = document.getElementById('full-display');
            AppState.responseData = response.data; // Reset point data

            // Move event listener outside the AJAX callback or nest it properly
            const originalValue = displayRangeInput.value; // Fixed 'input' to 'value'
            if (fullDisplayCheckbox.checked) {
                displayRangeInput.disabled = true;
                displayRangeInput.placeholder = "Disabled by Full Display";
                displayRangeInput.value = "";
            } else {
                displayRangeInput.disabled = false;
                displayRangeInput.value = originalValue || 1000; // Restore original or default to 1000
            }

            // Update plot based on current mode
            updatePlotBasedOnMode(response, jsonFile, unit, window_size, isSplitMode, isFullDisplay);

            if (AppState.currentMeasurementMode !== "calibrate") {
                // Process concentration value input
                const conValueInput = document.getElementById('con-value-read');
                const conValueFromFile = AppState.responseData.map(row => row['Concentration'])[0];

                conValueInput.disabled = conValueFromFile !== "NONE";
                conValueInput.value = conValueFromFile !== "NONE" ? conValueFromFile : "";
                
                // Handle kinetics mode
                if (AppState.currentMeasurementMode === "kinetics" && jsonFile) {
                    const conQuantityInput = document.getElementById('regressed-quantity').value;
                    const blankType = jsonFile["for_blank_type"];
                    let value = null;
                    
                    // Calculate value based on quantity and blank type
                    switch(conQuantityInput) {
                        case "maxrate":
                            value = getKineticValue("maxrate", blankType) * 60;
                            break;
                        case "slope":
                            value = getKineticValue("slope", blankType) * 60;
                            break;
                        case "sat":
                            value = getKineticValue("sat", blankType);
                            break;
                        case "time_to_sat":
                            value = getKineticValue("time_to_sat", blankType) / 60;
                            break;
                    }
                    
                    if (value !== null) {
                        const coef = jsonFile[conQuantityInput]["fit_coef"];
                        try {
                            calculated_con = computeFit(value, jsonFile["fit_type"], coef).toFixed(4);
                            derived_con_text.innerHTML = `${calculated_con}`;
                        } catch (error) {
                            console.error("Error computing derived concentration:", error);
                            derived_con_text.innerHTML = `<span style="color: red;">${error.message}</span>`;
                        }
                    }
                } 
            } 
            // Handle calibration mode
            else {
                handleCalibrationMode();
            }

        } else {
            $("#plot-canvas, #blanked-canvas, #non-blanked-canvas").hide();
            $("#analysis-info").html(`<span style="color: red;">No data available</span>`);
        }
    }).fail(function(xhr, status, error) {
        console.error("Failed to fetch data:", status, error, xhr.responseText);
    }); // Close $.get callback
} // Close fetchData function

function getKineticValue(property, blankType) {
    const analysis = AppState.globalAnalysis;
    switch(blankType) {
        case "MIXED": return analysis ? analysis[property] : null;
        case "BLANKED": return analysis ? analysis[`${property}_blanked`] : null;
        case "NON-BLANKED": return analysis ? analysis[`${property}_non_blanked`] : null;
        default: return null;
    }
}

function updateRefCalPoint(jsonFile) {
    const calPoint = $("#cal-point");
    const timeUnitSet = $("#time-unit").val();
    const jsonTimePoint = jsonFile["time"];
    const jsonTimeUnit = jsonFile["time-unit"];
    
    // Convert time units
    const conversionFactor = getTimeUnitMultiplier(jsonTimeUnit + "s") / getTimeUnitMultiplier(timeUnitSet);
    AppState.refCalPoint = jsonTimePoint * conversionFactor;
    calPoint.text(AppState.refCalPoint);
}

function processPointMode(response, jsonFile, derived_con_text) {
    $("#point-json-exp-section").removeClass("hidden");
    // Display estimated value
    const estValueRead = getEstimatedValue(AppState.responseData, AppState.refCalPoint * 60, jsonFile["for_blank_type"]).toFixed(4);
    if (estValueRead) {
        const unitPrinted = AppState.responseData[0]["Unit"] === "NONE" ? "" : AppState.responseData[0]["Unit"];
        $("#add-json-section").text(`The estimated ${AppState.globalAnalysis.meas} value read from recorded data is ${estValueRead}${unitPrinted}.`);
    } else {
        $("#add-json-section").text("");
    }
    try {
        calculated_con = computeFit(estValueRead, jsonFile["fit_type"], jsonFile["fit_coef"]).toFixed(4);
        derived_con_text.innerHTML = `${calculated_con}`;
    } catch (error) {
        console.error("Error computing derived concentration:", error);
        derived_con_text.innerHTML = `<span style="color: red;">$${error.message}</span>`;
    }
}

function handleCalibrationMode() {
    if ($("#cal-mode-select").val() === "kinetics") {
        $("#select-quantity-section").removeClass("hidden");
    }
    $("#derived-concentration-section").addClass("hidden");
    $("#blank-derived-concentration-section").addClass("hidden");
    $("#non-blank-derived-concentration-section").addClass("hidden");
}

function updatePlotBasedOnMode(response, jsonFile, unit, window_size, isSplitMode, isFullDisplay, derived_con_text = document.getElementById('der-con-value')) {
    if (AppState.currentMeasurementMode === "point" && jsonFile) {
        const range = $("#range-value").val();
        updateRefCalPoint(jsonFile);
        AppState.globalAnalysis = updatePlot(
            AppState.responseData, range, unit, window_size, 
            response.unit || "NONE", isSplitMode, isFullDisplay, 
            jsonFile["for_blank_type"]
        );
        processPointMode(response, jsonFile, derived_con_text);
    } else if (AppState.currentMeasurementMode === "calibrate") {
        const cal_type = $("#cal-mode-select").val();
        if (cal_type === "kinetics") {
            const quantity_obj = document.getElementById('regressed-quantity');
            AppState.exp_json_content = updatePlot(
                AppState.responseData, null, null, null, 
                AppState.responseData[0]["MeasUnit"], isSplitMode, true, null, 
                "Concentration", quantity_obj.selectedOptions[0].text
            );
        } else if (cal_type === "point") {
            const uniqueTimePoints = getUniqueColumnEntries(AppState.responseData, 'TimePoint');
            console.log("Give me uniqueTimePoints ", uniqueTimePoints);
            AppState.prevDropdownEntries = populateDropdown(uniqueTimePoints);
            const timePoint = $("#regressed-time-point").val();
            const processingData = AppState.responseData.filter(row => 
                !timePoint || parseFloat(row["TimePoint"]) === parseFloat(timePoint)
            );
            AppState.exp_json_content = updatePlot(
                processingData, null, null, null, 
                AppState.responseData[0]["MeasUnit"], isSplitMode, true, null, 
                "Concentration", "Value"
            );
        }
    } else {
        const range = $("#range-value").val();
        AppState.globalAnalysis = updatePlot(
            AppState.responseData, range, unit, window_size, 
            response.unit || "NONE", isSplitMode, isFullDisplay
        );
    }
}

function toggleMode() {
    if ($("#full-display").is(":checked") && AppState.currentMeasurementMode === "kinetics") {
        $("#quantity-checkboxes").removeClass("hidden");
    } else {   
        $("#quantity-checkboxes").addClass("hidden");
    }
    // To redraw the chart when mode is toggled, new file is selected, or JSON is changed
    if (AppState.currentFile) {
        if (AppState.currentMeasurementMode !== "calibrate") {
            drawMeasurementChart();
        } else fetchData(null, null, AppState.currentFile, AppState.currentJSONcontent);
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
    if ($("#cal-mode-select").val === "kinetics") {
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
}

function exportData() {
    const isValidFileName = validateFileName("save-file");
    const isValidPathName = validatePathName("save-dir");
    // Validate file name and path before proceeding
    if (!isValidFileName || !isValidPathName) {
        return; // Stop if validation fails
    }
    
    if ($("#con-value-read").val() === "") {
        alert("Please enter a concentration value before exporting data.");
        blinkingItem('#con-value-read', 5000);
        return;
    }
    AppState.processedExpPath = $("#save-dir").val().trim() || "";
    const saveFile = $("#save-file").val().trim() || "results";
    const concentration = $("#con-value-read").val();
    const timeUnit = $("#time-unit").val();
    let analysisData = null;

    bindButtonToString("#go-to-exp-btn", AppState.processedExpPath);
    console.log("Global analysis data is ", AppState.globalAnalysis);
    if (AppState.currentMeasurementMode === "kinetics") {
        switch ($("#exp-json-blank-type").val()) {
            case "MIXED":
                if (!$("#split-mode").is(":checked")) {
                    analysisData = {
                        maxrate: AppState.globalAnalysis.maxrate * getTimeUnitMultiplier('minutes'),
                        slope: AppState.globalAnalysis.slope * getTimeUnitMultiplier('minutes'),
                        saturationValue: AppState.globalAnalysis.sat,
                        timeToSaturation: AppState.globalAnalysis.time_to_sat / getTimeUnitMultiplier('minutes'),
                        measurement: AppState.globalAnalysis.meas,
                        measUnit: AppState.globalAnalysis.meas_unit
                    };
                }
                break;

            case "BLANKED":
                if ($("#split-mode").is(":checked")) {
                    analysisData = {
                        maxrate: AppState.globalAnalysis.maxrate_blanked * getTimeUnitMultiplier('minutes'),
                        slope: AppState.globalAnalysis.slope_blanked * getTimeUnitMultiplier('minutes'),
                        saturationValue: AppState.globalAnalysis.sat_blanked,
                        timeToSaturation: AppState.globalAnalysis.time_to_sat_blanked / getTimeUnitMultiplier('minutes'),
                        measurement: AppState.globalAnalysis.meas,
                        measUnit: AppState.globalAnalysis.meas_unit
                    };
                }
                break;

            case "NON-BLANKED": 
                if ($("#split-mode").is(":checked")) {
                    analysisData = {
                        maxrate: AppState.globalAnalysis.maxrate_non_blanked * getTimeUnitMultiplier('minutes'),
                        slope: AppState.globalAnalysis.slope_non_blanked * getTimeUnitMultiplier('minutes'),
                        saturationValue: AppState.globalAnalysis.sat_non_blanked,
                        timeToSaturation: AppState.globalAnalysis.time_to_sat_non_blanked / getTimeUnitMultiplier('minutes'),
                        measurement: AppState.globalAnalysis.meas,
                        measUnit: AppState.globalAnalysis.meas_unit
                    };
                }
                break;
        }
        sendExportData(AppState.processedExpPath, saveFile, analysisData, concentration, timeUnit, $("#exp-json-blank-type").val());

    } else if (AppState.currentMeasurementMode === "point") {
        // Store current experiment values
        const currExpTimePoint = $("#exp-json-time-value").val();
        let currExpBlankType = $("#exp-json-blank-type").val();
        let globalEstimatedValue = null;
        console.log("point data is ", AppState.responseData);
        if (currExpTimePoint) {
            globalEstimatedValue = getEstimatedValue(AppState.responseData, currExpTimePoint * 60, currExpBlankType).toFixed(4);
        }
        if (currExpTimePoint) { 
            analysisData = {
                estValue: globalEstimatedValue,
                timePoint: currExpTimePoint,
                measurement: AppState.globalAnalysis.meas,
                measUnit: AppState.globalAnalysis.meas_unit
            } 
            sendExportData(AppState.processedExpPath, saveFile, analysisData, concentration, timeUnit, $("#exp-json-blank-type").val());
            if (AppState.globalAnalysis.meas_unit !== "NONE")
                $("#est-val-exp").text(`Estimated ${AppState.globalAnalysis.meas} value being exported is ${globalEstimatedValue}${AppState.globalAnalysis.meas_unit}`);
            else 
                $("#est-val-exp").text(`Estimated ${AppState.globalAnalysis.meas} value being exported is ${globalEstimatedValue}`);
        } else {
            alert("Please set the reference time point to export data");
        }
    }
}

function sendExportData(saveDir, saveFile, analysisData, concentration, timeUnit, blankedType, newFile=true) {
    console.log("analysisData is ", analysisData);
    if (analysisData) {
        const data = {
            save_dir: saveDir,
            save_file: saveFile,
            maxrate: analysisData.maxrate !== "--" ? analysisData.maxrate : "NONE",
            slope: analysisData.slope !== "--" ? analysisData.slope : "NONE",
            sat: analysisData.saturationValue !== "--" ? analysisData.saturationValue : "NONE",
            timeSat: analysisData.timeToSaturation !== "--" ? analysisData.timeToSaturation : "NONE",
            con: concentration,
            measUnit: analysisData.measUnit, 
            blanked: blankedType,
            timeUnit: timeUnit,
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
    if ($("#cal-mode-select").val() === "point" && (!$("#regressed-time-point").val())){
        alert("Please set time point to regress data from");
        return null;
    } else {
        if (AppState.exp_json_content) {
            const data = {
                fit_type: $("#exp-json-regress-algo").val(),
                for_meas: AppState.exp_json_content.meas,
                for_blank_type: $("#exp-json-blank-type").val(),
                coef_content: AppState.exp_json_content.analysis,
                time: $("#regressed-time-point").val(),
                file_name: $("#save-json-file").val(),
                cal_mode: $("#cal-mode-select").val(),
                cal_params: Array.from(selectElement.options).map(option => { return option.dataset.original }),
                threshold_val: $("#threshold-value").val()
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