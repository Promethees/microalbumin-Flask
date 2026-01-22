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

        // Prevent clicks on spotlight from closing
        this.spotlight.addEventListener('click', (e) => e.stopPropagation());
        this.tooltip.addEventListener('click', (e) => e.stopPropagation());
    }

    /**
     * Define the guide steps
     */
    defineSteps() {
        this.steps = [
            {
                target: '#logo',
                title: 'Welcome to Easy OKAPI!',
                description: 'This is your colorimeter analysis platform. Click the logo anytime to scroll to the top of the page.',
                position: 'bottom'
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
                position: 'right'
            },
            {
                target: '#options-section',
                title: 'Options',
                description: 'Configure your preferences here. You can disable popups and filter sensors by number of sources.',
                position: 'right'
            },
            {
                target: '#drive-section',
                title: 'Google Drive Storage',
                description: 'Connect to Google Drive to automatically sync your data. You can push and pull data from the cloud.',
                position: 'right'
            },
            {
                target: '#cal-json-sel-section',
                title: 'Calibration Coefficients',
                description: 'Select calibrated JSON files containing standard curve coefficients. You can upload, download, edit, or delete calibration files.',
                position: 'left'
            },
            {
                target: '#file-selection',
                title: 'File Selection',
                description: 'Select CSV data files to analyze. You can upload new files, edit existing ones, or merge multiple files together.',
                position: 'left'
            },
            {
                target: '#data-display-section',
                title: 'Data Display & Analysis',
                description: 'Once you select a file, this section will show your data visualization, charts, and analysis tools. You can configure time ranges, normalization, and export results.',
                position: 'left',
                scrollIntoView: true
            }
        ];
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
        this.showStep(this.currentStep);
    }

    /**
     * Stop the user guide
     */
    stop() {
        this.isActive = false;
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

        const step = this.steps[stepIndex];
        const targetElement = document.querySelector(step.target);

        if (!targetElement) {
            console.warn(`Target element not found: ${step.target}`);
            return;
        }

        // Scroll into view if needed
        if (step.scrollIntoView) {
            targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
            // Wait for scroll to complete
            setTimeout(() => this.positionSpotlight(targetElement, step), 300);
        } else {
            this.positionSpotlight(targetElement, step);
        }

        // Update tooltip content
        this.updateTooltip(step, stepIndex);
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

        counter.textContent = `Step ${stepIndex + 1} of ${this.steps.length}`;
        title.textContent = step.title;
        description.textContent = step.description;

        // Show/hide navigation buttons
        prevBtn.style.display = stepIndex > 0 ? 'inline-block' : 'none';
        nextBtn.style.display = stepIndex < this.steps.length - 1 ? 'inline-block' : 'none';
        finishBtn.style.display = stepIndex === this.steps.length - 1 ? 'inline-block' : 'none';
    }

    /**
     * Go to next step
     */
    nextStep() {
        if (this.currentStep < this.steps.length - 1) {
            this.currentStep++;
            this.showStep(this.currentStep);
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
