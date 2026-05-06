#!/bin/bash

# Change to the script's directory (repo root)
cd "$(dirname "$0")"

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
echo -e "  ${BOLD}${CYAN}║        EasyOKAPI  ·  Launching …         ║${RESET}"
echo -e "  ${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

exec > >(tee -a /tmp/easyokapi-run.log) 2>&1

# ── Root check ────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo -e "\n  ${RED}✗  This script must be run as root (sudo ./setup-3-run.sh).${RESET}\n"
    exit 1
fi

# ── Step 1: Activate venv (0 → 40%) ──────────────────────────────────────────
fill_to 0 20 "Activating virtual environment …"
if [ ! -f "venv/bin/activate" ]; then
    echo -e "\n\n  ${RED}✗  Virtual environment not found. Run setup-2-install-venv.sh first.${RESET}\n"
    exit 1
fi
source venv/bin/activate

# ── Terminal icon via _NET_WM_ICON (X11, best-effort) ────────────────────────
# Requires: $WINDOWID set by terminal emulator, xprop installed, PIL in venv
if [ -n "$WINDOWID" ] && command -v xprop &>/dev/null; then
    python3 - "$WINDOWID" "$(pwd)/static/ht.ico" 2>/dev/null <<'PYEOF'
import sys, subprocess
try:
    from PIL import Image
    wid, ico = sys.argv[1], sys.argv[2]
    img = Image.open(ico).convert("RGBA")
    def argb_data(sz):
        r = img.resize((sz, sz))
        return [sz, sz] + [(a<<24)|(rv<<16)|(g<<8)|b for rv,g,b,a in r.getdata()]
    data = argb_data(48) + argb_data(32) + argb_data(16)
    subprocess.run(["xprop", "-id", wid, "-format", "_NET_WM_ICON", "32c",
                    "-set", "_NET_WM_ICON", ",".join(map(str, data))],
                   capture_output=True)
except Exception:
    pass
PYEOF
fi

fill_to 20 40 "Activating virtual environment …"

# ── Step 2: Preflight (40 → 50%) ─────────────────────────────────────────────
fill_to 40 50 "Running preflight checks …"
if [ ! -f "main.py" ]; then
    echo -e "\n\n  ${RED}✗  main.py not found. Make sure you are in the repo root.${RESET}\n"
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

# ── Launch application ────────────────────────────────────────────────────────
python3 main.py "$@"

kill "$READER_PID" 2>/dev/null
rm -f "$PROGRESS_PIPE"

echo ""
read -p "  Press Enter to exit…"
exit 0
