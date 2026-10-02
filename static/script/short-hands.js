// Utility short-hands

// Shared: the non-numeric tokens a colorimeter value cell can carry — mirror of
// src/sentinels.py (OVFL saturated, NONE nothing measured yet, INF a fully
// attenuated channel; firmware predating the token writes "inf"). Single global
// definition — do not redefine elsewhere.
const MEAS_SENTINELS = ["NONE", "OVFL", "INF", "-INF", "inf", "-inf"];
const isMeasSentinel = v => typeof v === 'string' && MEAS_SENTINELS.includes(v.trim());
// A value cell as a finite number, or null when it is not one: sentinel, blank,
// text, or an infinity — Number("Infinity") parses and must never reach a chart.
const measNumber = v => {
    if (v === null || v === undefined || isMeasSentinel(v)) return null;
    if (typeof v === 'string' && v.trim() === '') return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
};

const $id = id => document.getElementById(id);
const $text = (id, text) => {
    const element = $id(id);
    if (element) {
        element.textContent = text;
    }
};
const $append = (id, text) => { $id(id).textContent += text; };
const $disable = (ids, state = true) => ids.forEach(id => $id(id).disabled = state);
const $toggleClass = (id, cls, state) => {
    const element = $id(id);
    if (element)
        element.classList.toggle(cls, state);
}

const $qid = id => document.querySelectorAll(id)
const $toggleQueryClass = (selector, cls, state) =>
    $qid(selector).forEach(el => el.classList.toggle(cls, state));

const $hidden = (ids, state = true) => ids.forEach(id => $toggleClass(id, "hidden", state));

const getValFloat = id => parseFloat(document.getElementById(id).value);
const getValInt = id => parseInt(document.getElementById(id).value);
const getBtnChecked = id => document.getElementById(id) ? document.getElementById(id).checked : false;

function getTimeUnitValue(id = 'time-unit') {
    const element = document.getElementById(id);
    if (element && (element.style.display !== 'none' && element.style.visibility !== 'hidden')) {
        return element.value;
    }
    return null;
}

// ── Announcements to assistive technology (WCAG 4.1.3 Status Messages) ──────
// Two live regions live in the page from first paint (see templates/index.html)
// because a region inserted at the moment it has something to say is usually
// missed: the screen reader has to be observing it beforehand.
//
//   announce()      polite  — progress, results, "chart updated". Waits for a
//                             gap in speech and never interrupts.
//   announceAlert() assertive — errors and anything the user must act on.
//
// The same text written twice in a row is not re-announced by most screen
// readers, so a zero-width reset is written first.
const _announceInto = (regionId, message) => {
    const region = document.getElementById(regionId);
    if (!region || !message) return;
    region.textContent = '';
    // A frame's gap is enough for the region to be seen as changed twice.
    window.requestAnimationFrame(() => { region.textContent = String(message); });
};

const announce = message => _announceInto('a11y-live-region', message);
const announceAlert = message => _announceInto('a11y-alert-region', message);

window.announce = announce;
window.announceAlert = announceAlert;

// Writing an error into a corner of the page is not enough on its own: nothing
// tells a screen reader user it appeared. Every caller of `$showText` is an
// error path, so the text is announced as well as displayed (3.3.1).
const $showText = (id, text) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.style.display = "";
    if (text) announceAlert(text);
};

// Shared by fetchJSON and fetchJSONProgress so the session-expiry hook cannot
// end up wired into one of them and not the other.
async function _throwForResponse(response) {
    const errorData = await response.json().catch(() => ({}));
    // The server expires idle account sessions (see Config.ACCOUNT_IDLE_TIMEOUT);
    // surface that to the inactivity handler so any API call can trigger logout.
    if (response.status === 401 && errorData.code === 'session_expired'
        && typeof window.__eokSessionExpired === 'function') {
        window.__eokSessionExpired();
    }
    throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
}

async function fetchJSON(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
    };

    // Merge options, making sure to handle Method and Body if provided
    const mergedOptions = { ...defaultOptions, ...options };

    try {
        const response = await fetch(url, mergedOptions);
        if (!response.ok) await _throwForResponse(response);
        return await response.json();
    } catch (error) {
        console.error(`Fetch error for ${url}:`, error);
        throw error;
    }
}

