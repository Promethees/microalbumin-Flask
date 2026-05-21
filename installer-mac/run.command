#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROGRESS_PIPE="/tmp/easyokapi_progress.pipe"
REPO_NAME="microalbumin-Flask"
INSTALL_DIR="/Applications/$REPO_NAME"

RESET="\033[0m"
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
RED="\033[31m"

# ═══════════════════════════════════════════════════════════════════════════════
# --inner  Runs as root (called via sudo by the outer section below).
#          Performs pyenv/venv setup and launches main.py.
#          The FIFO already exists (created by the outer section, chmod 666).
# ═══════════════════════════════════════════════════════════════════════════════
if [ "$1" = "--inner" ]; then
    exec > >(tee -a /tmp/run.log) 2>&1

    if [ ! -d "$INSTALL_DIR" ]; then
        osascript -e 'display dialog "Installation directory not found. Please install the application first." buttons {"OK"} default button "OK" with title "EasyOKAPI Run"'
        exit 1
    fi

    cd "$INSTALL_DIR"

    # ── pyenv ──────────────────────────────────────────────────────────────────
    eval "$(pyenv init --path)" 2>/dev/null
    eval "$(pyenv init -)"      2>/dev/null

    # ── venv ───────────────────────────────────────────────────────────────────
    if [ ! -d "venv" ]; then
        osascript -e 'display dialog "Virtual environment not found. Please run install-venv.command first." buttons {"OK"} default button "OK" with title "EasyOKAPI Run"'
        exit 1
    fi
    source venv/bin/activate

    # ── preflight ──────────────────────────────────────────────────────────────
    if [ ! -f "main.py" ]; then
        osascript -e 'display dialog "main.py not found." buttons {"OK"} default button "OK" with title "EasyOKAPI Run"'
        exit 1
    fi

    # ── launch ─────────────────────────────────────────────────────────────────
    python3 main.py
    echo "Application exited at $(date)"
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Outer  Runs as the current user.
#        1. Prompts for sudo password (in Terminal).
#        2. Creates IPC pipe and launches the GUI splash window.
#        3. Minimises Terminal so the splash is the only visible thing.
#        4. Elevates to root (--inner) for pyenv/venv/Flask startup.
# ═══════════════════════════════════════════════════════════════════════════════
clear
echo ""
echo -e "  ${BOLD}${CYAN}EasyOKAPI${RESET}  —  launching …"
echo ""

# Prompt for sudo credentials now, while Terminal is still visible.
if ! sudo -v 2>/dev/null; then
    echo -e "\n  ${RED}✗  Authentication failed.${RESET}\n"
    osascript -e 'display dialog "Authentication failed." buttons {"OK"} default button "OK" with title "EasyOKAPI Run"'
    exit 1
fi

# IPC pipe (user-created so the splash process can read it without root).
rm -f "$PROGRESS_PIPE"
mkfifo "$PROGRESS_PIPE"
chmod 666 "$PROGRESS_PIPE"

# GUI splash — launch as the current user.
SPLASH_PID=""
if [ -f "$SCRIPT_DIR/splash.py" ] && command -v python3 >/dev/null 2>&1; then
    python3 "$SCRIPT_DIR/splash.py" &
    SPLASH_PID=$!
    sleep 0.25   # let tkinter initialise before we minimise Terminal
    osascript -e 'tell application "Terminal" to set miniaturized of (every window) to true' 2>/dev/null
fi

# Privileged launch (pyenv → venv → Flask).
sudo bash "$SCRIPT_DIR/run.command" --inner

# ── Cleanup ────────────────────────────────────────────────────────────────────
[ -n "$SPLASH_PID" ] && kill "$SPLASH_PID" 2>/dev/null
rm -f "$PROGRESS_PIPE"
exit 0
