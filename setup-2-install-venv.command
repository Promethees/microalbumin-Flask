#!/bin/bash

# Exit on error
set -e

# Change to the script's directory
cd "$(dirname "$0")"

# Initialize pyenv
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

# Set Python 3.8.10 as the local version for this directory
# Check Python version
sudo pyenv global 3.8.10 
PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
if [ "$PY_VER" != "3.8.10" ]; then
    echo "❌ Python 3.8.10 is required. Current version: $PY_VER"
    pyenv local 3.8.10 | echo "Setting Python 3.8.10 via pyenv..."
    pyenv shell 3.8.10
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

# Download front-end vendor libraries into static/vendor/
echo "Downloading front-end vendor libraries..."
SCRIPT_DIR="$(dirname "$0")"
VENDOR_DIR="$SCRIPT_DIR/static/vendor"
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
        exit 1
    fi
done
echo "✅ Vendor libraries downloaded successfully."

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
echo "Proceed to setup-3-run.command to launch the app"
read -n 1 -s -r -p "Installation process done, press any key to proceed..."
