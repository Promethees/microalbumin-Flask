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
VERSION_TAG="v1.0.3"

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

# Check if installation directory is not empty
if [ -d "$INSTALL_DIR" ]; then
    # Count items in the directory
    ITEM_COUNT=$(find "$INSTALL_DIR" -maxdepth 1 -type f -o -type d | wc -l)
    
    if [ "$ITEM_COUNT" -gt 1 ]; then  # More than 1 because the directory itself counts as 1
        echo "An existing installation was found at: $INSTALL_DIR"
        
        # Check if version file exists to display current version
        if [ -f "$INSTALL_DIR/VERSION.txt" ]; then
            CURRENT_VERSION=$(cat "$INSTALL_DIR/VERSION.txt")
            echo "Current version: $CURRENT_VERSION"
        else
            echo "Current version: Unknown (no version file found)"
            CURRENT_VERSION="Unknown"
        fi
        
        echo "New version: $VERSION_TAG"
        echo ""
        
        # Prompt user using osascript with better formatting
        CHOICE=$(osascript -e 'Tell application "System Events" to display dialog "An existing installation was found.\n\nCurrent version: '$CURRENT_VERSION'\nNew version: '$VERSION_TAG'\n\nWould you like to overwrite it?" buttons {"Cancel", "Overwrite"} default button "Cancel" with title "EasySensorKit Installer"' -e 'button returned of result' 2>/dev/null)
        
        if [ "$CHOICE" = "Overwrite" ]; then
            echo "Removing existing installation..."
            rm -rf "$INSTALL_DIR"
            if [ $? -ne 0 ]; then
                echo "❌ Error: Failed to remove existing installation."
                osascript -e 'display dialog "Failed to remove existing installation. Check permissions and try again." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
                exit 1
            fi
            echo "Existing installation removed successfully."
        else
            echo "Installation cancelled. Keeping existing installation."
            osascript -e 'display dialog "Installation cancelled. Keeping existing installation." buttons {"OK"} default button "OK" with title "EasySensorKit Installer"'
            exit 0
        fi
    fi
fi

# Clone the repository
echo "Cloning repository to $INSTALL_DIR..."
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

# Remove unwanted files and directories (adapted from Windows batch approach)
echo "Cleaning up unwanted files and directories..."

# Remove Git history
rm -rf "$INSTALL_DIR/.git" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Warning: Failed to remove .git history."
fi

# Remove .gitignore
rm -f "$INSTALL_DIR/.gitignore" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Warning: Failed to remove .gitignore."
fi

# Remove Windows-specific installer scripts
rm -f "$INSTALL_DIR"/*.bat 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Warning: Failed to remove .bat files."
fi


# Remove development/build files
[ -d "$INSTALL_DIR/tests" ] && rm -rf "$INSTALL_DIR/tests"
[ -d "$INSTALL_DIR/.github" ] && rm -rf "$INSTALL_DIR/.github"
[ -d "$INSTALL_DIR/mac" ] && rm -rf "$INSTALL_DIR/mac"
[ -d "$INSTALL_DIR/easyokapi-knowledge" ] && rm -rf "$INSTALL_DIR/easyokapi-knowledge"
[ -d "$INSTALL_DIR/images" ] && rm -rf "$INSTALL_DIR/images"
[ -d "$INSTALL_DIR/installer-mac" ] && rm -rf "$INSTALL_DIR/installer-mac"
[ -d "$INSTALL_DIR/installer-win" ] && rm -rf "$INSTALL_DIR/installer-win"

# Remove development/documentation files
rm -f "$INSTALL_DIR/log_hid_data_pyusb.py" 2>/dev/null
rm -f "$INSTALL_DIR/requirements.txt" 2>/dev/null
rm -f "$INSTALL_DIR/requirements-win.txt" 2>/dev/null
rm -f "$INSTALL_DIR/generate-tree.sh" 2>/dev/null
rm -f "$INSTALL_DIR/BUILD_MAC.md" 2>/dev/null
rm -f "$INSTALL_DIR/Rule.md" 2>/dev/null

# Save version information for future checks
echo "$VERSION_TAG" > "$INSTALL_DIR/VERSION.txt"

echo "Repository cloned successfully to $INSTALL_DIR with tag $VERSION_TAG."
echo "Preinstall script completed at $(date)"
osascript -e "display dialog \"Installation step 1 complete. Please run install-venv.command to continue.\" buttons {\"OK\"} default button \"OK\" with title \"EasySensorKit Installer\""
exit 0