async function filterFiles(files) {
    const checks = await Promise.all(
        files.map(async (fileName) => {
            let response;
            try {
                response = await fetch('/get_headers?file=' + encodeURIComponent(fileName));
            } catch (networkErr) {
                console.warn(`Network error for ${fileName}:`, networkErr);
                return false;
            }

            let data;
            try {
                data = await response.json();
            } catch (jsonErr) {
                console.warn(`Invalid JSON for ${fileName}:`, jsonErr);
                return false;
            }

            if (!response.ok) {
                const friendlyMsg = data.error ?? `Server error ${response.status}`;
                console.info(`Header check failed (${response.status}) for ${fileName}: ${friendlyMsg}`);
                return { error: friendlyMsg };
            }

            const cal_headers_kinetics = ["Concentration", "maxRate", "Slope", "Sat", "Time To Sat"];
            const cal_headers_point = ["Concentration", "Value", "TimePoint"];

            if (!data.headers) {
                return false;
            }

            const isMeasHeader = checkMeasHeader(data.headers);

            if (AppState.currentMeasurementMode === "kinetics" || AppState.currentMeasurementMode === "point") {
                return isMeasHeader;
            }

            if (AppState.currentMeasurementMode === "calibrate") {
                const cal_type = calDiv.getAttribute('data-value');
                const expected = cal_type === "kinetics" ? cal_headers_kinetics : cal_headers_point;
                return arraysEqual(data.headers, expected);
            }

            return false;
        })
    );

    const filteredFiles = files.filter((_, idx) => {
        const result = checks[idx];
        return result === true;
    });

    return filteredFiles;
}

function buildMeasHeaders() {
    const headers = ["Timestamp"];
    for (let i = 1; i <= AppState.numSources; i++) {
        headers.push(`Value:${i}`);
    }
    return headers;
}

function checkMeasHeader(headers) {
    if (getBtnChecked("filter-source")) {
        const expectedHeaders = buildMeasHeaders();
        return arraysEqual(headers, expectedHeaders);
    } else {
        const meas_headers = /^\s*Timestamp\s*Value:\d+(?:\s*Value:\d+)*\s*$/;
        const headerString = headers.join('');
        return meas_headers.test(headerString);
    }
}

function arraysEqual(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
}

function updateJSONTable(files) {
    let html = '<tr><th>Calibrated JSON</th><th colspan="3">Action</th></tr>';
    if (files && files.length > 0) {
        files.forEach(file => {
            const isSelected = file === AppState.currentJSON ? ' class="selected"' : '';
            html += `<tr${isSelected}><td>${file}</td><td><button onclick="selectFile('${file}', this, '#json-table')">✅ Select</button></td><td><button onclick="deleteFile('${file}', this, '#json-table')">❌ Delete</button></td><td><button onclick="editFile('${file}', this, '#json-table')">✏️ Edit</button></td></tr>`;
        })
    } else {
        html += '<tr><td colspan="2">No Calibrated JSON is available.</td></tr>';
    }
    document.getElementById("json-table").innerHTML = html;
    const searchInput = document.getElementById('json-search');
    if (searchInput && searchInput.value) {
        filterTable('json-table', searchInput.value);
    }
}

function updateFileTable(files, deselect = false) {

    let html = '<tr><th>File Name</th><th colspan="3">Action</th></tr>';
    if (files) {
        filterFiles(files).then((filteredFiles) => {
            if (filteredFiles && filteredFiles.length > 0) {
                filteredFiles.forEach(file => {
                    const isSelected = file === AppState.currentFile ? ' class="selected"' : '';
                    html += `<tr${isSelected}><td>${file}</td><td><button onclick="selectFile('${file}', this)">✅ Select</button></td><td><button onclick="deleteFile('${file}', this)">❌ Delete</button></td><td><button onclick="editFile('${file}', this)">✏️ Edit</button></td></tr>`;
                });
            } else {
                html += '<tr><td colspan="3">No CSV files is available.</td></tr>';
            }
            document.getElementById("file-table").innerHTML = html;
            const searchInput = document.getElementById('file-search');
            if (searchInput && searchInput.value) {
                filterTable('file-table', searchInput.value);
            }
            if (deselect) {
                AppState.currentFile = null;
                $toggleQueryClass("#file-table tr", "selected", false);
                updateFileDisplay(AppState.currentFile);
            }
        });
    }
}

