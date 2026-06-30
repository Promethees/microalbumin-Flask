// The cal-mode-select toggle is a top-level const in init.js; expose its value
// defensively (report generators may run before/without it in tests).
function _calSubMode() {
    return (typeof calDiv !== 'undefined' && calDiv) ? calDiv.getAttribute('data-value') : null;
}

// Fit-function descriptions shown in report exports (quick/full × PDF/Excel),
// mirroring the "Formula" row of the calibration-curve JSON display. Plain
// Unicode (not LaTeX) so they render in printed PDFs and Excel cells.
//   [S] = initial analyte concentration, q = quantity value (per-minute for kinetics)
const REPORT_FIT_FORMULAS = {
    linear:             '[S] = a·q + b',
    polynomial:         '[S] = a·q² + b·q + c',
    logarithmic:        '[S] = a·ln(q + b) + c',
    exponential:        '[S] = a·e^(b·q) + c',
    'michaelis-menten': '[S] = (Km·q) / (Vmax − q)',
};

// Return the human-readable formula for a fit type, or '' if unknown/empty.
function getReportFitFormula(fitType) {
    if (!fitType) return '';
    return REPORT_FIT_FORMULAS[String(fitType).toLowerCase()] || '';
}

// Per-algorithm parameter glossary — the symbols are the exact ones used by that
// fit's formula (e.g. linear uses a, b; Michaelis-Menten uses Vmax, Km).
const REPORT_FIT_PARAMS = {
    linear:             'a = slope, b = y-intercept',
    polynomial:         'a, b, c = quadratic, linear and constant coefficients',
    logarithmic:        'a = scale, b = horizontal shift, c = vertical offset',
    exponential:        'a = scale, b = growth/decay rate, c = vertical offset',
    'michaelis-menten': 'Vmax = maximum rate, Km = half-saturation constant',
};

// Parameter notes for one fit type ('' if unknown).
function getReportFitParams(fitType) {
    if (!fitType) return '';
    return REPORT_FIT_PARAMS[String(fitType).toLowerCase()] || '';
}

// Full "where" clause: the shared variables ([S], q) plus this fit's own params.
function getReportFitWhere(fitType) {
    const p = getReportFitParams(fitType);
    return `[S] = initial analyte concentration; q = measured quantity value${p ? '; ' + p : ''}`;
}

// "Michaelis-Menten: [S] = (Km·q)/(Vmax − q) — where …" — formula + full notes.
function getReportFitFunctionLabel(fitType) {
    const formula = getReportFitFormula(fitType);
    if (!fitType) return '';
    return formula ? `${fitType}: ${formula} — where ${getReportFitWhere(fitType)}` : String(fitType);
}

// A legend line (HTML) for a calibration fit table: explains [S] and q once and
// lists the parameter notes for each distinct algorithm present in the table.
function _reportFormulaLegendHtml(algoList) {
    const distinct = [...new Set((algoList || []).filter(Boolean).map(String))];
    const perAlgo = distinct
        .map(a => { const p = getReportFitParams(a); return p ? `<b>${a}</b> — ${p}` : ''; })
        .filter(Boolean).join('; ');
    return `<p style="font-size:0.78rem; color:#666; margin:6px 0 0;">
        Where <b>[S]</b> = initial analyte concentration (the value the curve returns) and
        <b>q</b> = measured quantity value (slope, maxRate, endpoint value, …)${perAlgo ? `. Fit parameters — ${perAlgo}` : ''}.
    </p>`;
}

// Exact coefficient column names for each fit type. analysis.coefficients is
// positional, so names[i] labels coefficients[i] (linear → a,b; MM → Vmax,Km).
const REPORT_FIT_COEF_NAMES = {
    linear:             ['a', 'b'],
    polynomial:         ['a', 'b', 'c'],
    logarithmic:        ['a', 'b', 'c'],
    exponential:        ['a', 'b', 'c'],
    'michaelis-menten': ['Vmax', 'Km'],
};
function getReportFitCoefNames(fitType) {
    return REPORT_FIT_COEF_NAMES[String(fitType || '').toLowerCase()] || ['a', 'b', 'c'];
}
function _fmtCoef(v) {
    return (v != null && !isNaN(v)) ? Number(v).toFixed(5) : '--';
}

// Render calibration fit results grouped by algorithm — one table per algorithm
// with that algorithm's exact coefficient columns. `fits` is a list of
// { entity, algo, coefficients: [...], rSquared }. `entityHeader` labels the
// first column (e.g. "Metric" or "Time Point").
function _renderCoefTablesHtml(entityHeader, fits) {
    if (!fits || !fits.length) return '';
    const groups = new Map();
    for (const f of fits) {
        const key = String(f.algo);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(f);
    }
    let html = '';
    for (const [algo, rows] of groups) {
        const names = getReportFitCoefNames(algo);
        const headCols = names.map(n => `<th style="padding:10px; text-align:left;">${n}</th>`).join('');
        const bodyRows = rows.map(f => {
            const cells = names.map((n, i) => `<td style="padding:10px; border:1px solid #eee;">${_fmtCoef(f.coefficients[i])}</td>`).join('');
            return `<tr>
                <td style="padding:10px; border:1px solid #eee;"><strong>${f.entity}</strong></td>
                ${cells}
                <td style="padding:10px; border:1px solid #eee;">${Number(f.rSquared).toFixed(4)}</td>
            </tr>`;
        }).join('');
        html += `
            <div style="margin-top:18px;">
                <h4 style="margin:0 0 6px; color:#2c3e50;">${algo} &nbsp;<span style="font-weight:normal; color:#555;">${getReportFitFormula(algo)}</span></h4>
                <table style="width:100%; border-collapse: collapse; font-size: 0.9rem; text-align:left;">
                    <thead><tr style="background:#f8fafc; border-bottom: 2px solid #3498db;">
                        <th style="padding:10px;">${entityHeader}</th>
                        ${headCols}
                        <th style="padding:10px;">R²</th>
                    </tr></thead>
                    <tbody>${bodyRows}</tbody>
                </table>
            </div>`;
    }
    html += _reportFormulaLegendHtml([...groups.keys()]);
    return html;
}

// Same grouping for Excel: returns [{ title, columns, rows }] — one table per
// algorithm with its exact coefficient columns — for the xlsx writer.
function _buildCoefTables(entityHeader, fits) {
    const groups = new Map();
    for (const f of (fits || [])) {
        const key = String(f.algo);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(f);
    }
    const tables = [];
    for (const [algo, rows] of groups) {
        const names = getReportFitCoefNames(algo);
        const columns = [entityHeader, ...names, 'R²'];
        const outRows = rows.map(f => {
            const o = { [entityHeader]: f.entity };
            names.forEach((n, i) => { o[n] = _fmtCoef(f.coefficients[i]); });
            o['R²'] = Number(f.rSquared).toFixed(4);
            return o;
        });
        tables.push({
            title: `${algo} — ${getReportFitFormula(algo)}`,
            note: `where ${getReportFitWhere(algo)}`,
            columns, rows: outRows
        });
    }
    return tables;
}

// Fit algorithms offered in report dialogs (matches the data-display picker).
const REPORT_ALGO_OPTIONS = ['polynomial', 'linear', 'logarithmic', 'exponential', 'Michaelis-Menten'];

// Build the set of algorithm checkboxes for one metric / time point. Multiple
// fits can be selected so a single file's report can show several curves for the
// same metric/time point. 'linear' is checked by default.
function _reportAlgoChecksHtml(groupCls) {
    return REPORT_ALGO_OPTIONS.map(a =>
        `<label style="display:inline-flex; align-items:center; gap:3px; margin-right:10px; font-size:0.8rem; white-space:nowrap;">
            <input type="checkbox" class="${groupCls}" value="${a}" ${a === 'linear' ? 'checked' : ''}> ${a}
        </label>`).join('');
}

// Short algorithm labels used by the Full-report item cards.
const REPORT_ALGO_CHOICES = [
    { id: 'polynomial', label: 'Poly' },
    { id: 'linear', label: 'Lin' },
    { id: 'logarithmic', label: 'Log' },
    { id: 'exponential', label: 'Exp' },
    { id: 'Michaelis-Menten', label: 'MM' }
];

// One point-mode time-point entry for a Full-report card: a time-point <select>,
// a remove button and its own multiple-fit checkboxes. Used both in the initial
// card render and when the user clicks "+ Add time point".
function _fullPointTpEntryHtml(filename, timePoints) {
    return `<div class="point-tp-entry" style="border:1px solid #e2e8f0; border-radius:5px; padding:6px; margin-bottom:6px;">
        <div style="display:flex; align-items:center; gap:6px; margin-bottom:4px;">
            <select class="point-timepoint-select" data-filename="${filename}" onchange="updatePointPreview('${filename}')" style="flex:1;">
                <option value="">All time points</option>
                ${timePoints.map(tp => `<option value="${tp}">${tp}</option>`).join('')}
            </select>
            <button type="button" class="point-tp-remove" onclick="removePointTimePoint(this, '${filename}')" data-hint="Remove time point"
                style="border:none; background:#fdecea; color:#c0392b; border-radius:4px; cursor:pointer; padding:2px 8px;">✕</button>
        </div>
        <div style="display:flex; flex-wrap:wrap; gap:5px; font-size:0.7rem;">
            ${REPORT_ALGO_CHOICES.map(a => `
                <label class="algo-include-label" data-hint="${a.label}" style="cursor:pointer; background:#f0f0f0; padding:2px 4px; border-radius:3px;">
                    <input type="checkbox" class="point-algo-checkbox" data-filename="${filename}" data-algo="${a.id}" ${a.id === 'linear' ? 'checked' : ''}>
                    ${a.label}
                </label>`).join('')}
        </div>
    </div>`;
}

// Recompute the available discrete time points for a Full-report item.
function _reportItemTimePoints(filename) {
    const config = window.ReportItemConfig ? window.ReportItemConfig[filename] : null;
    if (!config) return [];
    return [...new Set((config.data || []).map(r => r['TimePoint']).filter(v => v != null && v !== 'NONE'))]
        .sort((a, b) => parseFloat(a) - parseFloat(b));
}

// "+ Add time point" / "✕ remove" handlers for Full-report point cards.
function addPointTimePoint(filename) {
    const list = document.querySelector(`.report-item-card[data-filename="${CSS.escape(filename)}"] .point-tp-list`);
    if (list) list.insertAdjacentHTML('beforeend', _fullPointTpEntryHtml(filename, _reportItemTimePoints(filename)));
}
function removePointTimePoint(btn, filename) {
    const list = btn.closest('.point-tp-list');
    if (list && list.querySelectorAll('.point-tp-entry').length > 1) {
        btn.closest('.point-tp-entry').remove();
        updatePointPreview(filename);
    }
}

// Extract the point-mode calibration standards (Concentration, Value), filtered
// to a time point. When `timePointOverride` is provided (incl. '' = all points)
// it wins; otherwise the live data-display picker is used, the same way
// updatePlotBasedOnMode() builds the on-screen chart.
function getPointCalibrationData(timePointOverride) {
    const timePoint = (timePointOverride !== undefined && timePointOverride !== null)
        ? timePointOverride
        : document.getElementById('regressed-time-point')?.value;
    const rows = (AppState.responseData || []).filter(r =>
        !timePoint || parseFloat(r['TimePoint']) === parseFloat(timePoint));
    const pts = rows
        .filter(r => r['Concentration'] !== 'NONE' && r['Value'] !== 'NONE')
        .map(r => ({ x: parseFloat(r['Concentration']), y: parseFloat(r['Value']) }))
        .filter(p => !isNaN(p.x) && !isNaN(p.y))
        .sort((a, b) => a.x - b.x);
    return { x: pts.map(p => p.x), y: pts.map(p => p.y) };
}

// Build the {x,y} points of a calibration regression curve across the
// concentration domain [xMin..xMax] (padded 10%), inverting the fitted
// metric→concentration relationship. Mirrors getRegressionData() and the inline
// loops in the kinetics report branches. Returns [] when there are no coefficients.
function buildCalibrationRegressionLine(xConc, coefficients, algo) {
    if (!coefficients || !xConc || xConc.length === 0) return [];
    const xMin = Math.min(...xConc), xMax = Math.max(...xConc);
    const range = (xMax - xMin) || Math.abs(xMax) || 1;
    const pXMin = xMin - 0.1 * range, pXMax = xMax + 0.1 * range;
    const step = (pXMax - pXMin) / 149;
    const [a = 0, b = 0, c = 0] = coefficients;
    const line = [];
    for (let j = 0; j < 150; j++) {
        const x = pXMin + j * step;
        let y = 0;
        if (algo === 'linear') y = a !== 0 ? (x - b) / a : 0;
        else if (algo === 'polynomial') {
            if (a === 0) y = b !== 0 ? (x - c) / b : 0;
            else { const d = b * b - 4 * a * (c - x); y = d >= 0 ? (-b + Math.sqrt(d)) / (2 * a) : 0; }
        } else if (algo === 'logarithmic') y = a !== 0 ? Math.exp((x - c) / a) - b : 0;
        else if (algo === 'exponential') y = (a !== 0 && x > c && b !== 0) ? Math.log((x - c) / a) / b : 0;
        else if (algo === 'Michaelis-Menten') y = (a * x) / (b + x);
        line.push({ x, y });
    }
    return line;
}

// Build a native-chart series descriptor for the Excel exporter. Instead of a
// baked-in PNG, this ships the raw standards points + fit-line points and the
// axis labels so the backend can emit an editable ScatterChart whose axis
// titles can be renamed inside Excel. xLabel/yLabel may be user overrides from
// the export dialog; blank falls back to the per-chart natural label.
function buildScatterSeries({ xConc, yMetric, regLine, title, label, algo, xLabel, yLabel }) {
    return {
        label: label || title,
        title: title,
        algo: algo,
        xLabel: (xLabel && xLabel.trim()) || 'Concentration',
        yLabel: (yLabel && yLabel.trim()) || 'Value',
        points: (xConc || []).map((x, i) => ({ x, y: (yMetric || [])[i] })),
        fit: regLine || []
    };
}

// Default X-axis label for a calibration chart: "Concentration (<unit>)", honoring
// the file's `# ConcenUnit` (the post-602bb94 schema — ng/µL, nM, %), mirroring the
// live chart (generate-chart.js) and the report's derived-concentration lines. A
// label only; it never converts the plotted values. `metadata` is the file's CSV
// metadata (AppState.metaData for the current file, config.metadata in the console).
function _concenAxisLabel(metadata) {
    const unit = (typeof getMetaConcenUnit === 'function') ? getMetaConcenUnit(metadata) : 'ng/µL';
    return `Concentration (${unit})`;
}

// Render a calibration scatter (standards) + fit line to a PNG data URL,
// off-screen at print resolution. Shared by the PDF and Excel generators.
function renderCalibrationChartImage({ xConc, yMetric, regLine, title, yLabel, algo, xLabel }) {
    return new Promise(resolve => {
        const cv = document.createElement('canvas');
        cv.width = 1600; cv.height = 800;
        const tc = new Chart(cv.getContext('2d'), {
            type: 'scatter',
            data: {
                datasets: [
                    { label: 'Standards', data: xConc.map((x, i) => ({ x, y: yMetric[i] })), backgroundColor: '#3498db', pointRadius: 6 },
                    { label: `Fit (${algo})`, data: regLine, type: 'line', borderColor: '#e74c3c', borderWidth: 3, fill: false, pointRadius: 0, tension: 0.2 }
                ]
            },
            options: {
                responsive: false, animation: false,
                plugins: {
                    title: { display: true, text: title, font: { size: 18 } },
                    legend: { display: true, position: 'bottom' }
                },
                scales: {
                    x: { title: { display: true, text: xLabel || 'Concentration', font: { size: 14, weight: 'bold' } } },
                    y: { title: { display: true, text: yLabel, font: { size: 14, weight: 'bold' } } }
                }
            }
        });
        setTimeout(() => { const img = cv.toDataURL('image/png'); tc.destroy(); resolve(img); }, 250);
    });
}

