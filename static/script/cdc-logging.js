let statusCheckInterval = null;
const STATUS_CHECK_INTERVAL = 2000; // Check every 2 seconds
let _terminationNoticeFired = false;
// Set once a device-side end sentinel (SESSION TIMEOUT / STOPPED) has handed the
// run-end over to /check_status, so later log frames do not ask again.
let _endSentinelSeen = false;
// True for the duration of a manual point-mode capture (device idle, one row per
// "Measure now" press). Set when runScript starts a manual session, cleared on
// stop/completion. Used to suppress the interval countdown and to re-enable the
// Measure-now button when each requested row lands.
let manualSession = false;
// Watches whether the inline #measure-point-btn is on-screen. When it scrolls out
// of view during a manual run (e.g. user scrolled down to the live data), a fixed
// floating mirror (#measure-point-fab) is shown so the next Turn can be recorded
// without scrolling back up to the control panel.
let _measureObserver = null;
let _inlineMeasureVisible = true;
// Pause state of the live automatic run ("Pause reading"). The device holds off
// streaming and the logger drops any row that still arrives, so no data is
// recorded until Resume; the run itself stays alive.
let readingPaused = false;
let _pausedAt = null;
// Same scroll-watch pattern as the Measure-now mirror, for the automatic-run
// Pause/Resume + Stop floating controls (#reading-control-fab).
let _controlObserver = null;
let _inlineControlVisible = true;

// --- Session timer state ---
let sessionStartTime = null;
let lastDataPointTime = null;
let sessionIntervalSec = null;
let sessionTimerHandle = null;
let _prevDataPointCount = 0;

/* ==========================================================================
   Session strip (#session-strip) — the live run drawn across the top of the page.

   One thin polyline per source, in the same `--ramp-*` steps as the main chart,
   redrawn from AppState.responseData (which both the SSE push and the fallback
   poll already keep current — so this adds no fetching of its own). The pen
   advances left to right across the session rather than scrolling a window: the
   shape of the run so far is the useful thing, and a fixed left edge means the
   trace does not appear to move when nothing is happening.

   The trace is the recording indicator. Paused greys every line and stops the
   advance, so a held run looks held at any scroll position — the timer widget
   and the floating transport can both be off-screen (Rule.md §2.33).
   Opt out with the `session_strip_enabled` setting.
========================================================================== */
const STRIP_W = 900, STRIP_H = 64;

function stripEnabled() {
    // The strip is an instrument-style element: the classic style's live readout is
    // the top-right timer widget, exactly as it was before (Rule.md §2.34).
    if (typeof isClassicUI === 'function' && isClassicUI()) return false;
    return typeof USER_SETTINGS === 'undefined' || USER_SETTINGS.session_strip_enabled !== false;
}

function showSessionStrip() {
    if (!stripEnabled()) return;
    const el = document.getElementById('session-strip');
    if (!el) return;
    el.classList.remove('hidden');
    document.body.classList.add('strip-open');
}

// Apply a changed session_strip_enabled without a reload. Mid-session the
// live readout moves between the strip and the timer widget (only one of the
// two is ever shown); between sessions there is nothing to show.
function applySessionStripSetting() {
    if (!sessionStartTime) return;
    const timerEl = document.getElementById('session-timer');
    if (timerEl) timerEl.classList.toggle('hidden', stripEnabled());
    if (stripEnabled()) {
        showSessionStrip();
        drawSessionStrip();
    } else {
        const el = document.getElementById('session-strip');
        if (el) el.classList.add('hidden');
        document.body.classList.remove('strip-open');
    }
}

function hideSessionStrip() {
    const el = document.getElementById('session-strip');
    if (el) el.classList.add('hidden');
    // Clear the class *and* the "Paused" wording: the next run's strip must not
    // come up labelled Paused over a live trace.
    applyStripPausedState(false);
    document.body.classList.remove('strip-open');
    const traces = document.getElementById('strip-traces');
    if (traces) traces.textContent = '';
    const elapsed = document.getElementById('strip-elapsed');
    if (elapsed) elapsed.textContent = '00:00';
    const latest = document.getElementById('strip-latest');
    if (latest) latest.textContent = '\u2014';
    const next = document.getElementById('strip-next');
    if (next) { next.textContent = '--:--'; next.classList.remove('urgent'); }
    const nextField = document.getElementById('strip-next-field');
    if (nextField) nextField.classList.add('hidden');
    const scale = document.getElementById('strip-scale');
    if (scale) scale.textContent = '';
}

