function editFile(fileName, button, tableSelector = "#file-table") {
    /* --------------------------------------------------------------
   JSON → Graphic UI helpers
   -------------------------------------------------------------- */
    function buildGraphicUI(jsonObj, pathPrefix = 'root') {
        const isArray = Array.isArray(jsonObj);
        let html = '';

        if (isArray) {
            jsonObj.forEach((item, idx) => {
                const itemPath = `${pathPrefix}[${idx}]`;
                html += `
                    <fieldset class="json-array-item" style="margin-bottom:12px; border:1px solid #ddd; border-radius:6px;">
                        <div class="json-section">${buildGraphicUI(item, itemPath)}</div>
                        <button type="button" class="json-delete-item btn-small" data-path="${itemPath}"
                                style="margin:4px 0 0 4px; background:#c33; color:#fff; border:none; padding:2px 6px; border-radius:3px;">
                            Delete
                        </button>
                    </fieldset>`;
            });
            // Add-item button for arrays
            html += `
                <button type="button" class="json-add-array-item btn-small" data-path="${pathPrefix}"
                        style="margin-top:8px; background:#28a745; color:#fff; border:none; padding:4px 8px; border-radius:3px;">
                    + Add Item
                </button>`;
        } else if (jsonObj !== null && typeof jsonObj === 'object') {
            // Object → field list
            const entries = Object.entries(jsonObj);
            if (entries.length === 0) {
                html += '<p style="color:#888; font-style:italic; margin:8px 0;">(empty object)</p>';
            }
            entries.forEach(([key, val]) => {
                const fullPath = `${pathPrefix}.${key}`;
                const label = key;
                const isObj = val !== null && typeof val === 'object';

                html += `
                    <div class="json-field" style="margin-bottom:12px; display:flex; align-items:flex-start; gap:8px;">
                        <label style="min-width:140px; font-weight:600; margin-top:6px;">${label}</label>
                        <div style="flex:1;">`;

                if (isObj) {
                    // Nested collapsible section
                    html += `
                        <fieldset style="border:1px solid #ddd; border-radius:4px; padding:8px; margin:0;">
                            <legend style="cursor:pointer; padding:0 4px; font-size:0.9em; user-select:none;"
                                    onclick="toggleCollapse(this)">
                                Collapse [−] 
                            </legend>
                            <div class="json-section">${buildGraphicUI(val, fullPath)}</div>
                        </fieldset>`;
                } else {
                    // Primitive
                    const inputType = typeof val === 'number' ? 'number' :
                        typeof val === 'boolean' ? 'checkbox' : 'text';
                    const valueAttr = typeof val === 'boolean' ? (val ? 'checked' : '') :
                        `value="${escapeHtml(String(val))}"`;

                    if (inputType === 'checkbox') {
                        html += `
                            <label style="display:flex; align-items:center; gap:4px; cursor:pointer;">
                                <input type="checkbox" class="json-input" data-path="${fullPath}" ${valueAttr}>
                                <span>${val ? 'true' : 'false'}</span>
                            </label>`;
                    } else if (inputType === 'number') {
                        html += `
                            <input type="${inputType}" class="json-input" data-path="${fullPath}" ${valueAttr}>`;
                    } else {
                        // Text / fallback – use textarea for multi-line
                        const isMultiline = String(val).includes('\n');
                        if (isMultiline) {
                            html += `
                                <textarea class="json-input" data-path="${fullPath}">${escapeHtml(String(val))}</textarea>`;
                        } else {
                            html += generateInputHtml(key, val, fullPath, valueAttr);
                        }
                    }
                }
                html += `</div></div>`;
            });
        } else {
            // Primitive root (rare)
            html += `<p><em></em> ${escapeHtml(String(jsonObj))}</p>`;
        }
        return html;
    }

    function generateInputHtml(key, value, fullPath, valueAttr) {
        // -----------------------------------------------------------------
        // 1. Helper to extract the raw value from valueAttr (e.g. "linear")
        // -----------------------------------------------------------------
        const getValueFromAttr = () => {
            const m = valueAttr.match(/value=["']([^"']+)["']/);
            return m ? m[1] : null;
        };

        // -----------------------------------------------------------------
        // 2. Multi-select definitions
        // -----------------------------------------------------------------
        const configs = {
            fit_type: {
                options: ["linear", "polynomial", "logarithmic", "exponential", "Michaelis-Menten"]
            }
        };

        // -----------------------------------------------------------------
        // 3. Is this a special multi-select key?
        // -----------------------------------------------------------------
        if (configs[key]) {
            const cfg = configs[key];
            const rawAttrVal = getValueFromAttr();                // e.g. "linear"
            const currentArray = Array.isArray(value) ? value : (value ? [value] : []);

            // Ensure the value from valueAttr is part of the selection set
            if (rawAttrVal && !currentArray.includes(rawAttrVal)) {
                currentArray.push(rawAttrVal);
            }

            // Build the option list – include any "foreign" value as an extra option
            const allOptions = [...new Set([...cfg.options, ...currentArray])];

            let html = `<select class="json-input" data-path="${fullPath}">`;
            for (const opt of allOptions) {
                const selected = currentArray.includes(opt) ? "selected" : "";
                html += `<option value="${opt}" ${selected}>${opt}</option>`;
            }
            html += `</select>`;
            return html;
        }

        // -----------------------------------------------------------------
        // 4. Fallback – original text input
        // -----------------------------------------------------------------
        return `
            <input type="text" class="json-input" data-path="${fullPath}" ${valueAttr}>`;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function collectTableContent() {
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

        const table = document.getElementById('swal-edit-table');
        const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
        const rows = Array.from(table.querySelectorAll('tbody tr'));
        const dataLines = rows.map(row => {
            const cells = Array.from(row.querySelectorAll('td'));
            return cells.map(cell => cell.textContent.trim()).join(',');
        });

        return metaLines.join('\n') + (metaLines.length ? '\n' : '') + headers.join(',') + '\n' + dataLines.join('\n');
    }


    checkScriptStatus().then((isRunning) => {
        if (isRunning || AppState.scriptRunning) {
            Swal.fire({
                title: 'Error!',
                text: 'Cannot edit files while the data collection process is running. Stop the process and try again.',
                icon: 'error',
                confirmButtonText: 'OK'
            }).then(() => {
                const terminateBtn = document.getElementById('#terminate-script-btn');
                if (terminateBtn) {
                    terminateBtn.focus();
                    terminateBtn.classList.add('blinking');
                    setTimeout(() => {
                        terminateBtn.classList.remove('blinking');
                    }, 5000);
                }
            });
            return;
        }

        const row = $(button).closest("tr");
        const deleteBtn = row.find("button:contains('Delete')");
        deleteBtn.prop('disabled', true).addClass('disabled').attr('aria-disabled', 'true');

        let editMode = tableSelector === '#file-table' ? 'table' : 'graphic'; // Default mode depend on selected table

        const nonEditableColumns = ['Unit', 'Type', 'Concentration'];
        const nonEditableMetadata = ['TimeUnit', 'MeasMode'];

        function setupTableEvents() {
            const table = document.getElementById('swal-edit-table');
            if (!table) return;

            const addRowBtn = document.getElementById('add-row-btn');
            const deleteRowBtn = document.getElementById('delete-row-btn');
            const removeColsBtn = document.getElementById('remove-cols-btn');
            let selectedRow = null;

            // Row selection
            table.addEventListener('click', function (e) {
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
                addRowBtn.addEventListener('click', function () {
                    const tbody = document.getElementById('swal-edit-body');
                    if (!tbody) return;

                    const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
                    const newRow = document.createElement('tr');
                    newRow.dataset.rowIndex = tbody.children.length;

                    // Get reference values from first existing row (if available)
                    const referenceValues = {};
                    const defaultValues = {
                        'Timestamp': '0.00', 'Measurement': 'ABSORBANCE', 'Unit': 'NONE',
                        'Type': 'NONE', 'Concentration': 'NONE',
                        'Value': '0.00', 'maxRate': '0.00', 'Slope': '0.00',
                        'Sat': '0.00', 'Time To Sat': '0.00', 'MeasUnit': 'NONE',
                        'TimeUnit': 'minutes', 'MeasMode': 'kinetics',
                        'TimePoint': '0'
                    };
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
                deleteRowBtn.addEventListener('click', function () {
                    if (selectedRow) {
                        selectedRow.remove();
                        selectedRow = null;
                        deleteRowBtn.disabled = true;
                    }
                });
            }

            // Remove columns
        }

        function renderContent(content) {
            let html = '';
            if (tableSelector === '#json-table' && editMode === 'graphic') {
                let parsed;
                try { parsed = JSON.parse(content.content); } catch (e) {
                    return `<p style="color:red;">Invalid JSON: ${e.message}</p>`;
                }

                return `
                    <input type="text" id="swal-input-filename" class="swal2-input"
                        value="${fileName}" placeholder="Enter new filename">
                    <div class="json-graphic-container" style="margin-top:12px; max-height:500px; overflow-y:auto;">
                        ${buildGraphicUI(parsed)}
                    </div>`;
            }
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
                        <div>
                            <button id="add-row-btn" class="swal2-confirm swal2-styled" style="padding: 5px 10px;">
                                Add Row (+)
                            </button>
                            <button id="delete-row-btn" class="swal2-deny swal2-styled" style="padding: 5px 10px;" disabled>
                                Delete Selected Row (-)
                            </button>
                        </div>
                    </div>
                    <div style="max-height: 400px; overflow-y: auto; margin-top: 10px;">
                        <table id="swal-edit-table" style="width: 100%; border-collapse: collapse; font-family: Arial, sans-serif;">
                            <thead>
                                <tr style="position: sticky; top: 0; background: white; z-index: 10;">
                                    ${headers.map(col => {
                    const isValueCol = col.startsWith('Value:');
                    return `<th style="border: 1px solid #ddd; padding: 6px; text-align: left; 
                                            font-size: 0.85em; font-weight: bold; white-space: nowrap;">
                                            ${col}
                                            ${isValueCol ? `
                                                <span class="move-col-btn" onclick="moveColumn('${col}', -1)" style="cursor: pointer; margin-left: 5px;">(&lt;)</span>
                                                <span class="move-col-btn" onclick="moveColumn('${col}', 1)" style="cursor: pointer; margin-left: 5px;">(&gt;)</span>
                                                <span class="remove-col-btn" onclick="removeColumn('${col}')" style="color: red; cursor: pointer; font-weight: bold; margin-left: 5px;">(-)</span>
                                            ` : ''}
                                        </th>`;
                }).join('')}
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
        const filePath = tableSelector === '#file-table' ? document.getElementById("directory").value : AppState.jsonPath + DELIMITER + AppState.currentMeasurementMode;
        console.log("File Path is ", filePath);
        // Fetch CSV content
        $.get(`/get_file_content?file=${encodeURIComponent(fileName)}&path=${encodeURIComponent(filePath)}`, function (content) {
            let originalContent = content.content; // ← raw string
            let finalContent = null; // ← final string to save
            let workingJSON = null; // ← **one-time parse**

            const rebuildContent = () => {
                if (workingJSON !== null)
                    finalContent = JSON.stringify(workingJSON, null, 2);
            };

            function setValueByPath(path, value) {
                if (workingJSON === null) {
                    console.error("setValueByPath called on a non-JSON file");
                    return;
                }
                const parts = path
                    .replace(/\[(\d+)\]/g, ".$1")
                    .split(".")
                    .filter(Boolean)
                    .slice(1);               // remove leading "root"
                const last = parts.pop();
                let cur = workingJSON;

                for (const part of parts) {
                    // auto-create missing objects / arrays
                    cur[part] = cur[part] ?? (isNaN(part) ? {} : []);
                    cur = cur[part];
                }
                cur[last] = value;
                rebuildContent();          // keep the displayed string in sync
            }

            function getValueByPath(path) {
                if (workingJSON === null) return undefined;
                let cur = workingJSON;
                const parts = path
                    .replace(/\[(\d+)\]/g, ".$1")
                    .split(".")
                    .filter(Boolean);
                for (const part of parts) {
                    if (cur === undefined || cur === null) return undefined;
                    cur = cur[part];
                }
                return cur;
            }

            function bindDynamicButtons() {
                // ---- Add field (object) ----
                document.querySelectorAll('.json-add-field').forEach(btn => {
                    btn.onclick = () => {
                        const path = btn.dataset.path;
                        const keyInp = btn.parentElement.querySelector('.json-new-key');
                        const valInp = btn.parentElement.querySelector('.json-new-value');
                        const key = keyInp.value.trim();
                        const raw = valInp.value.trim();
                        if (!key) return Swal.showValidationMessage('Key is required');
                        let val;
                        try { val = raw === '' ? null : JSON.parse(raw); }
                        catch { val = raw; }
                        setValueByPath(path + '.' + key, val);
                        keyInp.value = ''; valInp.value = '';
                        refreshGraphicUI();
                    };
                });

                // ---- Add array item ----
                document.querySelectorAll('.json-add-array-item').forEach(btn => {
                    btn.onclick = () => {
                        const path = btn.dataset.path;
                        const arr = getValueByPath(path) || [];
                        arr.push(null); // placeholder
                        setValueByPath(path, arr);
                        refreshGraphicUI();
                    };
                });

                // ---- Delete array item ----
                document.querySelectorAll('.json-delete-item').forEach(btn => {
                    btn.onclick = () => {
                        const path = btn.dataset.path;
                        const parts = path.replace(/\[(\d+)\]/g, '.$1').split('.').filter(Boolean);
                        const idx = parseInt(parts.pop());
                        const parentPath = parts.join('.');
                        const arr = getValueByPath(parentPath);
                        if (Array.isArray(arr)) {
                            arr.splice(idx, 1);
                            setValueByPath(parentPath, arr);
                            refreshGraphicUI();
                        }
                    };
                });
            }

            function refreshGraphicUI() {
                const container = document.querySelector('.json-graphic-container');
                if (!container) return;
                let parsed;
                try { parsed = JSON.parse(originalContent); } catch (_) { return; }
                container.innerHTML = buildGraphicUI(parsed);
                bindDynamicButtons();
                syncFitCoefLabels(document.querySelector('.swal2-popup'));
            }
            /* --------------------------------------------------------------
            SINGLE FIT_TYPE → MULTIPLE FIT_COEF blocks (grouped)
            Remembers original fit_type + coefficient values
            -------------------------------------------------------------- */
            function syncFitCoefLabels(container) {
                const fitTypeSelect = container.querySelector('select[data-path$=".fit_type"]');
                if (!fitTypeSelect) return;

                const allCoefInputs = Array.from(
                    container.querySelectorAll('.json-input[data-path*="fit_coef"]')
                );
                if (allCoefInputs.length === 0) return;

                // -----------------------------------------------------------------
                // 1. Group inputs + fields by fit_coef base path
                // -----------------------------------------------------------------
                const groups = new Map();  // base → {fields: [], inputs: []}
                allCoefInputs.forEach(inp => {
                    const oldPath = inp.dataset.path;
                    const base = oldPath.replace(/\.[^.]+$/, '');
                    if (!groups.has(base)) groups.set(base, { fields: [], inputs: [] });
                    const group = groups.get(base);
                    const field = inp.closest('.json-field');
                    if (field && !group.fields.includes(field)) group.fields.push(field);
                    group.inputs.push(inp);
                });

                // -----------------------------------------------------------------
                // 2. Mapping: fit_type → [label1, label2, (label3)]
                // -----------------------------------------------------------------
                const labelMap = {
                    linear: ['a', 'b'],
                    'Michaelis-Menten': ['VMax', 'Km'],
                    default: ['a', 'b', 'c']
                };

                // -----------------------------------------------------------------
                // 3. FIRST-TIME: Remember original state
                // -----------------------------------------------------------------
                if (!fitTypeSelect.dataset.originalType) {
                    fitTypeSelect.dataset.originalType = fitTypeSelect.value;

                    // Store original coefficient values: path → original value
                    window._originalCoefValues = window._originalCoefValues || new Map();
                    allCoefInputs.forEach(inp => {
                        const path = inp.dataset.path;
                        const value = inp.tagName === 'TEXTAREA' ? inp.value :
                            inp.type === 'checkbox' ? inp.checked :
                                inp.value;
                        window._originalCoefValues.set(path, value);
                    });
                }

                // -----------------------------------------------------------------
                // 4. Helper: restore original values for a given fit_type
                // -----------------------------------------------------------------
                function restoreOriginalForType(type) {
                    const labels = labelMap[type] || labelMap.default;
                    for (const [base, group] of groups) {
                        labels.forEach((label, j) => {
                            const key = label;
                            const originalPath = `${base}.${key}`;
                            const input = group.inputs[j];
                            if (!input) return;

                            const originalValue = window._originalCoefValues.get(originalPath);
                            if (originalValue !== undefined) {
                                if (input.type === 'checkbox') {
                                    input.checked = originalValue;
                                } else if (input.tagName === 'TEXTAREA') {
                                    input.value = originalValue;
                                } else {
                                    input.value = originalValue;
                                    input.type = typeof originalValue === 'number' ? 'number' : 'text';
                                }
                                // Also restore in live JSON
                                setValueByPath(input.dataset.path, originalValue);
                            }
                        });
                    }
                }

                // -----------------------------------------------------------------
                // 5. Core update routine
                // -----------------------------------------------------------------
                function updateAllBlocks(tupleChanged = false, isRestore = false) {
                    const selected = fitTypeSelect.value.trim();
                    const labels = labelMap[selected] || labelMap.default;
                    const originalType = fitTypeSelect.dataset.originalType;

                    for (const [base, group] of groups) {
                        // ---- Grow group if needed (e.g. 2 → 3) ----
                        while (group.inputs.length < labels.length) {
                            const lastIndex = group.fields.length - 1;
                            const clonedField = group.fields[lastIndex].cloneNode(true);
                            const clonedInput = clonedField.querySelector('.json-input');

                            // New field: blank or 'NONE' if tuple changed
                            clonedInput.value = tupleChanged ? 'NONE' : '';
                            clonedInput.type = 'text';

                            const parentSection = group.fields[0].parentNode;
                            parentSection.appendChild(clonedField);

                            group.fields.push(clonedField);
                            group.inputs.push(clonedInput);
                        }

                        // ---- Update visible fields ----
                        labels.forEach((label, j) => {
                            const field = group.fields[j];
                            const input = group.inputs[j];
                            const newKey = label;
                            const newPath = `${base}.${newKey}`;

                            field.style.display = 'flex';
                            const labelEl = field.querySelector('label');
                            if (labelEl) labelEl.textContent = label;

                            input.dataset.path = newPath;

                            // Restore original value if switching back AND not reset
                            if (isRestore && selected === originalType) {
                                const originalValue = window._originalCoefValues.get(newPath);
                                if (originalValue !== undefined) {
                                    if (input.type === 'checkbox') input.checked = originalValue;
                                    else if (input.tagName === 'TEXTAREA') input.value = originalValue;
                                    else {
                                        input.value = originalValue;
                                        input.type = typeof originalValue === 'number' ? 'number' : 'text';
                                    }
                                    setValueByPath(newPath, originalValue);
                                    return;
                                }
                            }

                            // Reset if tuple changed
                            if (tupleChanged && !isRestore) {
                                input.type = 'text';
                                input.value = 'NONE';
                                setValueByPath(newPath, 'NONE');
                            }
                        });

                        // ---- Hide extras ----
                        for (let j = labels.length; j < group.fields.length; j++) {
                            group.fields[j].style.display = 'none';
                            if (tupleChanged && !isRestore) {
                                const input = group.inputs[j];
                                input.type = 'text';
                                input.value = 'NONE';
                                setValueByPath(input.dataset.path, 'NONE');
                            }
                        }
                    }
                }

                // -----------------------------------------------------------------
                // 6. Initial render
                // -----------------------------------------------------------------
                fitTypeSelect.dataset.prev = fitTypeSelect.value;
                updateAllBlocks(false, false);

                // -----------------------------------------------------------------
                // 7. Change handler
                // -----------------------------------------------------------------
                fitTypeSelect.addEventListener('change', () => {
                    const oldTuple = labelMap[fitTypeSelect.dataset.prev || 'linear'] || labelMap.default;
                    const newTuple = labelMap[fitTypeSelect.value] || labelMap.default;
                    const tupleChanged = oldTuple.length !== newTuple.length ||
                        oldTuple.some((v, i) => v !== newTuple[i]);

                    const originalType = fitTypeSelect.dataset.originalType;
                    const isRestore = fitTypeSelect.value === originalType && fitTypeSelect.dataset.prev !== originalType;

                    fitTypeSelect.dataset.prev = fitTypeSelect.value;

                    if (isRestore) {
                        // Switching back to original type → restore values
                        restoreOriginalForType(fitTypeSelect.value);
                        updateAllBlocks(false, true);  // just relabel/hide/show
                    } else {
                        updateAllBlocks(tupleChanged, false);
                    }
                });
            }

            // On time workingJSON parser, only for json-table
            if (tableSelector === "#json-table") {
                try {
                    workingJSON = JSON.parse(originalContent);
                } catch (e) {
                    Swal.fire({
                        title: "Invalid JSON",
                        text: `The file contains malformed JSON: ${e.message}`,
                        icon: "error",
                    });
                    return;
                }
            }

            // --- End functions ---

            function showModal(contentToShow, nameToShow) {
                Swal.fire({
                    title: `Edit ${nameToShow}`,
                    width: '800px',
                    html: renderContent({ content: contentToShow }),
                    footer: '<button id="toggle-mode" class="swal2-confirm swal2-styled" style="margin-top: 10px; background-color: #3085d6">Switch to ' + (editMode === 'text' ? (tableSelector === '#file-table' ? 'Table' : 'Graphic') : 'Text') + ' Mode</button>',
                    focusConfirm: false,
                    showCancelButton: true,
                    confirmButtonText: 'Save Changes',
                    cancelButtonText: 'Cancel',
                    confirmButtonColor: '#50C878',
                    cancelButtonColor: '#d33',
                    didOpen: () => {
                        // Restore filename
                        const nameInput = document.getElementById('swal-input-filename');
                        if (nameInput) nameInput.value = nameToShow;

                        // -----------------------------------------------------------------
                        //  CSS for the graphic UI
                        // -----------------------------------------------------------------
                        if (!document.getElementById('json-graphic-styles')) {
                            const style = document.createElement('style');
                            style.id = 'json-graphic-styles';
                            style.textContent = `
                                .json-graphic-container fieldset.collapsed > .json-section { display:none; }
                                .json-graphic-container .json-input { font-size:0.9rem; }
                                .json-graphic-container .btn-small { font-size:0.8rem; cursor:pointer; }
                                .light .json-graphic-container .json-field:hover { background:#f8f9fa; }
                                .dark .json-graphic-container .json-field:hover { background:#343a40; }
                            `;
                            document.head.appendChild(style);
                        }
                        const toggleButton = document.getElementById('toggle-mode');
                        if (editMode === 'table') {
                            setupTableEvents();
                        } else if (editMode === 'graphic') {
                            syncFitCoefLabels(Swal.getPopup());
                        }

                        if (toggleButton) {
                            toggleButton.addEventListener('click', () => {
                                editMode = editMode === 'text' ? (tableSelector === '#file-table' ? 'table' : 'graphic') : 'text';
                                toggleButton.textContent = 'Switch to ' + (editMode === 'text' ? (tableSelector === "#file-table" ? 'Table' : 'Graphic') : 'Text') + ' Mode';
                                Swal.getHtmlContainer().innerHTML = renderContent({ content: originalContent });
                                if (editMode === 'table') {
                                    // Need a small delay to allow DOM to update
                                    setTimeout(setupTableEvents, 50);
                                } else if (editMode === 'graphic') {
                                    syncFitCoefLabels(Swal.getPopup());
                                }
                            });
                        }
                    },
                    preConfirm: () => {
                        const newFileName = document.getElementById('swal-input-filename').value;
                        let content;

                        if (editMode === 'text') {
                            content = document.getElementById('swal-input-content').value;
                        } else if (editMode === 'table') {
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
                            const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.replace(/\s*(?:\n\s*\([^)]+\)){1,3}\s*$/, '').trim());
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
                                    // File pattern with metadata and headers
                                    header: /^\s*Concentration\s*,\s*maxRate\s*,\s*Slope\s*,\s*Sat\s*,\s*Time To Sat\s*$/,
                                    data: /^\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d*)\s*$/,
                                    error: 'Invalid format (Pattern 1). Header must be: Concentration,maxRate,Slope,Sat,Time To Sat',
                                    meta: [/^#\s*Measurement\s*:\s*.+$/, /^#\s*MeasUnit\s*:\s*.+$/, /^#\s*TimeUnit\s*:\s*.+$/, /^#\s*MeasMode\s*:\s*.+$/]
                                },
                                {
                                    header: /^\s*Concentration\s*,\s*Value\s*,\s*TimePoint\s*$/,
                                    data: /^\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*$/,
                                    error: 'Invalid format (Pattern 2). Header must be: Concentration,Value,TimePoint',
                                    meta: [/^#\s*Measurement\s*:\s*.+$/, /^#\s*MeasUnit\s*:\s*.+$/, /^#\s*TimeUnit\s*:\s*.+$/, /^#\s*MeasMode\s*:\s*.+$/]
                                },
                                {
                                    header: /^\s*Timestamp\s*,\s*Value:\d+(?:\s*,\s*Value:\d+)*\s*$/,
                                    data: /^\s*\d+(?:\.\d{1,2})?\s*(?:(?:,\s*)?(?:-?\d+(?:\.\d{1,3})?|OVFL|NONE)?\s*)*$/,
                                    error: 'Invalid format (Pattern 3). Header must be: Timestamp,Value:1,Value:2,...',
                                    meta: [
                                        /^#\s*Measurement\s*:\s*.+$/,
                                        /^#\s*Unit\s*:\s*.+$/,
                                        /^#\s*Concentration\s*:\s*.+$/
                                    ]
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
                        } else if (tableSelector === '#json-table') {
                            if (editMode === 'text') {
                                try {
                                    JSON.parse(content);
                                } catch (e) {
                                    return false;
                                }
                                content = (editMode === "graphic" && finalContent) ? finalContent : originalContent;  // final string
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
                            calibrate_mode: AppState.currentMeasurementMode === 'calibrate' ? calDiv.getAttribute('data-value') : 'timestamp'
                        }, function (response) {
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
                                if (getBtnChecked("no-swal-checkbox")) {
                                    console.log(textMsg);
                                    if (tableSelector === "#file-table") {
                                        updateDirectory(document.getElementById("directory").value);
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
                        }).fail(function (jqXHR) {
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
            }

            showModal(originalContent, fileName);
        }).fail(function (jqXHR) {
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

function toggleCollapse(legend) {
    const fieldset = legend.parentElement;
    const isCollapsed = fieldset.classList.toggle('collapsed');

    // Update label and icon based on state
    const labelText = isCollapsed ? 'Expand [+]' : 'Collapse [−]';

    legend.firstChild.nodeValue = labelText + ' ';
}

function moveColumn(headerName, direction) {
    const table = document.getElementById('swal-edit-table');
    if (!table) return;

    // Clean header name to find index
    const cleanHeader = (text) => text.replace(/\s*\(\-\)\s*$/, '').replace(/\(\<\)\s*\(\>\)\s*$/, '').trim().split(' ')[0];

    const headers = Array.from(table.querySelectorAll('th'));
    const colIndex = headers.findIndex(th => cleanHeader(th.textContent) === headerName);

    if (colIndex === -1) {
        console.error(`Column '${headerName}' not found.`);
        return;
    }

    const targetIndex = colIndex + direction;

    // Boundary Validation
    if (targetIndex < 0 || targetIndex >= headers.length) {
        return; // Can't move outside bounds
    }

    const targetHeaderName = cleanHeader(headers[targetIndex].textContent);

    // Prevent swapping with Timestamp or non-Value columns if strictly enforced
    // The requirement says "not swapping with Timestamp". Usually Timestamp is first.
    // Also likely want to restrict to swapping only between 'Value:' columns.
    if (!targetHeaderName.startsWith('Value:')) {
        Swal.showValidationMessage('Can only swap with other Value columns.');
        return;
    }

    // Perform DOM Swap
    // 1. Swap Headers
    const headerRow = table.querySelector('thead tr');
    // Using insertBefore. If direction is 1 (right), insert current after target.
    // Use standard node swapping logic
    if (direction === 1) {
        headerRow.insertBefore(headers[targetIndex], headers[colIndex]);
        // Wait, if I move A to right of B (A, B -> B, A)
        // insertBefore(node, reference). 
        // If A is at 1, B is at 2. Move A to 2. 
        // insertBefore(A, B.nextSibling)
        headerRow.insertBefore(headers[colIndex], headers[targetIndex].nextSibling);
    } else {
        // Move A left (B, A -> A, B)
        // insertBefore(A, B)
        headerRow.insertBefore(headers[colIndex], headers[targetIndex]);
    }

    // 2. Swap All Data Cells
    const rows = table.querySelectorAll('tbody tr');
    rows.forEach(row => {
        const cells = row.children;
        if (direction === 1) {
            row.insertBefore(cells[colIndex], cells[targetIndex].nextSibling);
        } else {
            row.insertBefore(cells[colIndex], cells[targetIndex]);
        }
    });

    // Renumber Columns
    renumberValueColumns(table);
}

function removeColumn(headerName) {
    const table = document.getElementById('swal-edit-table');
    if (!table) return;

    // Use regex to strip the buttons and trim
    // Note: The move buttons adds text content to the header? 
    // Usually buttons are elements so th.textContent includes them.
    // We should be careful matching headerName. 
    // The passed headerName usually comes from the original render or current state.

    const headers = Array.from(table.querySelectorAll('th'));
    // Find column index
    const colIndex = headers.findIndex(th => {
        // We need to match the 'Value:X' part. 
        // The header content might be "Value:1 (<) (>) (-)"
        return th.textContent.includes(headerName);
    });

    // Check if enough Value columns remain
    const valueCols = headers.filter(th => th.textContent.trim().startsWith('Value:'));
    if (valueCols.length <= 1) {
        Swal.showValidationMessage('At least one Value column must remain.');
        return;
    }

    if (colIndex === -1) {
        console.error(`Column '${headerName}' not found in headers.`);
        return;
    }

    // Remove header
    headers[colIndex].remove();

    // Remove cells
    table.querySelectorAll('tbody tr').forEach(row => {
        if (row.children[colIndex]) {
            row.children[colIndex].remove();
        }
    });

    // Renumber remaining Value: columns
    renumberValueColumns(table);
}

function renumberValueColumns(table) {
    const headers = Array.from(table.querySelectorAll('th'));
    let valueCount = 1;

    headers.forEach((th, index) => {
        // Check if it was a Value column (by checking text content or previous setup)
        // Since we might have messed up text content with buttons, best is to check if it starts with Value
        // Or cleaner: We know Timestamp is usually first. 
        // Let's assume all columns after Timestamp that are not Type/Unit etc are Value columns
        // Or just check if the text starts with Value:

        let text = th.textContent.trim();
        if (text.startsWith('Value:')) {
            const newName = `Value:${valueCount}`;
            th.innerHTML = `
                ${newName}
                <span class="move-col-btn" onclick="moveColumn('${newName}', -1)" style="cursor: pointer; margin-left: 5px;">(&lt;)</span>
                <span class="move-col-btn" onclick="moveColumn('${newName}', 1)" style="cursor: pointer; margin-left: 5px;">(&gt;)</span>
                <span class="remove-col-btn" onclick="removeColumn('${newName}')" style="color: red; cursor: pointer; font-weight: bold; margin-left: 5px;">(-)</span>
            `;

            // Update data-col attribute for all cells in this column
            const colIdx = Array.from(th.parentNode.children).indexOf(th);
            table.querySelectorAll(`tbody tr`).forEach(row => {
                const td = row.children[colIdx];
                if (td) td.dataset.col = newName;
            });

            valueCount++;
        }
    });
}