/**
 * fetchJSON for a response worth watching arrive.
 *
 * Selecting a large data file is the case this exists for: `/get_data` expands
 * the CSV into a JSON array of row objects, so a long measurement comes back as
 * several megabytes over a dyno link. A plain `await response.json()` shows
 * nothing at all until the last byte lands, which is what made opening a big
 * file look like a dead click.
 *
 * `onProgress(receivedBytes, totalBytes)` is called as chunks arrive.
 * `totalBytes` is **null** whenever a percentage would be a guess — no
 * Content-Length, or an encoded body, where the header counts compressed bytes
 * while the reader hands back decoded ones and the ratio would run past 100%.
 * Callers show movement rather than a position in that case.
 *
 * Streaming is a progressive enhancement: anywhere `body.getReader` or
 * TextDecoder is missing this is exactly fetchJSON.
 */
async function fetchJSONProgress(url, onProgress, options = {}) {
    const mergedOptions = {
        headers: { 'Content-Type': 'application/json' },
        ...options
    };

    try {
        const response = await fetch(url, mergedOptions);
        if (!response.ok) await _throwForResponse(response);

        const body = response.body;
        if (!body || typeof body.getReader !== 'function' || typeof TextDecoder === 'undefined') {
            return await response.json();
        }

        const declared = parseInt(response.headers.get('Content-Length') || '', 10);
        const encoded = response.headers.get('Content-Encoding');
        const total = (!encoded && isFinite(declared) && declared > 0) ? declared : null;

        const reader = body.getReader();
        // Decoded incrementally rather than buffering the raw bytes and
        // concatenating at the end: for a multi-megabyte payload that would hold
        // the whole body twice over.
        const decoder = new TextDecoder('utf-8');
        const parts = [];
        let received = 0;

        for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            received += value.length;
            parts.push(decoder.decode(value, { stream: true }));
            if (typeof onProgress === 'function') onProgress(received, total);
        }
        parts.push(decoder.decode());

        return JSON.parse(parts.join(''));
    } catch (error) {
        console.error(`Fetch error for ${url}:`, error);
        throw error;
    }
}

/** Bytes as something a person reads, for the spinner's detail line. */
function formatBytes(bytes) {
    if (!isFinite(bytes) || bytes < 0) return '';
    if (bytes < 1024) return bytes + ' B';
    const units = ['KB', 'MB', 'GB'];
    let value = bytes / 1024;
    let i = 0;
    while (value >= 1024 && i < units.length - 1) {
        value /= 1024;
        i++;
    }
    return (value >= 10 ? value.toFixed(0) : value.toFixed(1)) + ' ' + units[i];
}

/* The controls that only happen to be <button> for keyboard/AT reasons and keep
   their surrounding typography. Mirrors the `:not(...)` chain the global button
   styling in style.css uses. */
const NON_BUTTON_CONTROLS = '.swal2-confirm, .swal2-deny, .swal2-styled, .folder-section-toggle, .logo-btn, .toggle-container';

/**
 * Shrinks button text to fit within one line by reducing font size
 * @param {HTMLElement|string} button - Button element or selector
 * @param {number} minFontSize - Minimum font size in rem (default: 0.6)
 * @param {number} maxFontSize - Maximum font size in rem (default: 0.95)
 */
function shrinkButtonTextToFit(button, minFontSize = 0.6, maxFontSize = 0.95) {
    const btn = typeof button === 'string' ? document.querySelector(button) : button;
    if (!btn) return;
    // Buttons that are not styled as buttons — section headings, the logo, the
    // theme cycle — take their size from the element they stand in. Shrinking
    // them to the 0.95rem button scale flattens the type hierarchy.
    if (btn.matches(NON_BUTTON_CONTROLS)) return;

    // Store original font size if not already stored
    if (!btn.dataset.originalFontSize) {
        const computedStyle = window.getComputedStyle(btn);
        btn.dataset.originalFontSize = parseFloat(computedStyle.fontSize);
    }

    // Reset to max font size
    btn.style.fontSize = `${maxFontSize}rem`;

    // Check if text overflows
    const isOverflowing = btn.scrollWidth > btn.clientWidth;

    if (isOverflowing) {
        let fontSize = maxFontSize;
        const step = 0.05; // Decrease by 0.05rem each iteration

        // Reduce font size until text fits or minimum is reached
        while (btn.scrollWidth > btn.clientWidth && fontSize > minFontSize) {
            fontSize -= step;
            btn.style.fontSize = `${fontSize}rem`;
        }
    }
}

/**
 * Apply shrink-to-fit to all buttons or specific selector
 * @param {string} selector - CSS selector for buttons (default: 'button:not(.swal2-confirm):not(.swal2-deny):not(.swal2-styled)')
 */
function shrinkAllButtonsToFit(selector = `button:not(${NON_BUTTON_CONTROLS.split(', ').join('):not(')})`) {
    const buttons = document.querySelectorAll(selector);
    buttons.forEach(btn => shrinkButtonTextToFit(btn));
}