/* Redraw from the rows the session has produced so far. */
function drawSessionStrip() {
    const svgGroup = document.getElementById('strip-traces');
    // With the stream carrying the run, draw this session's pushed rows: the
    // chart's AppState.responseData is whatever file is open (another CSV's
    // trace under "Recording") and lags a pushed row by the render coalescing
    // (the Turn just taken was missing). Nothing is fetched either way (§2.33).
    const live = (typeof liveStripSource === 'function') ? liveStripSource() : null;
    // AppState.responseData is the row array itself (see processResponse); the
    // `.data` shape is what a raw /get_data payload looks like, so accept both.
    const raw = live ? live.rows : AppState.responseData;
    const rows = Array.isArray(raw) ? raw : (raw && Array.isArray(raw.data) ? raw.data : []);
    if (!svgGroup || !rows.length) return;

    const n = Math.max(1, (live ? live.numSources : AppState.numSources) || 1);
    const colors = sourceRamp(Math.max(2, n));
    const xs = rows.map(r => Number(r.Timestamp));
    // The x scale is the session so far, so the pen sits at the right edge as
    // soon as there are two rows; the trace lengthens rather than sliding.
    const xMax = Math.max(arrayMax(xs.filter(Number.isFinite)), 1);

    // One shared y scale across sources, from the data itself — a per-source
    // scale would make two different absorbances look identical.
    let lo = Infinity, hi = -Infinity;
    for (const row of rows) {
        for (let i = 1; i <= n; i++) {
            const v = measNumber(row[`Value:${i}`]);
            if (v !== null) { if (v < lo) lo = v; if (v > hi) hi = v; }
        }
    }
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return;
    if (hi - lo < 1e-6) { hi = lo + 0.05; }
    const pad = (hi - lo) * 0.12;
    lo -= pad; hi += pad;

    const px = x => (Number.isFinite(xMax) && xMax > 0 ? (x / xMax) * STRIP_W : 0);
    const py = v => STRIP_H - 6 - ((v - lo) / (hi - lo)) * (STRIP_H - 14);

    let markup = '';
    for (let i = 1; i <= n; i++) {
        let d = '', started = false;
        for (const row of rows) {
            const x = Number(row.Timestamp), v = measNumber(row[`Value:${i}`]);
            if (!Number.isFinite(x) || v === null) continue;   // OVFL / NONE / INF
            d += `${started ? 'L' : 'M'}${px(x).toFixed(1)} ${py(v).toFixed(1)}`;
            started = true;
        }
        if (d) {
            markup += `<path class="strip-trace" d="${d}" style="stroke:${colors[(i - 1) % colors.length]}"></path>`;
        }
    }
    svgGroup.innerHTML = markup;

    const scale = document.getElementById('strip-scale');
    if (scale) {
        const axis = ((live && live.xAxis) || AppState.xAxis) === 'turn' ? 'turns' : 's';
        scale.textContent = `${rows.length} rows \u00b7 ${n} src \u00b7 ${xMax.toFixed(0)} ${axis} \u00b7 ${lo.toFixed(2)}\u2013${hi.toFixed(2)}`;
    }

    // A single-source run has one unambiguous latest value, so show it. With
    // several sources there is no honest single number — show the row count.
    const latest = document.getElementById('strip-latest');
    const latestLabel = document.getElementById('strip-latest-label');
    const last = rows[rows.length - 1];
    if (latest && latestLabel) {
        if (n === 1) {
            const v = Number(last['Value:1']);
            latest.textContent = Number.isFinite(v) ? v.toFixed(3) : String(last['Value:1'] ?? '\u2014');
            latestLabel.setAttribute('data-i18n', 'strip.latest');
            latestLabel.textContent = t('strip.latest', 'Latest');
        } else {
            latest.textContent = String(rows.length);
            latestLabel.setAttribute('data-i18n', 'strip.rows');
            latestLabel.textContent = t('strip.rows', 'Rows');
        }
    }
}

