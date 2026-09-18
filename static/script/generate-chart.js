function initializeChartCanvas(canvasId) {
    if (AppState.chartInstances[canvasId]) {
        AppState.chartInstances[canvasId].destroy();
    }
    const $canvas = $(`#${canvasId}`).show();
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        $canvas.hide();
        return null;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) {
        $canvas.hide();
        return null;
    }
    return ctx;
}

function getCheckboxes(canvasId) {
    const canvasString = canvasId.split("-canvas")[0];
    return {
        maxrate: document.getElementById(`maxrate-${canvasString}`),
        slope: document.getElementById(`slope-${canvasString}`),
        saturation: document.getElementById(`sat-${canvasString}`),
        fullDisplay: document.getElementById(`full-display-${canvasString}`)
    };
}

function processData(allXColumn, allYColumnOrArray, timeUnit) {
    const isMultipleY = Array.isArray(allYColumnOrArray[0]);
    const allYColumns = isMultipleY ? allYColumnOrArray : [allYColumnOrArray];
    const conversionFactor = getTimeUnitMultiplier('seconds') / getTimeUnitMultiplier(timeUnit);

    const processedYColumns = [];
    const allYValues = [];
    let xColumn;

    allYColumns.forEach((yCol, i) => {
        const { x: px, y: py } = mapDuplicates(allXColumn, yCol, true);
        const { XColumn: xAfterAvg, YColumn: yAfterAvg, minY, maxY, stdY } = averageDuplicates(px, py);

        // Store y values along with their min/max/std for distribution bars and tooltips
        processedYColumns.push({
            avg: yAfterAvg,
            min: minY,
            max: maxY,
            std: stdY
        });

        // Include min and max in allYValues to ensure scales accommodate the bars
        allYValues.push(...yAfterAvg.filter(v => v !== null));
        allYValues.push(...minY.filter(v => v !== null));
        allYValues.push(...maxY.filter(v => v !== null));

        if (i === 0) {
            xColumn = xAfterAvg;
        }
    });

    return { xColumn, processedYColumns, allYValues, conversionFactor };
}

