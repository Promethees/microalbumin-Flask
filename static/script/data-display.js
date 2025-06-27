// Generates the Chart.js chart and returns the chart object
function generateChart(canvasId, allXColumn, allYColumn, label, unit, timeUnit, range, conversionFactor, analysis, isFullDisplay, refCalPoint = null, forThisBlankType = false) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    if (!ctx || allXColumn.length === 0 || allYColumn.length === 0) {
        $(`#${canvasId}`).hide();
        return null;
    }
    $(`#${canvasId}`).show();

    const { XColumn, YColumn } = averageDuplicates(allXColumn, allYColumn);

    // Handle single data point edge case
    const isSinglePoint = XColumn.length === 1 && YColumn.length === 1;
    const chartType = isSinglePoint ? 'scatter' : 'line';
    const xMin = isSinglePoint ? XColumn[0] - 1 : Math.min(...XColumn);
    const xMax = isSinglePoint ? XColumn[0] + 1 : Math.max(...XColumn);

    // Check if all Y values are equal
    const allYEqual = YColumn.every(y => y === YColumn[0]);
    let yMin, yMax, yStepSize;

    if (allYEqual) {
        // Case: All Y values are equal
        const yValue = YColumn[0];
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
        yMax = isSinglePoint ? YColumn[0] * 1.1 : Math.max(...YColumn) * 1.1;
        yStepSize = isSinglePoint
            ? Number(YColumn[0] / 10).toFixed(3) || 0.1
            : Number((yMax - yMin) / 10).toFixed(3) || 0.1;
    }

    // Calculate xStepSize safely
    const xStepSize = isSinglePoint
        ? 0.5
        : Number((xMax - xMin) / (XColumn.length - 1)).toFixed(2) || 1;

    let chart = new Chart(ctx, {
        type: chartType,
        data: {
            labels: XColumn,
            datasets: [{
                label: label,
                data: YColumn,
                borderColor: canvasId === 'blanked-canvas' ? 'rgb(255, 99, 132)' : 'rgb(75, 192, 192)',
                tension: isSinglePoint ? 0 : 0.1, // No tension for scatter
                fill: false,
                pointRadius: isSinglePoint || allYEqual ? 5 : 3 // Larger points for single or equal Y values
            }]
        },
        options: {
            animation: false,
            scales: {
                x: {
                    type: 'linear',
                    title: { display: true, text: timeUnit ? `Time (${timeUnit})` : 'Concentration (nM/l)' },
                    min: xMin,
                    max: xMax,
                    ticks: {
                        stepSize: xStepSize,
                        callback: function(value) {
                            return Number(value).toFixed(2);
                        }
                    }
                },
                y: {
                    type: 'linear',
                    title: { display: true, text: unit !== "NONE" ? unit : '' },
                    min: yMin,
                    max: yMax,
                    ticks: {
                        stepSize: yStepSize,
                        callback: function(value) {
                            return Number(value).toFixed(3);
                        }
                    }
                }
            },
            plugins: {
                annotation: {
                    annotations: {
                        ...(isFullDisplay && currentMeasurementMode === "point" && forThisBlankType && {
                            refCalLine: {
                                type: 'line',
                                borderColor: 'rgba(255, 0, 0, 0.5)',
                                borderWidth: 3,
                                xMin: parseFloat(refCalPoint),
                                xMax: parseFloat(refCalPoint),
                                yMin: yMin, // Use updated yMin
                                yMax: yMax, // Use updated yMax
                                label: {
                                    display: true,
                                    content: 'RefCal',
                                    position: 'start'
                                }
                            }
                        }),
                        ...(isFullDisplay && currentMeasurementMode === "kinetics" && analysis.startVMax && !isSinglePoint && {
                            VMaxLine: {
                                type: 'line',
                                borderColor: 'rgba(255, 0, 0, 0.5)',
                                borderWidth: 3,
                                xMin: parseFloat(analysis.startVMax * conversionFactor),
                                xMax: parseFloat(analysis.endVMax * conversionFactor),
                                yMin: parseFloat(analysis.yVMaxstart),
                                yMax: parseFloat(analysis.yVMaxend),
                                label: {
                                    display: true,
                                    content: 'VMax',
                                    position: 'start'
                                }
                            }
                        }),
                        ...(isFullDisplay && currentMeasurementMode === "kinetics" && analysis.linearXMin && !isSinglePoint && {
                            regressionLine: {
                                type: 'line',
                                borderColor: 'rgba(0, 0, 255, 0.5)',
                                borderWidth: 3,
                                xMin: parseFloat(analysis.linearXMin * conversionFactor),
                                xMax: parseFloat(analysis.linearXMax * conversionFactor),
                                yMin: parseFloat(analysis.linearYMin),
                                yMax: parseFloat(analysis.linearYMax),
                                label: {
                                    display: true,
                                    content: 'Linear',
                                    position: 'middle'
                                }
                            }
                        }),
                        ...(isFullDisplay && currentMeasurementMode === "kinetics" && analysis.saturationValue !== "--" && !isSinglePoint && {
                            saturationLine: {
                                type: 'line',
                                borderColor: 'rgba(255, 0, 255, 0.5)',
                                borderWidth: 3,
                                xMin: parseFloat(analysis.timeStartSaturation * conversionFactor),
                                xMax: xMax * 100,
                                yMin: parseFloat(analysis.saturationValue),
                                yMax: parseFloat(analysis.saturationValue),
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

    // Attach analysis data to the chart if provided
    if (analysis) {
        chart.data.datasets[0].analysis = formatAnalysisInfo(analysis, conversionFactor, unit, label);
    }

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
    let adjustedVmax = parseFloat(analysis.Vmax) / conversionFactor;
    let adjustedVmaxStart = analysis.startVMax ? (parseFloat(analysis.startVMax) * conversionFactor).toFixed(2) : "--";
    let adjustedVmaxEnd = analysis.endVMax ? (parseFloat(analysis.endVMax) * conversionFactor).toFixed(2) : "--";
    let adjustedTimeToSaturationDisplay = (analysis.timeToSaturation !== null) ? (parseFloat(analysis.timeToSaturation) * conversionFactor).toFixed(2) : "--";
    let adjustedSaturationValue = (analysis.timeToSaturation !== null) ? parseFloat(analysis.saturationValue).toFixed(3) : "--";
    adjustedVmax = (3600 * adjustedVmax).toFixed(5) !== "0.00000" ? adjustedVmax.toFixed(5) : "--";

    return {
        slope: adjustedSlope,
        linearStart: adjustedLinearStart,
        linearEnd: adjustedLinearEnd,
        saturationValue: adjustedSaturationValue,
        timeToSaturation: adjustedTimeToSaturationDisplay,
        Vmax: adjustedVmax,
        VmaxStart: adjustedVmaxStart,
        VmaxEnd: adjustedVmaxEnd,
        MeasUnit: unit,
        Meas: label
    };
}

function updatePlot(
    data, range, timeUnit, window_size, unit, isSplitMode,
    isFullDisplay = false, refCalPoint = null, forBlankType = null,
    XColumn = "Timestamp", YColumn = "Value"
) {
    destroyCharts();
    $("#plot-canvas, #blanked-canvas, #non-blanked-canvas").hide();
    $("#analysis-info").text("");

    // Clean and sort data
    data = preprocessData(data, XColumn, YColumn);

    const conversionFactor = getTimeUnitMultiplier('seconds') / getTimeUnitMultiplier(timeUnit);
    const hasBlankType = data.some(row => 'BlankType' in row);
    const hasBlank = data.some(row => 'Blanked' in row);

    if (!hasBlankType && !hasBlank) {
        console.warn("No Blank or BlankType column found in data");
        return;
    }

    const allGroups = getDataGroups(data, hasBlankType, forBlankType, XColumn, YColumn);
    const { allXColumn, allYColumn, allBlankedData, allNonBlankedData } = allGroups;
    const allBlankedXColumn = extractColumn(allBlankedData, XColumn);
    const allBlankedYColumn = extractColumn(allBlankedData, YColumn);
    const allNonBlankedXColumn = extractColumn(allNonBlankedData, XColumn);
    const allNonBlankedYColumn = extractColumn(allNonBlankedData, YColumn);

    let filteredData, XColumnVals, YColumnVals;
    if (currentMeasurementMode !== "calibrate") {
        if (isFullDisplay) range = Number.MAX_VALUE;
        const timeThreshold = Math.max(...allXColumn) - range * getTimeUnitMultiplier(timeUnit);

        filteredData = filterByTime(data, timeThreshold, forBlankType, hasBlankType);
        if (filteredData.length === 0) {
            console.warn("No data after filtering with threshold:", timeThreshold);
            return;
        }

        XColumnVals = extractAndConvert(filteredData, XColumn, conversionFactor);
        YColumnVals = extractColumn(filteredData, YColumn);
    } else {
        filteredData = filterByBlankType(data, forBlankType, hasBlankType);
        XColumnVals = extractColumn(filteredData, XColumn);
        YColumnVals = extractColumn(filteredData, YColumn);
    }

    const measurementLabel = determineMeasurementLabel(filteredData, XColumn, YColumn);

    const calMode = $("#cal-mode-select").val();
    const isCalKinetics = currentMeasurementMode === "calibrate" && calMode === "kinetics";
    const isCalPoint = currentMeasurementMode === "calibrate" && calMode === "point";
    const regressAlgo = $("#exp-json-regress-algo").val();
    const selectElement = document.getElementById('regressed-quantity');
    const calParams = Array.from(selectElement.options).map(option => option.dataset.original);

    if (isSplitMode) {
        const blankedData = filterBlankedData(filteredData, hasBlankType, true);
        const nonBlankedData = filterBlankedData(filteredData, hasBlankType, false);

        const blankedX = extractAndConvert(blankedData, XColumn, conversionFactor);
        const blankedY = extractColumn(blankedData, YColumn);
        const nonBlankedX = extractAndConvert(nonBlankedData, XColumn, conversionFactor);
        const nonBlankedY = extractColumn(nonBlankedData, YColumn);

        let analysis_blanked = null;
        let analysis_nonblanked = null;

        if (currentMeasurementMode !== "calibrate") {
            analysis_blanked = calculateKineticsQuantities(allBlankedXColumn, allBlankedYColumn, window_size);
            analysis_nonblanked = calculateKineticsQuantities(allNonBlankedXColumn, allNonBlankedYColumn, window_size);
        } else {
            if (isCalKinetics) {
                analysis_blanked = calParams.map(col =>
                    calculateCoefAndRSquared(allBlankedXColumn, extractColumn(allBlankedData, col), regressAlgo)
                );
                analysis_nonblanked = calParams.map(col =>
                    calculateCoefAndRSquared(allNonBlankedXColumn, extractColumn(allNonBlankedData, col), regressAlgo)
                );
            } else {
                analysis_blanked = calculateCoefAndRSquared(allBlankedXColumn, allBlankedYColumn, regressAlgo);
                analysis_nonblanked = calculateCoefAndRSquared(allNonBlankedXColumn, allNonBlankedYColumn, regressAlgo);
            }
        }

        $("#blanked-canvas, #non-blanked-canvas").show();
        blankedChart = generateChart('blanked-canvas', blankedX, blankedY, `${measurementLabel} (Blanked) ${unitDisplay(unit)}`,
            unit, timeUnit, range, conversionFactor, analysis_blanked, isFullDisplay, refCalPoint, forBlankType === "BLANKED");
        nonBlankedChart = generateChart('non-blanked-canvas', nonBlankedX, nonBlankedY, `${measurementLabel} (Non-Blanked) ${unitDisplay(unit)}`,
            unit, timeUnit, range, conversionFactor, analysis_nonblanked, isFullDisplay, refCalPoint, forBlankType === "NON-BLANKED");

        // Format analysis info for both charts
        const blankedAnalysisInfo = formatAnalysisInfo(analysis_blanked, conversionFactor, unit, `${measurementLabel} (Blanked)`);
        const nonBlankedAnalysisInfo = formatAnalysisInfo(analysis_nonblanked, conversionFactor, unit, `${measurementLabel} (Non-Blanked)`);

        // Update analysis info display
        if (currentMeasurementMode !== "calibrate") {
            updateSplitModeAnalysisInfo(blankedAnalysisInfo, nonBlankedAnalysisInfo, unit, timeUnit);
        } else {
            let blanked_string = "";
            let non_blanked_string = "";
            if (isCalKinetics) {
                blanked_string = getCalKineticsString(calParams, analysis_blanked);
                non_blanked_string = getCalKineticsString(calParams, analysis_nonblanked);
            } else if (isCalPoint) {
                blanked_string = getCalPointString(analysis_blanked);
                non_blanked_string = getCalPointString(analysis_nonblanked);
            }
            $("#analysis-info").html(
                `<span style="color: rgb(255, 99, 132);">Blanked: ${blanked_string}</span><br>` +
                `<span style="color: rgb(75, 192, 192);">Non-Blanked: ${non_blanked_string}</span>`
            );
        }

        if (currentMeasurementMode !== "calibrate") {
            return extractSplitResultSummary(data, analysis_blanked, analysis_nonblanked);
        } else {
            const analysis = $("#exp-json-blank-type").val() === "BLANKED" ? analysis_blanked : analysis_nonblanked;
            return {
                analysis,
                meas: data[0]["Measurement"]
            };
        }
    } else {
        let mixAnalysis = null;
        if (currentMeasurementMode !== "calibrate") {
            mixAnalysis = calculateKineticsQuantities(allXColumn, allYColumn, window_size);
        } else {
            if (isCalKinetics) {
                mixAnalysis = calParams.map(col =>
                    calculateCoefAndRSquared(allXColumn, extractColumn(filteredData, col), regressAlgo)
                );
            } else if (isCalPoint) {
                mixAnalysis = calculateCoefAndRSquared(allXColumn, allYColumn, regressAlgo);
            }
        }

        // Format analysis info before chart creation
        const mixAnalysisInfo = formatAnalysisInfo(mixAnalysis, conversionFactor, unit, measurementLabel);

        // Update analysis info display
        if (currentMeasurementMode !== "calibrate") {
            updateSingleModeAnalysisInfo(mixAnalysisInfo, unit, timeUnit);
        } else {
            let htmlString = "";
            if (isCalKinetics) {
                htmlString = getCalKineticsString(calParams, mixAnalysis);
            } else {
                htmlString = getCalPointString(mixAnalysis);
            }
            $("#analysis-info").html(htmlString);
        }

        // Generate chart
        $("#plot-canvas").show();
        const myChart = generateChart('plot-canvas', XColumnVals, YColumnVals, `${measurementLabel} ${unitDisplay(unit)}`,
            unit, timeUnit, range, conversionFactor, mixAnalysis, isFullDisplay, refCalPoint, forBlankType === "MIXED");

        if (currentMeasurementMode !== "calibrate") {
            return extractSingleResultSummary(data, mixAnalysis);
        } else {
            return {
                analysis: mixAnalysis,
                meas: data[0]["Measurement"]
            };
        }
    }
}


// Helper Functions
function getCalKineticsString(calParams, analysis) {
    let htmlString = "";
    for (let i = 0; i < calParams.length; i++) {
        let coefString = "";
        if (analysis[i].coefficients) {
            coefString += "[";
            for (let j = 0; j < analysis[i].coefficients.length; j++) {
                coefString += analysis[i].coefficients[j] ? Number(analysis[i].coefficients[j]).toFixed(5) : "--";
                if (j < analysis[i].coefficients.length - 1) 
                    coefString += ",";
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
    return data
        .filter(row => row[XColumn] !== "NONE" && row[YColumn] !== "NONE")
        .sort((a, b) => a[XColumn] - b[XColumn]);
}

function extractColumn(data, colName) {
    return data.map(row => row[colName]);
}

function extractAndConvert(data, colName, factor) {
    return data.map(row => Number((row[colName] * factor).toFixed(2)));
}

function getDataGroups(data, hasBlankType, forBlankType, XColumn, YColumn) {
    const selected = filterByBlankType(data, forBlankType, hasBlankType);
    return {
        allXColumn: extractColumn(selected, XColumn),
        allYColumn: extractColumn(selected, YColumn),
        allBlankedData: filterBlankedData(data, hasBlankType, true),
        allNonBlankedData: filterBlankedData(data, hasBlankType, false)
    };
}

function determineMeasurementLabel(data, XColumn, YColumn) {
    if (currentMeasurementMode !== "calibrate") {
        return data.length > 0 && 'Measurement' in data[0] ? data[0]['Measurement'] : 'Measurement';
    } else {
        return data.length > 0 && 'Concentration' in data[0] ? `${YColumn} against ${XColumn}` : 'Correlation';
    }
}

function unitDisplay(unit) {
    return unit !== "NONE" ? `(${unit})` : "";
}

function filterByBlankType(data, forBlankType, hasBlankType) {
    if (!hasBlankType) return data;

    return data.filter(row =>
        !forBlankType || row['BlankType'] === forBlankType || row['BlankType'] === "MIXED"
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

function filterByTime(data, timeThreshold, forBlankType, hasBlankType, XColumn = "Timestamp") {
    return data.filter(row =>
        row[XColumn] >= timeThreshold &&
        (!hasBlankType || !forBlankType || row["BlankType"] === forBlankType || row["BlankType"] === "MIXED")
    );
}

// New helper to format analysis metrics into HTML
function formatAnalysisHtml(analysisInfo, unit, timeUnit, color = null, label = '') {
    if (!analysisInfo) return '';

    const unitDisplay = unit !== "NONE" ? unit : '';
    const html = `<span ${color ? `style="color: ${color};"` : ''}>
        ${label ? `${label}: ` : ''}Slope = ${analysisInfo.slope} ${unitDisplay}/${timeUnit}, 
        Linear start = ${analysisInfo.linearStart} ${timeUnit},
        Linear end = ${analysisInfo.linearEnd} ${timeUnit}, <br/>
        Vmax = ${analysisInfo.Vmax}${unitDisplay}/${timeUnit}, 
        VmaxStart = ${analysisInfo.VmaxStart} ${timeUnit}, 
        VmaxEnd = ${analysisInfo.VmaxEnd} ${timeUnit}, <br/>
        Saturation = ${analysisInfo.saturationValue}, 
        Time to Saturation = ${analysisInfo.timeToSaturation} ${timeUnit}
    </span>`;
    return html;
}

// Modified to accept analysis info directly
function updateSplitModeAnalysisInfo(blankedAnalysisInfo, nonBlankedAnalysisInfo, unit, timeUnit) {
    let html = '';
    if (blankedAnalysisInfo) {
        html += formatAnalysisHtml(blankedAnalysisInfo, unit, timeUnit, 'rgb(255, 99, 132)', 'Blanked');
        if (nonBlankedAnalysisInfo) html += '<br>';
    }
    if (nonBlankedAnalysisInfo) {
        html += formatAnalysisHtml(nonBlankedAnalysisInfo, unit, timeUnit, 'rgb(75, 192, 192)', 'Non-Blanked');
    }
    $("#analysis-info").html(html || '');
}

// Preserved as-is
function extractSplitResultSummary(data, analysis_blanked, analysis_nonblanked) {
    return {
        split: true,
        vmax_blanked: analysis_blanked.Vmax,
        slope_blanked: analysis_blanked.slope,
        sat_blanked: analysis_blanked.saturationValue,
        time_to_sat_blanked: analysis_blanked.timeToSaturation,
        vmax_non_blanked: analysis_nonblanked.Vmax,
        slope_non_blanked: analysis_nonblanked.slope,
        sat_non_blanked: analysis_nonblanked.saturationValue,
        time_to_sat_non_blanked: analysis_nonblanked.timeToSaturation,
        meas: data[0]["Measurement"],
        meas_unit: data[0]["Unit"]
    };
}

// Modified to accept analysis info directly
function updateSingleModeAnalysisInfo(analysisInfo, unit, timeUnit) {
    if (analysisInfo) {
        $("#analysis-info").html(formatAnalysisHtml(analysisInfo, unit, timeUnit));
    } else {
        $("#analysis-info").html('');
    }
}

// Preserved as-is
function extractSingleResultSummary(data, mixAnalysis) {
    return {
        split: false,
        vmax: mixAnalysis.Vmax,
        slope: mixAnalysis.slope,
        sat: mixAnalysis.saturationValue,
        time_to_sat: mixAnalysis.timeToSaturation,
        meas: data[0]["Measurement"],
        meas_unit: data[0]["Unit"]
    };
}

function destroyCharts() {
    if (myChart) {
        myChart.destroy();
        myChart = null;
    }
    if (blankedChart) {
        blankedChart.destroy();
        blankedChart = null;
    }
    if (nonBlankedChart) {
        nonBlankedChart.destroy();
        nonBlankedChart = null;
    }
}

