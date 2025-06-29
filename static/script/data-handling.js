function selectFile(fileName, button, tableSelector = "#file-table") {        
    // Clear previous selection and highlight the current row
    $(`${tableSelector} tr`).removeClass("selected");
    $(button).closest("tr").addClass("selected");

    if (tableSelector === "#file-table") {
        currentFile = fileName;
        processDataDisplay(currentFile);
    } else if (tableSelector === "#json-table") {
        currentJSON = fileName;
        fetchJSON(currentJSON, function(JSON_content, JSON_path) {
            $("#json-display").text(`Current mode is \"${currentMeasurementMode}\".\nJSON file read from ${JSON_path}\n`);
            if (currentMeasurementMode === "kinetics") {
                $("#json-display").append("Quantity value is either Vmax, Slope, Saturation, Time to Saturation, which ever is set by user.\n");
            } else if (currentMeasurementMode === "point") {
                 $("#json-display").append("Quantity value is the Absorbance value read from selected data file whose recorded time is the closest to the time set in this JSON.\n");
            }
            $("#json-display").append(`${json_msg}`);
            $("#json-display").append(JSON.stringify(JSON_content, null, 4));
            currentJSONcontent = JSON_content;
            if (currentFile) 
                processDataDisplay(currentFile, currentJSONcontent);
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
        currentFile = null;
        $("#analysis-info").text("");
        updateFileDisplay(currentFile);
    } else if (tableSelector === "#json-table") {
        currentJSON = null;
        currentJSONcontent = null;
        $("#json-display").text("");
        processDataDisplay(currentFile, currentJSONcontent);
        $("#derived-concentration-section").addClass("hidden");
        $("#blank-derived-concentration-section").addClass("hidden");
        $("#non-blank-derived-concentration-section").addClass("hidden");
        $("#point-json-exp-section").addClass("hidden");
    }
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

// Triggered only after entries is changed
function populateDropdown(entries, dropdownId = 'regressed-time-point') {
    if (prevDropdownEntries && arraysEqual(prevDropdownEntries, entries)) {
        return prevDropdownEntries;
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
    return entries.sort((a, b) => b - a);
}

function fetchData(range, unit, window_size, filename, jsonFile) {
    const fullPath = $("#directory").val() + delimiter + filename;
    $.get('/get_data', {
        file: $("#directory").val() + delimiter + filename
    }, function(response) {
        if (response.data && response.data.length > 0) {
            if (window_size > response.data.length / 2) {
                $("#plot-canvas, #blanked-canvas, #non-blanked-canvas").hide();
                $("#analysis-info").html(`<span style="color: red;">Window Size is greater than half of data size. The file has only ${response.data.length} data points</span>`);
            } else {
                let derivedConSettings = null;
                let derived_section = null;
                let derived_con_text = null;
                if (jsonFile) {
                    derivedConSettings = settingDerivedCon(jsonFile);
                    derived_section = derivedConSettings.derived_section;
                    derived_con_text = derivedConSettings.derived_con_text;
                    if (derived_section) {
                        derived_section.classList.remove("hidden");
                    } else { // derived_section is null -> hide all
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

                if (currentMeasurementMode === "point" && jsonFile) {
                    analysis = updatePlot(response.data, range, unit, window_size, response.unit || "NONE", isSplitMode, isFullDisplay, refCalPoint, jsonFile["for_blank_type"]);
                } else {
                    if (currentMeasurementMode === "calibrate") {
                        const cal_type = $("#cal-mode-select").val();
                        // const regress_algo = $("#exp-json-time-point").val();
                        if (cal_type === "kinetics") {
                            const quantity_obj = document.getElementById('regressed-quantity');
                            exp_json_content = updatePlot(response.data, range=null, timeUnit=null, window_size=null, response.data[0]["MeasUnit"], isSplitMode, true, null, null, "Concentration", quantity_obj.selectedOptions[0].text);
                        } else if (cal_type === "point") {
                            const uniqueTimePoints = getUniqueColumnEntries(response.data, 'TimePoint');
                            prevDropdownEntries = populateDropdown(uniqueTimePoints);
                            const timePoint = $("#regressed-time-point").val();
                            const processingData = response.data.filter(row => !timePoint || parseFloat(row["TimePoint"]) === parseFloat(timePoint));
                            exp_json_content = updatePlot(processingData, range=null, timeUnit=null, window_size=null, response.data[0]["MeasUnit"], isSplitMode, true, null, null, "Concentration", "Value");
                        }
                    } else {
                        analysis = updatePlot(response.data, range, unit, window_size, response.unit || "NONE", isSplitMode, isFullDisplay);
                    }
                }

                if (currentMeasurementMode !== "calibrate") {                            
                    const conValueInput = document.getElementById('con-value-read');
                    const conValueFromFile = response.data.map(row => row['Concentration'])[0];

                    if (conValueFromFile !== "NONE") {
                        conValueInput.value = conValueFromFile;
                        conValueInput.disabled = true;
                    } else {
                        conValueInput.disabled = false;
                        conValueInput.value = "";
                    }

                    if (currentMeasurementMode === "kinetics") {
                        const conQuantityInput = document.getElementById('regressed-quantity').value;
                        if (jsonFile) {
                            const coef = jsonFile[conQuantityInput]["fit_coef"];
                            let value = null;
                            switch(conQuantityInput) {
                                case "vmax":
                                    if (jsonFile["for_blank_type"] === "MIXED") {
                                        value = analysis.vmax * 60;
                                    } else if (jsonFile["for_blank_type"] === "BLANKED") {
                                        value = analysis.vmax_blanked * 60;
                                    } else if (jsonFile["for_blank_type"] === "NON-BLANKED") {
                                        value = analysis.vmax_non_blanked * 60;
                                    }
                                    break;
                                case "slope":
                                    if (jsonFile["for_blank_type"] === "MIXED") {
                                        value = analysis.slope * 60;
                                    } else if (jsonFile["for_blank_type"] === "BLANKED") {
                                        value = analysis.slope_blanked * 60;
                                    } else if (jsonFile["for_blank_type"] === "NON-BLANKED") {
                                        value = analysis.slope_non_blanked * 60;
                                    }
                                    break;
                                case "sat":
                                    if (jsonFile["for_blank_type"] === "MIXED") {
                                        value = analysis.sat;
                                    } else if (jsonFile["for_blank_type"] === "BLANKED") {
                                        value = analysis.sat_blanked;
                                    } else if (jsonFile["for_blank_type"] === "NON-BLANKED") {
                                        value = analysis.sat_non_blanked;
                                    }
                                    break;
                                case "time_to_sat":
                                    if (jsonFile["for_blank_type"] === "MIXED") {
                                        value = analysis.time_to_sat / 60;
                                    } else if (jsonFile["for_blank_type"] === "BLANKED") {
                                        value = analysis.time_to_sat_blanked / 60;
                                    } else if (jsonFile["for_blank_type"] === "NON-BLANKED") {
                                        value = analysis.time_to_sat_non_blanked / 60;
                                    }
                                    break;
                            }
                            calculated_con = computeFit(value, jsonFile["fit_type"], coef);
                            derived_con_text.innerHTML = `${calculated_con}`;
                        }
                    } else if (currentMeasurementMode === "point") {
                        if (jsonFile) {
                            const timeUnitSet = $("#time-unit").val();
                            const calPoint = $("#cal-point");
                            $("#point-json-exp-section").removeClass("hidden");

                            const jsonTimePoint = jsonFile["time"];
                            const jsonTimeUnit = jsonFile["time-unit"];

                            const baseMultiplier = getTimeUnitMultiplier(jsonTimeUnit);
                            const targetMultiplier = getTimeUnitMultiplier(timeUnitSet);
                            const conversionFactor = baseMultiplier / targetMultiplier;
                            refCalPoint = jsonTimePoint * conversionFactor;
                            calPoint.text(refCalPoint);

                            const estValueRead = getEstimatedValue(response.data, jsonTimePoint * 60, jsonFile["for_blank_type"]).toFixed(4);
                            if (estValueRead) {
                                const unitPrinted = response.data[0]["Unit"] === "NONE" ? "" : response.data[0]["Unit"];
                                $("#add-json-section").text(`. The estimated ${analysis.meas} value read from recorded data is ${estValueRead}${unitPrinted}.`);
                            } else {
                                $("#add-json-section").text("");
                            }
                            calculated_con = computeFit(estValueRead, jsonFile["fit_type"], jsonFile["fit_coef"]);
                            derived_con_text.innerHTML = `${calculated_con}`;
                        }
                        currExpTimePoint = $("#exp-json-time-value").val();
                        let currExpBlankType = $("#exp-json-blank-type").val();
                        if (currExpTimePoint) {
                            globalEstimatedValue = getEstimatedValue(response.data, currExpTimePoint * 60, currExpBlankType);
                        }
                    }
                } else {
                    $("#derived-concentration-section").addClass("hidden");
                    $("#blank-derived-concentration-section").addClass("hidden");
                    $("#non-blank-derived-concentration-section").addClass("hidden");
                }
            }
        } else {
            $("#plot-canvas, #blanked-canvas, #non-blanked-canvas").hide();
            $("#analysis-info").html(`<span style="color: red;">No data available</span>`);
        }
    }).fail(function(xhr, status, error) {
        console.error("Failed to fetch data:", status, error, xhr.responseText);
    }); // Close $.get callback
} // Close fetchData function

function toggleMode() {
    if (currentFile) {
        if (currentMeasurementMode !== "calibrate") {
            let range = $("#range-value").val();
            let unit = $("#time-unit").val();
            let window_size = $("window_size").val();
            fetchData(range, unit, window_size, currentFile);
        } else fetchData(null, null, null, currentFile);
    }
}

function exportData() {
    if ($("#time-unit").val() === "minutes") {
        processedExpPath = $("#save-dir").val().trim() || "";
        const saveFile = $("#save-file").val().trim() || "results";
        const concentration = $("#con-value-read").val() || "NONE";
        const timeUnit = $("#time-unit").val();
        let analysisData = null;
        let newFile = true;

        bindButtonToString("#go-to-exp-btn", processedExpPath);
        
        if (currentMeasurementMode === "kinetics") {
            switch ($("#exp-json-blank-type").val()) {
                case "MIXED":
                    if (!$("#split-mode").is(":checked")) {
                        analysisData = {
                            Vmax: analysis.vmax * getTimeUnitMultiplier('minutes'),
                            slope: analysis.slope * getTimeUnitMultiplier('minutes'),
                            saturationValue: analysis.sat,
                            timeToSaturation: analysis.time_to_sat / getTimeUnitMultiplier('minutes'),
                            measurement: analysis.meas,
                            measUnit: analysis.meas_unit
                        };
                    }
                    break;

                case "BLANKED":
                    if ($("#split-mode").is(":checked")) {
                        analysisData = {
                            Vmax: analysis.vmax_blanked * getTimeUnitMultiplier('minutes'),
                            slope: analysis.slope_blanked * getTimeUnitMultiplier('minutes'),
                            saturationValue: analysis.sat_blanked,
                            timeToSaturation: analysis.time_to_sat_blanked / getTimeUnitMultiplier('minutes'),
                            measurement: analysis.meas,
                            measUnit: analysis.meas_unit
                        };
                    }
                    break;

                case "NON-BLANKED": 
                    if ($("#split-mode").is(":checked")) {
                        analysisData = {
                            Vmax: analysis.vmax_non_blanked * getTimeUnitMultiplier('minutes'),
                            slope: analysis.slope_non_blanked * getTimeUnitMultiplier('minutes'),
                            saturationValue: analysis.sat_non_blanked,
                            timeToSaturation: analysis.time_to_sat_non_blanked / getTimeUnitMultiplier('minutes'),
                            measurement: analysis.meas,
                            measUnit: analysis.meas_unit
                        };
                    }
                    break;
            }
            sendExportData(processedExpPath, saveFile, analysisData, concentration, timeUnit, $("#exp-json-blank-type").val());

        } else if (currentMeasurementMode === "point") {
            if (currExpTimePoint) { 
                analysisData = {
                    estValue: globalEstimatedValue,
                    timePoint: currExpTimePoint,
                    measurement: analysis.meas,
                    measUnit: analysis.meas_unit
                } 
                sendExportData(processedExpPath, saveFile, analysisData, concentration, timeUnit, $("#exp-json-blank-type").val());
                if (analysis.meas_unit !== "NONE")
                    $("#est-val-exp").text(`Estimated ${analysis.meas} value being exported is ${globalEstimatedValue}${analysis.meas_unit}`);
                else 
                    $("#est-val-exp").text(`Estimated ${analysis.meas} value being exported is ${globalEstimatedValue}`);
            } else {
                alert("Please set the reference time point to export data");
            }
        }
    } else {
        alert(`Please change your units in Display Range section from ${$("#time-unit").val()} to minutes!`);
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
            measMode: currentMeasurementMode,
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
        if (exp_json_content) {
            const data = {
                fit_type: $("#exp-json-regress-algo").val(),
                for_meas: exp_json_content.meas,
                for_blank_type: $("#exp-json-blank-type").val(),
                coef_content: exp_json_content.analysis,
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