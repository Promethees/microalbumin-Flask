#!/bin/bash

# Log all output to a file for debugging
exec > >(tee -a /tmp/install-venv.log) 2>&1
echo "Starting install-venv script at $(date)"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (sudo)."
    exit 1
fi

# Define installation directory
REPO_NAME="microalbumin-Flask"
INSTALL_DIR="/Applications/$REPO_NAME"

# Check if installation directory exists
if [ ! -d "$INSTALL_DIR" ]; then
    echo "❌ Installation directory $INSTALL_DIR does not exist."
    osascript -e 'display dialog "Installation directory not found. Please run install-homebrew-and-clone.command first." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

# Change to the installation directory
cd "$INSTALL_DIR"

# Initialize pyenv
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

# Verify Python 3.8.10
pyenv global 3.8.10
PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
if [ "$PY_VER" != "3.8.10" ]; then
    echo "❌ Python 3.8.10 is required. Current version: $PY_VER"
    osascript -e 'display dialog "Python 3.8.10 is required but not found. Current version: '$PY_VER'" buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create virtual environment."
        osascript -e 'display dialog "Failed to create virtual environment." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
        exit 1
    fi
fi

# Activate virtual environment
source venv/bin/activate

# Ensure pip is installed
echo "Checking pip..."
python3 -m ensurepip --upgrade
if [ $? -ne 0 ]; then
    echo "❌ Failed to ensure pip."
    osascript -e 'display dialog "Failed to ensure pip." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

# Install required libraries
echo "Installing requirements..."
pip install --upgrade pip
if [ $? -ne 0 ]; then
    echo "❌ Failed to upgrade pip."
    osascript -e 'display dialog "Failed to upgrade pip." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install requirements from requirements.txt."
        osascript -e 'display dialog "Failed to install requirements from requirements.txt." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
        exit 1
    fi
else
    echo "❌ requirements.txt not found in $INSTALL_DIR."
    osascript -e 'display dialog "requirements.txt not found in '$INSTALL_DIR'." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

pip install flask
if [ $? -ne 0 ]; then
    echo "❌ Failed to install Flask."
    osascript -e 'display dialog "Failed to install Flask." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

pip install pandas
if [ $? -ne 0 ]; then
    echo "❌ Failed to install pandas."
    osascript -e 'display dialog "Failed to install pandas." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

# Ensure libhidapi.dylib is present
if [ ! -f "mac/libhidapi.dylib" ]; then
    echo "❌ libhidapi.dylib not found in mac folder."
    osascript -e 'display dialog "libhidapi.dylib not found in mac folder." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

# Modify hid/__init__.py to load libhidapi.dylib
HID_INIT_PATH="venv/lib/python3.8/site-packages/hid/__init__.py"
if [ -f "$HID_INIT_PATH" ]; then
    cp "$HID_INIT_PATH" "$HID_INIT_PATH.bak"
    echo "Created backup of hid/__init__.py at $HID_INIT_PATH.bak"

    TEMP_FILE=$(mktemp)
    echo "import os" > "$TEMP_FILE"
    echo "import ctypes" >> "$TEMP_FILE"
    echo "" >> "$TEMP_FILE"
    echo "# Explicitly load libhidapi.dylib from mac folder" >> "$TEMP_FILE"
    echo "lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../mac/libhidapi.dylib'))" >> "$TEMP_FILE"
    echo "hidapi = ctypes.cdll.LoadLibrary(lib_path)" >> "$TEMP_FILE"
    echo "" >> "$TEMP_FILE"
    echo "# Original library search loop disabled" >> "$TEMP_FILE"
    echo "# hidapi = None" >> "$TEMP_FILE"
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
    echo "#     except OSError:" >> "$TEMP_FILE"
    echo "#         pass" >> "$TEMP_FILE"
    echo "# else:" >> "$TEMP_FILE"
    echo "#     error = \"Unable to load any of the following libraries:{}\"\\\n#         .format(' '.join(library_paths))" >> "$TEMP_FILE"
    echo "#     raise ImportError(error)" >> "$TEMP_FILE"
    echo "" >> "$TEMP_FILE"
    cat "$HID_INIT_PATH" >> "$TEMP_FILE"
    sed -i '' '/hidapi = None/,/raise ImportError(/d' "$TEMP_FILE"
    mv "$TEMP_FILE" "$HID_INIT_PATH"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to modify hid/__init__.py."
        osascript -e 'display dialog "Failed to modify hid/__init__.py." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
        exit 1
    fi
    echo "Modified hid/__init__.py to load libhidapi.dylib"
else
    echo "❌ Could not find hid/__init__.py."
    osascript -e 'display dialog "Could not find hid/__init__.py." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

echo "Setup complete. Application is installed in $INSTALL_DIR."
echo "Postinstall script completed at $(date)"
osascript -e 'display dialog "Installation complete. Run run.command to launch the application." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
exit 0