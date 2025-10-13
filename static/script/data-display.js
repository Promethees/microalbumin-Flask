function updatePlot(data, XColumn = "Timestamp", YColumn = "Value") {
    // Save current scroll position
    const chartContainer = document.getElementById('chart-container');
    const scrollPosition = chartContainer.scrollTop;

    destroyCharts();
    while (chartContainer.firstChild) {
        chartContainer.removeChild(chartContainer.firstChild);
    }

    // Restore scroll position
    chartContainer.scrollTop = scrollPosition;

    // Clean and sort data
    const rawData = data;
    data = preprocessData(data, XColumn, YColumn);
    
    const isSplitMode = AppState.multiSource
        ? getBtnChecked("split-sensor")
        : getBtnChecked("split-mode");

    // If multiSource, treat all data as mixed; otherwise, use getDataGroups
    const allGroups = AppState.multiSource 
        ? {
            allXColumn: extractColumnAndConvert(data, XColumn),
            allYColumn: Array.isArray(YColumn) ? YColumn.map(y => extractColumnAndNormalize(data, y)) : [extractColumnAndNormalize(data, YColumn)],
            allMixedData: data
        }
        : getDataGroups(data, XColumn, YColumn);

    if (AppState.multiSource) {
        const Args = [
            allGroups,
            XColumn,
            YColumn
        ]
        return isSplitMode ? splitMultiSourceRoutine(...Args) : groupMultiSourceRoutine(...Args);
    } else {
        // Original non-multiSource logic
        const Args = [
            allGroups,
            XColumn,
            YColumn,
            rawData
        ]
        return isSplitMode ? splitBlankRoutine(...Args) : defaultRoutine(...Args);
    }

    setTimeout(() => {
        chartContainer.scrollTop = scrollPosition;
    }, 0);
}

function formatAnalysisInfo(analysis, label) {
    if (!analysis) {
        return null;
    }
    const conversionFactor = getTimeUnitMultiplier('seconds') / getTimeUnitMultiplier(getTimeUnitValue());

    let chartScaleConstant = 1;
    let adjustedSlope = analysis.slope ? (parseFloat(analysis.slope) / conversionFactor).toFixed(5) : "--";
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
        MeasUnit: getMetaUnit(AppState.metaData),
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
          onchange="handleCkboxChange( 
              '${canvasId}', 
              ${JSON.stringify(allXColumn)}, 
              ${JSON.stringify(allYColumnOrArray)}, 
              '${labelOrLabels}', 
              '${unit}', 
              ${index}
          )">
      <span>${q}</span>
    `)
    .join("");
}

function handleCkboxChange(canvasId, originalAllXColumn, allYColumnOrArray, labelOrLabels, unit, index) {
    // Normalize Y values if normalizeMode is checked
    allYColumnOrArray = getBtnChecked("normalize-mode") ? (Array.isArray(allYColumnOrArray[0])
        ? allYColumnOrArray.map(yCol => yCol.map(value => (value - Math.min(...yCol))))
        : allYColumnOrArray.map(value => (value - Math.min(...allYColumnOrArray))))
        : allYColumnOrArray;

    const factor = getTimeUnitMultiplier('seconds') / getTimeUnitMultiplier(getTimeUnitValue());

    // Apply filtering only when fullDisplay checkbox is checked
    let filteredX = originalAllXColumn;
    let filteredY = allYColumnOrArray;
    if (!getCheckboxes(canvasId).fullDisplay.checked) {
        const startThreshold = getValFloat("range-value-start") / factor;
        const endThreshold = getValFloat("range-value-end") / factor;
        ({ filteredX, filteredY } = filterXYPairs(originalAllXColumn, allYColumnOrArray, startThreshold, endThreshold));
    }

    const displayedAllXColumn = filteredX.map(x => x * factor);

    // Calculate kinetics quantities using filtered data
    const analysis = calculateKineticsQuantities(filteredX, filteredY, getValInt("window-size"));

    // Generate the chart with filtered and converted data
    generateChart(
        canvasId,
        displayedAllXColumn,
        filteredY,
        labelOrLabels,
        unit,
        analysis,
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
    index
}) {
    return AppState.currentMeasurementMode !== "calibrate" ? 
    `
        <div id="${sectionId}">
            <label>
                <input type="checkbox" id="${fullDisplayId}" 
                    onchange="handleFullDisplayChange(
                        '${fullDisplayId}', 
                        '${quantityId}', 
                        '${canvasId}', 
                        ${JSON.stringify(allXColumn)}, 
                        ${JSON.stringify(allYColumnOrArray)}, 
                        '${labelOrLabels}', 
                        '${unit}', 
                        ${index}
                    )"> 
                Full display: See all data and special lines
            </label>
            <label id="quantity-checkboxes-${quantityId}" class="hidden">
                <h3>Quantities to display on graphic</h3>
                ${checkboxHtmlWithID(quantityId, canvasId, allXColumn, allYColumnOrArray, labelOrLabels, unit, index)}
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

