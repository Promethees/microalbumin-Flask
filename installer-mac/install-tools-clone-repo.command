#!/bin/bash

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
RED="\033[31m"
YELLOW="\033[33m"

# ── Helpers ───────────────────────────────────────────────────────────────────
print_step() { echo -e "\n  ${BOLD}${CYAN}▶  $1${RESET}"; }
print_ok()   { echo -e "  ${GREEN}✔  $1${RESET}"; }
print_fail() { echo -e "  ${RED}✗  $1${RESET}"; }
print_warn() { echo -e "  ${YELLOW}⚠  $1${RESET}"; }

# ── Banner ────────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "  ${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${CYAN}║  ⬡  HTBiotec · EasyOKAPI · Step 1/2      ║${RESET}"
echo -e "  ${BOLD}${CYAN}║     Install Tools & Download              ║${RESET}"
echo -e "  ${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# Log all output to a file for debugging
exec > >(tee -a /tmp/install-homebrew-and-clone.log) 2>&1
echo "Starting install-homebrew-and-clone script at $(date)"

# ── Okapi mascot icon (bundled in the DMG alongside this script) ──────────────
# Used as a custom window icon for osascript dialogs on macOS 12+.
OKAPI_ICON="$(dirname "$0")/okapi.png"
_dialog_icon() {
    # Returns AppleScript icon clause: custom PNG when available, else note icon
    if [ -f "$OKAPI_ICON" ]; then
        echo "with icon POSIX file \"$OKAPI_ICON\""
    else
        echo "with icon note"
    fi
}

# ── Root check ────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    print_fail "This script must be run as root (sudo)."
    exit 1
fi

# Get the current user
CURRENT_USER=$(stat -f '%Su' /dev/console)
if [ -z "$CURRENT_USER" ]; then
    print_fail "Unable to determine current user."
    exit 1
fi

# Version is substituted by the GitHub Actions build before packaging
VERSION_TAG="__APP_VERSION__"

# Auth service base URL (substituted at build time)
AUTH_BASE_URL="__AUTH_BASE_URL__"

HOMEBREW_PREFIX="/Users/$CURRENT_USER/homebrew"
REPO_NAME="microalbumin-Flask"
INSTALL_DIR="/Applications/$REPO_NAME"
BACKUP_DIR=""

# ── Step 1 / 4 : Homebrew ─────────────────────────────────────────────────────
print_step "1 / 4  Installing Homebrew"
if ! command -v "$HOMEBREW_PREFIX/bin/brew" &>/dev/null; then
    echo "  Homebrew not found — installing to $HOMEBREW_PREFIX …"
    mkdir -p "$HOMEBREW_PREFIX"
    chmod u+rwx "$HOMEBREW_PREFIX"
    curl -fsSL https://github.com/Homebrew/brew/tarball/master | tar -xzf - -C "$HOMEBREW_PREFIX" --strip-components 1
    if [ $? -ne 0 ]; then
        print_fail "Failed to download and extract Homebrew."
        exit 1
    fi
    chown -R "$CURRENT_USER:staff" "$HOMEBREW_PREFIX"
    chmod -R u+rwx "$HOMEBREW_PREFIX"
    eval "$($HOMEBREW_PREFIX/bin/brew shellenv)"
    su - "$CURRENT_USER" -c "$HOMEBREW_PREFIX/bin/brew update"
    if [ $? -ne 0 ]; then
        print_fail "brew update failed."
        exit 1
    fi
fi
print_ok "Homebrew ready."

# ── Step 2 / 4 : Git & pyenv ──────────────────────────────────────────────────
print_step "2 / 4  Installing Git & pyenv"
if ! command -v git &>/dev/null; then
    echo "  Installing Git via Homebrew…"
    su - "$CURRENT_USER" -c "$HOMEBREW_PREFIX/bin/brew install git"
    if [ $? -ne 0 ]; then print_fail "Failed to install Git."; exit 1; fi
fi
print_ok "Git ready."

if ! command -v pyenv &>/dev/null; then
    echo "  Installing pyenv via Homebrew…"
    su - "$CURRENT_USER" -c "$HOMEBREW_PREFIX/bin/brew install pyenv"
    if [ $? -ne 0 ]; then print_fail "Failed to install pyenv."; exit 1; fi
fi
eval "$(pyenv init --path)"
eval "$(pyenv init -)"
print_ok "pyenv ready."

# ── Step 3 / 4 : Python 3.8.10 ────────────────────────────────────────────────
print_step "3 / 4  Installing Python 3.8.10"
if ! pyenv versions | grep -q "3.8.10"; then
    echo "  Installing Python 3.8.10 via pyenv (this may take a few minutes)…"
    export CFLAGS="-I$(xcrun --show-sdk-path)/usr/include"
    export LDFLAGS="-L$(xcrun --show-sdk-path)/usr/lib"
    su - "$CURRENT_USER" -c 'pyenv install 3.8.10'
    if [ $? -ne 0 ]; then print_fail "Failed to install Python 3.8.10."; exit 1; fi
fi
print_ok "Python 3.8.10 ready."

# ── Step 4 / 4 : Download application ────────────────────────────────────────
print_step "4 / 4  Downloading EasyOKAPI"

