function selectFile(fileName, button, tableSelector = "#file-table") {        
    // Clear previous selection and highlight the current row
    $(`${tableSelector} tr`).removeClass("selected");
    $(button).closest("tr").addClass("selected");

    if (tableSelector === "#file-table") {
        AppState.prevFile = AppState.currentFile;
        AppState.currentFile = fileName;
        processDataDisplay(AppState.currentFile);
    } else if (tableSelector === "#json-table") {
        AppState.currentJSON = fileName;
        fetchJSON(AppState.currentJSON, function(JSON_content, JSON_path) {
            $("#json-display").text(`Current mode is \"${AppState.currentMeasurementMode}\".\nJSON file read from ${JSON_path}\n`);
            if (AppState.currentMeasurementMode === "kinetics") {
                $("#json-display").append("Quantity value is either Vmax, Slope, Saturation, Time to Saturation, which ever is set by user.\n");
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
}

function processDataDisplay(fileName, jsonFileContent=null) {
    // Get user inputs
    let range = $("#range-value").val();
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
    fetchData(range, unit, window_size, fileName, jsonFileContent);
    updateFileDisplay(fileName);
}


function deselectFile(tableSelector="#file-table") {
    $(`${tableSelector} tr`).removeClass("selected");
    if (tableSelector === "#file-table") {
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
                const terminateBtn = $('#terminate-script-btn');
                if (terminateBtn.length) {
                    terminateBtn.focus();
                    terminateBtn.addClass('blinking');
                    setTimeout(() => {
                        terminateBtn.removeClass('blinking');
                    }, 5000);
                }
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
                                const terminateBtn = $('#terminate-script-btn');
                                if (terminateBtn.length) {
                                    terminateBtn.focus();
                                    terminateBtn.addClass('blinking');
                                    setTimeout(() => {
                                        terminateBtn.removeClass('blinking');
                                    }, 5000);
                                }
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
                            const terminateBtn = $('#terminate-script-btn');
                            if (terminateBtn.length) {
                                terminateBtn.focus();
                                terminateBtn.addClass('blinking');
                                setTimeout(() => {
                                    terminateBtn.removeClass('blinking');
                                }, 5000);
                            }
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
                                const terminateBtn = $('#terminate-script-btn');
                                if (terminateBtn.length) {
                                    terminateBtn.focus();
                                    terminateBtn.addClass('blinking');
                                    setTimeout(() => {
                                        terminateBtn.removeClass('blinking');
                                    }, 5000);
                                }
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
                            const terminateBtn = $('#terminate-script-btn');
                            if (terminateBtn.length) {
                                terminateBtn.focus();
                                terminateBtn.addClass('blinking');
                                setTimeout(() => {
                                    terminateBtn.removeClass('blinking');
                                }, 5000);
                            }
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

function fetchData(range, unit, window_size, filename, jsonFile) {
    const fullPath = $("#directory").val() + delimiter + filename;
    $.get('/get_data', {
        file: $("#directory").val() + delimiter + filename
    }, function(response) {
        if (response.data && response.data.length > 0) {
            // if (window_size > response.data.length / 2) {
            //     $("#plot-canvas, #blanked-canvas, #non-blanked-canvas").hide();
            //     $("#analysis-info").html(`<span style="color: red;">Window Size is greater than half of data size. The file has only ${response.data.length} data points</span>`);
            // } else {
            let derivedConSettings = null;
            let derived_section = null;
            let derived_con_text = null;
            if (jsonFile && AppState.currentMeasurementMode !== "calibrate") {
                derivedConSettings = settingDerivedCon(jsonFile);
                derived_section = derivedConSettings.derived_section;
                derived_con_text = derivedConSettings.derived_con_text;
                if (derived_section) {
                    derived_section.classList.remove("hidden");
                    if (AppState.currentMeasurementMode === "kinetics") {
                        $("#select-quantity-section").removeClass("hidden");
                    } else {
                        $("#select-quantity-section").addClass("hidden");
                    }
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

            // Move event listener outside the AJAX callback or nest it properly
            fullDisplayCheckbox.addEventListener('change', function() {
                const originalValue = displayRangeInput.value; // Fixed 'input' to 'value'
                if (this.checked) {
                    displayRangeInput.disabled = true;
                    displayRangeInput.placeholder = "Disabled by Full Display";
                    displayRangeInput.value = "";
                } else {
                    displayRangeInput.disabled = false;
                    displayRangeInput.value = originalValue || 1000; // Restore original or default to 1000
                }
            });

            if (AppState.currentMeasurementMode !== "calibrate") {                            
                const conValueInput = document.getElementById('con-value-read');
                const conValueFromFile = response.data.map(row => row['Concentration'])[0];

                if (conValueFromFile !== "NONE") {
                    conValueInput.value = conValueFromFile;
                    conValueInput.disabled = true;
                } else {
                    conValueInput.disabled = false;
                    conValueInput.value = "";
                }

                if (AppState.currentMeasurementMode === "kinetics") {
                    const conQuantityInput = document.getElementById('regressed-quantity').value;
                    if (jsonFile) {
                        const coef = jsonFile[conQuantityInput]["fit_coef"];
                        let value = null;
                        switch(conQuantityInput) {
                            case "vmax":
                                if (jsonFile["for_blank_type"] === "MIXED") {
                                    value = AppState.globalAnalysis.vmax * 60;
                                } else if (jsonFile["for_blank_type"] === "BLANKED") {
                                    value = AppState.globalAnalysis.vmax_blanked * 60;
                                } else if (jsonFile["for_blank_type"] === "NON-BLANKED") {
                                    value = AppState.globalAnalysis.vmax_non_blanked * 60;
                                }
                                break;
                            case "slope":
                                if (jsonFile["for_blank_type"] === "MIXED") {
                                    value = AppState.globalAnalysis.slope * 60;
                                } else if (jsonFile["for_blank_type"] === "BLANKED") {
                                    value = AppState.globalAnalysis.slope_blanked * 60;
                                } else if (jsonFile["for_blank_type"] === "NON-BLANKED") {
                                    value = AppState.globalAnalysis.slope_non_blanked * 60;
                                }
                                break;
                            case "sat":
                                if (jsonFile["for_blank_type"] === "MIXED") {
                                    value = AppState.globalAnalysis.sat;
                                } else if (jsonFile["for_blank_type"] === "BLANKED") {
                                    value = AppState.globalAnalysis.sat_blanked;
                                } else if (jsonFile["for_blank_type"] === "NON-BLANKED") {
                                    value = AppState.globalAnalysis.sat_non_blanked;
                                }
                                break;
                            case "time_to_sat":
                                if (jsonFile["for_blank_type"] === "MIXED") {
                                    value = AppState.globalAnalysis.time_to_sat / 60;
                                } else if (jsonFile["for_blank_type"] === "BLANKED") {
                                    value = AppState.globalAnalysis.time_to_sat_blanked / 60;
                                } else if (jsonFile["for_blank_type"] === "NON-BLANKED") {
                                    value = AppState.globalAnalysis.time_to_sat_non_blanked / 60;
                                }
                                break;
                        }
                        calculated_con = computeFit(value, jsonFile["fit_type"], coef);
                        derived_con_text.innerHTML = `${calculated_con}`;
                    }
                } else if (AppState.currentMeasurementMode === "point") {
                    if (jsonFile) {
                        const timeUnitSet = $("#time-unit").val();
                        const calPoint = $("#cal-point");
                        $("#point-json-exp-section").removeClass("hidden");

                        const jsonTimePoint = jsonFile["time"];
                        const jsonTimeUnit = jsonFile["time-unit"];

                        const baseMultiplier = getTimeUnitMultiplier(jsonTimeUnit + "s");
                        const targetMultiplier = getTimeUnitMultiplier(timeUnitSet);
                        const conversionFactor = baseMultiplier / targetMultiplier;
                        AppState.refCalPoint = jsonTimePoint * conversionFactor;
                        calPoint.text(AppState.refCalPoint);

                        const estValueRead = getEstimatedValue(response.data, jsonTimePoint * 60, jsonFile["for_blank_type"]).toFixed(4);
                        if (estValueRead) {
                            const unitPrinted = response.data[0]["Unit"] === "NONE" ? "" : response.data[0]["Unit"];
                            $("#add-json-section").text(`The estimated ${AppState.globalAnalysis.meas} value read from recorded data is ${estValueRead}${unitPrinted}.`);
                        } else {
                            $("#add-json-section").text("");
                        }
                        calculated_con = computeFit(estValueRead, jsonFile["fit_type"], jsonFile["fit_coef"]);
                        derived_con_text.innerHTML = `${calculated_con}`;
                    }
                    AppState.currExpTimePoint = $("#exp-json-time-value").val();
                    let currExpBlankType = $("#exp-json-blank-type").val();
                    if (AppState.currExpTimePoint) {
                        AppState.globalEstimatedValue = getEstimatedValue(response.data, AppState.currExpTimePoint * 60, currExpBlankType);
                    }
                }
            } else {
                if ($("#cal-mode-select").val() === "kinetics") {
                    $("#select-quantity-section").removeClass("hidden");
                }
                $("#derived-concentration-section").addClass("hidden");
                $("#blank-derived-concentration-section").addClass("hidden");
                $("#non-blank-derived-concentration-section").addClass("hidden");
            }

            if (AppState.currentMeasurementMode === "point" && jsonFile) {
                AppState.globalAnalysis = updatePlot(response.data, range, unit, window_size, response.unit || "NONE", isSplitMode, isFullDisplay, AppState.refCalPoint, jsonFile["for_blank_type"]);
            } else {
                if (AppState.currentMeasurementMode === "calibrate") {
                    const cal_type = $("#cal-mode-select").val();
                    // const regress_algo = $("#exp-json-time-point").val();
                    if (cal_type === "kinetics") {
                        const quantity_obj = document.getElementById('regressed-quantity');
                        AppState.exp_json_content = updatePlot(response.data, range=null, timeUnit=null, window_size=null, response.data[0]["MeasUnit"], isSplitMode, true, null, null, "Concentration", quantity_obj.selectedOptions[0].text);
                    } else if (cal_type === "point") {
                        const uniqueTimePoints = getUniqueColumnEntries(response.data, 'TimePoint');
                        console.log("Give me uniqueTimePoints ", uniqueTimePoints);
                        AppState.prevDropdownEntries = populateDropdown(uniqueTimePoints);
                        const timePoint = $("#regressed-time-point").val();
                        const processingData = response.data.filter(row => !timePoint || parseFloat(row["TimePoint"]) === parseFloat(timePoint));
                        AppState.exp_json_content = updatePlot(processingData, range=null, timeUnit=null, window_size=null, response.data[0]["MeasUnit"], isSplitMode, true, null, null, "Concentration", "Value");
                    }
                } else {
                    AppState.globalAnalysis = updatePlot(response.data, range, unit, window_size, response.unit || "NONE", isSplitMode, isFullDisplay);
                }
            }
            // }
        } else {
            $("#plot-canvas, #blanked-canvas, #non-blanked-canvas").hide();
            $("#analysis-info").html(`<span style="color: red;">No data available</span>`);
        }
    }).fail(function(xhr, status, error) {
        console.error("Failed to fetch data:", status, error, xhr.responseText);
    }); // Close $.get callback
} // Close fetchData function

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
        } else fetchData(null, null, null, AppState.currentFile, AppState.currentJSONcontent);
    }
}

function exportData() {
    AppState.processedExpPath = $("#save-dir").val().trim() || "";
    const saveFile = $("#save-file").val().trim() || "results";
    const concentration = $("#con-value-read").val() || "NONE";
    const timeUnit = $("#time-unit").val();
    let analysisData = null;

    bindButtonToString("#go-to-exp-btn", AppState.processedExpPath);
    
    if (AppState.currentMeasurementMode === "kinetics") {
        switch ($("#exp-json-blank-type").val()) {
            case "MIXED":
                if (!$("#split-mode").is(":checked")) {
                    analysisData = {
                        Vmax: AppState.globalAnalysis.vmax * getTimeUnitMultiplier('minutes'),
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
                        Vmax: AppState.globalAnalysis.vmax_blanked * getTimeUnitMultiplier('minutes'),
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
                        Vmax: AppState.globalAnalysis.vmax_non_blanked * getTimeUnitMultiplier('minutes'),
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
        if (AppState.currExpTimePoint) { 
            analysisData = {
                estValue: AppState.globalEstimatedValue,
                timePoint: AppState.currExpTimePoint,
                measurement: AppState.globalAnalysis.meas,
                measUnit: AppState.globalAnalysis.meas_unit
            } 
            sendExportData(AppState.processedExpPath, saveFile, analysisData, concentration, timeUnit, $("#exp-json-blank-type").val());
            if (AppState.globalAnalysis.meas_unit !== "NONE")
                $("#est-val-exp").text(`Estimated ${AppState.globalAnalysis.meas} value being exported is ${AppState.globalEstimatedValue}${AppState.globalAnalysis.meas_unit}`);
            else 
                $("#est-val-exp").text(`Estimated ${AppState.globalAnalysis.meas} value being exported is ${AppState.globalEstimatedValue}`);
        } else {
            alert("Please set the reference time point to export data");
        }
    }
}

function sendExportData(saveDir, saveFile, analysisData, concentration, timeUnit, blankedType, newFile=true) {
    if (analysisData) {
        const data = {
            save_dir: saveDir,
            save_file: saveFile,
            vmax: analysisData.Vmax !== "--" ? analysisData.Vmax : "NONE",
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