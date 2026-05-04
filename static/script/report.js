async function generateReport() {
    // 1. Ask for a title and algorithm (if not already selected)
    const { value: formValues } = await Swal.fire({
        title: 'Report Details',
        html: `
            <div style="text-align: left;">
                <label style="display:block; margin-bottom:5px;">Report Title</label>
                <input id="swal-input1" class="swal2-input" value="Colorimetric Analysis Report" style="width: 80%; margin: 0 0 15px 0;">
                
                <label style="display:block; margin-bottom:5px;">Fit Curve for Report</label>
                <select id="swal-input2" class="swal2-input" style="width: 80%; margin: 0;">
                    <option value="polynomial">polynomial</option>
                    <option value="linear" selected>linear</option>
                    <option value="logarithmic">logarithmic</option>
                    <option value="exponential">exponential</option>
                    <option value="Michaelis-Menten">Michaelis-Menten</option>
                </select>
            </div>
        `,
        focusConfirm: false,
        showCancelButton: true,
        preConfirm: () => {
            return [
                document.getElementById('swal-input1').value,
                document.getElementById('swal-input2').value
            ]
        }
    });

    if (!formValues) return; // User cancelled
    const [reportTitle, promptedAlgo] = formValues;

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
    const isCalibrate = AppState.currentMeasurementMode === 'calibrate';

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
        const derConSections = document.querySelectorAll('[id^="derived-concentration-section-source-"]');
        derConSections.forEach((sec, idx) => {
            if (!sec.classList.contains('hidden')) {
                const val = sec.querySelector('.der-con-value')?.innerText || "--";
                concentrationResults += `<div style="margin-bottom:8px; font-size: 1.1rem;">Concentration (Source ${idx + 1}): <strong style="color:#2980b9;">${val} ng/µL</strong></div>`;
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

    const htmlContent = `
        <div class="report-header" style="position:relative; z-index:10; display:flex; justify-content:space-between; border-bottom:2px solid #3498db; padding-bottom:20px; margin-bottom:30px;">
            <div>
                <h1 style="margin: 0; font-size: 2rem; color: #3498db;">Easy<span style="color: #ff4444;">OKAPI</span> Report</h1>
                <h2 style="margin: 5px 0; font-size: 1.5rem; color:#333;">${reportTitle}</h2>
                <p style="margin: 5px 0; color: #666;">File: <strong>${selectedFile}</strong></p>
                <div style="margin-top:10px; font-size:0.9rem; display:grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                    <span>Mode: <strong>${measMode}</strong></span>
                    ${isCalibrate ? '' : `<span>Split Mode: <strong>${splitMode}</strong></span>`}
                    <span>Calibration Fit Type: <strong>${calCurve}</strong></span>
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
    const dir = document.getElementById("directory").value;
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

async function loadReportItems(subject) {
    const container = document.getElementById('report-items-container');
    container.innerHTML = '<p>Loading items...</p>';
    window.ReportItemConfig = {}; // reset

    try {
        const response = await fetch(`/get_report_items?subject=${encodeURIComponent(subject)}`);
        const result = await response.json();

        if (result.status === 'success') {
            if (result.items.length === 0) {
                container.innerHTML = '<p style="color: #666;">No items found in this subject folder.</p>';
                return;
            }

            // Separate JSONs for calibration mapping
            const jsonFiles = result.items.filter(i => i.filename.toLowerCase().endsWith('.json'));
            const dataFiles = result.items.filter(i => i.filename.toLowerCase().endsWith('.csv'));

            if (dataFiles.length === 0) {
                container.innerHTML = '<p style="color: #666;">No data (CSV) files found to preview.</p>';
                return;
            }

            container.innerHTML = ''; // clear loading message
            for (const item of dataFiles) {
                const itemID = `report-item-${item.filename.replace(/[^a-z0-9]/gi, '_')}`;
                const isCalibrate = item.metadata.mode === 'calibrate';
                const card = document.createElement('div');
                card.className = 'report-item-card';
                card.id = itemID;

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
                                        <div style="display: flex; flex-wrap: wrap; gap: 5px; font-size: 0.7rem;">
                                            ${algos.map(a => `
                                                <label title="${a.label}" style="cursor: pointer; background: #f0f0f0; padding: 2px 4px; border-radius: 3px;">
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
                    contentHtml = `
                        <div class="report-preview-layout">
                            <div class="report-preview-chart-container" style="flex: 2;">
                                <canvas id="preview-chart-${itemID}"></canvas>
                            </div>
                            <div class="report-item-controls" id="controls-${itemID}" style="flex: 1; min-width: 200px;">
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
                                        ${jsonFiles.map(j => `<option value="${j.filename}">${j.filename}</option>`).join('')}
                                    </select>
                                </div>
                                <div class="control-group">
                                    <label>Report Layout</label>
                                    <select class="layout-toggle-select">
                                        <option value="together">All in one plot</option>
                                        <option value="individual">Separate plots per trace</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    `;
                }

                card.innerHTML = `
                    <div class="report-item-header" style="background: #f8fafc; border-bottom: 1px solid #e2e8f0; margin: -10px -10px 10px -10px; padding: 5px 10px; border-radius: 8px 8px 0 0;">
                        <label style="font-weight: 700; cursor: pointer;">
                            <input type="checkbox" class="report-console-item-checkbox" checked data-filename="${item.filename}" data-path="${item.path}" onchange="toggleItemCardOpacity('${itemID}', this.checked)">
                            ${item.filename}
                        </label>
                        <span style="font-size: 0.8rem; color: #6366f1; background: #eef2ff; padding: 2px 8px; border-radius: 10px; font-weight: bold;">${item.metadata.mode || 'Measurement'}</span>
                    </div>
                    ${contentHtml}
                `;
                container.appendChild(card);

                // Initialize preview for this item
                initItemPreview(item, itemID);
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

async function initItemPreview(item, itemID) {
    try {
        const response = await $.get('/get_data', { file: item.path });
        if (!response.data || response.data.length === 0) return;

        const isCalibrate = item.metadata.mode === 'calibrate';
        const numSources = response.num_sources || 1;
        const config = {
            data: response.data,
            metadata: { ...response.metadata, ...item.metadata },
            num_sources: numSources,
            visibleTraces: Array.from({ length: numSources }, (_, i) => i + 1),
            visibleMetrics: isCalibrate ? ['Slope', 'Time To Sat', 'maxRate', 'Sat'] : [],
            calFile: null,
            layout: 'together',
            chart: null
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
                            x: { type: 'linear', display: true },
                            y: { display: true }
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
            const colors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

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
                        x: { type: 'linear', title: { display: true, text: 'Time (s)', font: { size: 10 } }, ticks: { font: { size: 8 } } },
                        y: { title: { display: true, text: 'Value', font: { size: 10 } }, ticks: { font: { size: 8 } } }
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

async function finalizeReport() {
    const subject = AppState.currentReportSubject;
    const selectedCheckboxes = Array.from(document.querySelectorAll('.report-console-item-checkbox:checked'));

    if (!subject || selectedCheckboxes.length === 0) {
        Swal.fire('No items selected', 'Please select at least one file to include in the report.', 'warning');
        return;
    }

    window.showSpinner();
    try {
        const includeWatermark = document.getElementById('console-watermark').checked;
        const includeLogo = document.getElementById('console-logo').checked;
        const reportTitle = document.getElementById('console-title').value || 'Analysis Report';

        let finalHtmlContent = '';

        for (const cb of selectedCheckboxes) {
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

                if (layout === 'together') {
                    const tempCanvas = document.createElement('canvas');
                    tempCanvas.width = 1600; tempCanvas.height = 800;
                    const tempCtx = tempCanvas.getContext('2d');
                    const colors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

                    const tempChart = new Chart(tempCtx, {
                        type: 'line',
                        data: {
                            datasets: visibleTraces.map(t => ({
                                label: `Source ${t}`,
                                data: renderData.map(row => ({ x: row.Timestamp, y: row[`Value:${t}`] })),
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
                                y: { title: { display: true, text: 'Value' } }
                            }
                        }
                    });

                    const img = tempCanvas.toDataURL('image/png');
                    finalHtmlContent += `
                        <div class="report-chart-block">
                            <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px;">Measurement Item: ${filename}</h2>
                            <img src="${img}" style="width:100%; border:1px solid #eee;"/>
                            <p style="font-size:0.8rem; color:#666; margin-top:5px;">Mode: ${config.metadata.mode || 'N/A'} | Calibration: ${calFile || 'None'}</p>
                            ${calFile ? `<div class="report-cal-meta" style="background:#f0f7ff; padding:10px; border-left:4px solid #3498db; font-size:0.8rem;">[Applied Calibration: ${calFile}]</div>` : ''}
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
                                    data: renderData.map(row => ({ x: row.Timestamp, y: row[`Value:${traceIdx}`] })),
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
                        finalHtmlContent += `
                            <div class="report-chart-block" style="margin-bottom: 20px;">
                                 <img src="${img}" style="width:100%; border:1px solid #eee;"/>
                            </div>
                        `;
                        tempChart.destroy();
                    }
                }
            }
            finalHtmlContent += `<hr style="margin: 30px 0; border: none; border-top: 1px dashed #ccc;"/>`;
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
            ${includeWatermark ? `<img src="/static/cbb.png" class="report-watermark-bg" style="position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); opacity:0.04; width:70%; z-index:1; pointer-events:none;" />` : ''}
            <div class="report-body" style="position:relative; z-index:10;">
                ${finalHtmlContent}
            </div>
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
