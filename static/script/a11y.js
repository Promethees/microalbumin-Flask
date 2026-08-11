/*
 * Accessibility behaviours that do not belong to any one feature.
 *
 * The markup-level work lives in the templates and the "Accessibility" block in
 * style.css; what is here is the part that only the browser can do — describing
 * a <canvas>, making an overflowing container reachable, and keeping focus
 * sensible when a panel opens or closes.
 *
 * Everything published at /accessibility as a conformance claim depends on one
 * of those three files. See `Rule.md` §2.15 before changing this.
 */

(function () {
    'use strict';

    var t = function (key, fallback) {
        return (window.t ? window.t(key, fallback) : fallback);
    };

    // ── 1.1.1 — a text alternative for every chart ──────────────────────────
    //
    // A Chart.js plot is pixels on a <canvas>: a screen reader is told there is
    // an image and nothing else. Each chart therefore gets
    //
    //   · an accessible name on the canvas saying what is plotted, and
    //   · a real data table holding the same numbers, built on demand.
    //
    // Built on demand because a kinetics trace can carry thousands of points,
    // and a table nobody opened has no business in the DOM.

    function _seriesSummary(chart) {
        var sets = (chart && chart.data && chart.data.datasets) || [];
        return sets.filter(function (d) { return d && d.label; })
            .map(function (d) { return d.label; });
    }

    function buildChartDataTable(canvasId, chart, title) {
        var canvas = document.getElementById(canvasId);
        if (!canvas || !chart) return;

        var points = (chart.data && chart.data.labels) ? chart.data.labels.length : 0;
        var labels = _seriesSummary(chart);
        var name = (title || t('a11y.charts_region', 'Charts and analyses'));
        // "Absorbance over time, 3 series (Source 1, Source 2, Source 3), 240 points."
        canvas.setAttribute('role', 'img');
        canvas.setAttribute('aria-label',
            name + ' — ' + labels.join(', ') + ' — ' + points + ' ' +
            t('a11y.points', 'points'));

        var wrapId = canvasId + '-alt';
        var wrap = document.getElementById(wrapId);
        if (!wrap) {
            wrap = document.createElement('div');
            wrap.id = wrapId;
            wrap.className = 'chart-alt';
            canvas.parentNode.insertBefore(wrap, canvas.nextSibling);
        }
        wrap.innerHTML = '';

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'utility-btn chart-alt-toggle';
        btn.setAttribute('aria-expanded', 'false');
        btn.setAttribute('aria-controls', canvasId + '-table');
        btn.setAttribute('data-canvas', canvasId);
        btn.textContent = t('a11y.show_data_table', 'Show data table');
        btn.addEventListener('click', function () { toggleChartDataTable(btn); });

        var table = document.createElement('table');
        table.id = canvasId + '-table';
        table.className = 'chart-data-table';
        table.hidden = true;

        wrap.appendChild(btn);
        wrap.appendChild(table);
    }

    function toggleChartDataTable(btn) {
        var canvasId = btn.getAttribute('data-canvas');
        var table = document.getElementById(canvasId + '-table');
        if (!table) return;

        var opening = table.hidden;
        if (opening && !table.dataset.filled) {
            _fillChartTable(table, canvasId);
            table.dataset.filled = '1';
        }
        table.hidden = !opening;
        btn.setAttribute('aria-expanded', opening ? 'true' : 'false');
        btn.textContent = opening
            ? t('a11y.hide_data_table', 'Hide data table')
            : t('a11y.show_data_table', 'Show data table');
    }

    function _fillChartTable(table, canvasId) {
        var chart = (window.AppState && AppState.chartInstances)
            ? AppState.chartInstances[canvasId] : null;
        if (!chart) return;

        var xs = (chart.data && chart.data.labels) || [];
        var sets = ((chart.data && chart.data.datasets) || []).filter(function (d) {
            // A regression overlay repeats the fitted line, not measured data.
            return d && d.data && !d._isRegression;
        });

        var caption = document.createElement('caption');
        caption.textContent = t('a11y.chart_table_caption',
            'Values plotted in the chart above');
        table.appendChild(caption);

        var thead = document.createElement('thead');
        var hrow = document.createElement('tr');
        [t('a11y.range_from', 'From')].concat(sets.map(function (d, i) {
            return d.label || ('Series ' + (i + 1));
        })).forEach(function (text, i) {
            var th = document.createElement('th');
            th.scope = 'col';
            // The first column is the X axis; name it after the axis in use.
            th.textContent = i === 0
                ? ((window.AppState && AppState.xAxis === 'turn') ? 'Turn' : 'Timestamp')
                : text;
            hrow.appendChild(th);
        });
        thead.appendChild(hrow);
        table.appendChild(thead);

        var tbody = document.createElement('tbody');
        xs.forEach(function (x, row) {
            var tr = document.createElement('tr');
            var th = document.createElement('th');
            th.scope = 'row';
            th.textContent = x;
            tr.appendChild(th);
            sets.forEach(function (d) {
                var td = document.createElement('td');
                var v = d.data[row];
                td.textContent = (v === null || v === undefined) ? '—' : v;
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
    }

    // ── 2.1.1 — a scrollable box must be reachable from the keyboard ────────
    //
    // A container with its own scrollbar cannot be scrolled by someone who has
    // no pointer unless it can take focus. Only containers that actually
    // overflow get a tab stop, so the tab order does not fill up with boxes
    // whose content happens to fit.
    var SCROLLERS = [
        '#top-left-scrollable', '#chart-container', '#json-display',
        '#report-items-container', '.file-table-container'
    ].join(',');

    function enhanceScrollableRegions() {
        document.querySelectorAll(SCROLLERS).forEach(function (el) {
            var overflows = el.scrollHeight > el.clientHeight + 2 ||
                el.scrollWidth > el.clientWidth + 2;
            if (!overflows) {
                if (el.dataset.a11yScroller) {
                    el.removeAttribute('tabindex');
                    delete el.dataset.a11yScroller;
                }
                return;
            }
            if (el.dataset.a11yScroller) return;
            // `#chart-container` is focused programmatically and already owns a
            // tabindex; promoting it to 0 keeps both behaviours.
            el.setAttribute('tabindex', '0');
            if (!el.getAttribute('role') && !el.getAttribute('aria-label')) {
                el.setAttribute('role', 'region');
                el.setAttribute('aria-label',
                    t('a11y.scrollable_region', 'Scrollable region'));
            }
            el.dataset.a11yScroller = '1';
        });
    }

    // Content arrives by fetch long after load, so overflow is re-checked when
    // the DOM settles rather than once at startup.
    var _rescan = null;
    function scheduleScrollScan() {
        clearTimeout(_rescan);
        _rescan = setTimeout(enhanceScrollableRegions, 250);
    }

    document.addEventListener('DOMContentLoaded', function () {
        enhanceScrollableRegions();

        var host = document.querySelector('.container');
        if (host && 'MutationObserver' in window) {
            new MutationObserver(scheduleScrollScan)
                .observe(host, { childList: true, subtree: true });
        }
        window.addEventListener('resize', scheduleScrollScan);
    });

    window.buildChartDataTable = buildChartDataTable;
    window.toggleChartDataTable = toggleChartDataTable;
    window.enhanceScrollableRegions = enhanceScrollableRegions;
})();