/* Mirror the pause state onto the strip: grey, still, and it says so. */
function applyStripPausedState(paused) {
    const el = document.getElementById('session-strip');
    if (el) el.classList.toggle('is-paused', paused);
    const state = document.getElementById('strip-state');
    if (state) {
        state.setAttribute('data-i18n', paused ? 'timer.paused' : 'cdc.state_recording');
        state.textContent = paused
            ? t('timer.paused', 'Paused')
            : t('cdc.state_recording', 'Recording');
    }
}

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

    // Both readouts run off this one tick: the strip (on screen at any scroll
    // position) and the timer widget (the fallback, only mounted when the strip
    // is switched off). They can never drift because there is one clock.
    const elapsed = formatHMS(elapsedSec);
    const elapsedEl = document.getElementById('session-elapsed');
    if (elapsedEl) elapsedEl.textContent = elapsed;
    const stripElapsed = document.getElementById('strip-elapsed');
    if (stripElapsed) stripElapsed.textContent = elapsed;

    const counting = !!(sessionIntervalSec && sessionIntervalSec > 0 && lastDataPointTime);
    let next = '--:--', urgent = false;
    if (counting) {
        const remaining = Math.max(0, sessionIntervalSec - (now - lastDataPointTime) / 1000);
        next = formatHMS(remaining);
        urgent = remaining <= 10;
    }
    for (const id of ['session-next', 'strip-next']) {
        const el = document.getElementById(id);
        if (!el) continue;
        el.textContent = next;
        el.classList.toggle('urgent', urgent);
    }
    // A manual point-mode run has no interval, so it gets no countdown field
    // rather than a permanently blank one.
    const nextField = document.getElementById('strip-next-field');
    if (nextField) nextField.classList.toggle('hidden', !counting);
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
    // First row proves the device is talking — the start-up notice has done its
    // job and the session timer takes over from here.
    endStartupWatch();
    if (!sessionStartTime) {
        // First data point: reveal the live readout and start ticking. The strip
        // shows the same elapsed/next/state, so the timer widget appears only when
        // the strip is switched off — two live clocks was one too many.
        sessionStartTime = now;
        const timerEl = document.getElementById('session-timer');
        if (timerEl) timerEl.classList.toggle('hidden', stripEnabled());
        sessionTimerHandle = setInterval(tickSessionTimer, 1000);
    } else if (!sessionIntervalSec && !manualSession) {
        // Second data point with no configured interval: measure the device's
        // actual interval from the gap between point 1 and point 2. Skipped in
        // manual capture — presses are irregular, so there is no interval.
        sessionIntervalSec = (now - sessionStartTime) / 1000;
    }
    lastDataPointTime = now;
    tickSessionTimer();
    showSessionStrip();
    drawSessionStrip();
    // Manual capture: each requested row has landed, so re-arm "Measure now".
    if (manualSession && AppState.scriptRunning) setMeasureArmed(true);
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
    hideSessionStrip();
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
                if (response.status === 'device_not_found' || response.status === 'failure' || response.status === 'success' || response.status === 'warning' || response.status === 'not_running') {
                    clearStatusCheck();
                    AppState.scriptRunning = false;
                    if (response.status === 'warning') {
                        // The device dropped and never came back. Rows captured
                        // before it vanished are saved, so this ends the run the
                        // same way a completion does — only the wording differs.
                        logDisplay.insertAdjacentText('beforeend', `${response.message}\n`);
                        resetUIAfterCompletion(response.message);
                    } else if (response.status !== 'success') {
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
                    // Self-heal if the two ever disagree (e.g. a pause request
                    // that landed on the server but whose reply never arrived).
                    if (typeof response.paused === 'boolean' && response.paused !== readingPaused) {
                        applyPausedState(response.paused);
                    }
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

// Return the per-run controls to their idle state: clear the session flags,
// re-enable the Auto/Manual radios, hide + disable the Measure-now button, and
// drop the Pause/Resume controls (a finished run is never "paused"). Shared by
// every run-end path (error, completion, manual terminate).
function resetRunControls() {
    // The run is over (or never started), so stop watching for it to come up.
    // A failed start keeps its notice visible — endStartupWatch handles that.
    endStartupWatch();
    // Close the push channel, then re-read the finished file once from disk. The
    // stream is not the authority on what was recorded: if the status poll won
    // the race to detect the end, or a reconnect gap swallowed a row, the chart
    // would otherwise keep whatever the stream last delivered.
    if (typeof stopLiveStream === 'function') stopLiveStream();
    if (AppState.currentFile && typeof drawMeasurementChart === 'function') drawMeasurementChart();
    // Pause/Resume: clear the state before the flags below, so the controls are
    // repainted in their default "Pause reading" wording for the next run.
    readingPaused = false;
    _pausedAt = null;
    applyPauseControlsUI();
    // Set directly above, so the next run's applyPausedState(false) returns
    // early — reset the strip's state here or it keeps saying "Paused".
    applyStripPausedState(false);
    const pauseBtn = document.getElementById('pause-reading-btn');
    if (pauseBtn) { pauseBtn.classList.add('hidden'); pauseBtn.disabled = false; }
    manualSession = false;
    stopControlObserver();
    const ctrlFab = document.getElementById('reading-control-fab');
    if (ctrlFab) ctrlFab.classList.add('hidden');
    const fabPause = document.getElementById('reading-fab-pause');
    if (fabPause) fabPause.disabled = false;
    document.querySelectorAll('input[name="cdc-run-mode"]').forEach(r => (r.disabled = false));
    const btn = document.getElementById('measure-point-btn');
    if (btn) { btn.disabled = true; btn.classList.remove('blinking'); }
    // Tear down the scroll watcher and hide the floating manual transport.
    stopMeasureObserver();
    const fab = document.getElementById('measure-point-fab');
    if (fab) { fab.classList.add('hidden'); fab.classList.remove('is-busy'); }
    const fabBtn = document.getElementById('measure-fab-btn');
    if (fabBtn) fabBtn.disabled = true;
    // Restore run-mode visibility (re-hides Measure-now unless still Manual+point).
    if (typeof updateRunModeVisibility === 'function') updateRunModeVisibility();
}

function resetUI({ goToEnabled }) {
    resetRunControls();
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
    // The Auto/Manual choice only exists for a Turn (point-mode) capture.
    updateRunModeVisibility();
}

// The current Auto/Manual run mode, but only when the choice is actually offered
// (point mode + Turn). Falls back to 'auto' when the run-mode control is hidden.
function currentRunMode() {
    const ctrl = document.getElementById('cdc-run-mode-control');
    if (!ctrl || ctrl.classList.contains('hidden')) return 'auto';
    return document.querySelector('input[name="cdc-run-mode"]:checked')?.value || 'auto';
}

// Show the Auto/Manual control only for a point-mode Turn capture; force Auto and
// restore the interval/timeout controls whenever it is hidden. Also applied on
// mode switch (via applyModeVisibility) and on load.
function updateRunModeVisibility() {
    const turnOn = !!document.getElementById('cdc-axis-turn')?.checked;
    const isPoint = (typeof AppState !== 'undefined' && AppState.currentMeasurementMode === 'point');
    const offer = turnOn && isPoint;
    const ctrl = document.getElementById('cdc-run-mode-control');
    if (ctrl) ctrl.classList.toggle('hidden', !offer);
    if (!offer) {
        const autoRadio = document.querySelector('input[name="cdc-run-mode"][value="auto"]');
        if (autoRadio) autoRadio.checked = true;
    }
    applyRunModeUI();
}

// Manual capture uses no interval/timeout (Stop-only, on-demand), so hide those
// controls and reveal the "Measure now" button when Manual is selected.
function applyRunModeUI() {
    const manual = currentRunMode() === 'manual';
    document.getElementById('interval-control')?.classList.toggle('hidden', manual);
    document.getElementById('timeout-control')?.classList.toggle('hidden', manual);
    // The Measure-now button appears only during an actual manual run (revealed by
    // runScript); keep it hidden whenever the app is idle so an inert button never
    // shows before Start.
    const btn = document.getElementById('measure-point-btn');
    if (btn && !AppState?.scriptRunning) btn.classList.add('hidden');
}

function onCdcRunModeChange() {
    const value = currentRunMode();
    if (typeof USER_SETTINGS !== 'undefined') USER_SETTINGS.cdc_run_mode = value;
    if (typeof saveUserSetting === 'function') saveUserSetting('cdc_run_mode', value);
    applyRunModeUI();
}

// Enable/disable the Measure-now button (armed = ready to record). Drives both the
// inline button and the floating transport so their state never diverges.
function setMeasureArmed(armed) {
    const btn = document.getElementById('measure-point-btn');
    if (btn) { btn.disabled = !armed; btn.classList.toggle('blinking', armed); }
    syncMeasureFab();
}

// Mirror the inline button's state onto the floating transport and decide its
// visibility: shown only during a live manual run while the inline button line is
// scrolled off-screen. Same bar as #reading-control-fab — the state readout says
// whether the device is armed for the next press (Ready) or still returning the
// row the last press asked for (Measuring).
function syncMeasureFab() {
    const fab = document.getElementById('measure-point-fab');
    if (!fab) return;
    const inline = document.getElementById('measure-point-btn');
    const active = manualSession && !!AppState?.scriptRunning;
    fab.classList.toggle('hidden', !(active && !_inlineMeasureVisible));

    const armed = inline ? !inline.disabled : false;
    const fabBtn = document.getElementById('measure-fab-btn');
    if (fabBtn) fabBtn.disabled = !armed;
    fab.classList.toggle('is-busy', !armed);
    _setToggleLabel('measure-fab-state-label',
        armed ? 'cdc.state_ready' : 'cdc.state_measuring',
        armed ? t('cdc.state_ready', 'Ready') : t('cdc.state_measuring', 'Measuring'));
}

function startMeasureObserver() {
    const inline = document.getElementById('measure-point-btn');
    if (!inline) return;
    if (!('IntersectionObserver' in window)) { _inlineMeasureVisible = false; syncMeasureFab(); return; }
    if (_measureObserver) _measureObserver.disconnect();
    _measureObserver = new IntersectionObserver((entries) => {
        _inlineMeasureVisible = entries[0].isIntersecting;
        syncMeasureFab();
    }, { threshold: 0 });
    _measureObserver.observe(inline);
}

function stopMeasureObserver() {
    if (_measureObserver) { _measureObserver.disconnect(); _measureObserver = null; }
    _inlineMeasureVisible = true;
    syncMeasureFab();
}

// Manual capture: ask the device for one on-demand reading. Disabled until the
// requested row lands (onNewDataPoint re-arms it) so rapid presses can't stack.
async function measurePoint() {
    setMeasureArmed(false);
    try {
        const res = await fetch('/measure_point', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        const response = await res.json();
        if (response.status !== 'success') {
            setMeasureArmed(true);
            $append('log-display', `Error: ${response.message}\n`);
        }
    } catch (err) {
        console.error('measurePoint error:', err);
        setMeasureArmed(true);
    }
}

// --- Start-up progress notice ------------------------------------------------
// Between pressing Start and the first row landing, the logger probes the serial
// ports, runs the command handshake (up to 3 attempts, 5 s each) and waits out
// the firmware's settle. None of that prints anything the user sees, so the panel
// used to sit silent for many seconds and a working run looked hung. This walks a
// notice through the phases and fails the run if the device never answers.

let _startupWatching = false;
let _startupStartedAt = null;
let _startupPhase = null;
let _startupTicker = null;

// Phases, in order, keyed off the lines log_cdc_data.py writes. Keep the patterns
// in sync with that file — they are the only progress signal available, since the
// logger is a separate process and Flask returns as soon as it spawns.
const STARTUP_PHASES = [
    { id: 'connecting', test: null,
      key: 'cdc.startup.connecting', text: 'Looking for the colorimeter…' },
    { id: 'handshaking', test: /Connected to PyBadge at/,
      key: 'cdc.startup.handshaking', text: 'Device found. Starting the session…' },
    { id: 'waiting', test: /New session started/,
      key: 'cdc.startup.waiting', text: 'Session started. Waiting for the first reading…' }
];

function startupTimeoutSec() {
    const v = (typeof USER_SETTINGS !== 'undefined') ? Number(USER_SETTINGS.reading_start_timeout_sec) : NaN;
    return (isFinite(v) && v >= 10) ? v : 60;
}

function _startupEl(id) { return document.getElementById(id); }

// Begin watching a freshly started run. Called from runScript on success.
function beginStartupWatch() {
    _startupWatching = true;
    _startupStartedAt = Date.now();
    _startupPhase = null;
    const box = _startupEl('reading-startup');
    if (box) { box.classList.remove('hidden', 'is-late', 'is-failed'); }
    const note = _startupEl('reading-startup-note');
    if (note) note.classList.remove('hidden');
    setStartupPhase(STARTUP_PHASES[0]);
    if (_startupTicker) clearInterval(_startupTicker);
    _startupTicker = setInterval(tickStartupWatch, 1000);
    tickStartupWatch();
}

function setStartupPhase(phase) {
    if (!phase || _startupPhase === phase.id) return;
    _startupPhase = phase.id;
    _setToggleLabel('reading-startup-text', phase.key, t(phase.key, phase.text));
}

// Walk the notice forward using the logger's log text. Only ever moves forward:
// the log is cumulative, so the latest matching phase wins.
function updateStartupProgress(logs) {
    if (!_startupWatching) return;
    let reached = STARTUP_PHASES[0];
    for (let i = 1; i < STARTUP_PHASES.length; i++) {
        if (STARTUP_PHASES[i].test.test(logs)) reached = STARTUP_PHASES[i];
    }
    setStartupPhase(reached);
}

function tickStartupWatch() {
    if (!_startupWatching) return;
    // A Pause pressed before the first row holds the start-up clock too:
    // otherwise a healthy, paused session is torn down as "did not respond"
    // once reading_start_timeout_sec runs out (Rule.md §2.29).
    if (readingPaused) return;
    const elapsed = Math.floor((Date.now() - _startupStartedAt) / 1000);
    const el = _startupEl('reading-startup-elapsed');
    if (el) el.textContent = `${elapsed}s`;

    // Past halfway, say plainly that this is slower than usual but still alive,
    // so the wait doesn't read as a freeze.
    const limit = startupTimeoutSec();
    const box = _startupEl('reading-startup');
    if (box && elapsed >= Math.floor(limit / 2)) box.classList.add('is-late');
    if (elapsed >= limit) failStartupWatch(elapsed);
}

// The device never answered. Stop the run — a session that never started writes
// nothing, and leaving the logger attached holds the serial port.
function failStartupWatch(elapsed) {
    endStartupWatch({ failed: true });
    const box = _startupEl('reading-startup');
    if (box) { box.classList.remove('hidden', 'is-late'); box.classList.add('is-failed'); }
    const note = _startupEl('reading-startup-note');
    if (note) note.classList.add('hidden');
    const msg = t('cdc.startup.timeout_text',
        'The colorimeter did not start a session in time. Check that it is connected and switched on, then try again.');
    _setToggleLabel('reading-startup-text', 'cdc.startup.timeout', t('cdc.startup.timeout', 'The device did not respond'));
    $append('log-display', `Error: ${msg} (${elapsed}s)\n`);
    // Route through the shared error path so the run is torn down exactly like
    // any other failed start (guarded, so it fires at most once).
    showTerminationNotice(msg, 'error');
}

// Stop watching. `failed` skips the success bookkeeping; otherwise the notice is
// simply hidden because the run is now live and the timer widget takes over.
function endStartupWatch(opts) {
    _startupWatching = false;
    if (_startupTicker) { clearInterval(_startupTicker); _startupTicker = null; }
    if (!(opts && opts.failed)) {
        const box = _startupEl('reading-startup');
        // A failed start keeps its message on screen until the next Start —
        // otherwise the teardown it triggers would immediately erase the reason.
        if (box && !box.classList.contains('is-failed')) box.classList.add('hidden');
    }
}

// --- Pause / Resume a live automatic run ------------------------------------
// Offered for automatic runs only (a manual run is already on-demand — it gets
// "Measure now" instead). Two entry points share this state: the inline
// #pause-reading-btn on the button line, and the floating #reading-control-fab
// shown once that line scrolls out of view.

// Write a label into its own span AND move its data-i18n key, so the wording
// survives a later applyTranslations() pass (which rewrites textContent from the
// key). Writing to the button itself would erase the icon beside the label.
function _setToggleLabel(elId, key, text) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.setAttribute('data-i18n', key);
    el.textContent = text;
}

// Paint both controls for the current pause state: the inline button's icon,
// label, tint and hint; and the floating transport's state readout, icon and
// action label. One function so the two entry points can never disagree.
function applyPauseControlsUI() {
    const hintKey = readingPaused ? 'hint.resume_reading' : 'hint.pause_reading';
    const hint = readingPaused
        ? t('hint.resume_reading', 'Continue the paused reading from where it left off')
        : t('hint.pause_reading', 'Hold the reading without ending the run — the device stops taking readings until you resume');

    const btn = document.getElementById('pause-reading-btn');
    if (btn) {
        btn.setAttribute('data-i18n-hint', hintKey);
        btn.setAttribute('data-hint', hint);
        // Amber tint while held — a solid state reads as "held", where a blinking
        // border read as "broken".
        btn.classList.toggle('is-paused', readingPaused);
    }
    _setToggleLabel('pause-reading-label',
        readingPaused ? 'cdc.resume_reading' : 'cdc.pause_reading',
        readingPaused ? t('cdc.resume_reading', 'Resume reading') : t('cdc.pause_reading', 'Pause reading'));

    const fab = document.getElementById('reading-control-fab');
    if (fab) fab.classList.toggle('paused', readingPaused);
    const fabBtn = document.getElementById('reading-fab-pause');
    if (fabBtn) {
        fabBtn.setAttribute('data-i18n-hint', hintKey);
        fabBtn.setAttribute('data-hint', hint);
    }
    // Short verbs in the transport (the state readout already gives context);
    // the inline button keeps the fuller "Pause reading" among its siblings.
    _setToggleLabel('reading-fab-pause-label',
        readingPaused ? 'cdc.resume' : 'cdc.pause',
        readingPaused ? t('cdc.resume', 'Resume') : t('cdc.pause', 'Pause'));
    _setToggleLabel('reading-fab-state-label',
        readingPaused ? 'timer.paused' : 'cdc.state_recording',
        readingPaused ? t('timer.paused', 'Paused') : t('cdc.state_recording', 'Recording'));
    // The timer widget freezes while paused — say so, or it reads as stuck.
    const badge = document.getElementById('session-paused-badge');
    if (badge) badge.classList.toggle('hidden', !readingPaused);
}

// Apply a pause state locally: freeze/thaw the session timer and repaint the
// controls. The device-side pause is requested separately by togglePauseReading.
// The elapsed and next-reading clocks are SHIFTED by the pause duration rather
// than left running, matching the device (its session clock freezes too), so a
// resumed series continues seamlessly instead of showing a hole.
function applyPausedState(paused) {
    if (paused === readingPaused) { applyPauseControlsUI(); return; }
    readingPaused = paused;
    if (paused) {
        _pausedAt = Date.now();
        if (sessionTimerHandle) { clearInterval(sessionTimerHandle); sessionTimerHandle = null; }
    } else {
        const held = _pausedAt ? Date.now() - _pausedAt : 0;
        if (sessionStartTime) sessionStartTime += held;
        if (lastDataPointTime) lastDataPointTime += held;
        if (_startupWatching) _startupStartedAt += held;
        _pausedAt = null;
        // Only resume ticking if the widget was already live (first point seen).
        if (sessionStartTime && !sessionTimerHandle) {
            sessionTimerHandle = setInterval(tickSessionTimer, 1000);
            tickSessionTimer();
        }
    }
    applyPauseControlsUI();
    applyStripPausedState(paused);
    syncReadingFab();
}

async function togglePauseReading() {
    if (!AppState?.scriptRunning) return;
    const wantPause = !readingPaused;
    const btn = document.getElementById('pause-reading-btn');
    const fabBtn = document.getElementById('reading-fab-pause');
    // Disable both entry points for the round-trip so a double press cannot
    // send PAUSE and RESUME back to back.
    if (btn) btn.disabled = true;
    if (fabBtn) fabBtn.disabled = true;
    try {
        const res = await fetch(wantPause ? '/pause_reading' : '/resume_reading', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }
        });
        const response = await res.json();
        if (response.status === 'success') {
            logEvent('hardware', wantPause ? 'pause' : 'resume');
            applyPausedState(wantPause);
        } else {
            $append('log-display', `Error: ${response.message}\n`);
        }
    } catch (err) {
        console.error('togglePauseReading error:', err);
        $append('log-display', 'Error: Failed to change the reading state\n');
    } finally {
        if (btn) btn.disabled = false;
        if (fabBtn) fabBtn.disabled = false;
    }
}

