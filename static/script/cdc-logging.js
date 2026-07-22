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
                        resetUIAfterError();
                    } else {
                        logDisplay.insertAdjacentText('beforeend', 'Script completed successfully\n');
                        // Backend reports why it ended (timeout / device stop) so
                        // the announcement matches the cause.
                        resetUIAfterCompletion(response.message);
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
                console.error("Status check error:", textStatus, errorThrown);
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
    document.querySelectorAll('input[name="cdc-save-mode"]').forEach(r => (r.disabled = false));
    const existingSel = document.getElementById('cdc-subfolder-select');
    if (existingSel) existingSel.disabled = false;
    const newInput = document.getElementById('cdc-new-folder-name');
    if (newInput) newInput.disabled = false;

    const baseEnabled = ['base-name', 'run-script-btn', 'inf-timeout', 'interval', 'interval-unit', 'cdc-axis-turn'];
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

function resetUIAfterCompletion(message) {
    stopSessionTimer();
    resetUI({ goToEnabled: true });
    // Refresh folder picker so any newly-created subfolder is visible
    if (typeof loadDataFolders === 'function') loadDataFolders();
    // Authoritative clean-completion path: notify here so the "done" chime/popup
    // no longer depends on the log poll winning the race against this status poll.
    // `message` is the backend's reason-aware text (timeout vs device stop);
    // fall back to the timeout wording if it's somehow absent.
    fireDoneNotification(message || "Session ended due to timeout.");
}

// CDC save-mode toggle handlers
function onCdcSaveModeChange() {
    const mode = document.querySelector('input[name="cdc-save-mode"]:checked')?.value || 'existing';
    const existingRow = document.getElementById('cdc-existing-row');
    const newRow = document.getElementById('cdc-new-row');
    if (existingRow) existingRow.style.display = mode === 'existing' ? 'flex' : 'none';
    if (newRow) newRow.style.display = mode === 'new' ? 'flex' : 'none';
}

function onCdcSubfolderChange(select) {
    AppState.processedCdcPath = select.value ? getNativePath(DATA_ROOT, select.value) : DATA_ROOT;
}

// Turn/Timestamp axis toggle — persists as the user's default (cdc_axis) so the
// next session opens with the same choice.
function onCdcAxisChange() {
    const useTurn = !!document.getElementById('cdc-axis-turn')?.checked;
    const value = useTurn ? 'turn' : 'time';
    if (typeof USER_SETTINGS !== 'undefined') USER_SETTINGS.cdc_axis = value;
    if (typeof saveUserSetting === 'function') saveUserSetting('cdc_axis', value);
}

// Main script runner
async function runScript() {
    if (!validateFileName("base-name") || !validateTimeoutInterval()) return;
    _terminationNoticeFired = false;

    const saveMode = document.querySelector('input[name="cdc-save-mode"]:checked')?.value || 'existing';
    let subfolder = '';

    if (saveMode === 'existing') {
        subfolder = (document.getElementById('cdc-subfolder-select') || {}).value || '';
    } else {
        if (!validateFileName("cdc-new-folder-name")) return;
        subfolder = ($id("cdc-new-folder-name").value || '').trim();
        if (!subfolder) {
            Swal.fire({ title: t('cdc.name_required.title', 'Name required'), text: t('cdc.name_required.text', 'Please enter a name for the new subfolder.'), icon: 'warning', confirmButtonText: t('common.ok', 'OK') });
            return;
        }
        if (typeof isReservedDataFolderName === 'function' && isReservedDataFolderName(subfolder)) {
            Swal.fire({ title: t('cdc.reserved_name.title', 'Reserved name'), text: `"${subfolder}" ${t('cdc.reserved_name.suffix', 'is a reserved folder name and cannot be used.')}`, icon: 'error', confirmButtonText: t('common.ok', 'OK') });
            return;
        }
    }

    const baseName = $id("base-name").value.trim();
    const timeoutEl = $id("timeout");
    const intervalEl = $id("interval");
    const infTimeout = $id("inf-timeout").checked;

    AppState.processedCdcPath = subfolder ? getNativePath(DATA_ROOT, subfolder) : DATA_ROOT;

    clearStatusCheck();
    blinkingItem("log-display", 3000);

    // Disable inputs while running
    document.querySelectorAll('input[name="cdc-save-mode"]').forEach(r => (r.disabled = true));
    const existingSel = document.getElementById('cdc-subfolder-select');
    if (existingSel) existingSel.disabled = true;
    const newInput = document.getElementById('cdc-new-folder-name');
    if (newInput) newInput.disabled = true;
    $disable(["base-name", "run-script-btn", "inf-timeout", "timeout", "timeout-unit", "interval", "interval-unit", "cdc-axis-turn"]);
    $toggleClass("run-script-btn", "blinking", false);
    modeButtons.forEach(btn => btn.disabled = true);

    const timeoutValue = timeoutEl.value.trim();
    const intervalValue = intervalEl.value.trim();
    const useTurn = !!document.getElementById('cdc-axis-turn')?.checked;
    const payload = {
        subfolder: subfolder,
        base_name: baseName,
        inf_checked: infTimeout,
        timeout_sec: timeoutValue ? parseFloat(timeoutValue) * getTimeUnitMultiplier($id("timeout-unit").value) : null,
        interval_sec: intervalValue ? parseFloat(intervalValue) * getTimeUnitMultiplier($id("interval-unit").value) : null,
        axis: useTurn ? 'turn' : 'time'
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
    document.querySelectorAll('input[name="cdc-save-mode"]').forEach(r => (r.disabled = false));
    const existingSel = document.getElementById('cdc-subfolder-select');
    if (existingSel) existingSel.disabled = false;
    const newInput = document.getElementById('cdc-new-folder-name');
    if (newInput) newInput.disabled = false;
    ["base-name", "inf-timeout", "interval", "interval-unit", "cdc-axis-turn"].forEach(id => $id(id).disabled = false);
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
            const dpCount = (logs.match(/Received: (?:Timestamp|Turn):/g) || []).length;
            if (dpCount > _prevDataPointCount) {
                _prevDataPointCount = dpCount;
                onNewDataPoint();
            }

            if (/PyBadge not found/.test(logs)) showTerminationNotice(t('cdc.err_pybadge_not_found', "PyBadge not found. Please check the connection."), "error");
            else if (/Failed to find input endpoint/.test(logs)) showTerminationNotice(t('cdc.err_no_endpoint', "Failed to find input endpoint. Please verify USB connection."), "error");
            else if (/SESSION STOPPED/.test(logs)) showTerminationNotice(t('cdc.session_stopped', "Session stopped manually on the device."), "info");
            else if (/SESSION TIMEOUT/.test(logs)) showTerminationNotice(t('cdc.session_timeout', "Session ended due to timeout."), "info");
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

// --- Completion notice ---
// Plays the completion chime + shows the "Reading Stopped" popup, honouring the
// "Notify me when Done" checkbox. Guarded by _terminationNoticeFired so it fires
// at most once per run, regardless of which poller detects the end first
// (fetchLogs spotting "SESSION TIMEOUT" vs checkScriptStatus seeing the process
// exit). Without this single source of truth the notify only fired when the log
// poll happened to win the race against the status poll.
function fireDoneNotification(message) {
    if (_terminationNoticeFired) return;
    _terminationNoticeFired = true;
    const notifyEl = $id("notify-me");
    if (!notifyEl || !notifyEl.checked) return;
    new Audio("../static/done.mp3").play().catch(err => console.warn("Audio play blocked:", err));
    Swal.fire({
        title: t('cdc.reading_stopped', "Reading Stopped"),
        text: message,
        icon: "info",
        background: "#f9f9f9",
        color: "#333",
        showConfirmButton: false,
        timer: 4000,
        timerProgressBar: true
    });
}

// --- Termination notice ---
function showTerminationNotice(message, iconType) {
    if (_terminationNoticeFired) return;

    if (iconType === "info") {
        // Clean completion detected via the logs: mirror the authoritative
        // completion path. fireDoneNotification owns the guard + chime/popup.
        AppState.scriptRunning = false;
        stopSessionTimer();
        terminateScript();
        fireDoneNotification(message);
        return;
    }

    // Error path: always surface, regardless of the notify preference.
    _terminationNoticeFired = true;
    AppState.scriptRunning = false;
    stopSessionTimer();
    terminateScript();
    Swal.fire({
        title: t('common.error', "Error!"),
        text: message,
        icon: iconType,
        background: "#f9f9f9",
        color: "#333",
        showConfirmButton: true,
        confirmButtonText: t('common.ok', "OK")
    });
}