async function generateReport() {
    const isCalibrate = AppState.currentMeasurementMode === 'calibrate';

    // 1. Ask for a title, fit algorithm, the calibration selection (kinetics:
    //    which metrics; point: which time point), and the export format.
    const calSubMode    = isCalibrate ? _calSubMode() : null;
    const isKineticsCal = calSubMode === 'kinetics';
    const isPointCal    = calSubMode === 'point';

    // Kinetics: the metrics present in the loaded standard curve. Each metric has
    // an include checkbox plus a set of fit-algorithm checkboxes (multiple fits
    // allowed). Unchecking the metric disables its algorithm checkboxes.
    const availableMetrics = (AppState.calibrationDataPoints || []).map(d => d.metric);
    const metricRows = availableMetrics.map(m =>
        `<div class="swal-metric-row" style="border:1px solid #eee; border-radius:6px; padding:6px 8px; margin:4px 0;">
            <label style="display:flex; align-items:center; gap:6px; cursor:pointer; font-weight:600;">
                <input type="checkbox" class="swal-metric" value="${m}" checked> ${m}
            </label>
            <div class="swal-metric-algos" style="margin-top:4px; margin-left:22px;">
                ${_reportAlgoChecksHtml('swal-metric-algo')}
            </div>
        </div>`).join('');

    // Point: the time points available in the data (mirrors the data-display picker).
    // The dialog starts with one time-point entry and the user can add more with a
    // "+" button; each entry picks a time point and one or more fit algorithms.
    const pointTimePoints = [...new Set((AppState.responseData || [])
        .map(r => r['TimePoint']).filter(v => v != null && v !== 'NONE'))]
        .sort((a, b) => parseFloat(a) - parseFloat(b));
    const currentTimePoint = document.getElementById('regressed-time-point')?.value ?? '';
    const tpOptionsHtml = `<option value="">All time points (pooled)</option>` +
        pointTimePoints.map(tp =>
            `<option value="${tp}" ${String(tp) === String(currentTimePoint) ? 'selected' : ''}>t = ${tp}</option>`).join('');
    // One time-point entry: a time-point <select>, a remove button and the algo checks.
    const tpEntryHtml = () =>
        `<div class="swal-tp-entry" style="border:1px solid #eee; border-radius:6px; padding:6px 8px; margin:4px 0;">
            <div style="display:flex; align-items:center; gap:8px;">
                <select class="swal-tp-select" style="margin:0; padding:2px 4px; height:auto; font-size:0.85rem; flex:1;">${tpOptionsHtml}</select>
                <button type="button" class="swal-tp-remove" data-hint="Remove this time point"
                    style="border:none; background:#fdecea; color:#c0392b; border-radius:4px; cursor:pointer; padding:2px 8px;">✕</button>
            </div>
            <div class="swal-tp-algos" style="margin-top:4px;">
                ${_reportAlgoChecksHtml('swal-tp-algo')}
            </div>
        </div>`;

    const { value: formValues } = await Swal.fire({
        title: 'Report Details',
        html: `
            <div style="text-align: left;">
                <label style="display:block; margin-bottom:5px;">Report Title</label>
                <input id="swal-input1" class="swal2-input" value="Colorimetric Analysis Report" style="width: 80%; margin: 0 0 15px 0;">
                ${isKineticsCal ? `
                <label style="display:block; margin-bottom:5px;">Metrics &amp; fit algorithms</label>
                <div id="swal-metrics" style="display:flex; flex-direction:column; gap:2px; margin:0 0 6px 4px;">
                    ${metricRows || '<span style="color:#888;">No metrics available.</span>'}
                </div>
                <div style="font-size:0.8rem; color:#888; margin-bottom:15px;">Tick one or more fits per metric. Unchecking a metric disables its fits. A fit that can't be resolved is omitted, with a warning.</div>` : ''}
                ${isPointCal ? `
                <label style="display:block; margin-bottom:5px;">Time points &amp; fit algorithms</label>
                <div id="swal-timepoints" style="display:flex; flex-direction:column; gap:2px; margin:0 0 6px 4px;">
                    ${tpEntryHtml()}
                </div>
                <button type="button" id="swal-tp-add" style="margin:0 0 6px 4px; padding:3px 10px; border:1px solid #3498db; background:#eaf4fc; color:#2980b9; border-radius:5px; cursor:pointer; font-size:0.85rem;">+ Add time point</button>
                <div style="font-size:0.8rem; color:#888; margin-bottom:15px;">Add a time point and tick one or more fits for it. One curve is produced per time point × fit.</div>` : ''}
                ${isCalibrate ? `
                <label style="display:block; margin:10px 0 5px;">Excel chart axis labels <span style="color:#888; font-weight:normal; font-size:0.8rem;">(editable later in Excel)</span></label>
                <div style="display:flex; gap:10px; margin-bottom:6px;">
                    <input id="swal-xlabel" class="swal2-input" placeholder="X-axis label" value="${_concenAxisLabel(AppState.metaData)}" style="margin:0; flex:1;">
                    <input id="swal-ylabel" class="swal2-input" placeholder="Y-axis (auto per metric)" style="margin:0; flex:1;">
                </div>
                <div style="font-size:0.8rem; color:#888; margin-bottom:15px;">Calibration charts export as native Excel charts. Leave Y blank to auto-label each chart with its metric.</div>` : ''}
                <label style="display:block; margin-bottom:5px;">Export Format</label>
                <div style="display:flex; gap:20px;">
                    <label style="cursor:pointer;"><input type="radio" name="swal-fmt" value="pdf" checked> PDF (print)</label>
                    <label style="cursor:pointer;"><input type="radio" name="swal-fmt" value="excel"> Excel (.xlsx)</label>
                </div>
            </div>
        `,
        focusConfirm: false,
        showCancelButton: true,
        didOpen: () => {
            // Kinetics: unchecking a metric disables its algorithm checkboxes.
            const syncMetricRow = (rowEl) => {
                const cb = rowEl.querySelector('.swal-metric');
                rowEl.querySelectorAll('.swal-metric-algo').forEach(a => { a.disabled = !cb.checked; });
                rowEl.style.opacity = cb.checked ? '1' : '0.5';
            };
            document.querySelectorAll('.swal-metric-row').forEach(rowEl => {
                syncMetricRow(rowEl);
                rowEl.querySelector('.swal-metric')?.addEventListener('change', () => syncMetricRow(rowEl));
            });

            // Point: "+ Add time point" appends an entry; "✕" removes one (keep ≥1).
            const list = document.getElementById('swal-timepoints');
            document.getElementById('swal-tp-add')?.addEventListener('click', () => {
                list.insertAdjacentHTML('beforeend', tpEntryHtml());
            });
            list?.addEventListener('click', (e) => {
                if (!e.target.classList.contains('swal-tp-remove')) return;
                const entries = list.querySelectorAll('.swal-tp-entry');
                if (entries.length > 1) e.target.closest('.swal-tp-entry').remove();
            });
        },
        preConfirm: () => {
            const title  = document.getElementById('swal-input1').value;
            const fmt    = document.querySelector('input[name="swal-fmt"]:checked')?.value || 'pdf';
            // Native Excel-chart axis-label overrides (calibration only).
            const axisLabels = {
                x: document.getElementById('swal-xlabel')?.value || '',
                y: document.getElementById('swal-ylabel')?.value || ''
            };
            if (!isCalibrate) return { title, fmt };
            if (isKineticsCal) {
                // Map each *checked* metric to the list of fit algorithms ticked on its row.
                const metricAlgos = {};
                document.querySelectorAll('.swal-metric-row').forEach(rowEl => {
                    const cb = rowEl.querySelector('.swal-metric');
                    if (!cb || !cb.checked) return;
                    const algos = Array.from(rowEl.querySelectorAll('.swal-metric-algo:checked')).map(c => c.value);
                    if (algos.length) metricAlgos[cb.value] = algos;
                });
                if (availableMetrics.length && Object.keys(metricAlgos).length === 0) {
                    Swal.showValidationMessage('Select at least one metric with at least one fit algorithm.');
                    return false;
                }
                return { title, fmt, metricAlgos, axisLabels };
            }
            if (isPointCal) {
                // One entry per time-point row, each with its list of ticked algorithms.
                const timePointAlgos = [];
                document.querySelectorAll('.swal-tp-entry').forEach(entry => {
                    const sel   = entry.querySelector('.swal-tp-select');
                    const algos = Array.from(entry.querySelectorAll('.swal-tp-algo:checked')).map(c => c.value);
                    if (sel && algos.length) timePointAlgos.push({ timePoint: sel.value, algos });
                });
                if (timePointAlgos.length === 0) {
                    Swal.showValidationMessage('Add at least one time point with a fit algorithm.');
                    return false;
                }
                return { title, fmt, timePointAlgos, axisLabels };
            }
            return { title, fmt, axisLabels };
        }
    });

    if (!formValues) return;
    const reportTitle       = formValues.title;
    const reportFormat      = formValues.fmt;
    const metricAlgos       = formValues.metricAlgos || null;     // kinetics calibrate: { metric: [algos] }
    const timePointAlgos    = formValues.timePointAlgos || null;  // point calibrate: [{ timePoint, algos: [algos] }]
    // Curves that could not be produced for the user's selection; surfaced as a
    // warning (modal + in-report banner) once generation finishes.
    const calibrationWarnings = [];
    logEvent('report', 'generate', { mode: AppState.currentMeasurementMode, format: reportFormat });

    if (reportFormat === 'excel') {
        await generateReportExcelFromCurrent(reportTitle, { metricAlgos, timePointAlgos, axisLabels: formValues.axisLabels });
        return;
    }

    // 2. Gather data
    const selectedFile = document.getElementById('selected-file-display') ? document.getElementById('selected-file-display').innerText.replace('Selected File: ', '') : 'No file selected';
    const timestamp = new Date().toLocaleString();
    const measMode = AppState.currentMeasurementMode || "Unknown";
    const splitMode = AppState.multiSource ? `Yes (${AppState.numSources} sources)` : "No";
    // For calibrate the algorithm now varies per metric / time point, so the
    // header summarises the distinct fits used and the per-row tables carry the
    // formulas. For standard mode the single curve JSON's fit_type is shown.
    let calCurve, calFormula;
    if (isCalibrate) {
        const algosUsed = isKineticsCal
            ? [...new Set(Object.values(metricAlgos || {}).flat())]
            : [...new Set((timePointAlgos || []).flatMap(t => t.algos))];
        calCurve = algosUsed.join(', ') || 'N/A';
        calFormula = ''; // per-row Function columns carry the formulas
    } else {
        calCurve = AppState.currentJSON || "None selected";
        calFormula = getReportFitFormula((AppState.currentJSONcontent && AppState.currentJSONcontent.fit_type) || '');
    }

    // 2.1 Gather Analytical Content (Specialized for Calibration or Standard)
    let analyticalContent = "";
    let chartImageSrc = "";
    let concentrationResults = "";
    let analysisSummaries = "";

    if (isCalibrate && _calSubMode() === 'point') {
        // Point-mode calibration: one Value-vs-Concentration curve per selected
        // time point × fit algorithm.
        const measLabel = (AppState.metaData && AppState.metaData['Measurement']) || 'Value';
        let chartsMarkup = '<div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 20px;">';
        const fits = [];

        for (const { timePoint, algos } of (timePointAlgos || [])) {
            const pd = getPointCalibrationData(timePoint);
            const tpLabel = (timePoint !== '' && timePoint != null) ? `t=${timePoint}` : 'all pooled';
            for (const algo of algos) {
                const analysis = pd.x.length >= 2 ? calculateCoefAndRSquared(pd.y, pd.x, algo) : null;
                if (analysis && analysis.coefficients) {
                    const regLine = buildCalibrationRegressionLine(pd.x, analysis.coefficients, algo);
                    const chartImg = await renderCalibrationChartImage({
                        xConc: pd.x, yMetric: pd.y, regLine,
                        title: `Calibration Curve (${measLabel} @ ${tpLabel}) — ${algo}`, yLabel: measLabel, algo,
                        xLabel: _concenAxisLabel(AppState.metaData)
                    });
                    chartsMarkup += `
                        <div style="width: 48%; margin-bottom: 20px; border: 1px solid #eee; padding: 10px; border-radius: 8px; background: #fff;">
                            <img src="${chartImg}" style="width: 100%; height: auto;"/>
                        </div>`;
                    fits.push({ entity: `${measLabel} @ ${tpLabel}`, algo, coefficients: analysis.coefficients, rSquared: analysis.rSquared });
                } else {
                    calibrationWarnings.push(`Point calibration @ ${tpLabel}: no ${algo} curve could be fitted — at least two concentration points are required (found ${pd.x.length}).`);
                }
            }
        }
        chartsMarkup += '</div>';

        analyticalContent = `
            <div class="report-analysis">
                <h3 style="color:#2c3e50; border-bottom: 1px solid #eee; padding-bottom:10px;">Calibration Curves</h3>
                ${fits.length ? chartsMarkup : '<p style="color:#888;">No calibration curve could be fitted for the selected time point(s).</p>'}
            </div>
            ${fits.length ? `
            <div class="report-results" style="margin-top:30px; margin-bottom:30px; border-left:4px solid #3498db; padding-left:20px;">
                <h3 style="margin-top:0; color:#2c3e50;">Calibration Fit Analysis</h3>
                ${_renderCoefTablesHtml('Time Point', fits)}
            </div>` : ''}
        `;
    } else if (isCalibrate && AppState.calibrationDataPoints && AppState.lastAnalyses) {
        // Specialized Calibration Quad-Report
        const fits = [];
        let chartsMarkup = '<div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 20px;">';

        for (let i = 0; i < AppState.calibrationDataPoints.length; i++) {
            const dataPoint = AppState.calibrationDataPoints[i];
            // Each metric is fitted with the algorithms ticked on its dialog row;
            // metrics left unchecked have no entry in metricAlgos and are skipped.
            const algos = metricAlgos ? metricAlgos[dataPoint.metric] : null;
            if (!algos || !algos.length) continue;

            for (const algo of algos) {
            // Recalculate coefficients based on the per-metric algo for the report
            const analysis = calculateCoefAndRSquared(dataPoint.y, dataPoint.x, algo);
            // Skip metrics the fit could not resolve (e.g. a calibration column with
            // only one non-"NONE" point yields coefficients: null). Matches the other
            // report generators; without this guard `analysis.coefficients.length`
            // below throws "Cannot read properties of null (reading 'length')". The
            // user is warned about any metric they selected that has no curve.
            if (!analysis || !analysis.coefficients) {
                calibrationWarnings.push(`${dataPoint.metric}: no ${algo} calibration curve could be fitted (insufficient or unsuitable data).`);
                continue;
            }

            // 1. Collect the fit (grouped into per-algorithm tables later)
            fits.push({ entity: dataPoint.metric, algo, coefficients: analysis.coefficients, rSquared: analysis.rSquared });

            // 2. Build high-res chart for this metric
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = 1600; tempCanvas.height = 800;
            const tempCtx = tempCanvas.getContext('2d');
            const regressAlgo = algo;

            // Generate regression curve points
            const xMin = Math.min(...dataPoint.x);
            const xMax = Math.max(...dataPoint.x);
            const range = xMax - xMin;
            const plotXMin = xMin - 0.1 * range;
            const plotXMax = xMax + 0.1 * range;
            const step = (plotXMax - plotXMin) / 149;
            const regressionLine = [];
            for (let j = 0; j < 150; j++) {
                const curX = plotXMin + j * step;
                let curY = 0;

                if (regressAlgo === "linear") {
                    const [a, b] = analysis.coefficients || [0, 0];
                    curY = a !== 0 ? (curX - b) / a : 0;
                } else if (regressAlgo === "polynomial") {
                    const [c2, c1, c0] = analysis.coefficients || [0, 0, 0];
                    if (c2 === 0) {
                        curY = c1 !== 0 ? (curX - c0) / c1 : 0;
                    } else {
                        const discriminant = c1 * c1 - 4 * c2 * (c0 - curX);
                        curY = discriminant >= 0 ? (-c1 + Math.sqrt(discriminant)) / (2 * c2) : 0;
                    }
                } else if (regressAlgo === "logarithmic") {
                    const [a, b, c] = analysis.coefficients || [0, 0, 0];
                    curY = a !== 0 ? Math.exp((curX - c) / a) - b : 0;
                } else if (regressAlgo === "exponential") {
                    const [a, b, c] = analysis.coefficients || [0, 0, 0];
                    curY = (a !== 0 && curX > c && b !== 0) ? Math.log((curX - c) / a) / b : 0;
                } else if (regressAlgo === "Michaelis-Menten") {
                    const [Vmax, Km] = analysis.coefficients || [1, 1];
                    curY = (Vmax * curX) / (Km + curX);
                }
                regressionLine.push({ x: curX, y: curY });
            }

            const tempChart = new Chart(tempCtx, {
                type: 'scatter',
                data: {
                    datasets: [
                        {
                            label: 'Standards',
                            data: dataPoint.x.map((x, idx) => ({ x: x, y: dataPoint.y[idx] })),
                            backgroundColor: '#3498db',
                            pointRadius: 6
                        },
                        {
                            label: `Fit (${regressAlgo})`,
                            data: regressionLine,
                            type: 'line',
                            borderColor: '#e74c3c',
                            borderWidth: 3,
                            fill: false,
                            pointRadius: 0,
                            tension: 0.2
                        }
                    ]
                },
                options: {
                    responsive: false, animation: false,
                    plugins: {
                        title: { display: true, text: `Calibration Curve against ${dataPoint.metric}`, font: { size: 18 } },
                        legend: { display: true, position: 'bottom' }
                    },
                    scales: {
                        x: { title: { display: true, text: _concenAxisLabel(AppState.metaData), font: { size: 14, weight: 'bold' } } },
                        y: { title: { display: true, text: dataPoint.metric, font: { size: 14, weight: 'bold' } } }
                    }
                }
            });

            const chartImg = tempCanvas.toDataURL('image/png');
            chartsMarkup += `
                <div style="width: 48%; margin-bottom: 20px; border: 1px solid #eee; padding: 10px; border-radius: 8px; background: #fff;">
                    <img src="${chartImg}" style="width: 100%; height: auto;"/>
                </div>`;
            tempChart.destroy();
            } // end algo loop
        }
        chartsMarkup += '</div>';

        analyticalContent = `
            <div class="report-analysis">
                <h3 style="color:#2c3e50; border-bottom: 1px solid #eee; padding-bottom:10px;">Metric-Specific Calibration Curves</h3>
                ${chartsMarkup}
            </div>
            <div class="report-results" style="margin-top:30px; margin-bottom:30px; border-left:4px solid #3498db; padding-left:20px;">
                <h3 style="margin-top:0; color:#2c3e50;">Calibration Fit Analysis</h3>
                ${_renderCoefTablesHtml('Metric', fits)}
            </div>
        `;
    } else {
        // Standard Measurement Report Trace Analysis
        if (AppState.lastAnalyses && AppState.lastAnalyses.length > 0) {
            const unitDisplay = getMetaUnit(AppState.metaData) !== "NONE" ? getMetaUnit(AppState.metaData) : '';
            const timeUnit = getTimeUnitValue() ? getTimeUnitValue().slice(0, -1) : 'min';

            AppState.lastAnalyses.forEach((rawAnalysis, idx) => {
                const label = AppState.lastAnalyses.length > 1 ? `Source ${idx + 1}` : "";
                const info = formatAnalysisInfo(rawAnalysis, label || "Measurement");
                if (!info) return;

                const displaySat = (!isNaN(info.saturationValue)) ? info.saturationValue : "--";
                const displayTimeSat = (!isNaN(info.timeToSaturation)) ? info.timeToSaturation : "--";

                analysisSummaries += `
                    <div style="margin-top:10px; border-top: 1px solid #eee; padding-top:10px; page-break-inside: auto;">
                        <strong style="color: #2c3e50; display:block; margin-bottom:5px;">${label ? label + " Analysis" : "Measurement Analysis"}</strong>
                        <table style="width:100%; border-collapse: collapse; font-size: 0.8rem; margin-bottom: 20px; border:1px solid #eee;">
                            <tr style="background:#f8f9fa; border-bottom: 2px solid #3498db;">
                                <th style="padding:8px; border:1px solid #eee;">Metric</th>
                                <th style="padding:8px; border:1px solid #eee;">Value</th>
                                <th style="padding:8px; border:1px solid #eee;">Range / Context</th>
                            </tr>
                            <tr><td style="padding:8px; border:1px solid #eee; font-weight:bold;">Slope</td><td style="padding:8px; border:1px solid #eee;">${info.slope} ${unitDisplay}/${timeUnit}</td><td style="padding:8px; border:1px solid #eee;">${info.linearStart} to ${info.linearEnd} ${timeUnit}</td></tr>
                            <tr style="background:#fcfcfc;"><td style="padding:8px; border:1px solid #eee; font-weight:bold;">Max Rate</td><td style="padding:8px; border:1px solid #eee;">${info.maxRate} ${unitDisplay}/${timeUnit}</td><td style="padding:8px; border:1px solid #eee;">${info.maxRateStart} to ${info.maxRateEnd} ${timeUnit}</td></tr>
                            <tr><td style="padding:8px; border:1px solid #eee; font-weight:bold;">Saturation</td><td style="padding:8px; border:1px solid #eee;">${displaySat} ${unitDisplay}</td><td style="padding:8px; border:1px solid #eee;">at ${displayTimeSat} ${timeUnit}</td></tr>
                        </table>
                    </div>`;
            });
        }

        // Gather Derived Concentrations
        const derConSections = document.querySelectorAll('[id^="derived-concentration-section-source-"]');
        derConSections.forEach((sec, idx) => {
            if (!sec.classList.contains('hidden')) {
                const val = sec.querySelector('.der-con-value')?.innerText || "--";
                concentrationResults += `<div style="margin-bottom:8px; font-size: 1.1rem;">Concentration (Source ${idx + 1}): <strong style="color:#2980b9;">${val} ${_reportConcenUnit(AppState.currentJSONcontent)}</strong></div>`;
            }
        });

        const chartKeys = Object.keys(AppState.chartInstances);
        if (chartKeys.length > 0) {
            const originalChart = AppState.chartInstances[chartKeys[0]];
            if (originalChart) {
                const tempCanvas = document.createElement('canvas');
                tempCanvas.width = 1600; tempCanvas.height = 800;
                const tempCtx = tempCanvas.getContext('2d');
                const tempChart = new Chart(tempCtx, {
                    type: originalChart.config.type,
                    data: JSON.parse(JSON.stringify(originalChart.config.data)),
                    options: {
                        ...originalChart.config.options,
                        responsive: false, animation: false,
                        plugins: { ...originalChart.config.options.plugins, legend: { display: true, position: 'bottom' } },
                        scales: { x: { title: { display: true, font: { weight: 'bold' } } }, y: { title: { display: true, font: { weight: 'bold' } } } }
                    }
                });
                chartImageSrc = tempCanvas.toDataURL('image/png');
                tempChart.destroy();
            }
        }
    }


    // 3. Build the final printable content
    // For standard mode, analyticalContent is built here if not already set by calibration mode
    if (!isCalibrate) {
        analyticalContent = `
            ${chartImageSrc ? `
            <div class="report-chart-block" style="text-align: center; margin-bottom: 30px;">
                <img src="${chartImageSrc}" style="width:100%; border:1px solid #eee;"/>
            </div>` : ''}

            ${concentrationResults ? `
            <div class="report-results" style="background:#f0f7ff; padding:20px; border-radius:8px; border:1px solid #d0e7ff; margin-bottom:20px;">
                <h3 style="margin-top:0; color:#2980b9; border-bottom:1px solid #d0e7ff; padding-bottom:10px;">Analytical Results</h3>
                ${calFormula ? `<p style="font-size:0.8rem; color:#555; margin:0 0 10px;">Derived using calibration function <strong>${calFormula}</strong> — where ${getReportFitWhere((AppState.currentJSONcontent && AppState.currentJSONcontent.fit_type) || '')}.</p>` : ''}
                ${concentrationResults}
            </div>` : ''}

            ${analysisSummaries ? `
            <div class="report-analysis" style="background:#fff; border:1px solid #eee; padding:20px; border-radius:8px;">
                <h3 style="margin-top:0; color:#34495e;">Measurement Trace Analysis</h3>
                <div class="analysis-tables-container">
                    ${analysisSummaries}
                </div>
            </div>` : ''}
        `;
    }

    const calibrationWarningBanner = calibrationWarnings.length ? `
        <div style="background:#fff8e1; border:1px solid #ffe082; color:#8a6d3b; padding:12px 16px; border-radius:8px; margin-bottom:20px;">
            ⚠️ <strong>Some calibration curves were not available:</strong><br>${calibrationWarnings.join('<br>')}
        </div>` : '';

    const htmlContent = `
        <div class="report-header" style="position:relative; z-index:10; display:flex; justify-content:space-between; border-bottom:2px solid #3498db; padding-bottom:20px; margin-bottom:30px;">
            <div>
                <h1 style="margin: 0; font-size: 2rem; color: #3498db;">Easy<span style="color: #ff4444;">OKAPI</span> Report</h1>
                <h2 style="margin: 5px 0; font-size: 1.5rem; color:#333;">${reportTitle}</h2>
                <p style="margin: 5px 0; color: #666;">File: <strong>${selectedFile}</strong></p>
                <div style="margin-top:10px; font-size:0.9rem; display:grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                    <span>Mode: <strong>${measMode}</strong></span>
                    ${isCalibrate ? '' : `<span>Split Mode: <strong>${splitMode}</strong></span>`}
                    <span>${isCalibrate ? 'Calibration Fit Type' : 'Calibration Curve'}: <strong>${calCurve}</strong></span>
                    ${calFormula ? `<span>Function: <strong>${calFormula}</strong></span>` : ''}
                    <span>Generated: <strong>${timestamp}</strong></span>
                </div>
            </div>
            <img src="/static/cbb.png" style="height: 70px;" />
        </div>

        <img src="/static/cbb.png" class="report-watermark-bg" style="position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); opacity:0.04; width:70%; z-index:1; pointer-events:none;" />

        <div class="report-body" style="position:relative; z-index:10;">
            ${calibrationWarningBanner}
            ${analyticalContent}
        </div>

        <div class="report-footer" style="margin-top:50px; text-align:center; font-size:0.75rem; color:#999; border-top:1px solid #eee; padding-top:20px;">
            Generated by EasyOKAPI Analytical Suite v1.0
        </div>
    `;

    // 4. Inject into the DOM
    const printContainer = document.getElementById('print-report-container');
    printContainer.innerHTML = htmlContent;

    // Be extremely explicit
    printContainer.classList.remove('hidden');
    printContainer.classList.add('report-mode');

    // Warn the user about any curve they selected that could not be produced,
    // before the print dialog opens.
    if (calibrationWarnings.length) {
        await Swal.fire({
            icon: 'warning',
            title: 'Some calibration curves unavailable',
            html: calibrationWarnings.map(w => `• ${w}`).join('<br>') +
                  '<br><br>The report was generated with the available curves.'
        });
    }

    setTimeout(() => {
        console.log("Triggering window.print() for Quick Report");
        window.print();
        printContainer.classList.add('hidden');
        printContainer.classList.remove('report-mode');
    }, 1000);
}

async function generateReportExcelFromCurrent(reportTitle, options = {}) {
    // options.metricAlgos    → kinetics calibrate: { metric: [algos] } for each chosen metric
    // options.timePointAlgos → point calibrate: [{ timePoint, algos: [algos] }] for each chosen time point
    const metricAlgos    = options.metricAlgos || null;
    const timePointAlgos  = options.timePointAlgos || null;
    const axisLabels      = options.axisLabels || {};   // { x, y } native-chart label overrides
    const calibrationWarnings = [];
    window.showSpinner();
    try {
        const isCalibrate = AppState.currentMeasurementMode === 'calibrate';
        const isKinetics  = AppState.currentMeasurementMode === 'kinetics';
        const isPoint     = AppState.currentMeasurementMode === 'point';

        const currentFile = AppState.currentFile;
        if (!currentFile) {
            Swal.fire('No File', 'Please select a file first.', 'warning');
            return;
        }
        const dir      = AppState.currentDirectory;
        const fullPath = dir + (dir.endsWith(DELIMITER) ? '' : DELIMITER) + currentFile;

        // Fetch raw CSV data from server
        const dataResp   = await $.get('/get_data', { file: fullPath });
        const renderData = dataResp.data || [];
        const numSources = dataResp.num_sources || 1;
        const shouldNormalize = (isKinetics || isPoint) && (document.getElementById('normalize-mode')?.checked || false);

        const itemData = {
            filename:      currentFile,
            mode:          AppState.currentMeasurementMode || 'N/A',
            chart_images:  [],
            chart_series:  [],
            csv_columns:   [],
            csv_rows:      [],
            analysis_rows: [],
            coef_rows:     [],
            coef_tables:   [],
            derived_lines: []
        };

        if (isCalibrate && _calSubMode() === 'point') {
            // ── Point-mode calibration ──────────────────────────────────────
            // One Value-vs-Concentration fit per selected time point × algorithm.
            const measLabel = (AppState.metaData && AppState.metaData['Measurement']) || 'Value';

            itemData.csv_columns = ['Concentration', 'Value', 'TimePoint'];
            itemData.csv_rows = renderData.map(row => ({
                Concentration: row['Concentration'], Value: row['Value'], TimePoint: row['TimePoint']
            }));

            const fits = [];
            for (const { timePoint, algos } of (timePointAlgos || [])) {
                const pd = getPointCalibrationData(timePoint);
                const tpLabel = (timePoint !== '' && timePoint != null) ? `t=${timePoint}` : 'all pooled';
                for (const algo of algos) {
                const analysis = pd.x.length >= 2 ? calculateCoefAndRSquared(pd.y, pd.x, algo) : null;
                if (analysis && analysis.coefficients) {
                    const fitLabel = `${measLabel} @ ${tpLabel} — ${algo}`;
                    fits.push({ entity: `${measLabel} @ ${tpLabel}`, algo, coefficients: analysis.coefficients, rSquared: analysis.rSquared });
                    const regLine = buildCalibrationRegressionLine(pd.x, analysis.coefficients, algo);
                    itemData.chart_series.push(buildScatterSeries({
                        xConc: pd.x, yMetric: pd.y, regLine,
                        title: fitLabel, label: fitLabel, algo,
                        xLabel: axisLabels.x || _concenAxisLabel(AppState.metaData), yLabel: axisLabels.y || measLabel
                    }));
                } else {
                    calibrationWarnings.push(`Point calibration @ ${tpLabel}: no ${algo} curve could be fitted — at least two concentration points are required (found ${pd.x.length}).`);
                }
                } // end algo loop
            }
            itemData.coef_tables = _buildCoefTables('Time Point', fits);

        } else if (isCalibrate && AppState.calibrationDataPoints && AppState.calibrationDataPoints.length > 0) {
            // ── Calibrate mode ──────────────────────────────────────────────
            const xCol      = dataResp.metadata?.XColumn || 'Concentration';
            const calMetrics = ['Slope', 'Time To Sat', 'maxRate', 'Sat'];

            itemData.csv_columns = [xCol, ...calMetrics];
            itemData.csv_rows    = renderData.map(row => {
                const r = {};
                itemData.csv_columns.forEach(col => { r[col] = row[col]; });
                return r;
            });

            const fits = [];
            for (const dataPoint of AppState.calibrationDataPoints) {
                // Fit each metric with the algorithms ticked on its dialog row;
                // metrics left unchecked have no entry in metricAlgos and are skipped.
                const algos = metricAlgos ? metricAlgos[dataPoint.metric] : null;
                if (!algos || !algos.length) continue;
                for (const algo of algos) {
                const analysis = calculateCoefAndRSquared(dataPoint.y, dataPoint.x, algo);
                if (!analysis || !analysis.coefficients) {
                    calibrationWarnings.push(`${dataPoint.metric}: no ${algo} calibration curve could be fitted (insufficient or unsuitable data).`);
                    continue;
                }

                const [ca, cb2, cc] = analysis.coefficients;
                const niceMetric = dataPoint.metric.charAt(0).toUpperCase() +
                    dataPoint.metric.slice(1).replace(/([A-Z])/g, ' $1');
                const fitLabel = `${niceMetric} — ${algo}`;

                fits.push({ entity: dataPoint.metric, algo, coefficients: analysis.coefficients, rSquared: analysis.rSquared });

                // Build regression line
                const xMin  = Math.min(...dataPoint.x);
                const xMax  = Math.max(...dataPoint.x);
                const range = xMax - xMin;
                const pXMin = xMin - 0.1 * range;
                const pXMax = xMax + 0.1 * range;
                const step  = (pXMax - pXMin) / 149;
                const regLine = [];
                for (let j = 0; j < 150; j++) {
                    const curX = pXMin + j * step;
                    let curY = 0;
                    if (algo === 'linear')      curY = ca !== 0 ? (curX - cb2) / ca : 0;
                    else if (algo === 'polynomial') {
                        if (ca === 0) curY = cb2 !== 0 ? (curX - cc) / cb2 : 0;
                        else { const d = cb2 * cb2 - 4 * ca * (cc - curX); curY = d >= 0 ? (-cb2 + Math.sqrt(d)) / (2 * ca) : 0; }
                    } else if (algo === 'logarithmic') curY = ca !== 0 ? Math.exp((curX - cc) / ca) - cb2 : 0;
                    else if (algo === 'exponential')   curY = (ca !== 0 && curX > cc && cb2 !== 0) ? Math.log((curX - cc) / ca) / cb2 : 0;
                    else if (algo === 'Michaelis-Menten') curY = (ca * curX) / (cb2 + curX);
                    regLine.push({ x: curX, y: curY });
                }

                itemData.chart_series.push(buildScatterSeries({
                    xConc: dataPoint.x, yMetric: dataPoint.y, regLine,
                    title: fitLabel, label: fitLabel, algo,
                    xLabel: axisLabels.x || _concenAxisLabel(AppState.metaData), yLabel: axisLabels.y || niceMetric
                }));
                } // end algo loop
            }
            itemData.coef_tables = _buildCoefTables('Metric', fits);

        } else {
            // ── Standard / kinetics / point mode ────────────────────────────
            const visibleTraces = Array.from({ length: numSources }, (_, i) => i + 1);
            const displayData = shouldNormalize ? _normalizeTraces(renderData, visibleTraces) : renderData;
            const csvCols = ['Timestamp', ...visibleTraces.map(t => `Value:${t}`)];
            itemData.csv_columns = csvCols;
            itemData.csv_rows    = displayData.map(row => {
                const r = {};
                csvCols.forEach(col => { r[col] = row[col]; });
                return r;
            });

            // Analysis rows from AppState.lastAnalyses (already computed with correct time unit)
            if (AppState.lastAnalyses && AppState.lastAnalyses.length > 0) {
                const unitDisplay = getMetaUnit(AppState.metaData) !== 'NONE' ? getMetaUnit(AppState.metaData) : '';
                const timeUnit    = getTimeUnitValue() ? getTimeUnitValue().slice(0, -1) : 'min';

                AppState.lastAnalyses.forEach((rawAnalysis, idx) => {
                    const info = formatAnalysisInfo(rawAnalysis, `Source ${idx + 1}`);
                    if (!info) return;
                    const sat    = !isNaN(info.saturationValue)  ? info.saturationValue  : '--';
                    const timeSat = !isNaN(info.timeToSaturation) ? info.timeToSaturation : '--';
                    itemData.analysis_rows.push({
                        'Source':         `Source ${idx + 1}`,
                        'Slope':          `${info.slope}${unitDisplay ? ' ' + unitDisplay : ''}/${timeUnit}`,
                        'Slope Range':    `${info.linearStart} – ${info.linearEnd} ${timeUnit}`,
                        'Max Rate':       `${info.maxRate}${unitDisplay ? ' ' + unitDisplay : ''}/${timeUnit}`,
                        'Max Rate Range': `${info.maxRateStart} – ${info.maxRateEnd} ${timeUnit}`,
                        'Saturation':     `${sat}${unitDisplay ? ' ' + unitDisplay : ''}`,
                        'Time to Sat':    `${timeSat} ${timeUnit}`
                    });
                });
            }

            // Derived concentration values from DOM
            document.querySelectorAll('[id^="derived-concentration-section-source-"]').forEach((sec, idx) => {
                if (!sec.classList.contains('hidden')) {
                    const val = sec.querySelector('.der-con-value')?.innerText || '--';
                    itemData.derived_lines.push(`Source ${idx + 1}: ${val} ${_reportConcenUnit(AppState.currentJSONcontent)}`);
                }
            });

            // Prepend the calibration function used to derive those concentrations.
            const stdFitType = AppState.currentJSONcontent && AppState.currentJSONcontent.fit_type;
            if (itemData.derived_lines.length && stdFitType) {
                itemData.derived_lines.unshift(`Calibration function — ${getReportFitFunctionLabel(stdFitType)}`);
            }

            // Chart image from the live AppState chart instance
            const chartKeys = Object.keys(AppState.chartInstances || {});
            if (chartKeys.length > 0) {
                const orig = AppState.chartInstances[chartKeys[0]];
                if (orig) {
                    const cv = document.createElement('canvas');
                    cv.width = 1600; cv.height = 800;
                    const tc = new Chart(cv.getContext('2d'), {
                        type: orig.config.type,
                        data: JSON.parse(JSON.stringify(orig.config.data)),
                        options: {
                            ...orig.config.options,
                            responsive: false,
                            animation: false,
                            plugins: {
                                ...orig.config.options?.plugins,
                                legend: { display: true, position: 'bottom' }
                            }
                        }
                    });
                    await new Promise(r => setTimeout(r, 500));
                    itemData.chart_images.push({ label: currentFile, b64: cv.toDataURL('image/png') });
                    tc.destroy();
                }
            }
        }

        // POST → download
        const response = await fetch('/export_report_excel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title:        reportTitle,
                subject:      currentFile,
                split_sheets: false,
                items:        [itemData]
            })
        });

        if (!response.ok) {
            let msg = 'Export failed';
            try { const err = await response.json(); msg = err.message || msg; } catch (_) {}
            throw new Error(msg);
        }

        const blob = await response.blob();
        const dlUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = dlUrl;
        a.download = currentFile.replace(/\.csv$/i, '') + '_report.xlsx';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(dlUrl);

        if (calibrationWarnings.length) {
            Swal.fire({
                icon: 'warning',
                title: 'Excel report downloaded with warnings',
                html: 'Some calibration curves were not available:<br>' +
                      calibrationWarnings.map(w => `• ${w}`).join('<br>')
            });
        } else {
            Swal.fire('Success', 'Excel report downloaded.', 'success');
        }

    } catch (e) {
        console.error(e);
        Swal.fire('Error', 'Excel export failed: ' + e.message, 'error');
    } finally {
        window.hideSpinner();
    }
}

function loadReportSubjectsForPicker() {
    $.get('/get_report_subjects', function(response) {
        const sel = document.getElementById('report-subject-select');
        if (!sel) return;
        const prev = sel.value;
        sel.innerHTML = '<option value="">— select subject —</option>';
        if (response.status === 'success') {
            response.subjects.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s;
                opt.textContent = s;
                sel.appendChild(opt);
            });
        }
        if (prev) sel.value = prev;
    }).fail(() => console.error('Failed to load report subjects for picker'));
}

function onReportSaveModeChange() {
    const mode = document.querySelector('input[name="report-save-mode"]:checked')?.value || 'existing';
    const existingRow = document.getElementById('report-existing-row');
    const newRow = document.getElementById('report-new-row');
    if (existingRow) existingRow.style.display = mode === 'existing' ? 'flex' : 'none';
    if (newRow) newRow.style.display = mode === 'new' ? 'flex' : 'none';
    if (mode === 'existing') loadReportSubjectsForPicker();
}

async function exportToReport() {
    const saveMode = document.querySelector('input[name="report-save-mode"]:checked')?.value || 'existing';
    const subject = saveMode === 'existing'
        ? (document.getElementById('report-subject-select')?.value || '').trim()
        : (document.getElementById('report-subject-name')?.value || '').trim();
    if (!subject) {
        Swal.fire(
            'Subject Required',
            saveMode === 'existing' ? 'Please select an existing subject.' : 'Please enter a name for the new subject.',
            'warning'
        );
        return;
    }

    const currentFile = AppState.currentFile;
    if (!currentFile) {
        Swal.fire('No selection', 'Please select a file to export first.', 'warning');
        return;
    }

    const measMode = AppState.currentMeasurementMode || "Unknown";
    const dir = AppState.currentDirectory;
    const fullPath = dir + (dir.endsWith(DELIMITER) ? '' : DELIMITER) + currentFile;

    const metadata = {
        filename: currentFile,
        mode: measMode,
        timestamp: new Date().toLocaleString()
    };

    try {
        window.showSpinner();
        const response = await fetch('/export_to_report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                subject: subject,
                file_path: fullPath,
                metadata: metadata
            })
        });

        const result = await response.json();
        if (result.status === 'success') {
            Swal.fire('Export Successful', result.message, 'success');
            if (saveMode === 'new') loadReportSubjectsForPicker();
        } else {
            throw new Error(result.message);
        }
    } catch (e) {
        Swal.fire('Export Failed', e.message, 'error');
    } finally {
        window.hideSpinner();
    }
}

// In report mode, selecting a folder triggers the console
function onReportFolderSelected(folderName) {
    document.getElementById('report-console-section').classList.remove('hidden');
    document.getElementById('report-subject-info').innerText = `Editing Subject: ${folderName}`;
    AppState.currentReportSubject = folderName;
    loadReportItems(folderName);
}

// Store item configurations independently
window.ReportItemConfig = {};

function updateReportWindowSize(filename, value) {
    const config = window.ReportItemConfig?.[filename];
    if (!config) return;

    let v = parseInt(value, 10);
    if (Number.isNaN(v) || v < 3) v = 4;
    config.windowSize = v;
}

function updateReportDerivedQuantity(filename, value) {
    const config = window.ReportItemConfig?.[filename];
    if (!config) return;
    config.derivedQuantity = value || 'maxrate';
}

async function loadReportItems(subject) {
    const container = document.getElementById('report-items-container');
    container.innerHTML = '<p>Loading items...</p>';
    window.ReportItemConfig = {}; // reset

    try {
        const [itemsRes, kinJsonRes, pointJsonRes] = await Promise.all([
            fetch(`/get_report_items?subject=${encodeURIComponent(subject)}`),
            fetch(`/get_calibration_json_list?mode=kinetics`),
            fetch(`/get_calibration_json_list?mode=point`)
        ]);
        const result = await itemsRes.json();
        const kinJson = await kinJsonRes.json();
        const pointJson = await pointJsonRes.json();

        if (result.status === 'success') {
            if (result.items.length === 0) {
                container.innerHTML = '<p style="color: #666;">No items found in this subject folder.</p>';
                return;
            }

            // Global calibration JSONs (stored under /json/<mode>)
            const kineticsJsonFiles = (kinJson.status === 'success' && Array.isArray(kinJson.items)) ? kinJson.items : [];
            const pointJsonFiles = (pointJson.status === 'success' && Array.isArray(pointJson.items)) ? pointJson.items : [];

            const dataFiles = result.items.filter(i => i.filename.toLowerCase().endsWith('.csv'));

            if (dataFiles.length === 0) {
                container.innerHTML = '<p style="color: #666;">No data (CSV) files found to preview.</p>';
                return;
            }

            container.innerHTML = ''; // clear loading message

            // Pre-fetch every item's data once. This lets us tell a point-mode
            // calibration file (Concentration/TimePoint/Value) apart from a
            // kinetics standard curve (per-metric columns) and populate the point
            // time-point picker. The response is passed to initItemPreview so it
            // does not fetch a second time.
            const itemResponses = await Promise.all(dataFiles.map(it =>
                $.get('/get_data', { file: it.path }).then(r => r).catch(() => null)));

            for (let _i = 0; _i < dataFiles.length; _i++) {
                const item = dataFiles[_i];
                const response = itemResponses[_i];
                const itemID = `report-item-${item.filename.replace(/[^a-z0-9]/gi, '_')}`;
                const isCalibrate = item.metadata.mode === 'calibrate';
                const isKinetics = item.metadata.mode === 'kinetics';
                const cols = (response && response.data && response.data[0]) ? Object.keys(response.data[0]) : [];
                // A calibrate file carrying Concentration/TimePoint/Value columns is
                // a point-mode standard curve; anything else is a kinetics curve.
                const isPointCal = isCalibrate && cols.includes('Value') && cols.includes('TimePoint');
                const calType = isPointCal ? 'point' : (isCalibrate ? 'kinetics' : null);
                const card = document.createElement('div');
                card.className = 'report-item-card';
                card.id = itemID;
                card.dataset.filename = item.filename;
                card.dataset.subject = subject;

                let contentHtml = '';
                if (isPointCal) {
                    // Point-mode calibration: one Value-vs-Concentration curve. Let
                    // the user pick the time point and which fit algorithms to plot.
                    const timePoints = [...new Set(response.data.map(r => r['TimePoint']).filter(v => v != null && v !== 'NONE'))]
                        .sort((a, b) => parseFloat(a) - parseFloat(b));
                    contentHtml = `
                        <div class="point-cal-block" style="border: 1px solid #ddd; padding: 8px; border-radius: 6px; background: #fff; margin-top: 10px;">
                            <div style="height: 140px; margin-bottom: 8px;">
                                <canvas id="preview-chart-${itemID}-point"></canvas>
                            </div>
                            <label style="font-size:0.85rem; font-weight:700;">Time points &amp; fit curves</label>
                            <div class="point-tp-list" data-filename="${item.filename}">
                                ${_fullPointTpEntryHtml(item.filename, timePoints)}
                            </div>
                            <button type="button" onclick="addPointTimePoint('${item.filename}')"
                                style="margin-top:4px; padding:3px 10px; border:1px solid #3498db; background:#eaf4fc; color:#2980b9; border-radius:5px; cursor:pointer; font-size:0.8rem;">+ Add time point</button>
                        </div>
                    `;
                } else if (isCalibrate) {
                    const metrics = [
                        { id: 'Slope', label: 'Slope' },
                        { id: 'Time To Sat', label: 'Time To Sat' },
                        { id: 'maxRate', label: 'Max Rate' },
                        { id: 'Sat', label: 'Sat' }
                    ];
                    const algos = [
                        { id: 'polynomial', label: 'Poly' },
                        { id: 'linear', label: 'Lin' },
                        { id: 'logarithmic', label: 'Log' },
                        { id: 'exponential', label: 'Exp' },
                        { id: 'Michaelis-Menten', label: 'MM' }
                    ];

                    contentHtml = `
                        <div class="calibration-metrics-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; width: 100%; margin-top: 10px;">
                            ${metrics.map(m => `
                                <div class="metric-console-block" style="border: 1px solid #ddd; padding: 8px; border-radius: 6px; background: #fff;">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                                        <label style="font-size: 0.85rem; font-weight: 700; cursor: pointer;">
                                            <input type="checkbox" class="metric-include-checkbox" checked data-filename="${item.filename}" data-metric="${m.id}" onchange="toggleMetricDisplayArea('${itemID}-${m.id}', this.checked)">
                                            ${m.label}
                                        </label>
                                    </div>
                                    <div id="${itemID}-${m.id}-display-area" style="opacity: 1;">
                                        <div style="height: 100px; margin-bottom: 5px;">
                                            <canvas id="preview-chart-${itemID}-${m.id}"></canvas>
                                        </div>
                                        <div id="${itemID}-${m.id}-algo-checkboxes" style="display: flex; flex-wrap: wrap; gap: 5px; font-size: 0.7rem;">
                                            ${algos.map(a => `
                                                <label class="algo-include-label" data-hint="${a.label}" style="cursor: pointer; background: #f0f0f0; padding: 2px 4px; border-radius: 3px;">
                                                    <input type="checkbox" class="algo-include-checkbox" data-filename="${item.filename}" data-metric="${m.id}" data-algo="${a.id}" ${a.id === 'linear' ? 'checked' : ''}>
                                                    ${a.label}
                                                </label>
                                            `).join('')}
                                        </div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    `;
                } else {
                    const applicableJsonFiles = isKinetics ? kineticsJsonFiles : pointJsonFiles;
                    contentHtml = `
                        <div class="report-preview-layout">
                            <div class="report-preview-chart-container" style="flex: 2;">
                                <canvas id="preview-chart-${itemID}"></canvas>
                            </div>
                            <div class="report-item-controls" id="controls-${itemID}" style="flex: 1; min-width: 200px;">
                                ${isKinetics ? `
                                <div class="control-group">
                                    <label>Window size (auto = 4)</label>
                                    <input
                                        type="number"
                                        min="3"
                                        value="4"
                                        style="width: 6em;"
                                        class="report-window-size-input"
                                        data-item="${item.filename}"
                                        onchange="updateReportWindowSize('${item.filename}', this.value)"
                                    >
                                </div>
                                ` : ''}
                                <div class="control-group">
                                    <label>Visible Traces</label>
                                    <div class="trace-selection-group" id="traces-${itemID}">
                                        <span style="color: #999;">Loading traces...</span>
                                    </div>
                                </div>
                                <div class="control-group">
                                    <label>Calibration Curve</label>
                                    <select class="cal-source-select" data-item="${item.filename}">
                                        <option value="">None (Raw Data)</option>
                                        ${applicableJsonFiles.map(j => `<option value="${j}">${j}</option>`).join('')}
                                    </select>
                                </div>
                                ${isKinetics ? `
                                <div class="control-group">
                                    <label>Derived concentration from</label>
                                    <select class="derived-quantity-select" data-item="${item.filename}" onchange="updateReportDerivedQuantity('${item.filename}', this.value)">
                                        <option value="maxrate" selected>maxRate</option>
                                        <option value="slope">Slope</option>
                                        <option value="sat">Saturation</option>
                                        <option value="time_to_sat">Time to Sat</option>
                                    </select>
                                </div>
                                ` : ''}
                                <div class="control-group">
                                    <label>Report Layout</label>
                                    <select class="layout-toggle-select">
                                        <option value="together">All in one plot</option>
                                        <option value="individual">Separate plots per trace</option>
                                    </select>
                                </div>
                                ${(isKinetics || item.metadata.mode === 'point') ? `
                                <div class="control-group">
                                    <label style="cursor: pointer;">
                                        <input type="checkbox" class="item-normalize-checkbox" data-item="${item.filename}">
                                        Normalize Data
                                    </label>
                                </div>
                                ` : ''}
                            </div>
                        </div>
                    `;
                }

                card.innerHTML = `
                    <div class="report-item-header" style="background: #f8fafc; border-bottom: 1px solid #e2e8f0; margin: -10px -10px 10px -10px; padding: 5px 10px; border-radius: 8px 8px 0 0; display: flex; align-items: center; gap: 8px;">
                        <button class="move-card-btn" onclick="moveCardUp(this)" data-hint="Move up" style="background: none; border: 1px solid #cbd5e1; cursor: pointer; color: #64748b; font-size: 0.75rem; padding: 1px 6px; border-radius: 4px; flex-shrink: 0;">▲</button>
                        <button class="move-card-btn" onclick="moveCardDown(this)" data-hint="Move down" style="background: none; border: 1px solid #cbd5e1; cursor: pointer; color: #64748b; font-size: 0.75rem; padding: 1px 6px; border-radius: 4px; flex-shrink: 0;">▼</button>
                        <label style="font-weight: 700; cursor: pointer; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            <input type="checkbox" class="report-console-item-checkbox" checked data-filename="${item.filename}" data-path="${item.path}" onchange="toggleItemCardOpacity('${itemID}', this.checked)">
                            ${item.filename}
                        </label>
                        <span class="item-mode-badge" style="font-size: 0.8rem; color: #6366f1; background: #eef2ff; padding: 2px 8px; border-radius: 10px; font-weight: bold; flex-shrink: 0;">${item.metadata.mode || 'Measurement'}</span>
                        <button class="delete-item-btn" data-card-id="${itemID}" data-filename="${item.filename}" data-hint="Remove from subject" onclick="deleteReportItem(this)" style="background: none; border: 1px solid #fca5a5; cursor: pointer; color: #ef4444; font-size: 0.75rem; padding: 2px 8px; border-radius: 4px; flex-shrink: 0;">✕ Remove</button>
                    </div>
                    ${contentHtml}
                `;
                container.appendChild(card);

                // Initialize preview for this item (reuse the pre-fetched data)
                initItemPreview(item, itemID, response, calType);

                const normCb = card.querySelector('.item-normalize-checkbox');
                if (normCb) {
                    normCb.addEventListener('change', () => refreshPreviewNormalization(item.filename));
                }
            }
        } else {
            container.innerHTML = `<p style="color: red;">Error: ${result.message}</p>`;
        }
    } catch (e) {
        container.innerHTML = `<p style="color: red;">Failed to load items: ${e.message}</p>`;
    }
}

