let statusCheckInterval = null;
const STATUS_CHECK_INTERVAL = 2000; // Check every 2 seconds

function checkScriptStatus() {
    const logDisplay = document.getElementById('log-display');
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
                            logDisplay.insertAdjacentText('beforeend', `Error: ${response.message}\n`);
                        }
                        else console.log("Script is not running");
                        resetUIAfterError();
                    } else {
                        logDisplay.insertAdjacentText('beforeend', 'Script completed successfully\n');
                        resetUIAfterCompletion();
                    }
                    resolve(false); // Script is not running
                } else if (response.status === 'resending') {
                    AppState.scriptRunning = true;
                    logDisplay.insertAdjacentText('beforeend', `${response.message}\n`);
                    resolve(true); // Keep polling
                } else {
                    AppState.scriptRunning = true;
                    resolve(true); // Script is running
                }
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.log("Status check error:", textStatus, errorThrown);
                logDisplay.insertAdjacentText('beforeend', 'Error checking script status\n');
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

function resetUI({ goToEnabled }) {
    const saveSameDir = document.getElementById('save-same-dir');
    const infTimeout = document.getElementById('inf-timeout');

    if (!saveSameDir.checked) {
    document.getElementById('base-dir').disabled = false;
    }

    const baseEnabled = ['base-name', 'run-script-btn', 'inf-timeout', 'interval', 'interval-unit'];
    baseEnabled.forEach(id => (document.getElementById(id).disabled = false));

    document.getElementById('terminate-script-btn').disabled = true;
    document.getElementById('go-to-btn').disabled = !goToEnabled;

    document.getElementById('run-script-btn').classList.add('blinking');
    document.getElementById('terminate-script-btn').classList.remove('blinking');
    document.getElementById('go-to-btn').classList.toggle('blinking', false);

    const timeoutDisabled = infTimeout.checked;
    document.getElementById('timeout').disabled = timeoutDisabled;
    document.getElementById('timeout-unit').disabled = timeoutDisabled;

    modeButtons.forEach(button => (button.disabled = false));
}

function resetUIAfterError() {
    resetUI({ goToEnabled: false });
}

function resetUIAfterCompletion() {
    resetUI({ goToEnabled: true });     
}

