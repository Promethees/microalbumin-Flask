// function calculateSlopeAndSaturation(data, windowSize, algo = 'linear') {
//     if (!data || data.length < windowSize || windowSize < 3) {
//         return { slope: 0, saturation: 0 };
//     }

//     // Use first windowSize points
//     const subset = data.slice(0, windowSize);
//     const x = subset.map(d => d.time);
//     const y = subset.map(d => d.value);

//     let slope = 0;
//     let saturation = Math.max(...y); // Default: max value in window

//     switch (algo.toLowerCase()) {
//         case 'linear':
//             slope = linearRegressionSlope(x, y);
//             break;
//         case 'polynomial':
//             slope = polynomialRegressionSlope(x, y, 2);
//             // Estimate saturation as max fitted value
//             const polyCoeffs = polynomialRegression(x, y, 2);
//             saturation = Math.max(...x.map(xi => polyCoeffs.reduce((sum, c, i) => sum + c * Math.pow(xi, i), 0)));
//             break;
//         case 'logarithmic':
//             slope = logarithmicRegressionSlope(x, y);
//             // Estimate saturation as asymptote (approximated)
//             const { a, b } = logarithmicRegression(x, y);
//             saturation = a * Math.log(Math.max(...x)) + b;
//             break;
//         default:
//             slope = 0;
//             saturation = 0;
//     }

//     return { slope, saturation };
// }

// function estimateValue(data, timePoint, algo = 'linear') {
//     if (!data || data.length < 2 || !timePoint) {
//         return 0;
//     }

//     const x = data.map(d => d.time);
//     const y = data.map(d => d.value);

//     switch (algo.toLowerCase()) {
//         case 'linear':
//             const { slope, intercept } = linearRegression(x, y);
//             return slope * timePoint + intercept;
//         case 'polynomial':
//             const coeffs = polynomialRegression(x, y, 2);
//             return coeffs.reduce((sum, c, i) => sum + c * Math.pow(timePoint, i), 0);
//         case 'logarithmic':
//             const { a, b } = logarithmicRegression(x, y);
//             return a * Math.log(timePoint) + b;
//         default:
//             return 0;
//     }
// }

// // Linear regression: Returns slope and intercept
// function linearRegression(x, y) {
//     const n = x.length;
//     const sumX = x.reduce((sum, xi) => sum + xi, 0);
//     const sumY = y.reduce((sum, yi) => sum + yi, 0);
//     const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
//     const sumXX = x.reduce((sum, xi) => sum + xi * xi, 0);

//     const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
//     const intercept = (sumY - slope * sumX) / n;

//     return { slope, intercept };
// }

// // Linear regression slope
// function linearRegressionSlope(x, y) {
//     return linearRegression(x, y).slope;
// }

// // Polynomial regression: Returns coefficients [c0, c1, c2, ...] for degree
// function polynomialRegression(x, y, degree) {
//     const n = x.length;
//     const X = Array(2 * degree + 1).fill(0);
//     const Y = Array(degree + 1).fill(0);

//     // Build Vandermonde matrix sums
//     for (let i = 0; i < n; i++) {
//         for (let j = 0; j <= 2 * degree; j++) {
//             X[j] = (X[j] || 0) + Math.pow(x[i], j);
//         }
//         for (let j = 0; j <= degree; j++) {
//             Y[j] = (Y[j] || 0) + y[i] * Math.pow(x[i], j);
//         }
//     }

//     // Solve system: X_matrix * coeffs = Y
//     const X_matrix = Array(degree + 1).fill().map((_, i) =>
//         Array(degree + 1).fill().map((_, j) => X[i + j])
//     );
//     const coeffs = gaussianElimination(X_matrix, Y);
//     return coeffs;
// }

// // Polynomial regression slope (approximated as derivative at midpoint)
// function polynomialRegressionSlope(x, y, degree) {
//     const coeffs = polynomialRegression(x, y, degree);
//     const midX = (Math.max(...x) + Math.min(...x)) / 2;
//     let slope = 0;
//     for (let i = 1; i < coeffs.length; i++) {
//         slope += i * coeffs[i] * Math.pow(midX, i - 1);
//     }
//     return slope;
// }

