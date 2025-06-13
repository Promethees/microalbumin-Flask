# Easy Sensor Kit Web application

## Overview
This document provides instruction on deploying a web interface that helps visualize data recorded by a handy colorimeter, inspired by [IORodeo Open Colorimeter](https://iorodeo.com/products/open-colorimeter) 

## Features

* **Directory** Browse host's directories to select CSV files.

![](/images/browse.png)

* **Display Range** Filter data by time range and unit (seconds, minutes, hours). Only latest `<time><unit>` data points will be displayed.

![](/images/displayrange.png)

* **Window size** Specifies the number of data in a group to determine local slopes. Minimum is 3, maximum is half of data size in the browsing csv file.

![](/images/window.png)

* **File Selection** When a directory with csv files is browsed, the list of selectable csv files are displayed under **File Selection** table. Currently, the feature only supports display data from **ONE** file at a time. Click **Select** to visualize the chosen csv, **Deselect** to turn the visualization off.

![](/images/fileselection.png)

* **Data Display**:
	- **Display Range** Modification in display range changes the displayed data and respective unit displayed on the plot. 
	- **Split by Blanked** Seperate data points into 2 plots, *Blanked* and *Non-Blanked*, which is set by value of column ['Blanked'] in the browsed csv. [](/images/blank.png)
	- **Full Display** Enable, Disable graphics of ***Vmax***, ***Linear***, ***Sat*** lines. When it is checked and a csv file is being browsed, all data of that file will be shown and **Display Range** value should be disabled.

## Requirements

* Python 3.x: Ensure Python 3 is installed on your system.
* pip: Python package manager to install dependencies.
* Operating System: Tested on Unix-like systems (Linux, macOS). Windows users may need to adjust the shell script (setup_and_run.sh) for cmd or PowerShell compatibility.

## Setup and Usage
1. Clone or Download the Project
* Ensure you have all project files in a directory (e.g., microalbumin-Flask).
2. Make the Shell Script Executable (Unix-like Systems)
* `chmod +x setup_and_run.sh`

3. Run the Setup and Start Script
* This script will create a virtual environment, install dependencies, and start the Flask app.
* `./setup_and_run.sh` 

4. If you prefer transparency:
* Install `flask` and `pandas` by `pip3 install -r requirements_local.txt`. Then run `sudo python3 main.py --port <default: 5000>` (or "Run as Administrator" in Windows) to allow the Web app to access local folders. Open the Application in browser at address `http://127.0.0.1:<port>`

5. Access the App

* Open your browser and navigate to http://127.0.0.1:5000/.
* If port 5000 is in use, the script will attempt to use port 5001 (http://127.0.0.1:5001/).

6. Example CSV Files provided in subfolder `/data`

## Directory Structure
```
microalbumin-Flask/
├── src/
│   ├── file_path.py    # Manages directory navigation
│   ├── file.py         # Handles file listing
│   ├── measure.py      # Processes CSV data for plotting
│   └── range.py        # Defines range input parameters
├── templates/
│   └── index.html      # Frontend template with Chart.js integration
├── main.py             # Flask app entry point
├── README.md           # Project documentation
└── setup_and_run.sh    # Script to setup and start the app
```

## Troubleshooting

* Port in Use:
	-If both ports 5000 and 5001 fail, check for processes using those ports: `lsof -i :5001`

* Kill the processes if needed (e.g., `kill -9 <PID>`).


* Dependencies Not Installed:
	- Ensure pip is installed and working: `python3 -m ensurepip --upgrade`


	- Manually install dependencies:pip install flask pandas

* Windows Users:
	- Modify setup_and_run.sh for Windows (e.g., use venv\Scripts\activate instead of source venv/bin/activate).
	- Alternatively, manually run:python -m venv venv
```
venv\Scripts\activate
pip install flask pandas
python main.py
```

## Notes

* The app assumes Timestamp in CSV files is in seconds. Adjust baseMultiplier in index.html if your data uses a different unit.
* Hidden files and directories (starting with .) are automatically excluded.

## License
* This project is for educational purposes and does not include a specific license. Feel free to use and modify it as needed.
