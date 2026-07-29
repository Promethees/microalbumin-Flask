// Community content: the collapsible user-reviews banner at the top of the page
// and the publication-reference block at the bottom.
//
// The lists themselves are rendered server-side from the curated JSON files
// (see src/community.py), so this file only handles interaction: collapse state,
// the review submission dialog, and citation copy-to-clipboard.

const REVIEWS_COLLAPSED_KEY = 'reviews-banner-collapsed';

// The banner is fixed to the top of the viewport, so the page has to reserve
// room for it — and it must reserve the banner's *whole* current height, not
// just the header row. Reserving only the header made an expanded banner overlay
// the app, burying the logo and the User Guide button. Everything pinned to the
// top of the viewport — the page padding, .top-left and the User Guide button —
// reads --reviews-bar-h, so expanding pushes them all down instead.
function syncReviewsBarHeight() {
    const banner = document.getElementById('reviews-banner');
    if (!banner) return;
    const h = Math.round(banner.getBoundingClientRect().height);
    document.documentElement.style.setProperty('--reviews-bar-h', `${h}px`);
    // .top-right is positioned from a measured offset rather than the variable,
    // so it has to be re-measured once the reserved gap changes. Reading the
    // rect above already forced the layout the measurement below depends on.
    if (typeof window.alignTopWithReference === 'function') window.alignTopWithReference();
}

// Collapse/expand the reviews banner and remember the choice — a returning user
// who closed it should not have to close it again on every load.
function toggleReviewsBanner(force) {
    const banner = document.getElementById('reviews-banner');
    if (!banner) return;
    const collapsed = (force === undefined)
        ? !banner.classList.contains('collapsed')
        : !!force;
    banner.classList.toggle('collapsed', collapsed);

    const chevron = document.getElementById('reviews-chevron');
    if (chevron) chevron.classList.toggle('collapsed-chevron', collapsed);
    const toggle = document.getElementById('reviews-banner-toggle');
    if (toggle) toggle.setAttribute('aria-expanded', String(!collapsed));

    try { localStorage.setItem(REVIEWS_COLLAPSED_KEY, collapsed ? '1' : '0'); } catch (e) { /* private mode */ }

    // The reserved gap is the banner's height, which just changed.
    syncReviewsBarHeight();
}

// Restore the stored collapse state and reserve the bar's height.
function initReviewsBanner() {
    if (!document.getElementById('reviews-banner')) return;
    let stored = null;
    try { stored = localStorage.getItem(REVIEWS_COLLAPSED_KEY); } catch (e) { /* private mode */ }
    // Default collapsed: the banner sits above the app, and the tool — not the
    // testimonials — is what a returning user came for.
    toggleReviewsBanner(stored === null ? true : stored === '1');
    // Content reflows at narrow widths, changing the banner's height.
    window.addEventListener('resize', syncReviewsBarHeight);
}

// Review submission dialog. Nothing here publishes: the payload is emailed to
// the admin, who confirms with the author before adding it to testimonials.json.
async function openReviewForm() {
    const result = await Swal.fire({
        title: 'Share your experience',
        html: `
            <div style="text-align:left; font-size:0.92rem;">
                <p style="margin:0 0 12px; color:#666;">
                    Your review is sent to our team. We publish it only after confirming
                    with you by email — nothing appears on the site automatically.
                </p>
                <label class="review-field">Name*
                    <input id="review-name" class="swal2-input" style="margin:4px 0 0; width:100%;"
                        maxlength="120" autocomplete="name">
                </label>
                <label class="review-field">Email* <span style="color:#888;">(so we can reach you)</span>
                    <input id="review-email" type="email" class="swal2-input" style="margin:4px 0 0; width:100%;"
                        maxlength="120" autocomplete="email">
                </label>
                <label class="review-field">Role
                    <input id="review-role" class="swal2-input" style="margin:4px 0 0; width:100%;"
                        maxlength="120" placeholder="e.g. Research assistant">
                </label>
                <label class="review-field">Affiliation
                    <input id="review-affiliation" class="swal2-input" style="margin:4px 0 0; width:100%;"
                        maxlength="200" placeholder="e.g. Your lab or institution">
                </label>
                <label class="review-field">Rating
                    <select id="review-rating" class="swal2-input" style="margin:4px 0 0; width:100%;">
                        <option value="5">★★★★★</option>
                        <option value="4">★★★★☆</option>
                        <option value="3">★★★☆☆</option>
                        <option value="2">★★☆☆☆</option>
                        <option value="1">★☆☆☆☆</option>
                    </select>
                </label>
                <label class="review-field">Your review*
                    <textarea id="review-quote" class="swal2-textarea" style="margin:4px 0 0; width:100%;"
                        maxlength="1200" rows="5"
                        placeholder="What did you use Easy OKAPI for, and how did it help?"></textarea>
                </label>
            </div>`,
        showCancelButton: true,
        confirmButtonText: 'Send for review',
        cancelButtonText: 'Cancel',
        focusConfirm: false,
        width: '32rem',
        preConfirm: () => {
            const val = id => (document.getElementById(id)?.value || '').trim();
            const name = val('review-name');
            const email = val('review-email');
            const quote = val('review-quote');
            if (!name) { Swal.showValidationMessage('Please enter your name.'); return false; }
            if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
                Swal.showValidationMessage('Please enter a valid email address.');
                return false;
            }
            if (quote.length < 20) {
                Swal.showValidationMessage('Please write at least 20 characters about your experience.');
                return false;
            }
            return {
                name, email, quote,
                role: val('review-role'),
                affiliation: val('review-affiliation'),
                rating: parseInt(val('review-rating'), 10) || 5
            };
        }
    });
    if (!result.isConfirmed || !result.value) return;

    try {
        if (typeof window.showSpinner === 'function') window.showSpinner();
        const res = await fetch('/api/testimonials/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(result.value)
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.status !== 'success') {
            // 429 comes from the rate limiter, which returns no JSON body.
            const msg = data.message
                || (res.status === 429
                    ? 'You have sent several reviews already. Please try again later.'
                    : 'Could not send your review. Please try again later.');
            throw new Error(msg);
        }
        Swal.fire({ icon: 'success', title: 'Thank you!', text: data.message });
    } catch (e) {
        Swal.fire({ icon: 'error', title: 'Not sent', text: e.message });
    } finally {
        if (typeof window.hideSpinner === 'function') window.hideSpinner();
    }
}

// Copy a citation block (APA or BibTeX) and flash confirmation on the button.
async function copyCitation(elementId, btn) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const text = el.textContent || '';
    try {
        await navigator.clipboard.writeText(text);
    } catch (e) {
        // Clipboard API needs a secure context; fall back to a hidden textarea.
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); } catch (err) { /* nothing else to try */ }
        document.body.removeChild(ta);
    }
    if (btn) {
        const original = btn.textContent;
        btn.textContent = '✅ Copied';
        setTimeout(() => { btn.textContent = original; }, 1600);
    }
}

window.addEventListener('load', initReviewsBanner);
