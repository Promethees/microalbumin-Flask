# Easy OKAPI Web application

## Setup and Usage
The web-based software is available at [https://www.easysensorkit.cbbiotec.vn/](https://www.easysensorkit.cbbiotec.vn/)

### Run it locally 
	- Install `pyenv` with `Python 3.12.11` using `setup-install-pyenv.command`
	- Set local python version as `3.12.11` using `pyenv local 3.12.11`
	- Install dependencies using `pip3 install -r requirements.txt`
	- Install `gunicorn` with `pip3 install gunicorn`
	- Start the app locally with `gunicorn -k eventlet -w 1 main:app --bind 0.0.0.0:5000`
	- Open browser, access the software via address of `http://0.0.0.0:5000` or `http://localhost:5000`

### Online deployment
	- Download `npm` with [Node.js](https://nodejs.org/en/download/)
	- Download `terser` with `npm install --save-dev terser`
	- Make changes, then use `npm run build` to obfuscate your latest code
	- Commit locally using `git commit -m "Your message"`
	- Check if already logged in with heroku `heroku whoami`, if not yet use `heroku login`
	- Configure heroku remote using `heroku git:remote -a easysensor-kit`
	- Push to deployment using `git push heroku online:main`

### Update package.json with latest versions
	- Use `npm init -y && npm pkg set scripts.build="node build.js" scripts.start="gunicorn main:app" && npm install --save-dev javascript-obfuscator terser clean-css`

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

* ***Set measurement Modes*** The Application has 3 modes: `kinetics`, `point`, `calibrate`

* ***Select type of Calibration*** You can specify which calibration you're calculating for, either `kinetics` or `point`

* ***Log HID*** Get data being sent from the ***PyBadge*** colorimeter. Specifiying location and file pattern name in `--base-dir` and `--base-name`. The logged file is saved at: `\log\script_logs.txt`. Disabled in **calibrate** mode

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

* ***Upload data*** Data can only be uploaded align with the following formats to be processed properly.

	- Format for [`Kinetics JSON`](https://github.com/Promethees/microalbumin-Flask/tree/online/json/exp_kinetics.json)

	- Format for [`Points JSON`](https://github.com/Promethees/microalbumin-Flask/tree/online/json/exp_point.json)

	- Format for [`Single Source CSV`](https://github.com/Promethees/microalbumin-Flask/tree/online/csv/single.csv)

	- Format for [`Multiple Source CSV`](https://github.com/Promethees/microalbumin-Flask/tree/online/csv/multi.csv)

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
|-- log_hid_data.py
|-- log_hid_data_pyusb.py
|-- main.py
|-- main_code.py
|-- requirements-win.txt
|-- requirements.txt
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
