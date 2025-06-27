let blankedChart = null;
let nonBlankedChart = null;
let myChart = null;
let scriptRunning = false;
let currentMeasurementMode = "kinetics";
let currentFile = null;
let currentJSON = null;
let currentJSONcontent = null;

const platform = navigator.platform.toLowerCase();
const delimiter = platform.includes("window") ? "\\" : "/";
let refCalPoint = null;
let analysis = null;
let json_msg = 'When fit_type: \n';
let globalEstimatedValue = null;
let currExpTimePoint = null;
let prevDropdownEntries = null;
let exp_json_content = null;

const chartInstances = {};

json_msg += '  + linear: concentration = quantity_json[0]*quantity_value + quantity_json[1]\n';
json_msg += '  + polynomial: concentration = quantity_json[0]*quantity_value^2 + quantity_json[1]*quantity_value + quantity_json[2]\n';
json_msg += '  + logarit: concentration = quantity_json[0]*loge(quantity_json[1]*quantity_value)\n';

$("#point-json-exp-section").addClass("hidden");
$("#cal-json-exp-section").addClass("hidden");
$("#derived-concentration-section").addClass("hidden");
$("#blank-derived-concentration-section").addClass("hidden");
$("#non-blank-derived-concentration-section").addClass("hidden");
$("#set-exp-point-section").addClass("hidden");
$("#select-regress-algo").addClass("hidden");
$("#select-time-point").addClass("hidden");
$("#export-coef").addClass("hidden");
$("#select-exp-blank-type-cal").addClass("hidden");

const input = document.getElementById("window-size");

input.addEventListener("keydown", function (e) {
    // Allow: ArrowUp, ArrowDown, Tab, etc.
    if (
      ["ArrowUp", "ArrowDown", "Tab"].includes(e.key)
    ) return;

    // Prevent all other key presses
    e.preventDefault();
  });

