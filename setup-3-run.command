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
echo -e "  ${BOLD}${CYAN}║        EasyOKAPI  ·  Launching …         ║${RESET}"
echo -e "  ${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── Step 1 : initialise pyenv (0 → 20%) ─────────────────────────────────────
fill_to 0 15 "Initialising pyenv …"
eval "$(pyenv init --path)" 2>/dev/null
eval "$(pyenv init -)"      2>/dev/null
fill_to 15 25 "Initialising pyenv …"

# ── Step 2 : activate virtual environment (25 → 50%) ────────────────────────
fill_to 25 40 "Activating virtual environment …"
if [ ! -f "venv/bin/activate" ]; then
    echo -e "\n\n  ${RED}✗  Virtual environment not found. Run setup-2-install-venv.command first.${RESET}\n"
    exit 1
fi
source venv/bin/activate
fill_to 40 55 "Activating virtual environment …"

# ── Step 3 : preflight check (55 → 60%) ─────────────────────────────────────
fill_to 55 60 "Running preflight checks …"
if [ ! -f "main.py" ]; then
    echo -e "\n\n  ${RED}✗  main.py not found.${RESET}\n"
    exit 1
fi

# ── Set up IPC pipe so main.py can report its import progress ────────────────
# main.py writes lines of the form:  "<percent> <label>"
# e.g.  "45 Loading routes …"
# This reader maps Python's 0-100 → display range 60-100.
PROGRESS_PIPE="/tmp/easyokapi_progress.pipe"
rm -f "$PROGRESS_PIPE"
mkfifo "$PROGRESS_PIPE"

(
    while IFS= read -r line; do
        raw_pct="${line%% *}"
        label="${line#* }"
        # Sanitise to integer
        pct=$(( raw_pct + 0 )) 2>/dev/null || pct=0
        # Map Python 0-100 → display 60-100
        mapped=$(( 60 + pct * 40 / 100 ))
        [ "$mapped" -gt 100 ] && mapped=100
        progress "$mapped" "$label"
        if [ "$pct" -ge 100 ] 2>/dev/null; then
            break
        fi
    done < "$PROGRESS_PIPE"
    # Finalise bar
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

# Cleanup if python exits before the pipe reader finishes
kill "$READER_PID" 2>/dev/null
rm -f "$PROGRESS_PIPE"

# ── Keep terminal open ───────────────────────────────────────────────────────
echo ""
read -p "  Press Enter to exit…"