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

cd "$PROJECT_ROOT" || exit 1

# ── Cleanup ───────────────────────────────────────────────────────────────────
echo "🧹 Cleaning up previous build artefacts…"
rm -f "$DMG_NAME" "$RW_DMG"
rm -rf "$TMP_DIR"

# ── Prepare DMG root ──────────────────────────────────────────────────────────
echo "📂 Preparing DMG root…"
mkdir -p "$TMP_DIR"

# Copy only the files that belong in the DMG root:
#   • uninstall.command — advanced users who need to remove the app
#   • okapi.png         — dialog icon used by uninstall.command (hidden off-canvas)
# Everything else (setup.sh, launch.sh, splash.py) lives inside the app bundle.
cp "$SOURCE_DIR/uninstall.command" "$TMP_DIR/"
cp "$PROJECT_ROOT/static/okapi.png" "$TMP_DIR/okapi.png"

# ── DMG background (drag-to-install style: 800 × 430 px) ─────────────────────
mkdir -p "$TMP_DIR/.background"
LOGO_SRC="$PROJECT_ROOT/static/ht-logo.jpeg"
OKAPI_SRC="$PROJECT_ROOT/static/okapi.png"
BG_OUT="$TMP_DIR/.background/background.png"
BG_W=800; BG_H=430

echo "🎨 Creating DMG background image…"
if command -v convert &>/dev/null || command -v magick &>/dev/null; then
    CONVERT=$(command -v magick || command -v convert)
    # Warm off-white canvas, subtle arrow in the centre, faint brand watermarks.
    "$CONVERT" -size "${BG_W}x${BG_H}" "xc:#FFFEF5" \
        \( "$LOGO_SRC"  -resize 160x160 -alpha set -channel Alpha -evaluate multiply 0.10 +channel \) \
        -gravity SouthEast -geometry +20+16 -composite \
        \( "$OKAPI_SRC" -resize 80x80   -alpha set -channel Alpha -evaluate multiply 0.16 +channel \) \
        -gravity SouthWest -geometry +20+16 -composite \
        -stroke "#89B4FA" -strokewidth 2.5 -fill none \
        -draw "line 330,215 455,215" \
        -fill "#89B4FA" -stroke "#89B4FA" -strokewidth 1 \
        -draw "polygon 450,207 468,215 450,223" \
        -font "Helvetica" -pointsize 12 -fill "#6C7086" \
        -gravity Center -annotate +0+80 "Drag EasyOKAPI to Applications to install" \
        "$BG_OUT"
    echo "✅ Background image created with ImageMagick."
elif command -v sips &>/dev/null; then
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
    echo "⚠️  Plain background (install ImageMagick for arrow + watermarks)."
fi

# ── Build EasyOKAPI.app ────────────────────────────────────────────────────────
echo "🎨 Building EasyOKAPI.app…"

_ICONSET="$(mktemp -d)/ht.iconset"
mkdir -p "$_ICONSET"
_BASE_PNG="$(mktemp).png"

sips -s format png "$PROJECT_ROOT/static/ht.ico" --out "$_BASE_PNG" 2>/dev/null
if [ $? -eq 0 ]; then
    for sz in 16 32 128 256 512; do
        sips -z $sz $sz "$_BASE_PNG" --out "$_ICONSET/icon_${sz}x${sz}.png"      2>/dev/null
    done
    sips -z 32  32  "$_BASE_PNG" --out "$_ICONSET/icon_16x16@2x.png"   2>/dev/null
    sips -z 64  64  "$_BASE_PNG" --out "$_ICONSET/icon_32x32@2x.png"   2>/dev/null
    sips -z 256 256 "$_BASE_PNG" --out "$_ICONSET/icon_128x128@2x.png" 2>/dev/null
    sips -z 512 512 "$_BASE_PNG" --out "$_ICONSET/icon_256x256@2x.png" 2>/dev/null
    _ICNS_PATH="$(mktemp).icns"
    iconutil -c icns "$_ICONSET" -o "$_ICNS_PATH"
    rm -rf "$(dirname "$_ICONSET")" "$_BASE_PNG"

    osacompile -o "$TMP_DIR/EasyOKAPI.app" "$SOURCE_DIR/run.scpt"
    if [ $? -eq 0 ]; then
        cp "$_ICNS_PATH" "$TMP_DIR/EasyOKAPI.app/Contents/Resources/applet.icns"
        echo "✅ EasyOKAPI.app built with ht icon."
    else
        echo "❌ osacompile failed — aborting."
        rm -f "$_ICNS_PATH"; exit 1
    fi
    rm -f "$_ICNS_PATH"
