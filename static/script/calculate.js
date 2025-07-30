// Helper function to calculate R-squared
function computeRSquared(actual, predicted) {
    if (actual.length !== predicted.length || actual.length < 1) return 0;
    const meanY = actual.reduce((sum, yi) => sum + yi, 0) / actual.length;
    const ssTotal = actual.reduce((sum, yi) => sum + Math.pow(yi - meanY, 2), 0);
    const ssResidual = actual.reduce((sum, yi, i) => sum + Math.pow(yi - predicted[i], 2), 0);
    return ssTotal === 0 ? 0 : 1 - ssResidual / ssTotal;
}

function calculateCoefAndRSquared(x, y, algo = "linear") {
    // Preprocess the data first
    const { x: processedX, y: processedY } = mapDuplicates(x, y);
    
    if (processedX.length !== processedY.length || processedX.length < 2) {
        return { slope: 0, rSquared: 0, coefficients: null };
    }

    let slope = 0;
    let predicted = [];
    let coefficients = null;
    let rSquared = 0;

    switch (algo) {
        case "polynomial":
            try {
                const degree = 2;
                coefficients = polynomialRegression(processedX, processedY, degree);
                if (!coefficients || !Array.isArray(coefficients)) {
                    throw new Error("polynomialRegression returned invalid coefficients");
                }
                predicted = processedX.map(xi =>
                    coefficients.reduce((acc, c, i) => acc + c * Math.pow(xi, i), 0)
                );
                slope = polynomialRegressionSlope(processedX, processedY, degree);
                rSquared = computeRSquared(processedY, predicted);
            } catch (error) {
                console.error("Error in polynomial regression:", error.message);
                return { slope: 0, rSquared: 0, coefficients: null };
            }
            break;

        case "logarithmic":
            try {
                coefficients = logarithmicRegression(processedX, processedY);
                if (!coefficients || !Array.isArray(coefficients)) {
                    throw new Error("logarithmicRegression returned invalid coefficients");
                }
                predicted = processedX.map(xi => coefficients[0] * Math.log(xi + coefficients[1]) + coefficients[2]);
                slope = logarithmicRegressionSlope(processedX, processedY);
                rSquared = computeRSquared(processedY, predicted);
            } catch (error) {
                console.error("Error in logarithmic regression:", error.message);
                return { slope: 0, rSquared: 0, coefficients: null };
            }
            break;

        case "exponential":
            try {
                coefficients = exponentialRegression(processedX, processedY);
                if (!coefficients || !Array.isArray(coefficients) || coefficients.length < 3) {
                    throw new Error("exponentialRegression returned invalid coefficients");
                }
                predicted = processedX.map(xi => coefficients[0] * Math.exp(xi * coefficients[1]) + coefficients[2]);
                slope = exponentialRegressionSlope(processedX, processedY);
                rSquared = computeRSquared(processedY, predicted);
            } catch (error) {
                console.error("Error in exponential regression:", error.message);
                return { slope: 0, rSquared: 0, coefficients: null };
            }
            break;

        case "Michaelis-Menten":
            try {
                const expCoeffsMM = michaelisMentenConcentrationRegression(processedX, processedY);
                if (!expCoeffsMM || !expCoeffsMM.Vmax || !expCoeffsMM.Km) {
                    throw new Error("michaelisMentenConcentrationRegression returned invalid coefficients");
                }
                coefficients = [expCoeffsMM.Vmax, expCoeffsMM.Km];
                predicted = processedX.map(xi => coefficients[1] * xi / (coefficients[0] - xi));
                slope = coefficients[1] / (coefficients[0] - 1);
                rSquared = computeRSquared(processedY, predicted);
            } catch (error) {
                console.error("Error in Michaelis-Menten regression:", error.message);
                return { slope: 0, rSquared: 0, coefficients: null };
            }
            break;

        case "linear":
        default:
            try {
                const lin = linearRegression(processedX, processedY);
                if (!lin || !Array.isArray(lin)) {
                    throw new Error("linearRegression returned invalid coefficients");
                }
                coefficients = lin;
                slope = lin[0];
                predicted = processedX.map(xi => slope * xi + lin[1]);
                rSquared = computeRSquared(processedY, predicted);
            } catch (error) {
                console.error("Error in linear regression:", error.message);
                return { slope: 0, rSquared: 0, coefficients: null };
            }
            break;
    }

    return { 
        slope: slope, 
        rSquared: rSquared, 
        coefficients: coefficients 
    };
}


