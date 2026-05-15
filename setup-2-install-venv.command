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
    echo "Setting Python 3.8.10 via pyenv..."
    pyenv local 3.8.10
    pyenv shell 3.8.10
fi

# Create virtual environment if activate script is missing
if [ ! -f "venv/bin/activate" ]; then
    echo "Creating virtual environment..."
    rm -rf venv
    python3 -m venv venv
    if [ ! -f "venv/bin/activate" ]; then
        echo "❌ Failed to create virtual environment (venv/bin/activate not found)."
        exit 1
    fi
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

# Pre-compile bytecode for scipy/numpy so first app launch is not slow
echo "Pre-compiling Python bytecode for scientific libraries..."
python3 -m compileall -q venv/lib/python3.8/site-packages/scipy venv/lib/python3.8/site-packages/numpy 2>/dev/null || true
echo "✅ Bytecode pre-compilation complete."

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

# ── AI Assistant Setup (optional) ───────────────────────────────────────────
AI_SETTINGS_FILE="ai_settings.json"
if [ -f "$AI_SETTINGS_FILE" ]; then
    echo ""
    echo "  ℹ  AI Assistant settings already found (ai_settings.json)."
    read -p "     Reconfigure? [y/N]: " reconf_choice
    reconf_choice="${reconf_choice:-n}"
    if [[ ! "$reconf_choice" =~ ^[Yy]$ ]]; then
        echo "  Keeping existing AI settings."
    else
        rm -f "$AI_SETTINGS_FILE"
    fi
fi

