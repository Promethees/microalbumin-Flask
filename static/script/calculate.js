function calculateRSquared(predicted, y) {
    const meanY = y.reduce((a, b) => a + b, 0) / y.length;
    const ssTot = y.reduce((sum, yi) => sum + Math.pow(yi - meanY, 2), 0);
    const ssRes = y.reduce((sum, yi, i) => sum + Math.pow(yi - predicted[i], 2), 0);
    return ssTot === 0 ? 1 : 1 - ssRes / ssTot;
}

function calculateCoefAndRSquared(x, y, algo = "linear") {
    if (x.length !== y.length || x.length < 2) return { slope: 0, rSquared: 0, coefficients: null };

    let slope = 0;
    let predicted = [];
    let coefficients = null;

    switch (algo) {
        case "polynomial":
            const degree = 2;
            coefficients = polynomialRegression(x, y, degree);
            predicted = x.map(xi =>
                coefficients.reduce((acc, c, i) => acc + c * Math.pow(xi, i), 0)
            );
            slope = polynomialRegressionSlope(x, y, degree);
            break;

        case "logarithmic":
            if (x.some(xi => xi <= 0)) return { slope: 0, rSquared: 0, coefficients: null }; // invalid log(x)
            const logCoeffs = logarithmicRegression(x, y);
            coefficients = logCoeffs;
            predicted = x.map(xi => logCoeffs[0] * Math.log(xi) + logCoeffs[1]);
            slope = logarithmicRegressionSlope(x, y);
            break;

        case "linear":
        default:
            const lin = linearRegression(x, y);
            coefficients = lin;
            slope = lin[0];
            predicted = x.map(xi => slope * xi + lin[1]);
            break;
    }
    const rSquared = calculateRSquared(predicted, y);

    return { slope: slope, 
             rSquared: rSquared, 
             coefficients: coefficients };
}


function calculateKineticsQuantities(XColumn, YColumn, window_size) {
    if (XColumn.length < 2 || YColumn.length < 2 || window_size < 2 || window_size > XColumn.length) {
        return { slope: 0, intercept: 0, saturationValue: "--", timeToSaturation: "--", Vmax: 0, linearSlope: 0, linearYMin: 0, linearYMax: 0, linearXMin: 0, linearXMax: 0 };
    }

    let localSlopes = [];
    let rSquaredValues = [];
    let intercepts = [];

    for (let i = 0; i <= XColumn.length - window_size; i++) {
        const x = XColumn.slice(i, i + window_size);
        const y = YColumn.slice(i, i + window_size);
        const calc = calculateCoefAndRSquared(x, y);

        const intercept = y.reduce((a, b) => a + b, 0) / y.length - calc.slope * (x.reduce((a, b) => a + b, 0) / x.length);

        localSlopes.push(calc.slope);
        rSquaredValues.push(calc.rSquared);
        intercepts.push(intercept);
    }

    let Vmax = 0;
    let threshold = 0.2;
    let startVMax = -1;
    let endVMax = -1;
    let yVMaxstart = 0;
    let yVMaxend = 0;

    for (let i = 0; i < localSlopes.length; i++) {
        const adjustedLocal = 3600 * localSlopes[i];
        if (rSquaredValues[i] >= 0.95 && localSlopes[i] > Vmax && adjustedLocal > threshold) {
            Vmax = localSlopes[i];
            startVMax = i;
            endVMax = startVMax + window_size - 1;
            yVMaxstart = Vmax * XColumn[startVMax] + intercepts[i];
            yVMaxend = Vmax * XColumn[endVMax] + intercepts[i];
        }
    }

    let linearStartIdx = -1;
    let linearEndIdx = -1;
    if (Vmax !== 0) {
        for (let i = 0; i < localSlopes.length; i++) {
            if (localSlopes[i] >= 0.7 * Vmax) {
                if (linearStartIdx === -1) linearStartIdx = i;
                linearEndIdx = i;
            }
        }
    }

    let linearSlope = null;
    let linearIntercept = 0;
    let linearXMin = 0;
    let linearXMax = 0;
    let linearYMin = 0;
    let linearYMax = 0;
    let saturationValue = "--";
    let timeToSaturation = "--";
    let timeStartSaturation = "--";

    if (linearStartIdx !== -1 && linearEndIdx !== -1) {
        let start = linearStartIdx;
        let end = linearEndIdx + window_size;
        if (end > XColumn.length) end = XColumn.length;

        const x = XColumn.slice(start, end);
        const y = YColumn.slice(start, end);
        const { slope, rSquared } = calculateCoefAndRSquared(x, y);

        linearSlope = slope;
        const avgX = x.reduce((a, b) => a + b, 0) / x.length;
        const avgY = y.reduce((a, b) => a + b, 0) / y.length;
        linearIntercept = avgY - slope * avgX;

        linearXMin = XColumn[start];
        linearXMax = XColumn[end - 1];
        linearYMin = slope * linearXMin + linearIntercept;
        linearYMax = slope * linearXMax + linearIntercept;

        if (end >= YColumn.length) {
            saturationValue = "--";
        } else {
            const theRest = YColumn.slice(end);
            const sortedValuesForRest = [...theRest].sort((a, b) => a - b);
            saturationValue = sortedValuesForRest[Math.floor(theRest.length / 2)].toFixed(2);
        }
        timeToSaturation = (XColumn[end - 1] - XColumn[start]).toFixed(2);
        timeStartSaturation = XColumn[end - 1].toFixed(2);
    } else {
        const sortedValues = [...YColumn].sort((a, b) => a - b);
        saturationValue = sortedValues[Math.floor(YColumn.length / 2)];
        timeToSaturation = XColumn[0];
        timeStartSaturation = XColumn[0];
    }

    return {
        slope: linearSlope,
        intercept: linearIntercept.toFixed(2),
        saturationValue,
        timeToSaturation,
        Vmax: Vmax.toFixed(6),
        linearYMin: linearYMin.toFixed(2),
        linearYMax: linearYMax.toFixed(2),
        linearXMin: linearStartIdx !== -1 ? linearXMin.toFixed(2) : null,
        linearXMax: linearEndIdx !== -1 ? linearXMax.toFixed(2) : null,
        startVMax: startVMax !== -1 ? XColumn[startVMax].toFixed(2) : null,
        endVMax: endVMax !== -1 ? XColumn[endVMax].toFixed(2) : null,
        yVMaxstart,
        yVMaxend,
        timeStartSaturation
    };
}

