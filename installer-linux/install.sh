#!/bin/bash

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
RED="\033[31m"
YELLOW="\033[33m"

# ── Helpers ───────────────────────────────────────────────────────────────────
print_step() { echo -e "\n  ${BOLD}${CYAN}▶  $1${RESET}"; }
print_ok()   { echo -e "  ${GREEN}✔  $1${RESET}"; }
print_fail() { echo -e "  ${RED}✗  $1${RESET}"; }
print_warn() { echo -e "  ${YELLOW}⚠  $1${RESET}"; }

# ── Banner ────────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "  ${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${CYAN}║  ⬡  HTBiotec · EasyOKAPI · Installer     ║${RESET}"
echo -e "  ${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# Log all output to a file for debugging
exec > >(tee -a /tmp/easyokapi-install.log) 2>&1
echo "Starting EasyOKAPI install script at $(date)"

# ── Terminal prompt helpers ───────────────────────────────────────────────────
# install.sh always runs as root (enforced below). Root processes cannot use
# the user's X11/Wayland display session — even with DISPLAY forwarded, the
# compositor rejects root connections or renders a screenshot artifact.
# All GUI interaction is handled by setup.sh as the regular user before sudo
# is invoked. These helpers use whiptail (terminal TUI) or plain read only.

# Usage: prompt_input <title> <message> <secret>
#   Returns result in $PROMPT_RESULT
prompt_input() {
    local title="$1" msg="$2" secret="${3:-false}"
    PROMPT_RESULT=""
    if command -v whiptail &>/dev/null; then
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
    if command -v whiptail &>/dev/null; then
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
    print_fail "This script must be run as root (sudo)."
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
AUTH_BASE_URL="__AUTH_BASE_URL__"
INSTALL_DIR="/opt/EasyOKAPI"
PYENV_ROOT="$CURRENT_HOME/.pyenv"
PYTHON_VERSION="3.8.10"
BACKUP_DIR=""
# Okapi mascot icon bundled alongside the install scripts (added by build-tarball.sh)
OKAPI_ICON="$SCRIPT_DIR/okapi.png"

# ── Step 1: Install system dependencies ───────────────────────────────────────
print_step "1 / 5  Installing system dependencies"
apt-get update -y
apt-get install -y \
    git curl build-essential libssl-dev zlib1g-dev libbz2-dev \
    libreadline-dev libsqlite3-dev libffi-dev liblzma-dev \
    libusb-1.0-0-dev libudev-dev \
    libhidapi-hidraw0 libhidapi-dev \
    zenity whiptail
if [ $? -ne 0 ]; then
    print_fail "Failed to install system dependencies."
    exit 1
fi
print_ok "System dependencies installed."

# ── Step 2: Install pyenv for the real user ────────────────────────────────────
print_step "2 / 5  Installing pyenv & Python $PYTHON_VERSION"
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
    echo "  Installing Python $PYTHON_VERSION via pyenv (this may take a few minutes)…"
    su - "$CURRENT_USER" -c "PYENV_ROOT=\"$PYENV_ROOT\" $PYENV_BIN install $PYTHON_VERSION"
    if [ $? -ne 0 ]; then
        print_fail "Failed to install Python $PYTHON_VERSION."
        exit 1
    fi
fi
print_ok "Python $PYTHON_VERSION available."

# ── Step 4: Prompt for EasyOKAPI download token ───────────────────────────────
print_step "3 / 5  Downloading EasyOKAPI"
# setup.sh collects the token as the regular user (before sudo) and passes it
# here via EASYOKAPI_DOWNLOAD_TOKEN so zenity never needs to run as root.
if [ -n "${EASYOKAPI_DOWNLOAD_TOKEN:-}" ]; then
    DOWNLOAD_TOKEN="$EASYOKAPI_DOWNLOAD_TOKEN"
    unset EASYOKAPI_DOWNLOAD_TOKEN
    print_ok "Download token received from setup launcher."
else
    prompt_input "EasyOKAPI Installer" "Enter your Generated EasyOKAPI Token:" "true"
    DOWNLOAD_TOKEN="$PROMPT_RESULT"
fi
if [ -z "$DOWNLOAD_TOKEN" ]; then
    print_fail "EasyOKAPI token is required. Installation aborted."
    exit 1
fi

# ── Step 5: Handle existing installation ──────────────────────────────────────
if [ -d "$INSTALL_DIR" ] && [ "$(find "$INSTALL_DIR" -maxdepth 1 | wc -l)" -gt 1 ]; then
    CURRENT_VERSION="Unknown"
    [ -f "$INSTALL_DIR/VERSION.txt" ] && CURRENT_VERSION=$(cat "$INSTALL_DIR/VERSION.txt")
    echo "Existing installation found: $CURRENT_VERSION → $VERSION_TAG"
    if prompt_confirm "EasyOKAPI Installer" "Existing installation found.\n\nCurrent: $CURRENT_VERSION\nNew: $VERSION_TAG\n\nOverwrite?"; then
        echo "Backing up user data (data/, json/, report/)..."
        BACKUP_DIR="/tmp/easyokapi_userdata_backup_$$"
        mkdir -p "$BACKUP_DIR"
        for _dir in data json report; do
            [ -d "$INSTALL_DIR/$_dir" ] && cp -r "$INSTALL_DIR/$_dir" "$BACKUP_DIR/$_dir"
        done
        echo "Removing existing installation..."
        rm -rf "$INSTALL_DIR"
    else
        echo "Installation cancelled."
        exit 0
    fi
fi

# ── Step 6: Download the application ──────────────────────────────────────────
ARCHIVE_TMP="/tmp/easyokapi_app.tar.gz"
echo "Downloading application to $INSTALL_DIR..."
curl -L -o "$ARCHIVE_TMP" "$AUTH_BASE_URL/api/download?token=$DOWNLOAD_TOKEN"
if [ $? -ne 0 ] || [ ! -s "$ARCHIVE_TMP" ]; then
    echo "❌ Failed to download the application. Check your token and network connection."
    exit 1
fi

mkdir -p "$INSTALL_DIR"
tar -xzf "$ARCHIVE_TMP" -C "$INSTALL_DIR" --strip-components=1
if [ $? -ne 0 ]; then
    echo "❌ Failed to extract the application archive."
    rm -f "$ARCHIVE_TMP"
    exit 1
fi
rm -f "$ARCHIVE_TMP"

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

# Write activation.json — the download token doubles as the license token for the AI proxy
printf '{\n  "license_token": "%s"\n}\n' "$DOWNLOAD_TOKEN" > "$INSTALL_DIR/activation.json"

# ── Step 8: Create and populate virtual environment ───────────────────────────
print_step "4 / 5  Setting up virtual environment"
echo "  Creating virtual environment…"
PYTHON_BIN="$PYENV_ROOT/versions/$PYTHON_VERSION/bin/python"
su - "$CURRENT_USER" -c "$PYTHON_BIN -m venv $INSTALL_DIR/venv"
if [ $? -ne 0 ]; then
    print_fail "Failed to create virtual environment."
    exit 1
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
    print_fail "requirements.txt not found."
    exit 1
fi
print_ok "Virtual environment ready."

# ── Step 9: Download front-end vendor libraries ───────────────────────────────
print_step "5 / 5  Downloading front-end vendor libraries"
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

# ── Step 10: HID udev rule ────────────────────────────────────────────────────
UDEV_RULE="/etc/udev/rules.d/99-easyokapi-hid.rules"
cat > "$UDEV_RULE" <<'UDEV'
# EasyOKAPI – PyBadge colorimeter HID access for all users
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="239a", MODE="0666"
SUBSYSTEM=="usb",    ATTRS{idVendor}=="239a", MODE="0666"
UDEV
udevadm control --reload-rules
udevadm trigger
print_ok "udev rule installed."

# ── Step 11: Desktop entry ────────────────────────────────────────────────────
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
print_ok "Desktop entry installed."

# ── Step 12: Copy run/uninstall scripts into install dir ─────────────────────
cp "$SCRIPT_DIR/run.sh"        "$INSTALL_DIR/run.sh"
cp "$SCRIPT_DIR/uninstall.sh"  "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/run.sh" "$INSTALL_DIR/uninstall.sh"

# Restore user data preserved from the previous installation
if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
    echo "Restoring user data (data/, json/, report/)..."
    for _dir in data json report; do
        if [ -d "$BACKUP_DIR/$_dir" ]; then
            cp -r "$BACKUP_DIR/$_dir" "$INSTALL_DIR/$_dir"
        fi
    done
    rm -rf "$BACKUP_DIR"
    echo "✅ User data restored."
fi

# Fix ownership
chown -R "$CURRENT_USER:$CURRENT_USER" "$INSTALL_DIR"

echo ""
echo -e "  ${BOLD}${GREEN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${GREEN}║  EasyOKAPI installed successfully!       ║${RESET}"
echo -e "  ${BOLD}${GREEN}╚══════════════════════════════════════════╝${RESET}"
echo ""
print_ok "EasyOKAPI $VERSION_TAG installed to $INSTALL_DIR"
echo -e "     Run with: ${BOLD}sudo $INSTALL_DIR/run.sh${RESET}"
echo -e "     Or launch from your desktop application menu."
echo ""
echo "Install script completed at $(date)"
exit 0
