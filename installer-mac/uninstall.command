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

# Define installation directory
REPO_NAME="microalbumin-Flask"
INSTALL_DIR="/Applications/$REPO_NAME"

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
if [ -d "$INSTALL_DIR" ]; then
    USER_DATA_DEST="/Users/$CURRENT_USER/EasyOKAPI_data"
    DATA_SAVED=0
    for _dir in data json report; do
        if [ -d "$INSTALL_DIR/$_dir" ]; then
            mkdir -p "$USER_DATA_DEST"
            cp -r "$INSTALL_DIR/$_dir" "$USER_DATA_DEST/$_dir"
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

# Remove the application directory
if [ -d "$INSTALL_DIR" ]; then
    echo "Removing application directory $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to remove $INSTALL_DIR."
        osascript -e 'display dialog "Failed to remove application directory." buttons {"OK"} default button "OK" with title "EasyOKAPI Uninstall"'
        exit 1
    fi
else
    echo "Application directory $INSTALL_DIR not found."
fi

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