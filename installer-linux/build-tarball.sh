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

# ── Bundle the okapi mascot (used by setup_ui.py + zenity fallback) ──────────
echo "📎 Bundling installer assets..."
OKAPI_SRC="$PROJECT_ROOT/static/okapi.png"
OKAPI_DST="$SCRIPT_DIR/okapi.png"
if [ -f "$OKAPI_SRC" ]; then
    cp "$OKAPI_SRC" "$OKAPI_DST"
    echo "   ✔  okapi.png copied to $SOURCE_DIR/"
fi

# ── Legal documents ─────────────────────────────────────────────────────────
# The tarball is built from installer-linux/, so the agreement has to be staged
# inside it. install.sh runs unattended, so this is the only place a user can
# read the licence before the app starts. Removed again below to keep the repo
# clean, exactly like okapi.png.
LEGAL_DST="$SCRIPT_DIR/legal"
mkdir -p "$LEGAL_DST"
cp "$PROJECT_ROOT/legal/EULA.txt"   "$LEGAL_DST/"
cp "$PROJECT_ROOT/legal/PRIVACY.md" "$LEGAL_DST/"
cp "$PROJECT_ROOT/LICENSE"          "$LEGAL_DST/"
echo "   ✔  legal/ staged in $SOURCE_DIR/"

# ── Create tarball from installer-linux/ (excluding the build script itself) ──
echo "📦 Creating tarball: $TARBALL_NAME..."
tar -czf "$TARBALL_NAME" \
    --exclude="$SOURCE_DIR/build-tarball.sh" \
    "$SOURCE_DIR/"
echo "   ✔  setup.sh included in tarball"

if [ $? -eq 0 ]; then
    echo "✅ Success! $TARBALL_NAME created in $PROJECT_ROOT"
else
    echo "❌ Error: Failed to create tarball."
    rm -f "$OKAPI_DST"
    rm -rf "$LEGAL_DST"
    exit 1
fi

# Remove the temp copies from the source tree (keep repo clean)
rm -f "$OKAPI_DST"
rm -rf "$LEGAL_DST"

echo "Done."