function toHex(color) {
    if (/^#[0-9a-f]{6}/i.test(color)) return color.slice(0, 7);
    if (/^#[0-9a-f]{6}$/i.test(color)) return color.toLowerCase();
    if (/^#[0-9a-f]{3}$/i.test(color)) {
        return '#' + color.slice(1).split('').map(c => c + c).join('').toLowerCase();
    }
    const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (!m) return '#000000';
    return '#' + [m[1], m[2], m[3]].map(n => parseInt(n).toString(16).padStart(2, '0')).join('');
}

/* Chart type comes from the same tokens as the page: mono (tabular) for every
   tick figure, condensed for axis and chart titles. Chart.js takes a plain font
   family string, so the token is read once per module load. */
const _cssFont = name => (getComputedStyle(document.body).getPropertyValue(name) || '').trim();
const TICK_FONT = _cssFont('--font-mono') || 'ui-monospace, monospace';
const AXIS_TITLE_FONT = _cssFont('--font-label') || 'system-ui, sans-serif';

/* "None"/"NONE"/blank all mean the measurement has no unit. */
function isNoneUnit(unit) {
    return !unit || String(unit).trim().toUpperCase() === 'NONE';
}

/* The main chart's heading: what was measured, and which file it came from. */
function chartHeading() {
    const meta = AppState.metaData || {};
    const meas = meta['Measurement'];
    const file = AppState.currentFile;
    if (meas && file) return `${meas} — ${file}`;
    if (meas) return meas;
    return t('chart.title_csv_content', 'Display selected CSV Content');
}

function getSourceColor(index) {
    return localStorage.getItem(`custom-source-color-${index}`)
        || AppState.plotColors[index % AppState.plotColors.length];
}

function createDataset(yData, label, analysis, selectColor, i, isSinglePoint) {
    const yColumn = yData.avg;
    const thisYAllEqual = yColumn.every(y => y === yColumn[0]);
    // A marker per reading turns a 120-point kinetics trace into a bead chain and
    // hides its shape. Points earn a marker only when there are few enough to read
    // individually; a long series is a line, with the tooltip for exact values.
    const autoRadius = isSinglePoint || thisYAllEqual ? 5 : (yColumn.length > 40 ? 0 : 3);
    // `chart_marker_mode` ("Line styles" panel): `auto` is the rule above,
    // `always`/`never` override it for everyone at once. A single point still
    // gets a marker under `never` — with no line to draw, hiding it would plot
    // nothing at all.
    const markerMode = (typeof USER_SETTINGS !== 'undefined' && USER_SETTINGS)
        ? USER_SETTINGS.chart_marker_mode : 'auto';
    const pointRadius = markerMode === 'always' ? 3
        : markerMode === 'never' ? (isSinglePoint ? 5 : 0)
        : autoRadius;

    const seriesIndex = selectColor !== null ? selectColor : i;

    const dataset = {
        label,
        data: yColumn,
        minData: yData.min, // Store min for distribution bars
        maxData: yData.max, // Store max for distribution bars
        stdData: yData.std, // Store std for tooltips
        borderColor: getSourceColor(seriesIndex),
        backgroundColor: getSourceColor(seriesIndex),
        borderWidth: seriesLineWidth(),
        borderDash: seriesDash(seriesIndex),
        tension: isSinglePoint ? 0 : 0.1,
        fill: false,
        pointRadius,
        spanGaps: true
    };

    if (analysis) {
        dataset.analysis = formatAnalysisInfo(analysis, label);
    }

    return dataset;
}

function createRegressionDataset(xMax, xMin, analysis, label) {
    const regressionData = getRegressionData(xMax, xMin, analysis, 100);
    if (regressionData.length === 0) return null;

    return {
        label: `Regression (${label})`,
        data: regressionData,
        // Flags the fitted line as not-measured-data. The chart's text
        // alternative (a11y.js `_fillChartTable`) drops it: its points are
        // `{x, y}` objects on their own 100-step grid, so a column of them
        // neither stringifies nor lines up with the measured rows.
        _isRegression: true,
        borderColor: 'rgba(0, 128, 0, 0.7)',
        tension: 0.1,
        fill: false,
        pointRadius: 0,
        borderWidth: 2
    };
}

function getChartScales(xColumn, allYValues, labels) {
    const isSinglePoint = xColumn.length === 1;
    const xMin = isSinglePoint ? xColumn[0] - 1 : Math.min(...xColumn);
    const xMax = isSinglePoint ? xColumn[0] + 1 : Math.max(...xColumn);
    const xStepSize = isSinglePoint ? 0.5 : Number((xMax - xMin) / (xColumn.length - 1)).toFixed(4) || 1;
    const { yMin, yMax, yStepSize } = findYDimension(allYValues, labels[0]);

    return { isSinglePoint, xMin, xMax, xStepSize, yMin, yMax, yStepSize };
}

function getAxisStyle(colorProperty) {
    return AppState.lightDisplay
        ? getComputedStyle(document.documentElement).getPropertyValue(`--chart-${colorProperty}-light`).trim()
        : getComputedStyle(document.documentElement).getPropertyValue(`--chart-${colorProperty}-dark`).trim();
}

function createAnnotations(isFullDisplay, measurementMode, analysis, conversionFactor, xMax, yMin, yMax, checkboxes, isSinglePoint) {
    const fontSize = 8;
    const annotations = {};

    if (isFullDisplay && measurementMode === "point" && AppState.refCalPoint) {
        annotations.refCalLine = {
            type: 'line',
            borderColor: 'rgba(255, 0, 0, 0.5)',
            borderWidth: 3,
            xMin: AppState.refCalPoint,
            xMax: AppState.refCalPoint,
            yMin,
            yMax,
            label: { display: true, content: 'RefCal', position: 'middle', font: { size: fontSize } }
        };
    }

    if (isFullDisplay && measurementMode === "kinetics" && analysis) {
        if (analysis.startMaxRate && !isSinglePoint && checkboxes.maxrate.checked) {
            annotations.maxRateLine = {
                type: 'line',
                borderColor: 'rgba(255, 0, 0, 0.5)',
                borderWidth: 3,
                xMin: parseFloat(analysis.startMaxRate * conversionFactor),
                xMax: parseFloat(analysis.endMaxRate * conversionFactor),
                yMin: parseFloat(analysis.yMaxRateStart),
                yMax: parseFloat(analysis.yMaxRateEnd),
                label: { display: true, content: 'MaxRate', position: 'start', font: { size: fontSize } }
            };
        }

        if (analysis.linearXMin && !isSinglePoint && checkboxes.slope.checked) {
            annotations.regressionLine = {
                type: 'line',
                borderColor: 'rgba(0, 0, 255, 0.5)',
                borderWidth: 3,
                xMin: parseFloat(analysis.linearXMin * conversionFactor),
                xMax: parseFloat(analysis.linearXMax * conversionFactor),
                yMin: parseFloat(analysis.linearYMin),
                yMax: parseFloat(analysis.linearYMax),
                label: { display: true, content: 'Linear', position: 'middle', font: { size: fontSize } }
            };
        }

        if (analysis.saturationValue !== "--" && !isSinglePoint && checkboxes.saturation.checked) {
            annotations.saturationLine = {
                type: 'line',
                borderColor: 'rgba(255, 0, 255, 0.5)',
                borderWidth: 3,
                xMin: parseFloat(analysis.timeStartSaturation * conversionFactor),
                xMax: xMax * 100,
                yMin: parseFloat(analysis.saturationValue),
                yMax: parseFloat(analysis.saturationValue),
                label: { display: true, content: 'Sat', position: 'end', font: { size: fontSize } }
            };
        }
    }

    return annotations;
}

const distributionBarsPlugin = {
    id: 'distributionBars',
    afterDatasetsDraw(chart) {
        const { ctx, scales: { x, y } } = chart;
        if (!x || !y) return;

        chart.data.datasets.forEach((dataset, datasetIndex) => {
            if (!dataset.minData || !dataset.maxData) return;

            ctx.save();
            ctx.strokeStyle = dataset.borderColor;
            ctx.lineWidth = 1.5;

            const meta = chart.getDatasetMeta(datasetIndex);
            if (meta.hidden) return;

            dataset.data.forEach((val, i) => {
                if (val === null || dataset.minData[i] === null || dataset.maxData[i] === null) return;

                // Only draw if there's an actual distribution
                if (Math.abs(dataset.maxData[i] - dataset.minData[i]) < 1e-6) return;

                const xPos = meta.data[i].x;
                const yMinPos = y.getPixelForValue(dataset.minData[i]);
                const yMaxPos = y.getPixelForValue(dataset.maxData[i]);

                // Draw vertical line
                ctx.beginPath();
                ctx.moveTo(xPos, yMinPos);
                ctx.lineTo(xPos, yMaxPos);
                ctx.stroke();

                // Draw horizontal caps
                const capWidth = 4;
                ctx.beginPath();
                ctx.moveTo(xPos - capWidth, yMinPos);
                ctx.lineTo(xPos + capWidth, yMinPos);
                ctx.moveTo(xPos - capWidth, yMaxPos);
                ctx.lineTo(xPos + capWidth, yMaxPos);
                ctx.stroke();
            });
            ctx.restore();
        });
    }
};

function generateChart(canvasId, allXColumn, allYColumnOrArray, labelOrLabels, unit, analysisOrArray, index = null) {
    const ctx = initializeChartCanvas(canvasId);
    if (!ctx) return null;

    const checkboxes = getCheckboxes(canvasId);
    const isFullDisplay = checkboxes.fullDisplay ? checkboxes.fullDisplay.checked : false;

    const labels = Array.isArray(labelOrLabels) ? labelOrLabels : [labelOrLabels];
    // Analysis shape differs by mode:
    // - normal measurement: one analysis per dataset (array)
    // - calibrate point: single analysis object
    // - calibrate kinetics: array of analyses (one per metric), and regression builder expects the FULL array
    let analyses;
    if (AppState.currentMeasurementMode === "calibrate" && calDiv.getAttribute('data-value') === "kinetics" && Array.isArray(analysisOrArray)) {
        analyses = [analysisOrArray];
    } else {
        analyses = Array.isArray(analysisOrArray) ? analysisOrArray : [analysisOrArray];
    }

    const { xColumn, processedYColumns, allYValues, conversionFactor } = processData(allXColumn, allYColumnOrArray, getTimeUnitValue());
    if (!xColumn || xColumn.length === 0) {
        document.getElementById(canvasId).style.display = 'none';
        return null;
    }

    const { isSinglePoint, xMin, xMax, xStepSize, yMin, yMax, yStepSize } = getChartScales(xColumn, allYValues, labels);

    const datasets = processedYColumns.map((yData, i) => {
        const dataset = createDataset(yData, labels[i], analyses[i], selectColor = index, i, isSinglePoint);
        const regressionDataset = (AppState.currentMeasurementMode === "calibrate") ? createRegressionDataset(xMax, xMin, analyses[i], labels[i]) : null;
        return [dataset, ...(regressionDataset ? [regressionDataset] : [])];
    }).flat();

    const chart = new Chart(ctx, {
        type: isSinglePoint ? 'scatter' : 'line',
        data: {
            labels: xColumn,
            datasets
        },
        plugins: [distributionBarsPlugin],
        options: {
            responsive: true,  // Ensure responsive behavior
            maintainAspectRatio: true,  // Maintain the aspect ratio
            aspectRatio: 1.5,  // 1:1.5 ratio (width:height = 1.5:1, so y is 2/3 of x)
            animation: false,
            scales: {
                x: {
                    type: 'linear',
                    title: {
                        display: true,
                        text: (AppState.currentMeasurementMode !== "calibrate")
                            ? (AppState.xAxis === 'turn' ? t('chart.axis_turn', 'Turn') : `Time (${getTimeUnitValue()})`)
                            : `Concentration (${typeof getMetaConcenUnit === 'function' ? getMetaConcenUnit(AppState.metaData) : 'ng/µL'})`,
                        color: getAxisStyle('label'),
                        font: { family: AXIS_TITLE_FONT, size: 11, weight: '600' }
                    },
                    min: xMin,
                    max: xMax,
                    grid: { color: getAxisStyle('grid') },
                    ticks: {
                        stepSize: xStepSize,
                        color: getAxisStyle('label'),
                        font: { family: TICK_FONT, size: 10 },
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 12,
                        // Turn is an integer index; show whole numbers, not 1.00, 2.00.
                        callback: value => (AppState.currentMeasurementMode !== "calibrate" && AppState.xAxis === 'turn')
                            ? String(Math.round(Number(value)))
                            : Number(value).toFixed(2)
                    }
                },
                y: {
                    type: 'linear',
                    title: {
                        display: true,
                        // A unitless measurement still has a name: an absorbance axis
                        // labelled "None" (or blank) told the reader nothing. Metadata,
                        // not UI copy, so it is never translated (Rule 2.22).
                        // "# Unit: None" is written by the firmware with that exact
                        // casing, and older files carry "NONE" — compare case-insensitively
                        // or a unitless axis ends up literally labelled "None".
                        text: !isNoneUnit(unit)
                            ? unit
                            : (AppState.metaData && AppState.metaData['Measurement']) || '',
                        color: getAxisStyle('label'),
                        font: { family: AXIS_TITLE_FONT, size: 11, weight: '600' }
                    },
                    min: yMin,
                    max: yMax,
                    grid: { color: getAxisStyle('grid') },
                    ticks: {
                        stepSize: yStepSize,
                        color: getAxisStyle('label'),
                        font: { family: TICK_FONT, size: 10 },
                        callback: value => Number(value).toFixed(3)
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            let value = context.raw;

                            // Handle scatter vs line (object vs number)
                            if (typeof value === 'object' && value !== null) {
                                return `(${value.x.toFixed(4)}, ${value.y.toFixed(4)})`;
                            }

                            return `${context.dataset.label || ''}: ${Number(value).toFixed(4)}`;
                        },
                        afterLabel: function (context) {
                            const dataset = context.dataset;
                            const index = context.dataIndex;
                            if (dataset.stdData && dataset.stdData[index] !== null && dataset.stdData[index] !== 0) {
                                return `Std Dev: ${dataset.stdData[index].toFixed(4)}`;
                            }
                            return null;
                        }
                    }
                },
                legend: AppState.currentMeasurementMode === "calibrate"
                    ? { labels: { color: getAxisStyle('label') } }
                    : { display: false },
                title: {
                    display: true,
                    // "Display selected CSV Content" described the app's action. The
                    // title now names the data: measurement + file, both metadata, so
                    // it needs no translation. The old key stays as the fallback for a
                    // chart drawn before any metadata is known.
                    text: index !== null
                        ? t('chart.title_source_data', 'Source {n} Data').replace('{n}', index + 1)
                        : chartHeading(),
                    color: getAxisStyle('title'),
                    font: { family: AXIS_TITLE_FONT, size: 12, weight: '600' }
                },
                annotation: {
                    annotations: createAnnotations(isFullDisplay, AppState.currentMeasurementMode, analyses[0], conversionFactor,
                        xMax, yMin, yMax, checkboxes, allXColumn.length === 1)
                }
            }
        }
    });

    AppState.chartInstances[canvasId] = chart;
    if (AppState.currentMeasurementMode !== "calibrate") {
        renderHtmlLegend(chart, canvasId, index);
    }

    // 1.1.1 — the plot itself is unreadable to assistive technology. Name the
    // canvas and publish the same numbers as a table beside it (a11y.js). The
    // table is built only when someone opens it, so a long kinetics trace does
    // not cost thousands of DOM nodes nobody looks at.
    if (typeof buildChartDataTable === 'function') {
        buildChartDataTable(canvasId, chart,
            index !== null && index !== undefined ? `Source ${index + 1}` : null);
    }

    return chart;
}

function renderHtmlLegend(chart, canvasId, sourceIndex) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    let legendEl = document.getElementById(`html-legend-${canvasId}`);
    if (!legendEl) {
        legendEl = document.createElement('div');
        legendEl.id = `html-legend-${canvasId}`;
        canvas.parentElement.insertBefore(legendEl, canvas);
    }
    legendEl.innerHTML = '';

    const items = Chart.defaults.plugins.legend.labels.generateLabels(chart);

    // Toggling six sources one swatch at a time is six clicks to clear the plot
    // and six more to bring it back. One control does the lot. It leads the
    // strip because it acts on every item after it, and it only appears when
    // there is more than one line to act on.
    if (items.length > 1) {
        const anyVisible = items.some((it) => !it.hidden);
        const bulk = document.createElement('button');
        bulk.type = 'button';
        bulk.className = 'legend-bulk-toggle';
        bulk.textContent = anyVisible
            ? t('chart.hide_all_lines', 'Hide all lines')
            : t('chart.show_all_lines', 'Show all lines');
        bulk.setAttribute('aria-pressed', anyVisible ? 'false' : 'true');
        bulk.addEventListener('click', () => {
            items.forEach((it) => chart.setDatasetVisibility(it.datasetIndex, !anyVisible));
            chart.update('none');
            renderHtmlLegend(chart, canvasId, sourceIndex);
            if (typeof announce === 'function') {
                announce(anyVisible
                    ? t('chart.all_lines_hidden', 'All lines hidden')
                    : t('chart.all_lines_shown', 'All lines shown'));
            }
        });
        legendEl.appendChild(bulk);

        const styles = document.createElement('button');
        styles.type = 'button';
        styles.className = 'legend-bulk-toggle';
        styles.textContent = t('chart.line_styles', 'Line styles');
        styles.setAttribute('aria-haspopup', 'dialog');
        styles.addEventListener('click', (e) => {
            e.stopPropagation();
            const r = styles.getBoundingClientRect();
            showBulkStyleEditor(r.left, r.bottom, canvasId);
        });
        legendEl.appendChild(styles);
    }

    items.forEach((item) => {
        const isRegression = item.text.startsWith('Regression (');
        const storageIndex = sourceIndex !== null ? sourceIndex : item.datasetIndex;

        const row = document.createElement('span');
        row.className = 'legend-item' + (item.hidden ? ' hidden-dataset' : '');

        const swatch = document.createElement('span');
        swatch.className = 'legend-swatch';
        swatch.style.background = item.strokeStyle;

        const labelSpan = document.createElement('span');
        labelSpan.className = 'legend-label';
        labelSpan.textContent = item.text;

        const toggle = () => {
            chart.setDatasetVisibility(item.datasetIndex, item.hidden);
            chart.update('none');
            renderHtmlLegend(chart, canvasId, sourceIndex);
        };
        swatch.addEventListener('click', toggle);
        labelSpan.addEventListener('click', toggle);

        row.appendChild(swatch);
        row.appendChild(labelSpan);

        if (!isRegression) {
            const pencil = document.createElement('button');
            pencil.className = 'legend-pencil';
            pencil.textContent = '✎';
            pencil.setAttribute('data-hint', t('hint.edit_label_color', 'Edit label and color'));
            pencil.addEventListener('click', (e) => {
                e.stopPropagation();
                const rect = pencil.getBoundingClientRect();
                showLegendStyleEditor(rect.left, rect.bottom, item, canvasId, storageIndex);
            });
            row.appendChild(pencil);
        }

        legendEl.appendChild(row);
    });
}

