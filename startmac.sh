#!/bin/bash

# Exit on error
set -e

# Check if Homebrew is installed
if ! command -v brew &>/dev/null; then
    echo "❌ Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Check if Python is installed
if ! command -v python3 &>/dev/null; then
    echo "❌ Python not found. Installing Python 3.7.2..."
    brew install python@3.7
    # Ensure python3 points to Python 3.7.2
    brew link --force python@3.7
fi

# Check Python version
PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
if [ "$PY_VER" != "3.7.2" ]; then
    echo "❌ Python 3.7.2 is required. Current version: $PY_VER"
    echo "Installing Python 3.7.2..."
    brew install python@3.7
    brew link --force python@3.7
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Ensure pip is installed
echo "Checking pip..."
python3 -m ensurepip --upgrade

# Install required libraries
echo "Installing requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# Install Flask if not already installed
python3 -m pip install flask

# Install pandas if not already installed
python3 -m pip install pandas

# Start the app with sudo
echo "Starting app..."
sudo python3 main.py