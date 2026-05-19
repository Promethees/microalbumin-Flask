#!/bin/bash

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
RED="\033[31m"

# ── Progress-bar helper ───────────────────────────────────────────────────────
BAR_WIDTH=40
progress() {
    local pct=$1 label=$2
    local filled=$(( pct * BAR_WIDTH / 100 ))
    local empty=$(( BAR_WIDTH - filled ))
    local bar=""
    for (( i=0; i<filled; i++ )); do bar+="█"; done
    for (( i=0; i<empty;  i++ )); do bar+="░"; done
    printf "\r  ${CYAN}[${GREEN}${bar}${CYAN}]${RESET} ${BOLD}%3d%%${RESET}  %s" "$pct" "$label"
}

fill_to() {
    local from=$1 to=$2 label=$3
    for (( p=from; p<=to; p++ )); do
        progress "$p" "$label"
        sleep 0.015
    done
}

# ── Banner ────────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "  ${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${CYAN}║  ⬡  HTBiotec · EasyOKAPI · Launching …   ║${RESET}"
echo -e "  ${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

exec > >(tee -a /tmp/easyokapi-run.log) 2>&1

# ── Root check ────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo -e "\n  ${RED}✗  This script must be run as root (sudo).${RESET}\n"
    exit 1
fi

INSTALL_DIR="/opt/EasyOKAPI"

if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "\n  ${RED}✗  $INSTALL_DIR not found. Please run install.sh first.${RESET}\n"
    exit 1
fi

cd "$INSTALL_DIR"

# ── Step 1: Activate venv (0 → 40%) ──────────────────────────────────────────
fill_to 0 20 "Activating virtual environment …"
if [ ! -d "venv" ]; then
    echo -e "\n\n  ${RED}✗  Virtual environment not found. Please re-run install.sh.${RESET}\n"
    exit 1
fi
source venv/bin/activate
fill_to 20 40 "Activating virtual environment …"

# ── Step 2: Preflight (40 → 50%) ─────────────────────────────────────────────
fill_to 40 50 "Running preflight checks …"
if [ ! -f "main.py" ]; then
    echo -e "\n\n  ${RED}✗  main.py not found in $INSTALL_DIR.${RESET}\n"
    exit 1
fi

# ── Step 3: IPC pipe for startup progress (50 → 100%) ────────────────────────
PROGRESS_PIPE="/tmp/easyokapi_progress.pipe"
rm -f "$PROGRESS_PIPE"
mkfifo "$PROGRESS_PIPE"

(
    while IFS= read -r line; do
        raw_pct="${line%% *}"
        label="${line#* }"
        pct=$(( raw_pct + 0 )) 2>/dev/null || pct=0
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

python3 main.py

kill "$READER_PID" 2>/dev/null
rm -f "$PROGRESS_PIPE"
echo "Application exited at $(date)"
exit 0
