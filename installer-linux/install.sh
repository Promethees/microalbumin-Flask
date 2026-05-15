#!/bin/bash

# Log all output to a file for debugging
exec > >(tee -a /tmp/easyokapi-install.log) 2>&1
echo "Starting EasyOKAPI install script at $(date)"

# ── Helper: GUI prompt fallback chain ────────────────────────────────────────
# Usage: prompt_input <title> <message> <secret>
#   Returns result in $PROMPT_RESULT
prompt_input() {
    local title="$1" msg="$2" secret="${3:-false}"
    PROMPT_RESULT=""
    if command -v zenity &>/dev/null; then
        if [ "$secret" = "true" ]; then
            PROMPT_RESULT=$(zenity --password --title="$title" 2>/dev/null)
        else
            PROMPT_RESULT=$(zenity --entry --title="$title" --text="$msg" 2>/dev/null)
        fi
    elif command -v whiptail &>/dev/null; then
        if [ "$secret" = "true" ]; then
            PROMPT_RESULT=$(whiptail --passwordbox "$msg" 10 60 --title "$title" 3>&1 1>&2 2>&3)
        else
            PROMPT_RESULT=$(whiptail --inputbox "$msg" 10 60 --title "$title" 3>&1 1>&2 2>&3)
        fi
    else
        if [ "$secret" = "true" ]; then
            read -rsp "$msg: " PROMPT_RESULT; echo
        else
            read -rp "$msg: " PROMPT_RESULT
        fi
    fi
}

# Usage: prompt_confirm <title> <message>  → returns 0 for Yes, 1 for No
prompt_confirm() {
    local title="$1" msg="$2"
    if command -v zenity &>/dev/null; then
        zenity --question --title="$title" --text="$msg" 2>/dev/null
        return $?
    elif command -v whiptail &>/dev/null; then
        whiptail --yesno "$msg" 10 60 --title "$title" 3>&1 1>&2 2>&3
        return $?
    else
        read -rp "$msg [y/N]: " _ans
        [[ "$_ans" =~ ^[Yy]$ ]]
        return $?
    fi
}

# ── Root check ────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (sudo)."
    exit 1
fi

# ── Determine the real user (the one who ran sudo) ────────────────────────────
CURRENT_USER="${SUDO_USER:-}"
if [ -z "$CURRENT_USER" ] || [ "$CURRENT_USER" = "root" ]; then
    echo "❌ Unable to determine the invoking user. Run with: sudo ./install.sh"
    exit 1
fi
CURRENT_HOME=$(eval echo "~$CURRENT_USER")

# ── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_TAG="__APP_VERSION__"
INSTALL_DIR="/opt/EasyOKAPI"
REPO_URL="https://github.com/Promethees/microalbumin-Flask.git"
PYENV_ROOT="$CURRENT_HOME/.pyenv"
PYTHON_VERSION="3.8.10"

# ── Step 1: Install system dependencies ───────────────────────────────────────
echo "Installing system dependencies..."
apt-get update -y
apt-get install -y \
    git curl build-essential libssl-dev zlib1g-dev libbz2-dev \
    libreadline-dev libsqlite3-dev libffi-dev liblzma-dev \
    libusb-1.0-0-dev libudev-dev \
    libhidapi-hidraw0 libhidapi-dev \
    zenity whiptail
if [ $? -ne 0 ]; then
    echo "❌ Failed to install system dependencies."
    exit 1
fi
echo "✅ System dependencies installed."

# ── Step 2: Install pyenv for the real user ────────────────────────────────────
PYENV_BIN="$PYENV_ROOT/bin/pyenv"
if [ ! -d "$PYENV_ROOT" ]; then
    echo "Installing pyenv for $CURRENT_USER..."
    su - "$CURRENT_USER" -c 'curl -fsSL https://pyenv.run | bash'
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install pyenv."
        exit 1
    fi
fi

# Add pyenv to the user's .bashrc if not already present
SHELL_RC="$CURRENT_HOME/.bashrc"
if ! grep -q 'pyenv init' "$SHELL_RC" 2>/dev/null; then
    {
        echo ''
        echo '# pyenv'
        echo "export PYENV_ROOT=\"\$HOME/.pyenv\""
        echo 'export PATH="$PYENV_ROOT/bin:$PATH"'
        echo 'eval "$(pyenv init --path)"'
        echo 'eval "$(pyenv init -)"'
    } >> "$SHELL_RC"
    chown "$CURRENT_USER:$CURRENT_USER" "$SHELL_RC"
fi

# ── Step 3: Install Python 3.8.10 via pyenv ───────────────────────────────────
if ! su - "$CURRENT_USER" -c "PYENV_ROOT=$PYENV_ROOT $PYENV_BIN versions 2>/dev/null | grep -qF '$PYTHON_VERSION'"; then
    echo "Installing Python $PYTHON_VERSION via pyenv (this may take a few minutes)..."
    su - "$CURRENT_USER" -c "PYENV_ROOT=\"$PYENV_ROOT\" $PYENV_BIN install $PYTHON_VERSION"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install Python $PYTHON_VERSION."
        exit 1
    fi
