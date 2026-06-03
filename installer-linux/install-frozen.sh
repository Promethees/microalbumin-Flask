#!/bin/bash
# install-frozen.sh — installer for the no-source (PyInstaller) Linux build.
#
# Unlike install.sh (the source build) this needs no apt build deps, pyenv,
# Python build, source download, venv, or vendor fetch — the frozen onedir embeds
# all of that. It still needs root to place files under /opt, install a udev rule
# for the PyBadge serial port, and add a desktop entry; but RUNNING the app needs
# no root (CDC serial, not HID). User data lives in ~/.local/share/EasyOKAPI and
# is migrated from any old source install first.
#
# Usage:  sudo ./EasyOKAPI/install-frozen.sh

set -e

RESET="\033[0m"; BOLD="\033[1m"; GREEN="\033[32m"; CYAN="\033[36m"; RED="\033[31m"
print_step() { echo -e "\n  ${BOLD}${CYAN}▶  $1${RESET}"; }
print_ok()   { echo -e "  ${GREEN}✔  $1${RESET}"; }
print_fail() { echo -e "  ${RED}✗  $1${RESET}"; }

if [ "$EUID" -ne 0 ]; then
    print_fail "This installer must be run as root:  sudo ./EasyOKAPI/install-frozen.sh"
    exit 1
fi
CURRENT_USER="${SUDO_USER:-}"
if [ -z "$CURRENT_USER" ] || [ "$CURRENT_USER" = "root" ]; then
    print_fail "Unable to determine the invoking user. Run with: sudo ./EasyOKAPI/install-frozen.sh"
    exit 1
fi
CURRENT_HOME=$(eval echo "~$CURRENT_USER")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/EasyOKAPI"
APPDATA="$CURRENT_HOME/.local/share/EasyOKAPI"

echo ""
echo -e "  ${BOLD}${CYAN}⬡  HTBiotec · EasyOKAPI · No-source installer${RESET}"
echo ""

# ── Migrate user data from an old source install (it also lived at $INSTALL_DIR) ─
print_step "Migrating data from any previous installation"
if [ -d "$INSTALL_DIR" ] && { [ -f "$INSTALL_DIR/main.py" ] || [ -d "$INSTALL_DIR/venv" ]; }; then
    mkdir -p "$APPDATA"
    for d in data json report log; do
        if [ -d "$INSTALL_DIR/$d" ]; then
            mkdir -p "$APPDATA/$d"
            cp -rn "$INSTALL_DIR/$d/." "$APPDATA/$d/" 2>/dev/null || true
        fi
    done
    for f in activation.json user_settings.json ai_settings.json .env; do
        if [ -f "$INSTALL_DIR/$f" ] && [ ! -f "$APPDATA/$f" ]; then
            cp "$INSTALL_DIR/$f" "$APPDATA/$f" 2>/dev/null || true
        fi
    done
    chown -R "$CURRENT_USER:$CURRENT_USER" "$APPDATA"
    print_ok "Previous data migrated to $APPDATA"
else
    print_ok "No previous source install to migrate."
fi

# ── Replace the install dir with the frozen onedir ───────────────────────────
print_step "Installing application binary"
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -R "$SCRIPT_DIR/EasyOKAPI" "$INSTALL_DIR/EasyOKAPI"
cp "$SCRIPT_DIR/run-frozen.sh" "$INSTALL_DIR/run-frozen.sh"
[ -f "$SCRIPT_DIR/okapi.png" ] && cp "$SCRIPT_DIR/okapi.png" "$INSTALL_DIR/okapi.png"
chmod +x "$INSTALL_DIR/run-frozen.sh" "$INSTALL_DIR/EasyOKAPI/EasyOKAPI"
print_ok "Installed to $INSTALL_DIR"

# ── udev rule: user-level access to the PyBadge CDC serial port ──────────────
print_step "Installing udev rule for the colorimeter serial port"
cat > /etc/udev/rules.d/99-easyokapi-cdc.rules <<'UDEV'
# EasyOKAPI – PyBadge colorimeter CDC serial access for all users
SUBSYSTEM=="tty", ATTRS{idVendor}=="239a", MODE="0666"
UDEV
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger 2>/dev/null || true
print_ok "udev rule installed."

# ── Desktop entry — launches the binary as the user, no sudo ─────────────────
print_step "Installing desktop entry"
ICON="/opt/EasyOKAPI/okapi.png"
[ -f "$ICON" ] || ICON="/opt/EasyOKAPI/EasyOKAPI/_internal/static/ht.ico"
cat > /usr/share/applications/EasyOKAPI.desktop <<DESKTOP
[Desktop Entry]
Name=EasyOKAPI
Comment=PyBadge colorimeter biosensor app
Exec=/opt/EasyOKAPI/run-frozen.sh
Icon=$ICON
Terminal=false
Type=Application
Categories=Science;
DESKTOP
chmod 644 /usr/share/applications/EasyOKAPI.desktop
update-desktop-database /usr/share/applications/ 2>/dev/null || true
print_ok "Desktop entry installed."

echo ""
echo -e "  ${BOLD}${GREEN}✔  EasyOKAPI installed.${RESET}"
echo -e "     Launch it from your application menu, or run: ${BOLD}/opt/EasyOKAPI/run-frozen.sh${RESET}"
echo -e "     Your data lives in: ${BOLD}$APPDATA${RESET}"
echo ""
exit 0
