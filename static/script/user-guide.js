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
            // If there's a current step that requires interaction, handle it
            if (this.currentTargetElement && this.currentStepData && !this.currentStepData.skipInteraction) {
                const tagName = this.currentTargetElement.tagName.toLowerCase();
                const isInput = tagName === 'input';
                const isSelect = tagName === 'select';
                const elementType = isInput ? (this.currentTargetElement.type ? this.currentTargetElement.type.toLowerCase() : '') : '';
                const isCheckbox = isInput && (elementType === 'checkbox' || elementType === 'radio');
                const isTextInput = isInput && (elementType === 'text' || elementType === 'number');

                // For checkboxes, toggle them first (this will trigger the change handler)
                if (isCheckbox) {
                    this.currentTargetElement.checked = !this.currentTargetElement.checked;
                    // Trigger change event which will be caught by our handler
                    const changeEvent = new Event('change', { bubbles: true });
                    this.currentTargetElement.dispatchEvent(changeEvent);
                    return; // Handler will proceed
                }

                // For selects, focus them (user needs to actually change the value)
                if (isSelect) {
                    this.currentTargetElement.focus();
                    return; // Change handler will proceed when value changes
                }

                // For text inputs, focus them (user needs to type and blur)
                if (isTextInput) {
                    this.currentTargetElement.focus();
                    return; // Blur handler will proceed
                }

                // For buttons and other clickable elements, trigger their click
                // This will trigger the element's click handler which will proceed
                const isContainer = ['div', 'section', 'span'].includes(tagName);

                // Try to trigger the element's click handler by dispatching a click event
                // This should trigger the handler we attached in attachInteractionHandler
                try {
                    const clickEvent = new MouseEvent('click', {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        detail: 1
                    });
                    this.currentTargetElement.dispatchEvent(clickEvent);

                    // The dispatched click event will trigger the handler attached in attachInteractionHandler
                    // which handles the proceedToNextStep call. We don't need to do it here as well.
                } catch (err) {
                    console.warn('Error triggering element click:', err);
                    // If triggering fails, proceed directly
                    this.proceedToNextStep();
                }
            }
        });
        this.tooltip.addEventListener('click', (e) => e.stopPropagation());
    }

    /**
     * Define the guide steps
     */
    defineSteps() {
        // Check if data-display-section is currently visible (not hidden)
        // This indicates a file is selected and the section is shown
        const dataDisplaySection = document.getElementById('data-display-section');
        const isDataDisplayVisible = dataDisplaySection && !dataDisplaySection.classList.contains('hidden');
        const appState = (typeof AppState !== 'undefined') ? AppState : (window.AppState || {});
        const currentMode = appState.currentMeasurementMode || 'kinetics';

        // If data-display-section is visible (not hidden), use default guide
        // Otherwise, show mode-specific workflow for working with files in Data Display
        if (!isDataDisplayVisible) {
            const shareStepsFirstPart = [
                {
                    target: '#logo',
                    title: 'Welcome to Easy OKAPI!',
                    description: 'Easy OKAPI (Open-colorimeter Kinetics Analysis Platform), developed by Center for Bioscience and Biotechnology, HCMUS-VNU. Click the logo anytime to scroll to the top of the page.',
                    position: 'bottom',
                    skipInteraction: true
                },
                {
                    target: '#toggleContainer',
                    title: 'Theme Toggle',
                    description: 'Switch between light and dark modes for comfortable viewing in any environment.',
                    position: 'bottom'
                },
                {
                    target: '#meas-mode-section',
                    title: 'Measurement Mode',
                    description: 'Select your measurement mode: "kinetics" for time-series data or "point" for single-point measurements, or "calibrate" to create standard curves.',
                    position: 'right',
                    skipInteraction: true
                },
                {
                    target: '#options-section',
                    title: 'Options',
                    description: 'Configure your preferences here. You can disable popups and filter data files by number of measurement sources.',
                    position: 'right',
                    skipInteraction: true
                },
                {
                    target: '#drive-section',
                    title: 'Google Drive Storage',
                    description: 'Connect to Google Drive to sync your data. You can push and pull data from the cloud.',
                    position: 'right',
                    skipInteraction: true
                }
            ];
            const nonCalibrateStep =
            {
                target: '#cal-json-sel-section',
                title: 'Calibration Coefficients',
                description: 'Select calibrated JSON files containing standard curve coefficients, which can be selected to calculate Analyte concentration from measurement sources. Click on Edit button of the sample file to understand expected format of calibratation standard curve JSON files.',
                position: 'left',
                skipInteraction: true
            };

            const shareStepsSecondPart = [
                {
                    target: '#file-selection',
                    title: 'File Selection',
                    description: 'Select CSV data files to analyze. Click on Edit button of the sample file to understand expected format of data files.',
                    position: 'left',
                    skipInteraction: false
                }
            ];
            this.steps = [
                ...shareStepsFirstPart,
            ];
            if (currentMode !== 'calibrate') {
                this.steps.push(nonCalibrateStep);
            }
            this.steps.push(...shareStepsSecondPart);

        } else {
            // Data display section is hidden - show mode-specific workflow
            this.steps = this.getModeSpecificSteps(currentMode);
        }
    }

    /**
     * Get mode-specific workflow steps for data display section
     */
    getModeSpecificSteps(mode) {
        const JSONDisplay = document.getElementById('json-display');
        const isJSONDisplayVisible = JSONDisplay && !JSONDisplay.classList.contains('hidden');

        if (mode === 'kinetics') {
            const firstPart = [
                {
                    target: '#data-display-section',
                    title: 'Data Display Section',
                    description: 'After selecting a file, the Data Display section will appear here. In kinetics mode, you can view time-series measurements.',
                    position: 'left',
                    scrollIntoView: true,
                    skipInteraction: true
                },
                {
                    target: '#window-size-section',
                    title: 'Window Size (Kinetics Mode)',
                    description: 'Configure the window size for maxRate regression. This determines the number of data points used to calculate local slopes (minimum: 3).',
                    position: 'left',
                    skipInteraction: true,
                    scrollIntoView: true
                },
                {
                    target: '#range-display',
                    title: 'Display Range',
                    description: 'Set the time range to display on your charts. Adjust the "From" and "To" values and select the appropriate time unit.',
                    position: 'bottom',
                    skipInteraction: true,
                    scrollIntoView: true
                },
                {
                    target: '#split-sensor-section',
                    title: 'Split by Sensors',
                    description: 'Split the data by sensors. This will display each sensor\'s data in a separate chart and opt to display kinetics quantities for each measurement.',
                    position: 'right'
                },
                {
                    target: '#normalize-mode-section',
                    title: 'Normalize Data',
                    description: 'Normalize the data by substracting ground value for each measurement.',
                    position: 'right',
                    scrollIntoView: true
                },
                {
                    target: '#plot-button',
                    title: 'See kinetics analysis',
                    description: 'See the kinetics analysis of the data.',
                    position: 'right'
                },
                {
                    target: '#full-display-source-0',
                    title: 'Full Display',
                    description: 'Enable "Full Display" to see all data and special analysis lines. Check this box to see all data and special analysis lines.',
                    position: 'right'
                },
                {
                    target: 'label[id^="quantity-checkboxes-"]',
                    title: 'Select Quantities',
                    description: 'Select the quantities to display on the chart. You can select multiple quantities to display on the chart.',
                    position: 'right'
                },
                {
                    target: '#con-value-read-source-0',
                    title: 'Concentration Value',
                    description: 'The concentration value of the data. This will display the concentration value of the data.',
                    position: 'right',
                    skipInteraction: true
                },
                {
                    target: '#chart-container',
                    title: 'View Charts',
                    description: 'Your data will be visualized in charts here.',
                    position: 'left',
                    skipInteraction: true
                }];
            const deriveConPart = [
                {
                    target: '#json-display',
                    title: 'Details of Calibration Standard Curve',
                    description: 'Standard Curve used to derive Analyte Concentration is realized as coefficients for the chosen fitting function.',
                    position: 'left',
                    skipInteraction: true
                },
                {
                    target: '#derived-concentration-section-source-0',
                    title: 'Derived Concentration',
                    description: 'Concentration of the measuring Analyte derived from the selected standard curve and measurement data.',
                    position: 'right',
                    skipInteraction: true
                }];
            const secondPart = [
                {
                    target: '#select-sensor-to-export',
                    title: 'Select Sensor to Export',
                    description: 'Select the sensor to export the data. You can select multiple sensors to export the data.',
                    position: 'right',
                    skipInteraction: true,
                    scrollIntoView: true
                },
                {
                    target: '#export-analysis',
                    title: 'Export Analysis',
                    description: 'Export your analysis results. Set a reference point, enter a file name, and click "Export Data" to save your results.',
                    position: 'top',
                    skipInteraction: true,
                    scrollIntoView: true
                }];
            const JSONTable = {
                target: '#cal-json-sel-section',
                title: 'Standard Curve Coefficients',
                description: 'Select calibrated JSON files containing standard curve coefficients. Click on Edit button of the sample file to understand expected format of calibratation standard curve JSON files.',
                position: 'bottom',
                scrollIntoView: true,
                skipInteraction: true
            };
            const measurementMode = {
                target: '#measurement-mode',
                title: 'Switch to calibrate mode',
                description: 'Switch to calibrate mode to create standard curves from exported concentration with kinetics parameters.',
                scrollIntoView: true,
                position: 'right',
                skipInteraction: true
            };
            let returnedSteps = [
                ...firstPart
            ];

            if (isJSONDisplayVisible) {
                returnedSteps.push(...deriveConPart);
            }
            returnedSteps.push(...secondPart);

            if (!isJSONDisplayVisible) {
                returnedSteps.push(JSONTable);
            }

            returnedSteps.push(measurementMode);
            return returnedSteps;
        } else if (mode === 'point') {
            const firstPart = [
                {
                    target: '#data-display-section',
                    title: 'Data Display Section',
                    description: 'After selecting a file, Data Display section will appear here. In point mode, you can select an time point accompanying with measurement data for standard curve establishment.',
                    position: 'left',
                    scrollIntoView: true,
                    skipInteraction: true
                },
                {
                    target: '#set-exp-point-section',
                    title: 'Reference Point (Point Mode)',
                    description: 'Set the reference point for your measurements. This indicates the time point at which measurements were taken.',
                    position: 'left',
                    scrollIntoView: true,
                    skipInteraction: true
                },
                {
                    target: '#range-display',
                    title: 'Display Range',
                    description: 'Set the time range to display on your charts. Adjust the "From" and "To" values and select the appropriate time unit.',
                    position: 'bottom',
                    scrollIntoView: true,
                    skipInteraction: true
                },
                {
                    target: '#split-sensor-section',
                    title: 'Split by Sensors',
                    description: 'Split the data by sensors. This will display each sensor\'s data in a separate chart and opt to display kinetics quantities for each measurement.',
                    position: 'right',
                    scrollIntoView: true,
                },
                {
                    target: '#normalize-mode-section',
                    title: 'Normalize Data',
                    description: 'Normalize the data by substracting ground value for each measurement.',
                    position: 'right',
                    scrollIntoView: true
                },

                {
                    target: '#con-value-read-source-0',
                    title: 'Concentration Value',
                    description: 'The concentration value of the data. This will display the concentration value of the data.',
                    position: 'right',
                    skipInteraction: true,
                    scrollIntoView: true
                },
                {
                    target: '#chart-container',
                    title: 'View Charts',
                    description: 'Your data will be visualized in charts here.',
                    position: 'left',
                    skipInteraction: true,
                    scrollIntoView: true
                }];
            const deriveConPart = [
                {
                    target: '#json-display',
                    title: 'Details of Calibration Standard Curve',
                    description: 'Standard Curve used to derive Analyte Concentration is realized as coefficients for the chosen fitting function.',
                    position: 'left',
                    skipInteraction: true
                },
                {
                    target: '#derived-concentration-section-source-0',
                    title: 'Derived Concentration',
                    description: 'Concentration of the measuring Analyte derived from the selected standard curve and measurement data.',
                    position: 'right',
                    skipInteraction: true,
                    scrollIntoView: true
                }];
            const secondPart = [
                {
                    target: '#select-sensor-to-export',
                    title: 'Select Sensor to Export',
                    description: 'Select the sensor to export the data. You can select multiple sensors to export the data.',
                    position: 'right',
                    skipInteraction: true,
                    scrollIntoView: true
                },
                {
                    target: '#export-analysis',
                    title: 'Export Analysis',
                    description: 'Export your analysis results. Set a reference point, enter a file name, and click "Export Data" to save your results.',
                    position: 'top',
                    skipInteraction: true,
                    scrollIntoView: true
                }];
            const JSONTable = {
                target: '#cal-json-sel-section',
                title: 'Standard Curve Coefficients',
                description: 'Select calibrated JSON files containing standard curve coefficients. Click on Edit button of the sample file to understand expected format of calibratation standard curve JSON files.',
                position: 'bottom',
                scrollIntoView: true,
                skipInteraction: true
            };
            const measurementMode = {
                target: '#measurement-mode',
                title: 'Switch to calibrate mode',
                description: 'Switch to calibrate mode to create standard curves from exported concentration with kinetics parameters.',
                scrollIntoView: true,
                position: 'right',
                skipInteraction: true
            };
            let returnedSteps = [
                ...firstPart
            ];

            if (isJSONDisplayVisible) {
                returnedSteps.push(...deriveConPart);
            }
            returnedSteps.push(...secondPart);

            if (!isJSONDisplayVisible) {
                returnedSteps.push(JSONTable);
            }

            returnedSteps.push(measurementMode);
            return returnedSteps;
        } else if (mode === 'calibrate') {
            // Check if calibrate mode is kinetics or point
            const calModeDiv = document.getElementById('cal-mode-select');
            const calMode = (calModeDiv && calModeDiv.getAttribute('data-value')) || 'kinetics';

            if (calMode === 'kinetics') {
                return [
                    {
                        target: '#data-display-section',
                        title: 'Data Display Section',
                        description: 'After selecting a file, the Data Display section will appear here. In calibration mode (kinetics), you can create standard curves.',
                        position: 'left',
                        scrollIntoView: true,
                        skipInteraction: true
                    },
                    {
                        target: '#select-quantity-section',
                        title: 'Select Quantity (Calibration - Kinetics)',
                        description: 'Select which quantity to use for calibration: maxRate, Slope of Linear progression, Sat, or Reacting Time taken to Saturation.',
                        position: 'left'
                    },
                    {
                        target: '#select-regress-algo',
                        title: 'Select Regression Algorithm',
                        description: 'Choose the regression algorithm for your standard curve: polynomial, linear, logarithmic, exponential, or Michaelis-Menten.',
                        position: 'left'
                    },
                    {
                        target: '#chart-container',
                        title: 'View Calibration Chart',
                        description: 'Your calibration data will be displayed here with the selected regression fit. Review the standard curve and coefficients.',
                        position: 'left'
                    },
                    {
                        target: '#export-coef',
                        title: 'Export Coefficients',
                        description: 'Export your calibration coefficients. Enter a file name and click "Export Coefficients" to save the standard curve data.',
                        position: 'left'
                    }
                ];
            } else {
                return [
                    {
                        target: '#data-display-section',
                        title: 'Data Display Section',
                        description: 'After selecting a file, the Data Display section will appear here. In calibration mode (point), you can create standard curves.',
                        position: 'left',
                        scrollIntoView: true,
                        skipInteraction: true
                    },
                    {
                        target: '#select-time-point',
                        title: 'Select Time Point (Calibration - Point)',
                        description: 'Select which time point to use for calibration. Choose from the time points that were exported during measurement.',
                        position: 'left'
                    },
                    {
                        target: '#select-regress-algo',
                        title: 'Select Regression Algorithm',
                        description: 'Choose the regression algorithm for your standard curve: polynomial, linear, logarithmic, exponential, or Michaelis-Menten.',
                        position: 'left'
                    },
                    {
                        target: '#chart-container',
                        title: 'View Calibration Chart',
                        description: 'Your calibration data will be displayed here with the selected regression fit. Review the standard curve and coefficients.',
                        position: 'left',
                        skipInteraction: true
                    },
                    {
                        target: '#export-coef',
                        title: 'Export Coefficients',
                        description: 'Export your calibration coefficients. Enter a file name and click "Export Coefficients" to save the standard curve data.',
                        position: 'left'
                    }
                ];
            }
        } else {
            return;
        }
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

        // Show overlay and start first step
        this.overlay.classList.add('active');
        console.log(this.steps);
        this.showStep(this.currentStep);
    }

    /**
     * Stop the user guide
     */
    stop() {
        this.isActive = false;
        this.removeInteractionHandler();
        this.overlay.classList.remove('active');
        this.spotlight.classList.remove('active');
        this.tooltip.classList.remove('active');
        document.body.style.overflow = '';
    }

    /**
     * Show a specific step
     */
    showStep(stepIndex) {
        if (stepIndex < 0 || stepIndex >= this.steps.length) return;

        // Remove previous interaction handler if exists
        this.removeInteractionHandler();

        const step = this.steps[stepIndex];
        const targetElement = document.querySelector(step.target);

        if (!targetElement) {
            console.warn(`Target element not found: ${step.target}`);
            return;
        }

        // Store current target element and step data
        this.currentTargetElement = targetElement;
        this.currentStepData = step;

        // Scroll into view if needed
        if (step.scrollIntoView) {
            targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
            // Wait for scroll to complete
            setTimeout(() => {
                this.positionSpotlight(targetElement, step);
                this.attachInteractionHandler(targetElement, step);
            }, 300);
        } else {
            this.positionSpotlight(targetElement, step);
            this.attachInteractionHandler(targetElement, step);
        }

        // Update tooltip content
        this.updateTooltip(step, stepIndex);
    }

    /**
     * Attach interaction handler to target element
     */
    attachInteractionHandler(element, step) {
        // Skip if step allows skipping interaction
        if (step.skipInteraction) {
            return;
        }

        // Determine interaction type based on element
        const tagName = element.tagName.toLowerCase();
        const elementType = element.type ? element.type.toLowerCase() : '';
        const isInput = tagName === 'input';
        const isSelect = tagName === 'select';
        const isButton = tagName === 'button' || element.classList.contains('button') || element.onclick !== null;
        const isCheckbox = isInput && (elementType === 'checkbox' || elementType === 'radio');
        const isClickable = isButton || element.onclick !== null || element.style.cursor === 'pointer';
        const isTableRow = tagName === 'tr' || tagName === 'td';
        const isLabel = tagName === 'label';
        const isContainer = ['div', 'section', 'span'].includes(tagName) && !isClickable && !isTableRow;

        // Create handler function
        const handler = (e) => {
            // Remove interaction handler immediately to prevent double-firing
            this.removeInteractionHandler();

            // For checkboxes and radios, allow the default behavior
            if (isCheckbox) {
                // Wait a bit for the change to register, then proceed
                setTimeout(() => {
                    this.proceedToNextStep();
                }, 100);
                return;
            }

            // For labels, allow the click to trigger the associated input, then proceed
            if (isLabel) {
                // Let the label's default behavior happen (clicking associated input)
                setTimeout(() => {
                    this.proceedToNextStep();
                }, 150);
                return;
            }

            // For buttons and clickable elements, allow the click to happen first, then proceed
            if (isButton || isClickable) {
                // Don't prevent default - let the button's normal action happen
                setTimeout(() => {
                    this.proceedToNextStep();
                }, 200);
                return;
            }

            // For selects, proceed on change
            if (isSelect) {
                setTimeout(() => {
                    this.proceedToNextStep();
                }, 100);
                return;
            }

            // For table rows/cells, proceed on click
            if (isTableRow) {
                setTimeout(() => {
                    this.proceedToNextStep();
                }, 100);
                return;
            }

            // For containers/sections, proceed on click anywhere in the element
            if (isContainer) {
                e.stopPropagation();
                setTimeout(() => {
                    this.proceedToNextStep();
                }, 100);
                return;
            }

            // For other elements, proceed on click
            e.stopPropagation();
            setTimeout(() => {
                this.proceedToNextStep();
            }, 100);
        };

        // Attach appropriate event listener
        if (isCheckbox || isSelect) {
            element.addEventListener('change', handler);
            this.currentInteractionHandler = { element, event: 'change', handler };
        } else if (isInput && (elementType === 'text' || elementType === 'number')) {
            // For text/number inputs, proceed on blur (when user finishes editing)
            element.addEventListener('blur', handler);
            this.currentInteractionHandler = { element, event: 'blur', handler };
        } else {
            // Default to click for most elements
            element.addEventListener('click', handler);
            this.currentInteractionHandler = { element, event: 'click', handler };
        }

        // Make element visually indicate it's interactive (unless it's a container)
        if (!isContainer) {
            element.style.cursor = 'pointer';
            element.style.outline = '2px solid #3498db';
            element.style.outlineOffset = '2px';
        } else {
            // For containers, make the spotlight area clickable
            this.spotlight.style.cursor = 'pointer';
        }

        // For labels, also make them visually interactive
        if (isLabel) {
            element.style.cursor = 'pointer';
        }
    }

    /**
     * Remove interaction handler from current target
     */
    removeInteractionHandler() {
        if (this.currentInteractionHandler) {
            const { element, event, handler } = this.currentInteractionHandler;
            element.removeEventListener(event, handler);

            // Remove visual indicators
            element.style.cursor = '';
            element.style.outline = '';
            element.style.outlineOffset = '';

            this.currentInteractionHandler = null;
        }
        // Reset spotlight cursor
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
            // Last step - finish guide
            this.stop();
        }
    }

    /**
     * Position the spotlight on the target element
     */
    positionSpotlight(element, step) {
        const rect = element.getBoundingClientRect();
        const padding = 10;

        // Position spotlight
        this.spotlight.style.top = `${rect.top - padding + window.scrollY}px`;
        this.spotlight.style.left = `${rect.left - padding}px`;
        this.spotlight.style.width = `${rect.width + padding * 2}px`;
        this.spotlight.style.height = `${rect.height + padding * 2}px`;
        this.spotlight.classList.add('active');

        // Position tooltip
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

        // Ensure tooltip stays within viewport
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

        // Add instruction to interact with highlighted element
        const interactionInstruction = step.skipInteraction ? '' : ' Click or interact with the highlighted element to continue.';
        description.textContent = step.description + interactionInstruction;

        // Show/hide navigation buttons
        // Hide next button if interaction is required (unless step explicitly allows skipping)
        prevBtn.style.display = stepIndex > 0 ? 'inline-block' : 'none';
        nextBtn.style.display = (stepIndex < this.steps.length - 1 && step.skipInteraction) ? 'inline-block' : 'none';
        finishBtn.style.display = (stepIndex === this.steps.length - 1 && step.skipInteraction) ? 'inline-block' : 'none';
    }

    /**
     * Go to next step (manual navigation - only works if step allows skipping)
     */
    nextStep() {
        const currentStep = this.steps[this.currentStep];
        // Only allow manual next if step explicitly allows skipping interaction
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
