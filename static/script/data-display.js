function generateChart(canvasId, allXColumn, allYColumnOrArray, labelOrLabels, unit, timeUnit, conversionFactor, analysisOrArray, forThisBlankType = false, selectColor = null, index = null) {
    if (AppState.chartInstances[canvasId]) {
        AppState.chartInstances[canvasId].destroy();
    }
    
    const canvas = document.getElementById(canvasId);

    // Modify this according to the canvasID
    const canvasString = canvasId.split("-canvas")[0];
    const maxrate_chkbox = document.getElementById(`maxrate-${canvasString}`);
    const slope_chkbox = document.getElementById(`slope-${canvasString}`);
    const sat_chkbox = document.getElementById(`sat-${canvasString}`);
    const fullDisplayCheckbox = document.getElementById(`full-display-${canvasString}`);
    const isFullDisplay = fullDisplayCheckbox ? fullDisplayCheckbox.checked : false;
    const { x: processedX, y: dummyProcessedY } = mapDuplicates(allXColumn, allYColumnOrArray.length > 0 ? allYColumnOrArray[0] : allXColumn.map(() => 0)); // Use first Y or dummy for X processing

    if (!canvas || processedX.length === 0) {
        $(`#${canvasId}`).hide();
        return null;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx || processedX.length === 0) {
        $(`#${canvasId}`).hide();
        return null;
    }

    // Determine if multiple Y columns
    const isMultipleY = Array.isArray(allYColumnOrArray[0]);
    const allYColumns = isMultipleY ? allYColumnOrArray : [allYColumnOrArray];
    const labels = Array.isArray(labelOrLabels) ? labelOrLabels : [labelOrLabels];
    const analyses = (Array.isArray(analysisOrArray) && AppState.currentMeasurementMode !== "calibrate") ? analysisOrArray : [analysisOrArray];

    // Process each Y column
    const processedYColumns = [];
    const allYValues = [];
    let xColumn; // Shared X after processing
    allYColumns.forEach((yCol, i) => {
        const { x: px, y: py } = mapDuplicates(allXColumn, yCol);
        const { XColumn: xAfterAvg, YColumn: yAfterAvg } = averageDuplicates(px, py);
        processedYColumns.push(yAfterAvg);
        allYValues.push(...yAfterAvg);
        if (i === 0) {
            xColumn = xAfterAvg;
        }
    });

    // Handle single data point edge case (global, since X shared)
    const isSinglePoint = xColumn.length === 1;
    const chartType = isSinglePoint ? 'scatter' : 'line';
    const xMin = isSinglePoint ? xColumn[0] - 1 : Math.min(...xColumn);
    const xMax = isSinglePoint ? xColumn[0] + 1 : Math.max(...xColumn);

    // Check if all Y values across all datasets are equal
    const allYEqual = allYValues.length > 0 && allYValues.every(y => y === allYValues[0]);
    let yMin, yMax, yStepSize;

    if (allYEqual) {
        // Case: All Y values are equal
        const yValue = allYValues[0];
        if (yValue === 0) {
            // If Y value is 0, set a small range around 0
            yMin = -0.1;
            yMax = 0.1;
            yStepSize = 0.02; // Small step size for zero case
        } else {
            // For non-zero equal Y values, set range ±10% of the value
            yMin = yValue * 0.9;
            yMax = yValue * 1.1;
            yStepSize = Number((yMax - yMin) / 10).toFixed(3) || 0.01;
        }
    } else {
        // Original logic for non-equal Y values
        yMin = 0;
        yMax = isSinglePoint ? Math.max(...allYValues) * 1.1 : Math.max(...allYValues) * 1.1;
        yStepSize = Number((yMax - yMin) / 10).toFixed(3) || 0.1;
    }

    // Calculate xStepSize safely
    const xStepSize = isSinglePoint
        ? 0.5
        : Number((xMax - xMin) / (xColumn.length - 1)).toFixed(2) || 1;

    // Prepare datasets
    const datasets = [];
    allYColumns.forEach((_, i) => {
        const yColumn = processedYColumns[i];
        const label = labels[i];
        const analysis = analyses[i];

        // Per-dataset all Y equal check for point radius
        const thisYAllEqual = yColumn.every(y => y === yColumn[0]);
        const pointRadius = isSinglePoint || thisYAllEqual ? 5 : 3;

        const mainDataset = {
            label: label,
            data: yColumn,
            borderColor: selectColor !== null ? AppState.plotColors[selectColor % AppState.plotColors.length] : AppState.plotColors[i % AppState.plotColors.length],
            tension: isSinglePoint ? 0 : 0.1,
            fill: false,
            pointRadius: pointRadius
        };

        // Attach analysis data to the main dataset if provided
        if (analysis) {
            mainDataset.analysis = formatAnalysisInfo(analysis, conversionFactor, unit, label);
        }

        datasets.push(mainDataset);

        // Prepare regression line data if calibrate mode and analysis has coefficients
        let regressionData = getRegressionData(xMax, xMin, analysis, 100);  
        if (regressionData.length > 0) {
            datasets.push({
                label: `Regression (${label})`,
                data: regressionData,
                borderColor: 'rgba(0, 128, 0, 0.7)', // Green for regression line
                tension: 0.1,
                fill: false,
                pointRadius: 0, // No points for regression line
                borderWidth: 2
            });
        }
    });

    // Use first analysis for annotations (or null if none)
    const analysisForAnnotations = analyses.length > 0 ? analyses[0] : null;

    let chart = new Chart(ctx, {
        type: chartType,
        data: {
            labels: xColumn,
            datasets: datasets
        },
        options: {
            animation: false,
            scales: {
                x: {
                    type: 'linear',
                    title: { 
                        display: true, 
                        text: timeUnit ? `Time (${timeUnit})` : 'Concentration (ng/µL)',
                        color: AppState.lightDisplay ? getComputedStyle(document.documentElement).getPropertyValue('--chart-label-light').trim() :
                            getComputedStyle(document.documentElement).getPropertyValue('--chart-label-dark').trim() 
                    },
                    min: xMin,
                    max: xMax,
                    grid: {
                        color: AppState.lightDisplay ? getComputedStyle(document.documentElement).getPropertyValue('--chart-grid-light').trim() :
                            getComputedStyle(document.documentElement).getPropertyValue('--chart-grid-dark').trim()
                    },
                    ticks: {
                        stepSize: xStepSize,
                        color: AppState.lightDisplay ? getComputedStyle(document.documentElement).getPropertyValue('--chart-label-light').trim() :
                            getComputedStyle(document.documentElement).getPropertyValue('--chart-label-dark').trim(),
                        callback: function(value) {
                            return Number(value).toFixed(2);
                        }
                    }
                },
                y: {
                    type: 'linear',
                    title: { 
                        display: true, 
                        text: unit !== "NONE" ? unit : '',
                        color: AppState.lightDisplay ? getComputedStyle(document.documentElement).getPropertyValue('--chart-label-light').trim() :
                            getComputedStyle(document.documentElement).getPropertyValue('--chart-label-dark').trim()
                    },
                    min: yMin,
                    max: yMax,
                    grid: {
                        color: AppState.lightDisplay ? getComputedStyle(document.documentElement).getPropertyValue('--chart-grid-light').trim() :
                            getComputedStyle(document.documentElement).getPropertyValue('--chart-grid-dark').trim()
                    },
                    ticks: {
                        stepSize: yStepSize,
                        color: AppState.lightDisplay ? getComputedStyle(document.documentElement).getPropertyValue('--chart-label-light').trim() :
                            getComputedStyle(document.documentElement).getPropertyValue('--chart-label-dark').trim(),
                        callback: function(value) {
                            return Number(value).toFixed(3);
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: AppState.lightDisplay ? getComputedStyle(document.documentElement).getPropertyValue('--chart-label-light').trim() :
                            getComputedStyle(document.documentElement).getPropertyValue('--chart-label-dark').trim()
                    }
                },
                title: {
                    display: true,
                    text: AppState.multiSource && index !== null ? `Source ${index + 1} Data` : 'Display selected CSV Content',
                    color: AppState.lightDisplay ? getComputedStyle(document.documentElement).getPropertyValue('--chart-title-light').trim() :
                        getComputedStyle(document.documentElement).getPropertyValue('--chart-title-dark').trim()
                },
                annotation: {
                    annotations: {
                        ...(isFullDisplay && AppState.currentMeasurementMode === "point" && forThisBlankType && {
                            refCalLine: {
                                type: 'line',
                                borderColor: 'rgba(255, 0, 0, 0.5)',
                                borderWidth: 3,
                                xMin: AppState.refCalPoint,
                                xMax: AppState.refCalPoint,
                                yMin: yMin,
                                yMax: yMax,
                                label: {
                                    display: true,
                                    content: 'RefCal',
                                    position: 'middle'
                                }
                            }
                        }),
                        ...(isFullDisplay && AppState.currentMeasurementMode === "kinetics" && analysisForAnnotations?.startMaxRate && !isSinglePoint && maxrate_chkbox.checked && {
                            maxRateLine: {
                                type: 'line',
                                borderColor: 'rgba(255, 0, 0, 0.5)',
                                borderWidth: 3,
                                xMin: parseFloat(analysisForAnnotations.startMaxRate * conversionFactor),
                                xMax: parseFloat(analysisForAnnotations.endMaxRate * conversionFactor),
                                yMin: parseFloat(analysisForAnnotations.yMaxRateStart),
                                yMax: parseFloat(analysisForAnnotations.yMaxRateEnd),
                                label: {
                                    display: true,
                                    content: 'MaxRate',
                                    position: 'start'
                                }
                            }
                        }),
                        ...(isFullDisplay && AppState.currentMeasurementMode === "kinetics" && analysisForAnnotations?.linearXMin && !isSinglePoint && slope_chkbox.checked && {
                            regressionLine: {
                                type: 'line',
                                borderColor: 'rgba(0, 0, 255, 0.5)',
                                borderWidth: 3,
                                xMin: parseFloat(analysisForAnnotations.linearXMin * conversionFactor),
                                xMax: parseFloat(analysisForAnnotations.linearXMax * conversionFactor),
                                yMin: parseFloat(analysisForAnnotations.linearYMin),
                                yMax: parseFloat(analysisForAnnotations.linearYMax),
                                label: {
                                    display: true,
                                    content: 'Linear',
                                    position: 'middle'
                                }
                            }
                        }),
                        ...(isFullDisplay && AppState.currentMeasurementMode === "kinetics" && analysisForAnnotations?.saturationValue !== "--" && !isSinglePoint && sat_chkbox.checked && {
                            saturationLine: {
                                type: 'line',
                                borderColor: 'rgba(255, 0, 255, 0.5)',
                                borderWidth: 3,
                                xMin: parseFloat(analysisForAnnotations.timeStartSaturation * conversionFactor),
                                xMax: xMax * 100,
                                yMin: parseFloat(analysisForAnnotations.saturationValue),
                                yMax: parseFloat(analysisForAnnotations.saturationValue),
                                label: {
                                    display: true,
                                    content: 'Sat',
                                    position: 'end'
                                }
                            }
                        })
                    }
                }
            }
        }
    });

    AppState.chartInstances[canvasId] = chart;

    return chart;
}

function formatAnalysisInfo(analysis, conversionFactor, unit, label) {
    if (!analysis) {
        return null;
    }

    let chartScaleConstant = 1;
    let adjustedSlope = analysis.slope ? (parseFloat(analysis.slope) / conversionFactor).toFixed(4) : "--";
    let adjustedLinearStart = analysis.linearXMin ? (parseFloat(analysis.linearXMin) * conversionFactor).toFixed(2) : "--";
    let adjustedLinearEnd = analysis.linearXMax ? (parseFloat(analysis.linearXMax) * conversionFactor).toFixed(2) : "--";
    let adjustedMaxRate = parseFloat(analysis.maxRate) / conversionFactor;
    let adjustedMaxRateStart = analysis.startMaxRate ? (parseFloat(analysis.startMaxRate) * conversionFactor).toFixed(2) : "--";
    let adjustedMaxRateEnd = analysis.endMaxRate ? (parseFloat(analysis.endMaxRate) * conversionFactor).toFixed(2) : "--";
    let adjustedTimeToSaturationDisplay = (analysis.timeToSaturation !== null) ? (parseFloat(analysis.timeToSaturation) * conversionFactor).toFixed(2) : "--";
    let adjustedSaturationValue = (analysis.timeToSaturation !== null) ? parseFloat(analysis.saturationValue).toFixed(3) : "--";
    adjustedMaxRate = (3600 * adjustedMaxRate).toFixed(5) !== "0.00000" ? adjustedMaxRate.toFixed(5) : "--";

    return {
        slope: adjustedSlope,
        linearStart: adjustedLinearStart,
        linearEnd: adjustedLinearEnd,
        saturationValue: adjustedSaturationValue,
        timeToSaturation: adjustedTimeToSaturationDisplay,
        maxRate: adjustedMaxRate,
        maxRateStart: adjustedMaxRateStart,
        maxRateEnd: adjustedMaxRateEnd,
        MeasUnit: unit,
        Meas: label
    };
}

function checkboxHtmlWithID(
  id,
  canvasId,
  allXColumn,
  allYColumnOrArray,
  labelOrLabels,
  unit,
  timeUnit,
  conversionFactor,
  analysisOrArray,
  forThisBlankType,
  selectColor,
  index
) {
  return AppState.quantity_input.quantities
    .filter(q => q !== "Time To Sat")
    .map(q => `
      <input type="checkbox" 
          class="quantity-checkbox" 
          value="${q}" 
          id="${q.toLowerCase().replace(/\s+/g, '_')}-${id}" 
          checked
          data-analysis='${JSON.stringify(analysisOrArray)}'
          onchange="handleCkboxChange(this, 
              '${canvasId}', 
              ${JSON.stringify(allXColumn)}, 
              ${JSON.stringify(allYColumnOrArray)}, 
              '${labelOrLabels}', 
              '${unit}', 
              '${timeUnit}', 
              ${conversionFactor}, 
              ${forThisBlankType}, 
              ${JSON.stringify(selectColor)}, 
              ${index}
          )">
      <span>${q}</span>
    `)
    .join("");
}

function handleCkboxChange(checkbox, canvasId, allXColumn, allYColumnOrArray, labelOrLabels, unit, timeUnit, conversionFactor, forThisBlankType, selectColor, index) {
  const analysisOrArray = JSON.parse(checkbox.dataset.analysis);
  generateChart(
    canvasId,
    allXColumn,
    allYColumnOrArray,
    labelOrLabels,
    unit,
    timeUnit,
    conversionFactor,
    analysisOrArray,
    forThisBlankType,
    selectColor,
    index
  );
}

function createChartSection({
    sectionId,
    analysisId,
    canvasId,
    quantityId,
    fullDisplayId,
    allXColumn,
    allYColumnOrArray,
    labelOrLabels,
    unit,
    timeUnit,
    conversionFactor,
    analysisOrArray,
    forThisBlankType,
    selectColor,
    index
}) {
    return AppState.currentMeasurementMode !== "calibrate" ? 
    `
        <div id="${sectionId}">
            <label>
                <input type="checkbox" id="${fullDisplayId}" 
                    data-analysis='${JSON.stringify(analysisOrArray)}'
                    onchange="handleFullDisplayChange(
                        this,
                        '${fullDisplayId}', 
                        '${quantityId}', 
                        '${canvasId}', 
                        ${JSON.stringify(allXColumn)}, 
                        ${JSON.stringify(allYColumnOrArray)}, 
                        '${labelOrLabels}', 
                        '${unit}', 
                        '${timeUnit}', 
                        ${conversionFactor}, 
                        ${forThisBlankType}, 
                        ${JSON.stringify(selectColor)}, 
                        ${index}
                    )"> 
                Full display: See all data and special lines
            </label>
            <label id="quantity-checkboxes-${quantityId}" class="hidden">
                <h3>Quantities to display on graphic</h3>
                ${checkboxHtmlWithID(quantityId, canvasId, allXColumn, allYColumnOrArray, labelOrLabels, unit, timeUnit, conversionFactor, analysisOrArray, forThisBlankType, selectColor, index)}
            </label>
            <div id="${analysisId}"></div>
            ${AppState.multiSource ? 
                `
                <div id="concentration-reader-section-source-${index}">
                    Concentration from source-${index + 1} sample is 
                    <input type="number" id="con-value-read-source-${index}" 
                        value="" min=0 style="width: 5em;"> </input> ng/µL
                </div>
                <div id="derived-concentration-section-source-${index}" class="hidden">
                    Concentration derived from the source-${index + 1} is <span id="der-con-value-source-${index}" class="der-con-value" tabindex="-1"></span> ng/µL
                </div>
                `
                : ``}
            <canvas id="${canvasId}"></canvas>
        </div>
    ` : 
    `
        <div id="${sectionId}">
            <div id="${analysisId}"></div>
            <canvas id="${canvasId}"></canvas>
        </div>
    `;
}

function handleFullDisplayChange(checkbox, fullDisplayId, quantityId, canvasId, allXColumn, allYColumnOrArray, labelOrLabels, unit, timeUnit, conversionFactor, forThisBlankType, selectColor, index) {
    const fullDisplayCheckbox = document.getElementById(fullDisplayId);
    const quantityContainer = document.getElementById(`quantity-checkboxes-${quantityId}`);
    
    if (!fullDisplayCheckbox || !quantityContainer) return;

    // Toggle hidden class
    if (fullDisplayCheckbox.checked) {
        quantityContainer.classList.remove("hidden");
    } else {
        quantityContainer.classList.add("hidden");
    }

    // Call generateChart with updated state
    handleCkboxChange(
        checkbox,
        canvasId,
        allXColumn,
        allYColumnOrArray,
        labelOrLabels,
        unit,
        timeUnit,
        conversionFactor,
        forThisBlankType,
        selectColor,
        index
    );
}

function renderCharts(allXColumn, allYColumnOrArray, labelOrLabels, unit, timeUnit, conversionFactor, analysisOrArray, forThisBlankType = false, selectColor = null, index = null) {
    const $container = $("#chart-container");

    if (AppState.multiSource) {
        if ($("#split-sensor").is(":checked")) {
            // One section per source
            $container.append(
                createChartSection({
                    sectionId: `source-chart-${index}-section`,
                    analysisId: `source-${index}-analysis`,
                    canvasId: `source-${index}-canvas`,
                    quantityId: `source-${index}`,
                    fullDisplayId: `full-display-source-${index}`,
                    allXColumn: allXColumn,
                    allYColumnOrArray: allYColumnOrArray,
                    labelOrLabels: labelOrLabels,
                    unit: unit,
                    timeUnit: timeUnit,
                    conversionFactor: conversionFactor,
                    analysisOrArray: analysisOrArray,
                    forThisBlankType: forThisBlankType,
                    selectColor: selectColor,
                    index: index
                })
            );
        } else {
            // Single mixed plot
            $container.append(`
                <label id="quantity-checkboxes-plot" class="hidden">
                    <h3>Quantities to display on graphic</h3>
                    ${checkboxHtmlWithID("plot", "plot-canvas", allXColumn, allYColumnOrArray, labelOrLabels, unit, timeUnit, conversionFactor, analysisOrArray, forThisBlankType, selectColor, index)}
                </label>
                <div id="plot-chart-section">
                    <div id="plot-analysis"></div>
                    <canvas id="plot-canvas"></canvas>
                </div>
            `);
        }
    } else {
        if ($("#split-mode").is(":checked")) {
            // Blanked and non-blanked sections
            $container.append(
                createChartSection({
                    sectionId: "blanked-chart-section",
                    analysisId: "blanked-analysis",
                    canvasId: "blanked-canvas",
                    quantityId: "blanked",
                    fullDisplayId: "full-display-blanked",
                    allXColumn: allXColumn[0],
                    allYColumnOrArray: allYColumnOrArray[0],
                    labelOrLabels: labelOrLabels[0],
                    unit: unit,
                    timeUnit: timeUnit,
                    conversionFactor: conversionFactor,
                    analysisOrArray: analysisOrArray[0],
                    forThisBlankType: forThisBlankType[0],
                    selectColor: selectColor[0],
                    index: index
                })
            );
            $container.append(
                createChartSection({
                    sectionId: "non-blanked-chart-section",
                    analysisId: "non-blanked-analysis",
                    canvasId: "non-blanked-canvas",
                    quantityId: "non-blanked",
                    fullDisplayId: "full-display-non-blanked",
                    allXColumn: allXColumn[1],
                    allYColumnOrArray: allYColumnOrArray[1],
                    labelOrLabels: labelOrLabels[1],
                    unit: unit,
                    timeUnit: timeUnit,
                    conversionFactor: conversionFactor,
                    analysisOrArray: analysisOrArray[1],
                    forThisBlankType: forThisBlankType[1],
                    selectColor: selectColor[1],
                    index: index
                })
            );
        } else {
            // Single mixed plot
            $container.append(
                createChartSection({
                    sectionId: "plot-chart-section",
                    analysisId: "plot-analysis",
                    canvasId: "plot-canvas",
                    quantityId: "plot",
                    fullDisplayId: "full-display-plot",
                    allXColumn: allXColumn,
                    allYColumnOrArray: allYColumnOrArray,
                    labelOrLabels: labelOrLabels,
                    unit: unit,
                    timeUnit: timeUnit,
                    conversionFactor: conversionFactor,
                    analysisOrArray: analysisOrArray,
                    forThisBlankType: forThisBlankType,
                    selectColor: selectColor,
                    index: index
                })
            );
        }
    }
}

function updatePlot(
    data, metadata, range, timeUnit, window_size, unit, isSplitMode,
    isFullDisplay = false, forBlankType = null,
    XColumn = "Timestamp", YColumn = "Value"
) {
    // Save current scroll position
    const chartContainer = document.getElementById('chart-container');
    const scrollPosition = chartContainer.scrollTop;

    destroyCharts();
    $("#chart-container").empty(); // Clear existing chart sections

    // Restore scroll position
    chartContainer.scrollTop = scrollPosition;

    // Clean and sort data
    const selectElement = document.getElementById('regressed-quantity');
    const calParams = Array.from(selectElement.options).map(option => option.dataset.original);
    const rawData = data;
    data = preprocessData(data, XColumn, YColumn);

    const conversionFactor = getTimeUnitMultiplier('seconds') / getTimeUnitMultiplier(timeUnit);
    
    // Only check for blank columns if multiSource is false
    const hasBlankType = !AppState.multiSource && data.some(row => 'BlankType' in row);
    const hasBlank = !AppState.multiSource && data.some(row => 'Blanked' in row);

    if (!AppState.multiSource && !hasBlankType && !hasBlank) {
        console.warn("No Blank or BlankType column found in data");
        return;
    }

    // If multiSource, treat all data as mixed; otherwise, use getDataGroups
    const allGroups = AppState.multiSource 
        ? {
            allXColumn: extractColumn(data, XColumn),
            allYColumn: Array.isArray(YColumn) ? YColumn.map(y => extractColumn(data, y)) : [extractColumn(data, YColumn)],
            allMixedData: data
        }
        : getDataGroups(data, hasBlankType, XColumn, YColumn);
    const allXColumn = allGroups.allXColumn;
    const allYColumns = Array.isArray(YColumn) ? YColumn.map(y => extractColumn(data, y)) : [extractColumn(data, YColumn)];
    
    // Only define blanked/non-blanked data if multiSource is false
    let allBlankedXColumn, allBlankedYColumns, allNonBlankedXColumn, allNonBlankedYColumns;
    if (!AppState.multiSource) {
        allBlankedXColumn = extractColumn(allGroups.allBlankedData, XColumn);
        allBlankedYColumns = Array.isArray(YColumn) ? YColumn.map(y => extractColumn(allGroups.allBlankedData, y)) : [extractColumn(allGroups.allBlankedData, YColumn)];
        allNonBlankedXColumn = extractColumn(allGroups.allNonBlankedData, XColumn);
        allNonBlankedYColumns = Array.isArray(YColumn) ? YColumn.map(y => extractColumn(allGroups.allNonBlankedData, y)) : [extractColumn(allGroups.allNonBlankedData, YColumn)];
    }

    let filteredData, XColumnVals, YColumnVals;
    if (AppState.currentMeasurementMode !== "calibrate") {
        if (isFullDisplay) range = Number.MAX_VALUE;
        const timeThreshold = Math.max(...allXColumn) - range * getTimeUnitMultiplier(timeUnit);

        filteredData = AppState.multiSource 
            ? data 
            : filterByTime(data, timeThreshold, hasBlankType);
        
        if (filteredData.length === 0) {
            console.warn("No data after filtering with threshold:", timeThreshold);
            return;
        }

        XColumnVals = extractAndConvert(filteredData, XColumn, conversionFactor);
        YColumnVals = Array.isArray(YColumn) ? YColumn.map(y => extractColumn(filteredData, y)) : [extractColumn(filteredData, YColumn)];
    } else {
        filteredData = AppState.multiSource 
            ? data 
            : filterByBlankType(data, hasBlankType);
        XColumnVals = extractColumn(filteredData, XColumn);
        YColumnVals = Array.isArray(YColumn) ? YColumn.map(y => extractColumn(filteredData, y)) : [extractColumn(filteredData, YColumn)];
    }

    const measurementLabel = determineMeasurementLabel(metadata, XColumn, YColumn);

    const calMode = $("#cal-mode-select").val();
    const isCalKinetics = AppState.currentMeasurementMode === "calibrate" && calMode === "kinetics";
    const isCalPoint = AppState.currentMeasurementMode === "calibrate" && calMode === "point";
    const regressAlgo = $("#exp-json-regress-algo").val();

    const labels = Array.isArray(YColumn) 
        ? YColumn.map(y => `${measurementLabel} ${y} ${unitDisplay(unit)}`) 
        : [`${measurementLabel} ${unitDisplay(unit)}`];

    if (AppState.multiSource) {
        if (isSplitMode) {
            // Handle multiSource with isSplitMode=true: create a chart for each source
            const charts = [];
            const analyses = [];
            
            for (let i = 0; i < AppState.numSources; i++) {
                const yColumn = YColumn[i];
                const yValues = extractColumn(filteredData, yColumn);
                const label = `${measurementLabel} ${yColumn} ${unitDisplay(unit)}`;
                let analysis = null;

                if (AppState.currentMeasurementMode !== "calibrate") {
                    analysis = calculateKineticsQuantities(XColumnVals, yValues, window_size);
                } else {
                    if (isCalKinetics) {
                        analysis = calibrateKineticsAnalysis(rawData, XColumn, yColumn, calParams, "MIXED", calculateCoefAndRSquared, regressAlgo);
                    } else if (isCalPoint) {
                        analysis = calculateCoefAndRSquared(yValues, XColumnVals, regressAlgo);
                    }
                }

                analyses.push(analysis);

                const canvasId = `source-${i}-canvas`;
                const analysisId = `source-${i}-analysis`;
                renderCharts(XColumnVals, yValues, label, unit, timeUnit, conversionFactor, analysis, true, i, i);
                const chart = generateChart(canvasId, XColumnVals, [yValues], [label], unit, timeUnit, conversionFactor, [analysis], true, i, i);
                charts.push(chart);

                // Update analysis info display
                const analysisInfo = formatAnalysisInfo(analysis, conversionFactor, unit, label);
                $("#" + analysisId).html(formatAnalysisHtml(analysisInfo, unit, timeUnit, AppState.plotColors[i % AppState.plotColors.length], `Source ${i + 1}`));
            }

            AppState.sourceCharts = charts;

            if (AppState.currentMeasurementMode !== "calibrate") {
                return extractMultiSourceResultSummary(metadata, analyses);
            } else {
                return {
                    analysis: analyses,
                    meas: metadata["Measurement"]
                };
            }
        } else {
            // Handle multiSource with isSplitMode=false: plot all sources in a single chart
            let analyses = [];
            if (AppState.currentMeasurementMode !== "calibrate") {
                analyses = YColumn.map(yCol => calculateKineticsQuantities(XColumnVals, extractColumn(filteredData, yCol), window_size));
            } else {
                if (isCalKinetics) {
                    analyses = YColumn.map(yCol => calibrateKineticsAnalysis(rawData, XColumn, yCol, calParams, "MIXED", calculateCoefAndRSquared, regressAlgo));
                } else if (isCalPoint) {
                    analyses = YColumn.map(yCol => calculateCoefAndRSquared(extractColumn(filteredData, yCol), XColumnVals, regressAlgo));
                }
            }

            // Format analysis info for all sources
            const analysisInfo = analyses.map((a, i) => formatAnalysisInfo(a, conversionFactor, unit, labels[i]));

            // Generate single chart with all Y-columns
            renderCharts(XColumnVals, YColumnVals, labels, unit, timeUnit, conversionFactor, analyses, true);
            // Update analysis info display
            if (AppState.currentMeasurementMode !== "calibrate") {
                let html = '';
                analysisInfo.forEach((info, i) => {
                    html += formatAnalysisHtml(info, unit, timeUnit, AppState.plotColors[i % AppState.plotColors.length], `Source ${i + 1}`);
                    html += `
                        <div id="concentration-reader-section-source-${i}">
                            Concentration from source-${i + 1} sample is <input type="number" id="con-value-read-source-${i}" value="" min=0 style="width: 5em;"> </input> ng/µL
                        </div>
                        <div id="derived-concentration-section-source-${i}" class="hidden">
                            Concentration derived from the source-${i + 1} is <span id="der-con-value-source-${i}" class="der-con-value" tabindex="-1"></span> ng/µL
                        </div>
                    `
                    if (i < analysisInfo.length - 1) html += '<br/>';
                });
                $("#plot-analysis").html(html);
            } else {
                let htmlString = "";
                if (isCalKinetics) {
                    htmlString = getCalKineticsString(YColumn, analyses, regressAlgo === "Michaelis-Menten");
                } else {
                    htmlString = analyses.map(a => getCalPointString(a)).join('<br/>');
                }
                $("#plot-analysis").html(htmlString);
            }
            $("#plot-canvas").show();
            AppState.myChart = generateChart('plot-canvas', XColumnVals, YColumnVals, labels, unit, timeUnit, conversionFactor, analyses, true);

            if (AppState.currentMeasurementMode !== "calibrate") {
                return extractMultiSourceResultSummary(metadata, analyses);
            } else {
                return {
                    analysis: analyses,
                    meas: metadata["Measurement"]
                };
            }
        }
    } else {
        // Original non-multiSource logic
        if (isSplitMode) {
            const blankedData = filterBlankedData(filteredData, hasBlankType, true);
            const nonBlankedData = filterBlankedData(filteredData, hasBlankType, false);

            const blankedX = extractAndConvert(blankedData, XColumn, conversionFactor);
            const blankedY = Array.isArray(YColumn) ? YColumn.map(y => extractColumn(blankedData, y)) : [extractColumn(blankedData, YColumn)];
            const nonBlankedX = extractAndConvert(nonBlankedData, XColumn, conversionFactor);
            const nonBlankedY = Array.isArray(YColumn) ? YColumn.map(y => extractColumn(nonBlankedData, y)) : [extractColumn(nonBlankedData, YColumn)];

            let analysis_blanked = null;
            let analysis_nonblanked = null;

            if (AppState.currentMeasurementMode !== "calibrate") {
                analysis_blanked = allBlankedYColumns.map((yCol, i) => calculateKineticsQuantities(allBlankedXColumn, yCol, window_size));
                analysis_nonblanked = allNonBlankedYColumns.map((yCol, i) => calculateKineticsQuantities(allNonBlankedXColumn, yCol, window_size));
            } else {
                if (isCalKinetics) {
                    analysis_blanked = calibrateKineticsAnalysis(rawData, XColumn, YColumn, calParams, "BLANKED", calculateCoefAndRSquared, regressAlgo);
                    analysis_nonblanked = calibrateKineticsAnalysis(rawData, XColumn, YColumn, calParams, "NON-BLANKED", calculateCoefAndRSquared, regressAlgo);
                } else {
                    analysis_blanked = calculateCoefAndRSquared(allBlankedYColumns[0], allBlankedXColumn, regressAlgo);
                    analysis_nonblanked = calculateCoefAndRSquared(allNonBlankedYColumns[0], allNonBlankedXColumn, regressAlgo);
                }
            }

            const blankLabels = labels.map(l => `${l} (Blanked)`);
            const nonBlankLabels = labels.map(l => `${l} (Non-Blanked)`);
            renderCharts([blankedX, nonBlankedX], [blankedY, nonBlankedY], [blankLabels, nonBlankLabels], unit, timeUnit, conversionFactor, [analysis_blanked, analysis_nonblanked], [forBlankType === "BLANKED", forBlankType === "NON-BLANKED"], [1, 0])
            $("#blanked-canvas, #non-blanked-canvas").show();
            AppState.blankedChart = generateChart('blanked-canvas', blankedX, blankedY, blankLabels,
                unit, timeUnit, conversionFactor, analysis_blanked, forBlankType === "BLANKED", selectColor = 1);
            AppState.nonBlankedChart = generateChart('non-blanked-canvas', nonBlankedX, nonBlankedY, nonBlankLabels,
                unit, timeUnit, conversionFactor, analysis_nonblanked, forBlankType === "NON-BLANKED", selectColor = 0);

            // Format analysis info for both charts
            const blankedAnalysisInfo = Array.isArray(analysis_blanked) ? analysis_blanked.map((a, i) => formatAnalysisInfo(a, conversionFactor, unit, blankLabels[i])) : [formatAnalysisInfo(analysis_blanked, conversionFactor, unit, blankLabels[0])];
            const nonBlankedAnalysisInfo = Array.isArray(analysis_nonblanked) ? analysis_nonblanked.map((a, i) => formatAnalysisInfo(a, conversionFactor, unit, nonBlankLabels[i])) : [formatAnalysisInfo(analysis_nonblanked, conversionFactor, unit, nonBlankLabels[0])];

            // Update analysis info display
            if (AppState.currentMeasurementMode !== "calibrate") {
                updateSplitModeAnalysisInfo(blankedAnalysisInfo, nonBlankedAnalysisInfo, unit, timeUnit);
            } else {
                let blanked_string = "";
                let non_blanked_string = "";
                if (isCalKinetics) {
                    blanked_string = getCalKineticsString(calParams, analysis_blanked, $("#exp-json-regress-algo").val() === "Michaelis-Menten");
                    non_blanked_string = getCalKineticsString(calParams, analysis_nonblanked, $("#exp-json-regress-algo").val() === "Michaelis-Menten");
                } else if (isCalPoint) {
                    blanked_string = getCalPointString(analysis_blanked);
                    non_blanked_string = getCalPointString(analysis_nonblanked);
                }
                $("#blanked-analysis").html(
                    `<span style="color: rgb(255, 99, 132);">Blanked: ${blanked_string}</span>`
                );
                $("#non-blanked-analysis").html(
                    `<span style="color: rgb(75, 192, 192);">Non-Blanked: ${non_blanked_string}</span>`
                );
            }

            if (AppState.currentMeasurementMode !== "calibrate") {
                return extractSplitResultSummary(metadata, analysis_blanked[0], analysis_nonblanked[0]);
            } else {
                const analysis = $("#exp-json-blank-type").val() === "BLANKED" ? analysis_blanked : analysis_nonblanked;
                return {
                    analysis,
                    meas: metadata["Measurement"]
                };
            }
        } else {
            let mixAnalysis = null;
            if (AppState.currentMeasurementMode !== "calibrate") {
                mixAnalysis = allYColumns.map(yCol => calculateKineticsQuantities(allXColumn, yCol, window_size));
            } else {
                if (isCalKinetics) {
                    mixAnalysis = calibrateKineticsAnalysis(rawData, XColumn, YColumn, calParams, "MIXED", calculateCoefAndRSquared, regressAlgo);
                } else if (isCalPoint) {
                    mixAnalysis = calculateCoefAndRSquared(extractColumn(allGroups.allMixedData, YColumn), extractColumn(allGroups.allMixedData, XColumn), regressAlgo);
                }
            }

            // Format analysis info before chart creation
            const mixAnalysisInfo = Array.isArray(mixAnalysis) ? mixAnalysis.map((a, i) => formatAnalysisInfo(a, conversionFactor, unit, labels[i])) : [formatAnalysisInfo(mixAnalysis, conversionFactor, unit, labels[0])];

            // Generate chart
            const yValsForChart = Array.isArray(YColumnVals) ? YColumnVals : [YColumnVals];
            renderCharts(XColumnVals, yValsForChart, labels,
                unit, timeUnit, conversionFactor, mixAnalysis, forBlankType === "MIXED");
            $("#plot-canvas").show();
            AppState.myChart = generateChart('plot-canvas', XColumnVals, yValsForChart, labels,
                unit, timeUnit, conversionFactor, mixAnalysis, forBlankType === "MIXED");

            // Update analysis info display
            if (AppState.currentMeasurementMode !== "calibrate") {
                updateSingleModeAnalysisInfo(mixAnalysisInfo, unit, timeUnit);
            } else {
                let htmlString = "";
                if (isCalKinetics) {
                    htmlString = getCalKineticsString(calParams, mixAnalysis, $("#exp-json-regress-algo").val() === "Michaelis-Menten");
                } else {
                    htmlString = getCalPointString(mixAnalysis);
                }
                $("#plot-analysis").html(htmlString);
            }

            if (AppState.currentMeasurementMode !== "calibrate") {
                return extractSingleResultSummary(metadata, mixAnalysis[0]);
            } else {
                return {
                    analysis: mixAnalysis,
                    meas: metadata["Measurement"]
                };
            }
        }
    }

    setTimeout(() => {
        chartContainer.scrollTop = scrollPosition;
    }, 0);
}

// New helper function for multiSource result summary
function extractMultiSourceResultSummary(metadata, analyses) {
    const summary = {
        split: true,
        sources: [],
        meas: metadata["Measurement"],
        meas_unit: metadata["Unit"]
    };

    analyses.forEach((analysis, i) => {
        summary.sources.push({
            source: `Value:${i + 1}`,
            maxrate: analysis.maxRate,
            slope: analysis.slope,
            sat: analysis.saturationValue,
            time_to_sat: analysis.timeToSaturation
        });
    });

    return summary;
}

// Modified destroyCharts to handle multiSource charts
function destroyCharts() {
    if (AppState.myChart) {
        AppState.myChart.destroy();
        AppState.myChart = null;
    }
    if (AppState.blankedChart) {
        AppState.blankedChart.destroy();
        AppState.blankedChart = null;
    }
    if (AppState.nonBlankedChart) {
        AppState.nonBlankedChart.destroy();
        AppState.nonBlankedChart = null;
    }
    if (AppState.sourceCharts) {
        AppState.sourceCharts.forEach(chart => {
            if (chart) chart.destroy();
        });
        AppState.sourceCharts = [];
    }
    // Clear all chart instances
    Object.values(AppState.chartInstances).forEach(chart => {
        if (chart) chart.destroy();
    });
    AppState.chartInstances = {};
}

function getCalKineticsString(calParams, analysis, isMM=false) {
    let htmlString = "";
    for (let i = 0; i < calParams.length; i++) {
        let coefString = "";
        if (analysis[i].coefficients) {
            if (!isMM) {
                coefString += "[a = ";
            } else {
                coefString += "[V_max = ";
            }
            for (let j = 0; j < analysis[i].coefficients.length; j++) {
                coefString += analysis[i].coefficients[j] ? Number(analysis[i].coefficients[j]).toFixed(5) : "--";
                if (j < analysis[i].coefficients.length - 1) 
                    if (!isMM) {
                        if (j === 0) {
                            coefString += ", b = ";
                        } else {
                            coefString += ", c = ";
                        }
                    } else {
                        coefString += ", Km = ";
                    }
                else coefString += "], ";  
            } 
        }    
        htmlString += `${calParams[i]}: Coef:` + coefString;
        htmlString += "rSquared: ";
        htmlString += analysis[i].rSquared ? analysis[i].rSquared : "--,";
        htmlString += "<br/>";      
    }
    return htmlString;
}

function getCalPointString(analysis) {
    let htmlString = "Coef:";
    if (analysis.coefficients) {
        htmlString += "[";
        for (let j = 0; j < analysis.coefficients.length; j++) {
            htmlString += analysis.coefficients[j] ? Number(analysis.coefficients[j]).toFixed(5) : "--";
            if (j < analysis.coefficients.length - 1) 
                htmlString += ",";
        }
        htmlString += "], ";
    } 
    htmlString += "rSquared: ";
    htmlString += analysis.rSquared ? analysis.rSquared : "--";
    htmlString += "<br/>";
    return htmlString;
}

function preprocessData(data, XColumn, YColumn) {
    const isMultipleY = Array.isArray(YColumn);
    if (isMultipleY) {
        return data
            .filter(row => 
                row[XColumn] !== "NONE" && 
                YColumn.every(yCol => row[yCol] !== "NONE")
            )
            .sort((a, b) => a[XColumn] - b[XColumn]);
    } else {
        return data
            .filter(row => 
                row[XColumn] !== "NONE" && 
                row[YColumn] !== "NONE"
            )
            .sort((a, b) => a[XColumn] - b[XColumn]);
    }
}

function preprocessDataCalParams(data, XColumn, YColumn, calParams) {
    if (calParams && Array.isArray(calParams) && calParams.includes(YColumn)) {
        const results = calParams.map(param => {
            const filteredData = data
                .filter(row => row[XColumn] !== "NONE" && row[param] !== "NONE")
                .sort((a, b) => a[XColumn] - b[XColumn]);
            return { param, data: filteredData };
        });
        return results;
    }
}

function extractColumn(data, colName) {
    return data.map(row => row[colName]);
}

function extractAndConvert(data, colName, factor) {
    return data.map(row => Number((row[colName] * factor).toFixed(2)));
}

function getDataGroups(data, hasBlankType, XColumn, YColumn) {
    return {
        allXColumn: extractColumn(data, XColumn),
        allYColumn: extractColumn(data, YColumn),
        allBlankedData: filterBlankedData(data, hasBlankType, true),
        allNonBlankedData: filterBlankedData(data, hasBlankType, false),
        allMixedData: (!hasBlankType) ? data : data.filter(row => row["BlankType"] === "MIXED")
    };
}

function determineMeasurementLabel(metadata, XColumn, YColumn) {
    if (AppState.currentMeasurementMode !== "calibrate") {
        return 'Measurement' in metadata ? metadata['Measurement'] : 'Measurement';
    } else {
        return 'MeasMode' in metadata ? `${YColumn} against ${XColumn}` : 'Correlation';
    }
}

function unitDisplay(unit) {
    return unit !== "NONE" ? `(${unit})` : "";
}

function filterByBlankType(data, hasBlankType) {
    if (!hasBlankType) return data;
    return data.filter(row =>
        row['BlankType'] === "BLANKED" || row['BlankType'] === "NON-BLANKED" || row['BlankType'] === "MIXED"
    );
}

function filterBlankedData(data, hasBlankType, isBlanked) {
    if (hasBlankType) {
        return data.filter(row =>
            isBlanked ? row['BlankType'] === "BLANKED" : row['BlankType'] === "NON-BLANKED"
        );
    } else {
        return data.filter(row =>
            isBlanked ? row['Blanked'] === true || row['Blanked'] === 1
                      : row['Blanked'] === false || row['Blanked'] === 0
        );
    }
}

function filterByTime(data, timeThreshold, hasBlankType, XColumn = "Timestamp") {
    return data.filter(row =>
        row[XColumn] >= timeThreshold &&
        !hasBlankType
    );
}

function formatAnalysisHtml(analysisInfo, unit, timeUnit, color = null, label = '') {
    if (!analysisInfo) return '';
    const unitDisplay = unit !== "NONE" ? unit : '';
    const displaySat = (!isNaN(analysisInfo.saturationValue)) ? analysisInfo.saturationValue : "--";
    const displayTimeSat = (!isNaN(analysisInfo.timeToSaturation)) ? analysisInfo.timeToSaturation : "--";
    const html = `<span ${color ? `style="color: ${color};"` : ''}>
        ${label ? `${label}: ` : ''}Slope = ${analysisInfo.slope}${unitDisplay}/${timeUnit.slice(0, -1)}, 
        Linear start = ${analysisInfo.linearStart} ${timeUnit.slice(0, -1)},
        Linear end = ${analysisInfo.linearEnd} ${timeUnit.slice(0, -1)}, <br/>
        maxRate = ${analysisInfo.maxRate}${unitDisplay}/${timeUnit.slice(0, -1)}, 
        maxRateStart = ${analysisInfo.maxRateStart} ${timeUnit.slice(0, -1)}, 
        maxRateEnd = ${analysisInfo.maxRateEnd} ${timeUnit.slice(0, -1)}, <br/>
        Saturation = ${displaySat}${unitDisplay}, 
        Time to Saturation = ${displayTimeSat} ${timeUnit.slice(0, -1)}
    </span>`;
    return html;
}

function updateSplitModeAnalysisInfo(blankedAnalysisInfo, nonBlankedAnalysisInfo, unit, timeUnit) {
    let html_blank = '';
    let html_nonblank = '';
    if (blankedAnalysisInfo) {
        html_blank += formatAnalysisHtml(blankedAnalysisInfo[0], unit, timeUnit, 'rgb(255, 99, 132)', 'Blanked');
    }
    if (nonBlankedAnalysisInfo) {
        html_nonblank += formatAnalysisHtml(nonBlankedAnalysisInfo[0], unit, timeUnit, 'rgb(75, 192, 192)', 'Non-Blanked');
    }
    $("#blanked-analysis").html(html_blank || '');
    $("#non-blanked-analysis").html(html_nonblank || '');
}

function extractSplitResultSummary(metadata, analysis_blanked, analysis_nonblanked) {
    return {
        split: true,
        maxrate_blanked: analysis_blanked.maxRate,
        slope_blanked: analysis_blanked.slope,
        sat_blanked: analysis_blanked.saturationValue,
        time_to_sat_blanked: analysis_blanked.timeToSaturation,
        maxrate_non_blanked: analysis_nonblanked.maxRate,
        slope_non_blanked: analysis_nonblanked.slope,
        sat_non_blanked: analysis_nonblanked.saturationValue,
        time_to_sat_non_blanked: analysis_nonblanked.timeToSaturation,
        meas: metadata["Measurement"],
        meas_unit: metadata["Unit"]
    };
}

function updateSingleModeAnalysisInfo(analysisInfo, unit, timeUnit) {
    if (analysisInfo) {
        $("#plot-analysis").html(formatAnalysisHtml(analysisInfo[0], unit, timeUnit));
    } else {
        $("#plot-analysis").html('');
    }
}

function extractSingleResultSummary(metadata, mixAnalysis) {
    return {
        split: false,
        maxrate: mixAnalysis.maxRate,
        slope: mixAnalysis.slope,
        sat: mixAnalysis.saturationValue,
        time_to_sat: mixAnalysis.timeToSaturation,
        meas: metadata["Measurement"],
        meas_unit: metadata["Unit"]
    };
}

function calibrateKineticsAnalysis(data, XColumn, YColumn, calParams, blankTypeValue, calculateCoefAndRSquared, regressAlgo) {
    const dataMap = preprocessDataCalParams(data, XColumn, YColumn, calParams);
    if (dataMap) {
        const results = dataMap.map(({ param, data }) => {
            const filteredData = data.filter(row => row['BlankType'] === blankTypeValue && row[param] !== "NONE");
            const xValues = filteredData.map(row => row[XColumn]);
            const yValues = filteredData.map(row => row[param]);
            const result = calculateCoefAndRSquared(yValues, xValues, regressAlgo);
            return result;
        });
        return results;
    }
    const filteredData = data
        .filter(row => row[XColumn] !== "NONE" && row[YColumn] !== "NONE" && row['BlankType'] === blankTypeValue)
        .sort((a, b) => a[XColumn] - b[XColumn]);
    const xValues = filteredData.map(row => row[XColumn]);
    const yValues = filteredData.map(row => row[YColumn]);
    const result = calculateCoefAndRSquared(yValues, xValues, regressAlgo);
    return result;
}

function getRegressionData(xMax, xMin, analysisArray, numDiv = 100) {
    let regressionData = [];
    let analysis = null;
    if ($("#cal-mode-select").val() === "kinetics") {
        const selectElement = document.getElementById('regressed-quantity');
        const calParams = Array.from(selectElement.options).map(option => option.value);
        const currQuantity = selectElement.value;
        analysis = analysisArray[calParams.indexOf(currQuantity)];
    } else 
        analysis = analysisArray;

    if (AppState.currentMeasurementMode === "calibrate" && analysis && analysis.coefficients && numDiv > 0) {
        const step = (xMax - xMin) / (numDiv - 1);
        const regressAlgo = $("#exp-json-regress-algo").val();

        for (let i = 0; i < numDiv; i++) {
            const x = xMin + i * step;
            let y = 0;

            switch (regressAlgo) {
                case "linear": {
                    const [ a, b ] = analysis.coefficients;
                    y = a !== 0 ? (x - b) / a : 0;
                    break;
                }
                case "polynomial": {
                    const [c_0, c_1, c_2] = analysis.coefficients;
                    if (c_2 === 0) {
                        y = c_1 !== 0 ? (x - c_0) / c_1 : 0;
                    } else {
                        const discriminant = c_1 * c_1 - 4 * c_2 * (c_0 - x);
                        if (discriminant >= 0) {
                            y = (-c_1 + Math.sqrt(discriminant)) / (2 * c_2);
                        } else {
                            y = 0;
                        }
                    }
                    break;
                }
                case "logarithmic": {
                    const [ a, b, c ] = analysis.coefficients;
                    y = a !== 0 ? Math.exp((x - c) / a) - b : 0;
                    break;
                }
                case "exponential": {
                    const [ a, b, c ] = analysis.coefficients;
                    y = (a !== 0 && x > c && b != 0) ? Math.log((x - c) / a)/b : 0;
                    break;
                }
                case "Michaelis-Menten": {
                    const [ Vmax, Km ] = analysis.coefficients;
                    y = (Vmax * x)/ (Km + x);
                    break;
                }
                default:
                    y = 0;
            }
            regressionData.push({ x, y });
        }
    }
    return regressionData;
}