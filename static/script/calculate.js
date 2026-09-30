// AJAX wrapper for calculateCoefAndRSquared
function calculateCoefAndRSquared(x, y, regressAlgo = "linear") {
    let result = { slope: 0, rSquared: 0, coefficients: null };
    $.ajax({
        url: '/calculate_coef_and_rsquared',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ x: x, y: y, regress_algo: regressAlgo }),
        async: false,
        success: function (response) {
            if (response.status === 'success') {
                result = response.result;
            } else {
                console.error("Math API error:", response.message);
            }
        },
        error: function (jqXHR, textStatus, errorThrown) {
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
        success: function (response) {
            if (response.status === 'success') {
                result = response.result;
            } else {
                console.error("Math API error:", response.message);
            }
        },
        error: function (jqXHR, textStatus, errorThrown) {
            console.error("AJAX Error:", textStatus, errorThrown);
        }
    });
    return result;
}

// Every source of one file in one synchronous request (was one per source).
// Returns one result per entry of YColumns; a source the server could not
// analyse gets the same defaults calculateKineticsQuantities() falls back to.
function calculateKineticsQuantitiesBatch(XColumn, YColumns, window_size) {
    const fallback = () => ({ slope: 0, intercept: 0, saturationValue: "--", timeToSaturation: "--", maxRate: 0, linearSlope: 0, linearYMin: 0, linearYMax: 0, linearXMin: 0, linearXMax: 0 });
    let results = YColumns.map(fallback);
    $.ajax({
        url: '/calculate_kinetics_quantities_batch',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ XColumn: XColumn, YColumns: YColumns, window_size: window_size }),
        async: false,
        success: function (response) {
            if (response.status === 'success' && Array.isArray(response.results)) {
                results = YColumns.map((_, i) => response.results[i] || fallback());
            } else {
                console.error("Math API error:", response.message);
            }
        },
        error: function (jqXHR, textStatus, errorThrown) {
            console.error("AJAX Error:", textStatus, errorThrown);
        }
    });
    return results;
}

