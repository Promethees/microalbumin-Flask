let statusCheckInterval = null;
const STATUS_CHECK_INTERVAL = 2000; // Check every 2 seconds
let _terminationNoticeFired = false;

// --- Session timer state ---
let sessionStartTime = null;
let lastDataPointTime = null;
let sessionIntervalSec = null;
let sessionTimerHandle = null;
let _prevDataPointCount = 0;

function formatHMS(totalSeconds) {
    const s = Math.floor(totalSeconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const mm = String(m).padStart(2, '0');
    const ss = String(sec).padStart(2, '0');
    return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function tickSessionTimer() {
    if (!sessionStartTime) return;
    const now = Date.now();
    const elapsedSec = (now - sessionStartTime) / 1000;

    const elapsedEl = document.getElementById('session-elapsed');
    if (elapsedEl) elapsedEl.textContent = formatHMS(elapsedSec);

    const nextEl = document.getElementById('session-next');
    if (nextEl) {
        if (sessionIntervalSec && sessionIntervalSec > 0 && lastDataPointTime) {
            const sinceLastPoint = (now - lastDataPointTime) / 1000;
            const remaining = Math.max(0, sessionIntervalSec - sinceLastPoint);
            nextEl.textContent = formatHMS(remaining);
            nextEl.classList.toggle('urgent', remaining <= 10);
        } else {
            nextEl.textContent = '--:--';
            nextEl.classList.remove('urgent');
        }
    }
}

// Called when runScript succeeds — prepares state but keeps widget hidden
// until the first real data point arrives.
function startSessionTimer(intervalSec) {
    sessionIntervalSec = intervalSec || null;
    _prevDataPointCount = 0;
    sessionStartTime = null;
    lastDataPointTime = null;
    if (sessionTimerHandle) { clearInterval(sessionTimerHandle); sessionTimerHandle = null; }
}

// Called each time a new data point is detected in the log output.
function onNewDataPoint() {
    const now = Date.now();
    if (!sessionStartTime) {
        // First data point: reveal widget and start ticking.
        sessionStartTime = now;
        const timerEl = document.getElementById('session-timer');
        if (timerEl) timerEl.classList.remove('hidden');
        sessionTimerHandle = setInterval(tickSessionTimer, 1000);
    } else if (!sessionIntervalSec) {
        // Second data point with no configured interval: measure the device's
        // actual interval from the gap between point 1 and point 2.
        sessionIntervalSec = (now - sessionStartTime) / 1000;
    }
    lastDataPointTime = now;
    tickSessionTimer();
}

function stopSessionTimer() {
    if (sessionTimerHandle) {
        clearInterval(sessionTimerHandle);
        sessionTimerHandle = null;
    }
    sessionStartTime = null;
    lastDataPointTime = null;
    sessionIntervalSec = null;
    _prevDataPointCount = 0;
    const timerEl = document.getElementById('session-timer');
    if (timerEl) timerEl.classList.add('hidden');
    const elapsedEl = document.getElementById('session-elapsed');
    const nextEl = document.getElementById('session-next');
    if (elapsedEl) elapsedEl.textContent = '00:00:00';
    if (nextEl) { nextEl.textContent = '--:--'; nextEl.classList.remove('urgent'); }
}

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
    const infTimeout = document.getElementById('inf-timeout');

    // Re-enable subfolder selection controls
    document.querySelectorAll('input[name="hid-save-mode"]').forEach(r => (r.disabled = false));
    const existingSel = document.getElementById('hid-subfolder-select');
    if (existingSel) existingSel.disabled = false;
    const newInput = document.getElementById('hid-new-folder-name');
    if (newInput) newInput.disabled = false;

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
    stopSessionTimer();
    resetUI({ goToEnabled: false });
}

function resetUIAfterCompletion() {
    stopSessionTimer();
    resetUI({ goToEnabled: true });
    // Refresh folder picker so any newly-created subfolder is visible
    if (typeof loadDataFolders === 'function') loadDataFolders();
}

// HID save-mode toggle handlers
function onHidSaveModeChange() {
    const mode = document.querySelector('input[name="hid-save-mode"]:checked')?.value || 'existing';
    const existingRow = document.getElementById('hid-existing-row');
    const newRow = document.getElementById('hid-new-row');
    if (existingRow) existingRow.style.display = mode === 'existing' ? 'flex' : 'none';
    if (newRow) newRow.style.display = mode === 'new' ? 'flex' : 'none';
}

function onHidSubfolderChange(select) {
    AppState.processedHidPath = select.value ? getNativePath(DATA_ROOT, select.value) : DATA_ROOT;
}

// Main script runner
async function runScript() {
    if (!validateFileName("base-name") || !validateTimeoutInterval()) return;
    _terminationNoticeFired = false;

    const saveMode = document.querySelector('input[name="hid-save-mode"]:checked')?.value || 'existing';
    let subfolder = '';

    if (saveMode === 'existing') {
        subfolder = (document.getElementById('hid-subfolder-select') || {}).value || '';
    } else {
        if (!validateFileName("hid-new-folder-name")) return;
        subfolder = ($id("hid-new-folder-name").value || '').trim();
        if (!subfolder) {
            Swal.fire({ title: 'Name required', text: 'Please enter a name for the new subfolder.', icon: 'warning', confirmButtonText: 'OK' });
            return;
        }
        if (typeof isReservedDataFolderName === 'function' && isReservedDataFolderName(subfolder)) {
            Swal.fire({ title: 'Reserved name', text: `"${subfolder}" is a reserved folder name and cannot be used.`, icon: 'error', confirmButtonText: 'OK' });
            return;
        }
    }

    const baseName = $id("base-name").value.trim();
    const timeoutEl = $id("timeout");
    const intervalEl = $id("interval");
    const infTimeout = $id("inf-timeout").checked;

    AppState.processedHidPath = subfolder ? getNativePath(DATA_ROOT, subfolder) : DATA_ROOT;

    clearStatusCheck();
    blinkingItem("log-display", 3000);

    // Disable inputs while running
    document.querySelectorAll('input[name="hid-save-mode"]').forEach(r => (r.disabled = true));
    const existingSel = document.getElementById('hid-subfolder-select');
    if (existingSel) existingSel.disabled = true;
    const newInput = document.getElementById('hid-new-folder-name');
    if (newInput) newInput.disabled = true;
    $disable(["base-name", "run-script-btn", "inf-timeout", "timeout", "timeout-unit", "interval", "interval-unit"]);
    $toggleClass("run-script-btn", "blinking", false);
    modeButtons.forEach(btn => btn.disabled = true);

    const timeoutValue = timeoutEl.value.trim();
    const intervalValue = intervalEl.value.trim();
    const payload = {
        subfolder: subfolder,
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
            logEvent('hardware', 'start', { subfolder, base_name: baseName });
            AppState.scriptRunning = true;
            $disable(["terminate-script-btn"], false);
            $disable(["go-to-btn"], false);
            $toggleClass("go-to-btn", "blinking", true);
            $text("log-display", "Script started...\n");
            if (saveMode === 'new' && typeof loadDataFolders === 'function') loadDataFolders();
            startSessionTimer(payload.interval_sec);
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
            logEvent('hardware', 'stop');
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
    stopSessionTimer();
    $text("log-display", message);
    $disable(["run-script-btn"], false);
    $toggleClass("run-script-btn", "blinking", true);
    $disable(["terminate-script-btn", "go-to-btn"]);
    ["terminate-script-btn", "go-to-btn"].forEach(id => $toggleClass(id, "blinking", false));
    // Re-enable subfolder selection
    document.querySelectorAll('input[name="hid-save-mode"]').forEach(r => (r.disabled = false));
    const existingSel = document.getElementById('hid-subfolder-select');
    if (existingSel) existingSel.disabled = false;
    const newInput = document.getElementById('hid-new-folder-name');
    if (newInput) newInput.disabled = false;
    ["base-name", "inf-timeout", "interval", "interval-unit"].forEach(id => $id(id).disabled = false);
    const timeoutDisabled = $id("inf-timeout").checked;
    $id("timeout").disabled = timeoutDisabled;
    $id("timeout-unit").disabled = timeoutDisabled;
    modeButtons.forEach(btn => btn.disabled = false);
}

// --- Fetch logs ---
async function fetchLogs() {
    try {
        const res = await fetch("/get_logs");
        const response = await res.json();
        if (response.status === "success") {
            const logs = response.logs;
            $text("log-display", logs);

            // Detect newly recorded data points by counting log entries
            const dpCount = (logs.match(/Received: Timestamp:/g) || []).length;
            if (dpCount > _prevDataPointCount) {
                _prevDataPointCount = dpCount;
                onNewDataPoint();
            }

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
    if (_terminationNoticeFired) return;
    _terminationNoticeFired = true;
    AppState.scriptRunning = false;
    stopSessionTimer();
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