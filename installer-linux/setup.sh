#!/bin/bash
# EasyOKAPI Setup Launcher
# Distribute alongside install.sh inside the release tarball.
# The user extracts the tarball and double-clicks this file (or runs it from a
# terminal) to start a graphical installer, mirroring EasyOKAPI_Setup.exe on
# Windows.  The script:
#   1. Shows a zenity welcome dialog (GUI systems only).
#   2. Writes a desktop shortcut on ~/Desktop so the user can re-run it easily.
#   3. Launches install.sh in a graphical terminal with DISPLAY/XAUTHORITY
#      forwarded so zenity prompts (including the token dialog) work under sudo.
#   4. Falls back gracefully to the current terminal on headless systems.

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

# ── Welcome dialog ─────────────────────────────────────────────────────────────
if [ "$HAS_DISPLAY" = "1" ] && command -v zenity &>/dev/null; then
    _wicon=()
    [ -f "$OKAPI_ICON" ] && _wicon=("--window-icon=$OKAPI_ICON")
    zenity --info \
        --title="EasyOKAPI Setup" \
        --width=420 \
        --text="<b>Welcome to the EasyOKAPI Installer</b>\n\nA terminal window will open to complete the installation.\n\nYou will be asked for:\n  \xe2\x80\xa2 Your administrator password (sudo)\n  \xe2\x80\xa2 Your EasyOKAPI download token\n\nClick <b>OK</b> to begin." \
        "${_wicon[@]}" 2>/dev/null
    [ $? -ne 0 ] && exit 0   # user closed / cancelled the welcome dialog
fi

# ── Write a desktop shortcut so the user can re-run setup easily ───────────────
REAL_HOME="${HOME:-$(eval echo ~"$USER")}"
DESKTOP_DIR="$REAL_HOME/Desktop"
if [ -d "$DESKTOP_DIR" ]; then
    DESKTOP_FILE="$DESKTOP_DIR/EasyOKAPI_Setup.desktop"
    cat > "$DESKTOP_FILE" << DEOF
[Desktop Entry]
Name=EasyOKAPI Setup
Comment=Install HTBiotec EasyOKAPI biosensor application
Exec=bash "$SCRIPT_DIR/setup.sh"
Icon=$OKAPI_ICON
Terminal=false
Type=Application
Categories=Science;
DEOF
    chmod +x "$DESKTOP_FILE"
fi

# ── Write a temp script that runs install.sh with display forwarded ────────────
# Using a file avoids quoting hell when DISPLAY or paths contain special chars.
DISP="${DISPLAY:-}"
WDISP="${WAYLAND_DISPLAY:-}"
XAUTH="${XAUTHORITY:-}"
INSTALL_SH="$SCRIPT_DIR/install.sh"

TMP_RUNNER=$(mktemp /tmp/easyokapi_setup_XXXXXX.sh)
chmod +x "$TMP_RUNNER"

cat > "$TMP_RUNNER" << EOF
#!/bin/bash
DISPLAY="$DISP" WAYLAND_DISPLAY="$WDISP" XAUTHORITY="$XAUTH" sudo -E bash "$INSTALL_SH"
_status=\$?
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

# ── Launch ─────────────────────────────────────────────────────────────────────
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
    # No graphical terminal available — run directly in the current terminal.
    echo ""
    echo -e "  ${BOLD}${CYAN}No graphical terminal detected — running installer here.${RESET}"
    echo ""
    bash "$TMP_RUNNER"
fi