function handleFullDisplayChange(fullDisplayId, quantityId, canvasId, allXColumn, allYColumnOrArray, labelOrLabels, unit, index) {
    const fullDisplayCheckbox = document.getElementById(fullDisplayId);
    const quantityContainer = document.getElementById(`quantity-checkboxes-${quantityId}`);
    
    if (!fullDisplayCheckbox || !quantityContainer) return;

    // Toggle hidden class
    if (fullDisplayCheckbox.checked && AppState.currentMeasurementMode === "kinetics") {
        quantityContainer.classList.remove("hidden");
    } else {
        quantityContainer.classList.add("hidden");
    }

    // Call generateChart with updated state
    handleCkboxChange(
        canvasId,
        allXColumn,
        allYColumnOrArray,
        labelOrLabels,
        unit,
        index
    );
}

function renderCharts(allXColumn, allYColumnOrArray, labelOrLabels, unit, index = null) {
    const container = document.getElementById("chart-container");

    // Helper to append HTML or elements cleanly
    const appendHTML = (html) => {
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = html.trim();
        while (tempDiv.firstChild) {
            container.appendChild(tempDiv.firstChild);
        }
    };

    if (AppState.multiSource) {
        if (getBtnChecked("split-sensor")) {
            // One section per source
            const section = createChartSection({
                sectionId: `source-chart-${index}-section`,
                analysisId: `source-${index}-analysis`,
                canvasId: `source-${index}-canvas`,
                quantityId: `source-${index}`,
                fullDisplayId: `full-display-source-${index}`,
                allXColumn: allXColumn,
                allYColumnOrArray: allYColumnOrArray,
                labelOrLabels: labelOrLabels,
                unit: unit,
                index: index
            });
            appendHTML(section);
        } else {
            // Single mixed plot
            const html = `
                <label id="quantity-checkboxes-plot" class="hidden">
                    <h3>Quantities to display on graphic</h3>
                    ${checkboxHtmlWithID("plot", "plot-canvas", allXColumn, allYColumnOrArray, labelOrLabels, unit, index)}
                </label>
                <div id="plot-chart-section">
                    <div id="plot-analysis"></div>
                    <canvas id="plot-canvas"></canvas>
                </div>
            `;
            appendHTML(html);
        }
    } else {
        if (getBtnChecked("split-mode")) {
            // Blanked and non-blanked sections
            const blankedSection = createChartSection({
                sectionId: "blanked-chart-section",
                analysisId: "blanked-analysis",
                canvasId: "blanked-canvas",
                quantityId: "blanked",
                fullDisplayId: "full-display-blanked",
                allXColumn: allXColumn[0],
                allYColumnOrArray: allYColumnOrArray[0],
                labelOrLabels: labelOrLabels[0],
                unit: unit,
                index: index
            });

            const nonBlankedSection = createChartSection({
                sectionId: "non-blanked-chart-section",
                analysisId: "non-blanked-analysis",
                canvasId: "non-blanked-canvas",
                quantityId: "non-blanked",
                fullDisplayId: "full-display-non-blanked",
                allXColumn: allXColumn[1],
                allYColumnOrArray: allYColumnOrArray[1],
                labelOrLabels: labelOrLabels[1],
                unit: unit,
                index: index
            });

            appendHTML(blankedSection);
            appendHTML(nonBlankedSection);
        } else {
            // Single mixed plot
            const plotSection = createChartSection({
                sectionId: "plot-chart-section",
                analysisId: "plot-analysis",
                canvasId: "plot-canvas",
                quantityId: "plot",
                fullDisplayId: "full-display-plot",
                allXColumn: allXColumn,
                allYColumnOrArray: allYColumnOrArray,
                labelOrLabels: labelOrLabels,
                unit: unit,
                index: index
            });
            appendHTML(plotSection);
        }
    }
}