function toggleItemCardOpacity(id, checked) {
    document.getElementById(id).style.opacity = checked ? '1' : '0.5';
}

function _darkScale(overrides = {}) {
    const isLight = document.body.classList.contains('light');
    return {
        ...overrides,
        grid: { ...(overrides.grid || {}), color: isLight ? '#d1d5db' : '#6b7280' },
        ticks: { ...(overrides.ticks || {}), color: isLight ? '#374151' : '#e5e7eb' },
        title: { ...(overrides.title || {}), color: isLight ? '#111827' : '#e5e7eb' }
    };
}

function updateReportChartsTheme() {
    const isLight = document.body.classList.contains('light');
    const gridColor  = isLight ? '#d1d5db' : '#6b7280';
    const tickColor  = isLight ? '#374151' : '#e5e7eb';
    const titleColor = isLight ? '#111827' : '#e5e7eb';

    Object.values(window.ReportItemConfig || {}).forEach(config => {
        const charts = [];
        if (config.chart)  charts.push(config.chart);
        if (config.charts) charts.push(...Object.values(config.charts));

        charts.forEach(chart => {
            Object.values(chart.options.scales || {}).forEach(scale => {
                if (scale.grid)  scale.grid.color  = gridColor;
                if (scale.ticks) scale.ticks.color = tickColor;
                if (scale.title) scale.title.color = titleColor;
            });
            chart.update('none');
        });
    });
}