// Linear regression: Returns slope and intercept
function linearRegression(x, y) {
    const n = x.length;
    const sumX = x.reduce((sum, xi) => sum + xi, 0);
    const sumY = y.reduce((sum, yi) => sum + yi, 0);
    const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
    const sumXX = x.reduce((sum, xi) => sum + xi * xi, 0);

    const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
    const intercept = (sumY - slope * sumX) / n;

    return [ slope, intercept ];
}

// Linear regression slope
function linearRegressionSlope(x, y) {
    return linearRegression(x, y)[0];
}

// Polynomial regression: Returns coefficients [c0, c1, c2, ...] for degree
function polynomialRegression(x, y, degree) {
    const n = x.length;
    const X = Array(2 * degree + 1).fill(0);
    const Y = Array(degree + 1).fill(0);

    // Build Vandermonde matrix sums
    for (let i = 0; i < n; i++) {
        for (let j = 0; j <= 2 * degree; j++) {
            X[j] = (X[j] || 0) + Math.pow(x[i], j);
        }
        for (let j = 0; j <= degree; j++) {
            Y[j] = (Y[j] || 0) + y[i] * Math.pow(x[i], j);
        }
    }

    // Solve system: X_matrix * coeffs = Y
    const X_matrix = Array(degree + 1).fill().map((_, i) =>
        Array(degree + 1).fill().map((_, j) => X[i + j])
    );
    const coeffs = gaussianElimination(X_matrix, Y);
    return coeffs;
}

// Polynomial regression slope (approximated as derivative at midpoint)
function polynomialRegressionSlope(x, y, degree) {
    const coeffs = polynomialRegression(x, y, degree);
    const midX = (Math.max(...x) + Math.min(...x)) / 2;
    let slope = 0;
    for (let i = 1; i < coeffs.length; i++) {
        slope += i * coeffs[i] * Math.pow(midX, i - 1);
    }
    return slope;
}

// Logarithmic regression: y = a * ln(x) + b
function logarithmicRegression(x, y) {
    const n = x.length;
    const lnX = x.map(xi => Math.log(xi));
    const sumLnX = lnX.reduce((sum, xi) => sum + xi, 0);
    const sumY = y.reduce((sum, yi) => sum + yi, 0);
    const sumLnXY = lnX.reduce((sum, lnx, i) => sum + lnx * y[i], 0);
    const sumLnX2 = lnX.reduce((sum, lnx) => sum + lnx * lnx, 0);

    const a = (n * sumLnXY - sumLnX * sumY) / (n * sumLnX2 - sumLnX * sumLnX);
    const b = (sumY - a * sumLnX) / n;

    return [ a, b ];
}