else
    echo "❌ sips could not convert ht.ico — aborting."
    exit 1
fi

# ── Bundle Resources into the app ─────────────────────────────────────────────
# setup.sh   — first-run installer (Homebrew → pyenv → Python → download → venv)
# launch.sh  — subsequent launches (splash + Flask)
# splash.py  — GUI splash window
# okapi.png  — icon for osascript dialogs used by setup.sh / uninstall.command
echo "📦 Bundling Resources into EasyOKAPI.app…"
APP_RES="$TMP_DIR/EasyOKAPI.app/Contents/Resources"
if [ -d "$APP_RES" ]; then
    cp "$SOURCE_DIR/setup.sh"              "$APP_RES/"
    cp "$SOURCE_DIR/launch.sh"             "$APP_RES/"
    cp "$SOURCE_DIR/splash.py"             "$APP_RES/"
    cp "$SOURCE_DIR/uninstall.command"     "$APP_RES/"
    cp "$PROJECT_ROOT/static/okapi.png"    "$APP_RES/"
    chmod +x \
        "$APP_RES/setup.sh" \
        "$APP_RES/launch.sh" \
        "$APP_RES/splash.py" \
        "$APP_RES/uninstall.command"
    echo "✅ Resources bundled."
else
    echo "❌ App bundle Resources directory not found."
    exit 1
fi

# ── Applications symlink (drag-to-install) ────────────────────────────────────
echo "🔗 Adding Applications symlink…"
ln -sf /Applications "$TMP_DIR/Applications"

# ── Create writable DMG ───────────────────────────────────────────────────────
echo "🛠️  Creating writable DMG…"
hdiutil create -volname "$APP_NAME" -srcfolder "$TMP_DIR" \
    -ov -format UDRW -size 300m "$RW_DMG"
[ $? -ne 0 ] && { echo "❌ hdiutil create failed."; exit 1; }

echo "📎 Mounting DMG for layout branding…"
hdiutil attach -readwrite -noverify -noautoopen "$RW_DMG"
VOLUME="/Volumes/$APP_NAME"
sleep 3

echo "🖼️  Applying drag-to-install layout via Finder…"
# Window: 800 × 430 px (matches background image)
# EasyOKAPI.app left-centre; Applications alias right-centre; uninstall bottom-right.
osascript <<APPLESCRIPT
tell application "Finder"
    tell disk "$APP_NAME"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set bounds of container window to {200, 120, 1000, 550}
        set icon size of icon view options of container window to 96
        set text size of icon view options of container window to 12
        set arrangement of icon view options of container window to not arranged
        set background picture of icon view options of container window to file ".background:background.png"

        -- App (left side)
        try
            set position of item "EasyOKAPI.app" to {200, 200}
        end try
        -- Applications alias (right side)
        try
            set position of item "Applications" to {590, 200}
        end try
        -- Uninstall utility (bottom-right, secondary)
        try
            set position of item "uninstall.command" to {590, 360}
        end try
        -- Hide helper assets off-canvas
        try
            set position of item "okapi.png" to {-300, -300}
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
[ $? -ne 0 ] && { echo "❌ Conversion failed."; rm -f "$RW_DMG"; exit 1; }
rm -f "$RW_DMG"

echo "✅ $DMG_NAME created in $PROJECT_ROOT"

# ── Update version badge in README.md ────────────────────────────────────────
echo "📝 Updating version in README.md…"
sed -i '' "s|img.shields.io/github/v/release/Promethees/microalbumin-Flask?label=latest|img.shields.io/badge/latest-${VERSION}-blue|g" "$PROJECT_ROOT/README.md"
sed -i '' "s|img.shields.io/badge/latest-v[0-9.]*[a-z]*-blue|img.shields.io/badge/latest-${VERSION}-blue|g" "$PROJECT_ROOT/README.md"
echo "✅ README.md updated with $VERSION"

# ── Cleanup ───────────────────────────────────────────────────────────────────
rm -rf "$TMP_DIR"
echo "Done."
