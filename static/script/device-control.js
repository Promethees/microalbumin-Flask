/* Virtual controller — the colorimeter's own keypad, worked from the app.
 *
 * The device has eight buttons and a small screen, and what a button does
 * depends on which screen is up: `menu` saves in Settings, opens the menu in
 * Measure, and dismisses in a message. That mapping is the thing the keypad
 * itself cannot tell you, so this panel's real job is to *label* the buttons for
 * the screen the device is on — pressing them from here is the second half.
 *
 * Everything hangs off one poll of `/device/state`, which answers a STATE line
 * from the firmware (see src/device_link.py). Two rules shape the rest:
 *
 *   * The serial port has exactly one owner. During a reading session that owner
 *     is the logger subprocess, so the whole panel goes unavailable and says so
 *     — the mid-run controls live on the reading panel instead (Rule.md 2.29).
 *   * Polling only runs while the panel is expanded. Opening the panel is what
 *     opens the port, so a user who never opens it never touches the device.
 */

// ── the keypad ──────────────────────────────────────────────────────────────
// Names are the firmware's own (colorimeter.button_map), which is also what the
// BTN: command takes. `cluster` + `slot` place each one where it sits on the
// board, so the panel can be read against the instrument in front of the
// operator without a legend:
//
//        [SELECT]                        [START]
//          ▲          ┌────────┐             [A]
//        ◀   ▶        │ screen │         [B]
//          ▼          └────────┘
//
// — the screen in the middle column being the readout panel, where the PyBadge's
// own display sits.
//
// `glyph` is therefore the PyBadge's own silkscreen label, not a mnemonic for
// the firmware role — B is the button marked B (gain), which is exactly the
// letter the operator's thumb is over. Board mapping is colorimeter.button_map
// keyed by the PyBadge shift-register order (constants.BUTTON): bit0 B, bit1 A,
// bit2 START, bit3 SELECT, bits 4-7 the d-pad.
const DEVICE_BUTTONS = [
    { name: 'menu',  cluster: 'topleft',  glyph: 'SELECT', slot: 'kmenu' },
    { name: 'blank', cluster: 'topright', glyph: 'START',  slot: 'kblank' },
    { name: 'up',    cluster: 'dpad', glyph: '▲', slot: 'kup' },
    { name: 'left',  cluster: 'dpad', glyph: '◀', slot: 'kleft' },
    { name: 'right', cluster: 'dpad', glyph: '▶', slot: 'kright' },
    { name: 'down',  cluster: 'dpad', glyph: '▼', slot: 'kdown' },
    { name: 'itime', cluster: 'ab',   glyph: 'A', slot: 'ka' },
    { name: 'gain',  cluster: 'ab',   glyph: 'B', slot: 'kb' },
];

// What each button does on each device screen. Mirrors the firmware's
// ButtonHandler mode handlers — keep the two in lockstep; a label that lies is
// worse than no label. A missing entry means the button does nothing there.
const DEVICE_BUTTON_FUNCTIONS = {
    MEASURE: {
        blank: ['devctl.fn.blank', 'Blank / unblank'],
        menu:  ['devctl.fn.open_menu', 'Open menu'],
        gain:  ['devctl.fn.gain', 'Cycle gain'],
        itime: ['devctl.fn.itime', 'Cycle integration time'],
        // Right is the one button whose *meaning* differs between device builds,
        // so it is resolved from the firmware's `caps` rather than this table
        // (see deviceButtonFunction). Nothing here.
        // `left` starts the device's HID keyboard fallback here, which types the
        // readings into whichever window has focus. The firmware refuses it from
        // a host press, so it is shown as unavailable rather than offered.
        left:  ['devctl.fn.unavailable_hid', 'Unavailable — starts the device keyboard mode'],
    },
    MENU: {
        up:    ['devctl.fn.prev_item', 'Previous item'],
        down:  ['devctl.fn.next_item', 'Next item'],
        menu:  ['devctl.fn.select', 'Select'],
        left:  ['devctl.fn.select', 'Select'],
        right: ['devctl.fn.select', 'Select'],
    },
    SETTINGS: {
        menu:  ['devctl.fn.save_settings', 'Save settings'],
        left:  ['devctl.fn.back_to_menu', 'Back to menu'],
        up:    ['devctl.fn.increase', 'Increase'],
        down:  ['devctl.fn.decrease', 'Decrease'],
        right: ['devctl.fn.next_field', 'Next field'],
        itime: ['devctl.fn.cycle_unit', 'Cycle unit'],
        blank: ['devctl.fn.revert', 'Revert to saved'],
        gain:  ['devctl.fn.timeout_none', 'Timeout: none'],
    },
    CONCENTRATION: {
        menu:  ['devctl.fn.save_concentration', 'Save concentration'],
        blank: ['devctl.fn.unit_or_reset', 'Cycle unit / reset value'],
        up:    ['devctl.fn.plus_1', '+1'],
        down:  ['devctl.fn.minus_1', '−1'],
        right: ['devctl.fn.plus_10', '+10'],
        left:  ['devctl.fn.minus_10', '−10'],
        itime: ['devctl.fn.plus_100', '+100'],
        gain:  ['devctl.fn.minus_100', '−100'],
    },
    MESSAGE: { _any: ['devctl.fn.dismiss', 'Dismiss'] },
    ABORT:   { _any: ['devctl.fn.dismiss', 'Dismiss'] },
};

// Screen names as the operator sees them.
const DEVICE_MODE_LABELS = {
    MEASURE: ['devctl.mode.measure', 'Measure'],
    MENU: ['devctl.mode.menu', 'Menu'],
    SETTINGS: ['devctl.mode.settings', 'Settings'],
    CONCENTRATION: ['devctl.mode.concentration', 'Concentration'],
    CALIBRATION: ['devctl.mode.calibration', 'Sensor Cal'],
    MESSAGE: ['devctl.mode.message', 'Message'],
    ABORT: ['devctl.mode.abort', 'Halted'],
};