function updateFileDisplay(curFile) {
    const displayElement = document.getElementById('selected-file-display');
    if (curFile)
        displayElement.innerHTML = `Selected File: ${curFile}`;
    else
        displayElement.innerHTML = `No file selected`;
}

async function fetchJSONContent(jsonFile, callback) {
    try {
        const url = `/get_json_content?json_name=${encodeURIComponent(jsonFile)}&mode=${encodeURIComponent(AppState.currentMeasurementMode)}&numSources=${encodeURIComponent(AppState.numSources)}`;
        const data = await fetchJSON(url);
        callback(data.json);
    } catch (error) {
        console.error("Error fetching JSON content:", error);
    }
}

function browseSavingLocation(deselect, changeToCalibrate = false, button = null) {
    // Temporarily disable the button to prevent multiple clicks
    if (button) button.disabled = true;
    setTimeout(() => {
        if (button) button.disabled = false;
    }, 1000); // Re-enable the button after 1 second
    deselectFile();
    deselectFile("#json-table");
    if (button?.id === "go-to-exp-btn") {
        blinkingItem("cal-mode-select", 5000);
        blinkingItem("measurement-mode", 5000);
        blinkingItem("file-selection", 5000);
        updateDirectory(deselect, changeToCalibrate);
    } else {
        fetch('/api/current_output')
            .then(response => {
                if (!response.ok) {
                    // no marker or server error -> fallback
                    return { exists: false };
                }
                return response.json();
            })
            .then(data => {
                if (data && data.exists) {
                    // Use server-provided directory (with trailing separator if needed)
                    const fileName = data.filename;

                    updateDirectory(deselect, changeToCalibrate);

                    // Wait for the table to refresh/populate, then select the row's button
                    setTimeout(() => {
                        // find a TD whose text exactly equals the filename
                        const cells = document.querySelectorAll("#file-table tr td");
                        const cell = Array.from(cells).find(td => td.textContent.trim() === fileName);

                        if (cell) {
                            const row = cell.closest("tr");
                            const btn = row.querySelector("button");

                            if (btn) {
                                selectFile(fileName, btn, "#file-table");
                            } else {
                                // fallback: pass the cell element so selectFile still finds the row to highlight
                                selectFile(fileName, cell, "#file-table");
                            }
                        } else {
                            console.warn(`File "${fileName}" not found in #file-table.`);
                        }
                    }, 500); // adjust delay if your table takes longer to populate
                } else {
                    // no recorded path -> fallback to original behavior
                    updateDirectory(deselect, changeToCalibrate);
                    blinkingItem("file-selection", 5000);
                }
            })
            .catch(err => {
                console.error("Error fetching current_output:", err);
                updateDirectory(deselect, changeToCalibrate);
            });
    }
}

function blinkingItem(id, timeOut = 5000) {
    const element = document.getElementById(id);
    if (!element) return;

    element.focus();
    element.classList.add('blinking');

    if (timeOut) {
        setTimeout(() => {
            element.classList.remove('blinking');
        }, timeOut);
    }
}

function scrollWhenVisible(elementId, duration = 500) {
    const target = document.getElementById(elementId);
    if (!target) return;

    // Helper to check if element is visible
    const isVisible = el =>
        el.offsetParent !== null && window.getComputedStyle(el).display !== "none";

    // Scroll smoothly to the element
    const scrollToElement = () => {
        const targetTop = target.getBoundingClientRect().top + window.scrollY;
        window.scrollTo({ top: targetTop, behavior: "smooth" });
    };

    // If visible, scroll immediately
    if (isVisible(target)) {
        scrollToElement();
        return;
    }

    // Poll every 100ms until element becomes visible
    const interval = setInterval(() => {
        if (isVisible(target)) {
            scrollToElement();
            clearInterval(interval);
        }
    }, 100);
}