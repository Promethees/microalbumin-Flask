#!/usr/bin/env python3
"""Windows-compatible equivalent of build-bitmaps.sh.
Generates sidebar.bmp and header.bmp for the NSIS MUI2 installer using Pillow.

Design: indigo-to-white gradient theme.
  Sidebar: indigo-500 → white gradient (top to bottom), logo floats on white base
  Header:  white background with bottom indigo accent line

Usage:
    pip install Pillow
    python installer-win/build-bitmaps.py
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("ERROR: Pillow is not installed. Run: pip install Pillow")
    sys.exit(1)

SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

LOGO_SRC  = PROJECT_ROOT / "static" / "ht-logo.jpeg"
ICON_SRC  = PROJECT_ROOT / "static" / "ht-noname.png"
OKAPI_SRC = PROJECT_ROOT / "static" / "okapi.png"

SIDEBAR_OUT = SCRIPT_DIR / "sidebar.bmp"   # 164 x 314
HEADER_OUT  = SCRIPT_DIR / "header.bmp"    # 150 x 57

SIDEBAR_W, SIDEBAR_H = 164, 314
HEADER_W,  HEADER_H  = 150, 57

# ── Brand palette ─────────────────────────────────────────────────────────────
PURPLE_TOP  = (99, 102, 241)   # indigo-500  #6366f1  — gradient top
WHITE_BOT   = (255, 255, 255)  # white       #ffffff  — gradient bottom
ACCENT      = (99, 102, 241)   # indigo-500  (header accent line)
WHITE       = (255, 255, 255)


# ── Helpers ───────────────────────────────────────────────────────────────────

def vertical_gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    img  = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (w - 1, y)], fill=(r, g, b))
    return img


def fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    img = img.convert("RGBA")
    img.thumbnail((max_w, max_h), Image.LANCZOS)
    return img


def paste_centered(canvas: Image.Image, overlay: Image.Image, y_offset: int = 0) -> None:
    cx = (canvas.width  - overlay.width)  // 2
    cy = (canvas.height - overlay.height) // 2 + y_offset
    if overlay.mode == "RGBA":
        canvas.paste(overlay, (cx, cy), overlay)
    else:
        canvas.paste(overlay, (cx, cy))


def remove_white_bg(img: Image.Image, threshold: int = 230) -> Image.Image:
    """Make near-white pixels transparent so the logo floats on any background."""
    img    = img.convert("RGBA")
    pixels = img.load()
    w, h   = img.size
    for x in range(w):
        for y in range(h):
            r, g, b, a = pixels[x, y]
            if r > threshold and g > threshold and b > threshold:
                pixels[x, y] = (r, g, b, 0)
    return img


# ── Sidebar (164 × 314) ───────────────────────────────────────────────────────

def build_sidebar() -> None:
    for src in (LOGO_SRC, OKAPI_SRC):
        if not src.exists():
            print(f"ERROR: {src} not found.")
            sys.exit(1)

    # Indigo-500 at top → white at bottom
    canvas = vertical_gradient(SIDEBAR_W, SIDEBAR_H, PURPLE_TOP, WHITE_BOT)
    draw   = ImageDraw.Draw(canvas)

    # Three white decorative dots centred near the top (visible on purple bg)
    dot_y, dot_r = 11, 2
    for offset in (-10, 0, 10):
        cx = SIDEBAR_W // 2 + offset
        draw.ellipse([cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r],
                     fill=WHITE)

    # Okapi mascot — centred, slightly above middle
    okapi = fit_image(Image.open(OKAPI_SRC), 145, 145)
    paste_centered(canvas, okapi, y_offset=-20)

    # Logo floats on the white base — strip its white background first
    logo = remove_white_bg(Image.open(LOGO_SRC))
    logo.thumbnail((SIDEBAR_W - 24, 44), Image.LANCZOS)
    lx = (SIDEBAR_W - logo.width) // 2
    ly = SIDEBAR_H - logo.height - 14
    canvas.paste(logo, (lx, ly), logo)

    canvas.convert("RGB").save(str(SIDEBAR_OUT), format="BMP")
    print(f"  sidebar.bmp  written ({SIDEBAR_W}x{SIDEBAR_H})")


# ── Header (150 × 57) ─────────────────────────────────────────────────────────

def build_header() -> None:
    if not ICON_SRC.exists():
        print(f"ERROR: {ICON_SRC} not found.")
        sys.exit(1)

    canvas = Image.new("RGB", (HEADER_W, HEADER_H), WHITE)
    draw   = ImageDraw.Draw(canvas)

    # Bottom accent line (2 px) — ties header to the sidebar accent colour
    draw.rectangle([0, HEADER_H - 2, HEADER_W - 1, HEADER_H - 1], fill=ACCENT)

    # DNA icon centred (white canvas matches the installer inner-page background)
    icon = fit_image(Image.open(ICON_SRC), HEADER_W - 4, HEADER_H - 6)
    ix   = (HEADER_W  - icon.width)  // 2
    iy   = (HEADER_H  - icon.height) // 2 - 1  # nudge up slightly above the accent line
    canvas.paste(icon, (ix, iy), icon)

    canvas.convert("RGB").save(str(HEADER_OUT), format="BMP")
    print(f"  header.bmp   written ({HEADER_W}x{HEADER_H})")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Building NSIS installer bitmaps (indigo-to-white gradient)...")
    build_sidebar()
    build_header()
    print("Done. Recompile: makensis /DAPP_VERSION=x.x.x /DAUTH_BASE_URL=https://... setup.nsi")
