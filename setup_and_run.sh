#!/bin/bash

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python3 is not installed. Please install Python3 and try again."
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "pip3 is not installed. Please install pip3 and try again."
    exit 1
fi

# Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install flask pandas

# Function to find an available port
find_available_port() {
    for port in 5000 5001 5002; do
        if ! lsof -i :$port &> /dev/null; then
            echo $port
            return
        fi
    done
    echo "No available ports found (5000-5002). Please free up a port."
    exit 1
}

# Start the Flask app with an available port
PORT=$(find_available_port)
echo "Starting Flask app on port $PORT..."
python main.py $PORT || {
    echo "Failed to start on port $PORT. Please check main.py for port support or free up ports."
    exit 1
}

# Deactivate the virtual environment
deactivate