$(document).ready(function() {
    $.get('/get_parents', function(parentResponse) {
        console.log("Parent directory:", parentResponse.parent);
        let parentHtml = parentResponse.parent ? 
            (parentResponse.parent.split(delimiter).pop() ? 
                `<div onclick="updateDirectory('${parentResponse.parent}', true)">${parentResponse.parent.split(delimiter).pop()}</div>` : 
                '<div>No parent directory</div>') : 
            '<div>No parent directory</div>';
        $("#parent-dir").html(parentHtml);

        $.get('/get_children', function(childResponse) {
            console.log("Child directories:", childResponse.children);
            let childHtml = childResponse.children.length > 0 ? 
                childResponse.children.map(dir => 
                    `<div onclick="updateDirectory('${dir}', true)">${dir.split(delimiter).pop()}</div>`
                ).join('') : 
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

    // Poll logs every 2 seconds if script is running
    setInterval(function() {
        if (scriptRunning) {
            fetchLogs();
        }
    }, 2000);

    // Periodically update file table every 0.5 seconds
    setInterval(function() {
        const currentDir = $("#directory").val();
        if (currentDir) {
            updateDirectory(currentDir, false);
        }
    }, 500);

    $("#time-unit").on("change", function() {
        const currTimeUnit = $(this).val().slice(0, -1);
        $("#cal-time-unit").text(currTimeUnit);
    });

    // Initialize measurement method listener
    $("#measurement-mode").on("change", function() {
        const mode = $(this).val();
        currentMeasurementMode = mode;
        const currentDir = $("#directory").val();
        if (currentDir) {
            updateDirectory(currentDir, true);
        }
        currentJSON = null;
        currentJSONcontent = null;
        $("#json-display").text("");
        
        if (mode === "kinetics") {
            $("#window-size-section").removeClass("hidden");
            $("#select-quantity-section").removeClass("hidden");
            $("#point-json-exp-section").addClass("hidden");
            $("#cal-json-sel-section").removeClass("hidden");
            $("#kinetics-lines").removeClass("hidden");
            $("#cal-json-exp-section").addClass("hidden");
            $("#range-value").val("1000").prop("disabled", false);
            $("#json-display").removeClass("hidden");
            $("#export-analysis").removeClass("hidden");
            $("#set-exp-point-section").addClass("hidden");
            $("#select-exp-blank-type").removeClass("hidden");
            $("#range-display").removeClass("hidden");
            $("#concentration-reader-section").removeClass("hidden");
            $("#analysis-info").removeClass("hidden");
            $("#full-display-section").removeClass("hidden");
            $("#select-time-point").addClass("hidden");
            $("#select-regress-algo").addClass("hidden");
            $("#export-coef").addClass("hidden");
            $("#log-hid-data").removeClass("hidden");
            $("#select-exp-blank-type-meas").removeClass("hidden");
            $("#select-exp-blank-type-cal").addClass("hidden");
        } else if (mode === "point") {
            $("#window-size-section").addClass("hidden");
            $("#select-quantity-section").addClass("hidden"); 
            $("#point-json-exp-section").addClass("hidden");
            $("#cal-json-sel-section").removeClass("hidden");
            $("#kinetics-lines").addClass("hidden");
            $("#cal-json-exp-section").addClass("hidden");
            $("#range-value").val("1000").prop("disabled", false);
            $("#json-display").removeClass("hidden");
            $("#export-analysis").removeClass("hidden");
            $("#set-exp-point-section").removeClass("hidden");
            $("#select-exp-blank-type").removeClass("hidden");
            $("#range-display").removeClass("hidden");
            $("#concentration-reader-section").removeClass("hidden");
            $("#analysis-info").removeClass("hidden");
            $("#full-display-section").removeClass("hidden");
            $("#select-time-point").addClass("hidden");
            $("#select-regress-algo").addClass("hidden");
            $("#export-coef").addClass("hidden");
            $("#log-hid-data").removeClass("hidden");
            $("#select-exp-blank-type-meas").removeClass("hidden");
            $("#select-exp-blank-type-cal").addClass("hidden");
        } else {
            $("#window-size-section").addClass("hidden");
            if ($("#cal-mode-select").val() === "kinetics") {
                $("#select-quantity-section").removeClass("hidden");
                $("#select-time-point").addClass("hidden");
            } else {
                $("#select-quantity-section").addClass("hidden");
                $("#select-time-point").removeClass("hidden");
            }
            $("#point-json-exp-section").addClass("hidden");
            $("#cal-json-sel-section").addClass("hidden");
            $("#kinetics-lines").addClass("hidden");
            $("#cal-json-exp-section").removeClass("hidden");
            $("#range-value").val("").prop("disabled", true).attr("placeholder", "Disabled in Calibration mode");
            $("#json-display").addClass("hidden");
            $("#export-analysis").addClass("hidden");
            $("#select-exp-blank-type").removeClass("hidden");
            $("#range-display").addClass("hidden");
            $("#concentration-reader-section").addClass("hidden");
            $("#full-display-section").addClass("hidden");
            $("#select-regress-algo").removeClass("hidden");
            $("#analysis-info").removeClass("hidden");
            $("#export-coef").removeClass("hidden");
            $("#log-hid-data").addClass("hidden");
            $("#select-exp-blank-type-meas").addClass("hidden");
            $("#select-exp-blank-type-cal").removeClass("hidden");
        }
        
        if (currentFile) {
            if (currentMeasurementMode !== "calibrate") {
                let range = $("#range-value").val();
                let unit = $("#time-unit").val();
                let window_size = $("#window_size").val();
                fetchData(range, unit, window_size, currentFile);
            } else {
                fetchData(null, null, null, currentFile, null);
            }
        } 
        updateDirectory($("#directory").val(), true);
    });

    $("#cal-json-exp-section").on("change", function() {
        currentFile = null;
    });

    $("#cal-mode-select").on("change", function() {
        if ($("#cal-mode-select").val() === "kinetics") {
            $("#select-quantity-section").removeClass("hidden");
            $("#select-time-point").addClass("hidden");
        } else {
            $("#select-quantity-section").addClass("hidden");
            $("#select-time-point").removeClass("hidden");
        }
    });

    if (currentFile) {
        $("#data-display-section").removeClass("hidden");
    } else {
        $('#data-display-section').addClass("hidden");
    }
});

function updateDirectory(path, deselect) {
    // console.log("Sending path to server:", path);
    $.post('/browse', {path: path}, function(response) {
        if (response.status === 'success') {
            $("#directory").val(response.path);
            $("#error-message").hide();
            // console.log("Response files in update directory is: ". response.files);
            updateFileTable(response.files, deselect);
            if (deselect) {
                deselectFile();
            }
        } else {
            $("#error-message").text(response.message).show();
        }
    }).fail(function(jqXHR, textStatus, errorThrown) {
        console.log("AJAX error:", textStatus, errorThrown);
        $("#error-message").text("Error updating directory").show();
    });
    $.get('/get_json_cal', {mode: currentMeasurementMode}, function(response) {
        updateJSONTable(response.files);
    })
}

// Refresh data display according to range, unit, window size set
setInterval(function() {
    if (currentFile) {
        if (currentMeasurementMode !== "calibrate") {
            let range = $("#range-value").val();
            let unit = $("#time-unit").val();
            let window_size = $("#window-size").val();
            fetchData(range, unit, window_size, currentFile, currentJSONcontent);
            $("#data-display-section").removeClass("hidden");
        } else {
            fetchData(null, null, null, currentFile, null);
            $("#data-display-section").removeClass("hidden");
        }
    } else $("#data-display-section").addClass("hidden");
    if (!currentJSON) {
        $("#derived-concentration-section").addClass("hidden");
        $("#blank-derived-concentration-section").addClass("hidden");
        $("#non-blank-derived-concentration-section").addClass("hidden");
    }
}, 500);