# Easy OKAPI Web application

## Setup and Usage
### Get this source code: 
* Click on `Code`, in the DropDown, select `Download Zip`. 
* Or clone with `Github Desktop`, `ssh`, `https`
<img src="/images/CloneRepo.png" width="300">
* In the path you save at, <span style="color:red; font-weight: bold;">MUST NOT CONTAINS SPECIAL CHARACTERS!</span> (e.g, Vietnamese characters like ạ, ô, ệ,...)

### Installation:
* On Mac:
	- Using installer (DMG):
		- Download the ![Latest release](https://img.shields.io/badge/latest-1.3.7-blue) `EasyOKAPI.dmg` on Mac.
		- Open the `EasyOKAPI.dmg` to mount it.
		- **Terminal-based Installation** (to bypass security warnings):
			1. Open the **Terminal** app.
			2. Run the first installation script with `sudo`:
			   ```bash
			   sudo /Volumes/EasyOKAPI/install-tools-clone-repo.command
			   ```
			3. Run the second installation script:
			   ```bash
			   sudo /Volumes/EasyOKAPI/install-venv.command
			   ```
			4. To launch the application:
			   ```bash
			   sudo /Volumes/EasyOKAPI/run.command
			   ```
		- Key in your device password to proceed when prompted.
		- Email [Minh Thong](mailto:tqmthong@gmail.com) for Token to authorize your installation when prompted.
		- Use `uninstall` to uninstall the application. 

	- Using batch scripts:
		+ Double click `setup-1-install-pyenv.command` to install homebrew, pyenv and python
		+ Double click `setup-2-install-venv.command` to install dependencies to `venv` folder
		+ Double click `setup-3-run.command` to run the application
		+ For the next time you'd like to run the application and be sure every dependencies have been correctly installed by `setup-1` and `setup-2`, you can run `setup-3` right away.
* On Windows:
	- **No USB driver needed.** The app communicates with the PyBadge over its USB serial (CDC) port, which Windows 10/11 enumerates automatically — no `libusbK`/Zadig setup required.
	- Using Installer: 
		+ Download the ![Latest release](https://img.shields.io/badge/latest-1.3.7-blue) `EasyOKAPI_Setup.exe` on Windows
		+ Email [Minh Thong](mailto:tqmthong@gmail.com) for Token to authorize your installation
		+ Paste the given token here <img src="/images/github_token.PNG" width="200"> to Download 
		+ After the installation, you can use `Easy OKAPI` icon on the Desktop to start the app
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

* ***Set measurement Modes*** The Applicatiob has 4 modes: `kinetics`, `point`, `calibrate`, `report`

* ***Select type of Calibration*** You can specify which calibration you're calculating for, either `kinetics` or `point`

* ***Log data*** Capture data sent from the ***PyBadge*** colorimeter over USB serial (CDC). Specify the save location and filename pattern via `--base-dir` and `--base-name`. The host log is saved at: `\log\script_logs.txt`. Disabled in **calibrate** mode

<div align="center">
	<img src="/images/logHID.png" width="600">
</div>

* ***Standard curves*** Choose standard curve you'd like to derive concentration from measurements. Disabled in `calibrate` mode. You can read detailed description in each standard curve json to understand the calculation methods. The information of selected file shall be displayed on the right portion of the interface.

<div align="center">
	<img src="/images/standardJSON.png" width="600">
</div>

* ***File Selection*** When a directory with csv files is browsed, the list of selectable csv files are displayed under ***File Selection*** table. Currently, the feature only supports display data from ***ONE*** file at a time. Click `Select` to visualize the chosen csv, `Deselect` to turn the visualization off.

<div align="center">
	<img src="/images/fileselection.png" width="600">
</div>

* ***Data Display***:
	- `Full Display` Enable, Disable graphics of `maxRate` (maximum reaction velocity throughout the process), `Linear` (average speed along reaction stage), `Sat` (Measured value at saturating point when no longer reactions happening) lines. When it is checked and a csv file is being browsed, all data of that file will be shown and `Display Range` value should be disabled.
	- In `kinetics` and `point` measurement modes, displayed data should show Measurement values (i.e Absorbance agains Time) 

	<div align="center">
		<img src="/images/meas.png" width="600">
	</div>

	- In `calibrate` mode, if selected calibration type is `kinetics`, you can select which of these quantity: `maxRate`, `Slope` of `Linear` progression, `Sat`, and `Reacting Time taken to Saturation`.

	<div align="center">
		<img src="/images/calKinetics.png" width="600">
	</div>

	- In `calibrate` mode, if selected calibration type is `point`, you can select among timepoints, which are exported to the selected file earlier in the measuring stage for calibration. 

	<div align="center">
		<img src="/images/calPoint.png" width="600">
	</div>


* `Display Range` Modifications in display range change the displayed data and respective unit displayed on the plot. 

<div align="center">
	<img src="/images/displayrange.png" width="600">
</div>

* `Window size` Specifies the number of data in a group to determine local slopes. Minimum is 3, maximum is half of data size in the browsing csv file. Disabled in `point`, `calibrate` mode

<div align="center">
	<img src="/images/window.png" width="600">
</div>

* `Export Analysis` 
	- Become ***Export coefficients for standard curve*** in `calibrate` mode
	- For `point` mode, key in the time point, the system will export with corresponding approximated measurement value at that time point for you. 
	<div align="center">
		<img src="/images/exportA.png" width="600">
	</div>

	- For `calibrate` mode, you can specify the corresponding regression algorithm to export standard curve with coefficients and plot on the chart. 
	<div align="center">
		<img src="/images/exportC.png" width="600">
	</div>

	- ***Note***: Due to security reason, the API we used for ***Select Directory*** only allows you correctly browse and select immediate Child/Parent directories at a time. You might modify to get the correct path in the interactive text box.

* `Filter number of sources` Allows users to filter csv data files based on number of data sources available.

	- Filter source control panel dropdown. Uncheck to disable the filter
	<div align="center">
		<img src="/images/filter-control.png" width="600">
	</div>

	- Typical multiple sources display
	<div align="center">
		<img src="/images/multi-meas-display.png" width="600">
	</div>

	- You can either export all data analysis from these sources or select specific one to export
	<div align="center">
		<img src="/images/exp-multi.png" width="600">
	</div>

## Directory Structure
```
microalbumin-Flask/
|-- README.md
|-- generate-tree.sh
|-- log_cdc_data.py
|-- main.py
|-- main_code.py
|-- requirements.txt
|-- requirements-dev.txt
|-- setup-1-install-pyenv.command
|-- setup-2-install-venv.command
|-- setup-3-run.command
|-- src
|   |-- browser_mgt.py
|   |-- export_cal_json.py
|   |-- export_data.py
|   |-- file.py
|   |-- file_path.py
|   |-- get_next_filename.py
|   |-- measure.py
|   |-- mode.py
|   |-- quantity.py
|   |-- range.py
|   |-- script_monitor.py
|   `-- send_command.py
|-- startwindow-1-git.bat
|-- startwindow-2-pyenv.bat
|-- startwindow-3-python.bat
|-- startwindow-4-venv-run.bat
|-- static
|   |-- done.mp3
|   |-- ht-logo.jpeg
|   |-- ht-noname.png
|   |-- ht.ico
|   |-- script
|   |   |-- calculate.js
|   |   |-- data-display.js
|   |   |-- data-handling.js
|   |   |-- edit-file.js
|   |   |-- generate-chart.js
|   |   |-- hid-logging.js
|   |   |-- index.js
|   |   |-- init.js
|   |   |-- navigation.js
|   |   `-- short-hands.js
|   `-- style.css
`-- templates
    |-- goodbye.html
    `-- index.html
```

## Notes

* The app assumes Timestamp in CSV files is in seconds. Adjust baseMultiplier in index.html if your data uses a different unit.

## License
* This project is for educational purposes and does not include a specific license. Feel free to use and modify it as needed.
