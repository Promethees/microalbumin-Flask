// Utility short-hands

// Shared: element-wise strict comparison of flat arrays (used by navigation.js,
// data-handling.js). Single global definition — do not redefine elsewhere.
function arraysEqual(arr1, arr2) {
    if (arr1.length !== arr2.length) return false;
    return arr1.every((value, index) => value === arr2[index]);
}
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
// Two live regions live in the page from first paint (templates/index.html)
// because a region inserted at the moment it has something to say is usually
// missed: the screen reader has to be observing it beforehand.
//
//   announce()      polite    — progress, results, "chart updated". Waits for a
//                               gap in speech and never interrupts.
//   announceAlert() assertive — errors, and anything the user must act on.
//
// The same text written twice in a row is not re-announced by most screen
// readers, so the region is cleared for a frame first.
const _announceInto = (regionId, message) => {
    const region = document.getElementById(regionId);
    if (!region || !message) return;
    region.textContent = '';
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

/**
 * Shrinks button text to fit within one line by reducing font size
 * @param {HTMLElement|string} button - Button element or selector
 * @param {number} minFontSize - Minimum font size in rem (default: 0.6)
 * @param {number} maxFontSize - Maximum font size in rem (default: 0.95)
 */
function shrinkButtonTextToFit(button, minFontSize = 0.6, maxFontSize = 0.95) {
    const btn = typeof button === 'string' ? document.querySelector(button) : button;
    if (!btn) return;

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
function shrinkAllButtonsToFit(selector = 'button:not(.swal2-confirm):not(.swal2-deny):not(.swal2-styled)') {
    const buttons = document.querySelectorAll(selector);
    buttons.forEach(btn => shrinkButtonTextToFit(btn));
}
