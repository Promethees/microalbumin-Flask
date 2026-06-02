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

# ── Banner ────────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "  ${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${CYAN}║  ⬡  HTBiotec · EasyOKAPI · Step 1/2      ║${RESET}"
echo -e "  ${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# Log all output to a file for debugging
exec > >(tee -a /tmp/easyokapi-step1.log) 2>&1
echo "Starting EasyOKAPI install step 1 at $(date)"

# ── Terminal prompt helpers ───────────────────────────────────────────────────
# Runs as root — zenity is never used here (see install.sh for rationale).
prompt_input() {
    local title="$1" msg="$2" secret="${3:-false}"
    PROMPT_RESULT=""
    if command -v whiptail &>/dev/null; then
        if [ "$secret" = "true" ]; then
            PROMPT_RESULT=$(whiptail --passwordbox "$msg" 10 60 --title "$title" 3>&1 1>&2 2>&3)
        else
            PROMPT_RESULT=$(whiptail --inputbox "$msg" 10 60 --title "$title" 3>&1 1>&2 2>&3)
        fi
    else
        if [ "$secret" = "true" ]; then
            read -rsp "$msg: " PROMPT_RESULT; echo
        else
            read -rp "$msg: " PROMPT_RESULT
        fi
    fi
}

prompt_confirm() {
    local title="$1" msg="$2"
    if command -v whiptail &>/dev/null; then
        whiptail --yesno "$msg" 10 60 --title "$title" 3>&1 1>&2 2>&3
        return $?
    else
        read -rp "$msg [y/N]: " _ans
        [[ "$_ans" =~ ^[Yy]$ ]]
        return $?
    fi
}

# ── Root check ────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    print_fail "This script must be run as root (sudo)."
    exit 1
fi

# ── Determine the real user (the one who ran sudo) ────────────────────────────
CURRENT_USER="${SUDO_USER:-}"
if [ -z "$CURRENT_USER" ] || [ "$CURRENT_USER" = "root" ]; then
    print_fail "Unable to determine the invoking user. Run with: sudo ./install-1-deps-clone.sh"
    exit 1
fi
CURRENT_HOME=$(eval echo "~$CURRENT_USER")

# ── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_TAG="__APP_VERSION__"
AUTH_BASE_URL="__AUTH_BASE_URL__"
INSTALL_DIR="/opt/EasyOKAPI"
PYENV_ROOT="$CURRENT_HOME/.pyenv"
PYTHON_VERSION="3.8.10"
OKAPI_ICON="$SCRIPT_DIR/okapi.png"

# ── Step 1: Install system dependencies ───────────────────────────────────────
print_step "1 / 3  Installing system dependencies"
apt-get update -y
apt-get install -y \
    git curl build-essential libssl-dev zlib1g-dev libbz2-dev \
    libreadline-dev libsqlite3-dev libffi-dev liblzma-dev \
    libusb-1.0-0-dev libudev-dev \
    libhidapi-hidraw0 libhidapi-dev \
    zenity whiptail
if [ $? -ne 0 ]; then
    print_fail "Failed to install system dependencies."
    exit 1
fi
print_ok "System dependencies installed."

# ── Step 2: Install pyenv for the real user ────────────────────────────────────
print_step "2 / 3  Installing pyenv & Python $PYTHON_VERSION"
PYENV_BIN="$PYENV_ROOT/bin/pyenv"
if [ ! -d "$PYENV_ROOT" ]; then
    echo "  Installing pyenv for $CURRENT_USER…"
    su - "$CURRENT_USER" -c 'curl -fsSL https://pyenv.run | bash'
    if [ $? -ne 0 ]; then
        print_fail "Failed to install pyenv."
        exit 1
    fi
fi

# Add pyenv to the user's .bashrc if not already present
SHELL_RC="$CURRENT_HOME/.bashrc"
if ! grep -q 'pyenv init' "$SHELL_RC" 2>/dev/null; then
    {
        echo ''
        echo '# pyenv'
        echo "export PYENV_ROOT=\"\$HOME/.pyenv\""
        echo 'export PATH="$PYENV_ROOT/bin:$PATH"'
        echo 'eval "$(pyenv init --path)"'
        echo 'eval "$(pyenv init -)"'
    } >> "$SHELL_RC"
    chown "$CURRENT_USER:$CURRENT_USER" "$SHELL_RC"
fi
print_ok "pyenv ready."

# ── Step 3: Install Python 3.8.10 via pyenv ───────────────────────────────────
if ! su - "$CURRENT_USER" -c "PYENV_ROOT=$PYENV_ROOT $PYENV_BIN versions 2>/dev/null | grep -qF '$PYTHON_VERSION'"; then
    echo "  Installing Python $PYTHON_VERSION via pyenv (this may take a few minutes)…"
    su - "$CURRENT_USER" -c "PYENV_ROOT=$PYENV_ROOT $PYENV_BIN install $PYTHON_VERSION"
    if [ $? -ne 0 ]; then
        print_fail "Failed to install Python $PYTHON_VERSION."
        exit 1
    fi
fi
print_ok "Python $PYTHON_VERSION available."

