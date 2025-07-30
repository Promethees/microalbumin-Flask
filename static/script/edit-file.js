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

        const nonEditableColumns = ['Measurement', 'Unit', 'Type', 'Blanked', 'Concentration', 
                              'TimeUnit', 'BlankType', 'MeasMode', 'MeasUnit'];

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
                const headers = lines[0].split(',');
                const data = lines.slice(1);
                
                html = `
                    <input type="text" id="swal-input-filename" class="swal2-input" value="${fileName}" placeholder="Enter new filename">
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
        const filePath = tableSelector === '#file-table' ? $("#directory").val() : AppState.jsonPath + delimiter + AppState.currentMeasurementMode;
        // Fetch CSV content
        $.get(`/get_file_content?file=${encodeURIComponent(fileName)}&path=${encodeURIComponent(filePath)}`, function(content) {
            Swal.fire({
                title: `Edit ${fileName}`,
                width: '800px',
                html: renderContent(content),
                footer: tableSelector === '#file-table' ? '<button id="toggle-mode" class="swal2-confirm swal2-styled" style="margin-top: 10px;">Switch to ' + (editMode === 'text' ? 'Table' : 'Text') + ' Mode</button>' : '',
                focusConfirm: false,
                showCancelButton: true,
                confirmButtonText: 'Save Changes',
                cancelButtonText: 'Cancel',
                confirmButtonColor: '#3085d6',
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
                        // Reconstruct CSV from table
                        const table = document.getElementById('swal-edit-table');
                        const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
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
                    if (!newFileName.trim()) {
                        Swal.showValidationMessage('New file name cannot be empty');
                        return false;
                    } else {
                        if (tableSelector === '#file-table' && !newFileName.endsWith('.csv')) {
                            Swal.showValidationMessage('File name must end with .csv');
                            return false;
                        }
                        if (tableSelector === '#json-table' && !newFileName.endsWith('.json')) {
                            Swal.showValidationMessage('File name must end with .json');
                            return false;
                        }
                    }

                    // Validate content based on tableSelector
                    if (tableSelector === '#file-table') {
                        // CSV validation (for both table and text mode)
                        const patternSets = [
                            {
                                header: /^\s*Timestamp\s*,\s*Measurement\s*,\s*Value\s*,\s*Unit\s*,\s*Type\s*,\s*Blanked\s*,\s*Concentration\s*$/,
                                data: /^\s*\d+\.\d{1,2}\s*,\s*[A-Za-z]+\s*,\s*\d+\.\d{1,3}\s*,\s*[A-Za-z]+\s*,\s*[A-Za-z]+\s*,\s*[A-Za-z]+\s*,\s*(NONE|\d+)\s*$/,
                                error: 'Invalid format (Pattern 1). Header must be: Timestamp,Measurement,Value,Unit,Type,Blanked,Concentration'
                            },
                            {
                                header: /^\s*Measurement\s*,\s*Concentration\s*,\s*maxRate\s*,\s*Slope\s*,\s*Sat\s*,\s*Time To Sat\s*,\s*MeasUnit\s*,\s*TimeUnit\s*,\s*BlankType\s*,\s*MeasMode\s*$/,
                                data: /^\s*[A-Za-z]+\s*,\s*(NONE|\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d*)\s*,\s*[A-Za-z]+\s*,\s*[A-Za-z]+\s*,\s*[A-Za-z]+\s*,\s*[A-Za-z]+\s*$/,
                                error: 'Invalid format (Pattern 2). Header must be: Measurement,Concentration,maxRate,Slope,Sat,Time To Sat,MeasUnit,TimeUnit,BlankType,MeasMode'
                            },
                            {
                                header: /^\s*Measurement\s*,\s*Concentration\s*,\s*Value\s*,\s*MeasUnit\s*,\s*TimePoint\s*,\s*TimeUnit\s*,\s*BlankType\s*,\s*MeasMode\s*$/,
                                data: /^\s*[A-Za-z]+\s*,\s*(NONE|\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*[A-Za-z]+\s*,\s*(NONE|\d+|\d+\.\d*)\s*,\s*[A-Za-z]+\s*,\s*[A-Za-z]+\s*,\s*[A-Za-z]+\s*$/,
                                error: 'Invalid format (Pattern 3). Header must be: Measurement,Concentration,Value,MeasUnit,TimePoint,TimeUnit,BlankType,MeasMode'
                            }
                        ];

                        const lines = content.trim().split('\n');
                        if (lines.length < 1) {
                            Swal.showValidationMessage('Content must contain at least the header');
                            return false;
                        }

                        // Normalize the header line by removing extra spaces
                        const normalizedHeader = lines[0].replace(/\s*,\s*/g, ',');

                        // Find matching pattern set
                        const matchedPattern = patternSets.find(pattern => {
                            // Test against both the original and normalized header
                            return pattern.header.test(lines[0]) || pattern.header.test(normalizedHeader);
                        });
                        
                        if (!matchedPattern) {
                            const validHeaders = patternSets.map(p => p.error.split('Header must be: ')[1]).join(' OR ');
                            Swal.showValidationMessage(`Invalid header. Must match one of: ${validHeaders}`);
                            return false;
                        }

                        // Validate data rows with the matched pattern
                        for (let i = 1; i < lines.length; i++) {
                            const normalizedLine = lines[i].replace(/\s*,\s*/g, ',');
                            if (!matchedPattern.data.test(lines[i]) && !matchedPattern.data.test(normalizedLine)) {
                                Swal.showValidationMessage(`Invalid data in row ${i + 1} for the detected format.`);
                                return false;
                            }
                        }
                    } else if (tableSelector === '#json-table' && editMode === 'text') {
                        // JSON validation for text mode
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
    // Refresh data display section after editing
    toggleMode();
}