let deviceState = null;
let devicePollTimer = null;
let devicePollInFlight = false;
let deviceKeypadBuilt = false;
// Channels the operator has ticked but not applied yet. Null means "follow the
// device" — without it every poll would undo a half-made selection.
let devicePendingChannels = null;

function deviceControlEnabled() {
    return typeof USER_SETTINGS === 'undefined' || USER_SETTINGS.device_control_enabled !== false;
}

// The connection switch beside the status strip. Distinct from the setting
// above: that one hides the feature, this one decides whether the app may hold
// the port while the panel is open — the state to be in when a firmware update
// or a serial monitor wants the device.
function deviceLinkEnabled() {
    const box = document.getElementById('devctl-link-toggle');
    if (box) return box.checked;
    return typeof USER_SETTINGS === 'undefined' || USER_SETTINGS.device_link_enabled !== false;
}

function devicePollInterval() {
    const ms = (typeof USER_SETTINGS !== 'undefined') ? USER_SETTINGS.device_state_poll_ms : null;
    return (typeof ms === 'number' && ms >= 500) ? ms : 1500;
}

function deviceControlExpanded() {
    const collapse = document.getElementById('device-control-collapse');
    return !!collapse && !collapse.classList.contains('collapsed');
}

// ── panel lifecycle ─────────────────────────────────────────────────────────

function toggleDeviceController() {
    toggleFolderList('device-control-collapse', 'device-control-chevron');
    if (deviceControlExpanded()) {
        startDevicePolling();
    } else {
        stopDevicePolling();
    }
}

// Flipping the switch: on resumes the poll, off stops it and releases the port
// rather than leaving it to the 30 s idle reaper — someone who turns this off is
// usually about to give the port to something else, and a switch that appears to
// do nothing for half a minute is a switch that gets flipped again.
function onDeviceLinkToggle() {
    const enabled = deviceLinkEnabled();
    if (typeof saveUserSetting === 'function') saveUserSetting('device_link_enabled', enabled);
    if (enabled) {
        if (deviceControlExpanded()) startDevicePolling();
        return;
    }
    stopDevicePolling();
    releaseDeviceLink();
    setDeviceControlStatus('offline', t('devctl.link_off', 'Not connected — the port is free'));
}

async function releaseDeviceLink() {
    try {
        await fetch('/device/disconnect', { method: 'POST' });
    } catch (err) {
        // Nothing to tell the user: the reaper drops the port regardless, and
        // this runs while they are switching away from the device.
    }
}

function startDevicePolling() {
    if (devicePollTimer) return;
    // The switch is checked here rather than at every call site, so no path can
    // start a poll behind the user's back.
    if (!deviceLinkEnabled()) {
        setDeviceControlStatus('offline', t('devctl.link_off', 'Not connected — the port is free'));
        return;
    }
    pollDeviceState();
    devicePollTimer = setInterval(pollDeviceState, devicePollInterval());
}

function stopDevicePolling() {
    if (!devicePollTimer) return;
    clearInterval(devicePollTimer);
    devicePollTimer = null;
}

async function pollDeviceState() {
    // One request at a time: a slow reply must not queue a second poll behind it
    // and turn a busy port into a backlog of stale answers.
    if (devicePollInFlight) return;
    devicePollInFlight = true;
    try {
        const res = await fetch('/device/state');
        const data = await res.json();
        if (res.status === 409) {
            setDeviceControlStatus('busy', t('devctl.busy',
                'Unavailable while a reading session is running'));
            return;
        }
        if (data.status !== 'success' || !data.state) {
            setDeviceControlStatus('offline', data.message ||
                t('devctl.offline', 'No colorimeter found'));
            return;
        }
        applyDeviceState(data.state);
    } catch (err) {
        setDeviceControlStatus('offline', t('devctl.offline', 'No colorimeter found'));
    } finally {
        devicePollInFlight = false;
    }
}

// ── rendering ───────────────────────────────────────────────────────────────

function setDeviceControlStatus(kind, text) {
    const strip = document.getElementById('device-control-status');
    const label = document.getElementById('device-control-status-text');
    const body = document.getElementById('device-control-body');
    if (!strip || !label || !body) return;
    strip.classList.remove('devctl-status--live', 'devctl-status--busy', 'devctl-status--offline');
    strip.classList.add(`devctl-status--${kind}`);
    label.textContent = text;
    // The body stays up while offline would show a frozen snapshot as if it were
    // live, so hide it whenever the device is not answering.
    body.classList.toggle('hidden', kind !== 'live');
    // A device that stopped answering may be a *different* device (or the same
    // one rebooted with another calibrations.json) by the time it answers again,
    // so the menu is re-asked for rather than redrawn from the old list.
    if (kind !== 'live') {
        deviceState = null;
        deviceMenuItems = null;
        deviceConcUnits = null;
        deviceTimingUnits = null;
        // Same reasoning for the factors: the device that comes back may be a
        // different one, or the same one rebooted back to its configuration.json.
        deviceCalibFactors = null;
    }
}

function applyDeviceState(state) {
    deviceState = state;
    setDeviceControlStatus('live', t('devctl.connected', 'Connected'));
    renderDeviceReadout(state);
    renderDeviceKeypad(state);
    renderDeviceChannels(state);
    renderDeviceMenu(state);
    renderDeviceConcentration(state);
    renderDeviceTiming(state);
    renderDeviceCalibration(state);
}

