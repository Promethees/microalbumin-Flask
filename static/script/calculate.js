// Helper function to calculate R-squared
function computeRSquared(actual, predicted) {
    if (actual.length !== predicted.length || actual.length < 1) return 0;
    const meanY = actual.reduce((sum, yi) => sum + yi, 0) / actual.length;
    const ssTotal = actual.reduce((sum, yi) => sum + Math.pow(yi - meanY, 2), 0);
    const ssResidual = actual.reduce((sum, yi, i) => sum + Math.pow(yi - predicted[i], 2), 0);
    return ssTotal === 0 ? 0 : 1 - ssResidual / ssTotal;
}

/**
 * Perform regression analysis via the Python backend
 * @param {Array} x - X values
 * @param {Array} y - Y values
 * @param {string} regressAlgo - Regression algorithm type
 * @returns {Object} { slope, rSquared, coefficients }
 */
function calculateCoefAndRSquared(x, y, regressAlgo = "linear") {
    let result = { slope: 0, rSquared: 0, coefficients: null };
    $.ajax({
        url: '/calculate_coef_and_rsquared',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ x: x, y: y, regress_algo: regressAlgo }),
        async: false,
        success: function(response) {
            if (response.status === 'success') {
                result = response.result;
            } else {
                console.error("Math API Error:", response.message);
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            console.error("AJAX Error:", textStatus, errorThrown);
        }
    });
    return result;
}

/**
 * Calculate kinetics quantities via the Python backend
 * @param {Array} XColumn - Timestamps
 * @param {Array} YColumn - Values
 * @param {number} window_size - Sliding window size
 * @returns {Object} Kinetics analysis results
 */
function calculateKineticsQuantities(XColumn, YColumn, window_size) {
    let result = null;
    $.ajax({
        url: '/calculate_kinetics_quantities',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ XColumn: XColumn, YColumn: YColumn, window_size: window_size }),
        async: false,
        success: function (response) {
            if (response.status === 'success') {
                result = response.result;
            } else {
                console.error("Math API Error:", response.message);
            }
        },
        error: function (jqXHR, textStatus, errorThrown) {
            console.error("AJAX Error:", textStatus, errorThrown);
        }
    });
    return result;
}

/**
 * Get estimated value at a specific timepoint with interpolation
 */
function getEstimatedValue(data, timepoint, sourceIndex, maxTolerance = 60) {
    if (!Array.isArray(data) || data.length === 0 || !timepoint) return null;

    let valueKey = `Value:${sourceIndex}`;

    // Filter and sort valid numeric data for this source
    const validData = data
        .filter(row => {
            const val = row[valueKey];
            return val !== null && val !== "NONE" && val !== "OVFL" && !isNaN(parseFloat(val));
        })
        .sort((a, b) => a["Timestamp"] - b["Timestamp"]);

    if (validData.length === 0) return null;

    // Linear interpolation between surrounding points
    for (let i = 0; i < validData.length - 1; i++) {
        const t1 = validData[i]["Timestamp"];
        const t2 = validData[i + 1]["Timestamp"];

        if (parseFloat(t1) === parseFloat(timepoint)) return parseFloat(validData[i][valueKey]);
        if (parseFloat(t2) === parseFloat(timepoint)) return parseFloat(validData[i + 1][valueKey]);

        if (t1 < timepoint && timepoint < t2) {
            const minDiff = Math.min(Math.abs(timepoint - t1), Math.abs(timepoint - t2));
            if (minDiff > maxTolerance) return null;

            const v1 = parseFloat(validData[i][valueKey]);
            const v2 = parseFloat(validData[i + 1][valueKey]);

            const ratio = (timepoint - t1) / (t2 - t1);
            return v1 + ratio * (v2 - v1);
        }
    }

    // Handle endpoints with tolerance
    const first = validData[0], last = validData[validData.length - 1];
    if (Math.abs(timepoint - first["Timestamp"]) <= maxTolerance) return parseFloat(first[valueKey]);
    if (Math.abs(timepoint - last["Timestamp"]) <= maxTolerance) return parseFloat(last[valueKey]);

    return null;
}

/**
 * Compute fitted Y value based on fit type and coefficients
 */
