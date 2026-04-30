#!/bin/bash

# Configuration
APP_NAME="EasySensorKit"
VERSION="v1.0.1"
DMG_NAME="${APP_NAME}_${VERSION}.dmg"
SOURCE_DIR="installer-mac"
TMP_DIR="tmp_dmg_root"

# Get the script's directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

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

# Create the DMG using hdiutil
echo "🛠️ Creating DMG: $DMG_NAME..."
hdiutil create -volname "$APP_NAME" -srcfolder "$TMP_DIR" -ov -format UDZO "$DMG_NAME"

if [ $? -eq 0 ]; then
    echo "✅ Success! $DMG_NAME created in $PROJECT_ROOT"
    
    # Update version in README.md (Static Badge)
    echo "📝 Updating version in README.md..."
    # Update the badge URL: https://img.shields.io/badge/latest-v1.0.1-blue
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