function updateAnalysisColor(storageIndex, color) {
    // Split mode: source-N-analysis div contains a span as first child
    const splitDiv = document.getElementById(`source-${storageIndex}-analysis`);
    if (splitDiv) {
        const span = splitDiv.querySelector('span');
        if (span) span.style.color = color;
        return;
    }
    // Grouped mode: analysis-content-plot-analysis-source-N → parentElement is the span
    const innerDiv = document.getElementById(`analysis-content-plot-analysis-source-${storageIndex}`);
    if (innerDiv?.parentElement?.tagName === 'SPAN') {
        innerDiv.parentElement.style.color = color;
    }
}

/* ---------------------------------------------------------------------------
   "Line styles" — the bulk counterpart to the per-series pencil.

   Editing twelve series one pencil at a time is twelve popovers; this sets the
   four properties that apply to all of them at once. Every control writes
   straight to `user_settings.json` (a per-machine preference, not per-file
   state, so it does not belong in localStorage beside the custom labels) and
   redraws from `ChartDataStore`, so the effect is visible while the panel is
   still open.
--------------------------------------------------------------------------- */
/* One redraw for every surface the bulk style settings touch, so the "Line
   styles" panel and App Settings → Data Display cannot drift apart: both write
   the same `user_settings.json` keys, both update the live `USER_SETTINGS`, and
   both end here. Rebuilds each live chart from `ChartDataStore` (split-source
   mode has one per source) and repaints the analysis headings, which read the
   same palette but sit outside the chart. */