function renderDeviceReadout(state) {
    const modeLabel = DEVICE_MODE_LABELS[state.mode];
    $text('devctl-mode', modeLabel ? t(modeLabel[0], modeLabel[1]) : (state.mode || '—'));
    // The UV build reads one spectral channel of its sensor at a time, and which
    // one is part of what the measurement *is* — so it rides on that line rather
    // than claiming a row the other builds would leave empty.
    const measurement = state.meas || '—';
    $text('devctl-meas', state.uvchan ? `${measurement} · ${state.uvchan}` : measurement);

    // Values carry their unit when there is one, and are per channel, so they are
    // tagged with the channel they came from — "0.412 @0" is the only form that
    // stays readable when the channel set changes underneath.
    const values = state.vals || [];
    const channels = state.chans || [];
    const units = state.units || '';
    $text('devctl-vals', values.length
        ? values.map((v, i) => `${v}${units ? ' ' + units : ''}${channels[i] != null ? ' @' + channels[i] : ''}`).join('   ')
        : '—');

    let blank = t('devctl.blank_na', 'Not needed');
    if (state.needsblank) {
        blank = state.blanked ? t('devctl.blank_done', 'Blanked')
                              : t('devctl.blank_missing', 'Not blanked');
    }
    // Gain and integration time per sensor, with the one the buttons act on
    // marked the way the device marks it on its own screen. Without this the
    // operator has to press and watch the numbers to find out what moved — and
    // on the builds with no channel panel there was nowhere to read them at all.
    const gains = state.gains || [];
    const itimes = state.itimes || [];
    const selected = state.sel;
    $text('devctl-settings', gains.length
        ? gains.map((gain, i) => {
            const mark = (i === selected) ? '|' : '';
            return `${mark}${deviceSensorTag(state, i)} ${gain || '?'}·${itimes[i] || '?'}`;
        }).join('   ')
        : '—');

    $text('devctl-blank', blank);
    $text('devctl-bat', state.bat ? `${state.bat} V` : '—');
}

// The firmware keeps the gain / integration-time target on the DEVICE, not on
// the screen (colorimeter.selected_sensor), and steps it with Right:
// none -> first sensor -> … -> none. "None" is a real position: the two buttons
// then act on every sensor at once. So the label has to name the current target
// — "Cycle gain" alone would leave the operator guessing which cuvette moved.
function deviceSensorTag(state, index) {
    const channels = state.chans || [];
    if (channels[index] != null) return `@${channels[index]}`;
    return `#${index + 1}`;   // builds with fixed sensors report no channel list
}

function deviceGainTarget(state) {
    const selected = state.sel;
    if (selected === null || selected === undefined || selected === '') {
        return t('devctl.target_all', 'all sensors');
    }
    return deviceSensorTag(state, selected);
}

function deviceButtonFunction(state, name) {
    // Raw Count is the screen where gain and integration time are dialled in,
    // so leaving it is what commits them for the run — "Open menu" names the
    // mechanism rather than what the operator is doing. Session-scoped only:
    // the device cannot rewrite configuration.json, because CircuitPython mounts
    // its filesystem read-only while code.py runs.
    if (state.mode === 'MEASURE' && name === 'menu' && state.meas === 'Raw Count') {
        return ['devctl.fn.save_settings', 'Save settings'];
    }
    // Right in MEASURE mode is not the same control on every device: on the
    // multi-sensor builds it picks which sensor gain/integration time act on, on
    // the UV build it steps the sensor's own spectral channel, and on the plain
    // build it does nothing. The firmware says which in `caps`, so the label
    // comes from there instead of from a version guess.
    if (state.mode === 'MEASURE' && name === 'right') {
        const caps = state.caps || [];
        if (caps.indexOf('uvchannel') !== -1) return ['devctl.fn.next_uv_channel', 'Next spectral channel'];
        if (caps.indexOf('selsensor') !== -1) return ['devctl.fn.next_sensor', 'Next sensor'];
        return null;
    }
    const table = DEVICE_BUTTON_FUNCTIONS[state.mode];
    if (!table) return null;
    return table[name] || table._any || null;
}

// Suffix appended to a button's label at render time, for the controls whose
// meaning depends on the device's current selection rather than on its screen.
function deviceButtonTargetSuffix(state, name) {
    if (state.mode !== 'MEASURE') return '';
    const caps = state.caps || [];
    if (caps.indexOf('selsensor') === -1) return '';
    if (name === 'gain' || name === 'itime') {
        return ` — ${deviceGainTarget(state)}`;
    }
    if (name === 'right') {
        return ` (${t('devctl.target_now', 'now')}: ${deviceGainTarget(state)})`;
    }
    return '';
}

function renderDeviceKeypad(state) {
    if (!deviceKeypadBuilt) buildDeviceKeypad();
    for (const button of DEVICE_BUTTONS) {
        const el = document.getElementById(`devctl-btn-${button.name}`);
        if (!el) continue;
        const fn = deviceButtonFunction(state, button.name);
        const unavailable = fn && fn[0] === 'devctl.fn.unavailable_hid';
        const label = (fn ? t(fn[0], fn[1]) : t('devctl.fn.none', 'No effect here'))
            + (fn ? deviceButtonTargetSuffix(state, button.name) : '');
        el.disabled = !fn || unavailable;
        el.classList.toggle('devctl-btn--idle', !fn || unavailable);
        // The key face is a keycap: the board's mark plus the function. The
        // firmware's own name for the button (`menu`, `itime`) rides in the hint
        // instead, which is where it is wanted — when matching this panel
        // against a firmware handler or a log line, not while pressing keys.
        el.setAttribute('data-hint', `${button.name} · ${label}`);
        el.setAttribute('aria-label', `${button.name}: ${label}`);
        setDeviceButtonLabel(el, label);
    }
}

// A key is a fixed box and its label is one line, so a label wider than the box
// is scrolled through it on a loop rather than wrapped or clipped. Two copies
// chase each other so the loop has no blank sweep; the shift is one copy plus
// the gap between them, which is what makes the wrap invisible.
const DEVICE_MARQUEE_SPEED = 18;    // px per second — a reading pace, not a ticker
const DEVICE_MARQUEE_GAP = 28;      // px between the two copies; matches the CSS

