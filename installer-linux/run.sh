#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROGRESS_PIPE="/tmp/easyokapi_progress.pipe"
INSTALL_DIR="/opt/EasyOKAPI"

RESET="\033[0m"
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
RED="\033[31m"

# ═══════════════════════════════════════════════════════════════════════════════
# --inner  Runs as root (called via sudo by the outer section below).
#          Performs venv setup and launches main.py.
#          The FIFO already exists (created by the outer section, chmod 666).
# ═══════════════════════════════════════════════════════════════════════════════
if [ "$1" = "--inner" ]; then
    exec > >(tee -a /tmp/easyokapi-run.log) 2>&1

    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "\n  ${RED}✗  $INSTALL_DIR not found. Please run install.sh first.${RESET}\n"
        exit 1
    fi

    cd "$INSTALL_DIR"

    # ── venv ───────────────────────────────────────────────────────────────────
    if [ ! -d "venv" ]; then
        echo -e "\n  ${RED}✗  Virtual environment not found. Please re-run install.sh.${RESET}\n"
        exit 1
    fi
    source venv/bin/activate

    # ── preflight ──────────────────────────────────────────────────────────────
    if [ ! -f "main.py" ]; then
        echo -e "\n  ${RED}✗  main.py not found in $INSTALL_DIR.${RESET}\n"
        exit 1
    fi

    # ── launch ─────────────────────────────────────────────────────────────────
    python3 main.py
    echo "Application exited at $(date)"
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Outer  Runs as the current user.
#        Tries to show a GUI splash window when a display is available;
#        falls back to a plain terminal banner on headless systems.
#        Then elevates to root (--inner) for venv/Flask startup.
# ═══════════════════════════════════════════════════════════════════════════════
clear
echo ""
echo -e "  ${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${CYAN}║  ⬡  HTBiotec · EasyOKAPI · Launching …   ║${RESET}"
echo -e "  ${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# IPC pipe (user-created so the splash process can read it without root).
rm -f "$PROGRESS_PIPE"
mkfifo "$PROGRESS_PIPE"
chmod 666 "$PROGRESS_PIPE"

# GUI splash — only when a graphical display is available.
SPLASH_PID=""
USE_GUI=0

if [ -n "$DISPLAY" ] && [ -f "$SCRIPT_DIR/splash.py" ] && command -v python3 >/dev/null 2>&1; then
    # Quick check: does the python3 here have tkinter?
    if python3 -c "import tkinter" 2>/dev/null; then
        USE_GUI=1
    fi
fi

if [ "$USE_GUI" = "1" ]; then
    python3 "$SCRIPT_DIR/splash.py" &
    SPLASH_PID=$!
else
    # ── Headless fallback: ANSI progress bar driven by FIFO ───────────────────
    BAR_WIDTH=40
    (
        while IFS= read -r line; do
            raw_pct="${line%% *}"
            label="${line#* }"
            pct=$(( raw_pct + 0 )) 2>/dev/null || pct=0
            mapped=$(( 50 + pct * 50 / 100 ))
            [ "$mapped" -gt 100 ] && mapped=100
            filled=$(( mapped * BAR_WIDTH / 100 ))
            empty=$(( BAR_WIDTH - filled ))
            bar=""
            for (( i=0; i<filled; i++ )); do bar+="█"; done
            for (( i=0; i<empty;  i++ )); do bar+="░"; done
            printf "\r  ${CYAN}[${GREEN}%s${CYAN}]${RESET} ${BOLD}%3d%%${RESET}  %s" \
                   "$bar" "$mapped" "$label"
            if [ "$pct" -ge 100 ] 2>/dev/null; then break; fi
        done < "$PROGRESS_PIPE"
        printf "\r  ${CYAN}[${GREEN}%s${CYAN}]${RESET} ${BOLD}100%%${RESET}  Server ready!                    \n\n" \
               "$(printf '█%.0s' $(seq 1 $BAR_WIDTH))"
        echo -e "  ${GREEN}${BOLD}✔  EasyOKAPI is running — opening browser…${RESET}\n"
        rm -f "$PROGRESS_PIPE"
    ) &
    TEXT_PID=$!
fi

# Privileged launch (venv → Flask).
sudo bash "$SCRIPT_DIR/run.sh" --inner

# ── Cleanup ────────────────────────────────────────────────────────────────────
[ -n "$SPLASH_PID" ] && kill "$SPLASH_PID" 2>/dev/null
[ -n "$TEXT_PID"   ] && kill "$TEXT_PID"   2>/dev/null
rm -f "$PROGRESS_PIPE"
exit 0
