function browseDirectory(blinkItem = false) {
    $.get('/get_parents', function(parentResponse) {
        console.log("Parent directory:", parentResponse.parent);
        let parentHtml = parentResponse.parent ? 
            `${parentResponse.parent.split(delimiter).pop() ? 
                `<div onclick="updateDirectory('${parentResponse.parent}', 'true')" ondblclick="browseDirectory(true)">${parentResponse.parent.split(delimiter).pop()}</div>` : 
                '<div>No parent directory</div>'}` : 
            '<div>No parent directory</div>';
        $("#parent-dir").html(parentHtml);

        $.get('/get_children', function(childResponse) {
            console.log("Child directories:", childResponse.children);
            const sortedChildren = childResponse.children.sort((a, b) => a.localeCompare(b));
            // Update the child directories display
            let childHtml = sortedChildren.length > 0 ? 
                `${sortedChildren.map(dir => 
                    `<div onclick="updateDirectory('${dir}', 'true')" ondblclick="browseDirectory(true)">${dir.split(delimiter).pop()}</div>`
                ).join('')}` : 
                '<div>No child directories</div>';
            $("#child-dirs").html(childHtml);
        }).fail(function(jqXHR, textStatus, errorThrown) {
            console.log("Error fetching child directories:", textStatus, errorThrown);
            $("#error-message").text("Error fetching child directories").show();
        });
    }).fail(function(jqXHR, textStatus, errorThrown) {
        console.log("Error fetching parent directory:", textStatus, errorThrown);
        $("#error-message").text("Error fetching parent directory").show();
    });
    if (blinkItem)
        blinkingItem("#file-selection", 5000);
}

async function filterFiles(files) {
    const checks = await Promise.all(
        files.map(async (fileName) => {
            const filePath = $("#directory").val() + delimiter + fileName;

            try {
                const response = await fetch('/get_headers?file=' + encodeURIComponent(filePath));
                const data = await response.json();
                const meas_headers = ["Timestamp","Value","Type","Blanked"];
                const cal_headers_kinetics = ["Concentration","maxRate","Slope","Sat","Time To Sat","BlankType"];
                const cal_headers_point = ["Concentration", "Value", "TimePoint", "BlankType"];
                if (data.headers) {
                    const isMeasHeader = JSON.stringify(data.headers) === JSON.stringify(meas_headers);
                    if (AppState.currentMeasurementMode === "kinetics" || AppState.currentMeasurementMode === "point") {
                        return isMeasHeader;
                    } else if (AppState.currentMeasurementMode === "calibrate") {
                        const cal_type = $("#cal-mode-select").val();
                        let isCalHeader = false;
                        if (cal_type === "kinetics") {
                            isCalHeader = JSON.stringify(data.headers) === JSON.stringify(cal_headers_kinetics);
                        }
                        else {
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
    $("#json-table").html(html);
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
        $("#file-table").html(html);
        if (deselect) {
            AppState.currentFile = null;
            $("#file-table tr").removeClass("selected");
            updateFileDisplay(AppState.currentFile);
        }
    });  
}

function updateFileDisplay(curFile) {
    const displayElement = document.getElementById('selected-file-display');
    if (curFile)
        $("#selected-file-display").html(`Selected File: ${curFile}`);
    else
        $("#selected-file-display").html(`No file selected`);
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
        blinkingItem("#cal-mode-select", 5000);
        blinkingItem("#measurement-mode", 5000);
        blinkingItem("#file-selection", 5000);
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
                const dirPath = data.dir_with_sep || data.dir || path;
                const fileName = data.filename;

                updateDirectory(dirPath, deselect, changeToCalibrate);

                // Wait for the table to refresh/populate, then select the row's button
                setTimeout(() => {
                    // find a TD whose text exactly equals the filename
                    const $cell = $("#file-table tr td").filter(function() {
                        return $(this).text().trim() === fileName;
                    }).first();

                    if ($cell.length) {
                        const $row = $cell.closest("tr");
                        // try to find a button in the row (change selector to match your table if needed)
                        const $btn = $row.find("button").first();

                        if ($btn.length) {
                            selectFile(fileName, $btn[0], "#file-table");
                        } else {
                            // fallback: pass the cell element so selectFile still finds the row to highlight
                            selectFile(fileName, $cell[0], "#file-table");
                        }
                    } else {
                        console.warn(`File "${fileName}" not found in #file-table.`);
                    }
                }, 500); // adjust delay if your table takes longer to populate
            } else {
                // no recorded path -> fallback to original behavior
                updateDirectory(path, deselect, changeToCalibrate);
                blinkingItem("#file-selection", 5000);
            }
        })
        .catch(err => {
            console.error("Error fetching current_output:", err);
            updateDirectory(path, deselect, changeToCalibrate);
        });
    }
}

function blinkingItem(id, timeOut=5000) {
    const element = $(id);
    if (element.length) {
        element.focus();
        element.addClass('blinking');
        if (timeOut) {
            setTimeout(() => {
                element.removeClass('blinking');
            }, timeOut);
        }
    }
}

function scrollWhenVisible(elementId, duration) {
    const $target = $("#" + elementId);
    
    // Function to check if element is visible
    function isVisible($elem) {
        return $elem.is(":visible") && $elem.css("display") !== "none";
    }
    
    // If element is already visible, scroll immediately
    if (isVisible($target)) {
        $("html, body").animate({ scrollTop: $target.offset().top }, duration);
        return;
    }
    
    // Poll for visibility every 100ms
    const interval = setInterval(function() {
        if (isVisible($target)) {
            $("html, body").animate({ scrollTop: $target.offset().top }, duration);
            clearInterval(interval); // Stop polling once visible
        }
    }, 100);
}