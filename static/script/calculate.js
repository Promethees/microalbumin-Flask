// AJAX wrapper for calculateCoefAndRSquared
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
                console.error("Math API error:", response.message);
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            console.error("AJAX Error:", textStatus, errorThrown);
        }
    });
    return result;
}

// AJAX wrapper for calculateKineticsQuantities
function calculateKineticsQuantities(XColumn, YColumn, window_size) {
    let result = { slope: 0, intercept: 0, saturationValue: "--", timeToSaturation: "--", maxRate: 0, linearSlope: 0, linearYMin: 0, linearYMax: 0, linearXMin: 0, linearXMax: 0 };
    $.ajax({
        url: '/calculate_kinetics_quantities',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ XColumn: XColumn, YColumn: YColumn, window_size: window_size }),
        async: false,
        success: function(response) {
            if (response.status === 'success') {
                result = response.result;
            } else {
                console.error("Math API error:", response.message);
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            console.error("AJAX Error:", textStatus, errorThrown);
        }
    });
    return result;
}

function getEstimatedValue(data, timepoint, sourceIndex, maxTolerance = 60) {
    if (!Array.isArray(data) || data.length === 0 || !timepoint) return null;

    // Pick which key to use
    let valueKey = `Value:${sourceIndex}`; // e.g. Value:1, Value:2

    // Filter only rows with valid numeric values for this specific source
    const validData = data
        .filter(row => row[valueKey] !== null && row[valueKey] !== "NONE" && row[valueKey] !== "OVFL" && !isNaN(parseFloat(row[valueKey])))
        .sort((a, b) => a["Timestamp"] - b["Timestamp"]);

    if (validData.length === 0) return null;

    // Loop to find the two surrounding points in valid data
    for (let i = 0; i < validData.length - 1; i++) {
        const t1 = validData[i]["Timestamp"];
        const t2 = validData[i + 1]["Timestamp"];

        // Exact match
        if (parseFloat(t1) === parseFloat(timepoint)) return parseFloat(validData[i][valueKey]);
        if (parseFloat(t2) === parseFloat(timepoint)) return parseFloat(validData[i + 1][valueKey]);

        // Interpolation between surrounding timestamps
        if (t1 < timepoint && timepoint < t2) {
            const minDiff = Math.min(Math.abs(timepoint - t1), Math.abs(timepoint - t2));
            if (minDiff > maxTolerance) return null;

            const v1 = parseFloat(validData[i][valueKey]);
            const v2 = parseFloat(validData[i + 1][valueKey]);

            const ratio = (timepoint - t1) / (t2 - t1);
            return v1 + ratio * (v2 - v1);
        }
    }

    // Check ends if out-of-bounds but within tolerance
    const first = validData[0], last = validData[validData.length - 1];
    if (Math.abs(timepoint - first["Timestamp"]) <= maxTolerance) return parseFloat(first[valueKey]);
    if (Math.abs(timepoint - last["Timestamp"]) <= maxTolerance) return parseFloat(last[valueKey]);

    return null;
}

function getUniqueColumnEntries(data, columnName = "TimePoint") {
    const uniqueColumnEntries = new Set(data.map(row => row[columnName]).filter(tp => tp));
    return Array.from(uniqueColumnEntries).sort((a, b) => Number(b) - Number(a));
}

function arraysEqual(arr1, arr2) {
    if (arr1.length !== arr2.length) return false;
    return arr1.every((value, index) => value === arr2[index]);
}

