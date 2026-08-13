#!/bin/bash

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
RED="\033[31m"

# ── Helpers ───────────────────────────────────────────────────────────────────
print_step() { echo -e "\n  ${BOLD}${CYAN}▶  $1${RESET}"; }
print_ok()   { echo -e "  ${GREEN}✔  $1${RESET}"; }
print_fail() { echo -e "  ${RED}✗  $1${RESET}"; }
prompt_confirm() {
    local title="$1" msg="$2"
    if command -v whiptail &>/dev/null; then
        whiptail --yesno "$msg" 10 60 --title "$title" 3>&1 1>&2 2>&3
        return $?
    else
        read -rp "$msg [y/N]: " _ans
        [[ "$_ans" =~ ^[Yy]$ ]]
        return $?
    fi
}

# ── Banner ────────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "  ${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${CYAN}║  ⬡  HTBiotec · EasyOKAPI · Step 2/2      ║${RESET}"
echo -e "  ${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# Log all output to a file for debugging
exec > >(tee -a /tmp/easyokapi-step2.log) 2>&1
echo "Starting EasyOKAPI install step 2 at $(date)"

# ── Root check ────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    print_fail "This script must be run as root (sudo)."
    exit 1
fi

# ── Determine the real user (the one who ran sudo) ────────────────────────────
CURRENT_USER="${SUDO_USER:-}"
if [ -z "$CURRENT_USER" ] || [ "$CURRENT_USER" = "root" ]; then
    print_fail "Unable to determine the invoking user. Run with: sudo ./install-2-venv.sh"
    exit 1
fi
CURRENT_HOME=$(eval echo "~$CURRENT_USER")

# ── Configuration ─────────────────────────────────────────────────────────────
INSTALL_DIR="/opt/EasyOKAPI"
PYTHON_VERSION="3.12.11"
PYENV_ROOT="$CURRENT_HOME/.pyenv"

# ── Preflight: require step 1 to have run ─────────────────────────────────────
if [ ! -d "$INSTALL_DIR" ]; then
    print_fail "$INSTALL_DIR not found. Please run install-1-deps-clone.sh first."
    exit 1
fi

cd "$INSTALL_DIR"

# ── Step 1: Create virtual environment ────────────────────────────────────────
print_step "1 / 3  Creating virtual environment"
PYTHON_BIN="$PYENV_ROOT/versions/$PYTHON_VERSION/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo "❌ Python $PYTHON_VERSION not found at $PYTHON_BIN."
    echo "   Please run install-1-deps-clone.sh first."
    exit 1
fi

if [ ! -d "venv" ]; then
    su - "$CURRENT_USER" -c "$PYTHON_BIN -m venv $INSTALL_DIR/venv"
    if [ $? -ne 0 ]; then
        print_fail "Failed to create virtual environment."
        exit 1
    fi
fi

VENV_PIP="$INSTALL_DIR/venv/bin/pip"
su - "$CURRENT_USER" -c "$VENV_PIP install --upgrade pip"

if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    su - "$CURRENT_USER" -c "$VENV_PIP install -r $INSTALL_DIR/requirements.txt"
    if [ $? -ne 0 ]; then
        print_fail "Failed to install requirements."
        exit 1
    fi
else
    print_fail "requirements.txt not found in $INSTALL_DIR."
    exit 1
fi
print_ok "Virtual environment ready."

# ── Pre-compile bytecode for scipy/numpy so first app launch is not slow ──────
echo "  Pre-compiling Python bytecode for scientific libraries…"
VENV_PYTHON="$INSTALL_DIR/venv/bin/python"
su - "$CURRENT_USER" -c "$VENV_PYTHON -m compileall -q $INSTALL_DIR/venv/lib/python3.12/site-packages/scipy $INSTALL_DIR/venv/lib/python3.12/site-packages/numpy 2>/dev/null" || true
print_ok "Bytecode pre-compilation complete."

# ── Step 2: Download front-end vendor libraries ───────────────────────────────
print_step "2 / 3  Downloading front-end vendor libraries"
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
        print_fail "Failed to download $file."
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
        print_fail "Failed to download MathJax font: ${font}.woff"
        exit 1
    fi
done
print_ok "Vendor libraries downloaded."

# ── Step 3: HID udev rule & desktop entry ─────────────────────────────────────
print_step "3 / 3  Finalising installation"
UDEV_RULE="/etc/udev/rules.d/99-easyokapi-hid.rules"
cat > "$UDEV_RULE" <<'UDEV'
# EasyOKAPI – PyBadge colorimeter HID access for all users
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="239a", MODE="0666"
SUBSYSTEM=="usb",    ATTRS{idVendor}=="239a", MODE="0666"
UDEV
udevadm control --reload-rules
udevadm trigger
print_ok "udev rule installed."
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
print_ok "Desktop entry installed."

# ── Step 5: Copy run/uninstall scripts into install dir ───────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/run.sh"        "$INSTALL_DIR/run.sh"
cp "$SCRIPT_DIR/uninstall.sh"  "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/run.sh" "$INSTALL_DIR/uninstall.sh"

# ── Offer to import the bundled sample measurement data ───────────────────────
# sample_data/ ships in the source tarball as example CSVs. The app lists
# immediate subfolders of data/ as data folders, so importing copies it to
# data/sample_data/. The source copy is removed afterwards either way.
if [ -d "$INSTALL_DIR/sample_data" ]; then
    if prompt_confirm "EasyOKAPI Installer" "EasyOKAPI includes a set of sample measurement files.\n\nImport them into your data folder (as a 'sample_data' folder) so you can explore the app right away?"; then
        mkdir -p "$INSTALL_DIR/data/sample_data"
        cp -r "$INSTALL_DIR/sample_data/." "$INSTALL_DIR/data/sample_data/"
        print_ok "Sample data imported into data/sample_data."
    fi
    rm -rf "$INSTALL_DIR/sample_data"
fi

# Fix ownership
chown -R "$CURRENT_USER:$CURRENT_USER" "$INSTALL_DIR"

echo ""
echo -e "  ${BOLD}${GREEN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${GREEN}║  EasyOKAPI installation complete!        ║${RESET}"
echo -e "  ${BOLD}${GREEN}╚══════════════════════════════════════════╝${RESET}"
echo ""
print_ok "All steps finished."
echo -e "     Run with: ${BOLD}sudo $INSTALL_DIR/run.sh${RESET}"
echo -e "     Or launch from your desktop application menu."
echo ""
echo "Step 2 completed at $(date)"
exit 0