// // Logarithmic regression: y = a * ln(x) + b
// function logarithmicRegression(x, y) {
//     const n = x.length;
//     const lnX = x.map(xi => Math.log(xi));
//     const sumLnX = lnX.reduce((sum, xi) => sum + xi, 0);
//     const sumY = y.reduce((sum, yi) => sum + yi, 0);
//     const sumLnXY = lnX.reduce((sum, lnx, i) => sum + lnx * y[i], 0);
//     const sumLnX2 = lnX.reduce((sum, lnx) => sum + lnx * lnx, 0);

//     const a = (n * sumLnXY - sumLnX * sumY) / (n * sumLnX2 - sumLnX * sumLnX);
//     const b = (sumY - a * sumLnX) / n;

//     return { a, b };
// }

// // Logarithmic regression slope (approximated at midpoint)
// function logarithmicRegressionSlope(x, y) {
//     const { a } = logarithmicRegression(x, y);
//     const midX = (Math.max(...x) + Math.min(...x)) / 2;
//     return a / midX; // Derivative of a*ln(x) + b is a/x
// }

// // Gaussian elimination for solving linear systems
// function gaussianElimination(A, b) {
//     const n = b.length;
//     const augmented = A.map((row, i) => [...row, b[i]]);

//     // Forward elimination
//     for (let i = 0; i < n; i++) {
//         let maxEl = Math.abs(augmented[i][i]);
//         let maxRow = i;
//         for (let k = i + 1; k < n; k++) {
//             if (Math.abs(augmented[k][i]) > maxEl) {
//                 maxEl = Math.abs(augmented[k][i]);
//                 maxRow = k;
//             }
//         }

//         // Swap rows
//         [augmented[i], augmented[maxRow]] = [augmented[maxRow], augmented[i]];

//         // Eliminate column
//         for (let k = i + 1; k < n; k++) {
//             const c = -augmented[k][i] / augmented[i][i];
//             for (let j = i; j <= n; j++) {
//                 augmented[k][j] += c * augmented[i][j];
//             }
//         }
//     }

//     // Back substitution
//     const x = Array(n).fill(0);
//     for (let i = n - 1; i >= 0; i--) {
//         x[i] = augmented[i][n] / augmented[i][i];
//         for (let k = i - 1; k >= 0; k--) {
//             augmented[k][n] -= augmented[k][i] * x[i];
//         }
//     }

//     return x;
// }

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

                case "logarit":
                case "logarithmic":
                    // Expect coef = [a, b]
                    if (coef.length < 2) throw new Error("Logarithmic fit requires 2 coefficients: [a, b]");
                    if (coef[1] * value <= 0) throw new Error("Invalid input for logarithm: b * value must be > 0");
                    return coef[0] * Math.log(coef[1] * value);

                default:
                    throw new Error("Unknown fit type: " + fit_type);
            }
        }


