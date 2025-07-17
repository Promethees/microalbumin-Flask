#!/bin/bash

# Log all output to a file for debugging
exec > >(tee -a /tmp/install-homebrew-and-clone.log) 2>&1
echo "Starting install-homebrew-and-clone script at $(date)"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (sudo)."
    exit 1
fi

# Get the current user
CURRENT_USER=$(stat -f '%Su' /dev/console)
if [ -z "$CURRENT_USER" ]; then
    echo "❌ Unable to determine current user."
    exit 1
fi

# Define version tag
VERSION_TAG="v0.0.1beta"

# Set Homebrew installation directory
HOMEBREW_PREFIX="/Users/$CURRENT_USER/homebrew"

# Check if Homebrew is installed
if ! command -v "$HOMEBREW_PREFIX/bin/brew" &>/dev/null; then
    echo "❌ Homebrew not found. Installing Homebrew in $HOMEBREW_PREFIX..."
    mkdir -p "$HOMEBREW_PREFIX"
    chmod u+rwx "$HOMEBREW_PREFIX"
    curl -fsSL https://github.com/Homebrew/brew/tarball/master | tar -xzf - -C "$HOMEBREW_PREFIX" --strip-components 1
    if [ $? -ne 0 ]; then
        echo "❌ Failed to download and extract Homebrew."
        exit 1
    fi
    chown -R "$CURRENT_USER:staff" "$HOMEBREW_PREFIX"
    chmod -R u+rwx "$HOMEBREW_PREFIX"
    eval "$($HOMEBREW_PREFIX/bin/brew shellenv)"
    su - "$CURRENT_USER" -c "$HOMEBREW_PREFIX/bin/brew update"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to run brew update."
        exit 1
    fi
fi

# Check if Git is installed
if ! command -v git &>/dev/null; then
    echo "❌ Git not found. Installing Git..."
    su - "$CURRENT_USER" -c "$HOMEBREW_PREFIX/bin/brew install git"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install Git."
        exit 1
    fi
fi

# Check if pyenv is installed
if ! command -v pyenv &>/dev/null; then
    echo "❌ pyenv not found. Installing pyenv..."
    su - "$CURRENT_USER" -c "$HOMEBREW_PREFIX/bin/brew install pyenv"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install pyenv."
        exit 1
    fi
fi

# Initialize pyenv
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

# Check if Python 3.8.10 is installed
if ! pyenv versions | grep -q "3.8.10"; then
    echo "❌ Python 3.8.10 not found. Installing Python 3.8.10 via pyenv..."
    export CFLAGS="-I$(xcrun --show-sdk-path)/usr/include"
    export LDFLAGS="-L$(xcrun --show-sdk-path)/usr/lib"
    su - "$CURRENT_USER" -c 'pyenv install 3.8.10'
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install Python 3.8.10."
        exit 1
    fi
fi

# Prompt for GitHub token using osascript
GITHUB_TOKEN=$(osascript -e 'Tell application "System Events" to display dialog "Please enter your GitHub personal access token:" default answer "" with title "EasySensorKit Installer" with hidden answer' -e 'text returned of result' 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ Error: GitHub token is required. User cancelled or provided empty input."
    osascript -e 'display dialog "GitHub token is required. Installation aborted." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

# Define repository details
REPO_URL="https://github.com/Promethees/microalbumin-Flask.git"  # Replace with actual repository URL
REPO_NAME="microalbumin-Flask"
INSTALL_DIR="/Applications/$REPO_NAME"

# Clone the repository
echo "Cloning repository to $INSTALL_DIR..."
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory $INSTALL_DIR already exists. Removing it..."
    rm -rf "$INSTALL_DIR"
fi
su - "$CURRENT_USER" -c "git clone \"https://$GITHUB_TOKEN@github.com/Promethees/microalbumin-Flask.git\" \"$INSTALL_DIR\""
if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to clone repository."
    osascript -e 'display dialog "Failed to clone repository. Check your GitHub token and network connection." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

# Checkout specific tag
echo "Checking out tag $VERSION_TAG..."
cd "$INSTALL_DIR"
su - "$CURRENT_USER" -c "git checkout tags/$VERSION_TAG"
if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to checkout tag $VERSION_TAG."
    osascript -e "display dialog \"Failed to checkout tag $VERSION_TAG. Check if the tag exists.\" buttons {\"OK\"} default button \"OK\" with title \"EasySensorKit Installer\""
    exit 1
fi

# Remove Git history
echo "Removing Git history..."
rm -rf "$INSTALL_DIR/.git"
if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to remove Git history."
    osascript -e 'display dialog "Failed to remove Git history." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
    exit 1
fi

echo "Repository cloned successfully to $INSTALL_DIR with tag $VERSION_TAG."
echo "Preinstall script completed at $(date)"
osascript -e "display dialog \"Installation step 1 complete. Please run install-venv.command to continue.\" buttons {\"OK\"} default button \"OK\" with title \"EasySensorKit Installer\""
exit 0