DOWNLOAD_TOKEN=$(osascript \
    -e "Tell application \"System Events\" to display dialog \"Enter your Generated EasyOKAPI Token:\" default answer \"\" with title \"EasyOKAPI Installer\" $(_dialog_icon) with hidden answer" \
    -e 'text returned of result' 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$DOWNLOAD_TOKEN" ]; then
    print_fail "EasyOKAPI token is required. Installation aborted."
    osascript -e "display dialog \"EasyOKAPI token is required. Installation aborted.\" buttons {\"OK\"} default button \"OK\" with title \"EasyOKAPI Installer\" $(_dialog_icon)"
    exit 1
fi

# Handle existing installation
if [ -d "$INSTALL_DIR" ]; then
    ITEM_COUNT=$(find "$INSTALL_DIR" -maxdepth 1 -type f -o -type d | wc -l)
    if [ "$ITEM_COUNT" -gt 1 ]; then
        CURRENT_VERSION="Unknown"
        [ -f "$INSTALL_DIR/VERSION.txt" ] && CURRENT_VERSION=$(cat "$INSTALL_DIR/VERSION.txt")
        print_warn "Existing installation found (version $CURRENT_VERSION)."
        CHOICE=$(osascript \
            -e "Tell application \"System Events\" to display dialog \"An existing installation was found.\n\nCurrent: $CURRENT_VERSION\nNew: $VERSION_TAG\n\nOverwrite?\" buttons {\"Cancel\", \"Overwrite\"} default button \"Cancel\" with title \"EasyOKAPI Installer\" $(_dialog_icon)" \
            -e 'button returned of result' 2>/dev/null)
        if [ "$CHOICE" = "Overwrite" ]; then
            echo "  Backing up user data (data/, json/, report/)…"
            BACKUP_DIR="/tmp/easyokapi_userdata_backup_$$"
            mkdir -p "$BACKUP_DIR"
            for _dir in data json report; do
                [ -d "$INSTALL_DIR/$_dir" ] && cp -r "$INSTALL_DIR/$_dir" "$BACKUP_DIR/$_dir"
            done
            echo "  Removing existing installation…"
            rm -rf "$INSTALL_DIR"
            if [ $? -ne 0 ]; then
                print_fail "Failed to remove existing installation."
                osascript -e "display dialog \"Failed to remove existing installation. Check permissions and try again.\" buttons {\"OK\"} default button \"OK\" with title \"EasyOKAPI Installer\" $(_dialog_icon)"
                exit 1
            fi
        else
            echo "  Installation cancelled — keeping existing installation."
            exit 0
        fi
    fi
fi

ARCHIVE_TMP="/tmp/easyokapi_app.tar.gz"
echo "  Downloading application archive…"
curl -L -o "$ARCHIVE_TMP" "$AUTH_BASE_URL/api/download?token=$DOWNLOAD_TOKEN"
if [ $? -ne 0 ] || [ ! -s "$ARCHIVE_TMP" ]; then
    print_fail "Failed to download the application."
    osascript -e "display dialog \"Failed to download the application. Please check your token and network connection.\" buttons {\"OK\"} default button \"OK\" with title \"EasyOKAPI Installer\" $(_dialog_icon)"
    exit 1
fi

echo "  Extracting…"
mkdir -p "$INSTALL_DIR"
tar -xzf "$ARCHIVE_TMP" -C "$INSTALL_DIR" --strip-components=1
if [ $? -ne 0 ]; then
    print_fail "Failed to extract the application archive."
    osascript -e "display dialog \"Failed to extract the application archive.\" buttons {\"OK\"} default button \"OK\" with title \"EasyOKAPI Installer\" $(_dialog_icon)"
    rm -f "$ARCHIVE_TMP"
    exit 1
fi
rm -f "$ARCHIVE_TMP"
chown -R "$CURRENT_USER:staff" "$INSTALL_DIR"

echo "  Cleaning up development files…"
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

echo "$VERSION_TAG" > "$INSTALL_DIR/VERSION.txt"
printf '{\n  "license_token": "%s"\n}\n' "$DOWNLOAD_TOKEN" > "$INSTALL_DIR/activation.json"
chown "$CURRENT_USER:staff" "$INSTALL_DIR/activation.json"

# Restore user data
if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
    echo "  Restoring user data (data/, json/, report/)…"
    for _dir in data json report; do
        if [ -d "$BACKUP_DIR/$_dir" ]; then
            cp -r "$BACKUP_DIR/$_dir" "$INSTALL_DIR/$_dir"
            chown -R "$CURRENT_USER:staff" "$INSTALL_DIR/$_dir"
        fi
    done
    rm -rf "$BACKUP_DIR"
    print_ok "User data restored."
fi

print_ok "Application downloaded to $INSTALL_DIR ($VERSION_TAG)."

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}${GREEN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${GREEN}║  Step 1 complete — run install-venv next ║${RESET}"
echo -e "  ${BOLD}${GREEN}╚══════════════════════════════════════════╝${RESET}"
echo ""
osascript -e "display dialog \"Step 1 complete!\n\nEasyOKAPI has been downloaded.\n\nNext: open install-venv.command to finish setup.\" buttons {\"OK\"} default button \"OK\" with title \"EasyOKAPI Installer\" $(_dialog_icon)"
echo "Preinstall script completed at $(date)"
exit 0