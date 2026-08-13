#!/bin/bash

# Exit on error
set -e

# Change to the script's directory
cd "$(dirname "$0")"

# Check if Homebrew is installed
if ! command -v brew &>/dev/null; then
    echo "❌ Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

brew install xz

# Check if pyenv is installed
if ! command -v pyenv &>/dev/null; then
    echo "❌ pyenv not found. Installing pyenv..."
    brew install pyenv
fi

# Initialize pyenv
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

# Check if Python 3.12.11 is installed
if ! pyenv versions | grep -q "3.12.11"; then
    echo "❌ Python 3.12.11 not found. Installing Python 3.12.11 via pyenv..."
    # Set CFLAGS and LDFLAGS to use system headers
    export CFLAGS="-I$(xcrun --show-sdk-path)/usr/include"
    export LDFLAGS="-L$(xcrun --show-sdk-path)/usr/lib"
    pyenv install 3.12.11
else
    echo "Python 3.12.11 already installed. Proceeding..."
fi
echo "Proceed to setup-2-install-venv.command to proceed"
read -n 1 -s -r -p "Installation process done, press any key to proceed..."