if [ ! -f "$AI_SETTINGS_FILE" ]; then
    echo ""
    echo "  ╔══════════════════════════════════════════════════════════╗"
    echo "  ║   🤖  AI Assistant  (Optional Feature)                  ║"
    echo "  ╠══════════════════════════════════════════════════════════╣"
    echo "  ║  Answers questions about your data in 6 languages:       ║"
    echo "  ║  English · Tiếng Việt · 中文 · Français · 日本語 · Русский ║"
    echo "  ║  Powered by Ollama (local LLM — no internet after setup) ║"
    echo "  ╚══════════════════════════════════════════════════════════╝"
    echo ""
    read -p "  Install AI Assistant? [y/N]: " ai_choice
    ai_choice="${ai_choice:-n}"

    if [[ "$ai_choice" =~ ^[Yy]$ ]]; then
        AI_ENABLED="true"

        # ── Language selection (multi-select) ───────────────────────────────
        echo ""
        echo "  Choose languages (enter numbers separated by spaces, e.g. 1 2):"
        echo "    1) English   2) Tiếng Việt   3) 中文 (简体)"
        echo "    4) Français  5) 日本語        6) Русский"
        echo ""
        read -p "  Enter numbers [1-6, default=1]: " lang_input
        lang_input="${lang_input:-1}"
        AI_LANGS=()
        for num in $lang_input; do
            case "$num" in
                1) AI_LANGS+=("en") ;;
                2) AI_LANGS+=("vi") ;;
                3) AI_LANGS+=("zh") ;;
                4) AI_LANGS+=("fr") ;;
                5) AI_LANGS+=("ja") ;;
                6) AI_LANGS+=("ru") ;;
            esac
        done
        [ ${#AI_LANGS[@]} -eq 0 ] && AI_LANGS=("en")
        LANG_JSON="["
        _first=1
        for code in "${AI_LANGS[@]}"; do
            [ $_first -eq 0 ] && LANG_JSON+=","
            LANG_JSON+="\"$code\""
            _first=0
        done
        LANG_JSON+="]"
        echo "  ✓ Languages: ${AI_LANGS[*]}"

        # ── Model selection ─────────────────────────────────────────────────
        echo ""
        echo "  Choose AI model:"
        echo "    1) qwen2.5:7b  (4.7 GB) — Best multilingual  [recommended]"
        echo "    2) qwen2.5:3b  (1.9 GB) — Lighter, still multilingual"
        echo "    3) llama3.2:3b (2.0 GB) — Good English/French"
        echo "    4) mistral:7b  (4.1 GB) — Good European languages"
        echo ""
        read -p "  Enter number [1-4, default=1]: " model_choice
        case "${model_choice:-1}" in
            2) AI_MODEL="qwen2.5:3b";  AI_MODEL_SIZE="1.9 GB" ;;
            3) AI_MODEL="llama3.2:3b"; AI_MODEL_SIZE="2.0 GB" ;;
            4) AI_MODEL="mistral:7b";  AI_MODEL_SIZE="4.1 GB" ;;
            *) AI_MODEL="qwen2.5:7b";  AI_MODEL_SIZE="4.7 GB" ;;
        esac
        echo "  ✓ Model: $AI_MODEL"

        # ── Ollama check / pull ─────────────────────────────────────────────
        echo ""
        if command -v ollama &>/dev/null; then
            echo "  ✓ Ollama is installed."
            if ollama list 2>/dev/null | grep -q "^${AI_MODEL}"; then
                echo "  ✓ Model $AI_MODEL is already downloaded."
            else
                read -p "  Download $AI_MODEL now? ($AI_MODEL_SIZE, may take several minutes) [Y/n]: " pull_choice
                pull_choice="${pull_choice:-y}"
                if [[ "$pull_choice" =~ ^[Yy]$ ]]; then
                    echo "  Ensuring Ollama is running…"
                    if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
                        open -a Ollama &>/dev/null || ollama serve &>/dev/null &
                        echo "  Waiting for Ollama to start…"
                        for _i in $(seq 1 15); do
                            sleep 1
                            curl -sf http://localhost:11434/api/tags &>/dev/null && break || true
                        done
                    fi
                    echo "  Downloading $AI_MODEL…"
                    ollama pull "$AI_MODEL"
                    echo "  ✓ Model downloaded."
                else
                    echo "  ℹ  Skipped. You can download it from inside the app (🤖 button → Settings)."
                fi
            fi
        else
            echo "  ⚠  Ollama is not installed."
            read -p "  Install Ollama now? (requires Homebrew) [y/N]: " ollama_install_choice
            ollama_install_choice="${ollama_install_choice:-n}"
            if [[ "$ollama_install_choice" =~ ^[Yy]$ ]]; then
                echo "  Installing Ollama via Homebrew..."
                if ! command -v brew &>/dev/null; then
                    echo "  ❌ Homebrew is required for automated installation."
                    echo "     Please run setup-1-install-pyenv.command first."
                else
                    brew install --cask ollama
                    if [ $? -eq 0 ]; then
                        echo "  ✓ Ollama installed."
                        read -p "  Download $AI_MODEL now? ($AI_MODEL_SIZE, may take several minutes) [Y/n]: " pull_choice
                        pull_choice="${pull_choice:-y}"
                        if [[ "$pull_choice" =~ ^[Yy]$ ]]; then
                            echo "  Ensuring Ollama is running…"
                            if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
                                open -a Ollama &>/dev/null || ollama serve &>/dev/null &
                                echo "  Waiting for Ollama to start…"
                                for _i in $(seq 1 15); do
                                    sleep 1
                                    curl -sf http://localhost:11434/api/tags &>/dev/null && break || true
                                done
                            fi
                            echo "  Downloading $AI_MODEL…"
                            ollama pull "$AI_MODEL"
                            echo "  ✓ Model downloaded."
                        fi
                    else
                        echo "  ⚠  Ollama install failed. You can install it manually: https://ollama.com"
                    fi
                fi
            else
                echo "  ℹ  Skipped. Install Ollama later and then download the model from inside the app."
            fi
        fi

    else
        AI_ENABLED="false"
        LANG_JSON='["en"]'
        AI_MODEL="qwen2.5:7b"
        echo "  ℹ  AI Assistant disabled. Enable it any time from the 🤖 button inside the app."
    fi

    # Write ai_settings.json
    printf '{\n  "enabled": %s,\n  "preferred_languages": %s,\n  "model": "%s",\n  "ollama_url": "http://localhost:11434",\n  "first_run_shown": false\n}\n' \
        "$AI_ENABLED" "$LANG_JSON" "$AI_MODEL" > "$AI_SETTINGS_FILE"
    echo "  ✓ Saved: ai_settings.json"
fi
echo ""

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