function setDeviceButtonLabel(el, label) {
    const fnEl = el.querySelector('.devctl-btn-fn');
    if (!fnEl) return;
    // The label is its own cache key: re-writing an unchanged one on every poll
    // would restart the animation every 1.5 s and the text would never get far
    // enough to be read. It also keeps the measuring reflow off the poll path.
    if (fnEl.dataset.label === label) return;

    fnEl.dataset.label = label;
    fnEl.classList.remove('devctl-btn-fn--scroll');
    const track = document.createElement('span');
    track.className = 'devctl-btn-fn-track';
    const copy = document.createElement('span');
    copy.textContent = label;
    track.appendChild(copy);
    fnEl.innerHTML = '';
    fnEl.appendChild(track);

    const room = fnEl.clientWidth;
    const width = copy.offsetWidth;
    // Zero room means the panel is not laid out yet (collapsed, or hidden while
    // offline). Forget the cache rather than deciding it fits — the next render
    // with the panel open measures for real.
    if (!room) { delete fnEl.dataset.label; return; }
    if (width <= room) return;

    const second = copy.cloneNode(true);
    second.setAttribute('aria-hidden', 'true');
    track.appendChild(second);
    const shift = width + DEVICE_MARQUEE_GAP;
    fnEl.style.setProperty('--devctl-marquee-shift', `${shift}px`);
    fnEl.style.setProperty('--devctl-marquee-time', `${(shift / DEVICE_MARQUEE_SPEED).toFixed(1)}s`);
    fnEl.classList.add('devctl-btn-fn--scroll');
}

// Which labels overflow depends on the key width, and that steps with the
// window. Drop the caches and re-measure once the resize settles.
function remeasureDeviceLabels() {
    for (const button of DEVICE_BUTTONS) {
        const el = document.getElementById(`devctl-btn-${button.name}`);
        const fnEl = el && el.querySelector('.devctl-btn-fn');
        if (fnEl) delete fnEl.dataset.label;
    }
    if (deviceState) renderDeviceKeypad(deviceState);
}

function buildDeviceKeypad() {
    for (const cluster of ['topleft', 'topright', 'dpad', 'ab']) {
        const host = document.getElementById(`devctl-${cluster}`);
        if (!host) continue;
        host.innerHTML = DEVICE_BUTTONS
            .filter(b => b.cluster === cluster)
            .map(b => `
                <button type="button" id="devctl-btn-${b.name}" class="devctl-btn devctl-btn--${b.slot}"
                        onclick="pressDeviceButton('${b.name}')">
                    <span class="devctl-btn-glyph" aria-hidden="true">${b.glyph}</span>
                    <span class="devctl-btn-fn"></span>
                </button>`)
            .join('');
    }
    deviceKeypadBuilt = true;
}

// ── actions ─────────────────────────────────────────────────────────────────

async function pressDeviceButton(name) {
    const el = document.getElementById(`devctl-btn-${name}`);
    if (el) el.disabled = true;
    try {
        const res = await fetch('/device/button', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ button: name }),
        });
        const data = await res.json();
        if (data.status === 'success') {
            // The press may have changed the screen, so a button set drawn for
            // the old one is wrong immediately. The route hands back the new
            // state with the ACK precisely so there is no window where it is.
            // A half-made channel selection is left alone — no button changes
            // channels, so discarding it here would only lose the user's work.
            if (data.state) applyDeviceState(data.state);
            return;
        }
        if (res.status === 409) {
            setDeviceControlStatus('busy', t('devctl.busy',
                'Unavailable while a reading session is running'));
            return;
        }
        showDeviceControlError(data.message || t('devctl.press_failed', 'The device refused that button'));
    } catch (err) {
        showDeviceControlError(t('devctl.offline', 'No colorimeter found'));
    } finally {
        // Whatever happened, the next poll re-derives which buttons are live.
        if (deviceState) renderDeviceKeypad(deviceState);
    }
}

function showDeviceControlError(message) {
    // Only ever called for something the user just did, never for a background
    // poll — a controller that pops an alert every 1.5 s while the cable is out
    // is unusable. Honours "Disable popups" the same way the rest of the app does.
    if (typeof Swal === 'undefined' || getBtnChecked('no-swal-checkbox')) {
        setDeviceControlStatus('offline', message);
        return;
    }
    Swal.fire({ icon: 'error', title: t('devctl.error_title', 'Device controller'), text: message });
}

// ── active channels ─────────────────────────────────────────────────────────

function deviceSupportsChannels(state) {
    return (state.caps || []).indexOf('channels') !== -1 && (state.maxchan || 0) > 1;
}

function renderDeviceChannels(state) {
    const panel = document.getElementById('devctl-channels');
    const boxes = document.getElementById('devctl-channel-boxes');
    const apply = document.getElementById('devctl-channels-apply');
    if (!panel || !boxes || !apply) return;
    if (!deviceSupportsChannels(state)) {
        panel.classList.add('hidden');
        return;
    }
    panel.classList.remove('hidden');

    const deviceChannels = state.chans || [];
    renderDeviceChannelsPending(deviceChannels);

    // A half-made selection is the user's, not the device's. Leave the boxes
    // alone until it is applied or a press resets it, or the poll would tick the
    // checkboxes back every 1.5 s while they are being used.
    if (devicePendingChannels) {
        apply.disabled = !devicePendingChannels.length;
        return;
    }

    const gains = state.gains || [];
    const itimes = state.itimes || [];
    boxes.innerHTML = '';
    for (let channel = 0; channel < state.maxchan; channel++) {
        const onDevice = deviceChannels.indexOf(channel);
        const label = document.createElement('label');
        label.className = 'devctl-channel';

        const box = document.createElement('input');
        box.type = 'checkbox';
        box.value = String(channel);
        box.checked = onDevice !== -1;
        box.addEventListener('change', onDeviceChannelToggle);

        const id = document.createElement('span');
        id.className = 'devctl-channel-id';
        id.textContent = `@${channel}`;

        // Gain and integration time are only known for channels the device has a
        // sensor open on; an unticked channel has no settings to show yet. Set as
        // text, not markup — it is device output, and this panel is the one place
        // a garbled serial line reaches the DOM.
        const detail = document.createElement('span');
        detail.className = 'devctl-channel-detail';
        // The gain / integration-time buttons act on this one: say so here as
        // well, since this panel is where those two values are read.
        const isTarget = onDevice !== -1 && onDevice === state.sel;
        detail.textContent = onDevice === -1 ? '' :
            `${gains[onDevice] || '?'} · ${itimes[onDevice] || '?'}${isTarget ? '  ◀' : ''}`;
        label.classList.toggle('devctl-channel--target', isTarget);

        label.append(box, id, detail);
        boxes.appendChild(label);
    }
    apply.disabled = true;
}

