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
    const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (!m) return '#000000';
    return '#' + [m[1], m[2], m[3]].map(n => parseInt(n).toString(16).padStart(2, '0')).join('');
}

function getSourceColor(index) {
    return localStorage.getItem(`custom-source-color-${index}`)
        || AppState.plotColors[index % AppState.plotColors.length];
}

function createDataset(yData, label, analysis, selectColor, i, isSinglePoint) {
    const yColumn = yData.avg;
    const thisYAllEqual = yColumn.every(y => y === yColumn[0]);
    const pointRadius = isSinglePoint || thisYAllEqual ? 5 : 3;

    const dataset = {
        label,
        data: yColumn,
        minData: yData.min, // Store min for distribution bars
        maxData: yData.max, // Store max for distribution bars
        stdData: yData.std, // Store std for tooltips
        borderColor: getSourceColor(selectColor !== null ? selectColor : i),
        backgroundColor: getSourceColor(selectColor !== null ? selectColor : i),
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
                        text: (AppState.currentMeasurementMode !== "calibrate") ? `Time (${getTimeUnitValue()})` : 'Concentration (ng/µL)',
                        color: getAxisStyle('label')
                    },
                    min: xMin,
                    max: xMax,
                    grid: { color: getAxisStyle('grid') },
                    ticks: {
                        stepSize: xStepSize,
                        color: getAxisStyle('label'),
                        callback: value => Number(value).toFixed(2)
                    }
                },
                y: {
                    type: 'linear',
                    title: {
                        display: true,
                        text: unit !== "NONE" ? unit : '',
                        color: getAxisStyle('label')
                    },
                    min: yMin,
                    max: yMax,
                    grid: { color: getAxisStyle('grid') },
                    ticks: {
                        stepSize: yStepSize,
                        color: getAxisStyle('label'),
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
                    text: index !== null ? `Source ${index + 1} Data` : 'Display selected CSV Content',
                    color: getAxisStyle('title')
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
            pencil.title = 'Edit label and color';
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