async function initItemPreview(item, itemID, preloaded = null, calType = null) {
    try {
        const response = preloaded || await $.get('/get_data', { file: item.path });
        if (!response.data || response.data.length === 0) return;

        const isCalibrate = item.metadata.mode === 'calibrate';
        const isKinetics = item.metadata.mode === 'kinetics';
        const isPointCal = calType === 'point';
        const numSources = response.num_sources || 1;
        const config = {
            data: response.data,
            metadata: { ...response.metadata, ...item.metadata },
            num_sources: numSources,
            calType,
            visibleTraces: Array.from({ length: numSources }, (_, i) => i + 1),
            visibleMetrics: (isCalibrate && !isPointCal) ? ['Slope', 'Time To Sat', 'maxRate', 'Sat'] : [],
            calFile: null,
            layout: 'together',
            chart: null,
            windowSize: isKinetics ? 4 : null,
            derivedQuantity: isKinetics ? 'maxrate' : null
        };
        window.ReportItemConfig[item.filename] = config;

        if (isPointCal) {
            // Scatter of Value vs Concentration (all time points initially);
            // updatePointPreview() re-renders when the time point changes.
            const measLabel = (config.metadata && config.metadata['Measurement']) || 'Value';
            const ctx = document.getElementById(`preview-chart-${itemID}-point`).getContext('2d');
            config.pointChart = new Chart(ctx, {
                type: 'scatter',
                data: { datasets: [{
                    label: measLabel,
                    data: response.data
                        .filter(r => r['Concentration'] !== 'NONE' && r['Value'] !== 'NONE')
                        .map(r => ({ x: parseFloat(r['Concentration']), y: parseFloat(r['Value']) }))
                        .filter(p => !isNaN(p.x) && !isNaN(p.y)),
                    backgroundColor: '#6366f1'
                }]},
                options: {
                    responsive: true, maintainAspectRatio: false,
                    scales: { x: _darkScale({ type: 'linear', display: true }), y: _darkScale({ display: true }) },
                    plugins: { legend: { display: false } },
                    animation: false
                }
            });
        } else if (isCalibrate) {
            const metrics = ['Slope', 'Time To Sat', 'maxRate', 'Sat'];
            const xCol = config.metadata.XColumn || 'Concentration';
            config.charts = {};

            metrics.forEach(m => {
                const ctx = document.getElementById(`preview-chart-${itemID}-${m}`).getContext('2d');
                config.charts[m] = new Chart(ctx, {
                    type: 'scatter',
                    data: {
                        datasets: [{
                            label: m,
                            data: response.data.map(row => {
                                const xv = parseFloat(row[xCol]);
                                const yv = row[m] === "NONE" ? null : parseFloat(row[m]);
                                return { x: xv, y: yv };
                            }),
                            backgroundColor: '#6366f1'
                        }]
                    },
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        scales: {
                            x: _darkScale({ type: 'linear', display: true }),
                            y: _darkScale({ display: true })
                        },
                        plugins: { legend: { display: false } },
                        animation: false
                    }
                });
            });

        } else {
            // Render Traces Checkboxes (Standard Mode)
            const traceGroup = document.getElementById(`traces-${itemID}`);
            if (traceGroup) {
                traceGroup.innerHTML = '';
                for (let i = 1; i <= numSources; i++) {
                    const lbl = document.createElement('label');
                    lbl.style.display = 'flex';
                    lbl.style.alignItems = 'center';
                    lbl.style.gap = '4px';
                    lbl.style.cursor = 'pointer';
                    lbl.innerHTML = `<input type="checkbox" checked onchange="updateReportPreview('${item.filename}', ${i}, this.checked)"> S${i}`;
                    traceGroup.appendChild(lbl);
                }
            }

            const ctx = document.getElementById(`preview-chart-${itemID}`).getContext('2d');
            const datasets = [];
            const colors = [
                'rgb(75, 192, 192)',
                'rgb(255, 99, 132)',
                'rgba(190, 136, 9, 1)',
                'rgb(54, 162, 235)',
                'rgb(153, 102, 255)',
                'rgba(139, 144, 75, 1)',
                'rgba(228, 87, 246, 1)',
                'rgba(44, 136, 115, 1)',
                'rgba(255, 159, 64, 1)',
                'rgba(199, 199, 199, 1)',
                'rgba(83, 102, 255, 1)',
                'rgba(255, 102, 178, 1)',
                'rgba(60, 179, 113, 1)',
                'rgba(255, 140, 0, 1)',
                'rgba(100, 149, 237, 1)',
                'rgba(216, 191, 216, 1)'
            ];

            for (let i = 1; i <= numSources; i++) {
                datasets.push({
                    label: `Source ${i}`,
                    data: response.data.map(row => ({ x: row.Timestamp, y: row[`Value:${i}`] })),
                    borderColor: colors[(i - 1) % colors.length],
                    tension: 0.1,
                    pointRadius: 0
                });
            }

            config.chart = new Chart(ctx, {
                type: 'line',
                data: { datasets: datasets },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    scales: {
                        x: _darkScale({ type: 'linear', title: { display: true, text: 'Time (s)', font: { size: 10 } }, ticks: { font: { size: 8 } } }),
                        y: _darkScale({ title: { display: true, text: 'Value', font: { size: 10 } }, ticks: { font: { size: 8 } } })
                    },
                    plugins: { legend: { display: false } },
                    animation: false
                }
            });
        }
    } catch (e) {
        console.error("Preview failed for", item.filename, e);
    }
}

