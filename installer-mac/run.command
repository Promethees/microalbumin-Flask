#!/bin/bash

# Log all output to a file for debugging
exec > >(tee -a /tmp/run.log) 2>&1
echo "Starting run script at $(date)"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (sudo)."
    osascript -e 'display dialog "This script requires sudo privileges. Please run with sudo." buttons {"OK"} default button "OK" with title "EasySensorKit Run"'
    exit 1
fi

# Define installation directory
REPO_NAME="microalbumin-Flask"
INSTALL_DIR="/Applications/$REPO_NAME"

# Check if installation directory exists
if [ ! -d "$INSTALL_DIR" ]; then
    echo "❌ Installation directory $INSTALL_DIR does not exist."
    osascript -e 'display dialog "Installation directory not found. Please install the application first." buttons {"OK"} default button "OK" with title "EasySensorKit Run"'
    exit 1
fi

# Change to the installation directory
cd "$INSTALL_DIR"

# Initialize pyenv
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "❌ Virtual environment not found in $INSTALL_DIR/venv."
    osascript -e 'display dialog "Virtual environment not found. Please run install-venv.command first." buttons {"OK"} default button "OK" with title "EasySensorKit Run"'
    exit 1
fi

# Check if main.py exists
if [ ! -f "main.py" ]; then
    echo "❌ main.py not found in $INSTALL_DIR."
    osascript -e 'display dialog "main.py not found in '$INSTALL_DIR'." buttons {"OK"} default button "OK" with title "EasySensorKit Run"'
    exit 1
fi

# Run the application
echo "Starting application..."
sudo python3 main.py
if [ $? -ne 0 ]; then
    echo "❌ Failed to run main.py."
    osascript -e 'display dialog "Failed to run the application." buttons {"OK"} default button "OK" with title "EasySensorKit Run"'
    exit 1
fi

echo "Application exited at $(date)"
exit 0