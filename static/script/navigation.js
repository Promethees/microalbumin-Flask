function browseDirectory(blinkItem = false) {
    $.get('/get_parents', function (parentResponse) {
        console.log("Parent directory:", parentResponse.parent);
        let parentHtml = parentResponse.parent ?
            `${parentResponse.parent.split(DELIMITER).pop() ?
                `<div onclick="updateDirectory('${parentResponse.parent}', 'true')" ondblclick="browseDirectory(true)">${parentResponse.parent.split(DELIMITER).pop()}</div>` :
                '<div>No parent directory</div>'}` :
            '<div>No parent directory</div>';
        document.getElementById("parent-dir").innerHTML = parentHtml;

        $.get('/get_children', function (childResponse) {
            console.log("Child directories:", childResponse.children);
            const sortedChildren = childResponse.children.sort((a, b) => a.localeCompare(b));
            // Update the child directories display
            let childHtml = sortedChildren.length > 0 ?
                `${sortedChildren.map(dir =>
                    `<div onclick="updateDirectory('${dir}', 'true')" ondblclick="browseDirectory(true)">${dir.split(DELIMITER).pop()}</div>`
                ).join('')}` :
                '<div>No child directories</div>';
            document.getElementById("child-dirs").innerHTML = childHtml;
        }).fail(function (jqXHR, textStatus, errorThrown) {
            console.log("Error fetching child directories:", textStatus, errorThrown);
            $showText("error-message", "Error fetching child directories");
        });
    }).fail(function (jqXHR, textStatus, errorThrown) {
        console.log("Error fetching parent directory:", textStatus, errorThrown);
        $showText("error-message", "Error fetching parent directory");
    });
    if (blinkItem)
        blinkingItem("file-selection", 5000);
}

async function filterFiles(files) {
    const checks = await Promise.all(
        files.map(async (fileName) => {
            const filePath = document.getElementById("directory").value + DELIMITER + fileName;

            let response;
            try {
                response = await fetch('/get_headers?file=' + encodeURIComponent(filePath));
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

            if (AppState.currentMeasurementMode === "report") {
                return true;
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

function updateReportTable(subjects) {
    let html = '<tr><th id="file-table-header-name">Folder Name</th><th colspan="3">Action</th></tr>';
    document.getElementById("file-search").placeholder = "Search subject folders...";
    if (subjects && subjects.length > 0) {
        subjects.forEach(subject => {
            const isSelected = subject === AppState.currentReportSubject ? ' class="selected"' : '';
            html += `<tr${isSelected}><td>${subject}</td><td><button onclick="selectFile('${subject}', this)">📁 Select Subject</button></td><td><button onclick="deleteReportSubject('${subject}', this)">❌ Delete</button></td><td><button onclick="editReportSubject('${subject}', this)">✏️ Edit</button></td></tr>`;
        });
    } else {
        html += '<tr><td colspan="4">No report subjects found.</td></tr>';
    }
    document.getElementById("file-table").innerHTML = html;
    const searchInput = document.getElementById('file-search');
    if (searchInput && searchInput.value) {
        filterTable('file-table', searchInput.value);
    }
}

function updateFileTable(files, deselect) {
    let html = '<tr><th>File Name</th><th colspan="3">Action</th></tr>';

    return filterFiles(files).then((filteredFiles) => {
        if (filteredFiles && filteredFiles.length > 0) {
            filteredFiles.forEach(file => {
                const isSelected = file === AppState.currentFile ? ' class="selected"' : '';
                html += `<tr${isSelected}><td>${file}</td><td><button onclick="selectFile('${file}', this)">✅ Select</button></td><td><button onclick="deleteFile('${file}', this)">❌ Delete</button></td><td><button onclick="editFile('${file}', this)">✏️ Edit</button></td></tr>`;
            });
        } else {
            html += '<tr><td colspan="4">No CSV files found in the directory.</td></tr>';
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

function filterTable(tableId, query) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const trs = table.getElementsByTagName("tr");
    const lowerQuery = query.toLowerCase();
    for (let i = 1; i < trs.length; i++) {
        const tds = trs[i].getElementsByTagName("td");
        if (tds.length > 0) {
            const textValue = tds[0].textContent || tds[0].innerText;
            if (textValue.toLowerCase().indexOf(lowerQuery) > -1) {
                trs[i].style.display = "";
            } else {
                trs[i].style.display = "none";
            }
        }
    }
}

function updateFileDisplay(curFile) {
    const displayElement = document.getElementById('selected-file-display');
    if (curFile) {
        displayElement.innerHTML = `Selected File: ${curFile}`;
        if (AppState.currentMeasurementMode === 'report') {
            onReportFolderSelected(curFile);
        }
    } else {
        displayElement.innerHTML = `No file selected`;
    }
}


function fetchJSON(jsonFile, callback) {
    $.get('/get_json_content', {
        json_name: jsonFile,
        mode: AppState.currentMeasurementMode,
        numSources: AppState.numSources
    }, function (response) {
        callback(response.json);
    }).fail(function (xhr, status, error) {
        console.error("fetchJSON failed:", error);
        callback(null);
    });
}

async function browseSavingLocation(changeToCalibrate = false, button = null, path = "") {
    // Temporarily disable the button to prevent multiple clicks
    $(button).prop("disabled", true);
    setTimeout(() => {
        $(button).prop("disabled", false);
    }, 1000); // Re-enable the button after 1 second
    if (button.id === "go-to-exp-btn") {
        blinkingItem("cal-mode-select", 5000);
        blinkingItem("measurement-mode", 5000);
        blinkingItem("file-selection", 5000);
        const dirPath = document.getElementById("save-dir").value;
        await updateDirectory(dirPath, true, changeToCalibrate);
    } else {
        try {
            const response = await fetch('/api/current_output');
            let data = { exists: false };
            if (response.ok) {
                data = await response.json();
            }

            if (data && data.exists) {
                // Use server-provided directory (with trailing separator if needed)
                const dirPath = data.dir || data.dir_with_sep;
                const fileName = data.filename;

                await updateDirectory(dirPath, true, changeToCalibrate);

                // Wait for the table to refresh/populate, then select the row's button
                // Since updateDirectory now returns a Promise, we don't need a timeout here
                // but we wait one tick to ensure DOM is updated
                await new Promise(resolve => setTimeout(resolve, 50));

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
            } else {
                // no recorded path -> fallback to original behavior
                await updateDirectory(path, true, changeToCalibrate);
                blinkingItem("file-selection", 5000);
            }
        } catch (err) {
            console.error("Error fetching current_output:", err);
            await updateDirectory(path, true, changeToCalibrate);
        }
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

    // Poll every 100ms until element becomes visible, but cancel after `duration` ms
    // to prevent stale intervals from firing in a later session or context.
    const interval = setInterval(() => {
        if (isVisible(target)) {
            scrollToElement();
            clearInterval(interval);
        }
    }, 100);
    setTimeout(() => clearInterval(interval), duration);
}