function updateMetricVisibility(filename, metric, visible) {
    const config = window.ReportItemConfig[filename];
    if (!config) return;

    if (visible) {
        if (!config.visibleMetrics.includes(metric)) config.visibleMetrics.push(metric);
    } else {
        config.visibleMetrics = config.visibleMetrics.filter(m => m !== metric);
    }
}

// Re-render a point-calibration preview scatter for the selected time point.
function updatePointPreview(filename) {
    const config = window.ReportItemConfig[filename];
    if (!config || !config.pointChart) return;
    const card = document.querySelector(`.report-item-card[data-filename="${CSS.escape(filename)}"]`);
    // Preview the union of points across every selected time-point entry; an
    // "All time points" selection (empty value) shows everything.
    const tps = card ? Array.from(card.querySelectorAll('.point-timepoint-select')).map(s => s.value) : [];
    const showAll = tps.length === 0 || tps.some(v => v === '');
    const tpSet = new Set(tps.filter(v => v !== '').map(v => String(parseFloat(v))));
    const pts = (config.data || [])
        .filter(r => showAll || tpSet.has(String(parseFloat(r['TimePoint']))))
        .filter(r => r['Concentration'] !== 'NONE' && r['Value'] !== 'NONE')
        .map(r => ({ x: parseFloat(r['Concentration']), y: parseFloat(r['Value']) }))
        .filter(p => !isNaN(p.x) && !isNaN(p.y));
    config.pointChart.data.datasets[0].data = pts;
    config.pointChart.update();
}

function updateMetricAlgo(filename, metric, algo) {
    const config = window.ReportItemConfig[filename];
    if (!config) return;
    config.metricAlgos[metric] = algo;
}

function refreshPreviewNormalization(filename) {
    const config = window.ReportItemConfig[filename];
    if (!config || !config.chart) return;

    const card = document.querySelector(`.report-item-card[data-filename="${filename}"]`);
    const shouldNormalize = card?.querySelector('.item-normalize-checkbox')?.checked || false;

    const allTraces = Array.from({ length: config.num_sources }, (_, i) => i + 1);
    const displayData = shouldNormalize ? _normalizeTraces(config.data, allTraces) : config.data;

    config.chart.data.datasets.forEach((dataset, idx) => {
        const traceIdx = idx + 1;
        dataset.data = displayData.map(row => ({ x: row.Timestamp, y: row[`Value:${traceIdx}`] }));
    });

    const yAxis = config.chart.options.scales.y;
    if (yAxis?.title) yAxis.title.text = shouldNormalize ? 'Value (normalized)' : 'Value';

    config.chart.update();
}

function updateReportPreview(filename, sourceIdx, visible) {
    const config = window.ReportItemConfig[filename];
    if (!config || !config.chart) return;

    if (visible) {
        if (!config.visibleTraces.includes(sourceIdx)) config.visibleTraces.push(sourceIdx);
    } else {
        config.visibleTraces = config.visibleTraces.filter(t => t !== sourceIdx);
    }

    // Update chart visibility
    config.chart.setDatasetVisibility(sourceIdx - 1, visible);
    config.chart.update();
}

async function saveReportItemOrder(subject) {
    const order = Array.from(
        document.querySelectorAll('#report-items-container .report-item-card[data-filename]')
    ).map(el => el.dataset.filename);
    if (!subject || order.length === 0) return;
    try {
        await fetch('/save_report_item_order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject, order })
        });
    } catch (_) { /* non-critical, ignore */ }
}

