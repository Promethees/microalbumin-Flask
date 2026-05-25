#!/bin/bash
# EasyOKAPI Setup Launcher
# Distribute alongside install.sh inside the release tarball.
# The user extracts the tarball and double-clicks this file (or runs it from a
# terminal) to start the installer wizard, mirroring EasyOKAPI_Setup.exe on
# Windows.
#
# GUI priority:
#   1. Python tkinter (setup_ui.py) — works on X11 + Wayland; no zenity bugs
#   2. zenity                       — fallback if tkinter is unavailable
#   3. whiptail                     — terminal TUI fallback
#   4. plain read                   — last resort
#
# Design principle: ALL interactive steps run here as the regular user where
# the display session is valid.  The token is forwarded to install.sh via
# EASYOKAPI_DOWNLOAD_TOKEN so install.sh never needs to open a GUI as root.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OKAPI_ICON="$SCRIPT_DIR/okapi.png"

RESET="\033[0m"
BOLD="\033[1m"
CYAN="\033[36m"
GREEN="\033[32m"
RED="\033[31m"

# ── Display detection (X11 + Wayland) ─────────────────────────────────────────
HAS_DISPLAY=0
{ [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; } && HAS_DISPLAY=1

# ── Check tkinter availability ────────────────────────────────────────────────
HAS_TKINTER=0
if [ "$HAS_DISPLAY" = "1" ] && command -v python3 &>/dev/null; then
    python3 -c "import tkinter" 2>/dev/null && HAS_TKINTER=1
fi

# ── Token prompt ───────────────────────────────────────────────────────────────
EASYOKAPI_DOWNLOAD_TOKEN=""

if [ "$HAS_TKINTER" = "1" ]; then
    # Primary: tkinter GUI — reliable on X11 and Wayland (no zenity render bug)
    EASYOKAPI_DOWNLOAD_TOKEN=$(python3 "$SCRIPT_DIR/setup_ui.py" 2>/dev/null)
    _rc=$?
    if [ $_rc -ne 0 ] || [ -z "$EASYOKAPI_DOWNLOAD_TOKEN" ]; then
        exit 0   # user cancelled
    fi

elif [ "$HAS_DISPLAY" = "1" ] && command -v zenity &>/dev/null; then
    # Fallback: zenity (may have Wayland rendering issues on some distros)
    _wicon=()
    [ -f "$OKAPI_ICON" ] && _wicon=("--window-icon=$OKAPI_ICON")
    zenity --info \
        --title="EasyOKAPI Setup" \
        --width=400 \
        --text="<b>Welcome to the EasyOKAPI Installer</b>\n\nEnter your download token on the next screen." \
        "${_wicon[@]}" 2>/dev/null
    [ $? -ne 0 ] && exit 0
    EASYOKAPI_DOWNLOAD_TOKEN=$(zenity --password \
        --title="EasyOKAPI Setup — Download Token" \
        "${_wicon[@]}" 2>/dev/null)
    if [ $? -ne 0 ] || [ -z "$EASYOKAPI_DOWNLOAD_TOKEN" ]; then
        zenity --error --title="EasyOKAPI Setup" \
            --text="A download token is required.\nInstallation cancelled." \
            "${_wicon[@]}" 2>/dev/null
        exit 1
    fi

elif command -v whiptail &>/dev/null; then
    # Fallback: terminal TUI
    EASYOKAPI_DOWNLOAD_TOKEN=$(whiptail --passwordbox \
        "Enter your EasyOKAPI download token:" 10 60 \
        --title "EasyOKAPI Setup" 3>&1 1>&2 2>&3)
    if [ -z "$EASYOKAPI_DOWNLOAD_TOKEN" ]; then
        echo -e "  ${RED}A download token is required. Installation cancelled.${RESET}"
        exit 1
    fi

else
    # Last resort: plain read
    echo -e "\n  ${BOLD}${CYAN}EasyOKAPI Setup${RESET}"
    read -rsp "  Enter your EasyOKAPI download token: " EASYOKAPI_DOWNLOAD_TOKEN; echo
    if [ -z "$EASYOKAPI_DOWNLOAD_TOKEN" ]; then
        echo -e "  ${RED}A download token is required. Installation cancelled.${RESET}"
        exit 1
    fi
fi

# ── Write a desktop shortcut so the user can re-run setup easily ───────────────
REAL_HOME="${HOME:-$(eval echo ~"$USER")}"
DESKTOP_DIR="$REAL_HOME/Desktop"
if [ -d "$DESKTOP_DIR" ]; then
    cat > "$DESKTOP_DIR/EasyOKAPI_Setup.desktop" << DEOF
[Desktop Entry]
Name=EasyOKAPI Setup
Comment=Install HTBiotec EasyOKAPI biosensor application
Exec=bash "$SCRIPT_DIR/setup.sh"
Icon=$OKAPI_ICON
Terminal=false
Type=Application
Categories=Science;
DEOF
    chmod +x "$DESKTOP_DIR/EasyOKAPI_Setup.desktop"
fi

# ── Temp runner script ─────────────────────────────────────────────────────────
# chmod 600 so only the current user can read the embedded token.
# Deleted automatically when the install session closes.
INSTALL_SH="$SCRIPT_DIR/install.sh"
TMP_RUNNER=$(mktemp /tmp/easyokapi_setup_XXXXXX.sh)
chmod 600 "$TMP_RUNNER"

cat > "$TMP_RUNNER" << EOF
#!/bin/bash
export EASYOKAPI_DOWNLOAD_TOKEN="$EASYOKAPI_DOWNLOAD_TOKEN"
sudo -E bash "$INSTALL_SH"
_status=\$?
unset EASYOKAPI_DOWNLOAD_TOKEN
echo ""
if [ "\$_status" -eq 0 ]; then
    echo -e "  \033[1m\033[32m✔  EasyOKAPI installation complete.\033[0m"
else
    echo -e "  \033[1m\033[31m✗  Installation ended with errors (exit \$_status).\033[0m"
    echo -e "     See /tmp/easyokapi-install.log for details."
fi
echo ""
read -rp "Press Enter to close this window... " _ignored
rm -f "$TMP_RUNNER"
EOF

# ── Find a graphical terminal emulator ────────────────────────────────────────
TERM_BIN=""
if [ "$HAS_DISPLAY" = "1" ]; then
    for _t in gnome-terminal xfce4-terminal konsole tilix lxterminal mate-terminal xterm; do
        if command -v "$_t" &>/dev/null; then
            TERM_BIN="$_t"
            break
        fi
    done
fi

# ── Launch installer in terminal ───────────────────────────────────────────────
if [ -n "$TERM_BIN" ]; then
    echo -e "  ${BOLD}${CYAN}Opening installer in $TERM_BIN…${RESET}"
    case "$TERM_BIN" in
        gnome-terminal)  gnome-terminal --title="EasyOKAPI Installer" -- bash "$TMP_RUNNER" ;;
        xfce4-terminal)  xfce4-terminal --title="EasyOKAPI Installer" -e "bash $TMP_RUNNER" ;;
        konsole)         konsole --hold -e bash "$TMP_RUNNER" ;;
        tilix)           tilix -e "bash $TMP_RUNNER" ;;
        *)               "$TERM_BIN" -e "bash $TMP_RUNNER" ;;
    esac
else
    echo ""
    echo -e "  ${BOLD}${CYAN}No graphical terminal detected — running installer here.${RESET}"
    echo ""
    bash "$TMP_RUNNER"
fi
