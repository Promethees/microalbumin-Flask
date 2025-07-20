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

function editFile(fileName, button, tableSelector = "#file-table") {
    if (tableSelector !== "#file-table") {
        Swal.fire({
            title: 'Error!',
            text: 'Editing is only supported for CSV files in #file-table.',
            icon: 'error',
            confirmButtonText: 'OK'
        });
        return;
    }

    checkScriptStatus().then((isRunning) => {
        if (isRunning || AppState.scriptRunning) {
            Swal.fire({
                title: 'Error!',
                text: 'Cannot edit files while the data collection process is running. Stop the process and try again.',
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

        const row = $(button).closest("tr");
        const deleteBtn = row.find("button:contains('Delete')");
        deleteBtn.prop('disabled', true).addClass('disabled').attr('aria-disabled', 'true');

        let editMode = 'table'; // Default to table mode
        let originalContent = ''; // Store original content for reference

        function renderContent(content) {
            originalContent = content.content; // Store the original content
            let html = '';
            if (editMode === 'text') {
                html = `
                    Rename:<input type="text" id="swal-input-filename" class="swal2-input" value="${fileName}" placeholder="Enter new filename">
                    <textarea id="swal-input-content" class="swal2-input" rows="10" style="width: 100%; height: 200px;">${content.content}</textarea>
                `;
            } else {
                const lines = content.content.trim().split('\n');
                const headers = lines[0].split(',');
                const data = lines.slice(1);
                
                html = `
                    Rename:<input type="text" id="swal-input-filename" class="swal2-input" value="${fileName}" placeholder="Enter new filename">
                    <div style="max-height: 400px; overflow-y: auto; margin-top: 10px;">
                        <table id="swal-edit-table" style="width: 100%; border-collapse: collapse;">
                            <thead>
                                <tr style="position: sticky; top: 0; background: white;">
                                    ${headers.map(col => `<th style="border: 1px solid #ddd; padding: 8px; text-align: left;">${col}</th>`).join('')}
                                </tr>
                            </thead>
                            <tbody id="swal-edit-body">
                                ${data.map((row, rowIndex) => {
                                    const cells = row.split(',');
                                    return `<tr>
                                        ${cells.map((cell, cellIndex) => 
                                            cellIndex === 0 || cellIndex === 2 ?
                                            `
                                            <td contenteditable="true" 
                                                style="border: 1px solid #ddd; padding: 8px;"
                                                data-col="${headers[cellIndex]}"
                                                data-row="${rowIndex}">
                                                ${cell.trim()}
                                            </td>
                                            ` :
                                            `<td contenteditable="false" 
                                                style="border: 1px solid #ddd; padding: 8px;"
                                                data-col="${headers[cellIndex]}"
                                                data-row="${rowIndex}">
                                                ${cell.trim()}
                                            </td>`).join('')}
                                    </tr>`;
                                }).join('')}
                            </tbody>
                        </table>
                    </div>
                    <p style="font-size: 0.8em; color: #666; margin-top: 5px;">
                        Click cells to edit. Save to apply changes.
                    </p>
                `;
            }
            return html;
        }

        // Fetch CSV content
        $.get(`/get_file_content?file=${encodeURIComponent(fileName)}&path=${encodeURIComponent($("#directory").val())}`, function(content) {
            Swal.fire({
                title: `Edit ${fileName}`,
                width: '800px',
                html: renderContent(content),
                footer: '<button id="toggle-mode" class="swal2-confirm swal2-styled" style="margin-top: 10px;">Switch to ' + (editMode === 'text' ? 'Table' : 'Text') + ' Mode</button>',
                focusConfirm: false,
                showCancelButton: true,
                confirmButtonText: 'Save Changes',
                cancelButtonText: 'Cancel',
                confirmButtonColor: '#3085d6',
                cancelButtonColor: '#d33',
                didOpen: () => {
                    const toggleButton = document.getElementById('toggle-mode');
                    toggleButton.addEventListener('click', () => {
                        editMode = editMode === 'text' ? 'table' : 'text';
                        toggleButton.textContent = 'Switch to ' + (editMode === 'text' ? 'Table' : 'Text') + ' Mode';
                        Swal.getHtmlContainer().innerHTML = renderContent({content: originalContent});
                    });
                },
                preConfirm: () => {
                    const newFileName = document.getElementById('swal-input-filename').value;
                    let content;
                    
                    if (editMode === 'text') {
                        content = document.getElementById('swal-input-content').value;
                    } else {
                        // Reconstruct CSV from table
                        const table = document.getElementById('swal-edit-table');
                        const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent);
                        const rows = Array.from(table.querySelectorAll('tbody tr'));
                        
                        const csvRows = rows.map(row => {
                            return Array.from(row.querySelectorAll('td')).map(td => {
                                // Escape commas and newlines in cell content
                                let cellContent = td.textContent.trim();
                                if (cellContent.includes(',') || cellContent.includes('\n') || cellContent.includes('"')) {
                                    return `"${cellContent.replace(/"/g, '""')}"`;
                                }
                                return cellContent;
                            }).join(',');
                        });
                        
                        content = [headers.join(','), ...csvRows].join('\n');
                    }

                    if (!content.trim()) {
                        Swal.showValidationMessage('Content cannot be empty');
                        return false;
                    }
                    if (!newFileName.trim() || !newFileName.endsWith('.csv')) {
                        Swal.showValidationMessage('Filename must end with .csv');
                        return false;
                    }

                    // Define regex patterns
                    const headerPattern = /^Timestamp,Measurement,Value,Unit,Type,Blanked,Concentration$/;
                    const dataPattern = /^\d+\.\d{1,2},[A-Za-z]+,\d+\.\d{1,3},[A-Za-z]+,[A-Za-z]+,[A-Za-z]+,(NONE|\d+)$/;

                    const lines = content.trim().split('\n');
                    if (lines.length < 1) {
                        Swal.showValidationMessage('Content must contain at least the header');
                        return false;
                    }

                    // Validate header
                    if (!headerPattern.test(lines[0])) {
                        Swal.showValidationMessage('Invalid header. Must match: Timestamp,Measurement,Value,Unit,Type,Blanked,Concentration');
                        return false;
                    }

                    // Validate data rows
                    for (let i = 1; i < lines.length; i++) {
                        if (!dataPattern.test(lines[i])) {
                            Swal.showValidationMessage(`Invalid data in row ${i + 1}. Must match: \\d+\\.\\d{1,2},[A-Za-z]+,\\d+\\.\\d{1,3},[A-Za-z]+,[A-Za-z]+,[A-Za-z]+,(NONE|\\d+)`);
                            return false;
                        }
                    }

                    return { newFileName, content };
                }
            }).then((result) => {
                deleteBtn.prop('disabled', false).removeClass('disabled').attr('aria-disabled', 'false');

                if (result.isConfirmed) {
                    const { newFileName, content } = result.value;

                    $.post('/edit_file', {
                        filename: fileName,
                        new_filename: newFileName,
                        path: $("#directory").val(),
                        content: content
                    }, function(response) {
                        if (response.status === 'success') {
                            let textMsg;
                            if (fileName !== newFileName) {
                                row.find("td:first").text(newFileName);
                                row.find("button:contains('Select')").attr('onclick', `selectFile('${newFileName}', this, '#file-table')`);
                                row.find("button:contains('Edit')").attr('onclick', `editFile('${newFileName}', this, '#file-table')`);
                                row.find("button:contains('Delete')").attr('onclick', `deleteFile('${newFileName}', this, '#file-table')`);
                                if (AppState.currentFile === fileName) AppState.currentFile = newFileName;
                                textMsg = `File ${fileName} renamed to ${newFileName} and content updated successfully.`;
                            } else {
                                textMsg = `File ${fileName} content updated successfully.`;
                            }
                            Swal.fire({
                                title: 'Updated!',
                                text: textMsg,
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
                            });
                        }
                    }).fail(function(jqXHR) {
                        let errorMessage = 'An unexpected error occurred while saving the file';
                        if (jqXHR.responseJSON?.message) {
                            errorMessage = jqXHR.responseJSON.message;
                        } else if (jqXHR.status === 400) {
                            errorMessage = 'Invalid request';
                        } else if (jqXHR.status === 403) {
                            errorMessage = 'Permission denied';
                        } else if (jqXHR.status === 404) {
                            errorMessage = 'File not found';
                        } else if (jqXHR.status === 423) {
                            errorMessage = 'File is locked by the data collection process';
                        }
                        
                        Swal.fire({
                            title: 'Error!',
                            text: errorMessage,
                            icon: 'error',
                            confirmButtonText: 'OK'
                        });
                    });
                }
            });
        }).fail(function(jqXHR) {
            let errorMessage = 'Failed to load file content';
            if (jqXHR.responseJSON?.message) {
                errorMessage = jqXHR.responseJSON.message;
            } else if (jqXHR.status === 404) {
                errorMessage = 'File not found';
            } else if (jqXHR.status === 403) {
                errorMessage = 'Permission denied';
            } else if (jqXHR.status === 423) {
                errorMessage = 'File is in use by the data collection process';
            }
            
            Swal.fire({
                title: 'Error!',
                text: errorMessage,
                icon: 'error',
                confirmButtonText: 'OK'
            }).then(() => {
                deleteBtn.prop('disabled', false).removeClass('disabled').attr('aria-disabled', 'false');
            });
        });
    });
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
                    $("#select-quantity-section").removeClass("hidden");
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

                        const baseMultiplier = getTimeUnitMultiplier(jsonTimeUnit);
                        const targetMultiplier = getTimeUnitMultiplier(timeUnitSet);
                        const conversionFactor = baseMultiplier / targetMultiplier;
                        AppState.refCalPoint = jsonTimePoint * conversionFactor;
                        calPoint.text(AppState.refCalPoint);

                        const estValueRead = getEstimatedValue(response.data, jsonTimePoint * 60, jsonFile["for_blank_type"]).toFixed(4);
                        if (estValueRead) {
                            const unitPrinted = response.data[0]["Unit"] === "NONE" ? "" : response.data[0]["Unit"];
                            $("#add-json-section").text(`. The estimated ${AppState.globalAnalysis.meas} value read from recorded data is ${estValueRead}${unitPrinted}.`);
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
                $("#select-quantity-section").removeClass("hidden");
                $("#derived-concentration-section").addClass("hidden");
                $("#blank-derived-concentration-section").addClass("hidden");
                $("#non-blank-derived-concentration-section").addClass("hidden");
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
    if ($("#full-display").is(":checked") && AppState.currentMeasurementMode !== "calibrate") {
        $("#quantity-checkboxes").removeClass("hidden");
    } else {   
        $("#quantity-checkboxes").addClass("hidden");
    }
    if (AppState.currentFile) {
        // Nullify previous file so that graphics can be redrawn
        AppState.prevFile = null; 
        if (AppState.currentMeasurementMode !== "calibrate") {
            let range = $("#range-value").val();
            let unit = $("#time-unit").val();
            let window_size = $("window_size").val();
            fetchData(range, unit, window_size, AppState.currentFile, AppState.currentJSONcontent);
        } else fetchData(null, null, null, AppState.currentFile, AppState.currentJSONcontent);
    }
}

function exportData() {
    if ($("#time-unit").val() === "minutes") {
        AppState.processedExpPath = $("#save-dir").val().trim() || "";
        const saveFile = $("#save-file").val().trim() || "results";
        const concentration = $("#con-value-read").val() || "NONE";
        const timeUnit = $("#time-unit").val();
        let analysisData = null;
        let newFile = true;

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