async function finalizeReport() {
    const subject = AppState.currentReportSubject;
    const selectedCheckboxes = Array.from(document.querySelectorAll('.report-console-item-checkbox:checked'));

    if (!subject || selectedCheckboxes.length === 0) {
        Swal.fire('No items selected', 'Please select at least one file to include in the report.', 'warning');
        return;
    }

    // Persist the current drag order before generating
    await saveReportItemOrder(subject);

    window.showSpinner();
    try {
        const includeWatermark = document.getElementById('console-watermark').checked;
        const includeLogo = document.getElementById('console-logo').checked;
        const reportTitle = document.getElementById('console-title').value || 'Analysis Report';

        let finalHtmlContent = '';
        // Per-item curves that could not be fitted (e.g. a time point with < 2 points).
        const calibrationWarnings = [];

        for (let _cbIdx = 0; _cbIdx < selectedCheckboxes.length; _cbIdx++) {
            const cb = selectedCheckboxes[_cbIdx];
            if (_cbIdx > 0) finalHtmlContent += `<hr style="margin: 30px 0; border: none; border-top: 1px dashed #ccc;"/>`;

            const filename = cb.getAttribute('data-filename');
            const config = window.ReportItemConfig[filename];
            if (!config) continue;

            const isCalibrate = config.metadata.mode === 'calibrate';
            const card = cb.closest('.report-item-card');

            if (isCalibrate && config.calType === 'point') {
                // Point-mode calibration item: one Value-vs-Concentration curve per
                // time-point entry × selected fit algorithm.
                const measLabel = (config.metadata && config.metadata['Measurement']) || 'Value';
                const tpEntries = Array.from(card.querySelectorAll('.point-tp-entry'));

                let itemChartsMarkup = '<div style="display: flex; flex-wrap: wrap; gap: 4%;">';
                const fits = [];
                for (const entry of tpEntries) {
                    const timePoint = entry.querySelector('.point-timepoint-select')?.value || '';
                    const tpLabel = timePoint ? `t=${timePoint}` : 'all pooled';
                    const includeAlgos = Array.from(entry.querySelectorAll('.point-algo-checkbox:checked')).map(c => c.dataset.algo);

                    const pts = (config.data || [])
                        .filter(r => (!timePoint || parseFloat(r['TimePoint']) === parseFloat(timePoint)))
                        .filter(r => r['Concentration'] !== 'NONE' && r['Value'] !== 'NONE')
                        .map(r => ({ x: parseFloat(r['Concentration']), y: parseFloat(r['Value']) }))
                        .filter(p => !isNaN(p.x) && !isNaN(p.y))
                        .sort((a, b) => a.x - b.x);
                    const xValues = pts.map(p => p.x);
                    const yValues = pts.map(p => p.y);

                    for (const algo of includeAlgos) {
                        if (xValues.length < 2) {
                            calibrationWarnings.push(`Point calibration @ ${tpLabel}: no ${algo} curve could be fitted — at least two concentration points are required (found ${xValues.length}).`);
                            continue;
                        }
                        const analysis = calculateCoefAndRSquared(yValues, xValues, algo);
                        if (!analysis || !analysis.coefficients) continue;
                        fits.push({ entity: `${measLabel} @ ${tpLabel}`, algo, coefficients: analysis.coefficients, rSquared: analysis.rSquared });
                        const regLine = buildCalibrationRegressionLine(xValues, analysis.coefficients, algo);
                        const img = await renderCalibrationChartImage({
                            xConc: xValues, yMetric: yValues, regLine, title: `${measLabel} @ ${tpLabel} - ${algo}`, yLabel: measLabel, algo,
                            xLabel: _concenAxisLabel(config.metadata)
                        });
                        if (img) itemChartsMarkup += `
                            <div style="width: 48%; margin-bottom: 20px; border: 1px solid #eee; padding: 10px; border-radius: 8px; background: #fff;">
                                <img src="${img}" style="width: 100%; height: auto;"/>
                            </div>`;
                    }
                }
                itemChartsMarkup += '</div>';

                finalHtmlContent += `
                    <div class="report-item-block" style="page-break-inside: auto; margin-bottom: 40px;">
                        <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px;">Calibration (point): ${filename}</h2>
                        ${fits.length ? itemChartsMarkup : '<p style="color:#888;">Not enough calibration points to fit a curve for the selected time point(s).</p>'}
                        ${fits.length ? _renderCoefTablesHtml('Time Point', fits) : ''}
                    </div>
                `;

            } else if (isCalibrate) {
                const xCol = config.metadata.XColumn || 'Concentration';
                const renderData = config.data;
                const includeMetrics = Array.from(card.querySelectorAll('.metric-include-checkbox:checked'));

                for (const mCheckbox of includeMetrics) {
                    const metric = mCheckbox.dataset.metric;
                    const includeAlgos = Array.from(card.querySelectorAll(`.algo-include-checkbox[data-metric="${metric}"]:checked`));

                    if (includeAlgos.length === 0) continue;

                    let itemChartsMarkup = '<div style="display: flex; flex-wrap: wrap; gap: 4%;">';
                    const fits = [];
                    const niceMetricName = metric.charAt(0).toUpperCase() + metric.slice(1).replace(/([A-Z])/g, ' $1');

                    for (const aCheckbox of includeAlgos) {
                        const algo = aCheckbox.dataset.algo;
                        // Align and filter data points together
                        const alignedData = renderData.map(row => ({
                            xv: parseFloat(row[xCol]),
                            yv: row[metric] === "NONE" ? null : parseFloat(row[metric])
                        })).filter(p => !isNaN(p.xv) && p.yv !== null && !isNaN(p.yv));

                        const xValues = alignedData.map(p => p.xv);
                        const yValues = alignedData.map(p => p.yv);

                        if (xValues.length < 2) continue;

                        const analysis = calculateCoefAndRSquared(yValues, xValues, algo);
                        if (!analysis || !analysis.coefficients) continue;

                        const fitLabel = `${niceMetricName} - ${algo}`;

                        // 1. Collect the fit (grouped into per-algorithm tables later)
                        const [ca, cb, cc] = analysis.coefficients || [0, 0, 0];
                        fits.push({ entity: niceMetricName, algo, coefficients: analysis.coefficients, rSquared: analysis.rSquared });

                        // 2. High-res chart
                        const tempCanvas = document.createElement('canvas');
                        tempCanvas.width = 1600;
                        tempCanvas.height = 800;
                        const tempCtx = tempCanvas.getContext('2d');

                        const plotXMin = Math.min(...xValues);
                        const plotXMax = Math.max(...xValues);
                        const range = plotXMax - plotXMin;
                        const pXMin = plotXMin - 0.1 * range;
                        const pXMax = plotXMax + 0.1 * range;
                        const step = (pXMax - pXMin) / 149;
                        const regressionLine = [];
                        for (let j = 0; j < 150; j++) {
                            const curX = pXMin + j * step;
                            let curY = 0;
                            if (algo === "linear") {
                                curY = ca !== 0 ? (curX - cb) / ca : 0;
                            } else if (algo === "polynomial") {
                                if (ca === 0) curY = cb !== 0 ? (curX - cc) / cb : 0;
                                else {
                                    const disc = cb * cb - 4 * ca * (cc - curX);
                                    curY = disc >= 0 ? (-cb + Math.sqrt(disc)) / (2 * ca) : 0;
                                }
                            } else if (algo === "logarithmic") {
                                curY = ca !== 0 ? Math.exp((curX - cc) / ca) - cb : 0;
                            } else if (algo === "exponential") {
                                curY = (ca !== 0 && curX > cc && cb !== 0) ? Math.log((curX - cc) / ca) / cb : 0;
                            } else if (algo === "Michaelis-Menten") {
                                curY = (ca * curX) / (cb + curX);
                            }
                            regressionLine.push({ x: curX, y: curY });
                        }

                        let chartImageData = null;
                        try {
                            await new Promise(resolve => {
                                const tc = new Chart(tempCtx, {
                                    type: 'scatter',
                                    data: {
                                        datasets: [
                                            {
                                                label: 'Standards',
                                                data: xValues.map((x, idx) => ({ x, y: yValues[idx] })).filter(p => p.y !== null),
                                                backgroundColor: '#3498db',
                                                pointRadius: 6
                                            },
                                            { label: `Fit (${algo})`, data: regressionLine, type: 'line', borderColor: '#e74c3c', borderWidth: 3, fill: false, pointRadius: 0, tension: 0.2 }
                                        ]
                                    },
                                    options: {
                                        responsive: false, animation: false,
                                        plugins: {
                                            title: { display: true, text: fitLabel, font: { size: 18 } },
                                            legend: { display: true, position: 'bottom' }
                                        },
                                        scales: {
                                            x: { title: { display: true, text: _concenAxisLabel(config.metadata) } },
                                            y: { title: { display: true, text: niceMetricName } }
                                        }
                                    }
                                });
                                setTimeout(() => {
                                    chartImageData = tempCanvas.toDataURL();
                                    tc.destroy();
                                    resolve();
                                }, 250);
                            });

                            if (chartImageData) {
                                itemChartsMarkup += `
                                    <div style="width: 48%; margin-bottom: 20px; border: 1px solid #eee; padding: 10px; border-radius: 8px; background: #fff;">
                                        <img src="${chartImageData}" style="width: 100%; height: auto;"/>
                                    </div>`;
                            }
                        } catch (chartErr) {
                            console.error(`Error generating chart for ${filename}/${metric}/${algo}:`, chartErr);
                            continue;
                        }
                    }
                    itemChartsMarkup += '</div>';

                    finalHtmlContent += `
                        <div class="report-item-block" style="page-break-inside: auto; margin-bottom: 40px;">
                            <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px;">Calibration: ${filename} - ${metric}</h2>
                            ${itemChartsMarkup}
                            ${_renderCoefTablesHtml('Metric', fits)}
                        </div>
                    `;
                }

            } else {
                // Standard Measurement Item (Existing Logic)
                const calFile = card.querySelector('.cal-source-select').value;
                const layout = card.querySelector('.layout-toggle-select').value;
                const renderData = config.data;
                const visibleTraces = config.visibleTraces;
                const isKinetics = config.metadata.mode === 'kinetics';
                const windowSize = isKinetics ? (config.windowSize || 4) : null;
                const unit = (config.metadata && config.metadata.Unit) ? config.metadata.Unit : 'NONE';
                const isPoint = config.metadata.mode === 'point';
                const derivedQuantity = isKinetics ? (config.derivedQuantity || 'maxrate') : null;
                const shouldNormalize = card.querySelector('.item-normalize-checkbox')?.checked || false;
                const displayData = (shouldNormalize && (isKinetics || isPoint))
                    ? _normalizeTraces(renderData, visibleTraces)
                    : renderData;
                const derivedHtml = (calFile && (isKinetics || isPoint))
                    ? await buildDerivedConcentrationForReport({
                        mode: isKinetics ? 'kinetics' : 'point',
                        calFile,
                        renderData,
                        visibleTraces,
                        unit,
                        windowSize,
                        derivedQuantity
                    })
                    : '';

                if (layout === 'together') {
                    const tempCanvas = document.createElement('canvas');
                    tempCanvas.width = 1600; tempCanvas.height = 800;
                    const tempCtx = tempCanvas.getContext('2d');
                    const colors = [
                        'rgb(75, 192, 192)',
                        'rgb(255, 99, 132)',
                        'rgba(190, 136, 9, 1)',
                        'rgb(54, 162, 235)',
                        'rgb(153, 102, 255)',
                        'rgba(139, 144, 75, 1)',
                        'rgba(228, 87, 246, 1)',
                        'rgba(44, 136, 115, 1)',
                        'rgba(255, 159, 64, 1)',
                        'rgba(199, 199, 199, 1)',
                        'rgba(83, 102, 255, 1)',
                        'rgba(255, 102, 178, 1)',
                        'rgba(60, 179, 113, 1)',
                        'rgba(255, 140, 0, 1)',
                        'rgba(100, 149, 237, 1)',
                        'rgba(216, 191, 216, 1)'
                    ];

                    const tempChart = new Chart(tempCtx, {
                        type: 'line',
                        data: {
                            datasets: visibleTraces.map(t => ({
                                label: `Source ${t}`,
                                data: displayData.map(row => ({ x: row.Timestamp, y: row[`Value:${t}`] })),
                                borderColor: colors[(t - 1) % colors.length],
                                tension: 0.1,
                                pointRadius: 0
                            }))
                        },
                        options: {
                            responsive: false, animation: false,
                            plugins: {
                                title: { display: true, text: `Source: ${filename}`, font: { size: 18 } },
                                legend: { display: true, position: 'bottom' }
                            },
                            scales: {
                                x: { title: { display: true, text: 'Time (s)' } },
                                y: { title: { display: true, text: shouldNormalize ? 'Value (normalized)' : 'Value' } }
                            }
                        }
                    });

                    const img = tempCanvas.toDataURL('image/png');
                    const analysisHtml = isKinetics
                        ? buildKineticsAnalysisForReport(displayData, visibleTraces, unit, windowSize)
                        : '';
                    finalHtmlContent += `
                        <div style="margin-bottom: 30px;">
                            <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px;">Measurement Item: ${filename}</h2>
                            <div style="page-break-inside: avoid; break-inside: avoid;">
                                <img src="${img}" style="width:100%; border:1px solid #eee;"/>
                                <p style="font-size:0.8rem; color:#666; margin-top:5px;">Mode: ${config.metadata.mode || 'N/A'} | Calibration: ${calFile || 'None'}</p>
                                ${calFile ? `<div class="report-cal-meta" style="background:#f0f7ff; padding:10px; border-left:4px solid #3498db; font-size:0.8rem;">[Applied Calibration: ${calFile}]</div>` : ''}
                            </div>
                            ${derivedHtml}
                            ${analysisHtml}
                        </div>
                    `;
                    tempChart.destroy();
                } else {
                    finalHtmlContent += `<h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px;">Measurement Item: ${filename}</h2>`;
                    for (const traceIdx of visibleTraces) {
                        const tempCanvas = document.createElement('canvas');
                        tempCanvas.width = 1600; tempCanvas.height = 700;
                        const tempCtx = tempCanvas.getContext('2d');

                        const tempChart = new Chart(tempCtx, {
                            type: 'line',
                            data: {
                                datasets: [{
                                    label: `Source ${traceIdx}`,
                                    data: displayData.map(row => ({ x: row.Timestamp, y: row[`Value:${traceIdx}`] })),
                                    borderColor: '#6366f1',
                                    tension: 0.1,
                                    pointRadius: 0
                                }]
                            },
                            options: {
                                responsive: false, animation: false,
                                plugins: { title: { display: true, text: `${filename} - Source ${traceIdx}`, font: { size: 16 } } }
                            }
                        });

                        const img = tempCanvas.toDataURL('image/png');
                        const analysisHtml = isKinetics
                            ? buildKineticsAnalysisForReport(displayData, [traceIdx], unit, windowSize)
                            : '';
                        finalHtmlContent += `
                            <div style="margin-bottom: 20px;">
                                <div style="page-break-inside: avoid; break-inside: avoid;">
                                    <img src="${img}" style="width:100%; border:1px solid #eee;"/>
                                </div>
                                ${derivedHtml}
                                ${analysisHtml}
                            </div>
                        `;
                        tempChart.destroy();
                    }
                }
            }
        }

        const reportTemplate = `
        <div class="report-header" style="position:relative; z-index:10; display:flex; justify-content:space-between; border-bottom:2px solid #3498db; padding-bottom:20px; margin-bottom:30px;">
            <div>
                <h1 style="margin: 0; font-size: 2rem; color: #3498db;">Easy<span style="color: #ff4444;">OKAPI</span> Report</h1>
                <h2 style="margin: 5px 0; font-size: 1.5rem; color:#333;">${reportTitle}</h2>
                <p style="margin: 5px 0; color: #666;">Subject: <strong>${subject}</strong></p>
                <p style="margin: 5px 0; color: #999; font-size:0.8rem;">Generated on: ${new Date().toLocaleString()}</p>
            </div>
            ${includeLogo ? `<img src="/static/cbb.png" style="height: 70px;" />` : ''}
        </div>
        <div class="report-body" style="position:relative; z-index:1;">
            ${finalHtmlContent}
        </div>
        ${includeWatermark ? `<img src="/static/cbb.png" class="report-watermark-bg" style="position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); opacity:0.04; width:70%; z-index:100; pointer-events:none;" />` : ''}
        <div class="report-footer" style="margin-top:50px; text-align:center; font-size:0.75rem; color:#999; border-top:1px solid #eee; padding-top:20px;">
            Generated by EasyOKAPI Analytical Suite v1.0
        </div>
        `;

        const printContainer = document.getElementById('print-report-container');
        console.log("Injecting Advanced Report content...", !!finalHtmlContent);
        printContainer.innerHTML = reportTemplate;

        printContainer.classList.remove('hidden');
        printContainer.classList.add('report-mode');

        if (calibrationWarnings.length) {
            await Swal.fire({
                icon: 'warning',
                title: 'Some calibration curves unavailable',
                html: calibrationWarnings.map(w => `• ${w}`).join('<br>') +
                      '<br><br>The report was generated with the available curves.'
            });
        }

        setTimeout(() => {
            console.log("Triggering window.print() for Advanced Report");
            window.print();
            printContainer.classList.add('hidden');
            printContainer.classList.remove('report-mode');
            window.hideSpinner();
        }, 1500);

    } catch (e) {
        window.hideSpinner();
        console.error(e);
        Swal.fire('Error', 'Failed to generate report: ' + e.message, 'error');
    }
}

