#!/bin/bash

# Exit on error
set -e

# Change to the script's directory
cd "$(dirname "$0")"

# Initialize pyenv
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

# Activate virtual environment
source venv/bin/activate


# Set the library path for macOS and run with sudo
echo "Starting app..."
# sudo sh -c 'export DYLD_LIBRARY_PATH=$DYLD_LIBRARY_PATH:./mac; ./venv/bin/python3 main.py'
sudo python3 main.py
# Keep the Terminal window open for user interaction
read -p "Press Enter to exit..."