// Main script runner
async function runScript() {
    if (!validateFileName("base-name") || !validatePathName("base-dir") || !validateTimeoutInterval()) return;

    const baseDir = $id("base-dir").value.trim();
    const baseName = $id("base-name").value.trim();
    const timeoutEl = $id("timeout");
    const intervalEl = $id("interval");
    const infTimeout = $id("inf-timeout").checked;

    AppState.processedHidPath = baseDir;
    clearStatusCheck();

    blinkingItem("log-display", 3000);

    // Disable inputs
    $disable(["base-dir", "base-name", "run-script-btn", "inf-timeout", "timeout", "timeout-unit", "interval", "interval-unit"]);
    $toggleClass("run-script-btn", "blinking", false);
    modeButtons.forEach(btn => btn.disabled = true);

    const timeoutValue = timeoutEl.value.trim();
    const intervalValue = intervalEl.value.trim();
    const payload = {
        base_dir: baseDir,
        base_name: baseName,
        inf_checked: infTimeout,
        timeout_sec: timeoutValue ? parseFloat(timeoutValue) * getTimeUnitMultiplier($id("timeout-unit").value) : null,
        interval_sec: intervalValue ? parseFloat(intervalValue) * getTimeUnitMultiplier($id("interval-unit").value) : null
    };

    try {
        const res = await fetch("/run_script", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const response = await res.json();

        if (response.status === "success") {
            AppState.scriptRunning = true;
            $disable(["terminate-script-btn"], false);
            $disable(["go-to-btn"], false);
            $toggleClass("go-to-btn", "blinking", true);
            $text("log-display", "Script started...\n");
            // bindButtonToString("#go-to-btn", baseDir, false);
            statusCheckInterval = setInterval(checkScriptStatus, STATUS_CHECK_INTERVAL);
        } else if (response.status === "device_not_found") {
            handleDeviceNotFound(response);
        } else {
            handleOtherError(response);
        }
    } catch (err) {
        console.error("runScript error:", err);
        handleAjaxError("Network error", err);
    }
}

// --- Error handling helpers ---
function handleDeviceNotFound(response) {
    console.warn("Device not found:", response);
    AppState.scriptRunning = false;
    $text("log-display", `Error: ${response.message}\n`);
    resetUIAfterError();
}

function handleOtherError(response) {
    $text("log-display", `Error: ${response.message}\n`);
    resetUIAfterError();
}

function handleAjaxError(textStatus, errorThrown) {
    console.error("AJAX error:", textStatus, errorThrown);
    $text("log-display", "Error: Failed to start script\n");
    $append("log-display", "Terminating the script\n");
    AppState.scriptRunning = false;
    resetUIAfterError();
}

// --- Terminate script ---
async function terminateScript() {
    try {
        const res = await fetch("/terminate_script", { method: "POST", headers: { "Content-Type": "application/json" } });
        const response = await res.json();

        if (response.status === "success") {
            handleScriptTermination("Script terminated.\n");
        } else {
            $append("log-display", `Error: ${response.message}\n`);
            handleScriptTermination("");
        }
    } catch (err) {
        console.error("terminateScript error:", err);
        $append("log-display", `Error: Failed to terminate script, error: ${err}\n`);
        handleScriptTermination("");
    } finally {
        clearLogs();
        clearStatusCheck();
    }
}

function handleScriptTermination(message) {
    AppState.scriptRunning = false;
    $text("log-display", message);
    $disable(["run-script-btn"], false);
    $toggleClass("run-script-btn", "blinking", true);
    $disable(["terminate-script-btn", "go-to-btn"]);
    ["terminate-script-btn", "go-to-btn"].forEach(id => $toggleClass(id, "blinking", false));
    if (!document.getElementById("save-same-dir").checked) $id("base-dir").disabled = false;
    ["base-name", "inf-timeout", "interval", "interval-unit"].forEach(id => $id(id).disabled = false);
    const timeoutDisabled = $id("inf-timeout").checked;
    $id("timeout").disabled = timeoutDisabled;
    $id("timeout-unit").disabled = timeoutDisabled;
}

// --- Fetch logs ---
async function fetchLogs() {
    try {
        const res = await fetch("/get_logs");
        const response = await res.json();
        if (response.status === "success") {
            const logs = response.logs;
            $text("log-display", logs);
            if (/PyBadge not found/.test(logs)) showTerminationNotice("PyBadge not found. Please check the connection.", "error");
            else if (/Failed to find input endpoint/.test(logs)) showTerminationNotice("Failed to find input endpoint. Please verify USB connection.", "error");
            else if (/SESSION TIMEOUT/.test(logs)) showTerminationNotice("Session ended due to timeout.", "info");
        }
    } catch (err) {
        console.error("fetchLogs error:", err);
        $append("log-display", "Error: Failed to fetch logs\n");
    }
}

// --- Clear logs ---
async function clearLogs() {
    try {
        const res = await fetch("/clear_logs", { method: "POST", headers: { "Content-Type": "application/json" } });
        const response = await res.json();
        if (response.status === "success") {
            $text("log-display", "");
        } else {
            $append("log-display", `Error: Failed to clear logs - ${response.message}\n`);
        }
    } catch (err) {
        console.error("clearLogs error:", err);
        $append("log-display", `Error: Failed to clear logs - ${err}\n`);
    }
}

// --- Termination notice ---
function showTerminationNotice(message, iconType) {
    terminateScript();

    const baseOpts = {
        title: iconType === "info" ? "Reading Stopped" : "Error!",
        text: message,
        icon: iconType,
        background: "#f9f9f9",
        color: "#333",
        showConfirmButton: iconType !== "info",
        confirmButtonText: "OK",
        timer: iconType === "info" ? 4000 : undefined,
        timerProgressBar: iconType === "info"
    };

    if (iconType === "info" && $id("notify-me").checked) {
        new Audio("../static/done.mp3").play().catch(err => console.warn("Audio play blocked:", err));
        Swal.fire(baseOpts);
    } 
    // else {
    //     Swal.fire(baseOpts);
    // }
}