function calculateSlopeAndSaturation(allTimestamps, allValues, window_size) {
    if (allTimestamps.length < 2 || allValues.length < 2 || window_size < 2 || window_size > allTimestamps.length) {
        return { slope: 0, intercept: 0, saturationValue: "--", timeToSaturation: "--", Vmax: 0, linearSlope: 0, linearYMin: 0, linearYMax: 0, linearXMin: 0, linearXMax: 0 };
    }

    // Function to calculate R-squared for linear regression
    function calculateRSquared(x, y, slope, intercept) {
        let n = x.length;
        let sumY = y.reduce((a, b) => a + b, 0);
        let meanY = sumY / n;
        let ssTot = y.reduce((a, b) => a + Math.pow(b - meanY, 2), 0);
        let ssRes = x.reduce((a, b, i) => a + Math.pow(y[i] - (slope * b + intercept), 2), 0);
        return ssTot === 0 ? 1 : 1 - ssRes / ssTot;
    }

    // Calculate local slopes and R-squared for each window
    let localSlopes = [];
    let intercepts = [];
    let rSquaredValues = [];
    for (let i = 0; i <= allTimestamps.length - window_size; i++) {
        let x = allTimestamps.slice(i, i + window_size);
        let y = allValues.slice(i, i + window_size);

        let n = x.length;
        let sumX = x.reduce((a, b) => a + b, 0);
        let sumY = y.reduce((a, b) => a + b, 0);
        let sumXY = x.reduce((a, b, i) => a + b * y[i], 0);
        let sumXX = x.reduce((a, b) => a + b * b, 0);

        let slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX) || 0; // in units/second
        let intercept = (sumY - slope * sumX) / n;

        let rSquared = calculateRSquared(x, y, slope, intercept);
        localSlopes.push(slope);
        intercepts.push(intercept);
        rSquaredValues.push(rSquared);
    }

    // Find Vmax (maximum slope with R-squared >= 0.95)
    let Vmax = 0;
    let threshold = 0.2 // Vmax must be larger than threshold per hour
    let startVMax = -1;
    let endVMax = -1;
    let yVMaxstart = 0;
    let yVMaxend = 0;
    for (let i = 0; i < localSlopes.length; i++) {
        adjustedLocal = 3600*localSlopes[i];
        if (rSquaredValues[i] >= 0.95 && localSlopes[i] > Vmax && adjustedLocal > threshold) {
            Vmax = localSlopes[i];
            startVMax = Number(i);
            endVMax = startVMax + Number(window_size) - 1;
            yVMaxstart = Vmax*allTimestamps[startVMax] + intercepts[i];
            yVMaxend = Vmax*allTimestamps[endVMax] + intercepts[i];
        }
    }
    
    
    // Determine linear period (slopes >= 0.8 * Vmax)
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
    

    // Calculate linear period parameters
    let linearSlope = null;
    let linearIntercept = 0;
    let linearXMin = 0;
    let linearXMax = 0;
    let linearYMin = 0;
    let linearYMax = 0;
    let saturationValue = "--";
    let timeToSaturation = "--";

    if (linearStartIdx !== -1 && linearEndIdx !== -1) {
        // Adjust indices to include full window at the end
        let start = linearStartIdx;
        let end = linearEndIdx + window_size;

        if (end > allTimestamps.length) {
            end = allTimestamps.length;
        }

        let x = allTimestamps.slice(start, end);
        let y = allValues.slice(start, end);

        // Linear regression for the entire linear period
        let n = x.length;
        let sumX = x.reduce((a, b) => a + b, 0);
        let sumY = y.reduce((a, b) => a + b, 0);
        let sumXY = x.reduce((a, b, i) => a + b * y[i], 0);
        let sumXX = x.reduce((a, b) => a + b * b, 0);

        linearSlope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX) || 0; // In units/second
        linearIntercept = (sumY - linearSlope * sumX) / n;

        linearXMin = allTimestamps[start]; //in seconds
        linearXMax = allTimestamps[end - 1];
        linearYMin = linearSlope*linearXMin + linearIntercept; // in units (absorbance)
        linearYMax = linearSlope*linearXMax + linearIntercept;

        // Saturation point (end of linear period)
        // saturationValue = end < allValues.length ? linearYMax.toFixed(2) : "--";
        if (end >= allValues.length) {
            saturationValue = "--";
        } else {
            let theRest = allValues.slice(end, allValues.length);
            sortedValuesForRest = [...theRest].sort((a, b) => a - b);
            saturationValue = sortedValuesForRest[Math.floor(theRest.length/2)].toFixed(2);
        }
        timeToSaturation = end < allTimestamps.length ? (allTimestamps[end - 1] - allTimestamps[start]).toFixed(2) : null;
        timeStartSaturation = end < allTimestamps.length ? (allTimestamps[end - 1]).toFixed(2) : null;
    } else {
        sortedValues = [...allValues].sort((a, b) => a - b);
        saturationValue = sortedValues[allValues.length/2];
        timeToSaturation = allTimestamps[0];
        timeStartSaturation = allTimestamps[0];
    }
    return {
        slope: linearSlope, // Overall slope for compatibility
        intercept: linearIntercept.toFixed(2),
        saturationValue,
        timeToSaturation,
        Vmax: Vmax.toFixed(6),
        linearYMin: linearYMin.toFixed(2),
        linearYMax: linearYMax.toFixed(2),
        linearXMin: linearStartIdx !== -1 ? linearXMin.toFixed(2) : null,
        linearXMax: linearEndIdx !== -1 ? linearXMax.toFixed(2) : null,
        startVMax: startVMax !== -1 ? allTimestamps[startVMax].toFixed(2) : null,
        endVMax: endVMax !== -1 ? allTimestamps[endVMax].toFixed(2) : null,
        yVMaxstart: yVMaxstart,
        yVMaxend: yVMaxend,
        timeStartSaturation: timeStartSaturation,
    };
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