// Say when the boxes no longer describe the device.
//
// Unticking a channel stops the poll redrawing the boxes (devicePendingChannels
// above) so a half-made selection is not clobbered mid-edit — but that leaves
// the panel showing a channel set the device is not using, with nothing to
// distinguish "off" from "about to be turned off". An operator who unticked @2
// then went to calibrate got refused for a channel they believed was already
// out, and the only clue was the Apply button they had not pressed.
//
// Built in JS rather than a data-i18n element: it names the device's channels,
// which change, and the i18n pass sets textContent from a fixed catalog string.
function renderDeviceChannelsPending(deviceChannels) {
    const note = document.getElementById('devctl-channels-pending');
    if (!note) return;
    const staged = devicePendingChannels;
    const differs = !!staged && (
        staged.length !== deviceChannels.length ||
        staged.some((channel, i) => channel !== deviceChannels[i]));
    note.classList.toggle('hidden', !differs);
    if (!differs) return;
    const inUse = deviceChannels.length
        ? deviceChannels.map(channel => `@${channel}`).join(' ')
        : t('devctl.channels_pending_none', 'none');
    note.textContent = `${t('devctl.channels_pending',
        'Not sent yet — the device is still using')} ${inUse}. ${t('devctl.channels_pending_apply',
        'Press Apply channels to change it.')}`;
}

function readDeviceChannelBoxes() {
    return Array.from(document.querySelectorAll('#devctl-channel-boxes input:checked'))
        .map(input => parseInt(input.value, 10));
}

function onDeviceChannelToggle() {
    devicePendingChannels = readDeviceChannelBoxes();
    const apply = document.getElementById('devctl-channels-apply');
    if (apply) apply.disabled = !devicePendingChannels.length;
    // On the tick, not on the next poll: 1.5 s is long enough to untick a box,
    // read the panel, and conclude the change already took.
    renderDeviceChannelsPending((deviceState && deviceState.chans) || []);
}

async function applyDeviceChannels() {
    const channels = readDeviceChannelBoxes();
    if (!channels.length) return;
    const apply = document.getElementById('devctl-channels-apply');
    if (apply) apply.disabled = true;
    try {
        const res = await fetch('/device/channels', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channels: channels }),
        });
        const data = await res.json();
        if (data.status === 'success') {
            devicePendingChannels = null;
            if (data.state) applyDeviceState(data.state);
            return;
        }
        showDeviceControlError(data.message || t('devctl.channels_failed', 'The device refused that channel set'));
    } catch (err) {
        showDeviceControlError(t('devctl.offline', 'No colorimeter found'));
    } finally {
        if (apply) apply.disabled = false;
    }
}

// ── the device's menu, as a bar ──────────────────────────────────────────────
// The entries are built on the device (default measurements + every key in its
// calibrations.json + Concentration / About / Settings), so the host has to ask
// for them: `GET /device/menu` once, then `POST` an index to open one. The list
// changes only when the device reboots, which is why it is not part of the
// 1.5 s state poll — `menupos` in the state is what moves.

let deviceMenuItems = null;      // null = not fetched yet for this connection
let deviceMenuPending = false;   // a fetch or a selection is in flight

function deviceSupportsMenu(state) {
    return (state.caps || []).indexOf('menu') !== -1;
}

function renderDeviceMenu(state) {
    const panel = document.getElementById('devctl-menu');
    if (!panel) return;
    if (!deviceSupportsMenu(state)) {
        // An older build cannot list its menu, and a bar that guessed the
        // entries would be a bar that opens the wrong one.
        panel.classList.add('hidden');
        return;
    }
    panel.classList.remove('hidden');
    if (deviceMenuItems === null) {
        loadDeviceMenu();
        return;
    }
    drawDeviceMenuItems(state);
}

async function loadDeviceMenu() {
    if (deviceMenuPending) return;
    deviceMenuPending = true;
    try {
        const res = await fetch('/device/menu');
        const data = await res.json();
        if (data.status === 'success' && Array.isArray(data.items)) {
            deviceMenuItems = data.items;
            if (deviceState) drawDeviceMenuItems(deviceState);
        }
        // A failure leaves the list null so the next poll asks again — the
        // device may simply have been mid-rebuild when the question arrived.
    } catch (err) {
        /* same: retried by the next poll */
    } finally {
        deviceMenuPending = false;
    }
}

function drawDeviceMenuItems(state) {
    const host = document.getElementById('devctl-menu-items');
    if (!host || !deviceMenuItems) return;

    // The device highlights one entry (`menupos`) and is *on* one of them
    // (`meas`, or the screen it opened) — two different things, and the bar
    // shows both: the highlighted entry is where the keypad's Up/Down sit, the
    // open one is what the device is actually doing.
    const openName = deviceMenuOpenName(state);
    host.innerHTML = '';
    deviceMenuItems.forEach((item, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'devctl-menu-item';
        button.textContent = item || `#${index + 1}`;
        button.classList.toggle('devctl-menu-item--open', !!openName && item === openName);
        button.classList.toggle('devctl-menu-item--cursor', index === state.menupos);
        button.disabled = deviceMenuPending;
        button.setAttribute('data-hint', t('devctl.menu_open_hint', 'Open on the device') + ` — ${item}`);
        button.addEventListener('click', () => selectDeviceMenu(index));
        host.appendChild(button);
    });
}

// Which entry the device currently has open. In Measure that is the measurement
// itself; the three built-in screens name themselves through the mode.
function deviceMenuOpenName(state) {
    if (state.mode === 'SETTINGS') return 'Settings';
    if (state.mode === 'CONCENTRATION') return 'Concentration';
    if (state.mode === 'MEASURE') return state.meas || null;
    return null;
}

