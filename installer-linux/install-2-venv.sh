#!/bin/bash

# Log all output to a file for debugging
exec > >(tee -a /tmp/easyokapi-step2.log) 2>&1
echo "Starting EasyOKAPI install step 2 at $(date)"

# ── Root check ────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (sudo)."
    exit 1
fi

# ── Determine the real user (the one who ran sudo) ────────────────────────────
CURRENT_USER="${SUDO_USER:-}"
if [ -z "$CURRENT_USER" ] || [ "$CURRENT_USER" = "root" ]; then
    echo "❌ Unable to determine the invoking user. Run with: sudo ./install-2-venv.sh"
    exit 1
fi
CURRENT_HOME=$(eval echo "~$CURRENT_USER")

# ── Configuration ─────────────────────────────────────────────────────────────
INSTALL_DIR="/opt/EasyOKAPI"
PYTHON_VERSION="3.8.10"
PYENV_ROOT="$CURRENT_HOME/.pyenv"

# ── Preflight: require step 1 to have run ─────────────────────────────────────
if [ ! -d "$INSTALL_DIR" ]; then
    echo "❌ $INSTALL_DIR not found. Please run install-1-deps-clone.sh first."
    exit 1
fi

cd "$INSTALL_DIR"

# ── Step 1: Create virtual environment ────────────────────────────────────────
echo "Setting up Python virtual environment..."
PYTHON_BIN="$PYENV_ROOT/versions/$PYTHON_VERSION/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo "❌ Python $PYTHON_VERSION not found at $PYTHON_BIN."
    echo "   Please run install-1-deps-clone.sh first."
    exit 1
fi

if [ ! -d "venv" ]; then
    su - "$CURRENT_USER" -c "$PYTHON_BIN -m venv $INSTALL_DIR/venv"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create virtual environment."
        exit 1
    fi
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
    echo "❌ requirements.txt not found in $INSTALL_DIR."
    exit 1
fi
echo "✅ Virtual environment ready."

# ── Step 2: Download front-end vendor libraries ───────────────────────────────
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

# ── Step 3: HID udev rule ─────────────────────────────────────────────────────
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

# ── Step 4: Desktop entry ─────────────────────────────────────────────────────
echo "Installing desktop entry..."
cat > /usr/share/applications/EasyOKAPI.desktop <<DESKTOP
[Desktop Entry]
Name=EasyOKAPI
Comment=PyBadge colorimeter biosensor app
Exec=bash -c 'pkexec env DISPLAY=\$DISPLAY XAUTHORITY=\$XAUTHORITY /opt/EasyOKAPI/run.sh'
Icon=/opt/EasyOKAPI/static/favicon.ico
Terminal=true
Type=Application
Categories=Science;
DESKTOP
chmod 644 /usr/share/applications/EasyOKAPI.desktop
update-desktop-database /usr/share/applications/ 2>/dev/null || true
echo "✅ Desktop entry installed."

# ── Step 5: Copy run/uninstall scripts into install dir ───────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/run.sh"        "$INSTALL_DIR/run.sh"
cp "$SCRIPT_DIR/uninstall.sh"  "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/run.sh" "$INSTALL_DIR/uninstall.sh"

# Fix ownership
chown -R "$CURRENT_USER:$CURRENT_USER" "$INSTALL_DIR"

echo ""
echo "✅ EasyOKAPI installation complete."
echo "   Run with: sudo $INSTALL_DIR/run.sh"
echo "   Or launch from your desktop application menu."
echo "Step 2 completed at $(date)"
exit 0