fi
echo "✅ Python $PYTHON_VERSION available."

# ── Step 4: Prompt for EasyOKAPI token ────────────────────────────────────────
prompt_input "EasyOKAPI Installer" "Enter your Generated EasyOKAPI Token:" "true"
EASYOKAPI_TOKEN="$PROMPT_RESULT"
if [ -z "$EASYOKAPI_TOKEN" ]; then
    echo "❌ EasyOKAPI token is required. Installation aborted."
    exit 1
fi

# ── Step 5: Handle existing installation ──────────────────────────────────────
if [ -d "$INSTALL_DIR" ] && [ "$(find "$INSTALL_DIR" -maxdepth 1 | wc -l)" -gt 1 ]; then
    CURRENT_VERSION="Unknown"
    [ -f "$INSTALL_DIR/VERSION.txt" ] && CURRENT_VERSION=$(cat "$INSTALL_DIR/VERSION.txt")
    echo "Existing installation found: $CURRENT_VERSION → $VERSION_TAG"
    if prompt_confirm "EasyOKAPI Installer" "Existing installation found.\n\nCurrent: $CURRENT_VERSION\nNew: $VERSION_TAG\n\nOverwrite?"; then
        echo "Removing existing installation..."
        rm -rf "$INSTALL_DIR"
    else
        echo "Installation cancelled."
        exit 0
    fi
fi

# ── Step 6: Clone the repository ──────────────────────────────────────────────
echo "Cloning repository to $INSTALL_DIR..."
git clone "https://$EASYOKAPI_TOKEN@github.com/Promethees/microalbumin-Flask.git" "$INSTALL_DIR"
if [ $? -ne 0 ]; then
    echo "❌ Failed to clone repository. Check your token and network connection."
    exit 1
fi

cd "$INSTALL_DIR"
git checkout "tags/$VERSION_TAG"
if [ $? -ne 0 ]; then
    echo "❌ Failed to checkout tag $VERSION_TAG."
    exit 1
fi

