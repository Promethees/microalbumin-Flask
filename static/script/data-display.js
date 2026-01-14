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
    
    const isSplitMode = getBtnChecked("split-sensor");

    const allGroups = {
            allXColumn: extractColumnAndConvert(data, XColumn),
            allYColumn: Array.isArray(YColumn) ? YColumn.map(y => extractColumnAndNormalize(data, y)) : [extractColumnAndNormalize(data, YColumn)],
            allData: data
        };

    let Args = [
        allGroups,
        XColumn,
        YColumn
    ]
    if (AppState.currentMeasurementMode === "calibrate") {
        Args.push(rawData);
        return calibrateRoutine(...Args);
    } else {
        return isSplitMode ? splitMultiSourceRoutine(...Args) : groupMultiSourceRoutine(...Args);
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

function handleConValueReadChange(canvasId, allXColumn, allYColumnOrArray, index, unit) {
    const input = document.getElementById(`con-value-read-source-${index}`);
    const value = input ? input.value : '';
    // Save to localStorage for persistence
    if (value !== '') {
        localStorage.setItem(`con-value-read-source-${index}`, value);
    } else {
        // Optionally remove from localStorage if empty
        localStorage.removeItem(`con-value-read-source-${index}`);
    }

    // Call getLabel with the current value at change time
    const label = getLabel(`Value:${index + 1}`, unit);
    
    // Call the original handler with the dynamically generated label
    handleCkboxChange(canvasId, allXColumn, allYColumnOrArray, label, unit, index);
}

// Helper function to save value on blur (user leaves the field)
function saveConcentrationValue(index) {
    const input = document.getElementById(`con-value-read-source-${index}`);
    const value = input ? input.value : '';
    
    if (value !== '') {
        localStorage.setItem(`con-value-read-source-${index}`, value);
    } else {
        localStorage.removeItem(`con-value-read-source-${index}`);
    }
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
    if (!getCheckboxes(canvasId).fullDisplay || !getCheckboxes(canvasId).fullDisplay.checked) {
        const startThreshold = getValFloat("range-value-start") / factor;
        const endThreshold = getValFloat("range-value-end") / factor;
        ({ filteredX, filteredY } = filterXYPairs(originalAllXColumn, allYColumnOrArray, startThreshold, endThreshold));
    }

    const displayedAllXColumn = filteredX.map(x => x * factor);

    // Calculate kinetics quantities using filtered data
    const analysis = Array.isArray(filteredY[0]) ?
        filteredY.map(y => calculateKineticsQuantities(filteredX, y, getValInt("window-size"))) :
        calculateKineticsQuantities(filteredX, filteredY, getValInt("window-size"));

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
    // Get previous value from localStorage if it exists
    const previousValueKey = `con-value-read-source-${index}`;
    const previousValue = localStorage.getItem(previousValueKey) || '';

    // Store parameters needed for dynamic label generation
    window[`chartParams_${index}`] = {
        canvasId,
        allXColumn: JSON.stringify(allXColumn),
        allYColumnOrArray: JSON.stringify(allYColumnOrArray),
        unit,
        index
    };

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
            ${`
                <div id="concentration-reader-section-source-${index}">
                    Concentration from source-${index + 1} sample is 
                    <input type="number" id="con-value-read-source-${index}" 
                        value="${previousValue}"
                        onchange="handleConValueReadChange('${canvasId}', 
                            ${JSON.stringify(allXColumn)}, 
                            ${JSON.stringify(allYColumnOrArray)},
                            ${index},
                            '${unit}')" 
                        onblur="saveConcentrationValue(${index})"
                        value="${previousValue}" 
                        min=0 style="width: 5em;"> </input> ng/µL
                </div>
                <div id="derived-concentration-section-source-${index}" class="hidden">
                    Concentration derived from the source-${index + 1} is <span id="der-con-value-source-${index}" class="der-con-value" tabindex="-1"></span> ng/µL
                </div>
                `}
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
}

function splitMultiSourceRoutine(allGroups, XColumn, YColumn) {
    const measUnit = getMetaUnit(AppState.metaData);

    const charts = [];
    const analyses = [];
    
    for (let i = 0; i < AppState.numSources; i++) {
        const yColumn = YColumn[i];
        const isFullDisplay = getBtnChecked(`full-display-source-${i}`);
        const filteredData = filteredByRangeValue(isFullDisplay, allGroups.allData, XColumn, yColumn);
        const XColumnVals = extractColumnAndConvert(filteredData, XColumn, true);
        const yValues = extractColumnAndNormalize(filteredData, yColumn);
        const label = getLabel(`Value:${i + 1}`, measUnit);
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

    const filteredData = filteredByRangeValue(false, allGroups.allData, XColumn, YColumn[0]);
    const XColumnVals = extractColumnAndConvert(filteredData, XColumn, true);
    const YColumnVals = YColumn.map(yCol => extractColumnAndNormalize(filteredData, yCol));
    const analyses = allGroups.allYColumn.map(yCol => calculateKineticsQuantities(allGroups.allXColumn, yCol, getValInt("window-size")));
    const labels = YColumn.map(y => getLabel(y, measUnit));

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

    addConReadValueEventListener(XColumnVals, YColumnVals, YColumn, measUnit);

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

function getLabel(yColumn, measUnit) {
    // Extract n from "Value:n" format
    const match = yColumn.match(/Value:(\d+)/);
    if (!match) {
        throw new Error(`Invalid yColumn format: ${yColumn}. Expected format "Value:n"`);
    }
    const n = parseInt(match[1], 10);
    const elementId = `con-value-read-source-${n - 1}`;

    // let conValueRead = document.getElementById(elementId)?.value;
    
    // conValueRead = conValueRead ? 
    const conValueRead = localStorage.getItem(elementId);

    return conValueRead 
        ? `${AppState.metaData['Measurement']} at ${conValueRead} ng/µL ${unitDisplay(measUnit)}`
        : `${AppState.metaData['Measurement']} ${yColumn} ${unitDisplay(measUnit)}`;
}

function addConReadValueEventListener(XColumnVals, YColumnVals, YColumn, measUnit) {
    for (let i = 0; i < AppState.numSources; i++) {
        // Capture YColumn as it is *now*
        const capturedY = [...YColumn];

        // Get the input element
        const inputElement = document.getElementById(`con-value-read-source-${i}`);
        if (!inputElement) continue;

        // Set initial value from localStorage if not already set
        const storageKey = `con-value-read-source-${i}`;
        const storedValue = localStorage.getItem(storageKey);
        if (storedValue !== null && inputElement.value === '') {
            inputElement.value = storedValue;
        }

        // Attach the change listener
        inputElement.addEventListener("change", function () {
            const value = this.value;
            const storageKey = `con-value-read-source-${i}`;
            
            // Save to localStorage
            if (value !== '') {
                localStorage.setItem(storageKey, value);
            } else {
                localStorage.removeItem(storageKey);
            }
            
            // Generate labels and handle change
            const yLabels = capturedY.map(y => getLabel(y, measUnit));
            handleCkboxChange(
                "plot-canvas",
                XColumnVals,
                YColumnVals,
                yLabels,
                measUnit,
                null
            );
        });

        // Also save on blur to catch manual edits that don't trigger change
        inputElement.addEventListener("blur", function () {
            const value = this.value;
            const storageKey = `con-value-read-source-${i}`;
            
            if (value !== '') {
                localStorage.setItem(storageKey, value);
            } else {
                localStorage.removeItem(storageKey);
            }
        });
    }
}

function calibrateRoutine(allGroups, XColumn, YColumn, rawData) {
    let mixAnalysis = null;
    let XColumnVals, YColumnVals;
    const measUnit = getMetaUnit(AppState.metaData);


    XColumnVals = extractColumnAndConvert(allGroups.allData, XColumn);
    YColumnVals = Array.isArray(YColumn) ? YColumn.map(y => extractColumnAndNormalize(allGroups.allData, y)) : [extractColumnAndNormalize(allGroups.allData, YColumn)];
    if (calDiv.getAttribute('data-value') === "kinetics") {
        mixAnalysis = calibrateKineticsAnalysis(rawData, XColumn, YColumn, "MIXED");
    } else if (calDiv.getAttribute('data-value') === "point") {
        mixAnalysis = calculateCoefAndRSquared(extractColumnAndNormalize(allGroups.allData, YColumn), extractColumnAndConvert(allGroups.allData, XColumn), regressAlgo = document.getElementById("exp-json-regress-algo").value);
    }

    // Generate chart
    const labels = getLabelsFromYColumn(YColumn, determineMeasurementLabel(AppState.metaData, XColumn, YColumn), measUnit);
    renderCharts(allGroups.allXColumn, allGroups.allYColumn, labels, measUnit);
    AppState.myChart = generateChart('plot-canvas', XColumnVals, YColumnVals, labels, measUnit, mixAnalysis);

    // Update analysis info display
    let htmlString = "";
    if (calDiv.getAttribute('data-value') === "kinetics") {
        htmlString = getCalKineticsString(mixAnalysis, document.getElementById("exp-json-regress-algo").value);
    } else if (calDiv.getAttribute('data-value') === "point") {
        htmlString = getCalPointString(mixAnalysis);
    }
    document.getElementById("plot-analysis").innerHTML = htmlString;

    return {
        analysis: mixAnalysis,
        meas: AppState.metaData["Measurement"]
    };
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

function getCalKineticsString(analysis, fitType, analysisId = "cal-kinetics-analysis") {
    if (!analysis || !AppState.quantity_input.quantities) return '';
    let headers
    switch(fitType) {
        case "Michaelis-Menten":
            headers = ['V_max', 'Km'];
            break;
        case "linear":
            headers = ['a', 'b'];
            break;
        default:
            headers = ['a', 'b', 'c'];
            break;
    }
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

function getDataGroups(data, XColumn, YColumn) {
    return {
        allXColumn: extractColumnAndConvert(data, XColumn),
        allYColumn: extractColumnAndNormalize(data, YColumn),
        allData: data
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

function calibrateKineticsAnalysis(data, XColumn, YColumn) {
    const dataMap = preprocessDataCalParams(data, XColumn, YColumn);
    const regressAlgo = document.getElementById("exp-json-regress-algo").value;
    if (dataMap) {
        const results = dataMap.map(({ param, data }) => {
            const xValues = data.map(row => row[XColumn]);
            const yValues = data.map(row => row[param]);
            const result = calculateCoefAndRSquared(yValues, xValues, regressAlgo);
            return result;
        });
        return results;
    }
    const filteredData = data
        .filter(row => row[XColumn] !== "NONE" && row[YColumn] !== "NONE")
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
        if (labels.toLowerCase().includes("absorbance") && getBtnChecked("split-sensor")) {
            yMin = Math.min(Math.min(...allYValues), 0);
            yMax = 0.6;      
        } else {
            yMin = Math.min(Math.min(...allYValues), 0);
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

// Clear all concentration values for this session
function clearConcentrationValues() {
    for (let i = 0; i < AppState.numSources; i++) { // Adjust based on max sources
        localStorage.removeItem(`con-value-read-source-${i}`);
    }
}