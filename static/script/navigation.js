function browseDirectory() {
    $.get('/get_parents', function(parentResponse) {
        console.log("Parent directory:", parentResponse.parent);
        let parentHtml = parentResponse.parent ? 
            `${parentResponse.parent.split(delimiter).pop() ? 
                `<div onclick="updateDirectory('${parentResponse.parent}', 'true')">${parentResponse.parent.split(delimiter).pop()}</div>` : 
                '<div>No parent directory</div>'}` : 
            '<div>No parent directory</div>';
        $("#parent-dir").html(parentHtml);

        $.get('/get_children', function(childResponse) {
            console.log("Child directories:", childResponse.children);
            let childHtml = childResponse.children.length > 0 ? 
                `${childResponse.children.map(dir => 
                    `<div onclick="updateDirectory('${dir}', 'true')">${dir.split(delimiter).pop()}</div>`
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
}

async function filterFiles(files) {
    const checks = await Promise.all(
        files.map(async (fileName) => {
            const filePath = $("#directory").val() + delimiter + fileName;

            try {
                const response = await fetch('/get_headers?file=' + encodeURIComponent(filePath));
                const data = await response.json();
                const meas_headers = ["Timestamp","Measurement","Value","Unit","Type","Blanked","Concentration"];
                const cal_headers_kinetics = ["Measurement","Concentration","Vmax","Slope","Sat","Time To Sat", "MeasUnit", "TimeUnit","BlankType", "MeasMode"];
                const cal_headers_point = ["Measurement","Concentration", "Value", "MeasUnit", "TimePoint", "TimeUnit", "BlankType", "MeasMode"];
                if (data.headers) {
                    const isMeasHeader = JSON.stringify(data.headers) === JSON.stringify(meas_headers);
                    // const isCalHeader = JSON.stringify(data.headers) === JSON.stringify(cal_headers_1) || JSON.stringify(data.headers) === JSON.stringify(cal_headers_2);
                    if (currentMeasurementMode === "kinetics" || currentMeasurementMode === "point") {
                        // console.log("current data header is", data.headers);
                        return isMeasHeader;
                    } else if (currentMeasurementMode === "calibrate") {
                        const cal_type = $("#cal-mode-select").val();
                        // console.log("the cal type is ", cal_type);
                        let isCalHeader = false;
                        if (cal_type === "kinetics") {
                            isCalHeader = JSON.stringify(data.headers) === JSON.stringify(cal_headers_kinetics);
                        }
                        else {
                            isCalHeader = JSON.stringify(data.headers) === JSON.stringify(cal_headers_point);
                        }
                        return isCalHeader;
                    }
                    // return currentMeasurementMode === "kinetics" ? hasTimestamp : !hasTimestamp;
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
    let html = '<tr><th>Calibrated JSON</th><th>Action</th></tr>';
    if (files && files.length > 0) {
        files.forEach(file => {
           const isSelected = file === currentJSON ? ' class="selected"' : ''; 
           html += `<tr${isSelected}><td>${file}</td><td><button onclick="selectFile('${file}', this, '#json-table')">Select</button></td></tr>`;
        })
    } else {
        html += '<tr><td colspan="2">No Calibrated JSON is available.</td></tr>'; 
    }
    $("#json-table").html(html);
}

function updateFileTable(files, deselect) {

    let html = '<tr><th>File Name</th><th>Action</th></tr>';

    filterFiles(files).then((filteredFiles) => {
        if (filteredFiles && filteredFiles.length > 0) {
            filteredFiles.forEach(file => {
                const isSelected = file === currentFile ? ' class="selected"' : '';
                html += `<tr${isSelected}><td>${file}</td><td><button onclick="selectFile('${file}', this)">Select</button></td></tr>`;
            });
        } else {
            html += '<tr><td colspan="2">No CSV files found in the directory.</td></tr>';
        }
        $("#file-table").html(html);
        if (deselect) {
            currentFile = null;
            $("#file-table tr").removeClass("selected");
            updateFileDisplay(currentFile);
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
        mode: currentMeasurementMode
    }, function(response) {
        callback(response.json, response.path);
    })
}