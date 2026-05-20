#!/bin/bash
# Generates the two BMP assets required by the NSIS MUI2 installer:
#   header.bmp   – 150 × 57  px, shown top-right of every installer page
#   sidebar.bmp  – 164 × 314 px, shown on the Welcome and Finish pages
#
# Run this script once before compiling setup.nsi with makensis.
# Requires: ImageMagick (convert).  Falls back to sips on macOS (approximate).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

LOGO_SRC="$PROJECT_ROOT/static/ht-logo.jpeg"   # full HTBiotec brand logo
ICON_SRC="$PROJECT_ROOT/static/ht-noname.png"  # hexagon DNA icon (no text)
OKAPI_SRC="$PROJECT_ROOT/static/okapi.png"     # okapi mascot

SIDEBAR_OUT="$SCRIPT_DIR/sidebar.bmp"   # 164 × 314
HEADER_OUT="$SCRIPT_DIR/header.bmp"    # 150 × 57

if [ ! -f "$LOGO_SRC" ]; then
    echo "❌  $LOGO_SRC not found."
    exit 1
fi
if [ ! -f "$ICON_SRC" ]; then
    echo "❌  $ICON_SRC not found."
    exit 1
fi
if [ ! -f "$OKAPI_SRC" ]; then
    echo "❌  $OKAPI_SRC not found."
    exit 1
fi

# ── ImageMagick path (try 'convert', then 'magick convert') ──────────────────
CONVERT=""
if command -v convert &>/dev/null; then
    CONVERT="convert"
elif command -v magick &>/dev/null; then
    CONVERT="magick convert"
fi

if [ -n "$CONVERT" ]; then
    echo "Using ImageMagick…"

    # Sidebar — fit ht-logo within 164 × 260, center on warm-white 164 × 314 canvas,
    #           then composite the okapi mascot at bottom-left at 22% opacity
    $CONVERT "$LOGO_SRC" \
        -resize 164x260\> \
        -background "#FFFDF0" \
        -gravity North \
        -extent 164x314 \
        -type TrueColor \
        BMP3:"$SIDEBAR_OUT"
    $CONVERT "$SIDEBAR_OUT" \
        \( "$OKAPI_SRC" -resize 70x70 -alpha set -channel Alpha -evaluate multiply 0.22 +channel \) \
        -gravity SouthWest -geometry +6+6 -composite \
        -type TrueColor \
        BMP3:"$SIDEBAR_OUT"

    # Header — fit DNA icon to height 48, center on white 150 × 57 canvas
    $CONVERT "$ICON_SRC" \
        -resize x48\> \
        -background white \
        -gravity center \
        -extent 150x57 \
        -type TrueColor \
        BMP3:"$HEADER_OUT"

    echo "✅  sidebar.bmp and header.bmp created with ImageMagick (okapi watermark applied)."

elif command -v sips &>/dev/null; then
    echo "ImageMagick not found — using sips (macOS, approximate)…"

    # sips cannot pad/composite, so we resize to fill and accept slight stretch
    sips -z 314 164 "$LOGO_SRC"  --out "${SIDEBAR_OUT%.bmp}.png" 2>/dev/null
    sips -s format bmp "${SIDEBAR_OUT%.bmp}.png" --out "$SIDEBAR_OUT"   2>/dev/null
    rm -f "${SIDEBAR_OUT%.bmp}.png"

    sips -z 57 150  "$ICON_SRC" --out "${HEADER_OUT%.bmp}.png"  2>/dev/null
    sips -s format bmp "${HEADER_OUT%.bmp}.png"  --out "$HEADER_OUT"    2>/dev/null
    rm -f "${HEADER_OUT%.bmp}.png"

    echo "✅  sidebar.bmp and header.bmp created with sips (consider installing ImageMagick for better quality)."

else
    echo "❌  Neither ImageMagick nor sips is available."
    echo "    Install ImageMagick:  brew install imagemagick  or  sudo apt install imagemagick"
    exit 1
fi