// Show/hide the floating Pause+Stop group: only during a live automatic run,
// and only while the inline button line is scrolled out of view.
function syncReadingFab() {
    const fab = document.getElementById('reading-control-fab');
    if (!fab) return;
    const active = !!AppState?.scriptRunning && !manualSession;
    fab.classList.toggle('hidden', !(active && !_inlineControlVisible));
}

function startControlObserver() {
    const inline = document.getElementById('pause-reading-btn');
    if (!inline) return;
    if (!('IntersectionObserver' in window)) { _inlineControlVisible = false; syncReadingFab(); return; }
    if (_controlObserver) _controlObserver.disconnect();
    _controlObserver = new IntersectionObserver((entries) => {
        _inlineControlVisible = entries[0].isIntersecting;
        syncReadingFab();
    }, { threshold: 0 });
    _controlObserver.observe(inline);
}

function stopControlObserver() {
    if (_controlObserver) { _controlObserver.disconnect(); _controlObserver = null; }
    _inlineControlVisible = true;
    syncReadingFab();
}

// Lock the reading-setup inputs for the length of a run.
function lockRunInputs() {
    document.querySelectorAll('input[name="cdc-save-mode"]').forEach(r => (r.disabled = true));
    const existingSel = document.getElementById('cdc-subfolder-select');
    if (existingSel) existingSel.disabled = true;
    const newInput = document.getElementById('cdc-new-folder-name');
    if (newInput) newInput.disabled = true;
    $disable(["base-name", "run-script-btn", "inf-timeout", "timeout", "timeout-unit", "interval", "interval-unit", "cdc-axis-turn"]);
    document.querySelectorAll('input[name="cdc-run-mode"]').forEach(r => (r.disabled = true));
    $toggleClass("run-script-btn", "blinking", false);
    modeButtons.forEach(btn => btn.disabled = true);
}

