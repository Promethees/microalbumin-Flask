let statusCheckInterval = null;
const STATUS_CHECK_INTERVAL = 2000; // Check every 2 seconds

function checkScriptStatus() {
    $.ajax({
        url: '/check_status',
        type: 'GET',
        success: function(response) {
            if (response.status === 'device_not_found') {
                // Device error detected
                clearStatusCheck();
                AppState.scriptRunning = false;
                $("#log-display").append(`Error: ${response.message}\n`);
                resetUIAfterError();
            }
            else if (response.status === 'failure') {
                // Other error detected
                clearStatusCheck();
                AppState.scriptRunning = false;
                $("#log-display").append(`Error: ${response.message}\n`);
                resetUIAfterError();
            }
            else if (response.status === 'success') {
                // Script completed successfully
                clearStatusCheck();
                AppState.scriptRunning = false;
                $("#log-display").append("Script completed successfully\n");
                resetUIAfterCompletion();
            }
            else if (response.status === 'not_running') {
                // Script isn't running (unexpected state)
                clearStatusCheck();
                AppState.scriptRunning = false;
                $("#log-display").append("Script is not running\n");
                resetUIAfterError();
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            console.log("Status check error:", textStatus, errorThrown);
            $("#log-display").append("Error checking script status\n");
        }
    });
}

function clearStatusCheck() {
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
        statusCheckInterval = null;
    }
}

function resetUIAfterError() {
    $("#base-dir").prop('disabled', false);
    $("#base-name").prop('disabled', false);
    $("#run-script-btn").prop('disabled', false);
    $("#terminate-script-btn").prop('disabled', true);
    $("#go-to-btn").prop('disabled', true);
}

function resetUIAfterCompletion() {
    $("#base-dir").prop('disabled', false);
    $("#base-name").prop('disabled', false);
    $("#run-script-btn").prop('disabled', false);
    $("#terminate-script-btn").prop('disabled', true);
    $("#go-to-btn").prop('disabled', false);
}

// Modified runScript function
function runScript() {
    AppState.processedHidPath = $("#base-dir").val();
    const baseName = $("#base-name").val();
    
    // Clear any existing status checks
    clearStatusCheck();
    
    // Disable UI elements
    $("#base-dir").prop('disabled', true);
    $("#base-name").prop('disabled', true);
    $("#run-script-btn").prop('disabled', true);
    
    $.ajax({
        url: '/run_script',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ base_dir: AppState.processedHidPath, base_name: baseName }),
        success: function(response) {
            if (response.status === 'success') {
                AppState.scriptRunning = true;
                $("#terminate-script-btn").prop('disabled', false);
                $("#go-to-btn").prop('disabled', false);
                $("#log-display").text("Script started...\n");
                bindButtonToString("#go-to-btn", AppState.processedHidPath, false);
                
                // Start periodic status checks
                statusCheckInterval = setInterval(checkScriptStatus, STATUS_CHECK_INTERVAL);
            } 
            else if (response.status === 'device_not_found') {
                handleDeviceNotFound(response);
            } 
            else {
                handleOtherError(response);
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            handleAjaxError(textStatus, errorThrown);
        }
    });
}

// Helper functions for error handling
function handleDeviceNotFound(response) {
    console.log("Device not found in response:", response);
    AppState.scriptRunning = false;
    $("#log-display").text(`Error: ${response.message}\n`);
    resetUIAfterError();
}

function handleOtherError(response) {
    $("#log-display").text(`Error: ${response.message}\n`);
    resetUIAfterError();
}

function handleAjaxError(textStatus, errorThrown) {
    console.log("AJAX error:", textStatus, errorThrown);
    $("#log-display").text(`Error: Failed to start script\n`);
    $("#log-display").append(`Terminating the script\n`);
    AppState.scriptRunning = false;
    resetUIAfterError();
}

function terminateScript() {
    $.ajax({
        url: '/terminate_script',
        type: 'POST',
        contentType: 'application/json',
        success: function(response) {
            console.log("Terminate script response:", response);
            if (response.status === 'success') {
                AppState.scriptRunning = false;
                $("#run-script-btn").prop('disabled', false);
                $("#terminate-script-btn").prop('disabled', true);
                $("#base-dir").prop('disabled', false);
                $("#base-name").prop('disabled', false);
                $("#log-display").append("Script terminated.\n");
            } else {
                $("#log-display").append(`Error: ${response.message}\n`);
                if (response.message.includes('No process running')) {
                    AppState.scriptRunning = false;
                    $("#run-script-btn").prop('disabled', false);
                    $("#terminate-script-btn").prop('disabled', true);
                    $("#base-dir").prop('disabled', false);
                    $("#base-name").prop('disabled', false);
                    $("#go-to-btn").prop('disabled', true);
                }
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            console.log("AJAX error:", textStatus, errorThrown);
            $("#log-display").append(`Error: Failed to terminate script, error: ${errorThrown}\n`);
            AppState.scriptRunning = false;
            $("#run-script-btn").prop('disabled', false);
            $("#terminate-script-btn", "#go-to-btn").prop('disabled', true);
            $("#base-dir").prop('disabled', false);
            $("#base-name").prop('disabled', false);
        }
    });
}

function fetchLogs() {
    $.get('/get_logs', function(response) {
        if (response.status === 'success') {
            $("#log-display").text(response.logs);
        }
    }).fail(function(jqXHR, textStatus, errorThrown) {
        console.log("AJAX error:", textStatus, errorThrown);
        $("#log-display").append(`Error: Failed to fetch logs\n`);
    });
}

function clearLogs() {
    $.ajax({
        url: '/clear_logs',
        type: 'POST',
        contentType: 'application/json',
        success: function(response) {
            if (response.status === 'success') {
                $("#log-display").text("");
            } else {
                $("#log-display").append(`Error: Failed to clear logs - ${response.message}\n`);
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            console.log("AJAX error:", textStatus, errorThrown);
            $("#log-display").append(`Error: Failed to clear logs - ${textStatus}\n`);
        }
    });
}