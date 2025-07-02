#!/bin/bash

# Exit on error
set -e

# Change to the script's directory
cd "$(dirname "$0")"

# Check if Homebrew is installed
if ! command -v brew &>/dev/null; then
    echo "❌ Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Check if pyenv is installed
if ! command -v pyenv &>/dev/null; then
    echo "❌ pyenv not found. Installing pyenv..."
    brew install pyenv
fi

# Initialize pyenv
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

# Check if Python 3.8.10 is installed
if ! pyenv versions | grep -q "3.8.10"; then
    echo "❌ Python 3.8.10 not found. Installing Python 3.8.10 via pyenv..."
    # Set CFLAGS and LDFLAGS to use system headers
    export CFLAGS="-I$(xcrun --show-sdk-path)/usr/include"
    export LDFLAGS="-L$(xcrun --show-sdk-path)/usr/lib"
    pyenv install 3.8.10
else
    echo "Python 3.8.10 already installed. Proceeding..."
fi

# Set Python 3.8.10 as the local version for this directory
pyenv local 3.8.10

# Check Python version
PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
if [ "$PY_VER" != "3.8.10" ]; then
    echo "❌ Python 3.8.10 is required. Current version: $PY_VER"
    echo "Setting Python 3.8.10 via pyenv..."
    pyenv local 3.8.10
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

# Ensure libhidapi.dylib is present in the mac folder
if [ ! -f "mac/libhidapi.dylib" ]; then
    echo "❌ libhidapi.dylib not found in mac folder. Please place it in the 'mac' folder and retry."
    exit 1
fi

# Modify hid/__init__.py to load libhidapi.dylib explicitly
HID_INIT_PATH="venv/lib/python3.8/site-packages/hid/__init__.py"
if [ -f "$HID_INIT_PATH" ]; then
    # Create a backup
    cp "$HID_INIT_PATH" "$HID_INIT_PATH.bak"
    echo "Created backup of hid/__init__.py at $HID_INIT_PATH.bak"

    # Use a temporary file to handle multiline insertion
    TEMP_FILE=$(mktemp)
    echo "import os" > "$TEMP_FILE"
    echo "import ctypes" >> "$TEMP_FILE"
    echo "" >> "$TEMP_FILE"
    echo "# Explicitly load libhidapi.dylib from mac folder" >> "$TEMP_FILE"
    echo "lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../mac/libhidapi.dylib'))" >> "$TEMP_FILE"
    echo "hidapi = ctypes.cdll.LoadLibrary(lib_path)" >> "$TEMP_FILE"
    echo "" >> "$TEMP_FILE"
    echo "# Original library search loop disabled to prevent overwriting hidapi" >> "$TEMP_FILE"
    echo "# hidapid = None" >> "$TEMP_FILE"
    echo "# library_paths = (" >> "$TEMP_FILE"
    echo "#     'libhidapi-hidraw.so'," >> "$TEMP_FILE"
    echo "#     'libhidapi-hidraw.so.0'," >> "$TEMP_FILE"
    echo "#     'libhidapi-libusb.so'," >> "$TEMP_FILE"
    echo "#     'libhidapi-libusb.so.0'," >> "$TEMP_FILE"
    echo "#     'libhidapi-iohidmanager.so'," >> "$TEMP_FILE"
    echo "#     'libhidapi-iohidmanager.so.0'," >> "$TEMP_FILE"
    echo "#     'libhidapi.dylib'," >> "$TEMP_FILE"
    echo "#     'hidapi.dll'," >> "$TEMP_FILE"
    echo "#     'libhidapi-0.dll'" >> "$TEMP_FILE"
    echo "# )" >> "$TEMP_FILE"
    echo "#" >> "$TEMP_FILE"
    echo "# for lib in library_paths:" >> "$TEMP_FILE"
    echo "#     try:" >> "$TEMP_FILE"
    echo "#         hidapi = ctypes.cdll.LoadLibrary(lib)" >> "$TEMP_FILE"
    echo "#         break" >> "$TEMP_FILE"
    echo "#     except OSError:" >> "$TEMP_FILE"
    echo "#         pass" >> "$TEMP_FILE"
    echo "# else:" >> "$TEMP_FILE"
    echo "#     error = \"Unable to load any of the following libraries:{}\"\\\n#         .format(' '.join(library_paths))" >> "$TEMP_FILE"
    echo "#     raise ImportError(error)" >> "$TEMP_FILE"
    echo "" >> "$TEMP_FILE"
    cat "$HID_INIT_PATH" >> "$TEMP_FILE"
    # Remove the original loop section from the appended file
    sed -i '' '/hidapi = None/,/raise ImportError(/d' "$TEMP_FILE"
    mv "$TEMP_FILE" "$HID_INIT_PATH"
    echo "Modified hid/__init__.py to load libhidapi.dylib from mac/ directory and disabled original loop"
else
    echo "❌ Could not find hid/__init__.py. Please ensure the hid package is installed."
    exit 1
fi

# Set the library path for macOS and run with sudo
echo "Starting app..."
sudo sh -c 'export DYLD_LIBRARY_PATH=$DYLD_LIBRARY_PATH:./mac; ./venv/bin/python3 main.py'
# Keep the Terminal window open for user interaction
read -p "Press Enter to exit..."