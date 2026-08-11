/*
 * Styled hover-hint tooltip component.
 *
 * Replaces native `title` tooltips with a single themed bubble that is
 * appended to <body>, so it can never be clipped by the app's many
 * `overflow:hidden` collapsible sections (`.section-collapse`,
 * `#top-left-scrollable`, `.file-table-container`, …).
 *
 * Usage: add `data-hint="some text"` to any element. The bubble shows on
 * hover and on keyboard focus, positioned above the element (flipping below
 * when there isn't room) and clamped to the viewport. All styling lives in
 * style.css (`#okapi-tooltip`); this file only handles show/hide + placement.
 */
(function () {
    'use strict';

    var SHOW_DELAY = 350;   // ms before a hover hint appears
    var HIDE_DELAY = 60;    // ms grace so moving onto the bubble edge doesn't flicker
    var GAP = 8;            // px between the target and the bubble
    var EDGE = 6;           // px minimum distance from the viewport edge

    var tip = null;
    var current = null;
    var showTimer = null;
    var hideTimer = null;

    function ensureTip() {
        if (tip) return tip;
        tip = document.createElement('div');
        tip.id = 'okapi-tooltip';
        tip.setAttribute('role', 'tooltip');
        document.body.appendChild(tip);
        return tip;
    }

    function place(el) {
        var t = ensureTip();
        var r = el.getBoundingClientRect();
        var tr = t.getBoundingClientRect(); // measured at current (wrapped) size

        var placement = 'top';
        var top = r.top - tr.height - GAP;
        if (top < EDGE) {
            top = r.bottom + GAP;       // not enough room above → flip below
            placement = 'bottom';
        }

        var left = r.left + (r.width - tr.width) / 2;
        left = Math.max(EDGE, Math.min(left, window.innerWidth - tr.width - EDGE));

        // Keep the arrow pointing at the target's centre even after clamping.
        var arrowX = r.left + r.width / 2 - left;
        arrowX = Math.max(12, Math.min(arrowX, tr.width - 12));

        t.style.top = Math.round(top) + 'px';
        t.style.left = Math.round(left) + 'px';
        t.style.setProperty('--arrow-x', Math.round(arrowX) + 'px');
        t.setAttribute('data-placement', placement);
    }

    function show(el) {
        var text = el.getAttribute('data-hint');
        if (!text) return;
        var t = ensureTip();
        t.textContent = text;
        current = el;
        // WCAG 4.1.2 — the bubble is a visual affordance only unless the
        // element it describes points at it. `aria-describedby` is what makes
        // a screen reader read the hint after the control's own name.
        el.setAttribute('aria-describedby', 'okapi-tooltip');
        place(el);
        // place() reads the bubble size before it is shown; reveal next frame.
        requestAnimationFrame(function () { t.classList.add('visible'); });
    }

    function hide() {
        clearTimeout(showTimer);
        clearTimeout(hideTimer);
        if (current) current.removeAttribute('aria-describedby');
        current = null;
        if (tip) tip.classList.remove('visible');
    }

    function onOver(e) {
        var el = e.target.closest ? e.target.closest('[data-hint]') : null;
        if (!el || el === current) return;
        clearTimeout(showTimer);
        clearTimeout(hideTimer);
        showTimer = setTimeout(function () { show(el); }, SHOW_DELAY);
    }

    function onOut(e) {
        var el = e.target.closest ? e.target.closest('[data-hint]') : null;
        if (!el) return;
        // Ignore moves that stay within the same hinted element.
        if (e.relatedTarget && el.contains(e.relatedTarget)) return;
        clearTimeout(showTimer);
        hideTimer = setTimeout(hide, HIDE_DELAY);
    }

    function onFocus(e) {
        var el = e.target.closest ? e.target.closest('[data-hint]') : null;
        if (!el) return;
        clearTimeout(showTimer);
        show(el); // keyboard focus → show immediately, no hover delay
    }

    document.addEventListener('mouseover', onOver);
    document.addEventListener('mouseout', onOut);
    document.addEventListener('focusin', onFocus);
    document.addEventListener('focusout', hide);
    // A press or resize invalidates the position → just hide.
    document.addEventListener('click', hide, true);
    window.addEventListener('resize', hide);

    // WCAG 1.4.13 Content on Hover or Focus. The criterion has three parts and
    // each needs something here:
    //
    //   dismissible — Escape closes the bubble without moving focus, so a hint
    //                 can never end up covering the thing you were reading.
    //   hoverable   — the bubble is appended to <body>, so moving the pointer
    //                 onto it fires `mouseout` on the target; without this the
    //                 hint would vanish as you reached for it. Someone using
    //                 magnification often has to do exactly that.
    //   persistent  — a hint stays until dismissed, focus moves or the pointer
    //                 leaves. It is *not* removed on scroll any more: scrolling
    //                 to read a long hint used to close it.
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && current) {
            e.stopPropagation();
            hide();
        }
    }, true);

    document.addEventListener('scroll', function () {
        // Reposition rather than hide, so the hint follows its target.
        if (current) place(current);
    }, true);

    document.addEventListener('mouseover', function (e) {
        if (tip && e.target === tip) clearTimeout(hideTimer);
    });
    document.addEventListener('mouseout', function (e) {
        if (tip && e.target === tip) hideTimer = setTimeout(hide, HIDE_DELAY);
    });
})();
