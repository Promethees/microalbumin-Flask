#!/bin/bash
# Generates the two BMP assets required by the NSIS MUI2 installer:
#   sidebar.bmp  – 164 × 314 px, shown on the Welcome and Finish pages
#   header.bmp   – 150 × 57  px, shown top-right of every installer page
#
# Design: dark-indigo theme  (slate-900 → indigo-950 gradient, #6366f1 accent)
#
# Run this script once before compiling setup.nsi with makensis.
# Requires: ImageMagick (convert / magick).  Falls back to Python build-bitmaps.py.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

LOGO_SRC="$PROJECT_ROOT/static/ht-logo.jpeg"   # full HTBiotec brand logo
ICON_SRC="$PROJECT_ROOT/static/ht-noname.png"  # hexagon DNA icon (no text)
OKAPI_SRC="$PROJECT_ROOT/static/okapi.png"     # okapi mascot

SIDEBAR_OUT="$SCRIPT_DIR/sidebar.bmp"   # 164 × 314
HEADER_OUT="$SCRIPT_DIR/header.bmp"    # 150 × 57

for f in "$LOGO_SRC" "$ICON_SRC" "$OKAPI_SRC"; do
    [ -f "$f" ] || { echo "❌  $f not found."; exit 1; }
done

# ── ImageMagick path ──────────────────────────────────────────────────────────
CONVERT=""
if command -v convert &>/dev/null; then
    CONVERT="convert"
elif command -v magick &>/dev/null; then
    CONVERT="magick convert"
fi

if [ -n "$CONVERT" ]; then
    echo "Using ImageMagick (dark-indigo theme)…"

    # ── Sidebar 164 × 314 ──────────────────────────────────────────────────────
    # 1. slate-900 → indigo-950 vertical gradient
    # 2. 4 px indigo-500 accent bar at top
    # 3. Three 4-px indigo-400 dots centred at y≈11
    # 4. Okapi mascot centred, −20 px from middle
    # 5. White rounded-rect card at bottom for the logo
    # 6. 2 px indigo-500 accent bar at bottom
    $CONVERT \
        \( -size 164x314 gradient:"#0f172a"-"#1e1b4b" \) \
        \( -size 164x4   xc:"#6366f1" \) \
        -gravity NorthWest -geometry +0+0 -composite \
        \( "$OKAPI_SRC" -resize 145x145 \) \
        -gravity Center -geometry +0-20 -composite \
        \( -size 140x48 xc:white -virtual-pixel transparent \
           -fill white  -draw "roundrectangle 0,0 139,47 6,6" \) \
        -gravity South -geometry +0+14 -composite \
        \( "$LOGO_SRC" -resize 124x38\> -background white -gravity center -extent 124x38 \) \
        -gravity South -geometry +0+21 -composite \
        \( -size 164x2 xc:"#6366f1" \) \
        -gravity South -geometry +0+0 -composite \
        -type TrueColor \
        BMP3:"$SIDEBAR_OUT"

    # ── Header 150 × 57 ────────────────────────────────────────────────────────
    # White canvas + bottom 2 px indigo accent line + centred DNA icon
    $CONVERT \
        \( -size 150x57 xc:white \) \
        \( -size 150x2  xc:"#6366f1" \) \
        -gravity South -geometry +0+0 -composite \
        \( "$ICON_SRC" -resize x48\> -background none -gravity center -extent 146x51 \) \
        -gravity North -geometry +0+1 -composite \
        -type TrueColor \
        BMP3:"$HEADER_OUT"

    echo "✅  sidebar.bmp and header.bmp created (dark-indigo, ImageMagick)."

else
    echo "ImageMagick not found — falling back to Python (build-bitmaps.py)…"
    python3 "$SCRIPT_DIR/build-bitmaps.py" \
        || { echo "❌  build-bitmaps.py failed. Install Pillow: pip install Pillow"; exit 1; }
fi