function computeFit(value, fit_type, coef) {
    const regressedQuantity = document.getElementById("regressed-quantity").value;
    if (coef[0] === 'NONE' || coef[0] === 'NaN') {
        throw new Error(`Fit_type: ${fit_type} cannot be used to derive concentration from ${regressedQuantity}`);
    }
    if (typeof value !== 'number' || isNaN(value)) {
        throw new Error(`Quantity: ${regressedQuantity} is not available`);
    }
    switch (fit_type.toLowerCase()) {
        case "linear":
            // Expect coef = [a, b]
            if (Object.keys(coef).length !== 2) throw new Error("Linear fit requires 2 coefficients: [a, b]");
            return coef["a"] * value + coef["b"];

        case "polynomial":
            // Expect coef = [a, b, c]
            if (Object.keys(coef).length !== 3) throw new Error("Polynomial fit requires 3 coefficients: [a, b, c]");
            return coef["a"] * Math.pow(value, 2) + coef["b"] * value + coef["c"];

        case "logarithmic":
            // Expect coef = [a, b, c]
            if (Object.keys(coef).length !== 3) throw new Error("Logarithmic fit requires 3 coefficients: [a, b, c]");
            if (value <= 0) throw new Error("Invalid input for logarithm: value must be > 0");
            return coef["a"] * Math.log(value + coef["b"]) + coef["c"];

        case "exponential":
            // Expect coef = [a, b, c]
            if (Object.keys(coef).length !== 3) throw new Error("Exponential fit requires 3 coefficients: [a, b, c]");
            return coef["a"] * Math.exp(value * coef["b"]) + coef["c"];

        case "michaelis-menten":
            // Expect coef = [Vmax, Km]
            if (Object.keys(coef).length !== 2) throw new Error("Michaelis-Menten fit requires 2 coefficients: [Vmax, Km]");
            if (value >= coef["VMax"] || value < 0) throw new Error(`Invalid input for Michaelis-Menten: value ${value}/minute must be < Vmax: ${coef["VMax"]} and >= 0`);
            return (coef["Km"] * value) / (coef["VMax"] - value);

        default:
            throw new Error("Unknown fit type: " + fit_type);
    }
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

function getTimeUnitMultiplier(unit) {
    const multipliers = {
        'seconds': 1,
        'minutes': 60,
        'hours': 3600
    };
    return multipliers[unit] || 1;
}

function mapDuplicates(x, y, keepGaps = false) {
    // Create a map to store sum and count of y values for each x
    const xMap = new Map();

    // Process each pair
    for (let i = 0; i < x.length; i++) {
        const currentX = x[i];
        const currentY = y[i];

        // Skip or mark as gap if y is "NONE" or null
        const isNone = currentY === "NONE" || currentY === null || currentY === "OVFL";
        if (isNone) {
            if (!keepGaps) continue;
            if (!xMap.has(currentX)) {
                xMap.set(currentX, { sum: 0, count: 0, hasValid: false });
            }
        } else {
            const val = parseFloat(currentY);
            if (!isNaN(val)) {
                if (!xMap.has(currentX)) {
                    xMap.set(currentX, { sum: val, count: 1, hasValid: true });
                } else {
                    const entry = xMap.get(currentX);
                    entry.sum += val;
                    entry.count++;
                    entry.hasValid = true;
                }
            } else if (keepGaps) {
                if (!xMap.has(currentX)) {
                    xMap.set(currentX, { sum: 0, count: 0, hasValid: false });
                }
            }
        }
    }

    // Convert the map back to arrays
    const processedX = [];
    const processedY = [];

    xMap.forEach((value, key) => {
        processedX.push(key);
        processedY.push(value.hasValid ? (value.sum / value.count) : null);
    });

    return { x: processedX, y: processedY };
}

function filterXYPairs(XColumnVals, YColumnVals, startThreshold, endThreshold) {
    const isMultiY = Array.isArray(YColumnVals[0]);

    // Ensure X/Y sizes match
    if (isMultiY) {
        YColumnVals.forEach(y => checkSize(XColumnVals, y));
    } else {
        checkSize(XColumnVals, YColumnVals);
    }

    // Determine indices that satisfy the threshold range
    const validIndices = XColumnVals
        .map((x, i) => (x >= startThreshold && x <= endThreshold ? i : -1))
        .filter(i => i !== -1);

    // Filter X based on those indices
    const filteredX = validIndices.map(i => XColumnVals[i]);

    // Filter Y — handle both single and multiple Y columns
    const filteredY = isMultiY
        ? YColumnVals.map(y => validIndices.map(i => y[i]))
        : validIndices.map(i => YColumnVals[i]);

    return { filteredX, filteredY };
}

function checkSize(XColumn, YColumn) {
    if (XColumn.length !== YColumn.length) {
        throw new Error(
            `X and Y columns must have the same length. Got X: ${XColumn.length}, Y: ${YColumn.length}`
        );
    }
}