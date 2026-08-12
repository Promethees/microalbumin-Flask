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

    const SHOW_DELAY = 350;   // ms before a hover hint appears
    const HIDE_DELAY = 60;    // ms grace so moving onto the bubble edge doesn't flicker
    const GAP = 8;            // px between the target and the bubble
    const EDGE = 6;           // px minimum distance from the viewport edge

    let tip = null;
    let current = null;
    let showTimer = null;
    let hideTimer = null;
    let shownByFocus = false; // keyboard-shown hints own the Escape key; see below
    let scrollRaf = 0;        // rAF handle so scroll repositioning runs once a frame

    function ensureTip() {
        if (tip) return tip;
        tip = document.createElement('div');
        tip.id = 'okapi-tooltip';
        tip.setAttribute('role', 'tooltip');
        document.body.appendChild(tip);
        return tip;
    }

    // `rect` lets a caller that has already measured the target hand the
    // measurement in, so repositioning during a scroll costs one forced layout
    // a frame rather than two.
    function place(el, rect) {
        const t = ensureTip();
        const r = rect || el.getBoundingClientRect();
        const tr = t.getBoundingClientRect(); // measured at current (wrapped) size

        let placement = 'top';
        let top = r.top - tr.height - GAP;
        if (top < EDGE) {
            top = r.bottom + GAP;       // not enough room above → flip below
            placement = 'bottom';
        }

        let left = r.left + (r.width - tr.width) / 2;
        left = Math.max(EDGE, Math.min(left, window.innerWidth - tr.width - EDGE));

        // Keep the arrow pointing at the target's centre even after clamping.
        let arrowX = r.left + r.width / 2 - left;
        arrowX = Math.max(12, Math.min(arrowX, tr.width - 12));

        t.style.top = Math.round(top) + 'px';
        t.style.left = Math.round(left) + 'px';
        t.style.setProperty('--arrow-x', Math.round(arrowX) + 'px');
        t.setAttribute('data-placement', placement);
    }

    function show(el, viaFocus) {
        const text = el.getAttribute('data-hint');
        if (!text) return;
        const t = ensureTip();
        t.textContent = text;
        current = el;
        shownByFocus = !!viaFocus;
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
        shownByFocus = false;
        if (tip) tip.classList.remove('visible');
    }

    function onOver(e) {
        const el = e.target.closest ? e.target.closest('[data-hint]') : null;
        if (!el || el === current) return;
        clearTimeout(showTimer);
        clearTimeout(hideTimer);
        showTimer = setTimeout(function () { show(el); }, SHOW_DELAY);
    }

    function onOut(e) {
        const el = e.target.closest ? e.target.closest('[data-hint]') : null;
        if (!el) return;
        // Ignore moves that stay within the same hinted element.
        if (e.relatedTarget && el.contains(e.relatedTarget)) return;
        clearTimeout(showTimer);
        hideTimer = setTimeout(hide, HIDE_DELAY);
    }

    function onFocus(e) {
        const el = e.target.closest ? e.target.closest('[data-hint]') : null;
        if (!el) return;
        clearTimeout(showTimer);
        show(el, true); // keyboard focus → show immediately, no hover delay
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
    //   persistent  — a hint stays until dismissed, focus moves, or the pointer
    //                 leaves. It is no longer removed on scroll: scrolling to
    //                 read a long hint used to close it.
    // Escape dismisses the hint, but only a *keyboard-shown* hint swallows the
    // key. The criterion asks for dismissal "without moving pointer hover or
    // keyboard focus": a hover hint can already be dismissed by moving the
    // pointer, so Escape is a convenience there, while a focus hint on a
    // keyboard has no other way out — that is the case that needs the key.
    //
    // The distinction matters because this listener is on `document` at capture
    // phase, ahead of everything: SweetAlert2 binds its own Escape on `window`
    // at bubble phase, which is dead last, so an unconditional
    // `stopPropagation()` here ate the key before any dialog saw it. Every
    // control in a dialog carries `data-hint`, so resting the pointer on one
    // was enough to make Escape stop closing the dialog with no sign why.
    // Layered dismissal (hint first, dialog on the second press) is the APG
    // pattern and is kept for the keyboard case, where the hint is genuinely a
    // layer the user put there; for a hover hint the dialog wins.
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape' || !current) return;
        if (shownByFocus) e.stopPropagation();
        hide();
    }, true);

    // Reposition rather than hide, so the hint follows its target — but at most
    // once a frame. This listener is on `document` at capture phase because
    // `scroll` does not bubble, which means it fires for every scroller in the
    // app (`#top-left-scrollable`, `.file-table-container`, `.dir-blocks`, the
    // chat log…). Calling place() straight from the event ran two forced
    // layouts and four style writes per event, interleaved read-write — the
    // scroll jank was the hint, not the list.
    document.addEventListener('scroll', function () {
        if (!current || scrollRaf) return;
        scrollRaf = requestAnimationFrame(function () {
            scrollRaf = 0;
            if (!current) return;
            const r = current.getBoundingClientRect();
            // Scrolled out of view entirely: the bubble would otherwise float
            // over unrelated UI with its arrow pointing at nothing.
            if (r.bottom < 0 || r.right < 0 ||
                r.top > window.innerHeight || r.left > window.innerWidth) {
                hide();
                return;
            }
            place(current, r);
        });
    }, true);

    document.addEventListener('mouseover', function (e) {
        if (tip && e.target === tip) clearTimeout(hideTimer);
    });
    document.addEventListener('mouseout', function (e) {
        if (tip && e.target === tip) hideTimer = setTimeout(hide, HIDE_DELAY);
    });
})();
