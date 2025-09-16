// Generates the Chart.js chart and returns the chart object
function generateChart(canvasId, allXColumn, allYColumnOrArray, labelOrLabels, unit, timeUnit, conversionFactor, analysisOrArray, isFullDisplay, forThisBlankType = false, selectColor = null) {
    const canvas = document.getElementById(canvasId);
    const maxrate_chkbox = document.getElementById('maxrate');
    const slope_chkbox = document.getElementById('slope');
    const sat_chkbox = document.getElementById('sat');
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
    const analyses = Array.isArray(analysisOrArray) ? analysisOrArray : [analysisOrArray];

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
            borderColor: selectColor ? AppState.plotColors[selectColor % AppState.plotColors.length] : AppState.plotColors[i % AppState.plotColors.length],
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
        if (AppState.currentMeasurementMode === "calibrate" && analysis && analysis.coefficients) {
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
                    title: { display: true, text: timeUnit ? `Time (${timeUnit})` : 'Concentration (ng/µL)',
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
                    title: { display: true, text: unit !== "NONE" ? unit : '',
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
                    text: 'Display selected CSV Content',
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
                                yMin: yMin, // Use updated yMin
                                yMax: yMax, // Use updated yMax
                                label: {
                                    display: true,
                                    content: 'RefCal',
                                    position: 'middle'
                                }
                            }
                        }),
                        ...(isFullDisplay && maxrate_chkbox.checked && AppState.currentMeasurementMode === "kinetics" && analysisForAnnotations?.startMaxRate && !isSinglePoint && {
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
                        ...(isFullDisplay && slope_chkbox.checked && AppState.currentMeasurementMode === "kinetics" && analysisForAnnotations?.linearXMin && !isSinglePoint && {
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
                        ...(isFullDisplay && sat_chkbox.checked && AppState.currentMeasurementMode === "kinetics" && analysisForAnnotations?.saturationValue !== "--" && !isSinglePoint && {
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

// Updates the plot with data, supporting multiple Y-columns and bypassing blanked data when multiSource is true
function updatePlot(
    data, metadata, range, timeUnit, window_size, unit, isSplitMode,
    isFullDisplay = false, forBlankType = null,
    XColumn = "Timestamp", YColumn = "Value"
) {
    // Save current scroll position
    const chartContainer = document.getElementById('chart-container');
    const scrollPosition = chartContainer.scrollTop;

    destroyCharts();
    $("#plot-canvas, #blanked-canvas, #non-blanked-canvas").hide();
    $("#mix-analysis").text("");
    $("#blank-analysis").text("");
    $("#non-blank-analysis").text("");

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

    // Skip split mode if multiSource is true
    if (!AppState.multiSource && isSplitMode) {
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
                analysis_blanked = allBlankedYColumns.map(yCol => calculateCoefAndRSquared(yCol, allBlankedXColumn, regressAlgo));
                analysis_nonblanked = allNonBlankedYColumns.map(yCol => calculateCoefAndRSquared(yCol, allNonBlankedXColumn, regressAlgo));
            }
        }

        const blankLabels = labels.map(l => `${l} (Blanked)`);
        const nonBlankLabels = labels.map(l => `${l} (Non-Blanked)`);

        $("#blanked-canvas, #non-blanked-canvas").show();
        AppState.blankedChart = generateChart('blanked-canvas', blankedX, blankedY, blankLabels,
            unit, timeUnit, conversionFactor, analysis_blanked, isFullDisplay, forBlankType === "BLANKED", selectColor = 1);
        AppState.nonBlankedChart = generateChart('non-blanked-canvas', nonBlankedX, nonBlankedY, nonBlankLabels,
            unit, timeUnit, conversionFactor, analysis_nonblanked, isFullDisplay, forBlankType === "NON-BLANKED", selectColor = 0);

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
            $("#blank-analysis").html(
                `<span style="color: rgb(255, 99, 132);">Blanked: ${blanked_string}</span>`
            );
            $("#non-blank-analysis").html(
                `<span style="color: rgb(75, 192, 192);">Non-Blanked: ${non_blanked_string}</span>`
            );
        }

        if (AppState.currentMeasurementMode !== "calibrate") {
            return extractSplitResultSummary(data, analysis_blanked, analysis_nonblanked);
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
                const mixedX = extractColumn(allGroups.allMixedData, XColumn);
                mixAnalysis = allYColumns.map(yCol => calculateCoefAndRSquared(yCol, mixedX, regressAlgo));
            }
        }

        // Format analysis info before chart creation
        const mixAnalysisInfo = Array.isArray(mixAnalysis) ? mixAnalysis.map((a, i) => formatAnalysisInfo(a, conversionFactor, unit, labels[i])) : [formatAnalysisInfo(mixAnalysis, conversionFactor, unit, labels[0])];

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
            $("#mix-analysis").html(htmlString);
        }

        // Generate chart
        $("#plot-canvas").show();
        const yValsForChart = Array.isArray(YColumnVals) ? YColumnVals : [YColumnVals];
        AppState.myChart = generateChart('plot-canvas', XColumnVals, yValsForChart, labels,
            unit, timeUnit, conversionFactor, mixAnalysis, isFullDisplay, AppState.multiSource ? true : forBlankType === "MIXED");

        if (AppState.currentMeasurementMode !== "calibrate") {
            return extractSingleResultSummary(metadata, mixAnalysis);
        } else {
            return {
                analysis: mixAnalysis,
                meas: metadata["Measurement"]
            };
        }
    }

    setTimeout(() => {
        chartContainer.scrollTop = scrollPosition;
    }, 0);
}


// Helper Functions
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
    // Determine if YColumn is an array
    const isMultipleY = Array.isArray(YColumn);
    
    // Process data with original YColumn(s)
    if (isMultipleY) {
        // For multiple Y columns, ensure XColumn and all YColumns are not "NONE"
        return data
            .filter(row => 
                row[XColumn] !== "NONE" && 
                YColumn.every(yCol => row[yCol] !== "NONE")
            )
            .sort((a, b) => a[XColumn] - b[XColumn]);
    } else {
        // For single Y column, original logic
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
        // Store results for each calParams element
        const results = calParams.map(param => {
            const filteredData = data
                .filter(row => row[XColumn] !== "NONE" && row[param] !== "NONE")
                .sort((a, b) => a[XColumn] - b[XColumn]);
            return { param, data: filteredData };
        });
        
        return results; // Return array of { param, data }
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

// New helper to format analysis metrics into HTML
function formatAnalysisHtml(analysisInfo, unit, timeUnit, color = null, label = '') {
    if (!analysisInfo) return '';
    // console.log("Formatting analysis info:", analysisInfo);
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

// Modified to accept analysis info directly
function updateSplitModeAnalysisInfo(blankedAnalysisInfo, nonBlankedAnalysisInfo, unit, timeUnit) {
    let html_blank = '';
    let html_nonblank = '';
    if (blankedAnalysisInfo) {
        html_blank += formatAnalysisHtml(blankedAnalysisInfo, unit, timeUnit, 'rgb(255, 99, 132)', 'Blanked');
    }
    if (nonBlankedAnalysisInfo) {
        html_nonblank += formatAnalysisHtml(nonBlankedAnalysisInfo, unit, timeUnit, 'rgb(75, 192, 192)', 'Non-Blanked');
    }
    $("#blank-analysis").html(html_blank || '');
    $("#non-blank-analysis").html(html_nonblank || '');
}

// Preserved as-is
function extractSplitResultSummary(data, analysis_blanked, analysis_nonblanked) {
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

// Modified to accept analysis info directly
function updateSingleModeAnalysisInfo(analysisInfo, unit, timeUnit) {
    if (analysisInfo) {
        $("#mix-analysis").html(formatAnalysisHtml(analysisInfo, unit, timeUnit));
    } else {
        $("#mix-analysis").html('');
    }
}

// Preserved as-is
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
}

function calibrateKineticsAnalysis(data, XColumn, YColumn, calParams, blankTypeValue, calculateCoefAndRSquared, regressAlgo) {
    // Get preprocessed data
    const dataMap = preprocessDataCalParams(data, XColumn, YColumn, calParams);
    
    // If dataMap is defined (i.e., YColumn is in calParams), process each param
    if (dataMap) {
        const results = dataMap.map(({ param, data }) => {
            // Filter data for rows where BlankType === blankTypeValue and param is not "NONE"
            const filteredData = data.filter(row => row['BlankType'] === blankTypeValue && row[param] !== "NONE");
            
            // Extract XColumn and param values
            const xValues = filteredData.map(row => row[XColumn]);
            const yValues = filteredData.map(row => row[param]);
            
            // Call calculateCoefAndRSquared with extracted values
            const result = calculateCoefAndRSquared(yValues, xValues, regressAlgo);
            
            return result ;
        });
        
        return results; // Return array of { param, result }
    }
    // Fallback: Process with original YColumn
    const filteredData = data
        .filter(row => row[XColumn] !== "NONE" && row[YColumn] !== "NONE" && row['BlankType'] === blankTypeValue)
        .sort((a, b) => a[XColumn] - b[XColumn]);
    const xValues = filteredData.map(row => row[XColumn]);
    const yValues = filteredData.map(row => row[YColumn]);
    const result = calculateCoefAndRSquared(yValues, xValues, regressAlgo);
    
    return  result ;
}

// Helper function to derive data for regression line 
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
        const step = (xMax - xMin) / (numDiv - 1); // 100 points including start and end
        const regressAlgo = $("#exp-json-regress-algo").val();

        for (let i = 0; i < numDiv; i++) {
            const x = xMin + i * step;
            let y = 0;

            switch (regressAlgo) {
                case "linear": {
                    // Original: x = a * y + b => y = (x - b) / a
                    const [ a, b ] = analysis.coefficients;
                    y = a !== 0 ? (x - b) / a : 0; // Avoid division by zero
                    break;
                }

                case "polynomial": {
                    // Original: x = c_0 + c_1*y + c_2*y^2
                    // Rewrite: c_2*y^2 + c_1*y + (c_0 - x) = 0
                    // Solve for y using quadratic formula: y = (-c_1 ± √(c_1^2 - 4*c_2*(c_0 - x))) / (2*c_2)
                    const [c_0, c_1, c_2] = analysis.coefficients; // Degree 2 polynomial: c_0 + c_1*y + c_2*y^2
                    if (c_2 === 0) {
                        // Degenerate case: linear equation
                        y = c_1 !== 0 ? (x - c_0) / c_1 : 0; // Avoid division by zero
                    } else {
                        const discriminant = c_1 * c_1 - 4 * c_2 * (c_0 - x);
                        if (discriminant >= 0) {
                            // Use the positive root (or adjust based on context)
                            y = (-c_1 + Math.sqrt(discriminant)) / (2 * c_2);
                            // If negative root is needed, use: y = (-c_1 - Math.sqrt(discriminant)) / (2 * c_2)
                        } else {
                            y = 0; // Handle invalid discriminant (no real roots)
                        }
                    }
                    break;
                }

                case "logarithmic": {
                    // Original: x = a * ln(y + b) + c => y = exp((x - c) / a) - b
                    const [ a, b, c ] = analysis.coefficients;
                    y = a !== 0 ? Math.exp((x - c) / a) - b : 0; // Avoid division by zero
                    break;
                }

                case "exponential": {
                    // Original: x = a * exp(y * b) + c => y = ln((x - c) / a)/b
                    const [ a, b, c ] = analysis.coefficients;
                    y = (a !== 0 && x > c && b != 0) ? Math.log((x - c) / a)/b : 0; // Ensure valid domain
                    break;
                }

                case "Michaelis-Menten":
                    // Original: x = (Km * y) / (Vmax - y) => y = (Vmax * x) / (Km + x)
                    const [ Vmax, Km ] = analysis.coefficients;
                    y = (Vmax * x)/ (Km + x);
                    break;

                default:
                    y = 0;
            }

            regressionData.push({ x, y });
        }
    }
    return regressionData;
}
