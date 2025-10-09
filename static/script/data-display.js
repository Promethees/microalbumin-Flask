function updatePlot(
    data, metadata,
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
    const rawData = data;
    data = preprocessData(data, XColumn, YColumn);
    
    const isSplitMode = AppState.multiSource ? $("#split-sensor").is(":checked") : $("#split-mode").is(":checked");

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
            YColumn,
            metadata
        ]
        return isSplitMode ? splitMultiSourceRoutine(...Args) : groupMultiSourceRoutine(...Args);
    } else {
        // Original non-multiSource logic
        const Args = [
            allGroups,
            XColumn,
            YColumn,
            metadata,
            rawData,
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
    const conversionFactor = getTimeUnitMultiplier('seconds') / getTimeUnitMultiplier($("#time-unit").val());

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
    const normalizeMode = document.getElementById('normalize-mode').checked;

    // Normalize Y values if normalizeMode is checked
    allYColumnOrArray = normalizeMode ? (Array.isArray(allYColumnOrArray[0])
        ? allYColumnOrArray.map(yCol => yCol.map(value => (value - Math.min(...yCol))))
        : allYColumnOrArray.map(value => (value - Math.min(...allYColumnOrArray))))
        : allYColumnOrArray;

    const factor = getTimeUnitMultiplier('seconds') / getTimeUnitMultiplier(getTimeUnitValue());

    // Apply filtering only when fullDisplay checkbox is checked
    let filteredX = originalAllXColumn;
    let filteredY = allYColumnOrArray;
    if (!getCheckboxes(canvasId).fullDisplay.checked) {
        const startThreshold = parseFloat($("#range-value-start").val()) / factor;
        const endThreshold = parseFloat($("#range-value-end").val()) / factor;
        ({ filteredX, filteredY } = filterXYPairs(originalAllXColumn, allYColumnOrArray, startThreshold, endThreshold));
    }

    const displayedAllXColumn = filteredX.map(x => x * factor);

    // Calculate kinetics quantities using filtered data
    const analysis = calculateKineticsQuantities(filteredX, filteredY, parseInt($("#window-size").val()));

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
                    index: index
                })
            );
        } else {
            // Single mixed plot
            $container.append(`
                <label id="quantity-checkboxes-plot" class="hidden">
                    <h3>Quantities to display on graphic</h3>
                    ${checkboxHtmlWithID("plot", "plot-canvas", allXColumn, allYColumnOrArray, labelOrLabels, unit, index)}
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
                    index: index
                })
            );
        }
    }
}

function splitMultiSourceRoutine(allGroups, XColumn, YColumn, metadata) {
    const measUnit = getMetaUnit(metadata);

    const charts = [];
    const analyses = [];
    
    for (let i = 0; i < AppState.numSources; i++) {
        const yColumn = YColumn[i];
        const fullDisplayCheckbox = document.getElementById(`full-display-source-${i}`);
        const isFullDisplay = fullDisplayCheckbox ? fullDisplayCheckbox.checked : false;
        const filteredData = filteredByRangeValue(isFullDisplay, allGroups.allMixedData, XColumn, yColumn);
        const XColumnVals = extractColumnAndConvert(filteredData, XColumn, true);
        const yValues = extractColumnAndNormalize(filteredData, yColumn);
        const label = `${metadata['Measurement']} ${yColumn} ${unitDisplay(measUnit)}`;
        let analysis = null;

        analysis = calculateKineticsQuantities(allGroups.allXColumn, allGroups.allYColumn[i], parseInt($("#window-size").val()));

        analyses.push(analysis);

        const canvasId = `source-${i}-canvas`;
        const analysisId = `source-${i}-analysis`;
        renderCharts(allGroups.allXColumn, allGroups.allYColumn[i], label, measUnit, i);
        const chart = generateChart(canvasId, XColumnVals, [yValues], [label], measUnit, [analysis], i);
        charts.push(chart);

        // Update analysis info display
        const analysisInfo = formatAnalysisInfo(analysis, label);
        $("#" + analysisId).html(formatAnalysisHtml(analysisInfo, AppState.plotColors[i % AppState.plotColors.length], `Source ${i + 1}`));
    }

    AppState.sourceCharts = charts;

    return extractMultiSourceResultSummary(metadata, analyses);

}

function groupMultiSourceRoutine(allGroups, XColumn, YColumn, metadata) {
    const measUnit = getMetaUnit(metadata);

    const filteredData = filteredByRangeValue(false, allGroups.allMixedData, XColumn, YColumn[0]);
    const XColumnVals = extractColumnAndConvert(filteredData, XColumn, true);
    const YColumnVals = YColumn.map(yCol => extractColumnAndNormalize(filteredData, yCol));
    const analyses = allGroups.allYColumn.map(yCol => calculateKineticsQuantities(allGroups.allXColumn, yCol, parseInt($("#window-size").val())));
    const labels = YColumn.map(y => `${metadata['Measurement']} ${y} ${unitDisplay(measUnit)}`);

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
    $("#plot-analysis").html(html);

    AppState.myChart = generateChart('plot-canvas', XColumnVals, YColumnVals, labels, measUnit, analyses);

    if (AppState.currentMeasurementMode !== "calibrate") {
        return extractMultiSourceResultSummary(metadata, analyses);
    } else {
        return {
            analysis: analyses,
            meas: metadata["Measurement"]
        };
    }
}

function splitBlankRoutine(allGroups, XColumn, YColumn, metadata, rawData) {
    const measUnit = getMetaUnit(metadata);
    
    const allBlankedXColumn = extractColumnAndConvert(allGroups.allBlankedData, XColumn);
    const allBlankedYColumns = Array.isArray(YColumn) ? YColumn.map(y => extractColumnAndNormalize(allGroups.allBlankedData, y)) : [extractColumnAndNormalize(allGroups.allBlankedData, YColumn)];
    const allNonBlankedXColumn = extractColumnAndConvert(allGroups.allNonBlankedData, XColumn);
    const allNonBlankedYColumns = Array.isArray(YColumn) ? YColumn.map(y => extractColumnAndNormalize(allGroups.allNonBlankedData, y)) : [extractColumnAndNormalize(allGroups.allNonBlankedData, YColumn)];
    
    const fullDisplayCheckboxBlanked = document.getElementById('full-display-blanked');
    const fullDisplayCheckboxNonBlanked = document.getElementById('full-display-non-blanked');
    const isFullDisplayBlanked = AppState.currentMeasurementMode === "calibrate" ? true : (fullDisplayCheckboxBlanked ? fullDisplayCheckboxBlanked.checked : false);
    const isFullDisplayNonBlanked = AppState.currentMeasurementMode === "calibrate" ? true : (fullDisplayCheckboxNonBlanked ? fullDisplayCheckboxNonBlanked.checked : false);
    
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
        analysis_blanked = allBlankedYColumns.map((yCol, i) => calculateKineticsQuantities(allBlankedXColumn, yCol, parseInt($("#window-size").val())));
        analysis_nonblanked = allNonBlankedYColumns.map((yCol, i) => calculateKineticsQuantities(allNonBlankedXColumn, yCol, parseInt($("#window-size").val())));
    } else {
        if (calDiv.getAttribute('data-value') === "kinetics") {
            analysis_blanked = calibrateKineticsAnalysis(rawData, XColumn, YColumn, "BLANKED");
            analysis_nonblanked = calibrateKineticsAnalysis(rawData, XColumn, YColumn, "NON-BLANKED");
        } else if (calDiv.getAttribute('data-value') === "point") {
            analysis_blanked = calculateCoefAndRSquared(allBlankedYColumns[0], allBlankedXColumn, regressAlgo = $("#exp-json-regress-algo").val());
            analysis_nonblanked = calculateCoefAndRSquared(allNonBlankedYColumns[0], allNonBlankedXColumn, regressAlgo = $("#exp-json-regress-algo").val());
        }
    }
    const labels = getLabelsFromYColumn(YColumn, determineMeasurementLabel(metadata, XColumn, YColumn), measUnit);
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
            blanked_string = getCalKineticsString(analysis_blanked, $("#exp-json-regress-algo").val() === "Michaelis-Menten");
            non_blanked_string = getCalKineticsString(analysis_nonblanked, $("#exp-json-regress-algo").val() === "Michaelis-Menten");
        } else if (calDiv.getAttribute('data-value') === "point") {
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
}

function defaultRoutine(allGroups, XColumn, YColumn, metadata, rawData) {
    let mixAnalysis = null;
    let filteredData, XColumnVals, YColumnVals;
    const measUnit = getMetaUnit(metadata);

    if (AppState.currentMeasurementMode !== "calibrate") {
        const fullDisplayCheckbox = document.getElementById('full-display-plot');
        const isFullDisplay = fullDisplayCheckbox ? fullDisplayCheckbox.checked : false;
        filteredData = filteredByRangeValue(isFullDisplay, allGroups.allMixedData, XColumn, Array.isArray(YColumn) ? YColumn[0] : YColumn);
        XColumnVals = extractColumnAndConvert(filteredData, XColumn, true);
        YColumnVals = extractColumnAndNormalize(filteredData, YColumn);
        mixAnalysis = calculateKineticsQuantities(allGroups.allXColumn, allGroups.allYColumn, parseInt($("#window-size").val()));
    } else {
        filteredData = filterByBlankType(allGroups.allMixedData);
        XColumnVals = extractColumnAndConvert(filteredData, XColumn);
        YColumnVals = Array.isArray(YColumn) ? YColumn.map(y => extractColumnAndNormalize(filteredData, y)) : [extractColumnAndNormalize(filteredData, YColumn)];
        if (calDiv.getAttribute('data-value') === "kinetics") {
            mixAnalysis = calibrateKineticsAnalysis(rawData, XColumn, YColumn, "MIXED");
        } else if (calDiv.getAttribute('data-value') === "point") {
            mixAnalysis = calculateCoefAndRSquared(extractColumnAndNormalize(allGroups.allMixedData, YColumn), extractColumnAndConvert(allGroups.allMixedData, XColumn), regressAlgo = $("#exp-json-regress-algo").val());
        }
    }

    // Generate chart
    const labels = getLabelsFromYColumn(YColumn, determineMeasurementLabel(metadata, XColumn, YColumn), measUnit);
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
            htmlString = getCalKineticsString(mixAnalysis, $("#exp-json-regress-algo").val() === "Michaelis-Menten");
        } else if (calDiv.getAttribute('data-value') === "point") {
            htmlString = getCalPointString(mixAnalysis);
        }
        $("#plot-analysis").html(htmlString);
    }

    if (AppState.currentMeasurementMode !== "calibrate") {
        return extractSingleResultSummary(metadata, mixAnalysis);
    } else {
        return {
            analysis: mixAnalysis,
            meas: metadata["Measurement"]
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
            start: parseFloat($("#range-value-start").val()),
            end: parseFloat($("#range-value-end").val())
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

function getCalKineticsString(analysis, isMM=false) {
    let htmlString = "";
    for (let i = 0; i < AppState.quantity_input.quantities.length; i++) {
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
        htmlString += `${AppState.quantity_input.quantities[i]}: Coef:` + coefString;
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
    const factor = getTimeUnitMultiplier('seconds') / getTimeUnitMultiplier($("#time-unit").val());
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

function formatAnalysisHtml(analysisInfo, color = null, label = '') {
    if (!analysisInfo) return '';
    const unitDisplay = getMetaUnit(AppState.metaData) !== "NONE" ? getMetaUnit(AppState.metaData) : '';
    const displaySat = (!isNaN(analysisInfo.saturationValue)) ? analysisInfo.saturationValue : "--";
    const displayTimeSat = (!isNaN(analysisInfo.timeToSaturation)) ? analysisInfo.timeToSaturation : "--";
    const html = `<span ${color ? `style="color: ${color};"` : ''}>
        ${label ? `${label}: ` : ''}Slope = ${analysisInfo.slope}${unitDisplay}/${getTimeUnitValue().slice(0, -1)}, 
        Linear start = ${analysisInfo.linearStart} ${getTimeUnitValue().slice(0, -1)},
        Linear end = ${analysisInfo.linearEnd} ${getTimeUnitValue().slice(0, -1)}, <br/>
        maxRate = ${analysisInfo.maxRate}${unitDisplay}/${getTimeUnitValue().slice(0, -1)}, 
        maxRateStart = ${analysisInfo.maxRateStart} ${getTimeUnitValue().slice(0, -1)}, 
        maxRateEnd = ${analysisInfo.maxRateEnd} ${getTimeUnitValue().slice(0, -1)}, <br/>
        Saturation = ${displaySat}${unitDisplay}, 
        Reacting Time taken to Saturation = ${displayTimeSat} ${getTimeUnitValue().slice(0, -1)}
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

function updateSingleModeAnalysisInfo(analysisInfo) {
    if (analysisInfo) {
        $("#plot-analysis").html(formatAnalysisHtml(analysisInfo));
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

function calibrateKineticsAnalysis(data, XColumn, YColumn, blankTypeValue) {
    const dataMap = preprocessDataCalParams(data, XColumn, YColumn);
    const regressAlgo = $("#exp-json-regress-algo").val();
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
        if (labels.toLowerCase().includes("absorbance") && $("#split-sensor").is(":checked") && AppState.multiSource) {
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