Microalbumin Flask App
Overviewd
This Flask application, named "Microalbumin," enables users to browse directories, select CSV files, and visualize data in a line chart. It supports dynamic filtering based on time range and unit, with features like directory navigation, file selection, and real-time plot updates. The code is organized with a src directory for Python modules and a templates directory for the HTML frontend.
Features

Browse directories and select CSV files.
Filter data by time range and unit (seconds, minutes, hours, micro-seconds).
Visualize data in a line chart using Chart.js.
Automatically exclude hidden files and directories (e.g., .git).
Round timestamps to 2 decimal places in the chart.
Custom measurement labels and units extracted from CSV data.
No animation on chart updates for seamless visualization.

Prerequisites

Python 3.x: Ensure Python 3 is installed on your system.
pip: Python package manager to install dependencies.
Operating System: Tested on Unix-like systems (Linux, macOS). Windows users may need to adjust the shell script (setup_and_run.sh) for cmd or PowerShell compatibility.

Setup and Usage
1. Clone or Download the Project
Ensure you have all project files in a directory (e.g., microalbumin-Flask).
2. Make the Shell Script Executable (Unix-like Systems)
`chmod +x setup_and_run.sh`

3. Run the Setup and Start Script
To run local, navigate to `main.py` and set `debug=True`, remove `host=0.0.0.0`, set `port` as a freely designated port (e.g 5000)
This script will create a virtual environment, install dependencies, and start the Flask app.
`./setup_and_run.sh` 

4. If you prefer transparency:
Install `flask` and `pandas` by `pip3 install -r requirements.txt`. Then run `sudo python3 main.py` (or "Run as Administrator" in Windows) to allow the Web app to access local folders. 

5. Access the App

Open your browser and navigate to http://127.0.0.1:5000/.
If port 5000 is in use, the script will attempt to use port 5001 (http://127.0.0.1:5001/).

6. Example CSV File
Create a CSV file in ~/Desktop/test_folder/ with the following format:
Measurement,Timestamp,Value,Unit
Temperature,100.12345,0.1,mg/L
Temperature,110.98765,0.4,mg/L
Temperature,120.45678,0.5,mg/L

The app will read this file and plot the data.
Directory Structure
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

Troubleshooting

Port in Use:
If both ports 5000 and 5001 fail, check for processes using those ports:lsof -i :5000
lsof -i :5001

Kill the processes if needed (e.g., kill -9 <PID>).


Dependencies Not Installed:
Ensure pip is installed and working:python3 -m ensurepip --upgrade


Manually install dependencies:pip install flask pandas




CSV File Not Found:
Ensure the directory ~/Desktop/test_folder/ exists and contains valid CSV files.
Check terminal logs for errors.


Chart Not Displaying:
Open the browser console (F12) and check for JavaScript errors.
Verify /get_data endpoint returns valid data in the Network tab.


Windows Users:
Modify setup_and_run.sh for Windows (e.g., use venv\Scripts\activate instead of source venv/bin/activate).
Alternatively, manually run:python -m venv venv
venv\Scripts\activate
pip install flask pandas
python main.py





Notes

The app assumes Timestamp in CSV files is in seconds. Adjust baseMultiplier in index.html if your data uses a different unit.
Hidden files and directories (starting with .) are automatically excluded.
Timestamps are rounded to 2 decimal places on the chart.

License
This project is for educational purposes and does not include a specific license. Feel free to use and modify it as needed.
