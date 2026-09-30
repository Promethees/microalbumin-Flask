/**
 * Report a Bug — button handler (left column, below Options).
 *
 * Flow when clicked:
 *   1. A SweetAlert asks whether to attach event log files to the report.
 *   2. If yes, a second dialog lists the files in log/events/ and lets the user
 *      pick up to MAX_LOG_FILES of them.
 *   3. A third dialog prompts for a name for the .zip archive.
 *   4. The chosen files are bundled (POST /download_event_logs) and downloaded
 *      to the user's machine, then the mail client opens with a report
 *      pre-filled to the maintainer (MAINTAINER_EMAIL) and an instruction to
 *      attach the downloaded zip (mailto: cannot attach files programmatically).
 *   5. "No, just email" opens a plain mailto: draft with no attachment.
 */

(function () {
    'use strict';

    const MAX_LOG_FILES = 5;

    // Dialog chrome follows the UI language (Rule.md §2.22). The email body
    // stays English on purpose: it is addressed to the maintainer.
    function _t(key, fallback) {
        return (typeof t === 'function') ? t(key, fallback) : fallback;
    }

    function _platform() {
        return navigator.platform || navigator.userAgent || 'unknown';
    }

    function _appVersion() {
        return (typeof APP_VERSION !== 'undefined' && APP_VERSION) ? APP_VERSION : 'unknown';
    }

    function _recipient() {
        return (typeof MAINTAINER_EMAIL !== 'undefined' && MAINTAINER_EMAIL) ? MAINTAINER_EMAIL : '';
    }

    function _subject() {
        return `Easy OKAPI Bug Report (v${_appVersion()})`;
    }

    function _formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    // "2026-06-03/10-00-00.jsonl" → "2026-06-03  10:00:00"
    function _fileLabel(relPath) {
        const parts = relPath.split('/');
        const datePart = parts.length > 1 ? parts[0] : '';
        const timePart = (parts[parts.length - 1] || '').replace(/\.jsonl$/, '').replace(/-/g, ':');
        return (datePart ? datePart + '  ' : '') + timePart;
    }

    function _esc(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function _buildBody(attachmentName) {
        const lines = [
            'Please describe the bug below. The more detail, the faster we can fix it.',
            '',
            '— What happened? ',
            '',
            '',
            '— What did you expect to happen? ',
            '',
            '',
            '— Steps to reproduce: ',
            '1. ',
            '2. ',
            '3. ',
            '',
        ];
        if (attachmentName) {
            lines.push(
                '──────────────────────────────────────────',
                'IMPORTANT — please attach the log file:',
                `The log archive "${attachmentName}" was just downloaded to your`,
                'Downloads folder. Please attach it to this email before sending —',
                'it helps us diagnose the problem.',
                '──────────────────────────────────────────',
                '');
        }
        lines.push(
            'App version: ' + _appVersion(),
            'Platform: ' + _platform(),
            'Date: ' + new Date().toString());
        return lines.join('\n');
    }

    // Open a mailto: draft. When attachmentName is given the body asks the user
    // to attach the zip they just downloaded.
    function _openMail(attachmentName) {
        const mailto = 'mailto:' + encodeURIComponent(_recipient()) +
            '?subject=' + encodeURIComponent(_subject()) +
            '&body=' + encodeURIComponent(_buildBody(attachmentName));
        window.location.href = mailto;
    }

    // Multi-select file picker. Returns: array of relative paths, 'none' (no
    // logs / skip), or 'cancel' (user backed out).
    async function _chooseFiles() {
        let files;
        try {
            const data = await fetch('/list_event_log_files').then(r => r.json());
            files = (data && data.status === 'success') ? (data.files || []) : [];
        } catch (e) {
            files = [];
        }

        if (!files.length) {
            await Swal.fire({
                title: _t('bug.no_logs_title', 'No log files found'),
                text: _t('bug.no_logs_text', 'There are no event log files to attach. The report email will still open.'),
                icon: 'info',
                confirmButtonText: _t('common.ok', 'OK'),
            });
            return 'none';
        }

        const rows = files.map((f, i) =>
            `<label class="bug-log-row">` +
            `<input type="checkbox" class="bug-log-cb" value="${_esc(f.path)}" data-i="${i}">` +
            `<span class="bug-log-name">${_esc(_fileLabel(f.path))}</span>` +
            `<span class="bug-log-size">${_esc(_formatSize(f.size))}</span>` +
            `</label>`
        ).join('');

        const result = await Swal.fire({
            title: _t('bug.choose_title', 'Choose log files'),
            html:
                `<p class="bug-log-hint">${_esc(_t('bug.choose_hint', 'Select up to {n} event log files to attach (newest first).').replace('{n}', MAX_LOG_FILES))}</p>` +
                `<div id="bug-log-list" class="bug-log-list">${rows}</div>`,
            focusConfirm: false,
            showCancelButton: true,
            confirmButtonText: _t('bug.next', 'Next'),
            cancelButtonText: _t('common.cancel', 'Cancel'),
            didOpen: () => {
                const boxes = Array.from(document.querySelectorAll('.bug-log-cb'));
                boxes.forEach(cb => cb.addEventListener('change', () => {
                    const checked = boxes.filter(b => b.checked);
                    if (checked.length > MAX_LOG_FILES) {
                        cb.checked = false;
                        Swal.showValidationMessage(_t('bug.too_many', 'You can attach at most {n} files.').replace('{n}', MAX_LOG_FILES));
                    } else {
                        Swal.resetValidationMessage();
                    }
                }));
            },
            preConfirm: () => {
                const chosen = Array.from(document.querySelectorAll('.bug-log-cb:checked')).map(cb => cb.value);
                if (!chosen.length) {
                    Swal.showValidationMessage(_t('bug.select_one', 'Please select at least one file.'));
                    return false;
                }
                if (chosen.length > MAX_LOG_FILES) {
                    Swal.showValidationMessage(_t('bug.too_many', 'You can attach at most {n} files.').replace('{n}', MAX_LOG_FILES));
                    return false;
                }
                return chosen;
            },
        });

        if (!result.isConfirmed || !result.value) return 'cancel';
        return result.value;
    }

    // Prompt for the zip filename. Returns the final ".zip" name, or null if cancelled.
    async function _promptZipName() {
        const ts = new Date().toISOString().replace(/[-:T.]/g, '').slice(0, 15);
        const result = await Swal.fire({
            title: _t('bug.name_title', 'Name the log archive'),
            input: 'text',
            inputLabel: _t('bug.name_label', 'The .zip file you will attach to your email'),
            inputValue: `easyokapi-logs-${ts}`,
            inputAttributes: { maxlength: '80', autocapitalize: 'off', spellcheck: 'false' },
            showCancelButton: true,
            confirmButtonText: _t('bug.download_open', 'Download & open email'),
            cancelButtonText: _t('common.cancel', 'Cancel'),
            inputValidator: (v) => (!v || !v.trim() ? _t('bug.name_required', 'Please enter a file name.') : null),
        });
        if (!result.isConfirmed || !result.value) return null;
        return result.value.trim().replace(/\.zip$/i, '') + '.zip';
    }

    // Bundle the chosen files server-side and download the zip to the machine.
    async function _downloadSelected(paths, zipName) {
        const resp = await fetch('/download_event_logs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: paths }),
        });
        if (!resp.ok) throw new Error(_t('bug.bundle_failed', 'Could not bundle the selected log files.'));
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = zipName;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 1000);
    }

    window.reportBug = async function reportBug() {
        if (typeof logEvent === 'function') logEvent('bug_report', 'open');

        // No SweetAlert available → fall back to a plain mail draft.
        if (typeof Swal === 'undefined') { _openMail(null); return; }

        const choice = await Swal.fire({
            title: _t('bug.report.aria', 'Report a Bug'),
            text: _t('bug.ask_attach', 'Would you like to attach event log files to help us diagnose the issue?'),
            icon: 'question',
            showCancelButton: true,
            showDenyButton: true,
            confirmButtonText: _t('bug.yes_choose', 'Yes, choose files'),
            denyButtonText: _t('bug.just_email', 'No, just email'),
            cancelButtonText: _t('common.cancel', 'Cancel'),
        });

        if (choice.isDismissed) return;                  // Cancel / Esc → abort
        if (choice.isDenied) { _openMail(null); return; }   // plain email, no attachment

        const files = await _chooseFiles();
        if (files === 'cancel') return;
        if (files === 'none') { _openMail(null); return; }

        const zipName = await _promptZipName();
        if (!zipName) return;

        try {
            await _downloadSelected(files, zipName);
        } catch (e) {
            await Swal.fire({ title: _t('bug.download_failed', 'Download failed'), text: e.message, icon: 'error', confirmButtonText: _t('common.ok', 'OK') });
            return;
        }

        await Swal.fire({
            title: _t('bug.downloaded_title', 'Log archive downloaded'),
            html: _esc(_t('bug.downloaded_saved', 'Saved {f} to your Downloads folder.')).replace('{f}', `<b>${_esc(zipName)}</b>`) + '<br><br>' +
                _esc(_t('bug.downloaded_attach', 'Your email will now open — please attach that file before sending.')),
            icon: 'success',
            confirmButtonText: _t('bug.open_email', 'Open email'),
        });
        _openMail(zipName);
    };
})();