# ── Step 4: Prompt for EasyOKAPI download token ───────────────────────────────
print_step "3 / 3  Downloading EasyOKAPI"
if [ -n "${EASYOKAPI_DOWNLOAD_TOKEN:-}" ]; then
    DOWNLOAD_TOKEN="$EASYOKAPI_DOWNLOAD_TOKEN"
    unset EASYOKAPI_DOWNLOAD_TOKEN
    print_ok "Download token received from setup launcher."
else
    prompt_input "EasyOKAPI Installer" "Enter your Generated EasyOKAPI Token:" "true"
    DOWNLOAD_TOKEN="$PROMPT_RESULT"
fi
if [ -z "$DOWNLOAD_TOKEN" ]; then
    print_fail "EasyOKAPI token is required. Installation aborted."
    exit 1
fi

# ── Step 5: Handle existing installation ──────────────────────────────────────
if [ -d "$INSTALL_DIR" ] && [ "$(find "$INSTALL_DIR" -maxdepth 1 | wc -l)" -gt 1 ]; then
    CURRENT_VERSION="Unknown"
    [ -f "$INSTALL_DIR/VERSION.txt" ] && CURRENT_VERSION=$(cat "$INSTALL_DIR/VERSION.txt")
    echo "Existing installation found: $CURRENT_VERSION → $VERSION_TAG"
    if prompt_confirm "EasyOKAPI Installer" "Existing installation found.\n\nCurrent: $CURRENT_VERSION\nNew: $VERSION_TAG\n\nOverwrite?"; then
        echo "Removing existing installation..."
        rm -rf "$INSTALL_DIR"
    else
        echo "Installation cancelled."
        exit 0
    fi
fi

# ── Step 6: Download the application ──────────────────────────────────────────
ARCHIVE_TMP="/tmp/easyokapi_app.tar.gz"
echo "Downloading application to $INSTALL_DIR..."
curl -L -o "$ARCHIVE_TMP" "$AUTH_BASE_URL/api/download?token=$DOWNLOAD_TOKEN&version=$VERSION_TAG"
if [ $? -ne 0 ] || [ ! -s "$ARCHIVE_TMP" ]; then
    echo "❌ Failed to download the application. Please try again."
    exit 1
fi

mkdir -p "$INSTALL_DIR"
tar -xzf "$ARCHIVE_TMP" -C "$INSTALL_DIR" --strip-components=1
if [ $? -ne 0 ]; then
    echo "❌ Failed to extract the application archive."
    rm -f "$ARCHIVE_TMP"
    exit 1
fi
rm -f "$ARCHIVE_TMP"

# ── Step 7: Clean up dev-only files ───────────────────────────────────────────
echo "Cleaning up development files..."
rm -rf "$INSTALL_DIR/.git" "$INSTALL_DIR/.gitignore"
rm -rf "$INSTALL_DIR/tests" "$INSTALL_DIR/.github"
rm -rf "$INSTALL_DIR/installer-mac" "$INSTALL_DIR/installer-win" "$INSTALL_DIR/installer-linux"
rm -rf "$INSTALL_DIR/easyokapi-knowledge" "$INSTALL_DIR/images"
rm -f  "$INSTALL_DIR/log_hid_data_pyusb.py" "$INSTALL_DIR/requirements-win.txt"
rm -f  "$INSTALL_DIR/generate-tree.sh" "$INSTALL_DIR/BUILD_MAC.md" "$INSTALL_DIR/Rule.md"
rm -f  "$INSTALL_DIR"/*.bat
echo "$VERSION_TAG" > "$INSTALL_DIR/VERSION.txt"

# Write activation.json. The download token doubles as the license token, but it
# is only valid for 30 minutes — persisting it raw means the AI proxy and in-app
# updates break (/api/download -> 401) once it expires. Exchange it now, while it
# is still fresh, for a permanent activation token (no expiry). Fall back to the
# raw token if the exchange fails; the app retries the exchange on startup.
LICENSE_TOKEN="$DOWNLOAD_TOKEN"
if _resp=$(curl -fsS -X POST "$AUTH_BASE_URL/api/activate" \
        -H "Content-Type: application/json" \
        -d "{\"token\": \"$DOWNLOAD_TOKEN\"}" 2>/dev/null); then
    _perm=$(printf '%s' "$_resp" | sed -n 's/.*"license_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    if [ -n "$_perm" ]; then LICENSE_TOKEN="$_perm"; fi
fi
printf '{\n  "license_token": "%s"\n}\n' "$LICENSE_TOKEN" > "$INSTALL_DIR/activation.json"

# Fix ownership so the user can write to the app dir
chown -R "$CURRENT_USER:$CURRENT_USER" "$INSTALL_DIR"

echo ""
echo -e "  ${BOLD}${GREEN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${GREEN}║  Step 1 complete — run install-2-venv    ║${RESET}"
echo -e "  ${BOLD}${GREEN}╚══════════════════════════════════════════╝${RESET}"
echo ""
print_ok "EasyOKAPI $VERSION_TAG downloaded to $INSTALL_DIR."
echo -e "     Next: ${BOLD}sudo ./install-2-venv.sh${RESET}"
echo ""
echo "Step 1 completed at $(date)"
exit 0
