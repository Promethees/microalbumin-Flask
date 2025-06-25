function createChart(canvasId, allXColumn, allYColumn, label, unit, timeUnit, range, conversionFactor, analysis, isFullDisplay, refCalPoint = null, forThisBlankType = false) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    if (!ctx || allXColumn.length === 0 || allYColumn.length === 0) {
        console.error("Invalid chart data or context:", { canvasId, allXColumn, allYColumn });
        return null;
    }

    let chartScaleConstant = 1;
    let adjustedSlope = null;
    let adjustedLinearStart = null;
    let adjustedLinearEnd = null;
    let adjustedVmax = null;
    let adjustedVmaxStart = null;
    let adjustedVmaxEnd = null;
    let adjustedTimeToSaturationDisplay = null;
    let adjustedSaturationValue = null;

    if (analysis) {
        adjustedSlope = analysis.slope ? (parseFloat(analysis.slope) / conversionFactor).toFixed(4) : "--";
        adjustedLinearStart = analysis.linearXMin ? (parseFloat(analysis.linearXMin) * conversionFactor).toFixed(2) : "--";
        adjustedLinearEnd = analysis.linearXMax ? (parseFloat(analysis.linearXMax) * conversionFactor).toFixed(2) : "--";
        adjustedVmax = parseFloat(analysis.Vmax) / conversionFactor;
        adjustedVmaxStart = analysis.startVMax ? (parseFloat(analysis.startVMax) * conversionFactor).toFixed(2) : "--";
        adjustedVmaxEnd = analysis.endVMax ? (parseFloat(analysis.endVMax) * conversionFactor).toFixed(2) : "--";
        adjustedTimeToSaturationDisplay = (analysis.timeToSaturation !== null) ? (parseFloat(analysis.timeToSaturation) * conversionFactor).toFixed(2) : "--";
        adjustedSaturationValue = (analysis.timeToSaturation !== null) ? parseFloat(analysis.saturationValue).toFixed(3) : "--";
        adjustedVmax = (3600 * adjustedVmax).toFixed(5) !== "0.00000" ? adjustedVmax.toFixed(5) : "--";
    }

    const { XColumn, YColumn } = averageDuplicates(allXColumn, allYColumn);

    // Handle single data point edge case
    const isSinglePoint = XColumn.length === 1 && YColumn.length === 1;
    const chartType = isSinglePoint ? 'scatter' : 'line'; // Use scatter for single point
    const xMin = isSinglePoint ? XColumn[0] - 1 : Math.min(...XColumn); // Arbitrary range for single point
    const xMax = isSinglePoint ? XColumn[0] + 1 : Math.max(...XColumn);
    const yMin = 0;
    const yMax = isSinglePoint ? YColumn[0] * 1.1 : Math.max(...YColumn) * 1.1;

    // Calculate stepSize safely
    const xStepSize = isSinglePoint
        ? 0.5 // Arbitrary step size for single point
        : Number((xMax - xMin) / (XColumn.length - 1)).toFixed(2) || 1; // Fallback to 1 if NaN
    const yStepSize = isSinglePoint
        ? Number(YColumn[0] / 10).toFixed(2) || 0.1 // Fallback for single point
        : Number((yMax - yMin) / 10).toFixed(2) || 0.1; // Fallback to 0.1 if NaN

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
                pointRadius: isSinglePoint ? 5 : 3 // Larger point for scatter
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
                                type: 'line', // Use horizontal line for single point
                                borderColor: 'rgba(255, 0, 0, 0.5)',
                                borderWidth: 3,
                                xMin: parseFloat(refCalPoint),
                                xMax: parseFloat(refCalPoint),
                                yMin: 0,
                                yMax: yMax,
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

    if (analysis) {
        chart.data.datasets[0].analysis = {
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
    return chart;
}

function updatePlot(data, range, timeUnit, window_size, unit, isSplitMode, isFullDisplay=false, refCalPoint=null, forBlankType=null,
    XColumn = "Timestamp", YColumn = "Value", groupColumn="TimePoint", groupVal=null) {
    destroyCharts();
    $("#plot-canvas, #blanked-canvas, #non-blanked-canvas").hide();
    $("#analysis-info").text("");
    data.sort((a, b) => a[XColumn] - b[XColumn]);
    data = data.filter(row => 
                      row[XColumn] !== "NONE" && 
                      row[YColumn] !== "NONE" && 
                      (!groupVal || parseFloat(row[groupColumn]) === parseFloat(groupVal))
                    );

    const baseMultiplier = getTimeUnitMultiplier('seconds');
    const targetMultiplier = getTimeUnitMultiplier(timeUnit);
    const conversionFactor = baseMultiplier / targetMultiplier;

    // Determine if data has Blank or BlankType column
    const hasBlankType = data.some(row => 'BlankType' in row);
    const hasBlank = data.some(row => 'Blanked' in row);

    // Prepare data based on column type
    let allXColumn, allYColumn, allBlankedData, allNonBlankedData;
    
    if (hasBlankType) {
        allXColumn = data.filter(row => !forBlankType || row['BlankType'] === forBlankType || row['BlankType'] === "MIXED")
                        .map(row => row[XColumn]);
        allYColumn = data.filter(row => !forBlankType || row['BlankType'] === forBlankType || row['BlankType'] === "MIXED")
                        .map(row => row[YColumn]);
        allBlankedData = data.filter(row => row['BlankType'] === "BLANKED");
        allNonBlankedData = data.filter(row => row['BlankType'] === "NON-BLANKED");
    } else if (hasBlank) {
        allXColumn = data.map(row => row[XColumn]);
        allYColumn = data.map(row => row[YColumn]);
        allBlankedData = data.filter(row => row['Blanked'] === true || row['Blanked'] === 1);
        allNonBlankedData = data.filter(row => row['Blanked'] === false || row['Blanked'] === 0);
    } else {
        console.warn("No Blank or BlankType column found in data");
        return;
    }

    const allBlankedXColumn = allBlankedData.map(row => row[XColumn]);
    const allBlankedYColumn = allBlankedData.map(row => row[YColumn]);
    const allNonBlankedXColumn = allNonBlankedData.map(row => row[XColumn]);
    const allNonBlankedYColumn = allNonBlankedData.map(row => row[YColumn]);

    let filteredData = null;
    let XColumnVals = null;
    let YColumnVals = null;

    if (currentMeasurementMode !== "calibrate") {
        if (isFullDisplay === true) {
            range = Number.MAX_VALUE;
        }
        const rangeInSeconds = range * getTimeUnitMultiplier(timeUnit);
        const mostRecentTime = Math.max(...allXColumn);
        const timeThreshold = mostRecentTime - rangeInSeconds;
        
        filteredData = hasBlankType 
            ? data.filter(row => row[XColumn] >= timeThreshold && 
                           (!forBlankType || row['BlankType'] === forBlankType || row['BlankType'] === "MIXED"))
            : data.filter(row => row[XColumn] >= timeThreshold);
            
        if (filteredData.length === 0) {
            console.warn("No data after filtering with threshold:", timeThreshold);
            return;
        }
        XColumnVals = filteredData.map(row => Number((row[XColumn] * conversionFactor).toFixed(2)));
        YColumnVals = filteredData.map(row => row[YColumn]);
    } else {
        filteredData = hasBlankType 
            ? data.filter(row => !forBlankType || row['BlankType'] === forBlankType || row['BlankType'] === "MIXED")
            : data;
        XColumnVals = allXColumn;
        YColumnVals = allYColumn;
    }

    let measurementLabel = null;
    if (currentMeasurementMode !== "calibrate") {
        measurementLabel = filteredData.length > 0 && 'Measurement' in filteredData[0] 
            ? filteredData[0]['Measurement'] 
            : 'Measurement';
    } else {
        measurementLabel = filteredData.length > 0 && 'Concentration' in filteredData[0]
            ? `${YColumn} against ${XColumn}`
            : 'Correlation';
    }

    if (isSplitMode) {
        const blankedData = hasBlankType 
            ? filteredData.filter(row => row['BlankType'] === "BLANKED")
            : filteredData.filter(row => row['Blanked'] === true || row['Blanked'] === 1);
        const nonBlankedData = hasBlankType 
            ? filteredData.filter(row => row['BlankType'] === "NON-BLANKED")
            : filteredData.filter(row => row['Blanked'] === false || row['Blanked'] === 0);

        const blankedXColumn = blankedData.map(row => Number((row[XColumn] * conversionFactor).toFixed(2)));
        const blankedYColumn = blankedData.map(row => row[YColumn]);
        const nonBlankedXColumn = nonBlankedData.map(row => Number((row[XColumn] * conversionFactor).toFixed(2)));
        const nonBlankedYColumn = nonBlankedData.map(row => row[YColumn]);

        let analysis_blanked = null;
        let analysis_nonblanked = null;
        if (currentMeasurementMode !== "calibrate") {
            analysis_blanked = calculateKineticsQuantities(allBlankedXColumn, allBlankedYColumn, window_size);
            analysis_nonblanked = calculateKineticsQuantities(allNonBlankedXColumn, allNonBlankedYColumn, window_size);
        }

        $("#blanked-canvas, #non-blanked-canvas").show();
        blankedChart = createChart(
            'blanked-canvas',
            blankedXColumn,
            blankedYColumn,
            `${measurementLabel} (Blanked) ${unit !== "NONE" ? `(${unit})` : ""}`,
            unit,
            timeUnit,
            range,
            conversionFactor,
            analysis_blanked,
            isFullDisplay,
            refCalPoint,
            (forBlankType === "BLANKED")
        );
        nonBlankedChart = createChart(
            'non-blanked-canvas',
            nonBlankedXColumn,
            nonBlankedYColumn,
            `${measurementLabel} (Non-Blanked) ${unit !== "NONE" ? `(${unit})` : ""}`,
            unit,
            timeUnit,
            range,
            conversionFactor,
            analysis_nonblanked,
            isFullDisplay,
            refCalPoint,
            (forBlankType === "NON-BLANKED")
        );

        if (currentMeasurementMode !== "calibrate") {
            $("#analysis-info").html(
                `<span style="color: rgb(255, 99, 132);">
                Blanked: Slope = ${blankedChart?.data.datasets[0].analysis.slope} ${unit !== "NONE" ? unit : ''}/${timeUnit}, 
                Linear start = ${blankedChart?.data.datasets[0].analysis.linearStart} ${timeUnit},
                Linear end = ${blankedChart?.data.datasets[0].analysis.linearEnd} ${timeUnit}, <br/>
                Vmax = ${blankedChart?.data.datasets[0].analysis.Vmax}${unit !== "NONE" ? unit : ''}/${timeUnit}, 
                VmaxStart = ${blankedChart?.data.datasets[0].analysis.VmaxStart} ${timeUnit}, 
                VmaxEnd = ${blankedChart?.data.datasets[0].analysis.VmaxEnd} ${timeUnit}, <br/>
                Saturation = ${blankedChart?.data.datasets[0].analysis.saturationValue}, 
                Time to Saturation = ${blankedChart?.data.datasets[0].analysis.timeToSaturation} ${timeUnit}<br> </span>` +
                `<span style="color: rgb(75, 192, 192);">
                Non-Blanked: Slope = ${nonBlankedChart?.data.datasets[0].analysis.slope} ${unit !== "NONE" ? unit : ''}/${timeUnit}, 
                Linear start = ${nonBlankedChart?.data.datasets[0].analysis.linearStart} ${timeUnit},
                Linear end = ${nonBlankedChart?.data.datasets[0].analysis.linearEnd} ${timeUnit}, <br/>
                Vmax = ${nonBlankedChart?.data.datasets[0].analysis.Vmax}${unit !== "NONE" ? unit : ''}/${timeUnit}, 
                VmaxStart = ${nonBlankedChart?.data.datasets[0].analysis.VmaxStart} ${timeUnit}, 
                VmaxEnd = ${nonBlankedChart?.data.datasets[0].analysis.VmaxEnd} ${timeUnit}, <br/>
                Saturation = ${nonBlankedChart?.data.datasets[0].analysis.saturationValue}, 
                Time to Saturation = ${nonBlankedChart?.data.datasets[0].analysis.timeToSaturation} ${timeUnit} </span>`
            );
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
            }
        } else {
            $("#analysis-info").addClass("hidden");
            return null;
        }
    } else {
        let mixAnalysis = null;
        if (currentMeasurementMode !== "calibrate") {
            mixAnalysis = calculateKineticsQuantities(allXColumn, allYColumn, window_size);
        }
        $("#plot-canvas").show();
        myChart = createChart(
            'plot-canvas',
            XColumnVals,
            YColumnVals,
            `${measurementLabel} ${unit !== "NONE" ? `(${unit})` : ""}`,
            unit,
            timeUnit,
            range,
            conversionFactor,
            mixAnalysis,
            isFullDisplay,
            refCalPoint,
            (forBlankType === "MIXED")
        );
        if (currentMeasurementMode !== "calibrate") {
            const analysisDisplay = myChart?.data.datasets[0].analysis;
            $("#analysis-info").html(
                `Slope = ${analysisDisplay.slope} ${unit !== "NONE" ? unit : ''}/${timeUnit},  
                Linear start = ${analysisDisplay.linearStart} ${timeUnit},
                Linear end = ${analysisDisplay.linearEnd} ${timeUnit}, <br/>
                Vmax = ${analysisDisplay.Vmax}${unit !== "NONE" ? unit : ''}/${timeUnit}, 
                VmaxStart = ${analysisDisplay.VmaxStart} ${timeUnit}, 
                VmaxEnd = ${analysisDisplay.VmaxEnd} ${timeUnit}, <br/>
                Saturation = ${analysisDisplay.saturationValue}, 
                Time to Saturation = ${analysisDisplay.timeToSaturation} ${timeUnit}`
            );
            return {
                split: false,
                vmax: mixAnalysis.Vmax,
                slope: mixAnalysis.slope,
                sat: mixAnalysis.saturationValue,
                time_to_sat: mixAnalysis.timeToSaturation,
                meas: data[0]["Measurement"],
                meas_unit: data[0]["Unit"]
            }
        } else {
            $("#analysis-info").addClass("hidden");
            return null;
        }
    }
}