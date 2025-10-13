function browseDirectory(blinkItem = false) {
    $.get('/get_parents', function(parentResponse) {
        console.log("Parent directory:", parentResponse.parent);
        let parentHtml = parentResponse.parent ? 
            `${parentResponse.parent.split(delimiter).pop() ? 
                `<div onclick="updateDirectory('${parentResponse.parent}', 'true')" ondblclick="browseDirectory(true)">${parentResponse.parent.split(delimiter).pop()}</div>` : 
                '<div>No parent directory</div>'}` : 
            '<div>No parent directory</div>';
        document.getElementById("parent-dir").innerHTML = parentHtml;

        $.get('/get_children', function(childResponse) {
            console.log("Child directories:", childResponse.children);
            const sortedChildren = childResponse.children.sort((a, b) => a.localeCompare(b));
            // Update the child directories display
            let childHtml = sortedChildren.length > 0 ? 
                `${sortedChildren.map(dir => 
                    `<div onclick="updateDirectory('${dir}', 'true')" ondblclick="browseDirectory(true)">${dir.split(delimiter).pop()}</div>`
                ).join('')}` : 
                '<div>No child directories</div>';
            document.getElementById("child-dirs").innerHTML = childHtml;
        }).fail(function(jqXHR, textStatus, errorThrown) {
            console.log("Error fetching child directories:", textStatus, errorThrown);
            $showText("error-message", "Error fetching child directories");
        });
    }).fail(function(jqXHR, textStatus, errorThrown) {
        console.log("Error fetching parent directory:", textStatus, errorThrown);
        $showText("error-message", "Error fetching parent directory");
    });
    if (blinkItem)
        blinkingItem("file-selection", 5000);
}

async function filterFiles(files) {
    const checks = await Promise.all(
        files.map(async (fileName) => {
            const filePath = document.getElementById("directory").value + delimiter + fileName;

            try {
                const response = await fetch('/get_headers?file=' + encodeURIComponent(filePath));
                const data = await response.json();
                let meas_headers, cal_headers_kinetics, cal_headers_point;
                cal_headers_kinetics = ["Concentration", "maxRate", "Slope", "Sat", "Time To Sat", "BlankType"];
                cal_headers_point = ["Concentration", "Value", "TimePoint", "BlankType"];
                
                if (!AppState.multiSource) {
                    meas_headers = ["Timestamp", "Value", "Type", "Blanked"];
                } else {
                    // Dynamically generate meas_headers based on numSources
                    meas_headers = ["Timestamp"];
                    for (let i = 1; i <= AppState.numSources; i++) {
                        meas_headers.push(`Value:${i}`);
                    }
                }

                if (data.headers) {
                    const isMeasHeader = JSON.stringify(data.headers) === JSON.stringify(meas_headers);
                    if (AppState.currentMeasurementMode === "kinetics" || AppState.currentMeasurementMode === "point") {
                        return isMeasHeader;
                    } else if (AppState.currentMeasurementMode === "calibrate") {
                        const cal_type = calDiv.getAttribute('data-value');
                        let isCalHeader = false;
                        if (cal_type === "kinetics") {
                            isCalHeader = JSON.stringify(data.headers) === JSON.stringify(cal_headers_kinetics);
                        } else {
                            isCalHeader = JSON.stringify(data.headers) === JSON.stringify(cal_headers_point);
                        }
                        return isCalHeader;
                    }
                }
                return false; // on error or no headers
            } catch (error) {
                console.error("Failed to fetch headers for", fileName, error);
                return false;
            }
        })
    );

    // Now filter files based on the results
    const filteredFiles = files.filter((_, idx) => checks[idx]);

    return filteredFiles;
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
}

function updateFileTable(files, deselect) {

    let html = '<tr><th>File Name</th><th colspan="3">Action</th></tr>';

    filterFiles(files).then((filteredFiles) => {
        if (filteredFiles && filteredFiles.length > 0) {
            filteredFiles.forEach(file => {
                const isSelected = file === AppState.currentFile ? ' class="selected"' : '';
                html += `<tr${isSelected}><td>${file}</td><td><button onclick="selectFile('${file}', this)">✅ Select</button></td><td><button onclick="deleteFile('${file}', this)">❌ Delete</button></td><td><button onclick="editFile('${file}', this)">✏️ Edit</button></td></tr>`;
            });
        } else {
            html += '<tr><td colspan="2">No CSV files found in the directory.</td></tr>';
        }
        document.getElementById("file-table").innerHTML = html;
        if (deselect) {
            AppState.currentFile = null;
            $toggleQueryClass("#file-table tr", "selected", false);
            updateFileDisplay(AppState.currentFile);
        }
    });  
}

function updateFileDisplay(curFile) {
    const displayElement = document.getElementById('selected-file-display');
    if (curFile)
        displayElement.innerHTML = `Selected File: ${curFile}`;
    else
        displayElement.innerHTML = `No file selected`;
}

function fetchJSON(jsonFile, callback) {
    $.get('/get_json_content', {
        json_name: jsonFile,
        mode: AppState.currentMeasurementMode,
        isMultiSource: AppState.multiSource,
        numSources: AppState.numSources
    }, function(response) {
        callback(response.json, response.path);
    })
}

function browseSavingLocation(path, deselect, changeToCalibrate=false, button = null) {
    // Temporarily disable the button to prevent multiple clicks
    $(button).prop("disabled", true);
    setTimeout(() => {
        $(button).prop("disabled", false);
    }, 1000); // Re-enable the button after 1 second
    if (button.id === "go-to-exp-btn") {
        blinkingItem("cal-mode-select", 5000);
        blinkingItem("measurement-mode", 5000);
        blinkingItem("file-selection", 5000);
        updateDirectory(path, deselect, changeToCalibrate);
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
                const dirPath = data.dir || path || data.dir_with_sep;
                const fileName = data.filename;

                updateDirectory(dirPath, deselect, changeToCalibrate);

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
                updateDirectory(path, deselect, changeToCalibrate);
                blinkingItem("file-selection", 5000);
            }
        })
        .catch(err => {
            console.error("Error fetching current_output:", err);
            updateDirectory(path, deselect, changeToCalibrate);
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