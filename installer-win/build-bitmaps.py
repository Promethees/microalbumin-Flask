#!/usr/bin/env python3
"""
Windows-compatible equivalent of build-bitmaps.sh.
Generates sidebar.bmp and header.bmp for the NSIS MUI2 installer using Pillow.

Usage:
    pip install Pillow
    python installer-win/build-bitmaps.py
"""

import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    print("ERROR: Pillow is not installed. Run: pip install Pillow")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

LOGO_SRC  = PROJECT_ROOT / "static" / "ht-logo.jpeg"
ICON_SRC  = PROJECT_ROOT / "static" / "ht-noname.png"
OKAPI_SRC = PROJECT_ROOT / "static" / "okapi.png"

SIDEBAR_OUT = SCRIPT_DIR / "sidebar.bmp"   # 164 x 314
HEADER_OUT  = SCRIPT_DIR / "header.bmp"    # 150 x 57

SIDEBAR_W, SIDEBAR_H = 164, 314
HEADER_W,  HEADER_H  = 150, 57
BG_COLOR = (255, 253, 240)  # #FFFDF0 warm white


def fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    img = img.convert("RGBA")
    img.thumbnail((max_w, max_h), Image.LANCZOS)
    return img


def paste_centered(canvas: Image.Image, overlay: Image.Image, y_offset: int = 0) -> None:
    cx = (canvas.width - overlay.width) // 2
    cy = (canvas.height - overlay.height) // 2 + y_offset
    canvas.paste(overlay, (cx, cy), overlay)


def build_sidebar() -> None:
    for src in (LOGO_SRC, OKAPI_SRC):
        if not src.exists():
            print(f"ERROR: {src} not found.")
            sys.exit(1)

    canvas = Image.new("RGB", (SIDEBAR_W, SIDEBAR_H), BG_COLOR)

    # Okapi mascot centred, slightly above centre (main visual element)
    okapi = fit_image(Image.open(OKAPI_SRC), 140, 140)
    paste_centered(canvas, okapi, y_offset=-20)

    # HTBiotec logo small at the bottom (brand anchor)
    logo = fit_image(Image.open(LOGO_SRC), 120, 40)
    lx = (canvas.width - logo.width) // 2
    ly = canvas.height - logo.height - 8
    canvas.paste(logo, (lx, ly), logo)

    # Save as 24-bit BMP (BMP3 in ImageMagick terms)
    canvas.convert("RGB").save(str(SIDEBAR_OUT), format="BMP")
    print(f"  sidebar.bmp  written ({SIDEBAR_W}x{SIDEBAR_H})")


def build_header() -> None:
    if not ICON_SRC.exists():
        print(f"ERROR: {ICON_SRC} not found.")
        sys.exit(1)

    canvas = Image.new("RGB", (HEADER_W, HEADER_H), "white")

    icon = fit_image(Image.open(ICON_SRC), HEADER_W, 48)
    ix = (canvas.width  - icon.width)  // 2
    iy = (canvas.height - icon.height) // 2
    canvas.paste(icon, (ix, iy), icon)

    canvas.convert("RGB").save(str(HEADER_OUT), format="BMP")
    print(f"  header.bmp   written ({HEADER_W}x{HEADER_H})")


if __name__ == "__main__":
    print("Building NSIS installer bitmaps…")
    build_sidebar()
    build_header()
    print("Done. Recompile setup.nsi with: makensis /DAPP_VERSION=x.x.x setup.nsi")
