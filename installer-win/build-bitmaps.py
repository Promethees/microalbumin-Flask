#!/usr/bin/env python3
"""Windows-compatible equivalent of build-bitmaps.sh.
Generates sidebar.bmp and header.bmp for the NSIS MUI2 installer using Pillow.

Design: dark-indigo theme matching the EasyOKAPI web app palette.
  Sidebar: slate-900 → indigo-950 gradient, indigo-500 accent bars, white logo card
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

# ── Brand palette (mirrors EasyOKAPI web app CSS variables) ───────────────────
DARK_TOP     = (15,  23,  42)   # slate-900   #0f172a
DARK_BOTTOM  = (30,  27,  75)   # indigo-950  #1e1b4b
ACCENT       = (99, 102, 241)   # indigo-500  #6366f1
ACCENT_SOFT  = (129, 140, 248)  # indigo-400  #818cf8
WHITE        = (255, 255, 255)
CARD_BG      = (255, 255, 255)


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


def rounded_rect(draw: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int,
                 r: int, fill: tuple) -> None:
    """Draw a filled rounded rectangle (no PIL built-in in older Pillow)."""
    draw.rectangle([x0 + r, y0,     x1 - r, y1],     fill=fill)
    draw.rectangle([x0,     y0 + r, x1,     y1 - r], fill=fill)
    draw.ellipse  ([x0,     y0,     x0 + 2*r, y0 + 2*r], fill=fill)
    draw.ellipse  ([x1 - 2*r, y0,   x1,     y0 + 2*r], fill=fill)
    draw.ellipse  ([x0,     y1 - 2*r, x0 + 2*r, y1],   fill=fill)
    draw.ellipse  ([x1 - 2*r, y1 - 2*r, x1, y1],       fill=fill)


# ── Sidebar (164 × 314) ───────────────────────────────────────────────────────

def build_sidebar() -> None:
    for src in (LOGO_SRC, OKAPI_SRC):
        if not src.exists():
            print(f"ERROR: {src} not found.")
            sys.exit(1)

    canvas = vertical_gradient(SIDEBAR_W, SIDEBAR_H, DARK_TOP, DARK_BOTTOM)
    draw   = ImageDraw.Draw(canvas)

    # Top accent bar (4 px)
    draw.rectangle([0, 0, SIDEBAR_W - 1, 3], fill=ACCENT)

    # Three decorative dots centred below the accent bar
    dot_y, dot_r = 11, 2
    for offset in (-10, 0, 10):
        cx = SIDEBAR_W // 2 + offset
        draw.ellipse([cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r],
                     fill=ACCENT_SOFT)

    # Okapi mascot — centred, slightly above middle
    okapi = fit_image(Image.open(OKAPI_SRC), 145, 145)
    paste_centered(canvas, okapi, y_offset=-20)

    # White rounded-rect card at the bottom for the logo
    card_margin = 12
    card_h      = 48
    card_x0     = card_margin
    card_x1     = SIDEBAR_W - card_margin
    card_y0     = SIDEBAR_H - card_h - 14
    card_y1     = card_y0 + card_h
    rounded_rect(draw, card_x0, card_y0, card_x1, card_y1, r=6, fill=CARD_BG)

    # Logo inside the card (JPEG has white bg — blends naturally with white card)
    logo = Image.open(LOGO_SRC).convert("RGB")
    logo.thumbnail((card_x1 - card_x0 - 16, card_h - 10), Image.LANCZOS)
    lx = card_x0 + (card_x1 - card_x0 - logo.width)  // 2
    ly = card_y0 + (card_h - logo.height) // 2
    canvas.paste(logo, (lx, ly))

    # Bottom accent bar (2 px)
    draw.rectangle([0, SIDEBAR_H - 2, SIDEBAR_W - 1, SIDEBAR_H - 1], fill=ACCENT)

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
    print("Building NSIS installer bitmaps (dark-indigo theme)…")
    build_sidebar()
    build_header()
    print("Done. Recompile: makensis /DAPP_VERSION=x.x.x /DAUTH_BASE_URL=https://... setup.nsi")
