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
RW_DMG="${APP_NAME}_${VERSION}_rw.dmg"

echo "🚀 Starting DMG build for $APP_NAME ($VERSION)…"

# Ensure we are in the project root
cd "$PROJECT_ROOT" || exit 1

# Cleanup previous builds
echo "🧹 Cleaning up previous build artifacts…"
rm -f "$DMG_NAME" "$RW_DMG"
rm -rf "$TMP_DIR"

# ── Prepare DMG contents ───────────────────────────────────────────────────────
echo "📂 Preparing DMG contents…"
mkdir -p "$TMP_DIR"
cp -R "$SOURCE_DIR/" "$TMP_DIR/"
rm -f "$TMP_DIR/build-dmg.sh"    # strip build script from the DMG

# ── Bundle the okapi mascot so install scripts can use it as a dialog icon ───
cp "$PROJECT_ROOT/static/okapi.png" "$TMP_DIR/okapi.png"

# ── Create a branded DMG background ──────────────────────────────────────────
#    The background sits in a hidden .background/ folder inside the DMG.
#    Finder reads it and renders it behind the icon grid.
#    Size: 620 × 420 px — matches the window bounds set in the AppleScript below.
mkdir -p "$TMP_DIR/.background"

LOGO_SRC="$PROJECT_ROOT/static/ht-logo.jpeg"
OKAPI_SRC="$PROJECT_ROOT/static/okapi.png"
BG_OUT="$TMP_DIR/.background/background.png"
BG_W=620; BG_H=420

echo "🎨 Creating DMG background image…"
if command -v convert &>/dev/null || command -v magick &>/dev/null; then
    CONVERT=$(command -v magick || command -v convert)
    # Warm off-white canvas, faint HTBiotec logo watermark bottom-right,
    # okapi mascot watermark bottom-left.
    "$CONVERT" -size "${BG_W}x${BG_H}" "xc:#FFFEF5" \
        \( "$LOGO_SRC"  -resize 180x180 -alpha set -channel Alpha -evaluate multiply 0.12 +channel \) \
        -gravity SouthEast -geometry +24+18 -composite \
        \( "$OKAPI_SRC" -resize 90x90   -alpha set -channel Alpha -evaluate multiply 0.20 +channel \) \
        -gravity SouthWest -geometry +24+18 -composite \
        "$BG_OUT"
    echo "✅ Background image created with ImageMagick."
elif command -v sips &>/dev/null; then
    # Fallback: a plain soft yellow matching the HTBiotec brand palette
    sips -z "$BG_H" "$BG_W" "$LOGO_SRC" --out "$BG_OUT" 2>/dev/null || \
        python3 -c "
import struct, zlib
def png_chunk(tag, data):
    raw = tag + data
    return struct.pack('>I', len(data)) + raw + struct.pack('>I', zlib.crc32(raw) & 0xffffffff)
w, h = $BG_W, $BG_H
row = bytes([0] + [0xFF, 0xFE, 0xF5] * w)
idat = zlib.compress(row * h)
with open('$BG_OUT', 'wb') as f:
    f.write(b'\x89PNG\r\n\x1a\n')
    f.write(png_chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)))
    f.write(png_chunk(b'IDAT', idat))
    f.write(png_chunk(b'IEND', b''))
"
    echo "⚠️  Background created with sips/Python (install ImageMagick for logo watermark)."
fi

# ── Build EasyOKAPI.app with custom ht icon ───────────────────────────────────
echo "🎨 Building EasyOKAPI.app with custom icon…"

_ICONSET="$(mktemp -d)/ht.iconset"
mkdir -p "$_ICONSET"
_BASE_PNG="$(mktemp).png"

