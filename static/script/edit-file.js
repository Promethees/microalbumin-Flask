function editFile(fileName, button, tableSelector = "#file-table") {
    // Metadata fields whose value may legitimately be "None": the measurement
    // unit (`Unit` timeseries / `MeasUnit` calibration) and the `Concentration`
    // value. Each renders a "None" checkbox that, when ticked, stores the "NONE"
    // sentinel and locks the text input. `ConcenUnit` is NOT here — a
    // concentration always has a unit, so it stays a constrained dropdown.
    const NONEABLE_META = ['Unit', 'MeasUnit', 'Concentration'];
    // Mirrors src/file.py::_norm_identity_value — blank or "NONE" (any case) is
    // the None sentinel; anything else is a real value.
    const isNoneMetaValue = (v) => {
        if (v === null || v === undefined) return true;
        const s = String(v).trim();
        return s === '' || s.toUpperCase() === 'NONE';
    };
    const nonePlaceholder = (key) => key === 'Concentration' ? 'e.g. 25' : 'e.g. AU';
    const noneLabel = (typeof t === 'function') ? t('metadata.none', 'None') : 'None';
    // Width (in chars) of a None-able text input — fits its content, min 6 so an
    // empty/placeholder field stays legible. Paired with the inline `oninput`
    // handler so the field grows/shrinks as the user types.
    const unitInputSize = (v) => Math.max(6, String(v == null ? '' : v).length + 1);
    const UNIT_INPUT_AUTOSIZE = 'this.size=Math.max(6,this.value.length+1)';

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
            },
            // ConcenUnit is constrained to the valid units (single source of truth:
            // the CONCEN_UNITS JS const injected from src/file_path.py). A legacy
            // value outside the list is preserved as an extra option (foreign-value
            // handling below), mirroring the CSV-metadata ConcenUnit dropdown.
            concen_unit: {
                options: (typeof CONCEN_UNITS !== 'undefined' && CONCEN_UNITS && CONCEN_UNITS.length)
                    ? CONCEN_UNITS : ['ng/µL', 'nM', '%', 'CFU', 'OD600']
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
        // 3b. Measurement unit (`meas_unit`) — free text, but None-able via a
        //     checkbox that locks the field and stores the "NONE" sentinel.
        // -----------------------------------------------------------------
        if (key === 'meas_unit') {
            const raw = getValueFromAttr();
            const current = raw !== null ? raw : (value != null ? String(value) : '');
            const isNone = isNoneMetaValue(current);
            return `
            <span class="noneable-json-cell" style="display:inline-flex; align-items:center; gap:8px; white-space:nowrap;">
                <label style="display:inline-flex; align-items:center; gap:4px; cursor:pointer;">
                    <input type="checkbox" class="meta-none-cb" ${isNone ? 'checked' : ''}>
                    <span>${noneLabel}</span>
                </label>
                <input type="text" class="json-input meta-none-input" data-path="${fullPath}"
                       size="${unitInputSize(isNone ? '' : current)}" oninput="${UNIT_INPUT_AUTOSIZE}"
                       value="${isNone ? '' : escapeHtml(current)}" ${isNone ? 'disabled' : ''}
                       placeholder="e.g. AU">
            </span>`;
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

        // Wire the "None" checkboxes in the metadata table (measurement unit /
        // concentration value): ticking locks the input, unticking re-enables it.
        function setupMetaNoneToggles() {
            const metaTable = document.getElementById('swal-metadata-table');
            if (!metaTable) return;
            metaTable.querySelectorAll('.noneable-meta-cell .meta-none-cb').forEach(cb => {
                cb.addEventListener('change', () => {
                    const inp = cb.closest('.noneable-meta-cell').querySelector('.meta-none-input');
                    if (!inp) return;
                    if (cb.checked) {
                        inp.value = '';
                        inp.size = 6;
                        inp.disabled = true;
                    } else {
                        inp.disabled = false;
                        inp.focus();
                    }
                });
            });
        }

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
                        'Timestamp': '0.00', 'Turn': '1', 'Measurement': 'ABSORBANCE', 'Unit': 'NONE',
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

            // Convert Timestamps -> Turns (point mode): rewrites the saved file's
            // first column to a 1,2,3… turn index. Destructive (drops the recorded
            // times and any unsaved editor edits), so it confirms first. The
            // editor is reopened afterwards to show the reloaded (converted) file;
            // on cancel/error it is reopened unchanged.
            const convertBtn = document.getElementById('convert-turn-btn');
            if (convertBtn) {
                convertBtn.addEventListener('click', function () {
                    Swal.fire({
                        title: t('editor.convert_turn.confirm_title', 'Convert to Turns?'),
                        text: t('editor.convert_turn.confirm_text', 'The Timestamp column will be replaced by a Turn index (1, 2, 3 …). Recorded times and any unsaved edits will be lost.'),
                        icon: 'warning',
                        showCancelButton: true,
                        confirmButtonText: t('editor.convert_turn.confirm_btn', 'Convert'),
                        cancelButtonText: t('common.cancel', 'Cancel')
                    }).then(function (res) {
                        if (!res.isConfirmed) {
                            editFile(fileName, button, tableSelector);  // restore editor
                            return;
                        }
                        $.ajax({
                            url: '/convert_timestamp_to_turn',
                            method: 'POST',
                            contentType: 'application/json',
                            data: JSON.stringify({ filename: fileName, path: filePath }),
                            success: function (resp) {
                                if (resp.status === 'success') {
                                    // Reopen the editor so the converted (Turn) file is
                                    // visible; if this file is the active display, reload
                                    // it too so the chart reflects the new X axis.
                                    if (tableSelector === '#file-table' && AppState.currentFile === fileName) {
                                        deselectFile(tableSelector);
                                        selectFile(fileName, button, tableSelector);
                                    }
                                    editFile(fileName, button, tableSelector);
                                } else {
                                    Swal.fire({ title: t('common.error', 'Error!'), text: resp.message, icon: 'error', confirmButtonText: t('common.ok', 'OK') })
                                        .then(function () { editFile(fileName, button, tableSelector); });
                                }
                            },
                            error: function (jqXHR) {
                                const msg = (jqXHR.responseJSON && jqXHR.responseJSON.message) || t('editor.convert_turn.failed', 'Conversion failed.');
                                Swal.fire({ title: t('common.error', 'Error!'), text: msg, icon: 'error', confirmButtonText: t('common.ok', 'OK') })
                                    .then(function () { editFile(fileName, button, tableSelector); });
                            }
                        });
                    });
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
                    // ConcenUnit is constrained to the valid units — edit it via a
                    // dropdown rather than free text so an invalid unit can't be typed.
                    if (key === 'ConcenUnit') {
                        const units = (typeof CONCEN_UNITS !== 'undefined') ? CONCEN_UNITS : ['ng/µL', 'nM', '%', 'CFU', 'OD600'];
                        const opts = units.map(u =>
                            `<option value="${escapeHtml(u)}" ${u === value ? 'selected' : ''}>${escapeHtml(u)}</option>`).join('');
                        return `
                                        <tr>
                                            <td class="metadata-key">${key}</td>
                                            <td class="metadata-value">
                                                <select class="metadata-value-select" data-meta-key="${key}">${opts}</select>
                                            </td>
                                        </tr>
                                    `;
                    }
                    // None-able fields (measurement unit / concentration value):
                    // a "None" checkbox locks the input and stores the "NONE"
                    // sentinel; unticking it re-enables free-text entry.
                    if (NONEABLE_META.includes(key)) {
                        const isNone = isNoneMetaValue(value);
                        return `
                                        <tr>
                                            <td class="metadata-key">${key}</td>
                                            <td class="metadata-value noneable-meta-cell" data-meta-key="${key}">
                                              <span style="display:inline-flex; align-items:center; gap:8px; white-space:nowrap;">
                                                <label class="meta-none-toggle" style="display:inline-flex; align-items:center; gap:4px; cursor:pointer;">
                                                    <input type="checkbox" class="meta-none-cb" ${isNone ? 'checked' : ''}>
                                                    <span>${noneLabel}</span>
                                                </label>
                                                <input type="text" class="meta-none-input" size="${unitInputSize(isNone ? '' : value)}" oninput="${UNIT_INPUT_AUTOSIZE}"
                                                       value="${isNone ? '' : escapeHtml(value)}" ${isNone ? 'disabled' : ''}
                                                       placeholder="${nonePlaceholder(key)}">
                                              </span>
                                            </td>
                                        </tr>
                                    `;
                    }
                    return `
                                        <tr>
                                            <td class="metadata-key">${key}</td>
                                            <td
                                                ${isNonEditable ? '' : 'contenteditable="true"'}
                                                data-meta-key="${key}"
                                                class="metadata-value ${isNonEditable ? 'noneditable' : ''}"
                                            >
                                                ${escapeHtml(value)}
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
                        ${(tableSelector === '#file-table' && headers[0] === 'Timestamp') ? `
                        <div>
                            <button id="convert-turn-btn" type="button" class="swal2-styled"
                                style="padding: 5px 10px; background-color: #2980b9;"
                                title="${escapeHtml(t('editor.convert_turn.hint', 'Replace the Timestamp column with a Turn index (1, 2, 3 …) for point mode. This discards the recorded times and any unsaved edits.'))}">
                                ${escapeHtml(t('editor.convert_turn', 'Timestamps → Turns'))}
                            </button>
                        </div>` : ''}
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
                                                    ${escapeHtml(cell.trim())}
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
        const filePath = tableSelector === '#file-table' ? AppState.currentDirectory : AppState.jsonPath + DELIMITER + AppState.currentMeasurementMode;

        // Edit-session lock: while this file is open in the editor, other tabs
        // must not be able to edit it. Acquire a server-side lock keyed to the
        // file before loading its content, heartbeat to keep it fresh, and
        // release it when the modal closes or the tab goes away.
        let editLockToken = null;
        let editLockHeartbeat = null;
        let editLockReleased = false;

        const releaseEditLock = () => {
            if (editLockReleased) return;
            editLockReleased = true;
            if (editLockHeartbeat) { clearInterval(editLockHeartbeat); editLockHeartbeat = null; }
            window.removeEventListener('beforeunload', releaseEditLock);
            if (!editLockToken) return;
            const payload = JSON.stringify({ filename: fileName, path: filePath, token: editLockToken });
            try {
                // sendBeacon survives the unload path (a normal ajax would be
                // cancelled); fall back to a fire-and-forget POST otherwise.
                if (navigator.sendBeacon) {
                    navigator.sendBeacon('/release_edit_lock', new Blob([payload], { type: 'application/json' }));
                } else {
                    $.ajax({ url: '/release_edit_lock', method: 'POST', contentType: 'application/json', data: payload });
                }
            } catch (e) { /* best-effort */ }
        };

        const loadFileForEdit = () => {
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
                if (!container || !workingJSON) return;
                container.innerHTML = buildGraphicUI(workingJSON);
                bindDynamicButtons();
                bindInputListeners();
                syncFitCoefLabels(document.querySelector('.swal2-popup'));
            }

            function bindInputListeners() {
                const popup = document.querySelector('.swal2-popup');
                if (!popup) return;
                popup.querySelectorAll('.json-input').forEach(input => {
                    input.addEventListener('change', () => {
                        const path = input.dataset.path;
                        let val;
                        if (input.type === 'checkbox') val = input.checked;
                        else if (input.type === 'number') val = input.value === '' ? null : parseFloat(input.value);
                        else val = input.value;
                        setValueByPath(path, val);
                    });
                });
                // None checkbox for the measurement unit (`meas_unit`): ticking it
                // locks the text field and stores the "NONE" sentinel; unticking
                // re-enables free-text entry.
                popup.querySelectorAll('.noneable-json-cell .meta-none-cb').forEach(cb => {
                    cb.addEventListener('change', () => {
                        const cell = cb.closest('.noneable-json-cell');
                        const inp = cell.querySelector('.meta-none-input');
                        const path = inp.dataset.path;
                        if (cb.checked) {
                            inp.value = '';
                            inp.size = 6;
                            inp.disabled = true;
                            setValueByPath(path, 'NONE');
                        } else {
                            inp.disabled = false;
                            setValueByPath(path, inp.value);
                            inp.focus();
                        }
                    });
                });
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
                            setupMetaNoneToggles();
                        } else if (editMode === 'graphic') {
                            syncFitCoefLabels(Swal.getPopup());
                            bindInputListeners();
                        }

                        if (toggleButton) {
                            toggleButton.addEventListener('click', () => {
                                editMode = editMode === 'text' ? (tableSelector === '#file-table' ? 'table' : 'graphic') : 'text';
                                toggleButton.textContent = 'Switch to ' + (editMode === 'text' ? (tableSelector === "#file-table" ? 'Table' : 'Graphic') : 'Text') + ' Mode';
                                Swal.getHtmlContainer().innerHTML = renderContent({ content: originalContent });
                                if (editMode === 'table') {
                                    setTimeout(() => { setupTableEvents(); setupMetaNoneToggles(); }, 50);
                                } else if (editMode === 'graphic') {
                                    syncFitCoefLabels(Swal.getPopup());
                                    bindInputListeners();
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
                                        // None-able field (measurement unit / concentration
                                        // value): read the checkbox + locked input, not
                                        // textContent. A ticked box (or an empty input) writes
                                        // the "NONE" sentinel so the file stays format-valid.
                                        if (cells[1].classList.contains('noneable-meta-cell')) {
                                            const cb = cells[1].querySelector('.meta-none-cb');
                                            const inp = cells[1].querySelector('.meta-none-input');
                                            const raw = (cb && cb.checked) ? '' : (inp ? inp.value.trim() : '');
                                            return `# ${key}: ${raw === '' ? 'NONE' : raw}`;
                                        }
                                        // Constrained metadata (e.g. ConcenUnit) is edited via a
                                        // <select>; read its value. Reading textContent would
                                        // concatenate every option label (e.g. "ng/µLnM%CFU").
                                        const sel = cells[1].querySelector('select');
                                        const value = sel ? sel.value.trim() : cells[1].textContent.trim();
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
                                    data: /^\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|-?\d+|-?\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d*)\s*$/,
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
                                    // Value cells: a number or a device token — OVFL / NONE /
                                    // INF (lower-case "inf" from firmware predating the token).
                                    // Mirrors sentinels.TOKEN_PATTERN in the backend validator.
                                    data: /^\s*\d+(?:\.\d{1,2})?\s*(?:(?:,\s*)?(?:-?\d+(?:\.\d{1,3})?|OVFL|NONE|[+-]?[Ii][Nn][Ff])?\s*)*$/,
                                    error: 'Invalid format (Pattern 3). Header must be: Timestamp,Value:1,Value:2,...',
                                    meta: [
                                        /^#\s*Measurement\s*:\s*.+$/,
                                        /^#\s*Unit\s*:\s*.+$/,
                                        /^#\s*Concentration\s*:\s*.+$/
                                    ]
                                },
                                {
                                    // Point-mode Turn series (Rule §2.27): same as the
                                    // Timestamp series but the first column is an
                                    // integer turn index (no decimal). Mirrors the
                                    // backend CSV_SCHEMA_TIMESERIES_TURN validator.
                                    header: /^\s*Turn\s*,\s*Value:\d+(?:\s*,\s*Value:\d+)*\s*$/,
                                    data: /^\s*\d+\s*(?:(?:,\s*)?(?:-?\d+(?:\.\d{1,3})?|OVFL|NONE|[+-]?[Ii][Nn][Ff])?\s*)*$/,
                                    error: 'Invalid format (Pattern 4). Header must be: Turn,Value:1,Value:2,...',
                                    meta: [
                                        /^#\s*Measurement\s*:\s*.+$/,
                                        /^#\s*Unit\s*:\s*.+$/,
                                        /^#\s*Concentration\s*:\s*.+$/
                                    ]
                                },
                                {
                                    // Turn-based point calibration (Rule §2.27): each
                                    // Turn is a standard, so the table is
                                    // Concentration,Value with no TimePoint column.
                                    // Mirrors backend CSV_SCHEMA_POINT_CAL_TURN.
                                    header: /^\s*Concentration\s*,\s*Value\s*$/,
                                    data: /^\s*(NONE|\d+|\d+\.\d+)\s*,\s*(NONE|\d+|\d+\.\d+)\s*$/,
                                    error: 'Invalid format (Pattern 5). Header must be: Concentration,Value',
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
                                    Swal.showValidationMessage('Invalid JSON format');
                                    return false;
                                }
                            } else if (editMode === 'graphic') {
                                content = finalContent !== null ? finalContent : originalContent;
                            }
                        }

                        return { newFileName, content };
                    }
                }).then((result) => {
                    // Modal closed (saved or cancelled) — free the file for other tabs.
                    releaseEditLock();
                    deleteBtn.prop('disabled', false).removeClass('disabled').attr('aria-disabled', 'false');

                    if (result.isConfirmed) {
                        const { newFileName, content } = result.value;

                        $.post('/edit_file', {
                            filename: fileName,
                            new_filename: newFileName,
                            path: filePath,
                            content: content,
                            edit_token: editLockToken,
                            calibrate_mode: AppState.currentMeasurementMode === 'calibrate' ? calDiv.getAttribute('data-value') : 'timestamp'
                        }, async function (response) {
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
                                // If the edited file is the active one, reload it so the
                                // display reflects the new content/metadata. Await it so the
                                // pairing re-validation below sees the freshly-loaded data.
                                if ((tableSelector === "#file-table" && AppState.currentFile === fileName) || (tableSelector === "#json-table" && AppState.currentJSON === fileName)) {
                                    deselectFile(tableSelector);
                                    await selectFile(newFileName, button, tableSelector);
                                    toggleMode();
                                }
                                // Refresh the table's identity maps + rows so badges and
                                // pairing disable-states reflect the edited metadata.
                                if (tableSelector === "#file-table") {
                                    await updateDirectory(AppState.currentDirectory);
                                } else if (tableSelector === "#json-table") {
                                    await updateJSONTable();
                                }
                                // A metadata edit can misalign a previously-matched CSV↔JSON
                                // pair; unpair the calibration curve if so (warns the user).
                                const unpaired = revalidateActivePairing();
                                if (getBtnChecked("no-swal-checkbox")) {
                                    return; // Exit if no popup is needed
                                }
                                if (!unpaired) {
                                    Swal.fire({
                                        title: 'Updated!',
                                        text: textMsg,
                                        icon: 'success',
                                        timer: 2000,
                                        showConfirmButton: false
                                    });
                                }
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
            releaseEditLock();
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
        };  // end loadFileForEdit

        // Acquire the edit lock first; only load the file if we got it.
        $.ajax({
            url: '/acquire_edit_lock',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ filename: fileName, path: filePath })
        }).done(function (lockResp) {
            editLockToken = (lockResp && lockResp.token) || null;
            window.addEventListener('beforeunload', releaseEditLock);
            editLockHeartbeat = setInterval(function () {
                if (!editLockToken) return;
                $.ajax({
                    url: '/refresh_edit_lock', method: 'POST', contentType: 'application/json',
                    data: JSON.stringify({ filename: fileName, path: filePath, token: editLockToken })
                });
            }, 30000);
            loadFileForEdit();
        }).fail(function (jqXHR) {
            deleteBtn.prop('disabled', false).removeClass('disabled').attr('aria-disabled', 'false');
            let msg = 'This file is currently being edited in another tab.';
            if (jqXHR.status !== 423 && jqXHR.responseJSON && jqXHR.responseJSON.message) {
                msg = jqXHR.responseJSON.message;
            }
            Swal.fire({ title: 'File in use', text: msg, icon: 'warning', confirmButtonText: 'OK' });
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

    const cleanHeader = t =>
        t.replace(/\s*\(\-\)\s*$/, '')
            .replace(/\(\<\)\s*\(\>\)\s*$/, '')
            .trim()
            .split(' ')[0];

    const headers = Array.from(table.querySelectorAll('th'));
    const colIndex = headers.findIndex(
        th => cleanHeader(th.textContent) === headerName
    );

    if (colIndex === -1) return;

    const first = 1;
    const last = headers.length - 1;

    // 🔄 wrap without shifting middle
    if (colIndex === first && direction === -1) {
        swapColumns(table, first, last);
    }
    else if (colIndex === last && direction === 1) {
        swapColumns(table, first, last);
    }
    else {
        const targetIndex = colIndex + direction;
        swapColumns(table, colIndex, targetIndex);
    }

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

function swapColumns(table, i, j) {
    if (i === j) return;
    if (i > j) [i, j] = [j, i]; // normalize order

    const headerRow = table.querySelector('thead tr');

    // --- HEADERS ---
    const headers = Array.from(headerRow.children);
    const thA = headers[i];
    const thB = headers[j];

    headerRow.removeChild(thB);
    headerRow.removeChild(thA);

    headerRow.insertBefore(thB, headerRow.children[i]);
    headerRow.insertBefore(thA, headerRow.children[j]);

    // --- BODY ---
    table.querySelectorAll('tbody tr').forEach(row => {
        const cells = Array.from(row.children);
        const tdA = cells[i];
        const tdB = cells[j];

        row.removeChild(tdB);
        row.removeChild(tdA);

        row.insertBefore(tdB, row.children[i]);
        row.insertBefore(tdA, row.children[j]);
    });
}

