// Utility short-hands
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

const $showText = (id, text) => {
    const el = document.getElementById(id);
    el.textContent = text;
    el.style.display = "";
};

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
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`Fetch error for ${url}:`, error);
        throw error;
    }
}

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
