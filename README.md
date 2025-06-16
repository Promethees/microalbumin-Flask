# Easy Sensor Kit Web application

## Overview
This document provides instruction on deploying a web interface that helps visualize data recorded by a handy colorimeter, inspired by [IORodeo Open Colorimeter](https://iorodeo.com/products/open-colorimeter) 

## Features

* **Directory** Browse host's directories to select CSV files.

![](/images/browse.png)

* **Display Range** Filter data by time range and unit (seconds, minutes, hours). Only latest `<time><unit>` data points will be displayed.

![](/images/displayrange.png)

* **Log HID** Get data being sent from the **PyBadge** colorimeter. Specifiying location and file pattern name in `--base-dir` and `--base-name`. The logged file is saved at: `\log\script_logs.txt`

![](/images/logHID.png)

* **Window size** Specifies the number of data in a group to determine local slopes. Minimum is 3, maximum is half of data size in the browsing csv file.

![](/images/window.png)

* **File Selection** When a directory with csv files is browsed, the list of selectable csv files are displayed under **File Selection** table. Currently, the feature only supports display data from **ONE** file at a time. Click **Select** to visualize the chosen csv, **Deselect** to turn the visualization off.

![](/images/fileselection.png)

* **Data Display**:
	- **Display Range** Modification in display range changes the displayed data and respective unit displayed on the plot. 
	- **Split by Blanked** Seperate data points into 2 plots, *Blanked* and *Non-Blanked*, which is set by value of column ['Blanked'] in the browsed csv. [](/images/blank.png)
	- **Full Display** Enable, Disable graphics of ***Vmax***, ***Linear***, ***Sat*** lines. When it is checked and a csv file is being browsed, all data of that file will be shown and **Display Range** value should be disabled.

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
├── log_hid_data.py     # Python script to log data read from the colorimeter from HID
├── README.md           # Project documentation
├── start.sh    		# Script to start the app in MacOS
├── start.bat           # Script to start the app in Windows
└── requirements.txt    # Depedencies needed to download
```


## Setup and Usage

1. Install [Python 3.7.2](https://www.python.org/downloads/release/python-372/)

2. Executing the scripts:
* In Mac:
	- Open the Directory in Terminal: Right-click > Services > New Terminal at Folder ![](/images/Terminal.png)
	- Make the `start.sh` executable: `chmod +x start.sh` then run it `./start.sh`
* In Windows:
	- Right click on `start.bat`, Select `Run as Administrator` ![](/images/RunBat.png)

## Notes

* The app assumes Timestamp in CSV files is in seconds. Adjust baseMultiplier in index.html if your data uses a different unit.

## License
* This project is for educational purposes and does not include a specific license. Feel free to use and modify it as needed.