function refreshChartStyles() {
    const store = window.ChartDataStore || {};
    Object.keys(store).forEach((canvasId) => {
        if (!document.getElementById(canvasId)) return;
        if (typeof handleCkboxChange === 'function') handleCkboxChange(canvasId);
    });
    if (typeof updateAnalysisColor === 'function' && typeof AppState !== 'undefined') {
        const n = AppState.numSources || 0;
        for (let i = 0; i < n; i++) updateAnalysisColor(i, getSourceColor(i));
    }
}

// The keys the panel and the settings modal share. Exported so init.js can ask
// "did any of these change?" without restating the list and letting it rot.
const CHART_STYLE_KEYS = [
    'chart_line_width', 'chart_dash_mode', 'chart_marker_mode',
    'chart_palette', 'chart_ramp_color'
];

// The theme's middle ramp stop — what the swatch shows when nothing is
// overridden, so opening the picker starts from the colour actually on screen.
function _currentRampMid() {
    const v = getComputedStyle(document.body).getPropertyValue('--ramp-5').trim();
    return /^#[0-9a-fA-F]{6}$/.test(v) ? v : '#b85207';
}

function showBulkStyleEditor(clientX, clientY, canvasId) {
    const existing = document.getElementById('bulk-style-editor');
    if (existing) { existing.remove(); return; }

    const settings = (typeof USER_SETTINGS !== 'undefined' && USER_SETTINGS) ? USER_SETTINGS : {};
    const panel = document.createElement('div');
    panel.id = 'bulk-style-editor';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', t('chart.line_styles', 'Line styles'));
    panel.style.left = `${clientX}px`;
    panel.style.top = `${clientY + 4}px`;

    const apply = (key, value) => {
        settings[key] = value;
        if (typeof saveUserSetting === 'function') saveUserSetting(key, value);
        redrawFromStore();
    };

    const row = (labelText) => {
        const r = document.createElement('div');
        r.className = 'bulk-style-row';
        const l = document.createElement('span');
        l.className = 'bulk-style-label';
        l.textContent = labelText;
        r.appendChild(l);
        return r;
    };

    // A segmented control: one button per choice, the current one pressed.
    const segmented = (key, choices, current) => {
        const group = document.createElement('div');
        group.className = 'bulk-style-seg';
        group.setAttribute('role', 'group');
        choices.forEach(([value, label]) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            b.setAttribute('aria-pressed', String(value === current));
            b.addEventListener('click', () => {
                group.querySelectorAll('button').forEach((o) => o.setAttribute('aria-pressed', 'false'));
                b.setAttribute('aria-pressed', 'true');
                apply(key, value);
            });
            group.appendChild(b);
        });
        return group;
    };

    const widthRow = row(t('chart.line_width', 'Width'));
    widthRow.appendChild(segmented('chart_line_width',
        [[1, '1'], [2, '2'], [3, '3'], [4, '4']],
        Number(settings.chart_line_width ?? 2)));
    panel.appendChild(widthRow);

    const dashRow = row(t('chart.line_dash', 'Dash'));
    dashRow.appendChild(segmented('chart_dash_mode', [
        ['none', t('chart.dash_none', 'None')],
        ['cycle', t('chart.dash_cycle', 'Cycle')]
    ], settings.chart_dash_mode || 'none'));
    panel.appendChild(dashRow);

    const markerRow = row(t('chart.line_markers', 'Markers'));
    markerRow.appendChild(segmented('chart_marker_mode', [
        ['auto', t('chart.markers_auto', 'Auto')],
        ['always', t('chart.markers_always', 'Always')],
        ['never', t('chart.markers_never', 'Never')]
    ], settings.chart_marker_mode || 'auto'));
    panel.appendChild(markerRow);

    const paletteRow = row(t('chart.line_palette', 'Palette'));
    paletteRow.appendChild(segmented('chart_palette', [
        ['ramp', t('chart.palette_ramp', 'Ramp')],
        ['distinct', t('chart.palette_distinct', 'Distinct')]
    ], settings.chart_palette || 'ramp'));
    panel.appendChild(paletteRow);

    // The ramp's own colour. Picking re-hues all ten stops; they keep the
    // lightness ladder, so the series stay separable whatever hue is chosen.
    // "Default" clears the override and hands the ramp back to the theme.
    const rampRow = row(t('chart.ramp_color', 'Ramp colour'));
    const rampControls = document.createElement('span');
    rampControls.className = 'bulk-style-seg';

    const swatch = document.createElement('input');
    swatch.type = 'color';
    swatch.className = 'bulk-style-swatch';
    swatch.setAttribute('aria-label', t('chart.ramp_color', 'Ramp colour'));
    swatch.value = settings.chart_ramp_color || _currentRampMid();
    // `input` fires continuously while dragging; redraw live but only persist
    // on `change`, so one pick is one write rather than a hundred.
    swatch.addEventListener('input', () => {
        settings.chart_ramp_color = swatch.value;
        redrawFromStore();
    });
    swatch.addEventListener('change', () => apply('chart_ramp_color', swatch.value));

    const rampDefault = document.createElement('button');
    rampDefault.type = 'button';
    rampDefault.textContent = t('chart.ramp_color_default', 'Default');
    rampDefault.addEventListener('click', () => {
        swatch.value = _currentRampMid();
        apply('chart_ramp_color', null);
        swatch.value = _currentRampMid();
    });

    rampControls.appendChild(swatch);
    rampControls.appendChild(rampDefault);
    rampRow.appendChild(rampControls);
    panel.appendChild(rampRow);

    // Per-series colours are localStorage overrides and outrank everything the
    // palette does, so a palette that "did nothing" is usually a stale override.
    const reset = document.createElement('button');
    reset.type = 'button';
    reset.className = 'bulk-style-reset';
    reset.textContent = t('chart.reset_styles', 'Reset custom colours');
    reset.addEventListener('click', () => {
        if (typeof clearCustomColors === 'function') clearCustomColors();
        redrawFromStore();
        if (typeof announce === 'function') {
            announce(t('chart.styles_reset', 'Custom colours cleared'));
        }
    });
    panel.appendChild(reset);

    // The same re-render entry point the per-series editor uses on close: it
    // reads `ChartDataStore` and rebuilds the analyses, so the styles land
    // without this panel having to reconstruct an argument list it would get
    // subtly wrong for split-source or calibrate charts.
    const redrawFromStore = () => refreshChartStyles();

    const onOutsideClick = (e) => {
        if (!panel.contains(e.target)) {
            document.removeEventListener('mousedown', onOutsideClick);
            document.removeEventListener('keydown', onEsc);
            panel.remove();
        }
    };
    const onEsc = (e) => {
        if (e.key === 'Escape') {
            document.removeEventListener('mousedown', onOutsideClick);
            document.removeEventListener('keydown', onEsc);
            panel.remove();
        }
    };

    document.body.appendChild(panel);
    setTimeout(() => {
        document.addEventListener('mousedown', onOutsideClick);
        document.addEventListener('keydown', onEsc);
        const first = panel.querySelector('button');
        if (first) first.focus();
    }, 0);
}

