/**
 * User Guide / Tutorial System
 * Provides step-by-step walkthrough with spotlight highlighting
 */

class UserGuide {
    constructor() {
        this.isActive = false;
        this.currentStep = 0;
        this.steps = [];
        this.overlay = null;
        this.spotlight = null;
        this.tooltip = null;
        this.initialized = false;
        this.currentInteractionHandler = null;
        this.currentTargetElement = null;
        this.currentStepData = null;
        this.resizeObserver = null;
        this.pollingInterval = null;

        // Step Definitions Configuration
        this.stepDefinitions = {
            common: [
                this.createStep('#logo', 'Welcome to Easy OKAPI!', 'Easy OKAPI (Open-colorimeter Kinetics Analysis Platform), developed by Center for Bioscience and Biotechnology, HCMUS-VNU. Click the logo anytime to scroll to the top of the page.', { position: 'bottom', skipInteraction: true }),
                this.createStep('#toggleContainer', 'Theme Toggle', 'Switch between light and dark modes for comfortable viewing in any environment.', { position: 'bottom' }),
                this.createStep('#meas-mode-section', 'Measurement Mode', 'Select your measurement mode: "kinetics" for time-series data or "point" for single-point measurements, or "calibrate" to create standard curves.', { position: 'right', skipInteraction: true }),
                this.createStep('#options-section', 'Options', 'Configure your preferences here. You can disable popups and filter data files by number of measurement sources.', { position: 'right', skipInteraction: true }),
                this.createStep('#drive-section', 'Google Drive Storage', 'Connect to Google Drive to sync your data. You can push and pull data from the cloud.', { position: 'right', skipInteraction: true })
            ],
            nonCalibrate: this.createStep('#cal-json-sel-section', 'Calibration Coefficients', 'Select calibrated JSON files containing standard curve coefficients, which can be selected to calculate Analyte concentration from measurement sources. Click on Edit button of the sample file to understand expected format of calibratation standard curve JSON files.', { position: 'left', skipInteraction: true }),
            fileSelection: [
                this.createStep('#file-selection', 'File Selection', 'Select CSV data files to analyze. Click on Edit button of the sample file to understand expected format of data files.', { position: 'left', skipInteraction: false })
            ],
            kinetics: {
                part1: [
                    this.createStep('#data-display-section', 'Data Display Section', 'After selecting a file, the Data Display section will appear here. In kinetics mode, you can view time-series measurements.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#window-size-section', 'Window Size (Kinetics Mode)', 'Configure the window size for maxRate regression. This determines the number of data points used to calculate local slopes (minimum: 3).', { position: 'left', skipInteraction: true, scrollIntoView: true }),
                    this.createStep('#range-display', 'Display Range', 'Set the time range to display on your charts. Adjust the "From" and "To" values and select the appropriate time unit.', { position: 'bottom', skipInteraction: true, scrollIntoView: true }),
                    this.createStep('#split-sensor-section', 'Split by Sensors', 'Split the data by sensors. This will display each measurement data in a separate chart and opt to display kinetics quantities for each measurement.', { position: 'right' }),
                    this.createStep('#normalize-mode-section', 'Normalize Data', 'Normalize the data by substracting ground value for each measurement.', { position: 'right', scrollIntoView: true }),
                    this.createStep('#open-all-analysis', 'Expand All Analyses', 'Expand all Kinetics Analysis of measurement data.', { position: 'right', scrollIntoView: true }),
                    this.createStep('#source-0-analysis', 'See kinetics analysis', 'Toggle the +/- button to view or hide kinetics analysis.', { position: 'right', scrollIntoView: true }),
                    this.createStep('#full-display-source-0', 'Full Display', 'Enable Full Display: to see all data and special analysis lines. Check this box to see all data and special analysis lines.', { position: 'right', scrollIntoView: true }),
                    this.createStep('label[id^="quantity-checkboxes-"]', 'Select Quantities', 'Select the quantities to display on the chart. You can select multiple quantities to display on the chart.', { position: 'right', skipInteraction: true }),
                    this.createStep('#con-value-read-source-0', 'Concentration Value', 'The concentration value of the data. This will display the concentration value of the data.', { position: 'right', skipInteraction: true }),
                    this.createStep('#chart-container', 'View Charts', 'Your data will be visualized in charts here.', { position: 'left', skipInteraction: true })
                ],
                deriveConPart: [
                    this.createStep('#json-display', 'Details of Calibration Standard Curve', 'Standard Curve used to derive Analyte Concentration is realized as coefficients for the chosen fitting function.', { position: 'left', skipInteraction: true }),
                    this.createStep('#derived-concentration-section-source-0', 'Derived Concentration', 'Concentration of the measuring Analyte derived from the selected standard curve and measurement data.', { position: 'right', skipInteraction: true })
                ],
                secondPart: [
                    this.createStep('#select-sensor-to-export', 'Select Sensor to Export', 'Select the sensor to export the data. You can select multiple sensors to export the data.', { position: 'right', skipInteraction: true, scrollIntoView: true }),
                    this.createStep('#export-analysis', 'Export Analysis', 'Export your analysis results. Set a reference point, enter a file name, and click "Export Data" to save your results.', { position: 'top', skipInteraction: true, scrollIntoView: true })
                ],
                jsonTable: this.createStep('#cal-json-sel-section', 'Standard Curve Coefficients', 'Select calibrated JSON files containing standard curve coefficients. Click on Edit button of the sample file to understand expected format of calibratation standard curve JSON files.', { position: 'bottom', scrollIntoView: true, skipInteraction: true }),
                measurementMode: this.createStep('#measurement-mode', 'Switch to calibrate mode', 'Switch to calibrate mode to create standard curves from exported concentration with kinetics parameters.', { scrollIntoView: true, position: 'right', skipInteraction: true })
            },
            point: {
                part1: [
                    this.createStep('#data-display-section', 'Data Display Section', 'After selecting a file, Data Display section will appear here. In point mode, you can select an time point accompanying with measurement data for standard curve establishment.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#set-exp-point-section', 'Reference Point (Point Mode)', 'Set the reference point for your measurements. This indicates the time point at which measurements were taken.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#range-display', 'Display Range', 'Set the time range to display on your charts. Adjust the "From" and "To" values and select the appropriate time unit.', { position: 'bottom', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#split-sensor-section', 'Split by Sensors', 'Split the data by sensors. This will display each measurement data in a separate chart and opt to display kinetics quantities for each measurement.', { position: 'right', scrollIntoView: true }),
                    this.createStep('#normalize-mode-section', 'Normalize Data', 'Normalize the data by substracting ground value for each measurement.', { position: 'right', scrollIntoView: true }),
                    this.createStep('#open-all-analysis', 'Expand All Analyses', 'Expand all Kinetics Analysis of measurement data.', { position: 'right', scrollIntoView: true }),
                    this.createStep('#source-0-analysis', 'See kinetics analysis', 'Toggle the +/- button to view or hide kinetics analysis.', { position: 'right', scrollIntoView: true }),
                    this.createStep('#full-display-source-0', 'Full Display', 'Enable "Full Display" to see all data and special analysis lines. Check this box to see all data Reference Calibration point', { position: 'right', scrollIntoView: true }),
                    this.createStep('#con-value-read-source-0', 'Concentration Value', 'The concentration value of the data. This will display the concentration value of the data.', { position: 'right', skipInteraction: true, scrollIntoView: true }),
                    this.createStep('#chart-container', 'View Charts', 'Your data will be visualized in charts here.', { position: 'left', skipInteraction: true, scrollIntoView: true })
                ],
                // deriveConPart, secondPart, jsonTable, measurementMode are shared or similar but defined separately if needed or reused
            },
            calibrate: {
                common: [
                    this.createStep('#cal-mode-select', 'Calibration Mode', 'Switch between "kinetics" and "point" calibration modes here.', { position: 'right', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#data-display-section', 'Data Display Section', 'After selecting a file, the Data Display section will appear here. In calibration mode (kinetics), you can create standard curves.', { position: 'left', scrollIntoView: true, skipInteraction: true }) // Note: description slightly differs in code, but checking logic
                ],
                kinetics: [
                    this.createStep('#select-quantity-section', 'Select Quantity (Calibration - Kinetics)', 'Select which quantity to use for calibration: maxRate, Slope of Linear progression, Sat, or Reacting Time taken to Saturation.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#select-regress-algo', 'Select Regression Algorithm', 'Choose the regression algorithm for your standard curve: polynomial, linear, logarithmic, exponential, or Michaelis-Menten.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#func-desc', 'Fitting function description', 'The description of the selected fitting function is displayed here.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#open-all-analysis', 'Expand all analyses', 'Expand all fitting coefficients tables for selected fitting functional formula with different kinetics parameters.', { position: 'bottom', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#cal-kinetics-button', 'Open/Collapse window of fitting coefficients', 'Toggle to see or hide fitting coefficients', { position: 'bottom', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#chart-container', 'View Calibration Chart', 'Your calibration data will be displayed here with the selected regression fit. Review the standard curve and coefficients.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#export-coef', 'Export Coefficients', 'Export your calibration coefficients. Enter a file name and click "Export Coefficients" to save the standard curve data.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#threshold-value', 'rSquared fitting threshold', 'Set the minimum accepted rSquared value for the fitting function. If the rSquared value is below this threshold, the fitting coefficients will not be exported.', { position: 'left', scrollIntoView: true, skipInteraction: true })
                ],
                point: [
                    this.createStep('#select-time-point', 'Select Time Point (Calibration - Point)', 'Select which time point to use for calibration. Choose from the time points that were exported during measurement.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    // Reuse similar steps from kinetics where possible or define explicit
                    this.createStep('#select-regress-algo', 'Select Regression Algorithm', 'Choose the regression algorithm for your standard curve: polynomial, linear, logarithmic, exponential, or Michaelis-Menten.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#func-desc', 'Fitting function description', 'The description of the selected fitting function is displayed here.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#open-all-analysis', 'Expand all analyses', 'Expand all fitting coefficients tables for selected fitting functional formula.', { position: 'bottom', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#cal-point-button', 'Open/Collapse window of fitting coefficients', 'Toggle to see or hide fitting coefficients', { position: 'bottom', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#chart-container', 'View Calibration Chart', 'Your calibration data will be displayed here with the selected regression fit. Review the standard curve and coefficients.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#export-coef', 'Export Coefficients', 'Export your calibration coefficients. Enter a file name and click "Export Coefficients" to save the standard curve data.', { position: 'left', scrollIntoView: true, skipInteraction: true }),
                    this.createStep('#threshold-value', 'rSquared fitting threshold', 'Set the minimum accepted rSquared value for the fitting function. If the rSquared value is below this threshold, the fitting coefficients will not be exported.', { position: 'left', scrollIntoView: true, skipInteraction: true })
                ]
            }
        };
    }

    /**
     * Helper to create a step object
     */
    createStep(target, title, description, options = {}) {
        return {
            target,
            title,
            description,
            ...options
        };
    }

    /**
     * Initialize the user guide system
     */
    init() {
        if (this.initialized) return;

        // Create overlay element
        this.overlay = document.createElement('div');
        this.overlay.id = 'user-guide-overlay';
        this.overlay.className = 'user-guide-overlay';

        // Create spotlight element
        this.spotlight = document.createElement('div');
        this.spotlight.id = 'user-guide-spotlight';
        this.spotlight.className = 'user-guide-spotlight';

        // Create tooltip element
        this.tooltip = document.createElement('div');
        this.tooltip.id = 'user-guide-tooltip';
        this.tooltip.className = 'user-guide-tooltip';
        this.tooltip.innerHTML = `
            <div class="tooltip-header">
                <span class="tooltip-step-counter"></span>
                <button class="tooltip-close-btn" aria-label="Close guide">×</button>
            </div>
            <div class="tooltip-content">
                <h3 class="tooltip-title"></h3>
                <p class="tooltip-description"></p>
            </div>
            <div class="tooltip-footer">
                <button class="tooltip-btn tooltip-prev-btn">← Previous</button>
                <button class="tooltip-btn tooltip-next-btn">Next →</button>
                <button class="tooltip-btn tooltip-finish-btn">Finish</button>
            </div>
        `;

        // Append to body
        document.body.appendChild(this.overlay);
        document.body.appendChild(this.spotlight);
        document.body.appendChild(this.tooltip);

        // Bind event listeners
        this.bindEvents();

        this.initialized = true;
    }

    /**
     * Bind event listeners for tooltip buttons
     */
    bindEvents() {
        const closeBtn = this.tooltip.querySelector('.tooltip-close-btn');
        const prevBtn = this.tooltip.querySelector('.tooltip-prev-btn');
        const nextBtn = this.tooltip.querySelector('.tooltip-next-btn');
        const finishBtn = this.tooltip.querySelector('.tooltip-finish-btn');

        closeBtn.addEventListener('click', () => this.stop());
        prevBtn.addEventListener('click', () => this.previousStep());
        nextBtn.addEventListener('click', () => this.nextStep());
        finishBtn.addEventListener('click', () => this.stop());

        // Close on overlay click
        this.overlay.addEventListener('click', () => this.stop());

        // Prevent clicks on spotlight from closing, but allow forwarding to target
        this.spotlight.addEventListener('click', (e) => {
            e.stopPropagation();
            if (this.currentTargetElement && this.currentStepData && !this.currentStepData.skipInteraction) {
                const targetElement = this.currentTargetElement;
                this.handleInteraction({ currentTarget: targetElement, type: 'click' }); // Simulate click handling

                // Try to forward click to the actual element if it's not a direct interaction handled by us
                try {
                    // Check if we should manually trigger click on element
                    // Logic adapted from original: some elements need focus, some need click dispatch
                    const { tagName, isInput, isSelect, isCheckbox, isTextInput } = this.determineElementType(targetElement);

                    if (isCheckbox) {
                        targetElement.checked = !targetElement.checked;
                        targetElement.dispatchEvent(new Event('change', { bubbles: true }));
                    } else if (isSelect || isTextInput) {
                        targetElement.focus();
                    } else {
                        // Default click dispatch
                        const clickEvent = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            detail: 1
                        });
                        targetElement.dispatchEvent(clickEvent);
                    }

                } catch (err) {
                    console.warn('Error triggering element click:', err);
                }
            }
        });
        this.tooltip.addEventListener('click', (e) => e.stopPropagation());
    }

    /**
     * Define the guide steps
     */
    defineSteps() {
        const dataDisplaySection = document.getElementById('data-display-section');
        const isDataDisplayVisible = dataDisplaySection && !dataDisplaySection.classList.contains('hidden');
        const appState = (typeof AppState !== 'undefined') ? AppState : (window.AppState || {});
        const currentMode = appState.currentMeasurementMode || 'kinetics';

        if (!isDataDisplayVisible) {
            this.steps = [...this.stepDefinitions.common];
            if (currentMode !== 'calibrate') {
                this.steps.push(this.stepDefinitions.nonCalibrate);
            }
            this.steps.push(...this.stepDefinitions.fileSelection);
        } else {
            this.steps = this.getModeSpecificSteps(currentMode);
        }
    }

    /**
     * Get mode-specific workflow steps for data display section
     */
    getModeSpecificSteps(mode) {
        const JSONDisplay = document.getElementById('json-display');
        const isJSONDisplayVisible = JSONDisplay && !JSONDisplay.classList.contains('hidden');

        // Helper to reconstruct arrays safely
        const buildSteps = (part1, derivePart, secondPart, jsonTableInfo, measurementModeInfo) => {
            let steps = [...part1];
            if (isJSONDisplayVisible) {
                steps.push(...derivePart);
            }
            steps.push(...secondPart);
            if (!isJSONDisplayVisible) {
                steps.push(jsonTableInfo);
            }
            steps.push(measurementModeInfo);
            return steps;
        };

        if (mode === 'kinetics') {
            return buildSteps(
                this.stepDefinitions.kinetics.part1,
                this.stepDefinitions.kinetics.deriveConPart,
                this.stepDefinitions.kinetics.secondPart,
                this.stepDefinitions.kinetics.jsonTable,
                this.stepDefinitions.kinetics.measurementMode
            );
        } else if (mode === 'point') {
            // Reuse secondPart and others from kinetics where they are identical in content
            return buildSteps(
                this.stepDefinitions.point.part1,
                this.stepDefinitions.kinetics.deriveConPart, // Same content
                this.stepDefinitions.kinetics.secondPart, // Same content
                this.stepDefinitions.kinetics.jsonTable, // Same content
                this.stepDefinitions.kinetics.measurementMode // Same content
            );
        } else if (mode === 'calibrate') {
            const calModeDiv = document.getElementById('cal-mode-select');
            const calMode = (calModeDiv && calModeDiv.getAttribute('data-value')) || 'kinetics';

            // Common calibrate steps + specific
            // Update common step description for point mode if needed or just use generic
            let commonSteps = this.stepDefinitions.calibrate.common.map(step => ({ ...step })); // clone
            if (calMode === 'point') {
                commonSteps[1].description = 'After selecting a file, the Data Display section will appear here. In calibration mode (point), you can create standard curves.';
            }

            if (calMode === 'kinetics') {
                return [...commonSteps, ...this.stepDefinitions.calibrate.kinetics];
            } else {
                return [...commonSteps, ...this.stepDefinitions.calibrate.point];
            }
        }
        return [];
    }

    /**
     * Start the user guide
     */
    start() {
        if (!this.initialized) {
            this.init();
        }

        this.defineSteps();
        this.currentStep = 0;
        this.isActive = true;

        this.overlay.classList.add('active');
        console.log(this.steps);
        this.showStep(this.currentStep);
    }

    /**
     * Stop the user guide
     */
    stop() {
        this.isActive = false;
        this.cleanupObservers();
        this.removeInteractionHandler();
        this.overlay.classList.remove('active');
        this.spotlight.classList.remove('active');
        this.tooltip.classList.remove('active');
        document.body.style.overflow = '';
    }

    /**
     * Cleanup observers and intervals
     */
    cleanupObservers() {
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
            this.resizeObserver = null;
        }
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }

    /**
     * Start polling for position changes (fallback for layout shifts)
     */
    startPolling(element, step) {
        // Poll every 100ms for 2 seconds, then every 500ms
        let count = 0;
        this.pollingInterval = setInterval(() => {
            if (!this.isActive || !element) {
                this.cleanupObservers();
                return;
            }
            this.positionSpotlight(element, step);
            count++;
            // Slow down after 2 seconds
            if (count === 20) {
                clearInterval(this.pollingInterval);
                this.pollingInterval = setInterval(() => {
                    if (!this.isActive) return;
                    this.positionSpotlight(element, step);
                }, 500);
            }
        }, 100);
    }

    /**
     * Show a specific step
     */
    showStep(stepIndex) {
        if (stepIndex < 0 || stepIndex >= this.steps.length) return;

        this.removeInteractionHandler();
        this.cleanupObservers();

        const step = this.steps[stepIndex];
        const targetElement = document.querySelector(step.target);

        if (!targetElement) {
            console.warn(`Target element not found: ${step.target}`);
            return;
        }

        this.currentTargetElement = targetElement;
        this.currentStepData = step;

        const setupStep = () => {
            this.positionSpotlight(targetElement, step);
            this.attachInteractionHandler(targetElement, step);

            // Setup ResizeObserver
            if (window.ResizeObserver) {
                this.resizeObserver = new ResizeObserver(() => {
                    this.positionSpotlight(targetElement, step);
                });
                this.resizeObserver.observe(targetElement);
                this.resizeObserver.observe(document.body); // Watch body for major shifts
            }

            // Start Polling
            this.startPolling(targetElement, step);
        };

        if (step.scrollIntoView) {
            // Using 'auto' for instant scrolling to avoid timing issues with smooth scroll on slower devices/obfuscated builds
            // fallback to smooth if desired but with longer timeout
            const scrollBehavior = 'smooth';
            targetElement.scrollIntoView({ behavior: scrollBehavior, block: 'center' });
            // Increased timeout to ensure scroll completion, especially for obfuscated/slower execution
            setTimeout(setupStep, 800);
        } else {
            setupStep();
        }

        this.updateTooltip(step, stepIndex);
    }

    /**
     * Helper to determine element type and properties
     */
    determineElementType(element) {
        const tagName = element.tagName.toLowerCase();
        const elementType = element.type ? element.type.toLowerCase() : '';
        const isInput = tagName === 'input';

        return {
            tagName,
            isInput,
            isSelect: tagName === 'select',
            isButton: tagName === 'button' || element.classList.contains('button') || element.onclick !== null,
            isCheckbox: isInput && (elementType === 'checkbox' || elementType === 'radio'),
            isClickable: (tagName === 'button' || element.classList.contains('button') || element.onclick !== null) || element.style.cursor === 'pointer',
            isTableRow: tagName === 'tr' || tagName === 'td',
            isLabel: tagName === 'label',
            isContainer: ['div', 'section', 'span'].includes(tagName),
            isTextInput: isInput && (elementType === 'text' || elementType === 'number')
        };
    }

    /**
     * Attach interaction handler to target element
     */
    attachInteractionHandler(element, step) {
        if (step.skipInteraction) return;

        const { isCheckbox, isSelect, isInput, isTextInput, isContainer, isLabel } = this.determineElementType(element);

        const handler = (e) => this.handleInteraction(e);

        let eventType = 'click';
        if (isCheckbox || isSelect) {
            eventType = 'change';
        } else if (isInput && isTextInput) {
            eventType = 'blur';
        }

        element.addEventListener(eventType, handler);
        this.currentInteractionHandler = { element, event: eventType, handler };

        // Visual indicators
        if (!isContainer && !isLabel) { // Label logic was slightly different in original, but simplified here
            element.style.cursor = 'pointer';
            element.style.outline = '2px solid #3498db';
            element.style.outlineOffset = '2px';
        } else if (isContainer) {
            this.spotlight.style.cursor = 'pointer';
        } else if (isLabel) {
            element.style.cursor = 'pointer';
        }
    }

    /**
     * Handle interaction events
     */
    handleInteraction(e) {
        // Debounce or Prevent double calling is handled by removing handler immediately
        if (!this.currentInteractionHandler && e.type !== 'click') return; // approximate check

        const targetElement = this.currentTargetElement || e.currentTarget;

        this.removeInteractionHandler();

        // If targetElement is null (unexpected), return
        if (!targetElement) return;

        const { isCheckbox, isSelect, isButton, isClickable, isTableRow, isContainer } = this.determineElementType(targetElement);

        let delay = 100;

        if (isButton || isClickable) delay = 200;
        else if (isCheckbox) delay = 150; // Increased to match original code update
        else if (isContainer && e.stopPropagation) e.stopPropagation();
        else if (e.stopPropagation) e.stopPropagation(); // formatted default

        setTimeout(() => {
            this.proceedToNextStep();
        }, delay);
    }

    /**
     * Remove interaction handler from current target
     */
    removeInteractionHandler() {
        if (this.currentInteractionHandler) {
            const { element, event, handler } = this.currentInteractionHandler;
            element.removeEventListener(event, handler);

            element.style.cursor = '';
            element.style.outline = '';
            element.style.outlineOffset = '';

            this.currentInteractionHandler = null;
        }
        if (this.spotlight) {
            this.spotlight.style.cursor = '';
        }
        this.currentTargetElement = null;
        this.currentStepData = null;
    }

    /**
     * Proceed to next step after interaction
     */
    proceedToNextStep() {
        if (this.currentStep < this.steps.length - 1) {
            this.removeInteractionHandler();
            this.currentStep++;
            this.showStep(this.currentStep);
        } else {
            this.stop();
        }
    }

    /**
     * Position the spotlight on the target element
     */
    positionSpotlight(element, step) {
        if (!element || !this.isActive) return;

        const rect = element.getBoundingClientRect();
        const padding = 10;

        // Ensure rect is valid (non-zero if visible)
        if (rect.width === 0 && rect.height === 0) return;

        this.spotlight.style.top = `${rect.top - padding + window.scrollY}px`;
        this.spotlight.style.left = `${rect.left - padding}px`;
        this.spotlight.style.width = `${rect.width + padding * 2}px`;
        this.spotlight.style.height = `${rect.height + padding * 2}px`;
        this.spotlight.classList.add('active');

        // Ensure high z-index
        this.spotlight.style.zIndex = '9999';
        this.overlay.style.zIndex = '9998';
        this.tooltip.style.zIndex = '10000';

        this.positionTooltip(rect, step.position || 'bottom');
    }

    /**
     * Position the tooltip relative to the spotlight
     */
    positionTooltip(targetRect, position) {
        const tooltipRect = this.tooltip.getBoundingClientRect();
        const padding = 20;
        let top, left;

        switch (position) {
            case 'top':
                top = targetRect.top + window.scrollY - tooltipRect.height - padding;
                left = targetRect.left + (targetRect.width / 2) - (tooltipRect.width / 2);
                break;
            case 'bottom':
                top = targetRect.bottom + window.scrollY + padding;
                left = targetRect.left + (targetRect.width / 2) - (tooltipRect.width / 2);
                break;
            case 'left':
                top = targetRect.top + window.scrollY + (targetRect.height / 2) - (tooltipRect.height / 2);
                left = targetRect.left - tooltipRect.width - padding;
                break;
            case 'right':
                top = targetRect.top + window.scrollY + (targetRect.height / 2) - (tooltipRect.height / 2);
                left = targetRect.right + padding;
                break;
            default:
                top = targetRect.bottom + window.scrollY + padding;
                left = targetRect.left + (targetRect.width / 2) - (tooltipRect.width / 2);
        }

        const maxLeft = window.innerWidth - tooltipRect.width - 20;
        const maxTop = window.innerHeight + window.scrollY - tooltipRect.height - 20;

        left = Math.max(20, Math.min(left, maxLeft));
        top = Math.max(20, Math.min(top, maxTop));

        this.tooltip.style.top = `${top}px`;
        this.tooltip.style.left = `${left}px`;
        this.tooltip.classList.add('active');
    }

    /**
     * Update tooltip content
     */
    updateTooltip(step, stepIndex) {
        const counter = this.tooltip.querySelector('.tooltip-step-counter');
        const title = this.tooltip.querySelector('.tooltip-title');
        const description = this.tooltip.querySelector('.tooltip-description');
        const prevBtn = this.tooltip.querySelector('.tooltip-prev-btn');
        const nextBtn = this.tooltip.querySelector('.tooltip-next-btn');
        const finishBtn = this.tooltip.querySelector('.tooltip-finish-btn');

        counter.textContent = `${stepIndex + 1} of ${this.steps.length}`;
        title.textContent = step.title;

        const interactionInstruction = step.skipInteraction ? '' : ' Click or interact with the highlighted element to continue.';
        description.textContent = step.description + interactionInstruction;

        prevBtn.style.display = stepIndex > 0 ? 'inline-block' : 'none';
        nextBtn.style.display = (stepIndex < this.steps.length - 1 && step.skipInteraction) ? 'inline-block' : 'none';
        finishBtn.style.display = (stepIndex === this.steps.length - 1 && step.skipInteraction) ? 'inline-block' : 'none';
    }

    /**
     * Go to next step (manual navigation)
     */
    nextStep() {
        const currentStep = this.steps[this.currentStep];
        if (currentStep && currentStep.skipInteraction) {
            if (this.currentStep < this.steps.length - 1) {
                this.removeInteractionHandler();
                this.currentStep++;
                this.showStep(this.currentStep);
            }
        }
    }

    /**
     * Go to previous step
     */
    previousStep() {
        if (this.currentStep > 0) {
            this.currentStep--;
            this.showStep(this.currentStep);
        }
    }

    /**
     * Toggle the guide on/off
     */
    toggle() {
        if (this.isActive) {
            this.stop();
        } else {
            this.start();
        }
    }
}

// Create global instance
window.userGuide = new UserGuide();

// Function to toggle guide (called from button)
function toggleUserGuide() {
    window.userGuide.toggle();
}
