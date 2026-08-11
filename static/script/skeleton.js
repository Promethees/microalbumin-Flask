/**
 * Skeleton placeholders for regions that are waiting on the server.
 *
 * Why this exists: the hosted app talks to a dyno, so a table refresh or a
 * chart reload is roughly a second of round trip. Without a placeholder the
 * user reads stale rows (and can click them) until the answer lands.
 *
 * Two rules keep it from spreading:
 *   1. Skeletons are for CONTENT arriving. A blocking operation — merge,
 *      export, report build — keeps window.showSpinner()/hideSpinner().
 *   2. Nothing shows before DELAY_MS. A warm dyno answers fast enough that an
 *      instant skeleton would only flash, which reads worse than a short wait.
 *
 * Shapes live in the "Skeleton placeholders" block of static/style.css.
 */
(function () {
    'use strict';

    // Long enough that a fast response never flashes a placeholder, short
    // enough that a real wait is acknowledged well inside the first second.
    var DELAY_MS = 200;

    // host element -> { timer, kind, node } for the skeleton it is showing.
    var _active = new Map();

    function _el(target) {
        if (!target) return null;
        return typeof target === 'string' ? document.getElementById(target) : target;
    }

    function _bar(cls) {
        var d = document.createElement('div');
        d.className = 'skel' + (cls ? ' ' + cls : '');
        return d;
    }

    /**
     * Skeleton rows in a <table>, keeping its header row in place.
     *
     * The rows already on screen are dropped, not covered: they belong to the
     * mode or subject being left behind, and a stale row is clickable.
     */
    function _paintRows(table, rows, cols) {
        var body = table.tBodies[0] || table;
        for (var i = body.rows.length - 1; i >= 1; i--) {
            body.deleteRow(i);
        }
        var frag = document.createDocumentFragment();
        for (var r = 0; r < rows; r++) {
            var tr = document.createElement('tr');
            tr.className = 'skel-row';
            for (var c = 0; c < cols; c++) {
                var td = document.createElement('td');
                td.appendChild(_bar(c === 0 ? 'skel-line-lg' : 'skel-line-sm'));
                tr.appendChild(td);
            }
            frag.appendChild(tr);
        }
        body.appendChild(frag);
        return frag;
    }

    /** A cover over a region whose real content has to survive the wait. */
    function _paintCover(host) {
        var cover = document.createElement('div');
        cover.className = 'skel-cover';
        cover.appendChild(_bar('skel-line-md'));
        cover.appendChild(_bar('skel-line-lg'));
        cover.appendChild(_bar('skel-line-sm'));
        host.appendChild(cover);
        return cover;
    }

    /** Card outlines, for a list of report items. */
    function _paintCards(host, count) {
        host.innerHTML = '';
        for (var i = 0; i < count; i++) {
            var card = document.createElement('div');
            card.className = 'skel-card';
            card.appendChild(_bar('skel-line-md'));
            card.appendChild(_bar('skel-line-lg'));
            card.appendChild(_bar('skel-line-sm'));
            host.appendChild(card);
        }
        return host;
    }

    /**
     * Show a skeleton in `target` after the delay.
     *
     * opts.kind — 'rows' (default, target is a <table>), 'cover' (target is a
     *             positioned region), or 'cards'.
     * opts.rows / opts.cols / opts.count — shape, per kind.
     *
     * Calling it twice on the same target is a no-op: the first skeleton stays,
     * so a re-entrant refresh does not stack placeholders.
     */
    function showSkeleton(target, opts) {
        var host = _el(target);
        if (!host || _active.has(host)) return;
        opts = opts || {};
        var kind = opts.kind || 'rows';

        var timer = window.setTimeout(function () {
            var entry = _active.get(host);
            if (!entry) return;             // hidden before the delay elapsed
            entry.timer = null;
            host.setAttribute('aria-busy', 'true');
            if (kind === 'cover') {
                entry.node = _paintCover(host);
            } else if (kind === 'cards') {
                entry.node = _paintCards(host, opts.count || 3);
            } else {
                entry.node = _paintRows(host, opts.rows || 4, opts.cols || 4);
            }
        }, DELAY_MS);

        _active.set(host, { timer: timer, kind: kind, node: null });
    }

    /**
     * Take the skeleton down. Safe to call when none is up, and safe to call
     * before the delay has elapsed — that just cancels the pending one.
     *
     * For 'rows' and 'cards' the caller normally overwrites the region with the
     * loaded content anyway; the leftover nodes are still removed here so an
     * error path that renders nothing does not strand a placeholder.
     */
    function hideSkeleton(target) {
        var host = _el(target);
        if (!host) return;
        var entry = _active.get(host);
        if (!entry) return;
        _active.delete(host);
        if (entry.timer) window.clearTimeout(entry.timer);
        host.removeAttribute('aria-busy');
        if (entry.kind === 'cover') {
            if (entry.node && entry.node.parentNode) entry.node.parentNode.removeChild(entry.node);
        } else if (entry.kind === 'rows') {
            host.querySelectorAll('tr.skel-row').forEach(function (tr) {
                if (tr.parentNode) tr.parentNode.removeChild(tr);
            });
        } else {
            host.querySelectorAll('.skel-card').forEach(function (card) {
                if (card.parentNode) card.parentNode.removeChild(card);
            });
        }
    }

    window.showSkeleton = showSkeleton;
    window.hideSkeleton = hideSkeleton;
})();
