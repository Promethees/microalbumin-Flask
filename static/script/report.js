async function generateReport() {
    const isCalibrate = AppState.currentMeasurementMode === 'calibrate';

    // 1. Ask for a title, algorithm (calibrate only), and export format
    const { value: formValues } = await Swal.fire({
        title: 'Report Details',
        html: `
            <div style="text-align: left;">
                <label style="display:block; margin-bottom:5px;">Report Title</label>
                <input id="swal-input1" class="swal2-input" value="Colorimetric Analysis Report" style="width: 80%; margin: 0 0 15px 0;">
                ${isCalibrate ? `
                <label style="display:block; margin-bottom:5px;">Fit Curve for Report</label>
                <select id="swal-input2" class="swal2-input" style="width: 80%; margin: 0 0 15px 0;">
                    <option value="polynomial">polynomial</option>
                    <option value="linear" selected>linear</option>
                    <option value="logarithmic">logarithmic</option>
                    <option value="exponential">exponential</option>
                    <option value="Michaelis-Menten">Michaelis-Menten</option>
                </select>` : ''}
                <label style="display:block; margin-bottom:5px;">Export Format</label>
                <div style="display:flex; gap:20px;">
                    <label style="cursor:pointer;"><input type="radio" name="swal-fmt" value="pdf" checked> PDF (print)</label>
                    <label style="cursor:pointer;"><input type="radio" name="swal-fmt" value="excel"> Excel (.xlsx)</label>
                </div>
            </div>
        `,
        focusConfirm: false,
        showCancelButton: true,
        preConfirm: () => {
            const title  = document.getElementById('swal-input1').value;
            const algoEl = document.getElementById('swal-input2');
            const fmt    = document.querySelector('input[name="swal-fmt"]:checked')?.value || 'pdf';
            return isCalibrate ? [title, algoEl ? algoEl.value : 'linear', fmt] : [title, null, fmt];
        }
    });

    if (!formValues) return;
    const [reportTitle, promptedAlgo, reportFormat] = formValues;

    if (reportFormat === 'excel') {
        await generateReportExcelFromCurrent(reportTitle, promptedAlgo || 'linear');
        return;
    }

    // 2. Gather data
    const selectedFile = document.getElementById('selected-file-display') ? document.getElementById('selected-file-display').innerText.replace('Selected File: ', '') : 'No file selected';
    const timestamp = new Date().toLocaleString();
    const measMode = AppState.currentMeasurementMode || "Unknown";
    const splitMode = AppState.multiSource ? `Yes (${AppState.numSources} sources)` : "No";
    const calCurve = AppState.currentMeasurementMode === 'calibrate'
        ? promptedAlgo
        : (AppState.currentJSON || "None selected");

    // 2.1 Gather Analytical Content (Specialized for Calibration or Standard)
    let analyticalContent = "";
    let chartImageSrc = "";
    let concentrationResults = "";
    let analysisSummaries = "";
    let derivedConcentrationHtml = "";

    if (isCalibrate && AppState.calibrationDataPoints && AppState.lastAnalyses) {
        // Specialized Calibration Quad-Report
        let coefficientRows = '';
        let chartsMarkup = '<div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 20px;">';

        for (let i = 0; i < AppState.calibrationDataPoints.length; i++) {
            const dataPoint = AppState.calibrationDataPoints[i];

            // Recalculate coefficients based on the user-selected algo for the report
            const analysis = calculateCoefAndRSquared(dataPoint.y, dataPoint.x, promptedAlgo);
            if (!analysis) continue;

            // 1. Build table row
            const [a, b, c] = analysis.coefficients || [0, 0, 0];
            coefficientRows += `
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding:10px; font-weight:bold;">${dataPoint.metric}</td>
                    <td style="padding:10px;">${a.toFixed(5)}</td>
                    <td style="padding:10px;">${b.toFixed(5)}</td>
                    <td style="padding:10px;">${analysis.coefficients.length > 2 ? c.toFixed(5) : '--'}</td>
                    <td style="padding:10px;">${analysis.rSquared.toFixed(4)}</td>
                </tr>`;

            // 2. Build high-res chart for this metric
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = 1600; tempCanvas.height = 800;
            const tempCtx = tempCanvas.getContext('2d');
            const regressAlgo = promptedAlgo;

            // Generate regression curve points
            const xMin = Math.min(...dataPoint.x);
            const xMax = Math.max(...dataPoint.x);
            const range = xMax - xMin;
            const plotXMin = xMin - 0.1 * range;
            const plotXMax = xMax + 0.1 * range;
            const step = (plotXMax - plotXMin) / 49;
            const regressionLine = [];
            for (let j = 0; j < 50; j++) {
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
                        if (discriminant < 0) continue;
                        curY = (-c1 + Math.sqrt(discriminant)) / (2 * c2);
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
                        x: { title: { display: true, text: 'Concentration', font: { size: 14, weight: 'bold' } } },
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
        }
        chartsMarkup += '</div>';

        analyticalContent = `
            <div class="report-analysis">
                <h3 style="color:#2c3e50; border-bottom: 1px solid #eee; padding-bottom:10px;">Metric-Specific Calibration Curves</h3>
                ${chartsMarkup}
            </div>
            <div class="report-results" style="margin-top:30px; margin-bottom:30px; border-left:4px solid #3498db; padding-left:20px;">
                <h3 style="margin-top:0; color:#2c3e50;">Calibration Fit Analysis</h3>
                <table style="width:100%; border-collapse: collapse; font-size: 0.9rem; text-align: left;">
                    <tr style="background:#f8fafc; border-bottom: 2px solid #3498db;">
                        <th style="padding:10px;">Metric</th>
                        <th style="padding:10px;">a</th>
                        <th style="padding:10px;">b</th>
                        <th style="padding:10px;">c</th>
                        <th style="padding:10px;">R²</th>
                    </tr>
                    ${coefficientRows}
                </table>
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
        if (AppState.currentJSON && (measMode === 'kinetics' || measMode === 'point')) {
            const visibleTraces = Array.from({ length: AppState.numSources }, (_, i) => i + 1);
            const windowSize = getValInt('window-size');
            const derivedQuantity = measMode === 'kinetics'
                ? (document.getElementById('regressed-quantity')?.value || 'maxrate')
                : null;
            const unit = getMetaUnit(AppState.metaData);
            derivedConcentrationHtml = await buildDerivedConcentrationForReport({
                mode: measMode,
                calFile: AppState.currentJSON,
                renderData: AppState.responseData,
                visibleTraces,
                unit,
                windowSize,
                derivedQuantity
            });
        } else {
            const derConSections = document.querySelectorAll('[id^="derived-concentration-section-source-"]');
            derConSections.forEach((sec, idx) => {
                if (!sec.classList.contains('hidden')) {
                    const val = sec.querySelector('.der-con-value')?.innerText || "--";
                    concentrationResults += `<div style="margin-bottom:8px; font-size: 1.1rem;">Concentration (Source ${idx + 1}): <strong style="color:#2980b9;">${val} ng/µL</strong></div>`;
                }
            });
        }

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

            ${derivedConcentrationHtml || (concentrationResults ? `
            <div class="report-results" style="background:#f0f7ff; padding:20px; border-radius:8px; border:1px solid #d0e7ff; margin-bottom:20px;">
                <h3 style="margin-top:0; color:#2980b9; border-bottom:1px solid #d0e7ff; padding-bottom:10px;">Analytical Results</h3>
                ${concentrationResults}
            </div>` : '')}

            ${analysisSummaries ? `
            <div class="report-analysis" style="background:#fff; border:1px solid #eee; padding:20px; border-radius:8px;">
                <h3 style="margin-top:0; color:#34495e;">Measurement Trace Analysis</h3>
                <div class="analysis-tables-container">
                    ${analysisSummaries}
                </div>
            </div>` : ''}
        `;
    }

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
                    <span>Generated: <strong>${timestamp}</strong></span>
                </div>
            </div>
            <img src="/static/cbb.png" style="height: 70px;" />
        </div>

        <img src="/static/cbb.png" class="report-watermark-bg" style="position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); opacity:0.04; width:70%; z-index:1; pointer-events:none;" />

        <div class="report-body" style="position:relative; z-index:10;">
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

    setTimeout(() => {
        console.log("Triggering window.print() for Quick Report");
        window.print();
        printContainer.classList.add('hidden');
        printContainer.classList.remove('report-mode');
    }, 1000);
}

async function exportToReport() {
    const subject = document.getElementById('report-subject-name').value.trim();
    if (!subject) {
        Swal.fire('Subject Required', 'Please enter a subject name for this report.', 'warning');
        return;
    }

    const currentFile = AppState.currentFile;
    if (!currentFile) {
        Swal.fire('No selection', 'Please select a file to export first.', 'warning');
        return;
    }

    const measMode = AppState.currentMeasurementMode || "Unknown";
    const dirEl = document.getElementById("directory");
    const fullPath = dirEl
        ? (dirEl.value + (dirEl.value.endsWith(DELIMITER) ? '' : DELIMITER) + currentFile)
        : currentFile;

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
            for (const item of dataFiles) {
                const itemID = `report-item-${item.filename.replace(/[^a-z0-9]/gi, '_')}`;
                const isCalibrate = item.metadata.mode === 'calibrate';
                const isKinetics = item.metadata.mode === 'kinetics';
                const card = document.createElement('div');
                card.className = 'report-item-card';
                card.id = itemID;
                card.dataset.filename = item.filename;
                card.dataset.subject = subject;

                let contentHtml = '';
                if (isCalibrate) {
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
                                                <label class="algo-include-label" title="${a.label}" style="cursor: pointer; background: #f0f0f0; padding: 2px 4px; border-radius: 3px;">
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
                        <button class="move-card-btn" onclick="moveCardUp(this)" title="Move up" style="background: none; border: 1px solid #cbd5e1; cursor: pointer; color: #64748b; font-size: 0.75rem; padding: 1px 6px; border-radius: 4px; flex-shrink: 0;">▲</button>
                        <button class="move-card-btn" onclick="moveCardDown(this)" title="Move down" style="background: none; border: 1px solid #cbd5e1; cursor: pointer; color: #64748b; font-size: 0.75rem; padding: 1px 6px; border-radius: 4px; flex-shrink: 0;">▼</button>
                        <label style="font-weight: 700; cursor: pointer; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            <input type="checkbox" class="report-console-item-checkbox" checked data-filename="${item.filename}" data-path="${item.path}" onchange="toggleItemCardOpacity('${itemID}', this.checked)">
                            ${item.filename}
                        </label>
                        <span class="item-mode-badge" style="font-size: 0.8rem; color: #6366f1; background: #eef2ff; padding: 2px 8px; border-radius: 10px; font-weight: bold; flex-shrink: 0;">${item.metadata.mode || 'Measurement'}</span>
                        <button class="delete-item-btn" data-card-id="${itemID}" data-filename="${item.filename}" title="Remove from subject" onclick="deleteReportItem(this)" style="background: none; border: 1px solid #fca5a5; cursor: pointer; color: #ef4444; font-size: 0.75rem; padding: 2px 8px; border-radius: 4px; flex-shrink: 0;">✕ Remove</button>
                    </div>
                    ${contentHtml}
                `;
                container.appendChild(card);

                // Initialize preview for this item
                initItemPreview(item, itemID);

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

async function initItemPreview(item, itemID) {
    try {
        const dataParams = { file: item.path };
        if (AppState.currentReportSubject) dataParams.subject = AppState.currentReportSubject;
        const response = await $.get('/get_data', dataParams);
        if (!response.data || response.data.length === 0) return;

        const isCalibrate = item.metadata.mode === 'calibrate';
        const isKinetics = item.metadata.mode === 'kinetics';
        const numSources = response.num_sources || 1;
        const config = {
            data: response.data,
            metadata: { ...response.metadata, ...item.metadata },
            num_sources: numSources,
            visibleTraces: Array.from({ length: numSources }, (_, i) => i + 1),
            visibleMetrics: isCalibrate ? ['Slope', 'Time To Sat', 'maxRate', 'Sat'] : [],
            calFile: null,
            layout: 'together',
            chart: null,
            windowSize: isKinetics ? 4 : null,
            derivedQuantity: isKinetics ? 'maxrate' : null
        };
        window.ReportItemConfig[item.filename] = config;

        if (isCalibrate) {
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

        for (let _cbIdx = 0; _cbIdx < selectedCheckboxes.length; _cbIdx++) {
            const cb = selectedCheckboxes[_cbIdx];
            if (_cbIdx > 0) finalHtmlContent += `<hr style="margin: 30px 0; border: none; border-top: 1px dashed #ccc;"/>`;

            const filename = cb.getAttribute('data-filename');
            const config = window.ReportItemConfig[filename];
            if (!config) continue;

            const isCalibrate = config.metadata.mode === 'calibrate';
            const card = cb.closest('.report-item-card');

            if (isCalibrate) {
                const xCol = config.metadata.XColumn || 'Concentration';
                const renderData = config.data;
                const includeMetrics = Array.from(card.querySelectorAll('.metric-include-checkbox:checked'));

                for (const mCheckbox of includeMetrics) {
                    const metric = mCheckbox.dataset.metric;
                    const includeAlgos = Array.from(card.querySelectorAll(`.algo-include-checkbox[data-metric="${metric}"]:checked`));

                    if (includeAlgos.length === 0) continue;

                    let itemChartsMarkup = '<div style="display: flex; flex-wrap: wrap; gap: 4%;">';
                    let coefficientRows = '';

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

                        const niceMetricName = metric.charAt(0).toUpperCase() + metric.slice(1).replace(/([A-Z])/g, ' $1');
                        const fitLabel = `${niceMetricName} - ${algo}`;

                        // 1. Build table row
                        const [ca, cb, cc] = analysis.coefficients || [0, 0, 0];
                        coefficientRows += `
                            <tr>
                                <td style="padding:10px; border:1px solid #eee;"><strong>${fitLabel}</strong></td>
                                <td style="padding:10px; border:1px solid #eee;">${ca.toFixed(5)}</td>
                                <td style="padding:10px; border:1px solid #eee;">${cb.toFixed(5)}</td>
                                <td style="padding:10px; border:1px solid #eee;">${analysis.coefficients.length > 2 ? cc.toFixed(5) : '--'}</td>
                                <td style="padding:10px; border:1px solid #eee;">${analysis.rSquared.toFixed(4)}</td>
                            </tr>`;

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
                        const step = (pXMax - pXMin) / 49;
                        const regressionLine = [];
                        for (let j = 0; j < 50; j++) {
                            const curX = pXMin + j * step;
                            let curY = 0;
                            if (algo === "linear") {
                                curY = ca !== 0 ? (curX - cb) / ca : 0;
                            } else if (algo === "polynomial") {
                                if (ca === 0) curY = cb !== 0 ? (curX - cc) / cb : 0;
                                else {
                                    const disc = cb * cb - 4 * ca * (cc - curX);
                                    if (disc < 0) continue;
                                    curY = (-cb + Math.sqrt(disc)) / (2 * ca);
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
                                            x: { title: { display: true, text: 'Concentration' } },
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
                            <table style="width:100%; border-collapse: collapse; margin-top:20px; font-size: 0.9rem;">
                                <thead>
                                    <tr style="background:#f8fafc; border-bottom: 2px solid #e2e8f0;">
                                        <th style="padding:10px; text-align:left;">Analysis</th>
                                        <th style="padding:10px; text-align:left;">a (or Vmax)</th>
                                        <th style="padding:10px; text-align:left;">b (or Km)</th>
                                        <th style="padding:10px; text-align:left;">c</th>
                                        <th style="padding:10px; text-align:left;">R²</th>
                                    </tr>
                                </thead>
                                <tbody>${coefficientRows}</tbody>
                            </table>
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
                rowsHtml += `<div style="margin-bottom:6px;">Concentration (Source ${t}): <strong style="color:#2980b9;">${con} ng/µL</strong></div>`;
            }
            return `
                <div class="report-derived-concentration" style="margin-top:12px; background:#f0f7ff; padding:12px; border-radius:8px; border:1px solid #d0e7ff;">
                    <h3 style="margin:0 0 8px 0; color:#2980b9;">Derived Concentration</h3>
                    <div style="font-size:0.85rem; color:#666; margin-bottom:8px;">From: <strong>${derivedQuantity}</strong> (per minute conversion applied where applicable)</div>
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
            rowsHtml += `<div style="margin-bottom:6px;">Concentration (Source ${t}): <strong style="color:#2980b9;">${con} ng/µL</strong></div>`;
        }

        return `
            <div class="report-derived-concentration" style="margin-top:12px; background:#f0f7ff; padding:12px; border-radius:8px; border:1px solid #d0e7ff;">
                <h3 style="margin:0 0 8px 0; color:#2980b9;">Derived Concentration</h3>
                <div style="font-size:0.85rem; color:#666; margin-bottom:8px;">Endpoint: <strong>${json.time} ${timeUnit || 'minute'}</strong></div>
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

function _normalizeTraces(renderData, traceIndices) {
    const normalized = renderData.map(row => ({ ...row }));
    for (const t of traceIndices) {
        const key = `Value:${t}`;
        const validVals = renderData
            .map(r => r[key])
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

async function generateReportExcelFromCurrent(reportTitle, promptedAlgo) {
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

        // In online mode, files are keyed by filename in the user session
        const dataResp   = await $.get('/get_data', { file: currentFile });
        const renderData = dataResp.data || [];
        const numSources = dataResp.num_sources || AppState.numSources || 1;
        const shouldNormalize = (isKinetics || isPoint) && (document.getElementById('normalize-mode')?.checked || false);

        const itemData = {
            filename:      currentFile,
            mode:          AppState.currentMeasurementMode || 'N/A',
            chart_images:  [],
            csv_columns:   [],
            csv_rows:      [],
            analysis_rows: [],
            coef_rows:     [],
            derived_lines: []
        };

        if (isCalibrate && AppState.calibrationDataPoints && AppState.calibrationDataPoints.length > 0) {
            const xCol       = dataResp.metadata?.XColumn || 'Concentration';
            const calMetrics = ['Slope', 'Time To Sat', 'maxRate', 'Sat'];

            itemData.csv_columns = [xCol, ...calMetrics];
            itemData.csv_rows    = renderData.map(row => {
                const r = {};
                itemData.csv_columns.forEach(col => { r[col] = row[col]; });
                return r;
            });

            for (const dataPoint of AppState.calibrationDataPoints) {
                const analysis = calculateCoefAndRSquared(dataPoint.y, dataPoint.x, promptedAlgo);
                if (!analysis || !analysis.coefficients) continue;

                const [ca, cb2, cc] = analysis.coefficients;
                const niceMetric = dataPoint.metric.charAt(0).toUpperCase() +
                    dataPoint.metric.slice(1).replace(/([A-Z])/g, ' $1');
                const fitLabel = `${niceMetric} — ${promptedAlgo}`;

                itemData.coef_rows.push({
                    'Metric':      dataPoint.metric,
                    'Algorithm':   promptedAlgo,
                    'a (or Vmax)': ca.toFixed(5),
                    'b (or Km)':   cb2.toFixed(5),
                    'c':           analysis.coefficients.length > 2 ? cc.toFixed(5) : '--',
                    'R²':          analysis.rSquared.toFixed(4)
                });

                const xMin  = Math.min(...dataPoint.x);
                const xMax  = Math.max(...dataPoint.x);
                const range = xMax - xMin;
                const pXMin = xMin - 0.1 * range;
                const pXMax = xMax + 0.1 * range;
                const step  = (pXMax - pXMin) / 49;
                const regLine = [];
                for (let j = 0; j < 50; j++) {
                    const curX = pXMin + j * step;
                    let curY = 0;
                    if (promptedAlgo === 'linear')           curY = ca !== 0 ? (curX - cb2) / ca : 0;
                    else if (promptedAlgo === 'polynomial') {
                        if (ca === 0) curY = cb2 !== 0 ? (curX - cc) / cb2 : 0;
                        else { const d = cb2 * cb2 - 4 * ca * (cc - curX); curY = d >= 0 ? (-cb2 + Math.sqrt(d)) / (2 * ca) : 0; }
                    } else if (promptedAlgo === 'logarithmic')    curY = ca !== 0 ? Math.exp((curX - cc) / ca) - cb2 : 0;
                    else if (promptedAlgo === 'exponential')      curY = (ca !== 0 && curX > cc && cb2 !== 0) ? Math.log((curX - cc) / ca) / cb2 : 0;
                    else if (promptedAlgo === 'Michaelis-Menten') curY = (ca * curX) / (cb2 + curX);
                    regLine.push({ x: curX, y: curY });
                }

                let imgData = null;
                await new Promise(resolve => {
                    const cv = document.createElement('canvas');
                    cv.width = 1600; cv.height = 800;
                    const tc = new Chart(cv.getContext('2d'), {
                        type: 'scatter',
                        data: {
                            datasets: [
                                { label: 'Standards', data: dataPoint.x.map((x, i) => ({ x, y: dataPoint.y[i] })), backgroundColor: '#3498db', pointRadius: 6 },
                                { label: `Fit (${promptedAlgo})`, data: regLine, type: 'line', borderColor: '#e74c3c', borderWidth: 3, fill: false, pointRadius: 0, tension: 0.2 }
                            ]
                        },
                        options: {
                            responsive: false, animation: false,
                            plugins: {
                                title: { display: true, text: fitLabel, font: { size: 18 } },
                                legend: { display: true, position: 'bottom' }
                            },
                            scales: {
                                x: { title: { display: true, text: 'Concentration', font: { size: 14 } } },
                                y: { title: { display: true, text: dataPoint.metric, font: { size: 14 } } }
                            }
                        }
                    });
                    setTimeout(() => { imgData = cv.toDataURL('image/png'); tc.destroy(); resolve(); }, 250);
                });
                if (imgData) itemData.chart_images.push({ label: fitLabel, b64: imgData });
            }

        } else {
            const visibleTraces = Array.from({ length: numSources }, (_, i) => i + 1);
            const displayData = shouldNormalize ? _normalizeTraces(renderData, visibleTraces) : renderData;
            const csvCols = ['Timestamp', ...visibleTraces.map(t => `Value:${t}`)];
            itemData.csv_columns = csvCols;
            itemData.csv_rows    = displayData.map(row => {
                const r = {};
                csvCols.forEach(col => { r[col] = row[col]; });
                return r;
            });

            if (AppState.lastAnalyses && AppState.lastAnalyses.length > 0) {
                const unitDisplay = getMetaUnit(AppState.metaData) !== 'NONE' ? getMetaUnit(AppState.metaData) : '';
                const timeUnit    = getTimeUnitValue() ? getTimeUnitValue().slice(0, -1) : 'min';
                AppState.lastAnalyses.forEach((rawAnalysis, idx) => {
                    const info = formatAnalysisInfo(rawAnalysis, `Source ${idx + 1}`);
                    if (!info) return;
                    const sat     = !isNaN(info.saturationValue)  ? info.saturationValue  : '--';
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

            document.querySelectorAll('[id^="derived-concentration-section-source-"]').forEach((sec, idx) => {
                if (!sec.classList.contains('hidden')) {
                    const val = sec.querySelector('.der-con-value')?.innerText || '--';
                    itemData.derived_lines.push(`Source ${idx + 1}: ${val} ng/µL`);
                }
            });

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

        const blob  = await response.blob();
        const dlUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = dlUrl;
        a.download = `${currentFile.replace(/\.[^.]+$/, '')}_report.xlsx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(dlUrl);

        Swal.fire('Success', 'Excel file downloaded.', 'success');

    } catch (e) {
        console.error(e);
        Swal.fire('Error', 'Failed to export as Excel: ' + e.message, 'error');
    } finally {
        window.hideSpinner();
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
                mode:          config.metadata.mode || 'N/A',
                chart_images:  [],
                csv_columns:   [],
                csv_rows:      [],
                analysis_rows: [],
                coef_rows:     [],
                derived_lines: []
            };

            if (isCalibrate) {
                const xCol       = config.metadata.XColumn || 'Concentration';
                const renderData = config.data;
                const calMetrics = ['Slope', 'Time To Sat', 'maxRate', 'Sat'];

                itemData.csv_columns = [xCol, ...calMetrics];
                itemData.csv_rows    = renderData.map(row => {
                    const r = {};
                    itemData.csv_columns.forEach(col => { r[col] = row[col]; });
                    return r;
                });

                const includeMetrics = Array.from(card.querySelectorAll('.metric-include-checkbox:checked'));
                for (const mCb of includeMetrics) {
                    const metric  = mCb.dataset.metric;
                    const algoCbs = Array.from(card.querySelectorAll(`.algo-include-checkbox[data-metric="${metric}"]:checked`));
                    if (algoCbs.length === 0) continue;

                    for (const aCb of algoCbs) {
                        const algo    = aCb.dataset.algo;
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
                        const fitLabel   = `${niceMetric} - ${algo}`;

                        itemData.coef_rows.push({
                            'Analysis':    fitLabel,
                            'a (or Vmax)': ca.toFixed(5),
                            'b (or Km)':   cb2.toFixed(5),
                            'c':           analysis.coefficients.length > 2 ? cc.toFixed(5) : '--',
                            'R²':          analysis.rSquared.toFixed(4)
                        });

                        const pXMin = Math.min(...xVals) - 0.1 * (Math.max(...xVals) - Math.min(...xVals));
                        const pXMax = Math.max(...xVals) + 0.1 * (Math.max(...xVals) - Math.min(...xVals));
                        const step  = (pXMax - pXMin) / 49;
                        const regLine = [];
                        for (let j = 0; j < 50; j++) {
                            const curX = pXMin + j * step;
                            let curY = 0;
                            if (algo === 'linear')           curY = ca !== 0 ? (curX - cb2) / ca : 0;
                            else if (algo === 'polynomial') {
                                if (ca === 0) curY = cb2 !== 0 ? (curX - cc) / cb2 : 0;
                                else { const d = cb2 * cb2 - 4 * ca * (cc - curX); curY = d >= 0 ? (-cb2 + Math.sqrt(d)) / (2 * ca) : 0; }
                            } else if (algo === 'logarithmic')    curY = ca !== 0 ? Math.exp((curX - cc) / ca) - cb2 : 0;
                            else if (algo === 'exponential')      curY = (ca !== 0 && curX > cc && cb2 !== 0) ? Math.log((curX - cc) / ca) / cb2 : 0;
                            else if (algo === 'Michaelis-Menten') curY = (ca * curX) / (cb2 + curX);
                            regLine.push({ x: curX, y: curY });
                        }

                        let imgData = null;
                        await new Promise(resolve => {
                            const calCv = document.createElement('canvas');
                            calCv.width = 1600; calCv.height = 800;
                            const tc = new Chart(calCv.getContext('2d'), {
                                type: 'scatter',
                                data: {
                                    datasets: [
                                        { label: 'Standards', data: xVals.map((x, i) => ({ x, y: yVals[i] })), backgroundColor: '#3498db', pointRadius: 6 },
                                        { label: `Fit (${algo})`, data: regLine, type: 'line', borderColor: '#e74c3c', borderWidth: 3, fill: false, pointRadius: 0, tension: 0.2 }
                                    ]
                                },
                                options: {
                                    responsive: false, animation: false,
                                    plugins: { title: { display: true, text: fitLabel, font: { size: 18 } }, legend: { display: true, position: 'bottom' } },
                                    scales: { x: { title: { display: true, text: 'Concentration' } }, y: { title: { display: true, text: niceMetric } } }
                                }
                            });
                            setTimeout(() => { imgData = calCv.toDataURL('image/png'); tc.destroy(); resolve(); }, 250);
                        });
                        if (imgData) itemData.chart_images.push({ label: fitLabel, b64: imgData });
                    }
                }

            } else {
                const calFile       = config.calFile;
                const layout        = config.layout || 'together';
                const renderData    = config.data;
                const visibleTraces = config.visibleTraces;
                const windowSize    = isKinetics ? (config.windowSize || 4) : null;
                const unit          = (config.metadata && config.metadata.Unit) ? config.metadata.Unit : 'NONE';
                const derivedQty    = isKinetics ? (config.derivedQuantity || 'maxrate') : null;
                const shouldNormalize = card.querySelector('.item-normalize-checkbox')?.checked || false;
                const displayData   = (shouldNormalize && (isKinetics || isPoint))
                    ? _normalizeTraces(renderData, visibleTraces)
                    : renderData;

                const csvCols = ['Timestamp', ...visibleTraces.map(t => `Value:${t}`)];
                itemData.csv_columns = csvCols;
                itemData.csv_rows    = displayData.map(row => {
                    const r = {};
                    csvCols.forEach(col => { r[col] = row[col]; });
                    return r;
                });

                if (isKinetics) {
                    for (const t of visibleTraces) {
                        const { x, y } = _extractValidXYForTrace(displayData, t);
                        if (x.length < 4) continue;
                        const a  = calculateKineticsQuantities(x, y, windowSize || 4);
                        const ut = _unitDisplayForReport(unit);
                        itemData.analysis_rows.push({
                            'Source':         `Source ${t}`,
                            'Slope':          `${_formatMaybeNum(a?.slope, 5)}${ut ? ' ' + ut : ''}/s`,
                            'Slope Range':    `${_formatMaybeNum(a?.linearXMin, 2)} – ${_formatMaybeNum(a?.linearXMax, 2)} s`,
                            'Max Rate':       `${_formatMaybeNum(a?.maxRate, 5)}${ut ? ' ' + ut : ''}/s`,
                            'Max Rate Range': `${_formatMaybeNum(a?.startMaxRate, 2)} – ${_formatMaybeNum(a?.endMaxRate, 2)} s`,
                            'Saturation':     `${_formatMaybeNum(a?.saturationValue, 5)}${ut ? ' ' + ut : ''}`,
                            'Time to Sat':    `${_formatMaybeNum(a?.timeToSaturation, 2)} s`
                        });
                    }
                }

                if (calFile && (isKinetics || isPoint)) {
                    try {
                        const json    = await fetchCalibrationJsonContent(isKinetics ? 'kinetics' : 'point', calFile);
                        const fitType = json.fit_type;
                        if (isKinetics) {
                            const coefNode = json?.[derivedQty]?.fit_coef;
                            for (const t of visibleTraces) {
                                const { x, y } = _extractValidXYForTrace(renderData, t);
                                const a = (x.length >= 4) ? calculateKineticsQuantities(x, y, windowSize || 4) : null;
                                const qVal = _kineticsQuantityValuePerExportUnit(a, derivedQty);
                                let con = '--';
                                try { con = Number(computeFitForReport(qVal, fitType, coefNode, derivedQty)).toFixed(4); } catch (_) {}
                                itemData.derived_lines.push(`Source ${t}: ${con} ng/µL (via ${derivedQty})`);
                            }
                        } else {
                            const coef    = json.fit_coef;
                            const timeSec = Number(json.time) * _timeUnitToSeconds(json['time-unit']);
                            for (const t of visibleTraces) {
                                const estValue = getEstimatedValue(renderData, timeSec, t);
                                let con = '--';
                                try { con = Number(computeFitForReport(Number(estValue), fitType, coef, 'Endpoint Value')).toFixed(4); } catch (_) {}
                                itemData.derived_lines.push(`Source ${t}: ${con} ng/µL`);
                            }
                        }
                    } catch (_) {}
                }

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
