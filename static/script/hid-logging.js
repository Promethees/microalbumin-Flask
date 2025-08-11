let statusCheckInterval = null;
const STATUS_CHECK_INTERVAL = 2000; // Check every 2 seconds

function checkScriptStatus() {
    return new Promise((resolve) => {
        $.ajax({
            url: '/check_status',
            type: 'GET',
            success: function(response) {
                if (response.status === 'device_not_found' || response.status === 'failure' || response.status === 'success' || response.status === 'not_running') {
                    clearStatusCheck();
                    AppState.scriptRunning = false;
                    if (response.status !== 'success') {
                        if (response.status !== 'not_running') {
                            $("#log-display").append(`Error: ${response.message}\n`);
                        }
                        else console.log("Script is not running");
                        resetUIAfterError();
                    } else {
                        $("#log-display").append("Script completed successfully\n");
                        resetUIAfterCompletion();
                    }
                    resolve(false); // Script is not running
                } else {
                    AppState.scriptRunning = true;
                    resolve(true); // Script is running
                }
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.log("Status check error:", textStatus, errorThrown);
                $("#log-display").append("Error checking script status\n");
                AppState.scriptRunning = false;
                resolve(false); // Assume not running on error
            }
        });
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
    $("#run-script-btn").addClass('blinking');
    $("#terminate-script-btn").prop('disabled', true);
    $("#go-to-btn").prop('disabled', true);
    $("#terminate-script-btn").removeClass('blinking');
    $("#go-to-btn").removeClass('blinking');
    $("#inf-timeout").prop('disabled', false);
    $("#timeout").prop('disabled', $("#inf-timeout").is(':checked'));
    $("#timeout-unit").prop('disabled', $("#inf-timeout").is(':checked'));
    $("#interval").prop('disabled', false);
    $("#interval-unit").prop('disabled', false);
}

function resetUIAfterCompletion() {
    $("#base-dir").prop('disabled', false);
    $("#base-name").prop('disabled', false);
    $("#run-script-btn").prop('disabled', false);
    $("#run-script-btn").addClass('blinking');
    $("#terminate-script-btn").prop('disabled', true);
    $("#go-to-btn").prop('disabled', false);
    $("#go-to-btn").removeClass('blinking');
    $("#inf-timeout").prop('disabled', false);
    $("#timeout").prop('disabled', $("#inf-timeout").is(':checked'));
    $("#timeout-unit").prop('disabled', $("#inf-timeout").is(':checked'));
    $("#interval").prop('disabled', false);
    $("#interval-unit").prop('disabled', false);
}

// Modified runScript function
function runScript() {
    const isValidFileName = validateFileName("base-name");
    const isValidPathName = validatePathName("base-dir");
    const isValidTimeoutInterval = validateTimeoutInterval();
    const timeoutInput = document.getElementById('timeout');
    const timeoutUnit = document.getElementById('timeout-unit').value;
    const intervalInput = document.getElementById('interval');
    const intervalUnit = document.getElementById('interval-unit').value;
    if (!isValidFileName || !isValidPathName || !isValidTimeoutInterval) {
        return; // Stop if validation fails
    }

    AppState.processedHidPath = $("#base-dir").val();
    const baseName = $("#base-name").val();
    
    // Clear any existing status checks
    clearStatusCheck();

    // Blink the log display section
    blinkingItem("#log-display", 3000);
    
    // Disable UI elements
    $("#base-dir").prop('disabled', true);
    $("#base-name").prop('disabled', true);
    $("#run-script-btn").prop('disabled', true);
    $("#run-script-btn").removeClass('blinking');
    $("#inf-timeout").prop('disabled', true);
    $("#timeout").prop('disabled', true);
    $("#timeout-unit").prop('disabled', true);
    $("#interval").prop('disabled', true);
    $("#interval-unit").prop('disabled', true);

    const timeoutValue = timeoutInput.value.trim();
    const intervalValue = intervalInput.value.trim();
    
    $.ajax({
        url: '/run_script',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ 
            base_dir: AppState.processedHidPath, 
            base_name: baseName,
            inf_checked: document.getElementById('inf-timeout').checked,
            timeout_sec: timeoutValue ? parseFloat(timeoutValue) * getTimeUnitMultiplier(timeoutUnit) : null,
            interval_sec: intervalValue ?  parseFloat(intervalValue) * getTimeUnitMultiplier(intervalUnit): null}),
        success: function(response) {
            if (response.status === 'success') {
                AppState.scriptRunning = true;
                $("#terminate-script-btn").prop('disabled', false);
                $("#go-to-btn").prop('disabled', false);
                $("#go-to-btn").addClass('blinking');
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
                $("#run-script-btn").addClass('blinking');
                $("#terminate-script-btn").prop('disabled', true);
                $("#base-dir").prop('disabled', false);
                $("#base-name").prop('disabled', false);
                $("#log-display").append("Script terminated.\n");
                $("#inf-timeout").prop('disabled', false);
                $("#timeout").prop('disabled', $("#inf-timeout").is(':checked'));
                $("#timeout-unit").prop('disabled', $("#inf-timeout").is(':checked'));
                $("#interval").prop('disabled', false);
                $("#interval-unit").prop('disabled', false);
            } else {
                $("#log-display").append(`Error: ${response.message}\n`);
                if (response.message.includes('No process running')) {
                    AppState.scriptRunning = false;
                    $("#run-script-btn").prop('disabled', false);
                    $("#run-script-btn").addClass('blinking');
                    $("#terminate-script-btn").prop('disabled', true);
                    $("#base-dir").prop('disabled', false);
                    $("#base-name").prop('disabled', false);
                    $("#go-to-btn").prop('disabled', true);
                    $("#terminate-script-btn").removeClass('blinking');
                    $("#go-to-btn").removeClass('blinking');
                    $("#inf-timeout").prop('disabled', false);
                    $("#timeout").prop('disabled', $("#inf-timeout").is(':checked'));
                    $("#timeout-unit").prop('disabled', $("#inf-timeout").is(':checked'));
                    $("#interval").prop('disabled', false);
                    $("#interval-unit").prop('disabled', false);
                }
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            console.log("AJAX error:", textStatus, errorThrown);
            $("#log-display").append(`Error: Failed to terminate script, error: ${errorThrown}\n`);
            AppState.scriptRunning = false;
            $("#run-script-btn").prop('disabled', false);
            $("#run-script-btn").addClass('blinking');
            $("#terminate-script-btn", "#go-to-btn").prop('disabled', true);
            $("#terminate-script-btn").removeClass('blinking');
            $("#go-to-btn").removeClass('blinking');
            $("#base-dir").prop('disabled', false);
            $("#base-name").prop('disabled', false);
            $("#inf-timeout").prop('disabled', false);
            $("#timeout").prop('disabled', $("#inf-timeout").is(':checked'));
            $("#timeout-unit").prop('disabled', $("#inf-timeout").is(':checked'));
            $("#interval").prop('disabled', false);
            $("#interval-unit").prop('disabled', false);
        }
    });
}

function fetchLogs() {
    $.get('/get_logs', function(response) {
        if (response.status === 'success') {
            const logs = response.logs;
            $("#log-display").text(logs);

            // Check for specific termination patterns
            if (/PyBadge not found/.test(logs)) {
                showTerminationNotice("PyBadge not found. Please check the connection.", 'error');
            }
            else if (/Failed to find input endpoint/.test(logs)) {
                showTerminationNotice("Failed to find input endpoint. Please verify USB connection.", 'error');
            }
            else if (/SESSION TIMEOUT/.test(logs)) {
                showTerminationNotice("Session ended due to timeout.", 'info');
            }
        }
    }).fail(function(jqXHR, textStatus, errorThrown) {
        console.log("AJAX error:", textStatus, errorThrown);
        $("#log-display").append(`Error: Failed to fetch logs\n`);
    });
}

// Helper function to show popup & terminate script
function showTerminationNotice(message, iconType) {
    // Call terminateScript immediately
    terminateScript();
    clearLogs();
    if ($("#notify-me").is(":checked")) {
        // Show SweetAlert2 auto-close popup
        Swal.fire({
            title: 'Reading Stopped',
            text: message,
            icon: iconType,
            showConfirmButton: false,
            timer: 4000,
            timerProgressBar: true,
            background: '#f9f9f9',
            color: '#333'
        });
    }
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