function computeFit(value, fitType, coefficients) {
    if (!coefficients) return 0;
    
    const isObject = !Array.isArray(coefficients);
    const fit = fitType.toLowerCase();

    switch (fit) {
        case "linear":
            if (isObject) return (coefficients.a || 0) * value + (coefficients.b || 0);
            return (coefficients[0] || 0) * value + (coefficients[1] || 0);

        case "polynomial":
            if (isObject) return (coefficients.a || 0) * Math.pow(value, 2) + (coefficients.b || 0) * value + (coefficients.c || 0);
            return coefficients.reduce((acc, c, i) => acc + c * Math.pow(value, coefficients.length - 1 - i), 0);

        case "logarithmic":
            if (isObject) return (coefficients.a || 0) * Math.log(value + (coefficients.b || 0)) + (coefficients.c || 0);
            return (coefficients[0] || 0) * Math.log(value + (coefficients[1] || 0)) + (coefficients[2] || 0);

        case "exponential":
            if (isObject) return (coefficients.a || 0) * Math.exp(value * (coefficients.b || 1)) + (coefficients.c || 0);
            return (coefficients[0] || 0) * Math.exp(value * (coefficients[1] || 1)) + (coefficients[2] || 0);

        case "michaelis-menten":
            const vmax = isObject ? (coefficients.Vmax || coefficients.VMax || 0) : (coefficients[0] || 0);
            const km = isObject ? (coefficients.Km || 0) : (coefficients[1] || 0);
            if (value >= vmax || value < 0) return Infinity;
            return (km * value) / (vmax - value);

        default:
            return 0;
    }
}

// Utility functions
function getUniqueColumnEntries(data, columnName = "TimePoint") {
    const unique = new Set(data.map(row => row[columnName]).filter(tp => tp));
    return Array.from(unique).sort((a, b) => Number(b) - Number(a));
}

function arraysEqual(arr1, arr2) {
    if (arr1.length !== arr2.length) return false;
    return arr1.every((value, index) => value === arr2[index]);
}

function getTimeUnitMultiplier(unit) {
    const multipliers = { 'seconds': 1, 'minutes': 60, 'hours': 3600 };
    return multipliers[unit] || 1;
}

/**
 * Handle duplicate X values by averaging their Y values
 */
function mapDuplicates(x, y, keepGaps = false) {
    const xMap = new Map();
    for (let i = 0; i < x.length; i++) {
        const curX = x[i];
        const curY = y[i];
        const isInvalid = curY === "NONE" || curY === null || curY === "OVFL";
        
        if (isInvalid) {
            if (!keepGaps) continue;
            if (!xMap.has(curX)) xMap.set(curX, { sum: 0, count: 0, hasValid: false });
        } else {
            const val = parseFloat(curY);
            if (!isNaN(val)) {
                if (!xMap.has(curX)) {
                    xMap.set(curX, { sum: val, count: 1, hasValid: true });
                } else {
                    const entry = xMap.get(curX);
                    entry.sum += val;
                    entry.count++;
                    entry.hasValid = true;
                }
            } else if (keepGaps && !xMap.has(curX)) {
                xMap.set(curX, { sum: 0, count: 0, hasValid: false });
            }
        }
    }
    const procX = [], procY = [];
    xMap.forEach((v, k) => {
        procX.push(k);
        procY.push(v.hasValid ? v.sum / v.count : null);
    });
    return { x: procX, y: procY };
}

function filterXYPairs(XColumnVals, YColumnVals, startThreshold, endThreshold) {
    const isMultiY = Array.isArray(YColumnVals[0]);
    if (isMultiY) {
        YColumnVals.forEach(y => checkSize(XColumnVals, y));
    } else {
        checkSize(XColumnVals, YColumnVals);
    }
    const validIndices = XColumnVals
        .map((x, i) => (x >= startThreshold && x <= endThreshold ? i : -1))
        .filter(i => i !== -1);
        
    const filteredX = validIndices.map(i => XColumnVals[i]);
    const filteredY = isMultiY
        ? YColumnVals.map(y => validIndices.map(i => y[i]))
        : validIndices.map(i => YColumnVals[i]);
        
    return { filteredX, filteredY };
}

function averageDuplicates(xColumn, yColumn) {
    const dataMap = new Map();

    // Group YColumn values by XColumn values
    for (let i = 0; i < xColumn.length; i++) {
        if (!dataMap.has(xColumn[i])) {
            dataMap.set(xColumn[i], []);
        }
        dataMap.get(xColumn[i]).push(yColumn[i]);
    }

    // Calculate average for each group
    const uniqueX = [];
    const averagedY = [];
    for (let [x, yValues] of dataMap) {
        uniqueX.push(x);
        const validValues = yValues.filter(v => v !== null && v !== "NONE" && !isNaN(v));
        if (validValues.length > 0) {
            const avg = validValues.reduce((sum, value) => sum + parseFloat(value), 0) / validValues.length;
            averagedY.push(avg);
        } else {
            averagedY.push(null);
        }
    }

    return { XColumn: uniqueX, YColumn: averagedY };
}

function checkSize(XColumn, YColumn) {
    if (XColumn.length !== YColumn.length) {
        throw new Error(
            `X and Y columns must have the same length. Got X: ${XColumn.length}, Y: ${YColumn.length}`
        );
    }
}