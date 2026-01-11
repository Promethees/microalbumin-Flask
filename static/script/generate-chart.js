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
        const { x: px, y: py } = mapDuplicates(allXColumn, yCol);
        const { XColumn: xAfterAvg, YColumn: yAfterAvg } = averageDuplicates(px, py);
        processedYColumns.push(yAfterAvg);
        allYValues.push(...yAfterAvg);
        if (i === 0) {
            xColumn = xAfterAvg;
        }
    });

    return { xColumn, processedYColumns, allYValues, conversionFactor };
}

function createDataset(yColumn, label, analysis, selectColor, i, isSinglePoint) {
    const thisYAllEqual = yColumn.every(y => y === yColumn[0]);
    const pointRadius = isSinglePoint || thisYAllEqual ? 5 : 3;
    
    const dataset = {
        label,
        data: yColumn,
        borderColor: selectColor !== null 
            ? AppState.plotColors[selectColor % AppState.plotColors.length] 
            : AppState.plotColors[i % AppState.plotColors.length],
        tension: isSinglePoint ? 0 : 0.1,
        fill: false,
        pointRadius
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

function generateChart(canvasId, allXColumn, allYColumnOrArray, labelOrLabels, unit, analysisOrArray, index = null) {
    const ctx = initializeChartCanvas(canvasId);
    if (!ctx) return null;

    const checkboxes = getCheckboxes(canvasId);
    const isFullDisplay = checkboxes.fullDisplay ? checkboxes.fullDisplay.checked : false;
    
    const labels = Array.isArray(labelOrLabels) ? labelOrLabels : [labelOrLabels];
    const analyses = (Array.isArray(analysisOrArray) && AppState.currentMeasurementMode !== "calibrate") 
        ? analysisOrArray 
        : [analysisOrArray];

    const { xColumn, processedYColumns, allYValues, conversionFactor } = processData(allXColumn, allYColumnOrArray, getTimeUnitValue());
    if (!xColumn || xColumn.length === 0) {
        document.getElementById(canvasId).style.display = 'none';
        return null;
    }

    const { isSinglePoint, xMin, xMax, xStepSize, yMin, yMax, yStepSize } = getChartScales(xColumn, allYValues, labels);

    const datasets = processedYColumns.map((yColumn, i) => {
        const dataset = createDataset(yColumn, labels[i], analyses[i], selectColor = index, i, isSinglePoint);
        const regressionDataset = (AppState.currentMeasurementMode === "calibrate") ? createRegressionDataset(xMax, xMin, analyses[i], labels[i]) : null;
        return [dataset, ...(regressionDataset ? [regressionDataset] : [])];
    }).flat();

    const chart = new Chart(ctx, {
        type: isSinglePoint ? 'scatter' : 'line',
        data: {
            labels: xColumn,
            datasets
        },
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
                legend: { labels: { color: getAxisStyle('label') } },
                title: {
                    display: true,
                    text: AppState.multiSource && index !== null ? `Source ${index + 1} Data` : 'Display selected CSV Content',
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
    return chart;
}