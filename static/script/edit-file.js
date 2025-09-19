function editFile(fileName, button, tableSelector = "#file-table") {
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

        let editMode = tableSelector === '#file-table' ? 'table' : 'text'; // Force text mode for non-#file-table
        let originalContent = ''; // Store original content for reference

        const nonEditableColumns = ['Unit', 'Type', 'Blanked', 'Concentration', 'BlankType'];
        const nonEditableMetadata = ['TimeUnit', 'MeasMode'];

        function setupTableEvents() {
            const table = document.getElementById('swal-edit-table');
            if (!table) return;

            const addRowBtn = document.getElementById('add-row-btn');
            const deleteRowBtn = document.getElementById('delete-row-btn');
            let selectedRow = null;

            // Row selection
            table.addEventListener('click', function(e) {
                const cell = e.target.closest('td, th');
                if (!cell) return;
                
                const row = cell.closest('tr');
                if (!row || row.parentNode.tagName !== 'TBODY') return;
                
                // Clear previous selection
                const previouslySelected = table.querySelector('tr.selected');
                if (previouslySelected) {
                    previouslySelected.classList.remove('selected');
                }
                
                // Set new selection
                row.classList.add('selected');
                selectedRow = row;
                if (deleteRowBtn) deleteRowBtn.disabled = false;
                
                // If clicking an editable cell, focus it
                if (cell.tagName === 'TD' && cell.contentEditable === 'true') {
                    cell.focus();
                }
            });

            // Add row
            if (addRowBtn) {
                addRowBtn.addEventListener('click', function() {
                    const tbody = document.getElementById('swal-edit-body');
                    if (!tbody) return;
                    
                    const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
                    const newRow = document.createElement('tr');
                    newRow.dataset.rowIndex = tbody.children.length;
                    
                    // Get reference values from first existing row (if available)
                    const referenceValues = {};
                    const defaultValues = {'Timestamp': '0.00', 'Measurement': 'ABSORBANCE', 'Unit': 'NONE',
                                            'Type': 'NONE', 'Blanked': 'FALSE', 'Concentration': 'NONE', 
                                            'Value': '0.00', 'maxRate': '0.00', 'Slope': '0.00',
                                            'Sat': '0.00', 'Time To Sat': '0.00', 'MeasUnit': 'NONE',
                                            'TimeUnit': 'minutes', 'BlankType': 'NONE', 'MeasMode': 'kinetics',
                                            'TimePoint': '0'};
                    if (tbody.children.length > 0) {
                        const firstRow = tbody.children[0];
                        headers.forEach((header, index) => {
                            if (nonEditableColumns.includes(header)) {
                                if (header !== 'Concentration' || AppState.currentMeasurementMode !== 'calibrate') {
                                    referenceValues[header] = firstRow.children[index].textContent;
                                }
                            }
                        });
                    }
                    
                    headers.forEach((header, index) => {
                        let isEditable = true;
                        // In calibrate mode, 'Concentration' is editable
                        if (header !== 'Concentration' || AppState.currentMeasurementMode !== 'calibrate') {
                            isEditable = !nonEditableColumns.includes(header);
                        }
                        const td = document.createElement('td');
                        td.dataset.col = header;
                        
                        // Set default values
                        let defaultValue = '';
                        console.log(`References values are:`, referenceValues);
                        if (!isEditable && referenceValues[header]) {
                            defaultValue = referenceValues[header];
                        } else {
                            defaultValue = defaultValues[header] || '';
                        }
                        
                        td.textContent = defaultValue;
                        Object.assign(td.style, {
                            border: '1px solid #ddd',
                            padding: '6px',
                            fontSize: '0.82em',
                            backgroundColor: !isEditable ? '#f8f8f8' : '',
                            cursor: !isEditable ? 'not-allowed' : '',
                            whiteSpace: header === 'Timestamp' ? 'nowrap' : '',
                            textAlign: (header === 'Value' || header === 'Concentration') ? 'right' : ''
                        });
                        
                        if (isEditable) {
                            td.contentEditable = true;
                        }
                        
                        newRow.appendChild(td);
                    });
                    
                    tbody.appendChild(newRow);
                    // Auto-select the new row
                    if (selectedRow) {
                        selectedRow.classList.remove('selected');
                    }
                    newRow.classList.add('selected');
                    newRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    selectedRow = newRow;
                    if (deleteRowBtn) deleteRowBtn.disabled = false;
                });
            }

            // Delete row
            if (deleteRowBtn) {
                deleteRowBtn.addEventListener('click', function() {
                    if (selectedRow) {
                        selectedRow.remove();
                        selectedRow = null;
                        deleteRowBtn.disabled = true;
                    }
                });
            }
        }
        
        function renderContent(content) {
            originalContent = content.content; // Store the original content
            let html = '';

            if (editMode === 'text') {
                html = `
                    <input type="text" id="swal-input-filename" class="swal2-input" value="${fileName}" placeholder="Enter new filename">
                    <textarea id="swal-input-content" class="swal2-input" rows="10" style="width: 100%; height: 200px; font-family: monospace;">${content.content}</textarea>
                `;
            } else {
                const lines = content.content.trim().split('\n');

                // Separate metadata (lines starting with "#") and data lines
                const metadata = {};
                const dataLines = [];
                lines.forEach(line => {
                    if (line.startsWith("#")) {
                        const parts = line.substring(1).split(":");
                        if (parts.length === 2) {
                            metadata[parts[0].trim()] = parts[1].trim();
                        }
                    } else {
                        dataLines.push(line);
                    }
                });

                // Extract headers + data
                const headers = dataLines.length > 0 ? dataLines[0].split(',') : [];
                const data = dataLines.slice(1);

                // Build editable metadata table
                const metadataHtml = Object.keys(metadata).length > 0 ? `
                    <div class="metadata-box">
                        <h4>Metadata</h4>
                        <table id="swal-metadata-table" class="metadata-table">
                            <thead>
                                <tr>
                                    <th>Key</th>
                                    <th>Value</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${Object.entries(metadata).map(([key, value]) => {
                                    const isNonEditable = nonEditableMetadata.includes(key);
                                    return `
                                        <tr>
                                            <td class="metadata-key">${key}</td>
                                            <td 
                                                ${isNonEditable ? '' : 'contenteditable="true"'} 
                                                data-meta-key="${key}" 
                                                class="metadata-value ${isNonEditable ? 'noneditable' : ''}"
                                            >
                                                ${value}
                                            </td>
                                        </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    </div>
                ` : '';

                // Build data table
                html = `
                    <input type="text" id="swal-input-filename" class="swal2-input" value="${fileName}" placeholder="Enter new filename">
                    ${metadataHtml}
                    <div style="display: flex; justify-content: space-between; margin: 10px 0;">
                        <button id="add-row-btn" class="swal2-confirm swal2-styled" style="padding: 5px 10px;">
                            Add Row (+)
                        </button>
                        <button id="delete-row-btn" class="swal2-deny swal2-styled" style="padding: 5px 10px;" disabled>
                            Delete Selected Row (-)
                        </button>
                    </div>
                    <div style="max-height: 400px; overflow-y: auto; margin-top: 10px;">
                        <table id="swal-edit-table" style="width: 100%; border-collapse: collapse; font-family: Arial, sans-serif;">
                            <thead>
                                <tr style="position: sticky; top: 0; background: white; z-index: 10;">
                                    ${headers.map(col => `
                                        <th style="border: 1px solid #ddd; padding: 6px; text-align: left; 
                                            font-size: 0.85em; font-weight: bold; white-space: nowrap;">
                                            ${col}
                                        </th>
                                    `).join('')}
                                </tr>
                            </thead>
                            <tbody id="swal-edit-body">
                                ${data.map((row, rowIndex) => {
                                    const cells = row.split(',');
                                    return `<tr data-row-index="${rowIndex}">
                                        ${cells.map((cell, cellIndex) => {
                                            const columnName = headers[cellIndex];
                                            let isEditable = true;
                                            if (columnName !== 'Concentration' || AppState.currentMeasurementMode !== 'calibrate') {
                                                isEditable = !nonEditableColumns.includes(columnName);
                                            }
                                            return `
                                                <td ${isEditable ? 'contenteditable="true"' : 'class="non-editable"'} 
                                                    style="border: 1px solid #ddd; padding: 6px;
                                                    font-size: 0.82em;
                                                    ${!isEditable ? 'background-color: #f8f8f8; cursor: not-allowed;' : ''}
                                                    ${columnName === 'Timestamp' ? 'white-space: nowrap;' : ''}
                                                    ${columnName === 'Value' || columnName === 'Concentration' ? 'text-align: right;' : ''}"
                                                    data-col="${columnName}">
                                                    ${cell.trim()}
                                                </td>
                                            `;
                                        }).join('')}
                                    </tr>`;
                                }).join('')}
                            </tbody>
                        </table>
                    </div>
                    <p style="font-size: 0.8em; color: #666; margin-top: 5px;">
                        Click cells to edit (gray cells are read-only). Select rows to delete. Save to apply changes.
                    </p>
                `;
            }
            return html;
        }
        // const filePath = tableSelector === '#file-table' ? $("#directory").val() : AppState.jsonPath + delimiter + AppState.currentMeasurementMode;
        const filePath = tableSelector === '#file-table' ? $("#directory").val() : getNativePath(AppState.jsonPath, AppState.multiSource ? `${AppState.numSources}_sensors` : 'single_sensor', AppState.currentMeasurementMode);
        console.log("File Path is ", filePath);
        // Fetch CSV content
        $.get(`/get_file_content?file=${encodeURIComponent(fileName)}&path=${encodeURIComponent(filePath)}`, function(content) {
            Swal.fire({
                title: `Edit ${fileName}`,
                width: '800px',
                html: renderContent(content),
                footer: tableSelector === '#file-table' ? '<button id="toggle-mode" class="swal2-confirm swal2-styled" style="margin-top: 10px; background-color: #3085d6">Switch to ' + (editMode === 'text' ? 'Table' : 'Text') + ' Mode</button>' : '',
                focusConfirm: false,
                showCancelButton: true,
                confirmButtonText: 'Save Changes',
                cancelButtonText: 'Cancel',
                confirmButtonColor: '#50C878',
                cancelButtonColor: '#d33',
                didOpen: () => {
                    const toggleButton = document.getElementById('toggle-mode');
                    if (editMode === 'table') {
                        setupTableEvents();
                    }
                    
                    if (toggleButton && tableSelector === '#file-table') {
                        toggleButton.addEventListener('click', () => {
                            editMode = editMode === 'text' ? 'table' : 'text';
                            toggleButton.textContent = 'Switch to ' + (editMode === 'text' ? 'Table' : 'Text') + ' Mode';
                            Swal.getHtmlContainer().innerHTML = renderContent({content: originalContent});
                            if (editMode === 'table') {
                                // Need a small delay to allow DOM to update
                                setTimeout(setupTableEvents, 50);
                            }
                        });
                    }
                },
                preConfirm: () => {
                    const newFileName = document.getElementById('swal-input-filename').value;
                    let content;

                    if (editMode === 'text') {
                        content = document.getElementById('swal-input-content').value;
                    } else {
                        // --- Collect metadata lines ---
                        const metaTable = document.getElementById('swal-metadata-table');
                        let metaLines = [];
                        if (metaTable) {
                            const metaRows = Array.from(metaTable.querySelectorAll('tbody tr'));
                            metaLines = metaRows.map(row => {
                                const cells = row.querySelectorAll('td');
                                if (cells.length === 2) {
                                    const key = cells[0].textContent.trim();
                                    const value = cells[1].textContent.trim();
                                    return `# ${key}: ${value}`;
                                }
                                return null;
                            }).filter(Boolean);
                        }

                        // --- Collect main data table ---
                        const table = document.getElementById('swal-edit-table');
                        const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
                        const rows = Array.from(table.querySelectorAll('tbody tr'));

                        const csvRows = rows.map(row => {
                            return Array.from(row.querySelectorAll('td')).map(td => {
                                let cellContent = td.textContent.trim();
                                if (cellContent.includes(',') || cellContent.includes('\n') || cellContent.includes('"')) {
                                    return `"${cellContent.replace(/"/g, '""')}"`;
                                }
                                return cellContent;
                            }).join(',');
                        });

                        // --- Final content (metadata first, then CSV) ---
                        content = [...metaLines, headers.join(','), ...csvRows].join('\n');
                    }

                    // Validate content based on tableSelector
                    if (tableSelector === '#file-table') {
                        const patternSets = [
                            {
                                // Pattern 1: Requires metadata
                                header: /^\s*Timestamp\s*,\s*Value\s*,\s*Type\s*,\s*Blanked\s*$/,
                                data: /^\s*\d+\.\d{1,2}\s*,\s*\d+\.\d{1,3}\s*,\s*[A-Za-z]+\s*,\s*(TRUE|FALSE)\s*$/,
                                error: 'Invalid format (Pattern 1). Header must be: Timestamp,Value,Type,Blanked',
                                meta: [/^#\s*Measurement\s*:\s*.+$/, /^#\s*Unit\s*:\s*.+$/, /^#\s*Concentration\s*:\s*.+$/]
                            },
                            {
                                header: /^\s*Concentration\s*,\s*maxRate\s*,\s*Slope\s*,\s*Sat\s*,\s*Time To Sat\s*,\s*BlankType\s*$/,
                                data: /^\s*(NONE|\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d*)\s*,\s*(MIXED|BLANKED|NON-BLANKED)\s*$/,
                                error: 'Invalid format (Pattern 2). Header must be: Concentration,maxRate,Slope,Sat,Time To Sat,BlankType',
                                meta: [/^#\s*Measurement\s*:\s*.+$/, /^#\s*MeasUnit\s*:\s*.+$/, /^#\s*TimeUnit\s*:\s*.+$/, /^#\s*MeasMode\s*:\s*.+$/]
                            },
                            {
                                header: /^\s*Concentration\s*,\s*Value\s*,\s*TimePoint\s*,\s*BlankType\s*$/,
                                data: /^\s*(NONE|\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(MIXED|BLANKED|NON-BLANKED)\s*$/,
                                error: 'Invalid format (Pattern 3). Header must be: Concentration,Value,TimePoint,BlankType',
                                meta: [/^#\s*Measurement\s*:\s*.+$/, /^#\s*MeasUnit\s*:\s*.+$/, /^#\s*TimeUnit\s*:\s*.+$/, /^#\s*MeasMode\s*:\s*.+$/]
                            }
                        ];

                        const lines = content.trim().split('\n');
                        if (lines.length < 1) {
                            Swal.showValidationMessage('Content must contain at least the header');
                            return false;
                        }

                        // Extract metadata lines and data lines
                        const metaLines = lines.filter(line => line.trim().startsWith('#'));
                        const dataLines = lines.filter(line => !line.trim().startsWith('#'));

                        if (dataLines.length < 1) {
                            Swal.showValidationMessage('CSV must contain a header after metadata');
                            return false;
                        }

                        // Normalize the header line
                        const normalizedHeader = dataLines[0].replace(/\s*,\s*/g, ',');

                        // Find matching pattern
                        const matchedPattern = patternSets.find(pattern => {
                            return pattern.header.test(dataLines[0]) || pattern.header.test(normalizedHeader);
                        });

                        if (!matchedPattern) {
                            const validHeaders = patternSets.map(p => p.error.split('Header must be: ')[1]).join(' OR ');
                            Swal.showValidationMessage(`Invalid header. Must match one of: ${validHeaders}`);
                            return false;
                        }

                        // ✅ Metadata validation if defined
                        console.log("Metadata lines are: ", metaLines);
                        if (matchedPattern.meta && matchedPattern.meta.length > 0) {
                            for (let rule of matchedPattern.meta) {
                                const found = metaLines.some(line => rule.test(line));
                                if (!found) {
                                    Swal.showValidationMessage(`Missing required metadata: must include "${rule}"`);
                                    return false;
                                }
                            }
                        }

                        // ✅ Data validation
                        for (let i = 1; i < dataLines.length; i++) {
                            const normalizedLine = dataLines[i].replace(/\s*,\s*/g, ',');
                            if (!matchedPattern.data.test(dataLines[i]) && !matchedPattern.data.test(normalizedLine)) {
                                Swal.showValidationMessage(`Invalid data in row ${i + 1} for the detected format.`);
                                return false;
                            }
                        }
                    } else if (tableSelector === '#json-table' && editMode === 'text') {
                        try {
                            JSON.parse(content);
                        } catch (e) {
                            Swal.showValidationMessage(`Invalid JSON format: ${e.message}`);
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
                        path: filePath,
                        content: content,
                        calibrate_mode: AppState.currentMeasurementMode === 'calibrate' ? $("#cal-mode-select").val() : 'timestamp'
                    }, function(response) {
                        if (response.status === 'success') {
                            let textMsg;
                            if (fileName !== newFileName) {
                                row.find("td:first").text(newFileName);
                                row.find("button:contains('Select')").attr('onclick', `selectFile('${newFileName}', this, '${tableSelector}')`);
                                row.find("button:contains('Edit')").attr('onclick', `editFile('${newFileName}', this, '${tableSelector}')`);
                                row.find("button:contains('Delete')").attr('onclick', `deleteFile('${newFileName}', this, '${tableSelector}')`);
                                textMsg = `File ${fileName} renamed to ${newFileName} and content updated successfully.`;
                            } else {
                                textMsg = `File ${fileName} content updated successfully.`;
                            }
                            // Update AppState and Data display if the currently selected file is being edited
                            if ((tableSelector === "#file-table" && AppState.currentFile === fileName) || (tableSelector === "#json-table" && AppState.currentJSON === fileName)) {
                                console.log("Changing data display");
                                deselectFile(tableSelector);
                                selectFile(newFileName, button, tableSelector);
                                toggleMode();
                            }
                            if ($("#no-swal-checkbox").is(":checked")) {
                                console.log(textMsg);
                                if (tableSelector === "#file-table") {
                                    updateDirectory($("#directory").val());
                                } else if (tableSelector === "#json-table") {
                                    updateJSONTable();
                                }
                                return; // Exit if no popup is needed
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