#!/bin/bash
# build-dmg-frozen.sh — wrap the PyInstaller onedir (dist/EasyOKAPI/) into a
# drag-to-install DMG for the no-source macOS build.
#
# Differs from build-dmg.sh (the source builder): the .app embeds the frozen
# binary in Contents/Resources/EasyOKAPI/ and launches it directly (run-frozen.scpt
# → launch-frozen.sh). There is no setup.sh / token prompt / pyenv / venv / source
# download — the binary is self-contained and self-creates its per-user data dirs.
#
# Prereq: `python tools/package.py --encode` has produced dist/EasyOKAPI/.
# Env:    APP_VERSION (bare, e.g. 1.4.1); optional SIGNING_IDENTITY.

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
APP_NAME="EasyOKAPI"
SOURCE_DIR="installer-mac"
TMP_DIR="tmp_dmg_frozen_root"
DIST_BUNDLE="$PROJECT_ROOT/dist/EasyOKAPI"

if [ -z "${APP_VERSION:-}" ]; then
    echo "❌ APP_VERSION is not set."; exit 1
fi
if [ ! -d "$DIST_BUNDLE" ]; then
    echo "❌ Frozen bundle not found at $DIST_BUNDLE. Run: python tools/package.py --encode"; exit 1
fi
VERSION="v${APP_VERSION}"
DMG_NAME="${APP_NAME}_${VERSION}.dmg"
RW_DMG="${APP_NAME}_${VERSION}_rw.dmg"

echo "🚀 Building no-source DMG for $APP_NAME ($VERSION)…"
cd "$PROJECT_ROOT"

rm -f "$DMG_NAME" "$RW_DMG"; rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"
cp "$SOURCE_DIR/uninstall.command" "$TMP_DIR/" 2>/dev/null || true
cp "$PROJECT_ROOT/static/okapi.png" "$TMP_DIR/okapi.png" 2>/dev/null || true

# ── Plain background (drag-to-install) ────────────────────────────────────────
mkdir -p "$TMP_DIR/.background"
python3 -c "
import struct, zlib
w, h = 800, 430
row = bytes([0] + [0xFF, 0xFE, 0xF5] * w)
idat = zlib.compress(row * h)
def chunk(tag, data):
    raw = tag + data
    return struct.pack('>I', len(data)) + raw + struct.pack('>I', zlib.crc32(raw) & 0xffffffff)
with open('$TMP_DIR/.background/background.png', 'wb') as f:
    f.write(b'\x89PNG\r\n\x1a\n')
    f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)))
    f.write(chunk(b'IDAT', idat))
    f.write(chunk(b'IEND', b''))
"

# ── Build EasyOKAPI.app from run-frozen.scpt ─────────────────────────────────
echo "🎨 Building EasyOKAPI.app…"
_ICONSET="$(mktemp -d)/ht.iconset"; mkdir -p "$_ICONSET"
_BASE_PNG="$(mktemp).png"
if sips -s format png "$PROJECT_ROOT/static/ht.ico" --out "$_BASE_PNG" 2>/dev/null; then
    for sz in 16 32 128 256 512; do
        sips -z $sz $sz "$_BASE_PNG" --out "$_ICONSET/icon_${sz}x${sz}.png" 2>/dev/null
    done
    sips -z 32 32 "$_BASE_PNG" --out "$_ICONSET/icon_16x16@2x.png" 2>/dev/null
    sips -z 64 64 "$_BASE_PNG" --out "$_ICONSET/icon_32x32@2x.png" 2>/dev/null
    sips -z 256 256 "$_BASE_PNG" --out "$_ICONSET/icon_128x128@2x.png" 2>/dev/null
    sips -z 512 512 "$_BASE_PNG" --out "$_ICONSET/icon_256x256@2x.png" 2>/dev/null
    _ICNS_PATH="$(mktemp).icns"
    iconutil -c icns "$_ICONSET" -o "$_ICNS_PATH"
fi

osacompile -o "$TMP_DIR/EasyOKAPI.app" "$SOURCE_DIR/run-frozen.scpt"
[ -n "${_ICNS_PATH:-}" ] && cp "$_ICNS_PATH" "$TMP_DIR/EasyOKAPI.app/Contents/Resources/applet.icns" 2>/dev/null || true
echo "✅ EasyOKAPI.app built."

# ── Embed the frozen bundle + launcher scripts ───────────────────────────────
echo "📦 Embedding frozen binary into the app…"
APP_RES="$TMP_DIR/EasyOKAPI.app/Contents/Resources"
cp -R "$DIST_BUNDLE" "$APP_RES/EasyOKAPI"
cp "$SOURCE_DIR/launch-frozen.sh"  "$APP_RES/"
cp "$SOURCE_DIR/migrate-frozen.sh" "$APP_RES/"
cp "$SOURCE_DIR/uninstall.command" "$APP_RES/" 2>/dev/null || true
cp "$PROJECT_ROOT/static/okapi.png" "$APP_RES/" 2>/dev/null || true
chmod +x "$APP_RES/launch-frozen.sh" "$APP_RES/migrate-frozen.sh" \
         "$APP_RES/EasyOKAPI/EasyOKAPI"
echo "✅ Frozen bundle embedded."

# ── Optional code-signing (set SIGNING_IDENTITY to enable) ───────────────────
if [ -n "${SIGNING_IDENTITY:-}" ]; then
    echo "🔏 Signing app (deep)…"
    xattr -cr "$TMP_DIR/EasyOKAPI.app"
    # Sign the embedded binary + the .app. --deep signs the nested onedir's
    # Mach-O + dylibs; notarization is handled separately (see SIGNING.md).
    codesign --deep --force --options runtime \
        --entitlements "$SOURCE_DIR/entitlements.plist" \
        --sign "$SIGNING_IDENTITY" "$TMP_DIR/EasyOKAPI.app"
    echo "✅ Signed."
else
    echo "ℹ️  SIGNING_IDENTITY not set — unsigned (users may need to bypass Gatekeeper)."
fi

ln -sf /Applications "$TMP_DIR/Applications"

# ── Create + brand the DMG (onedir is large → 800 MB) ────────────────────────
echo "🛠️  Creating DMG…"
hdiutil create -volname "$APP_NAME" -srcfolder "$TMP_DIR" -ov -format UDRW -size 800m "$RW_DMG"
hdiutil attach -readwrite -noverify -noautoopen "$RW_DMG"
VOLUME="/Volumes/$APP_NAME"; sleep 3

osascript <<APPLESCRIPT || true
tell application "Finder"
    tell disk "$APP_NAME"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set bounds of container window to {200, 120, 1000, 550}
        set icon size of icon view options of container window to 96
        set background picture of icon view options of container window to file ".background:background.png"
        try
            set position of item "EasyOKAPI.app" to {200, 200}
        end try
        try
            set position of item "Applications" to {590, 200}
        end try
        try
            set position of item "uninstall.command" to {590, 360}
        end try
        try
            set position of item "okapi.png" to {-300, -300}
        end try
        close
        open
        update without registering applications
        delay 2
        close
    end tell
end tell
APPLESCRIPT

hdiutil detach "$VOLUME" -force 2>/dev/null || hdiutil detach "$VOLUME" 2>/dev/null || true
sleep 2

echo "📦 Compressing → ${DMG_NAME}…"
hdiutil convert "$RW_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG_NAME"
rm -f "$RW_DMG"; rm -rf "$TMP_DIR"
echo "✅ $DMG_NAME created in $PROJECT_ROOT"
