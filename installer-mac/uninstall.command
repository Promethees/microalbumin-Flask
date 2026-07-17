#!/bin/bash

# Log all output to a file for debugging
exec > >(tee -a /tmp/uninstall.log) 2>&1
echo "Starting uninstall script at $(date)"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (sudo)."
    osascript -e 'display dialog "This script requires sudo privileges. Please run with sudo." buttons {"OK"} default button "OK" with title "EasyOKAPI Uninstall"'
    exit 1
fi

# Get the current user
CURRENT_USER=$(stat -f '%Su' /dev/console)
if [ -z "$CURRENT_USER" ]; then
    echo "❌ Unable to determine current user."
    osascript -e 'display dialog "Unable to determine current user." buttons {"OK"} default button "OK" with title "EasyOKAPI Uninstall"'
    exit 1
fi

# Define installation directory (layout documented in setup.sh)
APP_NAME="EasyOKAPI"
APP_DIR="/Applications/$APP_NAME"
INSTALL_DIR="$APP_DIR/code"
# Installs before v1.2.19 put the source straight in /Applications/microalbumin-Flask.
LEGACY_DIR="/Applications/microalbumin-Flask"

# This script also ships inside EasyOKAPI.app/Contents/Resources, so when it is
# launched from the installed bundle it lives under the very directory it is about
# to delete. bash reads a script lazily, so removing it mid-run can truncate
# execution — copy to /tmp and re-exec from there first. The copy's $0 is outside
# $APP_DIR, so this fires at most once.
case "$0" in
    "$APP_DIR"/*)
        _SELF_TMP="/tmp/easyokapi-uninstall-$$.command"
        cp "$0" "$_SELF_TMP" && chmod +x "$_SELF_TMP" && exec bash "$_SELF_TMP" "$@"
        ;;
esac

# ── Release this machine's license seat ───────────────────────────────────────
# A license is activated on a limited number of machines, and a seat stays taken
# until it is released. Deleting the software does not free it, so a user who
# uninstalls and moves to a new machine would be refused — the cap is held by a
# machine that no longer exists. Hand the seat back before removing anything.
#
# Python is not usable here (it is part of what we are deleting), so this is a
# plain HTTP call. The stored activation token is the credential and names its own
# seat, so no hardware fingerprint has to be recomputed in shell.
#
# Strictly best-effort: no network, no token, or a server that says no (a revoked
# or banned license may not be released) never blocks the uninstall.
AI_SERVICE_URL="${AI_SERVICE_URL:-https://www.easyokapi.cbbiotec.vn}"

_read_license_token() {  # $1 = directory that may hold activation.json
    [ -f "$1/activation.json" ] || return 1
    local tok
    tok=$(grep -o '"license_token"[[:space:]]*:[[:space:]]*"[^"]*"' "$1/activation.json" \
          | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
    [ -n "$tok" ] && printf '%s' "$tok"
}

_release_license_seat() {
    # The data root is <Documents>/EasyOKAPI unless the user relocated it, in which
    # case a pointer file beside the default location holds the real path (the
    # pointer lives outside the data folder precisely so it survives this).
    local docs="/Users/$CURRENT_USER/Documents"
    local pointer="$docs/.easyokapi_dataroot"
    local data_root="$docs/EasyOKAPI"
    if [ -f "$pointer" ]; then
        local moved
        moved=$(tr -d ' \t\r\n' < "$pointer" 2>/dev/null)
        [ -n "$moved" ] && data_root="$moved"
    fi

    # A frozen install keeps activation.json in the data root; a source install
    # keeps it in the install directory (there, script_dir IS the project root).
    local token=""
    local _d
    for _d in "$data_root" "$INSTALL_DIR" "$LEGACY_DIR"; do
        token=$(_read_license_token "$_d") && [ -n "$token" ] && break
        token=""
    done
    if [ -z "$token" ]; then
        echo "No license token found — nothing to deactivate."
        return 0
    fi

    echo "Deactivating this machine's license..."
    local body
    body=$(curl -fsS -m 15 -X POST \
                -H 'Content-Type: application/json' \
                -d "{\"license_token\":\"$token\"}" \
                "$AI_SERVICE_URL/api/license/release" 2>/dev/null)
    case "$body" in
        *'"status":"success"'*|*'"status": "success"'*)
            echo "✅ License seat released — you can activate EasyOKAPI on another machine."
            ;;
        "")
            echo "⚠️  Could not reach the license server; this machine still holds its seat."
            osascript -e "display dialog \"EasyOKAPI could not reach the license server, so this machine still counts against your license.\n\nSign in at $AI_SERVICE_URL and deactivate this machine from your account to free it.\" buttons {\"OK\"} default button \"OK\" with title \"EasyOKAPI Uninstall\"" 2>/dev/null
            ;;
        *)
            echo "⚠️  License server declined the deactivation: $body"
            ;;
    esac
}

_release_license_seat

# ── Data-archive layout helper ────────────────────────────────────────────────
# Keep the archived data/ tree purely subfolder-based: loose files sitting
# directly in the data root are stashed under data/root/ (the app forbids a real
# 'root' subfolder so there is no collision). The reinstall dissolves it back.
_archive_stash_root() {  # $1 = path to a data/ directory
    [ -d "$1" ] || return 0
    if [ -n "$(find "$1" -maxdepth 1 -type f -print -quit 2>/dev/null)" ]; then
        mkdir -p "$1/root"
        find "$1" -maxdepth 1 -type f -exec mv -f {} "$1/root/" \;
    fi
}

# ── Preserve user data before removing the application directory ──────────────
# Mirrors the Windows/Linux uninstallers: measurement data, calibration curves,
# and reports are copied to a persistent backup so a later reinstall can import
# them from the setup wizard.
# DATA_DIR is the current layout's code/ tree, or a pre-v1.2.19 install still at
# LEGACY_DIR; both are removed below.
DATA_DIR=""
for _d in "$INSTALL_DIR" "$LEGACY_DIR"; do
    [ -d "$_d" ] && { DATA_DIR="$_d"; break; }
done

if [ -n "$DATA_DIR" ]; then
    USER_DATA_DEST="/Users/$CURRENT_USER/EasyOKAPI_data"
    DATA_SAVED=0
    for _dir in data json report; do
        if [ -d "$DATA_DIR/$_dir" ]; then
            mkdir -p "$USER_DATA_DEST"
            cp -r "$DATA_DIR/$_dir" "$USER_DATA_DEST/$_dir"
            DATA_SAVED=1
        fi
    done
    _archive_stash_root "$USER_DATA_DEST/data"
    if [ "$DATA_SAVED" -eq 1 ]; then
        chown -R "$CURRENT_USER:staff" "$USER_DATA_DEST"
        echo "✅ User data (data/, json/, report/) preserved at $USER_DATA_DEST"
        osascript -e "display dialog \"Your measurement data, calibration curves, and reports have been saved to:\n\n$USER_DATA_DEST\n\nReinstall EasyOKAPI later to import them back.\" buttons {\"OK\"} default button \"OK\" with title \"EasyOKAPI Uninstall\"" 2>/dev/null
    fi
fi

# Remove the application directory. $APP_DIR takes the .app and code/ with it;
# $LEGACY_DIR clears a pre-v1.2.19 install. Neither matches /Applications/EasyOKAPI.app
# (the no-source frozen build), which is removed by dragging it to the Trash.
_REMOVED=0
for _dir in "$APP_DIR" "$LEGACY_DIR"; do
    [ -d "$_dir" ] || continue
    echo "Removing application directory $_dir..."
    if ! rm -rf "$_dir"; then
        echo "❌ Failed to remove $_dir."
        osascript -e 'display dialog "Failed to remove application directory." buttons {"OK"} default button "OK" with title "EasyOKAPI Uninstall"'
        exit 1
    fi
    _REMOVED=1
done
[ "$_REMOVED" -eq 0 ] && echo "Application directory $APP_DIR not found."

# Optionally remove Python 3.8.10
if command -v pyenv &>/dev/null && pyenv versions | grep -q "3.8.10"; then
    echo "Removing Python 3.8.10..."
    su - "$CURRENT_USER" -c 'pyenv uninstall -f 3.8.10'
    if [ $? -ne 0 ]; then
        echo "❌ Failed to uninstall Python 3.8.10."
        osascript -e 'display dialog "Failed to uninstall Python 3.8.10." buttons {"OK"} default button "OK" with title "EasyOKAPI Uninstall"'
        exit 1
    fi
fi

# Prompt to remove Homebrew and pyenv
REMOVE_HOMEBREW=$(osascript -e 'Tell application "System Events" to display dialog "Do you want to remove Homebrew and pyenv? This will delete /Users/'$CURRENT_USER'/homebrew and associated data." buttons {"Yes", "No"} default button "No" with title "EasyOKAPI Uninstall"' -e 'button returned of result' 2>/dev/null)
if [ "$REMOVE_HOMEBREW" = "Yes" ]; then
    HOMEBREW_PREFIX="/Users/$CURRENT_USER/homebrew"
    if [ -d "$HOMEBREW_PREFIX" ]; then
        echo "Removing Homebrew from $HOMEBREW_PREFIX..."
        rm -rf "$HOMEBREW_PREFIX"
        if [ $? -ne 0 ]; then
            echo "❌ Failed to remove Homebrew."
            osascript -e 'display dialog "Failed to remove Homebrew." buttons {"OK"} default button "OK" with title "EasyOKAPI Uninstall"'
            exit 1
        fi
    fi
fi

# ── AI Assistant (Ollama) removal guidance ───────────────────────────────────
# ai_settings.json is inside INSTALL_DIR and was already deleted above.
# Offer guidance on removing Ollama itself, which is a separate system install.
if command -v ollama &>/dev/null; then
    REMOVE_OLLAMA=$(osascript -e 'button returned of (display dialog "The AI Assistant (Ollama) is installed as a separate system tool.\n\nDo you want instructions to remove it?" buttons {"No thanks", "Show instructions"} default button "No thanks" with title "EasyOKAPI Uninstall — AI Assistant")' 2>/dev/null || echo "No thanks")
    if [ "$REMOVE_OLLAMA" = "Show instructions" ]; then
        osascript -e 'display dialog "To remove Ollama and its AI models:\n\n1. Open Terminal\n2. Remove downloaded models:\n     ollama list\n     ollama rm <model-name>\n3. Remove Ollama app:\n     sudo rm /usr/local/bin/ollama\n     rm -rf ~/.ollama\n\nFor full instructions: https://ollama.com" buttons {"OK"} default button "OK" with title "Remove Ollama"' 2>/dev/null
    fi
fi

echo "Uninstallation complete."
osascript -e 'display dialog "Uninstallation complete. EasyOKAPI has been removed." buttons {"OK"} default button "OK" with title "EasyOKAPI Uninstall"'
exit 0