async function selectDeviceMenu(index) {
    if (deviceMenuPending) return;
    deviceMenuPending = true;
    if (deviceState) drawDeviceMenuItems(deviceState);   // disables the row
    try {
        const res = await fetch('/device/menu', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: index }),
        });
        const data = await res.json();
        if (data.status === 'success') {
            deviceMenuPending = false;
            if (data.state) applyDeviceState(data.state);
            return;
        }
        if (res.status === 409) {
            setDeviceControlStatus('busy', t('devctl.busy',
                'Unavailable while a reading session is running'));
            return;
        }
        showDeviceControlError(data.message || t('devctl.menu_failed', 'The device refused that menu entry'));
    } catch (err) {
        showDeviceControlError(t('devctl.offline', 'No colorimeter found'));
    } finally {
        deviceMenuPending = false;
        if (deviceState) drawDeviceMenuItems(deviceState);
    }
}

// ── concentration ───────────────────────────────────────────────────────────
// The value the device sends as metadata with every session. Its keypad can only
// *step* it (+1, +10, +100 and back), so dialling in 250 was twelve presses; the
// firmware's CONC: takes it whole. The panel is mounted **only while the device
// is on its Concentration screen**, because that is the screen the value belongs
// to — the same rule the device itself follows.

let deviceConcUnits = null;    // null = not fetched yet for this connection
let deviceConcPending = false;
// True once the operator has typed or picked something not yet sent. Without it
// the 1.5 s poll would overwrite a half-typed value with the device's.
let deviceConcDirty = false;

function deviceSupportsConcentration(state) {
    return (state.caps || []).indexOf('conc') !== -1;
}

function renderDeviceConcentration(state) {
    const panel = document.getElementById('devctl-conc');
    if (!panel) return;
    const onScreen = state.mode === 'CONCENTRATION' && deviceSupportsConcentration(state);
    panel.classList.toggle('hidden', !onScreen);
    if (!onScreen) {
        // Leaving the screen drops the half-made edit with it: it was an edit to
        // a screen the device is no longer on.
        deviceConcDirty = false;
        return;
    }
    if (deviceConcUnits === null) {
        loadDeviceConcentrationUnits(state);
        return;
    }
    drawDeviceConcentration(state);
}

async function loadDeviceConcentrationUnits(state) {
    if (deviceConcPending) return;
    deviceConcPending = true;
    try {
        const res = await fetch('/device/concentration');
        const data = await res.json();
        if (data.status === 'success' && Array.isArray(data.units)) {
            deviceConcUnits = data.units;
            if (deviceState) drawDeviceConcentration(deviceState);
        }
    } catch (err) {
        /* retried by the next poll */
    } finally {
        deviceConcPending = false;
    }
}

function drawDeviceConcentration(state) {
    const unitSelect = document.getElementById('devctl-conc-unit');
    const input = document.getElementById('devctl-conc-value');
    const current = document.getElementById('devctl-conc-current');
    if (!unitSelect || !input || !current) return;

    // "" is the firmware's "not applicable" — here it means Unknown, which is a
    // value on this screen and not a blank one.
    const value = (state.conc === undefined || state.conc === null || state.conc === '')
        ? null : state.conc;
    const unit = state.cunit || '';
    current.textContent = value === null
        ? `${t('devctl.conc_unknown_value', 'Unknown')}${unit ? ' ' + unit : ''}`
        : `${value}${unit ? ' ' + unit : ''}`;

    fillDeviceUnitSelect(unitSelect, deviceConcUnits);
    // The device's own value and unit are what the fields show until the
    // operator touches them — then they are the operator's until sent.
    if (!deviceConcDirty) {
        input.value = value === null ? '' : value;
        if (unit) unitSelect.value = unit;
    }
    input.disabled = deviceConcPending;
    unitSelect.disabled = deviceConcPending;
    $disabled('devctl-conc-set', deviceConcPending);
    $disabled('devctl-conc-unknown', deviceConcPending);
}

function $disabled(id, disabled) {
    const el = document.getElementById(id);
    if (el) el.disabled = !!disabled;
}

function onDeviceConcentrationEdited() {
    deviceConcDirty = true;
}

function applyDeviceConcentration() {
    const input = document.getElementById('devctl-conc-value');
    if (!input) return;
    const text = input.value.trim();
    if (text === '') {
        // An empty box is not an accident to be rejected — it is Unknown, and
        // there is a button that says so; use it rather than guessing.
        showDeviceControlError(t('devctl.conc_empty',
            'Enter a value, or use Unknown to clear it on the device'));
        return;
    }
    const value = Number(text);
    if (!isFinite(value) || value < 0) {
        showDeviceControlError(t('devctl.conc_invalid', 'Concentration must be zero or more'));
        return;
    }
    sendDeviceConcentration(value);
}

function clearDeviceConcentration() {
    sendDeviceConcentration(null);
}

async function sendDeviceConcentration(value) {
    if (deviceConcPending) return;
    const unitSelect = document.getElementById('devctl-conc-unit');
    const unit = unitSelect ? unitSelect.value : '';
    deviceConcPending = true;
    if (deviceState) drawDeviceConcentration(deviceState);
    try {
        const res = await fetch('/device/concentration', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: value, unit: unit || undefined }),
        });
        const data = await res.json();
        if (data.status === 'success') {
            // Sent: the fields go back to following the device, which is now the
            // authority on what the concentration is.
            deviceConcDirty = false;
            deviceConcPending = false;
            if (data.state) applyDeviceState(data.state);
            return;
        }
        if (res.status === 409) {
            setDeviceControlStatus('busy', t('devctl.busy',
                'Unavailable while a reading session is running'));
            return;
        }
        showDeviceControlError(data.message || t('devctl.conc_failed', 'The device refused that concentration'));
    } catch (err) {
        showDeviceControlError(t('devctl.offline', 'No colorimeter found'));
    } finally {
        deviceConcPending = false;
        if (deviceState) drawDeviceConcentration(deviceState);
    }
}

// ── settings (timeout + interval) ───────────────────────────────────────────
// The Settings screen's own pair. Same shape as the concentration form and the
// same rule: mounted only while the device is on that screen. The device is the
// authority on whether the pair is legal — the timeout has to outlast the
// interval, or a run times out before its first reading — so the refusal comes
// back from it rather than being second-guessed here.