function splitMultiSourceRoutine(allGroups, XColumn, YColumn) {
    const measUnit = getMetaUnit(AppState.metaData);

    const charts = [];
    const analyses = [];
    
    for (let i = 0; i < AppState.numSources; i++) {
        const yColumn = YColumn[i];
        const isFullDisplay = getBtnChecked(`full-display-source-${i}`);
        const filteredData = filteredByRangeValue(isFullDisplay, allGroups.allMixedData, XColumn, yColumn);
        const XColumnVals = extractColumnAndConvert(filteredData, XColumn, true);
        const yValues = extractColumnAndNormalize(filteredData, yColumn);
        const label = `${AppState.metaData['Measurement']} ${yColumn} ${unitDisplay(measUnit)}`;
        let analysis = null;

        analysis = calculateKineticsQuantities(allGroups.allXColumn, allGroups.allYColumn[i], getValInt("window-size"));

        analyses.push(analysis);

        const canvasId = `source-${i}-canvas`;
        const analysisId = `source-${i}-analysis`;
        renderCharts(allGroups.allXColumn, allGroups.allYColumn[i], label, measUnit, i);
        const chart = generateChart(canvasId, XColumnVals, [yValues], [label], measUnit, [analysis], i);
        charts.push(chart);

        // Update analysis info display
        const analysisInfo = formatAnalysisInfo(analysis, label);
        document.getElementById(analysisId).innerHTML = formatAnalysisHtml(analysisInfo, 
                                                                            AppState.plotColors[i % AppState.plotColors.length], 
                                                                            `Source ${i + 1}`
                                                                            );
    }

    AppState.sourceCharts = charts;

    return extractMultiSourceResultSummary(AppState.metaData, analyses);

}

