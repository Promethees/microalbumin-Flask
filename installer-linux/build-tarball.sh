#!/bin/bash

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
APP_NAME="EasyOKAPI"
SOURCE_DIR="installer-linux"

if [ -z "${APP_VERSION:-}" ]; then
    echo "❌ APP_VERSION is not set. This script must be run from the GitHub Actions workflow."
    exit 1
fi
VERSION="v${APP_VERSION}"
TARBALL_NAME="${APP_NAME}_linux_${VERSION}.tar.gz"

echo "🚀 Starting Linux tarball build for $APP_NAME ($VERSION)..."

cd "$PROJECT_ROOT" || exit 1

# Cleanup previous build
echo "🧹 Cleaning up previous build artifacts..."
rm -f "$TARBALL_NAME"

# Create tarball from installer-linux/, excluding build script itself
echo "📦 Creating tarball: $TARBALL_NAME..."
tar -czf "$TARBALL_NAME" \
    --exclude="$SOURCE_DIR/build-tarball.sh" \
    "$SOURCE_DIR/"

if [ $? -eq 0 ]; then
    echo "✅ Success! $TARBALL_NAME created in $PROJECT_ROOT"
else
    echo "❌ Error: Failed to create tarball."
    exit 1
fi

echo "Done."
