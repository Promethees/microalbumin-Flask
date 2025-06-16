#!/bin/bash

# Ensure Python 3.7 is installed
PYTHON_VERSION=$(python3 --version 2>&1)
if [[ "$PYTHON_VERSION" != *"3.7.2"* ]]; then
  echo "❌ Python 3.7.2 is required. Current version: $PYTHON_VERSION"
  exit 1
fi

# Create venv if not exists
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Run the app
echo "✅ Starting Flask app with sudo..."
sudo python3 main.py --port 5000