function calculateKineticsQuantities(XColumn, YColumn, window_size) {
    if (XColumn.length < 2 || YColumn.length < 2 || window_size < 2 || window_size > XColumn.length) {
        return { slope: 0, intercept: 0, saturationValue: "--", timeToSaturation: "--", maxRate: 0, linearSlope: 0, linearYMin: 0, linearYMax: 0, linearXMin: 0, linearXMax: 0 };
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

    let maxRate = 0;
    let threshold = 0.2;
    let startMaxRate = -1;
    let endMaxRate = -1;
    let yMaxRateStart = 0;
    let yMaxRateEnd = 0;

    for (let i = 0; i < localSlopes.length; i++) {
        const adjustedLocal = 3600 * localSlopes[i];
        if (rSquaredValues[i] >= 0.95 && localSlopes[i] > maxRate && adjustedLocal > threshold) {
            maxRate = localSlopes[i];
            startMaxRate = i;
            endMaxRate = startMaxRate + Number(window_size) - 1;
            yMaxRateStart = maxRate * XColumn[startMaxRate] + intercepts[i];
            yMaxRateEnd = maxRate * XColumn[endMaxRate] + intercepts[i];
        }
    }

    let linearStartIdx = -1;
    let linearEndIdx = -1;
    if (maxRate !== 0) {
        for (let i = 0; i < localSlopes.length; i++) {
            if (localSlopes[i] >= 0.7 * maxRate) {
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
        maxRate: maxRate.toFixed(6),
        linearYMin: linearYMin.toFixed(2),
        linearYMax: linearYMax.toFixed(2),
        linearXMin: linearStartIdx !== -1 ? linearXMin.toFixed(2) : null,
        linearXMax: linearEndIdx !== -1 ? linearXMax.toFixed(2) : null,
        startMaxRate: startMaxRate !== -1 ? XColumn[startMaxRate].toFixed(2) : null,
        endMaxRate: endMaxRate !== -1 ? XColumn[endMaxRate].toFixed(2) : null,
        yMaxRateStart,
        yMaxRateEnd,
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

// Logarithmic regression: y = a * ln(x + b) + c
function logarithmicRegression(x, y) {
    // Ensure x + b > 0, so b > -min(x)
    const minX = Math.min(...x);
    if (minX <= 0) {
        // Initialize b slightly above -minX to ensure x + b > 0
        let b = -minX + 0.1;
        let bestB = b;
        let bestRSquared = -Infinity;
        let bestCoeffs = null;

        // Try a range of b values
        const step = 0.1;
        const maxSteps = 100;
        for (let i = 0; i < maxSteps; i++) {
            // Transform x to ln(x + b)
            const transformedX = x.map(xi => {
                if (xi + b <= 0) return null;
                return Math.log(xi + b);
            });

            // Filter out invalid data points
            const validData = x.reduce((acc, xi, i) => {
                if (transformedX[i] !== null && !isNaN(transformedX[i]) && isFinite(transformedX[i])) {
                    acc.x.push(transformedX[i]);
                    acc.y.push(y[i]);
                }
                return acc;
            }, { x: [], y: [] });

            if (validData.x.length < 2) {
                b += step;
                continue;
            }

            // Perform linear regression on ln(x + b) and y
            const [a, c] = linearRegression(validData.x, validData.y);
            
            // Compute R-squared
            const predicted = validData.x.map(xi => a * xi + c);
            const rSquared = computeRSquared(validData.y, predicted);
            
            if (rSquared > bestRSquared) {
                bestRSquared = rSquared;
                bestB = b;
                bestCoeffs = [a, bestB, c];
            }
            
            b += step;
        }

        return bestCoeffs || null;
    } else {
        // If all x > 0, start with b = 0
        let b = 0;
        let bestB = b;
        let bestRSquared = -Infinity;
        let bestCoeffs = null;

        const step = 0.1;
        const maxSteps = 100;
        for (let i = 0; i < maxSteps; i++) {
            const transformedX = x.map(xi => {
                if (xi + b <= 0) return null;
                return Math.log(xi + b);
            });

            const validData = x.reduce((acc, xi, i) => {
                if (transformedX[i] !== null && !isNaN(transformedX[i]) && isFinite(transformedX[i])) {
                    acc.x.push(transformedX[i]);
                    acc.y.push(y[i]);
                }
                return acc;
            }, { x: [], y: [] });

            if (validData.x.length < 2) {
                b += step;
                continue;
            }

            const [a, c] = linearRegression(validData.x, validData.y);
            const predicted = validData.x.map(xi => a * xi + c);
            const rSquared = computeRSquared(validData.y, predicted);

            if (rSquared > bestRSquared) {
                bestRSquared = rSquared;
                bestB = b;
                bestCoeffs = [a, bestB, c];
            }

            b += step;
        }

        return bestCoeffs || null;
    }
}

// Logarithmic regression slope (approximated at midpoint)
function logarithmicRegressionSlope(x, y) {
    const coeffs = logarithmicRegression(x, y);
    if (!coeffs) return 0;
    const [a, b] = coeffs;
    const midX = (Math.max(...x) + Math.min(...x)) / 2;
    return a / (midX + b); // Derivative of a * ln(x + b) + c is a / (x + b)
}

// Exponential regression: y = a * e^(b * x) + c
function exponentialRegression(x, y) {
    // Initial guess for c: minimum y value or mean if all positive
    const c = Math.min(...y) > 0 ? Math.min(...y) : y.reduce((sum, yi) => sum + yi, 0) / y.length;
    
    // Transform y to y' = y - c, then take logarithm: ln(y' - c) = ln(a) + b*x
    const transformedY = y.map(yi => {
        const diff = yi - c;
        if (diff <= 0) return null; // Handle non-positive values
        return Math.log(diff);
    });
    
    // Filter out invalid data points
    const validData = x.reduce((acc, xi, i) => {
        if (transformedY[i] !== null && !isNaN(transformedY[i]) && isFinite(transformedY[i])) {
            acc.x.push(xi);
            acc.y.push(transformedY[i]);
        }
        return acc;
    }, { x: [], y: [] });

    if (validData.x.length < 2) return null;

    // Perform linear regression on x and ln(y - c)
    const [b, lnA] = linearRegression(validData.x, validData.y);
    const a = Math.exp(lnA);

    return [a, b, c];
}

// Exponential regression slope (approximated at midpoint)
function exponentialRegressionSlope(x, y) {
    const coeffs = exponentialRegression(x, y);
    if (!coeffs) return 0;
    const [a, b] = coeffs;
    const midX = (Math.max(...x) + Math.min(...x)) / 2;
    return a * b * Math.exp(b * midX); // Derivative of a * e^(b*x) + c is a * b * e^(b*x)
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

// Michaelis-Menten function: [S] = (Km * v) / (Vmax - v)
function mmFunction(params, rates) {
    const [Vmax, Km] = params;
    // Return a large value for invalid parameters to guide optimization
    if (Vmax <= 0 || Km <= 0) {
        return rates.map(() => Infinity);
    }
    return rates.map(v => {
        if (v >= Vmax || v < 0) {
            return Infinity; // Handle invalid rates gracefully
        }
        return (Km * v) / (Vmax - v);
    });
}

// Residual function for optimization
function residual(params, rates, substrates) {
    const predicted = mmFunction(params, rates);
    return predicted.map((pred, i) => pred === Infinity ? Infinity : pred - substrates[i]);
}

// Derive Vmax, Km coefficients for Michaelis-Menten concentration regression
function michaelisMentenConcentrationRegression(rates, substrates) {
    // Input validation
    if (!Array.isArray(rates) || !Array.isArray(substrates) || rates.length !== substrates.length || rates.length === 0) {
        return { error: "Invalid input: rates and substrates must be arrays of equal length and non-empty" };
    }
    if (rates.some(v => !Number.isFinite(v)) || substrates.some(s => !Number.isFinite(s) || s < 0)) {
        return { error: "Invalid input: rates and substrates must contain finite, non-negative numbers" };
    }

    // Initial guess for parameters [Vmax, Km]
    const VmaxGuess = Math.max(...rates) * 1.1; // Slightly overestimate Vmax
    const halfMaxRateIndex = rates.findIndex(v => v >= VmaxGuess / 2);
    const KmGuess = halfMaxRateIndex !== -1 ? substrates[halfMaxRateIndex] : substrates[Math.floor(substrates.length / 2)];

    const initialParams = [VmaxGuess, KmGuess];

    try {
        // Perform Levenberg-Marquardt optimization (assuming numeric.levmar exists)
        const result = numeric.uncmin(
            params => numeric.norm2(residual(params, rates, substrates)),
            initialParams
        );

        const [Vmax, Km] = result.solution;

        // Validate fitted parameters
        if (Vmax <= 0 || Km <= 0) {
            return { error: "Optimization resulted in invalid parameters (Vmax or Km non-positive)" };
        }

        return { Vmax, Km };
    } catch (error) {
        return { error: `Optimization failed: ${error.message}` };
    }
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
    return Array.from(uniqueColumnEntries).sort((a, b) => Number(b) - Number(a));
}

function arraysEqual(arr1, arr2) {
    if (arr1.length !== arr2.length) return false;
    return arr1.every((value, index) => value === arr2[index]);
}

function computeFit(value, fit_type, coef) {
    if (coef[0] === 'NONE' || coef[0] === 'NaN') {
        throw new Error(`Fit_type: ${fit_type} cannot be used to derive concentration from ${$("#regressed-quantity").val()}`);
    }
    switch (fit_type.toLowerCase()) {
        case "linear":
            // Expect coef = [a, b]
            if (coef.length !== 2) throw new Error("Linear fit requires 2 coefficients: [a, b]");
            return coef[0] * value + coef[1];

        case "polynomial":
            // Expect coef = [a, b, c]
            if (coef.length !== 3) throw new Error("Polynomial fit requires 3 coefficients: [a, b, c]");
            return coef[0] * Math.pow(value, 2) + coef[1] * value + coef[2];

        case "logarithmic":
            // Expect coef = [a, b, c]
            if (coef.length !== 3) throw new Error("Logarithmic fit requires 3 coefficients: [a, b, c]");
            if (value <= 0) throw new Error("Invalid input for logarithm: value must be > 0");
            return coef[0] * Math.log(value + coef[1]) + coef[2];

        case "exponential":
            // Expect coef = [a, b, c]
            if (coef.length !== 3) throw new Error("Exponential fit requires 3 coefficients: [a, b, c]");
            return coef[0] * Math.exp(value * coef[1]) + coef[2];

        case "michaelis-menten":
            // Expect coef = [Vmax, Km]
            if (coef.length !== 2) throw new Error("Michaelis-Menten fit requires 2 coefficients: [Vmax, Km]");
            if (value >= coef[0] || value < 0) throw new Error(`Invalid input for Michaelis-Menten: value ${value}/minute must be < Vmax: ${coef[0]} and >= 0`);
            return (coef[1] * value) / (coef[0] - value);

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

function mapDuplicates(x, y) {
    // Create a map to store sum and count of y values for each x
    const xMap = new Map();
    
    // Process each pair
    for (let i = 0; i < x.length; i++) {
        const currentX = x[i];
        const currentY = y[i];
        
        // Skip if y is "NONE"
        if (currentY === "NONE") continue;
        
        if (!xMap.has(currentX)) {
            xMap.set(currentX, { sum: currentY, count: 1 });
        } else {
            const entry = xMap.get(currentX);
            entry.sum += currentY;
            entry.count++;
        }
    }
    
    // Convert the map back to arrays
    const processedX = [];
    const processedY = [];
    
    xMap.forEach((value, key) => {
        processedX.push(key);
        processedY.push(value.sum / value.count);
    });
    
    return { x: processedX, y: processedY };
}