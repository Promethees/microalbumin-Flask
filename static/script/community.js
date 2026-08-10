// Community content: the review submission dialog in the app's community strip.
//
// The reviews carousel and the citation block moved to the landing page
// (templates/landing.html), which renders them server-side from the same
// curated files (see src/community.py). What stays here is the one thing a
// visitor can *do*: send a review. Nothing here publishes — the payload is
// emailed to the admin, who confirms with the author first.

// Review submission dialog. Nothing here publishes: the payload is emailed to
// the admin, who confirms with the author before adding it to testimonials.json.
async function openReviewForm() {
    const result = await Swal.fire({
        title: window.t('dlg.share_experience', 'Share your experience'),
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
        confirmButtonText: window.t('dlg.send_for_review', 'Send for review'),
        cancelButtonText: window.t('dlg.cancel', 'Cancel'),
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
        Swal.fire({ icon: 'success', title: window.t('dlg.thank_you', 'Thank you!'), text: data.message });
    } catch (e) {
        Swal.fire({ icon: 'error', title: window.t('dlg.not_sent', 'Not sent'), text: e.message });
    } finally {
        if (typeof window.hideSpinner === 'function') window.hideSpinner();
    }
}
