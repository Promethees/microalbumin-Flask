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

# Version is substituted by the GitHub Actions build before packaging
VERSION_TAG="__APP_VERSION__"

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

# Auth service base URL (substituted at build time, or set manually)
AUTH_BASE_URL="__AUTH_BASE_URL__"

# Prompt for account email
ACCOUNT_EMAIL=$(osascript -e 'Tell application "System Events" to display dialog "Enter your Easy OKAPI account email:" default answer "" with title "EasyOKAPI Installer"' -e 'text returned of result' 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$ACCOUNT_EMAIL" ]; then
    echo "❌ Email is required. Installation aborted."
    osascript -e 'display dialog "Email is required. Installation aborted." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    exit 1
fi

# Prompt for account password
ACCOUNT_PASSWORD=$(osascript -e 'Tell application "System Events" to display dialog "Enter your Easy OKAPI account password:" default answer "" with title "EasyOKAPI Installer" with hidden answer' -e 'text returned of result' 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$ACCOUNT_PASSWORD" ]; then
    echo "❌ Password is required. Installation aborted."
    osascript -e 'display dialog "Password is required. Installation aborted." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    exit 1
fi

# Authenticate and get download token
echo "Authenticating with Easy OKAPI service..."
LOGIN_RESPONSE=$(curl -s -X POST "$AUTH_BASE_URL/api/account/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$ACCOUNT_EMAIL\", \"password\": \"$ACCOUNT_PASSWORD\"}" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$LOGIN_RESPONSE" ]; then
    echo "❌ Failed to reach the authentication server."
    osascript -e 'display dialog "Could not reach the authentication server. Check your internet connection." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    exit 1
fi

DOWNLOAD_TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('download_token',''))" 2>/dev/null)
if [ -z "$DOWNLOAD_TOKEN" ]; then
    LOGIN_MSG=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message','Login failed.'))" 2>/dev/null)
    echo "❌ Authentication failed: $LOGIN_MSG"
    osascript -e "display dialog \"Login failed: $LOGIN_MSG\" buttons {\"OK\"} default button \"OK\" with title \"EasyOKAPI Installer\""
    exit 1
fi
echo "Authentication successful."

# Define install directory
REPO_NAME="microalbumin-Flask"
INSTALL_DIR="/Applications/$REPO_NAME"

# Check if installation directory is not empty
if [ -d "$INSTALL_DIR" ]; then
    ITEM_COUNT=$(find "$INSTALL_DIR" -maxdepth 1 -type f -o -type d | wc -l)
    if [ "$ITEM_COUNT" -gt 1 ]; then
        echo "An existing installation was found at: $INSTALL_DIR"
        if [ -f "$INSTALL_DIR/VERSION.txt" ]; then
            CURRENT_VERSION=$(cat "$INSTALL_DIR/VERSION.txt")
        else
            CURRENT_VERSION="Unknown"
        fi
        echo "Current version: $CURRENT_VERSION"
        echo "New version: $VERSION_TAG"
        CHOICE=$(osascript -e 'Tell application "System Events" to display dialog "An existing installation was found.\n\nCurrent version: '$CURRENT_VERSION'\nNew version: '$VERSION_TAG'\n\nWould you like to overwrite it?" buttons {"Cancel", "Overwrite"} default button "Cancel" with title "EasyOKAPI Installer"' -e 'button returned of result' 2>/dev/null)
        if [ "$CHOICE" = "Overwrite" ]; then
            echo "Removing existing installation..."
            rm -rf "$INSTALL_DIR"
            if [ $? -ne 0 ]; then
                echo "❌ Error: Failed to remove existing installation."
                osascript -e 'display dialog "Failed to remove existing installation. Check permissions and try again." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
                exit 1
            fi
            echo "Existing installation removed successfully."
        else
            echo "Installation cancelled. Keeping existing installation."
            osascript -e 'display dialog "Installation cancelled. Keeping existing installation." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
            exit 0
        fi
    fi
fi

# Download the application archive
ARCHIVE_TMP="/tmp/easyokapi_app.tar.gz"
echo "Downloading application to $INSTALL_DIR..."
curl -L -o "$ARCHIVE_TMP" "$AUTH_BASE_URL/api/download?token=$DOWNLOAD_TOKEN"
if [ $? -ne 0 ] || [ ! -s "$ARCHIVE_TMP" ]; then
    echo "❌ Error: Failed to download the application."
    osascript -e 'display dialog "Failed to download the application. Please try again." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    exit 1
fi

# Extract archive to install directory
mkdir -p "$INSTALL_DIR"
tar -xzf "$ARCHIVE_TMP" -C "$INSTALL_DIR" --strip-components=1
if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to extract the application."
    osascript -e 'display dialog "Failed to extract the application archive." buttons {"OK"} default button "OK" with title "EasyOKAPI Installer"'
    rm -f "$ARCHIVE_TMP"
    exit 1
fi
rm -f "$ARCHIVE_TMP"
chown -R "$CURRENT_USER:staff" "$INSTALL_DIR"

# Cleanup: the GitHub tarball includes dev-only directories and files; remove them
echo "Cleaning up development files..."
rm -rf "$INSTALL_DIR/.git" "$INSTALL_DIR/.gitignore" 2>/dev/null
rm -f  "$INSTALL_DIR"/*.bat 2>/dev/null
for dir in tests .github mac easyokapi-knowledge images installer-mac installer-win installer-linux; do
    [ -d "$INSTALL_DIR/$dir" ] && rm -rf "$INSTALL_DIR/$dir"
done
rm -f "$INSTALL_DIR/log_hid_data_pyusb.py" \
      "$INSTALL_DIR/requirements-win.txt" \
      "$INSTALL_DIR/generate-tree.sh" \
      "$INSTALL_DIR/BUILD_MAC.md" \
      "$INSTALL_DIR/Rule.md" 2>/dev/null

# Save version information for future checks
echo "$VERSION_TAG" > "$INSTALL_DIR/VERSION.txt"

echo "Application downloaded successfully to $INSTALL_DIR ($VERSION_TAG)."
echo "Preinstall script completed at $(date)"
osascript -e "display dialog \"Installation step 1 complete. Please run install-venv.command to continue.\" buttons {\"OK\"} default button \"OK\" with title \"EasyOKAPI Installer\""
exit 0