# ── Step 7: Clean up dev-only files ───────────────────────────────────────────
echo "Cleaning up development files..."
rm -rf "$INSTALL_DIR/.git" "$INSTALL_DIR/.gitignore"
rm -rf "$INSTALL_DIR/tests" "$INSTALL_DIR/.github"
rm -rf "$INSTALL_DIR/installer-mac" "$INSTALL_DIR/installer-win" "$INSTALL_DIR/installer-linux"
rm -rf "$INSTALL_DIR/easyokapi-knowledge" "$INSTALL_DIR/images"
rm -f  "$INSTALL_DIR/log_hid_data_pyusb.py" "$INSTALL_DIR/generate-tree.sh"
rm -f  "$INSTALL_DIR/BUILD_MAC.md" "$INSTALL_DIR/Rule.md"
rm -f  "$INSTALL_DIR"/*.bat
echo "$VERSION_TAG" > "$INSTALL_DIR/VERSION.txt"

# ── Step 8: Create and populate virtual environment ───────────────────────────
echo "Setting up Python virtual environment..."
PYTHON_BIN="$PYENV_ROOT/versions/$PYTHON_VERSION/bin/python"
su - "$CURRENT_USER" -c "$PYTHON_BIN -m venv $INSTALL_DIR/venv"
if [ $? -ne 0 ]; then
    echo "❌ Failed to create virtual environment."
    exit 1
fi

VENV_PIP="$INSTALL_DIR/venv/bin/pip"
su - "$CURRENT_USER" -c "$VENV_PIP install --upgrade pip"
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    su - "$CURRENT_USER" -c "$VENV_PIP install -r $INSTALL_DIR/requirements.txt"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install requirements."
        exit 1
    fi
else
    echo "❌ requirements.txt not found."
    exit 1
fi
echo "✅ Virtual environment ready."

# ── Step 9: Download front-end vendor libraries ───────────────────────────────
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
        echo "❌ Failed to download $file."
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
    curl -fsSL "https://cdn.jsdelivr.net/npm/mathjax@3/es5/output/chtml/fonts/woff-v2/${font}.woff" \
        -o "$FONT_DIR/${font}.woff"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to download MathJax font: ${font}.woff"
        exit 1
    fi
done
echo "✅ Vendor libraries downloaded."

# ── Step 10: HID udev rule ────────────────────────────────────────────────────
echo "Installing HID udev rule..."
UDEV_RULE="/etc/udev/rules.d/99-easyokapi-hid.rules"
cat > "$UDEV_RULE" <<'UDEV'
# EasyOKAPI – PyBadge colorimeter HID access for all users
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="239a", MODE="0666"
SUBSYSTEM=="usb",    ATTRS{idVendor}=="239a", MODE="0666"
UDEV
udevadm control --reload-rules
udevadm trigger
echo "✅ udev rule installed."

# ── Step 11: Desktop entry ────────────────────────────────────────────────────
echo "Installing desktop entry..."
cat > /usr/share/applications/EasyOKAPI.desktop <<DESKTOP
[Desktop Entry]
Name=EasyOKAPI
Comment=PyBadge colorimeter biosensor app
Exec=bash -c 'pkexec env DISPLAY=\$DISPLAY XAUTHORITY=\$XAUTHORITY /opt/EasyOKAPI/run.sh'
Icon=/opt/EasyOKAPI/static/ht.ico
Terminal=true
Type=Application
Categories=Science;
DESKTOP
chmod 644 /usr/share/applications/EasyOKAPI.desktop
update-desktop-database /usr/share/applications/ 2>/dev/null || true
echo "✅ Desktop entry installed."

# ── Step 12: AI Assistant Setup (optional) ────────────────────────────────────
AI_SETTINGS_FILE="$INSTALL_DIR/ai_settings.json"
if [ ! -f "$AI_SETTINGS_FILE" ]; then
    if prompt_confirm "EasyOKAPI — AI Assistant" "Optional: Install AI Assistant?\n\nAnswers questions about your data and workflow in 6 languages:\nEnglish · Tiếng Việt · 中文 · Français · 日本語 · Русский\n\nPowered by Ollama (local LLM — no internet needed after setup)."; then
        AI_ENABLED="true"

        # Language selection (simple prompt for now as monolithic might be CLI-only fallback)
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

        # Model selection
        echo ""
        echo "  Choose AI model:"
        echo "    1) qwen2.5:7b  (4.7 GB) — Best multilingual"
        echo "    2) qwen2.5:3b  (1.9 GB) — Lighter"
        echo ""
        read -p "  Enter number [1-2, default=1]: " model_choice
        case "${model_choice:-1}" in
            2) AI_MODEL="qwen2.5:3b";  AI_MODEL_SIZE="1.9 GB" ;;
            *) AI_MODEL="qwen2.5:7b";  AI_MODEL_SIZE="4.7 GB" ;;
        esac

        # Ollama check / install
        echo ""
        _ensure_ollama_running() {
            if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
                systemctl start ollama 2>/dev/null || su - "$CURRENT_USER" -c "ollama serve &>/dev/null &"
                echo "  Waiting for Ollama to start…"
                for _i in $(seq 1 15); do
                    sleep 1
                    curl -sf http://localhost:11434/api/tags &>/dev/null && break || true
                done
            fi
        }
        if command -v ollama &>/dev/null; then
            echo "  ✓ Ollama is installed."
            if ollama list 2>/dev/null | grep -q "^${AI_MODEL}"; then
                echo "  ✓ Model $AI_MODEL is already downloaded."
            else
                if prompt_confirm "AI Model Download" "Download $AI_MODEL now? ($AI_MODEL_SIZE)"; then
                    _ensure_ollama_running
                    echo "  Downloading $AI_MODEL…"
                    su - "$CURRENT_USER" -c "ollama pull $AI_MODEL"
                fi
            fi
        else
            if prompt_confirm "Install Ollama" "Ollama is not installed. Install it now? (requires internet)"; then
                echo "  Installing Ollama…"
                curl -fsSL https://ollama.com/install.sh | sh
                if command -v ollama &>/dev/null; then
                    echo "  ✓ Ollama installed."
                    if prompt_confirm "AI Model Download" "Download $AI_MODEL now?"; then
                        _ensure_ollama_running
                        echo "  Downloading $AI_MODEL…"
                        su - "$CURRENT_USER" -c "ollama pull $AI_MODEL"
                    fi
                fi
            fi
        fi
    else
        AI_ENABLED="false"
        LANG_JSON='["en"]'
        AI_MODEL="qwen2.5:7b"
    fi

    printf '{\n  "enabled": %s,\n  "preferred_languages": %s,\n  "model": "%s",\n  "ollama_url": "http://localhost:11434",\n  "first_run_shown": false\n}\n' \
        "$AI_ENABLED" "$LANG_JSON" "$AI_MODEL" > "$AI_SETTINGS_FILE"
    chown "$CURRENT_USER:$CURRENT_USER" "$AI_SETTINGS_FILE"
fi

# ── Step 13: Copy run/uninstall scripts into install dir ─────────────────────
cp "$SCRIPT_DIR/run.sh"        "$INSTALL_DIR/run.sh"
cp "$SCRIPT_DIR/uninstall.sh"  "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/run.sh" "$INSTALL_DIR/uninstall.sh"

# Fix ownership
chown -R "$CURRENT_USER:$CURRENT_USER" "$INSTALL_DIR"

echo ""
echo "✅ EasyOKAPI $VERSION_TAG installed to $INSTALL_DIR"
echo "   Run with: sudo $INSTALL_DIR/run.sh"
echo "   Or launch from your desktop application menu."
echo "Install script completed at $(date)"
exit 0