let deviceTimingUnits = null;
let deviceTimingPending = false;
let deviceTimingDirty = false;

function deviceSupportsTiming(state) {
    return (state.caps || []).indexOf('timing') !== -1;
}

function renderDeviceTiming(state) {
    const panel = document.getElementById('devctl-timing');
    if (!panel) return;
    const onScreen = state.mode === 'SETTINGS' && deviceSupportsTiming(state);
    panel.classList.toggle('hidden', !onScreen);
    if (!onScreen) {
        deviceTimingDirty = false;
        return;
    }
    if (deviceTimingUnits === null) {
        loadDeviceTimingUnits();
        return;
    }
    drawDeviceTiming(state);
}

async function loadDeviceTimingUnits() {
    if (deviceTimingPending) return;
    deviceTimingPending = true;
    try {
        const res = await fetch('/device/timing');
        const data = await res.json();
        if (data.status === 'success' && Array.isArray(data.units)) {
            deviceTimingUnits = data.units;
            if (deviceState) drawDeviceTiming(deviceState);
        }
    } catch (err) {
        /* retried by the next poll */
    } finally {
        deviceTimingPending = false;
    }
}

function drawDeviceTiming(state) {
    const current = document.getElementById('devctl-timing-current');
    const timeoutValue = document.getElementById('devctl-timeout-value');
    const timeoutUnit = document.getElementById('devctl-timeout-unit');
    const intervalValue = document.getElementById('devctl-interval-value');
    const intervalUnit = document.getElementById('devctl-interval-unit');
    if (!current || !timeoutValue || !timeoutUnit || !intervalValue || !intervalUnit) return;

    // "" is the firmware's "not applicable": for the timeout it means the run
    // has no timeout at all, which is a setting rather than a blank.
    const hasTimeout = state.timeout !== undefined && state.timeout !== null && state.timeout !== '';
    if (current) {
        const timeoutText = hasTimeout
            ? `${state.timeout} ${state.timeoutunit || ''}`.trim()
            : t('devctl.timing_none', 'no timeout');
        current.textContent = `${timeoutText} · ${state.interval || '—'} ${state.intervalunit || ''}`.trim();
    }

    fillDeviceUnitSelect(timeoutUnit, deviceTimingUnits);
    fillDeviceUnitSelect(intervalUnit, deviceTimingUnits);
    if (!deviceTimingDirty) {
        timeoutValue.value = hasTimeout ? state.timeout : '';
        if (state.timeoutunit) timeoutUnit.value = state.timeoutunit;
        intervalValue.value = (state.interval === undefined || state.interval === null) ? '' : state.interval;
        if (state.intervalunit) intervalUnit.value = state.intervalunit;
    }
    for (const el of [timeoutValue, timeoutUnit, intervalValue, intervalUnit]) {
        el.disabled = deviceTimingPending;
    }
    $disabled('devctl-timing-set', deviceTimingPending);
    $disabled('devctl-timing-none', deviceTimingPending);
}

function fillDeviceUnitSelect(select, units) {
    if (!select || !units || select.options.length === units.length) return;
    select.innerHTML = '';
    units.forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        select.appendChild(option);
    });
}

function onDeviceTimingEdited() {
    deviceTimingDirty = true;
}

function applyDeviceTiming() {
    sendDeviceTiming(false);
}

function clearDeviceTimeout() {
    sendDeviceTiming(true);
}

async function sendDeviceTiming(noTimeout) {
    if (deviceTimingPending) return;
    const timeoutText = (document.getElementById('devctl-timeout-value') || {}).value || '';
    const intervalText = (document.getElementById('devctl-interval-value') || {}).value || '';
    const timeoutUnit = (document.getElementById('devctl-timeout-unit') || {}).value || '';
    const intervalUnit = (document.getElementById('devctl-interval-unit') || {}).value || '';

    const interval = Number(intervalText);
    if (intervalText.trim() === '' || !isFinite(interval) || interval <= 0) {
        showDeviceControlError(t('devctl.timing_interval_invalid', 'Interval must be more than zero'));
        return;
    }
    let timeout = null;
    if (!noTimeout) {
        if (timeoutText.trim() === '') {
            showDeviceControlError(t('devctl.timing_timeout_empty',
                'Enter a timeout, or use No timeout to run until stopped'));
            return;
        }
        timeout = Number(timeoutText);
        if (!isFinite(timeout) || timeout < 0) {
            showDeviceControlError(t('devctl.timing_timeout_invalid', 'Timeout must be zero or more'));
            return;
        }
    }

    deviceTimingPending = true;
    if (deviceState) drawDeviceTiming(deviceState);
    try {
        const res = await fetch('/device/timing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                timeout_value: timeout,
                timeout_unit: timeout === null ? undefined : timeoutUnit,
                interval_value: interval,
                interval_unit: intervalUnit,
            }),
        });
        const data = await res.json();
        if (data.status === 'success') {
            deviceTimingDirty = false;
            deviceTimingPending = false;
            if (data.state) applyDeviceState(data.state);
            return;
        }
        if (res.status === 409) {
            setDeviceControlStatus('busy', t('devctl.busy',
                'Unavailable while a reading session is running'));
            return;
        }
        // The device's own reason ("timeout is not longer than the interval") is
        // the actionable part, so it is shown rather than a generic refusal.
        showDeviceControlError(data.message || t('devctl.timing_failed', 'The device refused those settings'));
    } catch (err) {
        showDeviceControlError(t('devctl.offline', 'No colorimeter found'));
    } finally {
        deviceTimingPending = false;
        if (deviceState) drawDeviceTiming(deviceState);
    }
}

// ── raw count calibration ───────────────────────────────────────────────────
// Equalising what the channels count when every holder shows them the same LED
// (the firmware's raw_count_calibration.md). Mounted only while the device is on
// its Sensor Cal screen, for the same reason the Concentration and Settings
// forms are: that is the screen the operator set the conditions up on.
//
// Deliberately not an editable form. The numbers come from a measurement, not
// from a preference, and the one thing a human should be typing is the array
// into configuration.json — which is why the array is shown to be copied rather
// than offered as four inputs to nudge.