// Put the page into its "session running" state: Stop enabled, the run's own
// controls shown, the status poll and the live stream started. Shared by a
// fresh start (runScript) and a reload that finds a run already going
// (resyncRunningSession) — the two must never drift apart.
function enterRunningUI({ manual, intervalSec, paused, measureArmed }) {
    _endSentinelSeen = false;
    manualSession = !!manual;
    AppState.scriptRunning = true;
    $disable(["terminate-script-btn"], false);
    $disable(["go-to-btn"], false);
    $toggleClass("go-to-btn", "blinking", true);
    startSessionTimer(intervalSec);
    // Manual capture: reveal the "Measure now" button. A fresh start keeps it
    // disabled until Turn 1 lands — the logger auto-records the first Turn on
    // start, and onNewDataPoint arms the button once it arrives (so an early
    // press can't queue a duplicate). Start watching it so the floating mirror
    // appears when it scrolls out of view.
    if (manual) {
        const mBtn = document.getElementById('measure-point-btn');
        if (mBtn) mBtn.classList.remove('hidden');
        setMeasureArmed(!!measureArmed);
        startMeasureObserver();
    } else {
        // Automatic run: offer Pause/Resume (inline + floating mirror).
        // A manual run is already on-demand, so it has nothing to pause.
        const pBtn = document.getElementById('pause-reading-btn');
        if (pBtn) pBtn.classList.remove('hidden');
        applyPausedState(!!paused);
        startControlObserver();
    }
    clearStatusCheck();
    statusCheckInterval = setInterval(checkScriptStatus, STATUS_CHECK_INTERVAL);
    // Push channel for this run's rows and log text. The status poll
    // above stays: it owns why a session ended, which the stream does
    // not attempt to decide.
    startLiveStream();
}