const _ReportJsonCache = new Map();

async function fetchCalibrationJsonContent(mode, jsonName) {
    const cacheKey = `${mode}::${jsonName}`;
    if (_ReportJsonCache.has(cacheKey)) return _ReportJsonCache.get(cacheKey);

    const resp = await fetch(`/get_json_content?json_name=${encodeURIComponent(jsonName)}&mode=${encodeURIComponent(mode)}`);
    const payload = await resp.json();
    if (!payload || payload.status !== 'success') {
        throw new Error(payload?.message || `Failed to load calibration JSON: ${jsonName}`);
    }
    _ReportJsonCache.set(cacheKey, payload.json);
    return payload.json;
}

function computeFitForReport(value, fit_type, coef, quantityLabel = '') {
    // Copied behavior from calculate.js computeFit, but without relying on page DOM.
    if (!coef || coef[0] === 'NONE' || coef[0] === 'NaN') {
        throw new Error(`Fit_type: ${fit_type} cannot be used${quantityLabel ? ` to derive concentration from ${quantityLabel}` : ''}`);
    }
    if (typeof value !== 'number' || isNaN(value)) {
        throw new Error(`${quantityLabel || 'Quantity'} is not available`);
    }
    switch ((fit_type || '').toLowerCase()) {
        case "linear":
            return coef["a"] * value + coef["b"];
        case "polynomial":
            return coef["a"] * Math.pow(value, 2) + coef["b"] * value + coef["c"];
        case "logarithmic":
            if (value <= 0) throw new Error("Invalid input for logarithm: value must be > 0");
            return coef["a"] * Math.log(value + coef["b"]) + coef["c"];
        case "exponential":
            return coef["a"] * Math.exp(value * coef["b"]) + coef["c"];
        case "michaelis-menten":
            if (value >= coef["VMax"] || value < 0) throw new Error(`Invalid input for Michaelis-Menten: value must be < Vmax and >= 0`);
            return (coef["Km"] * value) / (coef["VMax"] - value);
        default:
            throw new Error("Unknown fit type: " + fit_type);
    }
}

function _timeUnitToSeconds(unit) {
    const u = String(unit || '').toLowerCase();
    if (u.startsWith('sec')) return 1;
    if (u.startsWith('min')) return 60;
    if (u.startsWith('hour')) return 3600;
    return 60; // default matches existing export behavior
}

function _kineticsQuantityValuePerExportUnit(analysis, derivedQuantity) {
    // Mirror static/script/data-handling.js calculateKineticValue conversions:
    // - maxrate, slope: per minute (value * 60), since analysis is per second
    // - sat: raw
    // - time_to_sat: minutes (value / 60), since analysis time is seconds
    const q = (derivedQuantity || 'maxrate').toLowerCase();
    if (!analysis) return null;
    if (q === 'maxrate') return (analysis.maxRate !== undefined) ? Number(analysis.maxRate) * 60 : null;
    if (q === 'slope') return (analysis.slope !== undefined) ? Number(analysis.slope) * 60 : null;
    if (q === 'sat') return (analysis.saturationValue !== undefined) ? Number(analysis.saturationValue) : null;
    if (q === 'time_to_sat') return (analysis.timeToSaturation !== undefined) ? Number(analysis.timeToSaturation) / 60 : null;
    return null;
}

async function buildDerivedConcentrationForReport({ mode, calFile, renderData, visibleTraces, unit, windowSize, derivedQuantity }) {
    try {
        const json = await fetchCalibrationJsonContent(mode, calFile);
        const fitType = json.fit_type;

        let rowsHtml = '';
        if (mode === 'kinetics') {
            const coefNode = json?.[derivedQuantity]?.fit_coef;
            if (!coefNode) {
                return `<div style="margin-top:12px; color:#b45309; font-size:0.85rem;">Derived concentration unavailable: JSON does not contain coefficients for <strong>${derivedQuantity}</strong>.</div>`;
            }
            for (const t of visibleTraces) {
                const { x, y } = _extractValidXYForTrace(renderData, t);
                const a = (x.length >= 4) ? calculateKineticsQuantities(x, y, (windowSize || 4)) : null;
                const qVal = _kineticsQuantityValuePerExportUnit(a, derivedQuantity);
                let con = '--';
                try {
                    con = Number(computeFitForReport(qVal, fitType, coefNode, derivedQuantity)).toFixed(4);
                } catch (e) {
                    con = `ERR: ${e.message}`;
                }
                rowsHtml += `<div style="margin-bottom:6px;">Concentration (Source ${t}): <strong style="color:#2980b9;">${con} ${_reportConcenUnit(json)}</strong></div>`;
            }
            return `
                <div class="report-derived-concentration" style="margin-top:12px; background:#f0f7ff; padding:12px; border-radius:8px; border:1px solid #d0e7ff;">
                    <h3 style="margin:0 0 8px 0; color:#2980b9;">Derived Concentration</h3>
                    <div style="font-size:0.85rem; color:#666; margin-bottom:8px;">From: <strong>${derivedQuantity}</strong> (per minute conversion applied where applicable)</div>
                    ${getReportFitFormula(fitType) ? `<div style="font-size:0.85rem; color:#666; margin-bottom:8px;">Calibration function: <strong>${getReportFitFormula(fitType)}</strong> (${fitType})<br><span style="font-size:0.78rem;">where ${getReportFitWhere(fitType)}</span></div>` : ''}
                    ${rowsHtml}
                </div>
            `;
        }

        // point mode
        const coef = json.fit_coef;
        const timePoint = Number(json.time);
        const timeUnit = json['time-unit'];
        const timeSec = timePoint * _timeUnitToSeconds(timeUnit);

        for (const t of visibleTraces) {
            const estValue = getEstimatedValue(renderData, timeSec, t);
            let con = '--';
            try {
                con = Number(computeFitForReport(Number(estValue), fitType, coef, 'Endpoint Value')).toFixed(4);
            } catch (e) {
                con = `ERR: ${e.message}`;
            }
            rowsHtml += `<div style="margin-bottom:6px;">Concentration (Source ${t}): <strong style="color:#2980b9;">${con} ${_reportConcenUnit(json)}</strong></div>`;
        }

        return `
            <div class="report-derived-concentration" style="margin-top:12px; background:#f0f7ff; padding:12px; border-radius:8px; border:1px solid #d0e7ff;">
                <h3 style="margin:0 0 8px 0; color:#2980b9;">Derived Concentration</h3>
                <div style="font-size:0.85rem; color:#666; margin-bottom:8px;">Endpoint: <strong>${json.time} ${timeUnit || 'minute'}</strong></div>
                ${getReportFitFormula(fitType) ? `<div style="font-size:0.85rem; color:#666; margin-bottom:8px;">Calibration function: <strong>${getReportFitFormula(fitType)}</strong> (${fitType})<br><span style="font-size:0.78rem;">where ${getReportFitWhere(fitType)}</span></div>` : ''}
                ${rowsHtml}
            </div>
        `;
    } catch (e) {
        return `<div style="margin-top:12px; color:#b45309; font-size:0.85rem;">Derived concentration unavailable: ${e.message}</div>`;
    }
}

function _unitDisplayForReport(unit) {
    if (!unit || unit === 'NONE') return '';
    return unit;
}

// The concentration unit to label a derived concentration in a report. Prefers the
// calibration curve's own unit (`json.concen_unit`); for the live report builder
// where the JSON object isn't in scope, falls back to the loaded file's ConcenUnit
// (CSV↔JSON matching guarantees the two agree), then ng/µL for legacy data.
function _reportConcenUnit(json) {
    if (json && json.concen_unit && String(json.concen_unit).trim()) return String(json.concen_unit).trim();
    if (typeof getMetaConcenUnit === 'function') return getMetaConcenUnit(AppState.metaData);
    return 'ng/µL';
}

function _extractValidXYForTrace(renderData, traceIdx) {
    const x = [];
    const y = [];
    const key = `Value:${traceIdx}`;

    for (const row of renderData) {
        const xv = Number(row.Timestamp);
        const rawY = row[key];
        if (!Number.isFinite(xv)) continue;
        if (rawY === null || rawY === undefined) continue;
        if (rawY === 'NONE' || rawY === 'OVFL') continue;
        const yv = Number(rawY);
        if (!Number.isFinite(yv)) continue;
        x.push(xv);
        y.push(yv);
    }
    return { x, y };
}

function _formatMaybeNum(v, digits = 5) {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(digits) : '--';
}

function _normalizeTraces(renderData, traceIndices) {
    const normalized = renderData.map(row => ({ ...row }));
    for (const t of traceIndices) {
        const key = `Value:${t}`;
        const validVals = renderData
            .map(row => row[key])
            .filter(v => v !== null && v !== undefined && v !== 'NONE' && v !== 'OVFL' && Number.isFinite(Number(v)))
            .map(Number);
        if (validVals.length === 0) continue;
        const min = Math.min(...validVals);
        normalized.forEach((row, i) => {
            const raw = renderData[i][key];
            if (raw !== null && raw !== undefined && raw !== 'NONE' && raw !== 'OVFL' && Number.isFinite(Number(raw))) {
                row[key] = Number(raw) - min;
            }
        });
    }
    return normalized;
}

function buildKineticsAnalysisForReport(renderData, traceIndices, unit, windowSize) {
    const unitText = _unitDisplayForReport(unit);
    const ws = (Number.isFinite(Number(windowSize)) && Number(windowSize) >= 3) ? Number(windowSize) : 4;

    let html = `
        <div class="report-analysis" style="margin-top: 12px; background:#fff; border:1px solid #eee; padding:12px; border-radius:8px;">
            <h3 style="margin: 0 0 10px 0; color:#34495e;">Measurement Trace Analysis (kinetics)</h3>
            <div style="font-size:0.8rem; color:#666; margin-bottom:10px;">Window size used: <strong>${ws}</strong></div>
    `;

    for (const t of traceIndices) {
        const { x, y } = _extractValidXYForTrace(renderData, t);
        if (x.length < 4) {
            html += `<div style="margin-bottom:10px; color:#b45309; font-size:0.85rem;">Source ${t}: not enough valid points for analysis.</div>`;
            continue;
        }

        const a = calculateKineticsQuantities(x, y, ws);
        const slope = _formatMaybeNum(a?.slope, 5);
        const maxRate = _formatMaybeNum(a?.maxRate, 5);
        const sat = _formatMaybeNum(a?.saturationValue, 5);
        const tSat = _formatMaybeNum(a?.timeToSaturation, 2);
        const linStart = _formatMaybeNum(a?.linearXMin, 2);
        const linEnd = _formatMaybeNum(a?.linearXMax, 2);
        const mrStart = _formatMaybeNum(a?.startMaxRate, 2);
        const mrEnd = _formatMaybeNum(a?.endMaxRate, 2);

        html += `
            <div style="margin-top:10px; border-top: 1px solid #eee; padding-top:10px;">
                <strong style="color: #2c3e50; display:block; margin-bottom:6px;">Source ${t}</strong>
                <table style="width:100%; border-collapse: collapse; font-size: 0.8rem; border:1px solid #eee;">
                    <tr style="background:#f8f9fa; border-bottom: 2px solid #3498db;">
                        <th style="padding:8px; border:1px solid #eee; text-align:left;">Metric</th>
                        <th style="padding:8px; border:1px solid #eee; text-align:left;">Value</th>
                        <th style="padding:8px; border:1px solid #eee; text-align:left;">Context</th>
                    </tr>
                    <tr>
                        <td style="padding:8px; border:1px solid #eee; font-weight:bold;">Slope</td>
                        <td style="padding:8px; border:1px solid #eee;">${slope}${unitText ? ` ${unitText}` : ''}/s</td>
                        <td style="padding:8px; border:1px solid #eee;">${linStart} to ${linEnd} s</td>
                    </tr>
                    <tr style="background:#fcfcfc;">
                        <td style="padding:8px; border:1px solid #eee; font-weight:bold;">Max Rate</td>
                        <td style="padding:8px; border:1px solid #eee;">${maxRate}${unitText ? ` ${unitText}` : ''}/s</td>
                        <td style="padding:8px; border:1px solid #eee;">${mrStart} to ${mrEnd} s</td>
                    </tr>
                    <tr>
                        <td style="padding:8px; border:1px solid #eee; font-weight:bold;">Saturation</td>
                        <td style="padding:8px; border:1px solid #eee;">${sat}${unitText ? ` ${unitText}` : ''}</td>
                        <td style="padding:8px; border:1px solid #eee;">at ${tSat} s</td>
                    </tr>
                </table>
            </div>
        `;
    }

    html += `</div>`;
    return html;
}


function clearReportSubject() {
    AppState.currentReportSubject = null;
    document.getElementById('report-console-section').classList.add('hidden');
    document.getElementById('report-items-container').innerHTML = '';
    // Also clear any stored configurations
    window.ReportItemConfig = {};
}

function clearReportItems() {
    Swal.fire({
        title: 'Are you sure?',
        text: "This will clear the current report subject and all your item configurations.",
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Yes, clear subject'
    }).then((result) => {
        if (result.isConfirmed) {
            clearReportSubject();
            Swal.fire('Cleared', 'Report subject has been deselected.', 'success');
        }
    });
}
function toggleMetricDisplayArea(areaID, visible) {
    const area = document.getElementById(`${areaID}-display-area`);
    if (area) {
        area.style.opacity = visible ? '1' : '0.3';
        area.style.pointerEvents = visible ? 'auto' : 'none';
    }
}

function toggleItemCardOpacity(itemID, checked) {
    const card = document.getElementById(itemID);
    if (card) {
        card.style.opacity = checked ? '1' : '0.5';
        card.style.filter = checked ? 'none' : 'grayscale(50%)';
    }
}

async function deleteReportItem(btn) {
    const card = btn.closest('.report-item-card');
    const cardId = btn.dataset.cardId;
    const filename = btn.dataset.filename;
    const subject = card.dataset.subject;

    const result = await Swal.fire({
        title: 'Remove item?',
        text: `Remove "${filename}" from this subject? The file will be deleted from disk.`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Remove',
        confirmButtonColor: '#ef4444'
    });
    if (!result.isConfirmed) return;

    try {
        window.showSpinner();
        const response = await fetch('/delete_report_item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject, filename })
        });
        const data = await response.json();
        if (data.status !== 'success') throw new Error(data.message);

        // Destroy preview charts to free memory before removing DOM node
        const config = window.ReportItemConfig[filename];
        if (config) {
            if (config.chart) config.chart.destroy();
            if (config.charts) Object.values(config.charts).forEach(c => c.destroy());
            delete window.ReportItemConfig[filename];
        }
        document.getElementById(cardId)?.remove();

        const remaining = document.querySelectorAll('#report-items-container .report-item-card').length;
        if (remaining === 0) {
            document.getElementById('report-items-container').innerHTML =
                '<p style="color: #666;">No items found in this subject folder.</p>';
        }
    } catch (e) {
        Swal.fire('Error', e.message, 'error');
    } finally {
        window.hideSpinner();
    }
}

