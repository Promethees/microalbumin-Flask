#!/bin/bash

# Change to the script's directory
cd "$(dirname "$0")"

# ── ANSI colours ────────────────────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
RED="\033[31m"

# ── Progress-bar helper ──────────────────────────────────────────────────────
# Usage: progress <percent 0-100> <label>
BAR_WIDTH=40
progress() {
    local pct=$1
    local label=$2
    local filled=$(( pct * BAR_WIDTH / 100 ))
    local empty=$(( BAR_WIDTH - filled ))
    local bar=""
    for (( i=0; i<filled; i++ )); do bar+="█"; done
    for (( i=0; i<empty;  i++ )); do bar+="░"; done
    # \r overwrites the current line so the bar animates in place
    printf "\r  ${CYAN}[${GREEN}${bar}${CYAN}]${RESET} ${BOLD}%3d%%${RESET}  %s" "$pct" "$label"
}

# Fill the bar smoothly from $1% to $2% while displaying $3
fill_to() {
    local from=$1 to=$2 label=$3
    for (( p=from; p<=to; p++ )); do
        progress "$p" "$label"
        sleep 0.015
    done
}

# ── Banner ───────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "  ${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${CYAN}║  ⬡  HTBiotec · EasyOKAPI · Launching …   ║${RESET}"
echo -e "  ${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── Log setup ────────────────────────────────────────────────────────────────
exec > >(tee -a /tmp/run.log) 2>&1

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "\n  ${RED}✗  This script must be run as root (sudo).${RESET}\n"
    osascript -e 'display dialog "This script requires sudo privileges. Please run with sudo." buttons {"OK"} default button "OK" with title "EasyOKAPI Run"'
    exit 1
fi

# Define installation directory
REPO_NAME="microalbumin-Flask"
INSTALL_DIR="/Applications/$REPO_NAME"

# Check if installation directory exists
if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "\n  ${RED}✗  Installation directory $INSTALL_DIR not found.${RESET}\n"
    osascript -e 'display dialog "Installation directory not found. Please install the application first." buttons {"OK"} default button "OK" with title "EasyOKAPI Run"'
    exit 1
fi

# Change to the installation directory
cd "$INSTALL_DIR"

# ── Step 1 : initialise pyenv (0 → 20%) ─────────────────────────────────────
fill_to 0 10 "Initialising pyenv …"
eval "$(pyenv init --path)" 2>/dev/null
eval "$(pyenv init -)"      2>/dev/null
fill_to 10 20 "Initialising pyenv …"

# ── Step 2 : activate virtual environment (20 → 40%) ────────────────────────
fill_to 20 30 "Activating virtual environment …"
if [ ! -d "venv" ]; then
    echo -e "\n\n  ${RED}✗  Virtual environment not found. Please run install-venv.command first.${RESET}\n"
    osascript -e 'display dialog "Virtual environment not found. Please run install-venv.command first." buttons {"OK"} default button "OK" with title "EasyOKAPI Run"'
    exit 1
fi
source venv/bin/activate
fill_to 30 40 "Activating virtual environment …"

# ── Step 3 : preflight check (40 → 50%) ─────────────────────────────────────
fill_to 40 50 "Running preflight checks …"
if [ ! -f "main.py" ]; then
    echo -e "\n\n  ${RED}✗  main.py not found.${RESET}\n"
    osascript -e 'display dialog "main.py not found in '$INSTALL_DIR'." buttons {"OK"} default button "OK" with title "EasyOKAPI Run"'
    exit 1
fi

# ── Set up IPC pipe for progress reporting (50 → 100%) ───────────────────────
PROGRESS_PIPE="/tmp/easyokapi_progress.pipe"
rm -f "$PROGRESS_PIPE"
mkfifo "$PROGRESS_PIPE"

(
    while IFS= read -r line; do
        raw_pct="${line%% *}"
        label="${line#* }"
        pct=$(( raw_pct + 0 )) 2>/dev/null || pct=0
        # Map Python 0-100 → display 50-100
        mapped=$(( 50 + pct * 50 / 100 ))
        [ "$mapped" -gt 100 ] && mapped=100
        progress "$mapped" "$label"
        if [ "$pct" -ge 100 ] 2>/dev/null; then break; fi
    done < "$PROGRESS_PIPE"
    progress 100 "Server ready!         "
    echo ""
    echo ""
    echo -e "  ${GREEN}${BOLD}✔  EasyOKAPI is running — opening browser…${RESET}"
    echo ""
    rm -f "$PROGRESS_PIPE"
) &
READER_PID=$!

# ── Launch application ───────────────────────────────────────────────────────
sudo python3 main.py

# Cleanup
kill "$READER_PID" 2>/dev/null
rm -f "$PROGRESS_PIPE"

echo "Application exited at $(date)"
exit 0