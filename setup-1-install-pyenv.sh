#!/bin/bash

# Exit on first error
set -e

# Change to the script's directory (repo root)
cd "$(dirname "$0")"

exec > >(tee -a /tmp/easyokapi-setup1.log) 2>&1
echo "Starting setup step 1 at $(date)"

# ── Root check ────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (sudo ./setup-1-install-pyenv.sh)."
    exit 1
fi

CURRENT_USER="${SUDO_USER:-}"
if [ -z "$CURRENT_USER" ] || [ "$CURRENT_USER" = "root" ]; then
    echo "❌ Unable to determine the invoking user. Run with: sudo ./setup-1-install-pyenv.sh"
    exit 1
fi
CURRENT_HOME=$(eval echo "~$CURRENT_USER")
PYENV_ROOT="$CURRENT_HOME/.pyenv"
PYENV_BIN="$PYENV_ROOT/bin/pyenv"
PYTHON_VERSION="3.8.10"

# ── Step 1: Install system dependencies ───────────────────────────────────────
echo "Installing system dependencies..."
apt-get update -y
apt-get install -y \
    git curl build-essential libssl-dev zlib1g-dev libbz2-dev \
    libreadline-dev libsqlite3-dev libffi-dev liblzma-dev \
    libusb-1.0-0-dev libudev-dev \
    libhidapi-hidraw0 libhidapi-dev
echo "✅ System dependencies installed."

# ── Step 2: Install pyenv ─────────────────────────────────────────────────────
if [ ! -d "$PYENV_ROOT" ]; then
    echo "Installing pyenv for $CURRENT_USER..."
    su - "$CURRENT_USER" -c 'curl -fsSL https://pyenv.run | bash'
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
echo "✅ pyenv ready."

# ── Step 3: Install Python 3.8.10 ─────────────────────────────────────────────
if ! su - "$CURRENT_USER" -c "PYENV_ROOT=$PYENV_ROOT $PYENV_BIN versions 2>/dev/null | grep -qF '$PYTHON_VERSION'"; then
    echo "Installing Python $PYTHON_VERSION via pyenv (this may take a few minutes)..."
    su - "$CURRENT_USER" -c "PYENV_ROOT=\"$PYENV_ROOT\" $PYENV_BIN install $PYTHON_VERSION"
else
    echo "Python $PYTHON_VERSION already installed. Skipping."
fi
echo "✅ Python $PYTHON_VERSION available."

echo ""
echo "✅ Step 1 complete."
echo "   Next: sudo ./setup-2-install-venv.sh"
read -n 1 -s -r -p "   Press any key to exit..."
echo ""
exit 0