function initSortableCards(container) {
    let dragging = null;

    container.addEventListener('dragstart', e => {
        const card = e.target.closest('.report-item-card');
        if (!card) return;
        dragging = card;
        e.dataTransfer.effectAllowed = 'move';
        // Defer opacity so the drag image captures the full card
        setTimeout(() => { card.style.opacity = '0.4'; }, 0);
    });

    container.addEventListener('dragend', () => {
        if (dragging) dragging.style.opacity = '';
        dragging = null;
    });

    container.addEventListener('dragover', e => {
        e.preventDefault();
        if (!dragging) return;
        const card = e.target.closest('.report-item-card');
        if (!card || card === dragging) return;
        const { top, height } = card.getBoundingClientRect();
        if (e.clientY < top + height / 2) {
            container.insertBefore(dragging, card);
        } else {
            container.insertBefore(dragging, card.nextSibling);
        }
    });
}

function moveCardUp(btn) {
    const card = btn.closest('.report-item-card');
    const prev = card.previousElementSibling;
    if (prev && prev.classList.contains('report-item-card')) {
        card.parentNode.insertBefore(card, prev);
    }
}

function moveCardDown(btn) {
    const card = btn.closest('.report-item-card');
    const next = card.nextElementSibling;
    if (next && next.classList.contains('report-item-card')) {
        card.parentNode.insertBefore(next, card);
    }
}

async function finalizeReportExcel() {
    const subject = AppState.currentReportSubject;
    const selectedCheckboxes = Array.from(document.querySelectorAll('.report-console-item-checkbox:checked'));

    if (!subject || selectedCheckboxes.length === 0) {
        Swal.fire('No items selected', 'Please select at least one file to include in the report.', 'warning');
        return;
    }

    await saveReportItemOrder(subject);

    window.showSpinner();
    try {
        const reportTitle = document.getElementById('console-title').value || 'Analysis Report';
        const splitSheets = document.getElementById('console-split-sheets').checked;
        const axisLabels  = {
            x: document.getElementById('console-xlabel')?.value || '',
            y: document.getElementById('console-ylabel')?.value || ''
        };
        const COLORS = [
            'rgb(75, 192, 192)', 'rgb(255, 99, 132)', 'rgba(190, 136, 9, 1)',
            'rgb(54, 162, 235)', 'rgb(153, 102, 255)', 'rgba(139, 144, 75, 1)',
            'rgba(228, 87, 246, 1)', 'rgba(44, 136, 115, 1)', 'rgba(255, 159, 64, 1)'
        ];

        const items = [];

        for (const cb of selectedCheckboxes) {
            const filename = cb.getAttribute('data-filename');
            const config = window.ReportItemConfig[filename];
            if (!config) continue;

            const isCalibrate = config.metadata.mode === 'calibrate';
            const isKinetics  = config.metadata.mode === 'kinetics';
            const isPoint     = config.metadata.mode === 'point';
            const card = cb.closest('.report-item-card');

            const itemData = {
                filename,
                mode: config.metadata.mode || 'N/A',
                chart_images: [],
                chart_series: [],
                csv_columns: [],
                csv_rows: [],
                analysis_rows: [],
                coef_rows: [],
                coef_tables: [],
                derived_lines: []
            };

            if (isCalibrate && config.calType === 'point') {
                // Point-mode calibration: one Value-vs-Concentration fit per
                // time-point entry × chosen algorithm.
                const measLabel = (config.metadata && config.metadata['Measurement']) || 'Value';
                const tpEntries = Array.from(card.querySelectorAll('.point-tp-entry'));

                itemData.csv_columns = ['Concentration', 'Value', 'TimePoint'];
                itemData.csv_rows = (config.data || []).map(r => ({
                    Concentration: r['Concentration'], Value: r['Value'], TimePoint: r['TimePoint']
                }));

                const fits = [];
                for (const entry of tpEntries) {
                    const timePoint = entry.querySelector('.point-timepoint-select')?.value || '';
                    const tpLabel = timePoint ? `t=${timePoint}` : 'all pooled';
                    const includeAlgos = Array.from(entry.querySelectorAll('.point-algo-checkbox:checked')).map(c => c.dataset.algo);
                    const pts = (config.data || [])
                        .filter(r => !timePoint || parseFloat(r['TimePoint']) === parseFloat(timePoint))
                        .filter(r => r['Concentration'] !== 'NONE' && r['Value'] !== 'NONE')
                        .map(r => ({ x: parseFloat(r['Concentration']), y: parseFloat(r['Value']) }))
                        .filter(p => !isNaN(p.x) && !isNaN(p.y))
                        .sort((a, b) => a.x - b.x);
                    const xVals = pts.map(p => p.x);
                    const yVals = pts.map(p => p.y);

                    for (const algo of includeAlgos) {
                        if (xVals.length < 2) break;
                        const analysis = calculateCoefAndRSquared(yVals, xVals, algo);
                        if (!analysis || !analysis.coefficients) continue;
                        const fitLabel = `${measLabel} @ ${tpLabel} - ${algo}`;
                        fits.push({ entity: `${measLabel} @ ${tpLabel}`, algo, coefficients: analysis.coefficients, rSquared: analysis.rSquared });
                        const regLine = buildCalibrationRegressionLine(xVals, analysis.coefficients, algo);
                        itemData.chart_series.push(buildScatterSeries({
                            xConc: xVals, yMetric: yVals, regLine,
                            title: fitLabel, label: fitLabel, algo,
                            xLabel: axisLabels.x || _concenAxisLabel(config.metadata), yLabel: axisLabels.y || measLabel
                        }));
                    }
                }
                itemData.coef_tables = _buildCoefTables('Time Point', fits);

            } else if (isCalibrate) {
                const xCol = config.metadata.XColumn || 'Concentration';
                const renderData = config.data;
                const calMetrics = ['Slope', 'Time To Sat', 'maxRate', 'Sat'];

                itemData.csv_columns = [xCol, ...calMetrics];
                itemData.csv_rows = renderData.map(row => {
                    const r = {};
                    itemData.csv_columns.forEach(col => { r[col] = row[col]; });
                    return r;
                });

                const includeMetrics = Array.from(card.querySelectorAll('.metric-include-checkbox:checked'));
                const fits = [];
                for (const mCb of includeMetrics) {
                    const metric = mCb.dataset.metric;
                    const algoCbs = Array.from(card.querySelectorAll(`.algo-include-checkbox[data-metric="${metric}"]:checked`));
                    if (algoCbs.length === 0) continue;

                    for (const aCb of algoCbs) {
                        const algo = aCb.dataset.algo;
                        const aligned = renderData.map(row => ({
                            xv: parseFloat(row[xCol]),
                            yv: row[metric] === 'NONE' ? null : parseFloat(row[metric])
                        })).filter(p => !isNaN(p.xv) && p.yv !== null && !isNaN(p.yv));

                        const xVals = aligned.map(p => p.xv);
                        const yVals = aligned.map(p => p.yv);
                        if (xVals.length < 2) continue;

                        const analysis = calculateCoefAndRSquared(yVals, xVals, algo);
                        if (!analysis || !analysis.coefficients) continue;

                        const [ca, cb2, cc] = analysis.coefficients;
                        const niceMetric = metric.charAt(0).toUpperCase() + metric.slice(1).replace(/([A-Z])/g, ' $1');
                        const fitLabel = `${niceMetric} - ${algo}`;

                        fits.push({ entity: niceMetric, algo, coefficients: analysis.coefficients, rSquared: analysis.rSquared });

                        const pXMin = Math.min(...xVals) - 0.1 * (Math.max(...xVals) - Math.min(...xVals));
                        const pXMax = Math.max(...xVals) + 0.1 * (Math.max(...xVals) - Math.min(...xVals));
                        const step  = (pXMax - pXMin) / 149;
                        const regLine = [];
                        for (let j = 0; j < 150; j++) {
                            const curX = pXMin + j * step;
                            let curY = 0;
                            if (algo === 'linear')            curY = ca !== 0 ? (curX - cb2) / ca : 0;
                            else if (algo === 'polynomial') {
                                if (ca === 0) curY = cb2 !== 0 ? (curX - cc) / cb2 : 0;
                                else { const d = cb2 * cb2 - 4 * ca * (cc - curX); curY = d >= 0 ? (-cb2 + Math.sqrt(d)) / (2 * ca) : 0; }
                            } else if (algo === 'logarithmic') curY = ca !== 0 ? Math.exp((curX - cc) / ca) - cb2 : 0;
                            else if (algo === 'exponential')   curY = (ca !== 0 && curX > cc && cb2 !== 0) ? Math.log((curX - cc) / ca) / cb2 : 0;
                            else if (algo === 'Michaelis-Menten') curY = (ca * curX) / (cb2 + curX);
                            regLine.push({ x: curX, y: curY });
                        }

                        itemData.chart_series.push(buildScatterSeries({
                            xConc: xVals, yMetric: yVals, regLine,
                            title: fitLabel, label: fitLabel, algo,
                            xLabel: axisLabels.x || _concenAxisLabel(config.metadata), yLabel: axisLabels.y || niceMetric
                        }));
                    }
                }
                itemData.coef_tables = _buildCoefTables('Metric', fits);

            } else {
                const calFile        = card.querySelector('.cal-source-select').value;
                const layout         = card.querySelector('.layout-toggle-select').value;
                const renderData     = config.data;
                const visibleTraces  = config.visibleTraces;
                const windowSize     = isKinetics ? (config.windowSize || 4) : null;
                const unit           = (config.metadata && config.metadata.Unit) ? config.metadata.Unit : 'NONE';
                const derivedQty     = isKinetics ? (config.derivedQuantity || 'maxrate') : null;
                const shouldNormalize = card.querySelector('.item-normalize-checkbox')?.checked || false;
                const displayData    = (shouldNormalize && (isKinetics || isPoint))
                    ? _normalizeTraces(renderData, visibleTraces)
                    : renderData;

                // CSV data
                const csvCols = ['Timestamp', ...visibleTraces.map(t => `Value:${t}`)];
                itemData.csv_columns = csvCols;
                itemData.csv_rows = displayData.map(row => {
                    const r = {};
                    csvCols.forEach(col => { r[col] = row[col]; });
                    return r;
                });

                // Kinetics analysis rows (structured, not HTML)
                if (isKinetics) {
                    for (const t of visibleTraces) {
                        const { x, y } = _extractValidXYForTrace(displayData, t);
                        if (x.length < 4) continue;
                        const a = calculateKineticsQuantities(x, y, windowSize || 4);
                        const ut = _unitDisplayForReport(unit);
                        itemData.analysis_rows.push({
                            'Source':        `Source ${t}`,
                            'Slope':         `${_formatMaybeNum(a?.slope, 5)}${ut ? ' ' + ut : ''}/s`,
                            'Slope Range':   `${_formatMaybeNum(a?.linearXMin, 2)} – ${_formatMaybeNum(a?.linearXMax, 2)} s`,
                            'Max Rate':      `${_formatMaybeNum(a?.maxRate, 5)}${ut ? ' ' + ut : ''}/s`,
                            'Max Rate Range':`${_formatMaybeNum(a?.startMaxRate, 2)} – ${_formatMaybeNum(a?.endMaxRate, 2)} s`,
                            'Saturation':    `${_formatMaybeNum(a?.saturationValue, 5)}${ut ? ' ' + ut : ''}`,
                            'Time to Sat':   `${_formatMaybeNum(a?.timeToSaturation, 2)} s`
                        });
                    }
                }

                // Derived concentration lines
                if (calFile && (isKinetics || isPoint)) {
                    try {
                        const json = await fetchCalibrationJsonContent(isKinetics ? 'kinetics' : 'point', calFile);
                        const fitType = json.fit_type;
                        if (isKinetics) {
                            const coefNode = json?.[derivedQty]?.fit_coef;
                            for (const t of visibleTraces) {
                                const { x, y } = _extractValidXYForTrace(renderData, t);
                                const a = (x.length >= 4) ? calculateKineticsQuantities(x, y, windowSize || 4) : null;
                                const qVal = _kineticsQuantityValuePerExportUnit(a, derivedQty);
                                let con = '--';
                                try { con = Number(computeFitForReport(qVal, fitType, coefNode, derivedQty)).toFixed(4); } catch (_) {}
                                itemData.derived_lines.push(`Source ${t}: ${con} ${_reportConcenUnit(json)} (via ${derivedQty})`);
                            }
                        } else {
                            const coef = json.fit_coef;
                            const timeSec = Number(json.time) * _timeUnitToSeconds(json['time-unit']);
                            for (const t of visibleTraces) {
                                const estValue = getEstimatedValue(renderData, timeSec, t);
                                let con = '--';
                                try { con = Number(computeFitForReport(Number(estValue), fitType, coef, 'Endpoint Value')).toFixed(4); } catch (_) {}
                                itemData.derived_lines.push(`Source ${t}: ${con} ${_reportConcenUnit(json)}`);
                            }
                        }
                        // Lead with the calibration function used to derive the values.
                        if (itemData.derived_lines.length && getReportFitFormula(fitType)) {
                            itemData.derived_lines.unshift(`Calibration function — ${getReportFitFunctionLabel(fitType)}`);
                        }
                    } catch (_) {}
                }

                // Chart image(s)
                if (layout === 'together') {
                    const cv = document.createElement('canvas');
                    cv.width = 1600; cv.height = 800;
                    const tc = new Chart(cv.getContext('2d'), {
                        type: 'line',
                        data: {
                            datasets: visibleTraces.map(t => ({
                                label: `Source ${t}`,
                                data: displayData.map(row => ({ x: row.Timestamp, y: row[`Value:${t}`] })),
                                borderColor: COLORS[(t - 1) % COLORS.length], tension: 0.1, pointRadius: 0
                            }))
                        },
                        options: {
                            responsive: false, animation: false,
                            plugins: { title: { display: true, text: filename, font: { size: 18 } }, legend: { display: true, position: 'bottom' } },
                            scales: { x: { title: { display: true, text: 'Time (s)' } }, y: { title: { display: true, text: shouldNormalize ? 'Value (normalized)' : 'Value' } } }
                        }
                    });
                    await new Promise(r => setTimeout(r, 250));
                    itemData.chart_images.push({ label: filename, b64: cv.toDataURL('image/png') });
                    tc.destroy();
                } else {
                    for (const t of visibleTraces) {
                        const cv = document.createElement('canvas');
                        cv.width = 1600; cv.height = 800;
                        const tc = new Chart(cv.getContext('2d'), {
                            type: 'line',
                            data: { datasets: [{ label: `Source ${t}`, data: displayData.map(row => ({ x: row.Timestamp, y: row[`Value:${t}`] })), borderColor: '#6366f1', tension: 0.1, pointRadius: 0 }] },
                            options: { responsive: false, animation: false, plugins: { title: { display: true, text: `${filename} – Source ${t}`, font: { size: 16 } } } }
                        });
                        await new Promise(r => setTimeout(r, 250));
                        itemData.chart_images.push({ label: `Source ${t}`, b64: cv.toDataURL('image/png') });
                        tc.destroy();
                    }
                }
            }

            items.push(itemData);
        }

        const response = await fetch('/export_report_excel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: reportTitle, subject, split_sheets: splitSheets, items })
        });

        if (!response.ok) {
            let msg = 'Export failed';
            try { const err = await response.json(); msg = err.message || msg; } catch (_) {}
            throw new Error(msg);
        }

        const blob = await response.blob();
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        a.download = `${subject.replace(/[^\w\-]/g, '_') || 'report'}_report.xlsx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        Swal.fire('Success', 'Excel file downloaded.', 'success');

    } catch (e) {
        console.error(e);
        Swal.fire('Error', 'Failed to export as Excel: ' + e.message, 'error');
    } finally {
        window.hideSpinner();
    }
}