function groupMultiSourceRoutine(allGroups, XColumn, YColumn) {
    const measUnit = getMetaUnit(AppState.metaData);

    const filteredData = filteredByRangeValue(false, allGroups.allMixedData, XColumn, YColumn[0]);
    const XColumnVals = extractColumnAndConvert(filteredData, XColumn, true);
    const YColumnVals = YColumn.map(yCol => extractColumnAndNormalize(filteredData, yCol));
    const analyses = allGroups.allYColumn.map(yCol => calculateKineticsQuantities(allGroups.allXColumn, yCol, getValInt("window-size")));
    const labels = YColumn.map(y => `${AppState.metaData['Measurement']} ${y} ${unitDisplay(measUnit)}`);

    // Format analysis info for all sources
    const analysisInfo = analyses.map((a, i) => formatAnalysisInfo(a, labels[i]));

    // Generate single chart with all Y-columns
    renderCharts(XColumnVals, YColumnVals, labels, measUnit);
    // Update analysis info display
    let html = '';
    analysisInfo.forEach((info, i) => {
        html += formatAnalysisHtml(info, AppState.plotColors[i % AppState.plotColors.length], `Source ${i + 1}`);
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
    document.getElementById("plot-analysis").innerHTML = html;

    AppState.myChart = generateChart('plot-canvas', XColumnVals, YColumnVals, labels, measUnit, analyses);

    if (AppState.currentMeasurementMode !== "calibrate") {
        return extractMultiSourceResultSummary(AppState.metaData, analyses);
    } else {
        return {
            analysis: analyses,
            meas: AppState.metaData["Measurement"]
        };
    }
}

function splitBlankRoutine(allGroups, XColumn, YColumn, rawData) {
    const measUnit = getMetaUnit(AppState.metaData);
    
    const allBlankedXColumn = extractColumnAndConvert(allGroups.allBlankedData, XColumn);
    const allBlankedYColumns = Array.isArray(YColumn) ? YColumn.map(y => extractColumnAndNormalize(allGroups.allBlankedData, y)) : [extractColumnAndNormalize(allGroups.allBlankedData, YColumn)];
    const allNonBlankedXColumn = extractColumnAndConvert(allGroups.allNonBlankedData, XColumn);
    const allNonBlankedYColumns = Array.isArray(YColumn) ? YColumn.map(y => extractColumnAndNormalize(allGroups.allNonBlankedData, y)) : [extractColumnAndNormalize(allGroups.allNonBlankedData, YColumn)];
    
    const isFullDisplayBlanked = AppState.currentMeasurementMode === "calibrate" ? true : getBtnChecked("full-display-blanked");
    const isFullDisplayNonBlanked = AppState.currentMeasurementMode === "calibrate" ? true : getBtnChecked("full-display-non-blanked");
    
    const filteredDataBlanked = filteredByRangeValue(isFullDisplayBlanked, allGroups.allBlankedData, XColumn, YColumn);
    const filteredDataNonBlanked = filteredByRangeValue(isFullDisplayNonBlanked, allGroups.allNonBlankedData, XColumn, YColumn);
    
    const blankedData = filterBlankedData(filteredDataBlanked, true);
    const nonBlankedData = filterBlankedData(filteredDataNonBlanked, false);

    const blankedX = extractColumnAndConvert(blankedData, XColumn, true);
    const blankedY = Array.isArray(YColumn) ? YColumn.map(y => extractColumnAndNormalize(blankedData, y)) : [extractColumnAndNormalize(blankedData, YColumn)];
    const nonBlankedX = extractColumnAndConvert(nonBlankedData, XColumn, true);
    const nonBlankedY = Array.isArray(YColumn) ? YColumn.map(y => extractColumnAndNormalize(nonBlankedData, y)) : [extractColumnAndNormalize(nonBlankedData, YColumn)];

    let analysis_blanked = null;
    let analysis_nonblanked = null;

    if (AppState.currentMeasurementMode !== "calibrate") {
        analysis_blanked = allBlankedYColumns.map((yCol, i) => calculateKineticsQuantities(allBlankedXColumn, yCol, getValInt("window-size")));
        analysis_nonblanked = allNonBlankedYColumns.map((yCol, i) => calculateKineticsQuantities(allNonBlankedXColumn, yCol, getValInt("window-size")));
    } else {
        if (calDiv.getAttribute('data-value') === "kinetics") {
            analysis_blanked = calibrateKineticsAnalysis(rawData, XColumn, YColumn, "BLANKED");
            analysis_nonblanked = calibrateKineticsAnalysis(rawData, XColumn, YColumn, "NON-BLANKED");
        } else if (calDiv.getAttribute('data-value') === "point") {
            analysis_blanked = calculateCoefAndRSquared(allBlankedYColumns[0], allBlankedXColumn, regressAlgo = document.getElementById("exp-json-regress-algo").value);
            analysis_nonblanked = calculateCoefAndRSquared(allNonBlankedYColumns[0], allNonBlankedXColumn, regressAlgo = document.getElementById("exp-json-regress-algo").value);
        }
    }
    const labels = getLabelsFromYColumn(YColumn, determineMeasurementLabel(AppState.metaData, XColumn, YColumn), measUnit);
    const blankLabels = labels.map(l => `${l} (Blanked)`);
    const nonBlankLabels = labels.map(l => `${l} (Non-Blanked)`);
    
    renderCharts([extractColumnAndConvert(allGroups.allBlankedData, XColumn), extractColumnAndConvert(allGroups.allNonBlankedData, XColumn)], 
        [extractColumnAndNormalize(allGroups.allBlankedData, YColumn), extractColumnAndNormalize(allGroups.allNonBlankedData, YColumn)], 
        [blankLabels, nonBlankLabels], 
        measUnit, 
        [1, 0])
    AppState.blankedChart = generateChart('blanked-canvas', blankedX, blankedY, blankLabels,
        measUnit, analysis_blanked, index = 1);
    AppState.nonBlankedChart = generateChart('non-blanked-canvas', nonBlankedX, nonBlankedY, nonBlankLabels,
        measUnit, analysis_nonblanked, index = 0);

    // Update analysis info display
    if (AppState.currentMeasurementMode !== "calibrate") {
        // Format analysis info for both charts
        const blankedAnalysisInfo = Array.isArray(analysis_blanked) ? analysis_blanked.map((a, i) => formatAnalysisInfo(a, blankLabels[i])) : [formatAnalysisInfo(analysis_blanked, blankLabels[0])];
        const nonBlankedAnalysisInfo = Array.isArray(analysis_nonblanked) ? analysis_nonblanked.map((a, i) => formatAnalysisInfo(a, nonBlankLabels[i])) : [formatAnalysisInfo(analysis_nonblanked, nonBlankLabels[0])];
        updateSplitModeAnalysisInfo(blankedAnalysisInfo, nonBlankedAnalysisInfo);
    } else {
        let blanked_string = "";
        let non_blanked_string = "";
        if (calDiv.getAttribute('data-value') === "kinetics") {
            blanked_string = getCalKineticsString(analysis_blanked, document.getElementById("exp-json-regress-algo").value === "Michaelis-Menten");
            non_blanked_string = getCalKineticsString(analysis_nonblanked, document.getElementById("exp-json-regress-algo").value === "Michaelis-Menten");
        } else if (calDiv.getAttribute('data-value') === "point") {
            blanked_string = getCalPointString(analysis_blanked);
            non_blanked_string = getCalPointString(analysis_nonblanked);
        }
        document.getElementById("blanked-analysis").innerHTML = `<span style="color: rgb(255, 99, 132);">Blanked: ${blanked_string}</span>`;
        document.getElementById("non-blanked-analysis").innerHTML = `<span style="color: rgb(75, 192, 192);">Non-Blanked: ${non_blanked_string}</span>`;
    }

    if (AppState.currentMeasurementMode !== "calibrate") {
        return extractSplitResultSummary(AppState.metaData, analysis_blanked[0], analysis_nonblanked[0]);
    } else {
        const analysis = document.getElementById("exp-json-blank-type").value === "BLANKED" ? analysis_blanked : analysis_nonblanked;
        return {
            analysis,
            meas: AppState.metaData["Measurement"]
        };
    }
}

function defaultRoutine(allGroups, XColumn, YColumn, rawData) {
    let mixAnalysis = null;
    let filteredData, XColumnVals, YColumnVals;
    const measUnit = getMetaUnit(AppState.metaData);

    if (AppState.currentMeasurementMode !== "calibrate") {
        filteredData = filteredByRangeValue(getBtnChecked("full-display-plot"), allGroups.allMixedData, XColumn, Array.isArray(YColumn) ? YColumn[0] : YColumn);
        XColumnVals = extractColumnAndConvert(filteredData, XColumn, true);
        YColumnVals = extractColumnAndNormalize(filteredData, YColumn);
        mixAnalysis = calculateKineticsQuantities(allGroups.allXColumn, allGroups.allYColumn, getValInt("window-size"));
    } else {
        filteredData = filterByBlankType(allGroups.allMixedData);
        XColumnVals = extractColumnAndConvert(filteredData, XColumn);
        YColumnVals = Array.isArray(YColumn) ? YColumn.map(y => extractColumnAndNormalize(filteredData, y)) : [extractColumnAndNormalize(filteredData, YColumn)];
        if (calDiv.getAttribute('data-value') === "kinetics") {
            mixAnalysis = calibrateKineticsAnalysis(rawData, XColumn, YColumn, "MIXED");
        } else if (calDiv.getAttribute('data-value') === "point") {
            mixAnalysis = calculateCoefAndRSquared(extractColumnAndNormalize(allGroups.allMixedData, YColumn), extractColumnAndConvert(allGroups.allMixedData, XColumn), regressAlgo = document.getElementById("exp-json-regress-algo").value);
        }
    }

    // Generate chart
    const labels = getLabelsFromYColumn(YColumn, determineMeasurementLabel(AppState.metaData, XColumn, YColumn), measUnit);
    renderCharts(allGroups.allXColumn, allGroups.allYColumn, labels, measUnit);
    AppState.myChart = generateChart('plot-canvas', XColumnVals, YColumnVals, labels, measUnit, mixAnalysis);

    // Update analysis info display
    if (AppState.currentMeasurementMode !== "calibrate") {
        // Format analysis info before chart creation
        const mixAnalysisInfo = formatAnalysisInfo(mixAnalysis, labels[0]);
        updateSingleModeAnalysisInfo(mixAnalysisInfo);
    } else {
        let htmlString = "";
        if (calDiv.getAttribute('data-value') === "kinetics") {
            htmlString = getCalKineticsString(mixAnalysis, document.getElementById("exp-json-regress-algo").value=== "Michaelis-Menten");
        } else if (calDiv.getAttribute('data-value') === "point") {
            htmlString = getCalPointString(mixAnalysis);
        }
        document.getElementById("plot-analysis").innerHTML = htmlString;
    }

    if (AppState.currentMeasurementMode !== "calibrate") {
        return extractSingleResultSummary(AppState.metaData, mixAnalysis);
    } else {
        return {
            analysis: mixAnalysis,
            meas: AppState.metaData["Measurement"]
        };
    }
}

function filteredByRangeValue(isFullDisplay, data, XColumn, YColumn) {
    if (AppState.currentMeasurementMode === "calibrate") {
        return data.filter(row => row[XColumn] !== "NONE" && row[YColumn] !== "NONE");
    }
    else {
        const range = getRangeStartEnd(isFullDisplay);
        const timeThresholdStart = range.start * getTimeUnitMultiplier(getTimeUnitValue());
        const timeThresholdEnd = range.end * getTimeUnitMultiplier(getTimeUnitValue());
        return data.filter(row => row[XColumn] >= timeThresholdStart && row[XColumn] <= timeThresholdEnd && row[YColumn] !== "NONE");
    }
}

function getRangeStartEnd(isFullDisplay) {
    if (isFullDisplay) {
        return { start: 0, end: Number.MAX_VALUE };
    } else {
        return {
            start: getValFloat("range-value-start"),
            end: getValFloat("range-value-end")
        };
    }
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

function formatCoefficient(value) {
    return value ? Number(value).toFixed(5) : "--";
}

function createTableRow(coef, rSquared, expectedLength) {
    // Pad coefficients to expected length with null if necessary
    const paddedCoef = coef && coef.length ? coef : Array(expectedLength).fill(null);
    const coefCells = paddedCoef.map(value => `
        <td class="analysis-cell">${formatCoefficient(value)}</td>
    `).join('');
    return `
        <tr>
            ${coefCells}
            <td class="analysis-cell">${formatCoefficient(rSquared)}</td>
        </tr>
    `;
}

function createTable(coef, rSquared, headers) {
    return `
        <table style="border-collapse: collapse;">
            <tr>
                ${headers.map(header => `
                    <td style="font-weight: bold;" class="analysis-cell">${header}</td>
                `).join('')}
                <td style="font-weight: bold;" class="analysis-cell">rSquared</td>
            </tr>
            ${createTableRow(coef, rSquared, headers.length)}
        </table>
    `;
}

function getCalKineticsString(analysis, isMM = false, analysisId = "cal-kinetics-analysis") {
    if (!analysis || !AppState.quantity_input.quantities) return '';

    const headers = isMM ? ['V_max', 'Km'] : ['a', 'b', 'c'];
    const initDisplay = getBtnChecked("open-all-analysis") ? "block" : "none";

    return AppState.quantity_input.quantities.map((label, i) => {
        const coef = analysis[i]?.coefficients || null;
        const rSquared = analysis[i]?.rSquared || null;
        const showText = 'See kinetics analysis';
        const hideText = 'Hide kinetics analysis';

        return `
            <span>
                ${label ? `${label}: ` : ''}
                ${createToggleButton(analysisId, showText, hideText)}
                <div style="max-height: auto; display: ${initDisplay}; overflow: hidden; transition: max-height 0.3s ease; margin-top: 10px; overflow-x: auto;" class="scrollbar-style">
                    ${createTable(coef, rSquared, headers)}
                </div>
            </span>
            <br/>
        `;
    }).join('');
}

function getCalPointString(analysis, analysisId = "cal-point-analysis") {
    if (!analysis) return '';

    const headers = ['a', 'b', 'c'];
    const coef = analysis.coefficients || null;
    const rSquared = analysis.rSquared || null;
    const showText = 'See point analysis';
    const hideText = 'Hide point analysis';
    const initDisplay = getBtnChecked("open-all-analysis") ? "block" : "none";

    return `
        <span>
            ${createToggleButton(analysisId, showText, hideText)}
            <div style="max-height: auto; display: ${initDisplay}; overflow: hidden; transition: max-height 0.3s ease; margin-top: 10px; overflow-x: auto;" class="scrollbar-style">
                ${createTable(coef, rSquared, headers)}
            </div>
        </span>
        <br/>
    `;
}

function preprocessData(data, XColumn, YColumn) {
    const isMultipleY = Array.isArray(YColumn);
    if (isMultipleY) {
        return data
            .filter(row => 
                row[XColumn] !== "NONE" && 
                YColumn.every(yCol => (row[yCol] !== "NONE" && row[yCol] !== null && row[yCol] !== "OVFL"))
            )
            .sort((a, b) => a[XColumn] - b[XColumn]);
    } else {
        return data
            .filter(row => 
                (row[XColumn] !== "NONE" && 
                row[YColumn] !== "NONE" && row[YColumn] !== null && row[YColumn] !== "OVFL")
            )
            .sort((a, b) => a[XColumn] - b[XColumn]);
    }
}

function preprocessDataCalParams(data, XColumn, YColumn) {
    if (AppState.quantity_input.quantities && Array.isArray(AppState.quantity_input.quantities) && AppState.quantity_input.quantities.includes(YColumn)) {
        const results = AppState.quantity_input.quantities.map(param => {
            const filteredData = data
                .filter(row => row[XColumn] !== "NONE" && row[param] !== "NONE")
                .sort((a, b) => a[XColumn] - b[XColumn]);
            return { param, data: filteredData };
        });
        return results;
    }
}

function extractColumnAndNormalize(data, colName) {
    const columnData = data.map(row => row[colName]);
    const min = Math.min(...columnData);
    const normalizeMode = document.getElementById('normalize-mode');
    const shouldNormalize = normalizeMode.style.display !== 'none' && normalizeMode.checked;
    return shouldNormalize ? columnData.map(value => (value - min)) : columnData;
}

function extractColumnAndConvert(data, colName, convert = false) {
    const factor = getTimeUnitMultiplier('seconds') / getTimeUnitMultiplier(getTimeUnitValue());
    return data.map(row => {
        return convert ? Number((row[colName] * factor)) : Number(row[colName]);
    });
}

function hasBlankType(data) {
    // Only check for blank columns if multiSource is false
    const hasBlankType = !AppState.multiSource && data.some(row => 'BlankType' in row);
    const hasBlank = !AppState.multiSource && data.some(row => 'Blanked' in row);

    if (!AppState.multiSource && !hasBlankType && !hasBlank) {
        console.warn("No Blank or BlankType column found in data");
        return;
    }

    return hasBlankType;
}

function getDataGroups(data, XColumn, YColumn) {
    return {
        allXColumn: extractColumnAndConvert(data, XColumn),
        allYColumn: extractColumnAndNormalize(data, YColumn),
        allBlankedData: filterBlankedData(data, true),
        allNonBlankedData: filterBlankedData(data, false),
        allMixedData: (!hasBlankType(data)) ? data : data.filter(row => row["BlankType"] === "MIXED")
    };
}

function determineMeasurementLabel(metadata, XColumn, YColumn) {
    if (AppState.currentMeasurementMode === "calibrate") {
        return 'MeasMode' in metadata ? `${YColumn} against ${XColumn}` : 'Correlation';
    } else {
        return 'Measurement' in metadata ? metadata['Measurement'] : 'Measurement';
    }
}

function unitDisplay(unit) {
    return unit !== "NONE" ? `(${unit})` : "";
}

function filterByBlankType(data) {
    if (!hasBlankType(data)) return data;
    return data.filter(row =>
        row['BlankType'] === "BLANKED" || row['BlankType'] === "NON-BLANKED" || row['BlankType'] === "MIXED"
    );
}

function filterBlankedData(data, isBlanked) {
    if (hasBlankType(data)) {
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

function createToggleButton(analysisId = "plot-analysis", showText = 'See the analysis', hideText = 'Hide the analysis') {
    const buttonId = analysisId.replace("analysis", "button");
    const allOpen = getBtnChecked("open-all-analysis");
    const initialSymbol = allOpen ? '-' : '+';
    const initialTooltipText = allOpen ? hideText : showText;
    return `
    <div style="position: relative; display: inline-block;">
        <button
            id="${buttonId}"
            title="${initialTooltipText}"
            onclick="
            let contentDiv = this.parentElement.nextElementSibling.nextElementSibling;
            this.innerHTML = this.innerHTML === '+' ? '-' : '+';
            let tooltip = this.nextElementSibling;
            tooltip.innerText = this.innerHTML === '-' ? '${hideText}' : '${showText}';
            this.title = this.innerHTML === '-' ? '${hideText}' : '${showText}';
            if (this.innerHTML === '-') {
                contentDiv.style.display = 'block';
            } else {
                contentDiv.style.display = 'none';
            }
        " style="cursor: pointer; background: #ccc; color: #000; border: none; font-weight: bold; padding: 0; margin: 0; width: 20px; height: 20px; border-radius: 50%; text-align: center; line-height: 20px; font-size: 16px;">${initialSymbol}</button>
        <span class="tooltip" style="position: absolute; top: 50%; left: 100%; margin-left: 5px; padding: 5px 10px; background: #333; color: #fff; border-radius: 4px; opacity: 0; transition: opacity 0.3s ease, transform 0.3s ease; transform: translateY(-50%) translateX(-10px); white-space: nowrap; pointer-events: none; z-index: 10;">${initialTooltipText}</span>
    </div>
    <style>
        button:hover + .tooltip {
            opacity: 1;
            transform: translateY(-50%) translateX(0);
        }
    </style>
    `;
}

function formatAnalysisHtml(analysisInfo, color = null, label = '', analysisId = "plot-analysis") {
    if (!analysisInfo) return '';
    const unitDisplay = getMetaUnit(AppState.metaData) !== "NONE" ? getMetaUnit(AppState.metaData) : '';
    const timeUnit = getTimeUnitValue().slice(0, -1);
    const displaySat = (!isNaN(analysisInfo.saturationValue)) ? analysisInfo.saturationValue : "--";
    const displayTimeSat = (!isNaN(analysisInfo.timeToSaturation)) ? analysisInfo.timeToSaturation : "--";
    const initDisplay = getBtnChecked("open-all-analysis") ? "block" : "none";
    const html = `<span ${color ? `style="color: ${color};"` : ''}>
        ${label ? `${label}: ` : ''}
        ${createToggleButton(analysisId=analysisId)}
        <div style="display: ${initDisplay}; overflow: hidden; transition: max-height 0.3s ease; margin-top: 10px; overflow-x: auto; scrollbar-width:thin;" class="scrollbar-style">
            <table style="border-collapse: collapse;">
                <tr>
                    <td style="font-weight: bold;" class="analysis-cell">Slope</td>
                    <td style="font-weight: bold;" class="analysis-cell">Linear start</td>
                    <td style="font-weight: bold;" class="analysis-cell">Linear end</td>
                    <td style="font-weight: bold;" class="analysis-cell">maxRate</td>
                    <td style="font-weight: bold;" class="analysis-cell">maxRateStart</td>
                    <td style="font-weight: bold;" class="analysis-cell">maxRateEnd</td>
                    <td style="font-weight: bold;" class="analysis-cell">Saturation</td>
                    <td style="font-weight: bold;" class="analysis-cell">Reacting Time taken to Saturation</td>
                </tr>
                <tr>
                    <td class="analysis-cell">${analysisInfo.slope}${unitDisplay}/${timeUnit}</td>
                    <td class="analysis-cell">${analysisInfo.linearStart} ${timeUnit}</td>
                    <td class="analysis-cell">${analysisInfo.linearEnd} ${timeUnit}</td>
                    <td class="analysis-cell">${analysisInfo.maxRate}${unitDisplay}/${timeUnit}</td>
                    <td class="analysis-cell">${analysisInfo.maxRateStart} ${timeUnit}</td>
                    <td class="analysis-cell">${analysisInfo.maxRateEnd} ${timeUnit}</td>
                    <td class="analysis-cell">${displaySat}${unitDisplay}</td>
                    <td class="analysis-cell">${displayTimeSat} ${timeUnit}</td>
                </tr>
            </table>
        </div>
    </span>`;
    return html;
}

function updateSplitModeAnalysisInfo(blankedAnalysisInfo, nonBlankedAnalysisInfo) {
    let html_blank = '';
    let html_nonblank = '';
    if (blankedAnalysisInfo) {
        html_blank += formatAnalysisHtml(blankedAnalysisInfo[0], 'rgb(255, 99, 132)', 'Blanked');
    }
    if (nonBlankedAnalysisInfo) {
        html_nonblank += formatAnalysisHtml(nonBlankedAnalysisInfo[0], 'rgb(75, 192, 192)', 'Non-Blanked');
    }
    document.getElementById("blanked-analysis").innerHTML = html_blank || '';
    document.getElementById("non-blanked-analysis").innerHTML = html_nonblank || '';
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

function updateSingleModeAnalysisInfo(analysisInfo) {
    document.getElementById("plot-analysis").innerHTML = analysisInfo ? formatAnalysisHtml(analysisInfo) : '';
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

function calibrateKineticsAnalysis(data, XColumn, YColumn, blankTypeValue) {
    const dataMap = preprocessDataCalParams(data, XColumn, YColumn);
    const regressAlgo = document.getElementById("exp-json-regress-algo").value;
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
    if (calDiv.getAttribute('data-value') === "kinetics") {
        const selectElement = document.getElementById('regressed-quantity');
        const calParams = Array.from(selectElement.options).map(option => option.value);
        const currQuantity = selectElement.value;
        analysis = analysisArray[calParams.indexOf(currQuantity)];
    } else 
        analysis = analysisArray;

    if (AppState.currentMeasurementMode === "calibrate" && analysis && analysis.coefficients && numDiv > 0) {
        const step = (xMax - xMin) / (numDiv - 1);
        const regressAlgo = document.getElementById("exp-json-regress-algo").value;

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
                    const [c_2, c_1, c_0] = analysis.coefficients;
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

function findYDimension(allYValues, labels) {
    const isSinglePoint = allYValues.length === 1;
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
        if (labels.toLowerCase().includes("absorbance") && getBtnChecked("split-sensor") && AppState.multiSource) {
            yMin = 0;
            yMax = 0.6;      
        } else {
            yMin = 0;
            yMax = isSinglePoint ? Math.max(...allYValues) * 1.1 : Math.max(...allYValues) * 1.1;
        }
        yStepSize = Number((yMax - yMin) / 10).toFixed(3) || 0.1;
    }
    return {
        yMin: yMin,
        yMax: yMax,
        yStepSize: yStepSize
    }
} 

function getLabelsFromYColumn(YColumn, measurementLabel, unit) {
    const labels = Array.isArray(YColumn) 
        ? YColumn.map(y => `${measurementLabel} ${y} ${unitDisplay(unit)}`) 
        : [`${measurementLabel} ${unitDisplay(unit)}`];
    return labels;
}

function getMetaUnit(metadata) {
    return (AppState.currentMeasurementMode === "calibrate") ? metadata['MeasUnit'] : metadata['Unit'];
}