function showLegendStyleEditor(clientX, clientY, legendItem, canvasId, storageIndex) {
    const existing = document.getElementById('legend-style-editor');
    if (existing) existing.remove();
    const existingSizer = document.getElementById('legend-label-editor-sizer');
    if (existingSizer) existingSizer.remove();

    const sizer = document.createElement('span');
    sizer.id = 'legend-label-editor-sizer';
    document.body.appendChild(sizer);

    const editor = document.createElement('div');
    editor.id = 'legend-style-editor';
    editor.style.left = `${clientX}px`;
    editor.style.top = `${clientY + 4}px`;

    const labelInput = document.createElement('input');
    labelInput.type = 'text';
    labelInput.value = legendItem.text;
    labelInput.placeholder = 'Label…';

    const colorInput = document.createElement('input');
    colorInput.type = 'color';
    colorInput.value = toHex(getSourceColor(storageIndex));

    editor.appendChild(labelInput);
    editor.appendChild(colorInput);

    const syncWidth = () => {
        sizer.textContent = labelInput.value || labelInput.placeholder;
        labelInput.style.width = `${sizer.offsetWidth + 2}px`;
    };
    labelInput.addEventListener('input', syncWidth);

    // Live color preview — fast path, no full re-render
    colorInput.addEventListener('input', () => {
        const chart = AppState.chartInstances[canvasId];
        if (chart) {
            const ds = chart.data.datasets[legendItem.datasetIndex];
            if (ds) {
                ds.borderColor = colorInput.value;
                ds.backgroundColor = colorInput.value;
                chart.update('none');
            }
        }
        updateAnalysisColor(storageIndex, colorInput.value);
    });

    let committed = false;
    const onOutsideClick = (e) => {
        if (!editor.contains(e.target)) closeEditor(true);
    };

    const closeEditor = (shouldCommit) => {
        if (committed) return;
        committed = true;
        document.removeEventListener('mousedown', onOutsideClick);
        sizer.remove();

        if (shouldCommit) {
            const labelValue = labelInput.value.trim();
            if (labelValue !== '') {
                localStorage.setItem(`custom-line-label-source-${storageIndex}`, labelValue);
            } else {
                localStorage.removeItem(`custom-line-label-source-${storageIndex}`);
            }
            const defaultColor = toHex(AppState.plotColors[storageIndex % AppState.plotColors.length]);
            if (colorInput.value !== defaultColor) {
                localStorage.setItem(`custom-source-color-${storageIndex}`, colorInput.value);
            } else {
                localStorage.removeItem(`custom-source-color-${storageIndex}`);
            }
        }

        editor.remove();
        handleCkboxChange(canvasId);
        updateAnalysisColor(storageIndex, getSourceColor(storageIndex));
    };

    labelInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); closeEditor(true); }
        if (e.key === 'Escape') { closeEditor(false); }
    });

    // Measure and set width before first paint to avoid shrink flash
    syncWidth();
    document.body.appendChild(editor);

    setTimeout(() => {
        document.addEventListener('mousedown', onOutsideClick);
        labelInput.select();
        labelInput.focus();
    }, 0);
}