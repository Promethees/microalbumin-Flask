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
    osascript -e 'display dialog "Installation directory not found. Please run install-homebrew-and-clone.command first." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
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
    osascript -e 'display dialog "Python 3.8.10 is required but not found. Current version: '$PY_VER'" buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    exit 1
fi

# Create virtual environment if activate script is missing
if [ ! -f "venv/bin/activate" ]; then
    echo "Creating virtual environment..."
    rm -rf venv
    python3 -m venv venv
    if [ ! -f "venv/bin/activate" ]; then
        echo "❌ Failed to create virtual environment (venv/bin/activate not found)."
        osascript -e 'display dialog "Failed to create virtual environment." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
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
    osascript -e 'display dialog "Failed to ensure pip." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    exit 1
fi

# Install required libraries
echo "Installing requirements..."
pip install --upgrade pip
if [ $? -ne 0 ]; then
    echo "❌ Failed to upgrade pip."
    osascript -e 'display dialog "Failed to upgrade pip." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    exit 1
fi

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install requirements from requirements.txt."
        osascript -e 'display dialog "Failed to install requirements from requirements.txt." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
        exit 1
    fi
else
    echo "❌ requirements.txt not found in $INSTALL_DIR."
    osascript -e 'display dialog "requirements.txt not found in '$INSTALL_DIR'." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    exit 1
fi

pip install flask
if [ $? -ne 0 ]; then
    echo "❌ Failed to install Flask."
    osascript -e 'display dialog "Failed to install Flask." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    exit 1
fi

pip install pandas
if [ $? -ne 0 ]; then
    echo "❌ Failed to install pandas."
    osascript -e 'display dialog "Failed to install pandas." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    exit 1
fi

# Pre-compile bytecode for scipy/numpy so first app launch is not slow
echo "Pre-compiling Python bytecode for scientific libraries..."
python3 -m compileall -q venv/lib/python3.8/site-packages/scipy venv/lib/python3.8/site-packages/numpy 2>/dev/null || true
echo "✅ Bytecode pre-compilation complete."

# Download front-end vendor libraries into static/vendor/
echo "Downloading front-end vendor libraries..."
VENDOR_DIR="$INSTALL_DIR/static/vendor"
FONT_DIR="$VENDOR_DIR/mathjax-fonts"
mkdir -p "$FONT_DIR"

VENDOR_URLS=(
    "https://code.jquery.com/jquery-3.6.0.min.js|jquery-3.6.0.min.js"
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js|chart.umd.min.js"
    "https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.0.0/dist/chartjs-plugin-annotation.min.js|chartjs-plugin-annotation-2.0.0.min.js"
    "https://cdn.jsdelivr.net/npm/sweetalert2@11/dist/sweetalert2.all.min.js|sweetalert2.all.min.js"
    "https://cdnjs.cloudflare.com/ajax/libs/numeric/1.2.6/numeric.min.js|numeric-1.2.6.min.js"
    "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js|mathjax-tex-mml-chtml.js"
)

for entry in "${VENDOR_URLS[@]}"; do
    url="${entry%%|*}"
    file="${entry##*|}"
    echo "  Downloading $file..."
    curl -fsSL "$url" -o "$VENDOR_DIR/$file"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to download $file from $url"
        osascript -e "display dialog \"Failed to download vendor library: $file\" buttons {\"OK\"} default button \"OK\" with title \"EasyOKAPI Installer\""
        exit 1
    fi
done

MATHJAX_FONTS=(
    "MathJax_AMS-Regular" "MathJax_Main-Regular" "MathJax_Main-Bold" "MathJax_Main-Italic"
    "MathJax_Math-Italic" "MathJax_Math-BoldItalic" "MathJax_Size1-Regular" "MathJax_Size2-Regular"
    "MathJax_Size3-Regular" "MathJax_Size4-Regular" "MathJax_Calligraphic-Regular"
    "MathJax_Calligraphic-Bold" "MathJax_Fraktur-Regular" "MathJax_Fraktur-Bold"
    "MathJax_SansSerif-Regular" "MathJax_SansSerif-Bold" "MathJax_SansSerif-Italic"
    "MathJax_Script-Regular" "MathJax_Typewriter-Regular" "MathJax_Vector-Regular"
    "MathJax_Vector-Bold" "MathJax_Zero"
)

for font in "${MATHJAX_FONTS[@]}"; do
    echo "  Downloading font ${font}.woff..."
    curl -fsSL "https://cdn.jsdelivr.net/npm/mathjax@3/es5/output/chtml/fonts/woff-v2/${font}.woff" -o "$FONT_DIR/${font}.woff"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to download MathJax font: ${font}.woff"
        osascript -e "display dialog \"Failed to download MathJax font: ${font}.woff\" buttons {\"OK\"} default button \"OK\" with title \"EasyOKAPI Installer\""
        exit 1
    fi
done
echo "✅ Vendor libraries downloaded successfully."

# Ensure libhidapi.dylib is present
if [ ! -f "mac/libhidapi.dylib" ]; then
    echo "❌ libhidapi.dylib not found in mac folder."
    osascript -e 'display dialog "libhidapi.dylib not found in mac folder." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
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
        osascript -e 'display dialog "Failed to modify hid/__init__.py." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
        exit 1
    fi
    echo "Modified hid/__init__.py to load libhidapi.dylib"
else
    echo "❌ Could not find hid/__init__.py."
    osascript -e 'display dialog "Could not find hid/__init__.py." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    exit 1
fi

echo "Setup complete. Application is installed in $INSTALL_DIR."
echo "Postinstall script completed at $(date)"
osascript -e 'display dialog "Installation complete. Run run.command to launch the application." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
exit 0