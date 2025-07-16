# Easy Sensor Kit Web application

## Setup and Usage
Download: 
* Click on `Code`, in the DropDown, select `Download Zip`. 
* In the path you save at, <span style="color:red; font-weight: bold;">MUST NOT CONTAINS SPECIAL CHARACTERS!</span> (e.g, Vietnamese characters like ạ, ô, ệ,...)

Installation:
* On Mac:
	- Using installer:
		+ Disable ***GATEKEEPER*** to let Mac allow your installation: Open `Terminal` app and key in `sudo spctl --master-disable` with your password when prompted
		+ After the download is done, reenable with `sudo spctl --master-enable`
		+ Download the [![Latest Release](https://img.shields.io/github/v/release/Promethees/microalbumin-Flask?label=latest)](https://github.com/Promethees/microalbumin-Flask/releases/latest) `EasySensorKit.dmg` on Mac
		+ Open the `EasySensorKit.dmg`
		+ From it, run `install-tools-clone-repo`, then `install-venv` to install dependencies and virtual environment. 
		+ Key in your device password to proceed when prompted 
		+ Email [Minh Thong](mailto:tqmthong@gmail.com) for Token to authorize your installation when prompted.
		+ Use `run` to start the Application when all of the above steps are finished
		+ Use `uninstall` to uninstall the application. 

	- Using batch scripts:
		+ Double click `setup-1-install-pyenv.command` to install homebrew, pyenv and python
		+ Double click `setup-2-install-venv.command` to install dependencies to `venv` folder
		+ Double click `setup-3-run.command` to run the application
		+ For the next time you'd like to run the application and be sure every dependencies have been correctly installed by `setup-1` and `setup-2`, you can run `setup-3` right away.
* On Windows:
	- Install `libusbK` driver for the PyBadge:
		+ Download [Zadig 2.9](https://zadig.akeo.ie/)
		+ Run `Zadig`, make sure `List All Devices` under `Options` tab is selected 
		<div align="center"> 
			<img src="/images/zadig_all_devices.PNG" width="600">
		</div>

		+ Select `CircuitPython HID (Interface 3)` under the Dropdown
		+ Install `libusbK 3.1.0.0` to the `Pybadge`
		<div align="center">
			<img src="/images/libusbK.PNG" width="600">
		</div>

		+ Verify the installation in `Device Manager` (open by `Win + R` > key in `devmgmt.msc`)
		<div align="center">
			<img src="/images/run.PNG" width="600">
		</div>

		+ Make sure that it is listed under `libusbK USB Devices` 
		<div align="center">
			<img src="/images/DevManager.PNG" width="600">
		</div>

	- Using Installer: 
		+ Download the [![Latest release](https://img.shields.io/github/v/release/Promethees/microalbumin-Flask?label=latest)](https://github.com/Promethees/microalbumin-Flask/releases/latest) `EasySensorKit_Setup.exe` on Windows
		+ Email [Minh Thong](mailto:tqmthong@gmail.com) for Token to authorize your installation
		+ Paste the given token here <img src="/images/github_token.PNG" width="200"> to Download 
		+ After the installation, you can use `EasySensor Kit` icon on the Desktop to start the app
		+ For `Uninstallation`, navigate to the local fodler in which you save the Program Files, use `Uninstall.exe` to uninstall
		
	- Using batch scripts:
		+ Right click on `startwindow-1-git.bat`, Select `Run as Administrator`. Click YES to install required dependencies.
		+ Repeat with `startwindow-2-pyenv.bat` -> `startwindow-3-python.bat` -> `startwindow-4-venv-run.bat`. Run ***ONE BY ONE!***
		+ For the next time you'd like to run the application and be sure every dependencies have been correctly installed by `start-1` and `start-2`, you can run `start-3` right away.

## Overview
This document provides instruction on deploying a web interface that helps visualize data recorded by a handy colorimeter, inspired by [IORodeo Open Colorimeter](https://iorodeo.com/products/open-colorimeter) 

## Features
* ***Init prompt*** Instruct you to select the correct started Directory for Directory Picker

<div align="center">
	<img src="/images/init-prompt.png" width="600">
</div>

* ***Directory*** Browse host's directories to select CSV files.

<div align="center">
	<img src="/images/browse.png" width="600">
</div>

* ***Set measurement Modes*** The Applicatiob has 3 modes: `kinetics`, `point`, `calibrate`

* ***Select type of Calibration*** You can specify which calibration you're calculating for, either `kinetics` or `point`

* ***Log HID*** Get data being sent from the ***PyBadge*** colorimeter. Specifiying location and file pattern name in `--base-dir` and `--base-name`. The logged file is saved at: `\log\script_logs.txt`. Disabled in **calibrate** mode
	- ***Note***: Due to security reason, the API we used for ***Select Directory*** only allows you correctly browse and select immediate Child/Parent directories at a time. You might modify to get the correct path in the interactive text box.

<div align="center">
	<img src="/images/logHID.png" width="600">
</div>

* ***Standard lines*** Choose standard line you'd like to derive concentration from measurements. Disabled in `calibrate` mode. You can read detailed description in each standard line json to understand the calculation methods.

<div align="center">
	<img src="/images/standardJSON.png" width="600">
</div>

* ***File Selection*** When a directory with csv files is browsed, the list of selectable csv files are displayed under ***File Selection*** table. Currently, the feature only supports display data from ***ONE*** file at a time. Click `Select` to visualize the chosen csv, `Deselect` to turn the visualization off.

<div align="center">
	<img src="/images/fileselection.png" width="600">
</div>

* ***Data Display***:
	- `Display Range` Modification in display range changes the displayed data and respective unit displayed on the plot. 
	- `Split by Blanked` Seperate data points into 2 plots, ***Blanked*** and ***Non-Blanked***, which is set by value of column ['Blanked'] in the browsed csv.

	<div align="center">
		<img src="/images/blank.png" width="600">
	</div>

	- `Full Display` Enable, Disable graphics of `Vmax` (maximum reaction velocity throughout the process), `Linear` (average speed along reaction stage), `Sat` (Measured value at saturating point when no longer reactions happening) lines. When it is checked and a csv file is being browsed, all data of that file will be shown and `Display Range` value should be disabled.
	- In `kinetics` and `point` measurement modes, displayed data should show Measurement values (i.e Absorbance agains Time) 

	<div align="center">
		<img src="/images/meas.png" width="600">
	</div>

	- In `calibrate` mode, if selected calibration type is `kinetics`, you can select which of these quantity: `Vmax`, `Slope` of `Linear` progression, `Sat`, and `Time to Saturation`.

	<div align="center">
		<img src="/images/calKinetics.png" width="600">
	</div>

	- In `calibrate` mode, if selected calibration type is `point`, you can select among timepoints, which are exported to the selected file earlier in the measuring stage for calibration. 

	<div align="center">
		<img src="/images/calPoint.png" width="600">
	</div>


* `Display Range` Filter data by time range and unit (seconds, minutes, hours). Only latest `<time><unit>` data points will be displayed. Disabled in `calibrate` mode

<div align="center">
	<img src="/images/displayrange.png" width="600">
</div>

* `Window size` Specifies the number of data in a group to determine local slopes. Minimum is 3, maximum is half of data size in the browsing csv file. Disabled in `point`, `calibrate` mode

<div align="center">
	<img src="/images/window.png" width="600">
</div>

* `Export Analysis` 
	- Become ***Export coefficients for standard line*** in `calibrate` mode
	- For both `kinetics` and `point` modes:
			+ Set `Display Unit` to `minutes` to ensure consistency among exported readings
			+ When setting export of analysis for Blank Type `MIXED`, display graphic must be in non Split mode. In the opposite way, whenever Blank Type is either `BLANKED` or `NON-BLANKED`, Split mode is needed (also applied in `calibrate` mode)
	- For `point` mode, key in the time point, the system will export with corresponding approximated measurement value at that time point for you. 
	<div align="center">
		<img src="/images/exportA.png" width="600">
	</div>

	- For `calibrate` mode, you can specify the corresponding regression algorithm to export standard line with coefficients and plot on the chart. 
	<div align="center">
		<img src="/images/exportC.png" width="600">
	</div>

	- ***Note***: Due to security reason, the API we used for ***Select Directory*** only allows you correctly browse and select immediate Child/Parent directories at a time. You might modify to get the correct path in the interactive text box.

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
├── setup-1-install-pyenv.command   # Script to start the app in MacOS
├── setup-2-install-venv.command    # Script to start the app in MacOS
├── setup-3-run.command   			# Script to start the app in MacOS
├── startwindow-1-git.bat           # Script to start the app in Windows
├── startwindow-2-pyenv.bat  		# Script to start the app in Windows
├── startwindow-3-python.bat      	# Script to start the app in Windows
├── startwindow-4-venv-run.bat      # Script to start the app in Windows
└── requirements.txt    		# Depedencies needed to download
```

## Notes

* The app assumes Timestamp in CSV files is in seconds. Adjust baseMultiplier in index.html if your data uses a different unit.

## License
* This project is for educational purposes and does not include a specific license. Feel free to use and modify it as needed.