sips -s format png "$PROJECT_ROOT/static/ht.ico" --out "$_BASE_PNG" 2>/dev/null
if [ $? -eq 0 ]; then
    sips -z 16  16  "$_BASE_PNG" --out "$_ICONSET/icon_16x16.png"      2>/dev/null
    sips -z 32  32  "$_BASE_PNG" --out "$_ICONSET/icon_16x16@2x.png"   2>/dev/null
    sips -z 32  32  "$_BASE_PNG" --out "$_ICONSET/icon_32x32.png"      2>/dev/null
    sips -z 64  64  "$_BASE_PNG" --out "$_ICONSET/icon_32x32@2x.png"   2>/dev/null
    sips -z 128 128 "$_BASE_PNG" --out "$_ICONSET/icon_128x128.png"    2>/dev/null
    sips -z 256 256 "$_BASE_PNG" --out "$_ICONSET/icon_128x128@2x.png" 2>/dev/null
    sips -z 256 256 "$_BASE_PNG" --out "$_ICONSET/icon_256x256.png"    2>/dev/null
    sips -z 512 512 "$_BASE_PNG" --out "$_ICONSET/icon_256x256@2x.png" 2>/dev/null
    _ICNS_PATH="$(mktemp).icns"
    iconutil -c icns "$_ICONSET" -o "$_ICNS_PATH"
    rm -rf "$(dirname "$_ICONSET")" "$_BASE_PNG"

    osacompile -o "$TMP_DIR/EasyOKAPI.app" "$SOURCE_DIR/run.scpt"
    if [ $? -eq 0 ]; then
        cp "$_ICNS_PATH" "$TMP_DIR/EasyOKAPI.app/Contents/Resources/applet.icns"
        echo "✅ EasyOKAPI.app built with ht icon."
    else
        echo "⚠️  osacompile failed — EasyOKAPI.app not included."
    fi
    rm -f "$_ICNS_PATH"
else
    echo "⚠️  sips could not convert ht.ico — EasyOKAPI.app not included."
fi

# ── Create writable DMG, brand it, then convert to read-only ─────────────────
echo "🛠️  Creating writable DMG…"
hdiutil create -volname "$APP_NAME" -srcfolder "$TMP_DIR" \
    -ov -format UDRW -size 300m "$RW_DMG"
if [ $? -ne 0 ]; then
    echo "❌ Failed to create writable DMG."
    exit 1
fi

echo "📎 Mounting DMG for branding…"
MOUNT_OUTPUT=$(hdiutil attach -readwrite -noverify -noautoopen "$RW_DMG" 2>&1)
VOLUME="/Volumes/$APP_NAME"

# Wait for Finder to register the volume
sleep 3

echo "🖼️  Applying background and icon layout via Finder…"
# Window bounds {left, top, right, bottom} → 620 × 420 px window
osascript <<APPLESCRIPT
tell application "Finder"
    tell disk "$APP_NAME"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set bounds of container window to {200, 120, 820, 540}
        set icon size of icon view options of container window to 80
        set text size of icon view options of container window to 12
        set arrangement of icon view options of container window to not arranged
        set background picture of icon view options of container window to file ".background:background.png"
        -- EasyOKAPI launcher — prominent on the left
        try
            set position of item "EasyOKAPI.app" to {130, 195}
        end try
        -- Install scripts — right column, top to bottom
        try
            set position of item "install-tools-clone-repo.command" to {390, 80}
        end try
        try
            set position of item "install-venv.command" to {390, 185}
        end try
        try
            set position of item "run.command" to {390, 290}
        end try
        try
            set position of item "uninstall.command" to {390, 380}
        end try
        -- okapi.png is a helper asset for the install scripts; hide it off-canvas
        try
            set position of item "okapi.png" to {-200, -200}
        end try
        close
        open
        update without registering applications
        delay 3
        close
    end tell
end tell
APPLESCRIPT

echo "💾 Detaching DMG…"
hdiutil detach "$VOLUME" -force 2>/dev/null || hdiutil detach "$VOLUME" 2>/dev/null
sleep 2

echo "📦 Converting to compressed read-only DMG: $DMG_NAME…"
hdiutil convert "$RW_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG_NAME"
if [ $? -ne 0 ]; then
    echo "❌ Conversion to UDZO failed."
    rm -f "$RW_DMG"
    exit 1
fi
rm -f "$RW_DMG"

echo "✅ $DMG_NAME created in $PROJECT_ROOT"

# ── Update version badge in README.md ────────────────────────────────────────
echo "📝 Updating version in README.md…"
sed -i '' "s|img.shields.io/github/v/release/Promethees/microalbumin-Flask?label=latest|img.shields.io/badge/latest-${VERSION}-blue|g" "$PROJECT_ROOT/README.md"
sed -i '' "s|img.shields.io/badge/latest-v[0-9.]*[a-z]*-blue|img.shields.io/badge/latest-${VERSION}-blue|g" "$PROJECT_ROOT/README.md"
echo "✅ README.md updated with version $VERSION"

# Cleanup
rm -rf "$TMP_DIR"
echo "Done."
