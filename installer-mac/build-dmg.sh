#!/bin/bash

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
APP_NAME="EasyOKAPI"
SOURCE_DIR="installer-mac"
TMP_DIR="tmp_dmg_root"

if [ -z "${APP_VERSION:-}" ]; then
    echo "❌ APP_VERSION is not set. This script must be run from the GitHub Actions workflow."
    exit 1
fi
VERSION="v${APP_VERSION}"
DMG_NAME="${APP_NAME}_${VERSION}.dmg"

echo "🚀 Starting DMG build for $APP_NAME ($VERSION)..."

# Ensure we are in the project root
cd "$PROJECT_ROOT" || exit 1

# Cleanup previous builds
echo "🧹 Cleaning up previous build artifacts..."
rm -f "$DMG_NAME"
rm -rf "$TMP_DIR"

# Create a temporary directory for the DMG contents
mkdir -p "$TMP_DIR"

# Copy the contents of installer-mac to the temporary directory
echo "📂 Preparing DMG contents..."
cp -R "$SOURCE_DIR/" "$TMP_DIR/"

# Remove the build script itself from the DMG
rm -f "$TMP_DIR/build-dmg.sh"

# ── Build EasyOKAPI.app with custom ht icon ───────────────────────────────────
echo "🎨 Building EasyOKAPI.app with custom icon..."

# 1. Convert ht.ico → ht.icns via a temporary iconset
_ICONSET="$(mktemp -d)/ht.iconset"
mkdir -p "$_ICONSET"
_BASE_PNG="$(mktemp).png"

# sips extracts the best frame from the .ico
sips -s format png "$PROJECT_ROOT/static/ht.ico" --out "$_BASE_PNG" 2>/dev/null
if [ $? -eq 0 ]; then
    sips -z 16  16  "$_BASE_PNG" --out "$_ICONSET/icon_16x16.png"     2>/dev/null
    sips -z 32  32  "$_BASE_PNG" --out "$_ICONSET/icon_16x16@2x.png"  2>/dev/null
    sips -z 32  32  "$_BASE_PNG" --out "$_ICONSET/icon_32x32.png"     2>/dev/null
    sips -z 64  64  "$_BASE_PNG" --out "$_ICONSET/icon_32x32@2x.png"  2>/dev/null
    sips -z 128 128 "$_BASE_PNG" --out "$_ICONSET/icon_128x128.png"   2>/dev/null
    sips -z 256 256 "$_BASE_PNG" --out "$_ICONSET/icon_128x128@2x.png" 2>/dev/null
    sips -z 256 256 "$_BASE_PNG" --out "$_ICONSET/icon_256x256.png"   2>/dev/null
    sips -z 512 512 "$_BASE_PNG" --out "$_ICONSET/icon_256x256@2x.png" 2>/dev/null
    _ICNS_PATH="$(mktemp).icns"
    iconutil -c icns "$_ICONSET" -o "$_ICNS_PATH"
    rm -rf "$(dirname "$_ICONSET")" "$_BASE_PNG"

    # 2. Compile run.scpt → EasyOKAPI.app
    osacompile -o "$TMP_DIR/EasyOKAPI.app" "$SOURCE_DIR/run.scpt"
    if [ $? -eq 0 ]; then
        # 3. Inject the ht icon into the app bundle
        cp "$_ICNS_PATH" "$TMP_DIR/EasyOKAPI.app/Contents/Resources/applet.icns"
        echo "✅ EasyOKAPI.app built with ht icon"
    else
        echo "⚠️  osacompile failed — EasyOKAPI.app not included"
    fi
    rm -f "$_ICNS_PATH"
else
    echo "⚠️  sips could not convert ht.ico — EasyOKAPI.app not included"
fi

# Create the DMG using hdiutil
echo "🛠️ Creating DMG: $DMG_NAME..."
hdiutil create -volname "$APP_NAME" -srcfolder "$TMP_DIR" -ov -format UDZO "$DMG_NAME"

if [ $? -eq 0 ]; then
    echo "✅ Success! $DMG_NAME created in $PROJECT_ROOT"
    
    # Update version in README.md (Static Badge)
    echo "📝 Updating version in README.md..."
    # Update the badge URL: https://img.shields.io/badge/latest-v1.0.8-blue
    # This regex looks for the dynamic github release badge OR the static one and replaces it.
    sed -i '' "s|img.shields.io/github/v/release/Promethees/microalbumin-Flask?label=latest|img.shields.io/badge/latest-${VERSION}-blue|g" "$PROJECT_ROOT/README.md"
    sed -i '' "s|img.shields.io/badge/latest-v[0-9.]*beta-blue|img.shields.io/badge/latest-${VERSION}-blue|g" "$PROJECT_ROOT/README.md"
    
    echo "✅ README.md updated with version $VERSION"
else
    echo "❌ Error: Failed to create DMG."
    exit 1
fi

# Cleanup
rm -rf "$TMP_DIR"

echo "Done."
