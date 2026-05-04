function generateReport() {
    // 1. Gather data
    const selectedFile = document.getElementById('selected-file-display') ? document.getElementById('selected-file-display').innerText.replace('Selected File: ', '') : 'No file selected';
    const timestamp = new Date().toLocaleString();
    const measMode = AppState.currentMeasurementMode || "Unknown";
    
    // Attempt to grab calibration equations, MathJax spans etc.
    const addJsonSection = document.getElementById('add-json-section');
    const eqHtml = addJsonSection ? addJsonSection.innerHTML : '';
    
    let chartImageSrc = '';
    // Extract the chart base64 image (assuming AppState.chartInstances has the active chart)
    const chartKeys = Object.keys(AppState.chartInstances);
    if (chartKeys.length > 0) {
        // Just grab the first available chart, or active chart if there's multiple
        const targetChartId = chartKeys[0];
        const chart = AppState.chartInstances[targetChartId];
        if (chart) {
            chartImageSrc = chart.toBase64Image();
        }
    }

    // 2. Build the printable content
    let htmlContent = `
        <div class="report-title">
            EasyOKAPI Colorimetric Analysis Report
        </div>
        <div class="report-meta">
            <p><strong>File Name:</strong> ${selectedFile}</p>
            <p><strong>Measurement Mode:</strong> ${measMode}</p>
            <p><strong>Generated On:</strong> ${timestamp}</p>
        </div>
    `;

    if (chartImageSrc) {
        htmlContent += `
        <div style="text-align: center;">
            <img src="${chartImageSrc}" class="report-chart" alt="Chart Plot"/>
        </div>`;
    }

    if (eqHtml && eqHtml.trim() !== '') {
        htmlContent += `
        <div class="report-equation">
            <strong>Calibration / Regression Results:</strong><br/>
            ${eqHtml}
        </div>`;
    }

    // 3. Inject into the DOM
    const printContainer = document.getElementById('print-report-container');
    printContainer.innerHTML = htmlContent;

    // Remove hidden class temporarily
    printContainer.classList.remove('hidden');

    // Due to MathJax, we wait a split second for it to render if we copied MathJax nodes
    setTimeout(() => {
        // Trigger browser print
        window.print();
        // Hide it again
        printContainer.classList.add('hidden');
    }, 500);
}
