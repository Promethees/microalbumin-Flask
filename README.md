# Easy Sensor Kit Web application

## Overview
This document provides instruction on deploying a web interface that helps visualize data recorded by a handy colorimeter, inspired by [IORodeo Open Colorimeter](https://iorodeo.com/products/open-colorimeter) 

## Features

* **Directory** Browse host's directories to select CSV files.

<div align="center">
	<img src="/images/browse.png" width="400">
</div>

* **Set measurement Modes** The Applicatiob has 3 modes: **kinetics**, **point**, **calibrate**

* **Select type of Calibration** You can specify which calibration you're calculating for, either **kinetics** or **point**

* **Log HID** Get data being sent from the **PyBadge** colorimeter. Specifiying location and file pattern name in `--base-dir` and `--base-name`. The logged file is saved at: `\log\script_logs.txt`. Disabled in **calibrate** mode

![](/images/logHID.png)

* **Standard lines** Choose standard line you'd like to derive concentration from measurements. Disabled in **calibrate** mode. You can read detailed description in each standard line json to understand the calculation methods.

![](/images/standardJSON.png)

* **File Selection** When a directory with csv files is browsed, the list of selectable csv files are displayed under **File Selection** table. Currently, the feature only supports display data from **ONE** file at a time. Click **Select** to visualize the chosen csv, **Deselect** to turn the visualization off.

![](/images/fileselection.png)

* **Data Display**:
	- **Display Range** Modification in display range changes the displayed data and respective unit displayed on the plot. 
	- **Split by Blanked** Seperate data points into 2 plots, *Blanked* and *Non-Blanked*, which is set by value of column ['Blanked'] in the browsed csv.

	![](/images/blank.png)

	- **Full Display** Enable, Disable graphics of ***Vmax***, ***Linear***, ***Sat*** lines. When it is checked and a csv file is being browsed, all data of that file will be shown and **Display Range** value should be disabled.
	- In **kinetics** and **point**, displayed data should show Measurement values (i.e Absorbance agains Time) 

	![](/images/meas.png)

	- In **calibrate** mode, if selected calibration type is **kinetics**, you can select which of these quantity: Vmax (maximum reaction velocity throughout the process), Slope (average speed along reaction stage), Sat (Measured value at saturating point when no longer reactions happening), and Time to Saturation.

	![](/images/calKinetics.png)

	- In **calibrate** mode, if selected calibration type is **point**, you can select among timepoints, which are exported to the selected file earlier in the measuring stage for calibration. 

	![](/images/calPoint.png)


* **Display Range** Filter data by time range and unit (seconds, minutes, hours). Only latest `<time><unit>` data points will be displayed. Disabled in **calibrate** mode

![](/images/displayrange.png)

* **Window size** Specifies the number of data in a group to determine local slopes. Minimum is 3, maximum is half of data size in the browsing csv file. Disabled in **point**, **calibrate** mode

![](/images/window.png)

* **Export Analysis** 
	- Become **Export coefficients for standard line** in **calibrate** mode
	- For both **kinetics** and **point** modes:
			+ Set **Display Unit** to **minutes** to ensure consistency among exported readings
			+ When setting export of analysis for Blank Type **MIXED**, display graphic must be in non Split mode. In the opposite way, whenever Blank Type is either **BLANKED** or **NON-BLANKED**, Split mode is needed (also applied in **calibrate** mode)
	- For **point** mode, key in the time point, the system will export with corresponding approximated measurement value at that time point for you. 
	![](/images/exportA.png)

	- For **calibrate** mode, you can specify the corresponding regression algorithm to export standard line with coefficients and plot on the chart. 
	![](/images/exportC.png)


## Directory Structure
```
microalbumin-Flask/
├── src/
│   ├── file_path.py    		# Manages directory navigation
│   ├── file.py         		# Handles file listing
│   ├── measure.py      		# Processes CSV data for plotting
│   ├── mode.py      			# Includes measurement modes used in the project
│   ├── quantity.py     		# Includes quantites for standard line regression
│   └── range.py        		# Defines range input parameters
├── templates/
│   └── index.html      		# Frontend template with Chart.js integration
├── static/
│   ├── script/  
│   │	├── index.js 			# To be executed first, entry point of the script, defining AppState global variables 
│   │	├── calculate.js 		# Functions handling numbers, calculations
│   │	├── data-display.js 	# Functions responsible for data display: updatePlot, generateChart
│   │	├── data-handling.js 	# Functions relating with selecting, exporting, fetching data
│   │	├── hid-logging.js 		# Functions interacting with with Colorimeter's HID interface
│   │	└── navigation.js 		# Functions responsible for browsing, updating correct states
│	└── style.css 
├── main.py             		# Flask app entry point
├── log_hid_data.py     		# Python script to log data read from the colorimeter from HID
├── README.md           		# Project documentation
├── setup.command    			# Script to start the app in MacOS
├── startwindow-1-git.bat           # Script to start the app in Windows
├── startwindow-2-pyenv-python.bat  # Script to start the app in Windows
├── startwindow-3-venv-run.bat      # Script to start the app in Windows
└── requirements.txt    		# Depedencies needed to download
```


## Setup and Usage

Installation:
* In Mac:
	- Double click `setup-1-install-pyenv.command` to install homebrew, pyenv and python
	- Double click `setup-2-install-venv.command` to install dependencies to `venv` folder
	- Double click `setup-3-run.command` to run the application
* In Windows:
	- Install `libusbK` driver for the PyBadge:
		+ Download [Zadig 2.9](https://zadig.akeo.ie/)
		+ Run `Zadig`, make sure `List All Devices` under `Options` tab is selected 
		![](/images/zadig_all_devices.PNG)
		+ Select `CircuitPython HID (Interface 3)` under the Dropdown
		+ Install `libusbK 3.1.0.0` to the `Pybadge`
		![](/images/libusbK.PNG)
		+ Verify the installation in `Device Manager` (open by `Win + R` > key in `devmgmt.msc`)
		![](/images/run.PNG)
		+ Make sure that it is listed under `libusbK USB Devices` 
		![](/images/DevManager.PNG)
	- Right click on `startwindow-1-git.bat`, Select `Run as Administrator`. Click YES to install required dependencies.
	- Repeat with `startwindow-2-pyenv-python.bat` then `startwindow-3-venv-run.bat`. 

## Notes

* The app assumes Timestamp in CSV files is in seconds. Adjust baseMultiplier in index.html if your data uses a different unit.

## License
* This project is for educational purposes and does not include a specific license. Feel free to use and modify it as needed.