let deviceCalibPending = false;
let deviceCalibFactors = null;

function deviceSupportsCalibration(state) {
    return (state.caps || []).indexOf('calib') !== -1;
}

function renderDeviceCalibration(state) {
    const panel = document.getElementById('devctl-calib');
    if (!panel) return;
    const onScreen = state.mode === 'CALIBRATION' && deviceSupportsCalibration(state);
    panel.classList.toggle('hidden', !onScreen);
    if (!onScreen) return;
    if (deviceCalibFactors === null) {
        loadDeviceCalibration();
        return;
    }
    drawDeviceCalibration(state);
}

async function loadDeviceCalibration() {
    if (deviceCalibPending) return;
    deviceCalibPending = true;
    try {
        const res = await fetch('/device/calibration');
        const data = await res.json();
        if (data.status === 'success' && Array.isArray(data.factors)) {
            deviceCalibFactors = data.factors;
            if (deviceState) drawDeviceCalibration(deviceState);
        }
    } catch (err) {
        /* retried by the next poll */
    } finally {
        deviceCalibPending = false;
    }
}

function drawDeviceCalibration(state) {
    // The live line reads from STATE's rcf — the ACTIVE channels, tagged with
    // the channel they belong to, exactly as the values and gains above are.
    const factors = state.rcf || [];
    const channels = state.chans || [];
    $text('devctl-calib-current', factors.length
        ? factors.map((factor, i) => `×${Number(factor).toFixed(3)}${channels[i] != null ? ' @' + channels[i] : ''}`).join('   ')
        : '—');

    // The copyable line is the WHOLE multiplexer-indexed array from
    // /device/calibration, because that is the shape configuration.json holds:
    // writing back only the active channels would blank the factors of every
    // holder not currently in use.
    const array = document.getElementById('devctl-calib-array');
    if (array) {
        array.textContent = deviceCalibFactors
            ? `"raw_count_factor": [${deviceCalibFactors.map(f => Number(f).toFixed(4)).join(', ')}]`
            : '—';
    }

    // Fewer than two channels and there is nothing to scale against — the
    // device refuses the pass ("only channel 0 active: need 2 to compare").
    // Say so before the press rather than after it, and take the button away:
    // an enabled Calibrate that always fails reads as a broken device.
    const tooFew = channels.length < 2;
    const warning = document.getElementById('devctl-calib-warn');
    if (warning) warning.classList.toggle('hidden', !tooFew);
    $disabled('devctl-calib-run', deviceCalibPending || tooFew);
    // Clear stays live. Factors set earlier (or loaded from configuration.json)
    // are still in force on the channel that is active, and resetting them is
    // exactly what an operator narrowing down to one channel may want.
    $disabled('devctl-calib-clear', deviceCalibPending);
}

function runDeviceCalibration() {
    sendDeviceCalibration({ run: true });
}

function clearDeviceCalibration() {
    // An empty body is "clear them", not "send nothing" — see the route.
    sendDeviceCalibration({});
}

async function sendDeviceCalibration(payload) {
    if (deviceCalibPending) return;
    deviceCalibPending = true;
    if (deviceState) drawDeviceCalibration(deviceState);
    try {
        const res = await fetch('/device/calibration', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (data.status === 'success') {
            if (Array.isArray(data.factors)) deviceCalibFactors = data.factors;
            deviceCalibPending = false;
            if (data.state) applyDeviceState(data.state);
            return;
        }
        if (res.status === 409) {
            setDeviceControlStatus('busy', t('devctl.busy',
                'Unavailable while a reading session is running'));
            return;
        }
        // The device's refusal names the holder to look at ("channel 2 reading
        // zero: LED off?"), which is the whole point of showing it.
        showDeviceControlError(data.message || t('devctl.calib_failed',
            'The device refused the calibration'));
    } catch (err) {
        showDeviceControlError(t('devctl.offline', 'No colorimeter found'));
    } finally {
        deviceCalibPending = false;
        if (deviceState) drawDeviceCalibration(deviceState);
    }
}

// ── wiring ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const section = document.getElementById('device-control-section');
    if (!section) return;
    if (!deviceControlEnabled()) section.classList.add('hidden');
    // The switch remembers its position across reloads: a user who parked the
    // port for a firmware update should not find the app holding it again after
    // the browser reloads.
    const linkToggle = document.getElementById('devctl-link-toggle');
    if (linkToggle && typeof USER_SETTINGS !== 'undefined') {
        linkToggle.checked = USER_SETTINGS.device_link_enabled !== false;
    }
    // Typing in the concentration fields takes them off the poll's redraw until
    // the value is sent (see deviceConcDirty).
    const concValue = document.getElementById('devctl-conc-value');
    const concUnit = document.getElementById('devctl-conc-unit');
    if (concValue) concValue.addEventListener('input', onDeviceConcentrationEdited);
    if (concUnit) concUnit.addEventListener('change', onDeviceConcentrationEdited);
    for (const id of ['devctl-timeout-value', 'devctl-interval-value',
                      'devctl-timeout-unit', 'devctl-interval-unit']) {
        const el = document.getElementById(id);
        if (el) el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', onDeviceTimingEdited);
    }
    // Nothing else to wire: the panel starts collapsed, and expanding it is what
    // starts the poll. A run beginning or ending is picked up by that same poll
    // (the route answers 409 for the duration), so the panel needs no hook into
    // the reading lifecycle to stay honest.
});

let deviceResizeTimer = null;
window.addEventListener('resize', () => {
    if (deviceResizeTimer) clearTimeout(deviceResizeTimer);
    deviceResizeTimer = setTimeout(remeasureDeviceLabels, 200);
});

// Stop touching the port when the tab goes away — a hidden tab polling a serial
// device is the kind of thing that keeps a port busy for no one's benefit.
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopDevicePolling();
    } else if (deviceControlExpanded() && deviceControlEnabled()) {
        startDevicePolling();
    }
});