// A reload (F5, or a language/style change) mid-run used to leave the page
// idle with Stop disabled while the logger kept recording. Ask the server
// once on load and, if a session is running, re-enter the running state —
// including a Pause already in force (Rule.md §2.29, §2.31). Only a running
// answer is acted on: any other status is left for the next run to handle.
async function resyncRunningSession() {
    let response;
    try {
        // peek: read-only — never consume a finished run's end status here.
        const res = await fetch('/check_status?peek=1');
        response = await res.json();
    } catch (err) {
        return;
    }
    if (!response || response.status !== 'running' || AppState.scriptRunning) return;
    _terminationNoticeFired = false;
    lockRunInputs();
    // Rows already exist, so a manual run's Measure now is armed straight away.
    enterRunningUI({ manual: !!response.manual, intervalSec: response.interval_sec || null, paused: response.paused === true, measureArmed: true });
    $append("log-display", t('cdc.reconnected', 'Reconnected to the running session.') + "\n");
}
document.addEventListener('DOMContentLoaded', resyncRunningSession);

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

    lockRunInputs();

    const manual = currentRunMode() === 'manual';
    manualSession = manual;
    const timeoutValue = timeoutEl.value.trim();
    const intervalValue = intervalEl.value.trim();
    const useTurn = !!document.getElementById('cdc-axis-turn')?.checked;
    const payload = {
        subfolder: subfolder,
        base_name: baseName,
        inf_checked: infTimeout,
        // Manual capture is Stop-only and on-demand, so it sends no timeout/interval.
        timeout_sec: manual ? null : (timeoutValue ? parseFloat(timeoutValue) * getTimeUnitMultiplier($id("timeout-unit").value) : null),
        interval_sec: manual ? null : (intervalValue ? parseFloat(intervalValue) * getTimeUnitMultiplier($id("interval-unit").value) : null),
        axis: (useTurn || manual) ? 'turn' : 'time',
        manual: manual
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
            $text("log-display", "Script started...\n");
            if (saveMode === 'new' && typeof loadDataFolders === 'function') loadDataFolders();
            // /run_script returns as soon as the logger process survives its
            // first half-second — the device has NOT been reached yet. Watch the
            // start-up from here so the wait is visible and bounded.
            enterRunningUI({ manual, intervalSec: payload.interval_sec, paused: false, measureArmed: false });
            beginStartupWatch();
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
// Stop buttons a user can reach during a run: the inline one and the two
// floating transports.
const STOP_BUTTON_IDS = ['terminate-script-btn', 'reading-fab-stop', 'measure-fab-stop'];
let _terminateInFlight = null;

// /terminate_script can block for ~6 s (SIGINT, wait, SIGTERM, wait). A second
// press in that window used to send a second SIGINT into the logger's clean
// shutdown, so one request at a time: later callers share the first one's
// promise, and every Stop control is disabled until it settles (§2.29).
function terminateScript() {
    if (_terminateInFlight) return _terminateInFlight;
    STOP_BUTTON_IDS.forEach(id => { const b = document.getElementById(id); if (b) b.disabled = true; });
    _terminateInFlight = _terminateScript().finally(() => {
        _terminateInFlight = null;
        // The floating Stops are hidden with their transports by now; re-enable
        // them for the next run (the inline Stop is owned by the run state).
        ['reading-fab-stop', 'measure-fab-stop'].forEach(id => { const b = document.getElementById(id); if (b) b.disabled = false; });
    });
    return _terminateInFlight;
}

async function _terminateScript() {
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
    resetRunControls();
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
    ["base-name", "inf-timeout", "interval", "interval-unit"].forEach(id => $id(id).disabled = false);
    // Turn axis is point-mode-only (Rule §2.27); re-enable it only there so a
    // finished kinetics/calibrate capture never re-arms the Turn checkbox.
    if (AppState?.currentMeasurementMode === 'point') $id("cdc-axis-turn").disabled = false;
    const timeoutDisabled = $id("inf-timeout").checked;
    $id("timeout").disabled = timeoutDisabled;
    $id("timeout-unit").disabled = timeoutDisabled;
    modeButtons.forEach(btn => btn.disabled = false);
}

// Interpret the session log accumulated so far: advance the start-up notice and
// raise any end-of-session notice. Shared by the SSE stream (which appends log
// deltas as they are pushed) and the fallback poll below, so both read the log
// exactly the same way.
//
// `countDataPoints` is the fallback path's row detector: it counts "Received:"
// lines in the whole log because a poll has no other way to notice a new row.
// The stream leaves it off — it is handed the rows themselves, so it calls
// onNewDataPoint() once per row instead of inferring a count.
function applyLogText(logs, { countDataPoints = false } = {}) {
    // Advance the start-up notice from the logger's own progress lines. Runs
    // before the data-point check so a run that goes live inside a single poll
    // still clears the notice.
    updateStartupProgress(logs);

    if (countDataPoints) {
        const dpCount = (logs.match(/Received: (?:Timestamp|Turn):/g) || []).length;
        if (dpCount > _prevDataPointCount) {
            _prevDataPointCount = dpCount;
            onNewDataPoint();
        }
    }

    if (/PyBadge not found/.test(logs)) showTerminationNotice(t('cdc.err_pybadge_not_found', "PyBadge not found. Please check the connection."), "error");
    else if (/Failed to find input endpoint/.test(logs)) showTerminationNotice(t('cdc.err_no_endpoint', "Failed to find input endpoint. Please verify USB connection."), "error");
    else if (/SESSION STOPPED/.test(logs)) showTerminationNotice(t('cdc.session_stopped', "Session stopped manually on the device."), "info");
    else if (/SESSION TIMEOUT/.test(logs)) showTerminationNotice(t('cdc.session_timeout', "Session ended due to timeout."), "info");
}

// --- Fetch logs (fallback path) ---
// Only runs while the SSE session stream is NOT carrying the session — see
// live-stream.js. With the stream up, log text arrives as deltas instead.
async function fetchLogs() {
    try {
        const res = await fetch("/get_logs");
        const response = await res.json();
        if (response.status === "success") {
            const logs = response.logs;
            $text("log-display", logs);
            applyLogText(logs, { countDataPoints: true });
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
        // The device ended the session itself (timeout, or Stop on the device)
        // and the logger is already exiting on its own. /check_status is the
        // single place that decides why a session ended (Rule.md §2.31): ask it
        // now rather than SIGINTing an exiting logger and announcing a reason
        // of our own — with SSE this frame routinely beats the status poll, and
        // a device-drop `warning` could be relabelled "ended due to timeout".
        // If the logger has not exited yet, the running status poll finishes
        // the job on its next tick.
        if (_endSentinelSeen) return;
        _endSentinelSeen = true;
        checkScriptStatus();
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