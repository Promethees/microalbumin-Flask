#!/bin/bash
#
# Launch EasyOKAPI from a source checkout (pyenv + venv + main.py).
#
# Every argument is forwarded verbatim to main.py, so the app's own flags work
# here: --port, --alias, --verbose, --mem-monitor, --no-browser and
#
#   ./setup-3-run.command --monitor
#       DEVELOPER ONLY. Attaches the live performance monitor at
#       http://<alias>:<port>/__dev/monitor — process, HTTP, device-link and SSE
#       counters. It lives in devtools/, is excluded from the shipped build and
#       is refused in a frozen one, so it can only ever appear on a dev machine.
#       See devtools/README.md.

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

# ── Developer performance monitor (--monitor) ────────────────────────────────
# Purely cosmetic: the flag itself reaches main.py through "$@" like every other
# argument. This only says where the page will be, reading --port/--alias out of
# the same argument list so the URL matches what the app will actually serve.
MONITOR_REQUESTED=0
MONITOR_PORT=5099
MONITOR_ALIAS="easyokapi.com"
_next=""
for arg in "$@"; do
    case "$_next" in
        port)  MONITOR_PORT="$arg";  _next="" ; continue ;;
        alias) MONITOR_ALIAS="$arg"; _next="" ; continue ;;
    esac
    case "$arg" in
        --monitor)   MONITOR_REQUESTED=1 ;;
        --port)      _next="port" ;;
        --alias)     _next="alias" ;;
        --port=*)    MONITOR_PORT="${arg#*=}" ;;
        --alias=*)   MONITOR_ALIAS="${arg#*=}" ;;
    esac
done

if [ "$MONITOR_REQUESTED" -eq 1 ]; then
    echo -e "  ${BOLD}${RED}DEVELOPER MODE${RESET} — performance monitor enabled at"
    echo -e "  ${BOLD}${CYAN}http://${MONITOR_ALIAS}:${MONITOR_PORT}/__dev/monitor${RESET}"
    echo -e "  ${CYAN}Dev tool only — absent from the shipped build. See devtools/README.md.${RESET}"
    echo ""
fi

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

# ── Terminal window title (macOS: Dock icon image is Terminal.app's and
#    cannot be changed from a script; set the title as the closest equivalent)
printf '\033]0;EasyOKAPI\007'
osascript -e 'tell application "Terminal" to set custom title of front window to "EasyOKAPI"' 2>/dev/null || true

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
sudo python3 main.py "$@"

# Cleanup if python exits before the pipe reader finishes
kill "$READER_PID" 2>/dev/null
rm -f "$PROGRESS_PIPE"

# ── Keep terminal open ───────────────────────────────────────────────────────
echo ""
read -p "  Press Enter to exit…"