function getEstimatedValue(data, timepoint, sourceIndex, maxTolerance = 60) {
    if (!Array.isArray(data) || data.length === 0 || !timepoint) return null;

    // Pick which key to use
    let valueKey = `Value:${sourceIndex}`; // e.g. Value:1, Value:2

    // Filter only rows with valid numeric values for this specific source
    const validData = data
        .filter(row => measNumber(row[valueKey]) !== null)
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
            // Same domain as math_ops.evaluate_curve (and excel_formula.py): the
            // logarithm's argument is x + b, not x.
            if (value + Number(coef["b"]) <= 0) throw new Error("Invalid input for logarithm: x + b must be > 0");
            return coef["a"] * Math.log(value + Number(coef["b"])) + coef["c"];

        case "exponential":
            // Expect coef = [a, b, c]
            if (Object.keys(coef).length !== 3) throw new Error("Exponential fit requires 3 coefficients: [a, b, c]");
            return coef["a"] * Math.exp(value * coef["b"]) + coef["c"];

        case "michaelis-menten":
            // Expect coef = [Vmax, Km]
            if (Object.keys(coef).length !== 2) throw new Error("Michaelis-Menten fit requires 2 coefficients: [Vmax, Km]");
            // Same domain as math_ops.evaluate_curve: only a zero denominator is
            // rejected. A rate outside 0..VMax yields a (negative) value, as the
            // server and the Excel formula do.
            if (Number(coef["VMax"]) - value === 0) throw new Error(`Invalid input for Michaelis-Menten: VMax - x is zero (VMax: ${coef["VMax"]})`);
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

    // Calculate average, min, max, and std for each group
    const uniqueX = [];
    const averagedY = [];
    const minY = [];
    const maxY = [];
    const stdY = [];

    for (let [x, yValues] of dataMap) {
        uniqueX.push(x);
        const validValues = yValues
            .map(measNumber)
            .filter(v => v !== null);

        if (validValues.length > 0) {
            const avg = validValues.reduce((sum, value) => sum + value, 0) / validValues.length;
            averagedY.push(avg);
            minY.push(arrayMin(validValues));
            maxY.push(arrayMax(validValues));

            // Calculate standard deviation
            if (validValues.length > 1) {
                const variance = validValues.reduce((sum, value) => sum + Math.pow(value - avg, 2), 0) / (validValues.length - 1);
                stdY.push(Math.sqrt(variance));
            } else {
                stdY.push(0);
            }
        } else {
            averagedY.push(null);
            minY.push(null);
            maxY.push(null);
            stdY.push(null);
        }
    }

    return { XColumn: uniqueX, YColumn: averagedY, minY: minY, maxY: maxY, stdY: stdY };
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
    // Create a map to store all y values for each x
    const xMap = new Map();

    // Process each pair
    for (let i = 0; i < x.length; i++) {
        const currentX = x[i];
        const currentY = y[i];

        // Skip or mark as gap when y is not a finite number: null, or one of the
        // device's sentinels (NONE / OVFL / INF — see short-hands.js).
        const val = measNumber(currentY);
        if (val === null) {
            if (!keepGaps) continue;
            if (!xMap.has(currentX)) {
                xMap.set(currentX, { values: [], hasValid: false });
            }
        } else {
            if (!xMap.has(currentX)) {
                xMap.set(currentX, { values: [val], hasValid: true });
            } else {
                const entry = xMap.get(currentX);
                entry.values.push(val);
                entry.hasValid = true;
            }
        }
    }

    // Convert the map back to flat arrays (maintaining duplicates)
    const processedX = [];
    const processedY = [];

    xMap.forEach((entry, key) => {
        if (entry.hasValid) {
            entry.values.forEach(v => {
                processedX.push(key);
                processedY.push(v);
            });
        } else if (keepGaps) {
            processedX.push(key);
            processedY.push(null);
        }
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
// ── Quick concentration calculator ───────────────────────────────────────────
// Standalone: type a curve's coefficients + a measured quantity value and get
// the derived concentration, with no CSV data file selected. Mirrors the applied
// -curve math server-side (/calculate_concentration → math_ops.evaluate_curve).
const QUICK_CONC_FIELDS = {
    linear: ['a', 'b'],
    polynomial: ['a', 'b', 'c'],
    logarithmic: ['a', 'b', 'c'],
    exponential: ['a', 'b', 'c'],
    'Michaelis-Menten': ['VMax', 'Km'],
};

function _quickConcCoefInputs(algo) {
    return (QUICK_CONC_FIELDS[algo] || QUICK_CONC_FIELDS.linear).map(k =>
        `<label style="display:flex;gap:6px;align-items:center;justify-content:space-between;margin:4px 0;">
            <span style="font-family:monospace;font-weight:600;">${k}</span>
            <input type="number" step="any" data-key="${k}" style="width:62%;padding:3px 6px;box-sizing:border-box;">
        </label>`).join('');
}

function quickConcentrationCalc() {
    const algos = Object.keys(QUICK_CONC_FIELDS);
    Swal.fire({
        title: t('quickconc.title', 'Quick concentration'),
        html: `<div style="text-align:left;">
            <p style="font-size:0.85em;color:#6b7280;margin:0 0 8px;">${t('quickconc.hint', 'Enter the standard-curve coefficients and a measured quantity — no data file needed.')}</p>
            <label style="display:block;margin-bottom:4px;font-weight:600;">${t('quickconc.model', 'Curve model')}
                <select id="qc-algo" style="width:100%;padding:4px;margin-top:2px;">${algos.map(a => `<option value="${a}">${a}</option>`).join('')}</select>
            </label>
            <div id="qc-coefs" style="margin:8px 0;">${_quickConcCoefInputs('linear')}</div>
            <label style="display:block;font-weight:600;">${t('quickconc.measured', 'Measured value (x)')}
                <input type="number" step="any" id="qc-x" style="width:100%;padding:3px 6px;box-sizing:border-box;margin-top:2px;">
            </label>
            <button type="button" id="qc-calc-btn" class="utility-btn" style="margin-top:10px;">${t('quickconc.calculate', 'Calculate')}</button>
            <div id="qc-result" style="margin-top:10px;font-weight:700;"></div>
        </div>`,
        showConfirmButton: true,
        confirmButtonText: t('common.close', 'Close'),
        width: 460,
        didOpen: () => {
            const algoSel = document.getElementById('qc-algo');
            const coefBox = document.getElementById('qc-coefs');
            algoSel.addEventListener('change', () => { coefBox.innerHTML = _quickConcCoefInputs(algoSel.value); });
            document.getElementById('qc-calc-btn').addEventListener('click', () => _runQuickConc(algoSel, coefBox));
        }
    });
}

async function _runQuickConc(algoSel, coefBox) {
    const resEl = document.getElementById('qc-result');
    const algo = algoSel.value;
    const coefficients = {};
    let missing = false;
    coefBox.querySelectorAll('input[data-key]').forEach(inp => {
        const v = (inp.value || '').trim();
        if (v === '') missing = true;
        coefficients[inp.dataset.key] = v === '' ? '' : parseFloat(v);
    });
    const xv = (document.getElementById('qc-x').value || '').trim();
    if (missing || xv === '') {
        resEl.style.color = '#b45309';
        resEl.textContent = t('quickconc.fill_all', 'Enter all coefficients and a measured value.');
        return;
    }
    try {
        const resp = await fetch('/calculate_concentration', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ regress_algo: algo, coefficients, x: parseFloat(xv) })
        });
        const data = await resp.json();
        if (data.status === 'success') {
            resEl.style.color = '';
            resEl.textContent = `${t('quickconc.result', 'Concentration')}: ${Number(data.concentration.toPrecision(6))}`;
        } else {
            resEl.style.color = '#b91c1c';
            resEl.textContent = data.message || t('quickconc.error', 'Calculation failed.');
        }
    } catch (e) {
        resEl.style.color = '#b91c1c';
        resEl.textContent = t('quickconc.error', 'Calculation failed.');
    }
}
