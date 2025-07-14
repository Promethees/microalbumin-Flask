#!/bin/bash

# Log all output to a file for debugging
exec > >(tee -a /tmp/uninstall.log) 2>&1
echo "Starting uninstall script at $(date)"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (sudo)."
    osascript -e 'display dialog "This script requires sudo privileges. Please run with sudo." buttons {"OK"} default button "OK" with title "EasySensorKit Uninstall"'
    exit 1
fi

# Get the current user
CURRENT_USER=$(stat -f '%Su' /dev/console)
if [ -z "$CURRENT_USER" ]; then
    echo "❌ Unable to determine current user."
    osascript -e 'display dialog "Unable to determine current user." buttons {"OK"} default button "OK" with title "EasySensorKit Uninstall"'
    exit 1
fi

# Define installation directory
REPO_NAME="microalbumin-Flask"
INSTALL_DIR="/Applications/$REPO_NAME"

# Remove the application directory
if [ -d "$INSTALL_DIR" ]; then
    echo "Removing application directory $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to remove $INSTALL_DIR."
        osascript -e 'display dialog "Failed to remove application directory." buttons {"OK"} default button "OK" with title "EasySensorKit Uninstall"'
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
        osascript -e 'display dialog "Failed to uninstall Python 3.8.10." buttons {"OK"} default button "OK" with title "EasySensorKit Uninstall"'
        exit 1
    fi
fi

# Prompt to remove Homebrew and pyenv
REMOVE_HOMEBREW=$(osascript -e 'Tell application "System Events" to display dialog "Do you want to remove Homebrew and pyenv? This will delete /Users/'$CURRENT_USER'/homebrew and associated data." buttons {"Yes", "No"} default button "No" with title "EasySensorKit Uninstall"' -e 'button returned of result' 2>/dev/null)
if [ "$REMOVE_HOMEBREW" = "Yes" ]; then
    HOMEBREW_PREFIX="/Users/$CURRENT_USER/homebrew"
    if [ -d "$HOMEBREW_PREFIX" ]; then
        echo "Removing Homebrew from $HOMEBREW_PREFIX..."
        rm -rf "$HOMEBREW_PREFIX"
        if [ $? -ne 0 ]; then
            echo "❌ Failed to remove Homebrew."
            osascript -e 'display dialog "Failed to remove Homebrew." buttons {"OK"} default button "OK" with title "EasySensorKit Uninstall"'
            exit 1
        fi
    fi
fi

echo "Uninstallation complete."
osascript -e 'display dialog "Uninstallation complete. EasySensorKit has been removed." buttons {"OK"} default button "OK" with title "EasySensorKit Uninstall"'
exit 0