// Logarithmic regression slope (approximated at midpoint)
function logarithmicRegressionSlope(x, y) {
    const { a } = logarithmicRegression(x, y);
    const midX = (Math.max(...x) + Math.min(...x)) / 2;
    return a / midX; // Derivative of a*ln(x) + b is a/x
}

// Gaussian elimination for solving linear systems
function gaussianElimination(A, b) {
    const n = b.length;
    const augmented = A.map((row, i) => [...row, b[i]]);

    // Forward elimination
    for (let i = 0; i < n; i++) {
        let maxEl = Math.abs(augmented[i][i]);
        let maxRow = i;
        for (let k = i + 1; k < n; k++) {
            if (Math.abs(augmented[k][i]) > maxEl) {
                maxEl = Math.abs(augmented[k][i]);
                maxRow = k;
            }
        }

        // Swap rows
        [augmented[i], augmented[maxRow]] = [augmented[maxRow], augmented[i]];

        // Eliminate column
        for (let k = i + 1; k < n; k++) {
            const c = -augmented[k][i] / augmented[i][i];
            for (let j = i; j <= n; j++) {
                augmented[k][j] += c * augmented[i][j];
            }
        }
    }

    // Back substitution
    const x = Array(n).fill(0);
    for (let i = n - 1; i >= 0; i--) {
        x[i] = augmented[i][n] / augmented[i][i];
        for (let k = i - 1; k >= 0; k--) {
            augmented[k][n] -= augmented[k][i] * x[i];
        }
    }

    return x;
}

function getEstimatedValue(data, timepoint, blankType = "MIXED", maxTolerance = 60) {
    if (!Array.isArray(data) || data.length === 0) return null;

    // Sort data by timestamp
    data.sort((a, b) => a["Timestamp"] - b["Timestamp"]);

    // Filter data based on blankType
    const filteredData = data.filter(item => {
        if (blankType === "MIXED") return true;
        if (blankType === "BLANKED") return item["Blanked"] === true; // Changed from "Blank" to "Blanked"
        if (blankType === "NON-BLANKED") return item["Blanked"] === false; // Changed from "Blank" to "Blanked"
        return true; // Default to MIXED behavior
    });

    if (filteredData.length === 0) return null;

    // Loop to find the two surrounding points
    for (let i = 0; i < filteredData.length - 1; i++) {
        const t1 = filteredData[i]["Timestamp"];
        const t2 = filteredData[i + 1]["Timestamp"];

        // Exact match
        if (t1 === timepoint) return filteredData[i]["Value"];
        if (t2 === timepoint) return filteredData[i + 1]["Value"];

        // Surrounding range for interpolation
        if (t1 < timepoint && timepoint < t2) {
            const minDiff = Math.min(Math.abs(timepoint - t1), Math.abs(timepoint - t2));
            if (minDiff > maxTolerance) return null;

            const v1 = filteredData[i]["Value"];
            const v2 = filteredData[i + 1]["Value"];

            const ratio = (timepoint - t1) / (t2 - t1);
            return v1 + ratio * (v2 - v1);
        }
    }

    // Check ends if out-of-bounds but within tolerance
    const first = filteredData[0], last = filteredData[filteredData.length - 1];
    if (Math.abs(timepoint - first["Timestamp"]) <= maxTolerance) return first["Value"];
    if (Math.abs(timepoint - last["Timestamp"]) <= maxTolerance) return last["Value"];

    return null;
}

function getUniqueColumnEntries(data, columnName="TimePoint") {
    const uniqueColumnEntries = new Set(data.map(row => row[columnName]).filter(tp => tp));
    return Array.from(uniqueColumnEntries);
}

function arraysEqual(arr1, arr2) {
    if (arr1.length !== arr2.length) return false;
    return arr1.every((value, index) => value === arr2[index]);
}

function computeFit(value, fit_type, coef) {
    switch (fit_type.toLowerCase()) {
        case "linear":
            // Expect coef = [a, b]
            if (coef.length < 2) throw new Error("Linear fit requires 2 coefficients: [a, b]");
            return coef[0] * value + coef[1];

        case "polynomial":
            // Expect coef = [a, b, c]
            if (coef.length < 3) throw new Error("Polynomial fit requires 3 coefficients: [a, b, c]");
            return coef[0] * Math.pow(value, 2) + coef[1] * value + coef[2];

        case "logarithmic":
            // Expect coef = [a, b]
            if (coef.length < 2) throw new Error("Logarithmic fit requires 2 coefficients: [a, b]");
            if (value <= 0) throw new Error("Invalid input for logarithm: value must be > 0");
            return coef[0] * Math.log(value) + coef[1];

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
        const avg = yValues.reduce((sum, value) => sum + value, 0) / yValues.length;
        averagedY.push(avg);
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