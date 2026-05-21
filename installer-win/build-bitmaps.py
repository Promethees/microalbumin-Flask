#!/usr/bin/env python3
"""Windows-compatible equivalent of build-bitmaps.sh.
Generates sidebar.bmp, header.bmp, and background.bmp for the NSIS installer.

Design: indigo-to-white gradient theme.
  Sidebar:    indigo-500 -> white gradient (top to bottom), logo floats on white base
  Header:     indigo-900 -> white gradient (left to right) with bottom accent line
  Background: vivid blue -> purple gradient, photorealistic-style 3-D DNA double
              helices with correct z-ordering, depth-of-field blur, and pink glow.

Usage:
    pip install Pillow
    python installer-win/build-bitmaps.py
"""

import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    print("ERROR: Pillow is not installed. Run: pip install Pillow")
    sys.exit(1)

SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

LOGO_SRC  = PROJECT_ROOT / "static" / "ht-logo.jpeg"
ICON_SRC  = PROJECT_ROOT / "static" / "ht-noname.png"
OKAPI_SRC = PROJECT_ROOT / "static" / "okapi.png"

SIDEBAR_OUT  = SCRIPT_DIR / "sidebar.bmp"     # 164 x 314
HEADER_OUT   = SCRIPT_DIR / "header.bmp"      # 150 x 57
BG_OUT       = SCRIPT_DIR / "background.bmp"  # 1280 x 720
PAGE_BG_OUT  = SCRIPT_DIR / "page_bg.bmp"     # 432 x 314  (NSIS inner-dialog size)

SIDEBAR_W,  SIDEBAR_H  = 164, 314
HEADER_W,   HEADER_H   = 150, 57
BG_W,       BG_H       = 1280, 720
# 432 px = standard MUI2 window width.
# 314 px = sidebar height = full inner-dialog height for the Welcome page.
# LoadImageW scaling is unreliable for large source bitmaps, so page_bg.bmp is
# pre-scaled here and loaded at native size (cx=0, cy=0) in the NSIS script.
# Any excess height is silently clipped by SetWindowPos on the STATIC control.
PAGE_BG_W,  PAGE_BG_H  = 432, 314

# ── Brand palette (sidebar / header) ─────────────────────────────────────────
PURPLE_TOP  = (99,  102, 241)   # indigo-500
WHITE_BOT   = (255, 255, 255)
ACCENT      = (99,  102, 241)
WHITE       = (255, 255, 255)
HEADER_LEFT = (49,  46,  129)   # indigo-900


# ── Generic helpers ───────────────────────────────────────────────────────────

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


def horizontal_gradient(w: int, h: int, left: tuple, right: tuple) -> Image.Image:
    img  = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for x in range(w):
        t = x / max(w - 1, 1)
        r = int(left[0] + (right[0] - left[0]) * t)
        g = int(left[1] + (right[1] - left[1]) * t)
        b = int(left[2] + (right[2] - left[2]) * t)
        draw.line([(x, 0), (x, h - 1)], fill=(r, g, b))
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


# ── Background: 3-D DNA helix rendering ──────────────────────────────────────

def _helix_points(cx, cy, angle_deg, n_turns, length, amp, steps=800):
    """
    Pre-compute (pts1, pts2, depths) for a double helix.

    Axis runs at angle_deg from horizontal (positive = tilted up-right).
    Oscillation is perpendicular to the axis in the image plane.
    depth[i] = cos(phase) — positive means strand-1 is toward the viewer.
    """
    theta = math.radians(angle_deg)
    adx, ady =  math.cos(theta), -math.sin(theta)   # axis direction
    pdx, pdy =  math.sin(theta),  math.cos(theta)   # perpendicular

    sx = cx - (length / 2) * adx
    sy = cy - (length / 2) * ady

    pts1, pts2, depths = [], [], []
    for i in range(steps + 1):
        s   = i / steps
        t   = s * 2 * math.pi * n_turns
        ax  = sx + s * length * adx
        ay  = sy + s * length * ady
        osc = amp * math.sin(t)
        pts1.append((ax + osc * pdx, ay + osc * pdy))
        pts2.append((ax - osc * pdx, ay - osc * pdy))
        depths.append(math.cos(t))

    return pts1, pts2, depths


def _draw_helix(draw, cx, cy, angle_deg, n_turns, length, amp,
                strand_col, rung_col,
                strand_w=13, rung_w=8, alpha=235, steps=800):
    """
    Draw a 3-D DNA double helix with correct z-ordering.

    Two-pass rendering:
      Pass 1 — draw every back-strand segment at reduced alpha/width.
      Rungs   — cross-bars at natural depth (between passes).
      Pass 2  — draw every front-strand segment at full alpha + highlight.

    This ensures the front strand is always painted on top of the back strand,
    giving the characteristic crossing-over appearance of a real double helix.
    """
    pts1, pts2, depths = _helix_points(cx, cy, angle_deg, n_turns, length, amp, steps)
    sr, sg, sb = strand_col
    rr, rg, rb = rung_col

    back_w = max(1, strand_w - 4)
    # Keep back-strand dim so the front/back crossing is clear, not striped
    back_a = int(alpha * 0.28)

    # ── Pass 1: back-strand segments ─────────────────────────────────────────
    for i in range(steps):
        d = depths[i]
        if d >= 0:          # strand-1 is in front  → strand-2 is the back
            pts = pts2
        else:               # strand-2 is in front  → strand-1 is the back
            pts = pts1
        x0, y0 = int(pts[i][0]),   int(pts[i][1])
        x1, y1 = int(pts[i+1][0]), int(pts[i+1][1])
        draw.line([(x0, y0), (x1, y1)], fill=(sr, sg, sb, back_a), width=back_w)

    # ── Rungs (base-pair cross-bars) — drawn between the two strand passes ────
    # 6 rungs per full turn: enough to suggest the ladder without filling the interior
    rung_every = max(1, steps // (n_turns * 6))
    for i in range(0, steps + 1, rung_every):
        d  = depths[i]
        rw = max(1, int(rung_w  * (0.40 + 0.60 * abs(d))))
        ra = int(alpha * (0.42 + 0.58 * abs(d)))
        x0, y0 = int(pts1[i][0]), int(pts1[i][1])
        x1, y1 = int(pts2[i][0]), int(pts2[i][1])
        draw.line([(x0, y0), (x1, y1)], fill=(rr, rg, rb, ra), width=rw)

    # ── Pass 2: front-strand segments + highlight strip ───────────────────────
    hw = max(1, strand_w // 4)   # highlight width
    for i in range(steps):
        d = depths[i]
        pts = pts1 if d >= 0 else pts2
        x0, y0 = int(pts[i][0]),   int(pts[i][1])
        x1, y1 = int(pts[i+1][0]), int(pts[i+1][1])
        # Base strand
        draw.line([(x0, y0), (x1, y1)], fill=(sr, sg, sb, alpha), width=strand_w)
        # Bright highlight: slightly lighter/whiter thin line on top
        draw.line([(x0, y0), (x1, y1)],
                  fill=(min(255, sr + 40), min(255, sg + 35), 255, int(alpha * 0.45)),
                  width=hw)


# ── Background: antibody / protein helpers ────────────────────────────────────

def _antibody(draw: ImageDraw.ImageDraw,
              cx: float, cy: float,
              scale: float = 1.0, rotation: float = 0.0,
              color: tuple = (220, 232, 255), alpha: int = 185) -> None:
    """
    Draw a stylised IgG antibody (Y-shaped domain model).

    Structure:
      Two Fab arms  — each has a lower junction domain (CH1/CL) and a tip
                      domain pair (VH/VL).
      Fc stem       — CH2 domain then CH3 domain going downward.
    """
    cr, cg, cb = color
    lw  = max(2, int(9 * scale))
    rot = math.radians(rotation)

    def rp(dx: float, dy: float):
        ca, sa = math.cos(rot), math.sin(rot)
        return cx + dx * ca - dy * sa, cy + dx * sa + dy * ca

    def seg(p0, p1) -> None:
        draw.line([(int(p0[0]), int(p0[1])), (int(p1[0]), int(p1[1]))],
                  fill=(cr, cg, cb, alpha), width=lw)

    def blob(p, r: int) -> None:
        bx, by = int(p[0]), int(p[1])
        draw.ellipse([bx - r, by - r, bx + r, by + r],
                     fill=(cr, cg, cb, alpha))
        # Bright inner highlight for a 3-D look
        hr = max(1, r // 2)
        draw.ellipse([bx - hr, by - hr, bx + hr, by + hr],
                     fill=(min(255, cr + 45), min(255, cg + 38), 255,
                           int(alpha * 0.55)))

    S = scale
    spread  = 50 * S
    arm_lo  = 58 * S   # length of lower arm segment
    arm_hi  = 60 * S   # length of upper arm segment
    stem_lo = 52 * S   # length of each stem segment

    hinge = rp(0,        0)
    la    = rp(-spread * 0.55, -arm_lo * 0.70)   # left  CH1/CL junction
    ra    = rp( spread * 0.55, -arm_lo * 0.70)   # right CH1/CL junction
    lt    = rp(-spread,        -arm_lo - arm_hi)  # left  VH/VL tip
    rt    = rp( spread,        -arm_lo - arm_hi)  # right VH/VL tip
    s1    = rp(0,  stem_lo * 0.85)               # CH2
    s2    = rp(0,  stem_lo * 1.90)               # CH3

    # Segments first (behind blobs)
    seg(hinge, la);  seg(la, lt)
    seg(hinge, ra);  seg(ra, rt)
    seg(hinge, s1);  seg(s1, s2)

    # Domain blobs on top
    ds = int(17 * S)   # standard domain radius
    ts = int(20 * S)   # tip domain (slightly larger)
    blob(lt, ts);  blob(rt, ts)
    blob(la, ds);  blob(ra, ds)
    blob(s1, ds);  blob(s2, ds)
    blob(hinge, int(11 * S))


def _protein_ring(draw: ImageDraw.ImageDraw,
                  cx: float, cy: float,
                  scale: float = 1.0, rotation: float = 0.0,
                  color: tuple = (220, 232, 255), alpha: int = 175) -> None:
    """
    Draw a simplified oligomeric protein ring complex (e.g. GroEL barrel top).

    Seven subunit domains arranged in a ring, connected by short segments,
    with a hollow centre to show the ring topology.
    """
    cr, cg, cb = color
    rot      = math.radians(rotation)
    n_sub    = 7
    ring_r   = int(48 * scale)    # radius of the subunit ring
    sub_r    = int(18 * scale)    # subunit domain radius
    lw       = max(2, int(7 * scale))

    pts = []
    for i in range(n_sub):
        theta = rot + 2 * math.pi * i / n_sub
        px = cx + ring_r * math.cos(theta)
        py = cy + ring_r * math.sin(theta)
        pts.append((px, py))

    # Connecting arcs between adjacent subunits
    for i in range(n_sub):
        p0, p1 = pts[i], pts[(i + 1) % n_sub]
        draw.line([(int(p0[0]), int(p0[1])), (int(p1[0]), int(p1[1]))],
                  fill=(cr, cg, cb, alpha), width=lw)

    # Subunit blobs
    for i, (px, py) in enumerate(pts):
        bx, by = int(px), int(py)
        draw.ellipse([bx - sub_r, by - sub_r, bx + sub_r, by + sub_r],
                     fill=(cr, cg, cb, alpha))
        hr = max(1, sub_r // 2)
        draw.ellipse([bx - hr, by - hr, bx + hr, by + hr],
                     fill=(min(255, cr + 40), min(255, cg + 33), 255,
                           int(alpha * 0.5)))

    # Small centre domain (channel pore)
    pr = max(2, int(10 * scale))
    draw.ellipse([int(cx) - pr, int(cy) - pr, int(cx) + pr, int(cy) + pr],
                 fill=(cr, cg, cb, int(alpha * 0.55)))


# ── Background (1280 x 720) ───────────────────────────────────────────────────

def build_background() -> None:
    W, H = BG_W, BG_H

    # ── Base: vivid blue (left) -> deep purple (right) ────────────────────────
    base = horizontal_gradient(W, H, (42, 100, 220), (108, 32, 182))

    # ── Pinkish-violet glow bloom in upper-right (matches reference image) ────
    bloom = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd    = ImageDraw.Draw(bloom)
    bd.ellipse([550, -150, 1200, 520], fill=(195, 105, 255, 165))
    bloom = bloom.filter(ImageFilter.GaussianBlur(radius=115))
    base  = Image.alpha_composite(base.convert("RGBA"), bloom).convert("RGB")

    # Strand / rung colours: near-white lavender-blue (matches reference)
    STRAND = (220, 232, 255)
    RUNG   = (195, 212, 255)

    # ── Far-background helix (lower-left, most blurred) ───────────────────────
    far = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _draw_helix(ImageDraw.Draw(far),
                cx=140, cy=460, angle_deg=32, n_turns=3, length=680, amp=72,
                strand_col=STRAND, rung_col=RUNG,
                strand_w=8, rung_w=5, alpha=140, steps=700)
    far = far.filter(ImageFilter.GaussianBlur(radius=16))

    # ── Mid-background helix (upper-right, moderately blurred) ───────────────
    mid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _draw_helix(ImageDraw.Draw(mid),
                cx=980, cy=195, angle_deg=27, n_turns=3, length=600, amp=65,
                strand_col=STRAND, rung_col=RUNG,
                strand_w=9, rung_w=6, alpha=165, steps=700)
    mid = mid.filter(ImageFilter.GaussianBlur(radius=9))

    # ── Foreground helix (sharp, large, extends beyond frame like reference) ──
    fg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _draw_helix(ImageDraw.Draw(fg),
                cx=630, cy=385, angle_deg=35, n_turns=3, length=1080, amp=118,
                strand_col=STRAND, rung_col=RUNG,
                strand_w=16, rung_w=10, alpha=240, steps=900)
    # Soft glow behind the foreground helix: blur a dimmed copy, then overlay sharp
    fg_glow = fg.filter(ImageFilter.GaussianBlur(radius=8))
    fg_glow = fg_glow.point(lambda p: int(p * 0.55))
    fg = Image.alpha_composite(fg_glow, fg)

    # ── Antibodies & protein complexes in the empty corner areas ─────────────
    mol = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    md  = ImageDraw.Draw(mol)

    # Top-left corner (above and to the left of the helix start)
    _antibody(md,    cx=248, cy=148, scale=1.10, rotation= 18, color=STRAND, alpha=168)
    _antibody(md,    cx= 62, cy=270, scale=0.72, rotation=-12, color=STRAND, alpha=130)
    _protein_ring(md, cx=360, cy= 58, scale=0.80, rotation= 10, color=STRAND, alpha=140)

    # Bottom-right corner (below and to the right of the helix end)
    _antibody(md,    cx=1082, cy=572, scale=1.05, rotation=-20, color=STRAND, alpha=170)
    _protein_ring(md, cx=1210, cy=655, scale=0.88, rotation= 30, color=STRAND, alpha=145)
    _antibody(md,    cx=1240, cy=490, scale=0.68, rotation= 12, color=STRAND, alpha=120)

    # Soft glow behind the molecules, then sharp layer on top
    mol_glow = mol.filter(ImageFilter.GaussianBlur(radius=11))
    mol_glow  = mol_glow.point(lambda p: int(p * 0.50))
    mol_final = Image.alpha_composite(mol_glow, mol)

    # ── Composite: base + far + mid + fg + molecules ─────────────────────────
    result = base.convert("RGBA")
    result = Image.alpha_composite(result, far)
    result = Image.alpha_composite(result, mid)
    result = Image.alpha_composite(result, mol_final)   # molecules behind main helix
    result = Image.alpha_composite(result, fg)

    result.convert("RGB").save(str(BG_OUT), format="BMP")
    print(f"  background.bmp written ({W}x{H})")


# ── Sidebar (164 x 314) ───────────────────────────────────────────────────────

def build_sidebar() -> None:
    for src in (LOGO_SRC, OKAPI_SRC):
        if not src.exists():
            print(f"ERROR: {src} not found.")
            sys.exit(1)

    canvas = vertical_gradient(SIDEBAR_W, SIDEBAR_H, PURPLE_TOP, WHITE_BOT)
    draw   = ImageDraw.Draw(canvas)

    dot_y, dot_r = 11, 2
    for offset in (-10, 0, 10):
        cx = SIDEBAR_W // 2 + offset
        draw.ellipse([cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r],
                     fill=WHITE)

    okapi = fit_image(Image.open(OKAPI_SRC), 145, 145)
    paste_centered(canvas, okapi, y_offset=-20)

    logo = remove_white_bg(Image.open(LOGO_SRC))
    logo.thumbnail((SIDEBAR_W - 24, 44), Image.LANCZOS)
    lx = (SIDEBAR_W - logo.width) // 2
    ly = SIDEBAR_H - logo.height - 14
    canvas.paste(logo, (lx, ly), logo)

    canvas.convert("RGB").save(str(SIDEBAR_OUT), format="BMP")
    print(f"  sidebar.bmp  written ({SIDEBAR_W}x{SIDEBAR_H})")


# ── Header (150 x 57) ─────────────────────────────────────────────────────────

def build_header() -> None:
    if not ICON_SRC.exists():
        print(f"ERROR: {ICON_SRC} not found.")
        sys.exit(1)

    canvas = horizontal_gradient(HEADER_W, HEADER_H, HEADER_LEFT, WHITE)
    draw   = ImageDraw.Draw(canvas)
    draw.rectangle([0, HEADER_H - 2, HEADER_W - 1, HEADER_H - 1], fill=ACCENT)

    icon = fit_image(Image.open(ICON_SRC), HEADER_W - 4, HEADER_H - 6)
    ix   = (HEADER_W  - icon.width)  // 2
    iy   = (HEADER_H  - icon.height) // 2 - 1
    canvas.paste(icon, (ix, iy), icon)

    canvas.convert("RGB").save(str(HEADER_OUT), format="BMP")
    print(f"  header.bmp   written ({HEADER_W}x{HEADER_H})")


# ── Page background (432 x 314) ──────────────────────────────────────────────

def build_page_bg() -> None:
    """
    Resize background.bmp to the NSIS inner-dialog dimensions and save as
    page_bg.bmp.  This file is loaded at native size in setup.nsi so that
    LoadImageW never needs to scale a large source bitmap — which is
    unreliable on some Windows / NSIS-plugin combinations.

    Aspect-ratio note: background.bmp is 16:9 (1280×720); page_bg.bmp is
    432×314 (~1.38:1).  A centre-crop is used to avoid distortion: we crop
    the widest rectangle from the source that matches the target ratio before
    down-sampling with LANCZOS.
    """
    bg = Image.open(str(BG_OUT)).convert("RGB")
    src_w, src_h = bg.size
    target_ar = PAGE_BG_W / PAGE_BG_H

    # Centre-crop to target aspect ratio
    crop_w = int(src_h * target_ar)
    crop_h = src_h
    if crop_w > src_w:           # source is taller than target AR — crop height
        crop_h = int(src_w / target_ar)
        crop_w = src_w
    left = (src_w - crop_w) // 2
    top  = (src_h - crop_h) // 2
    bg   = bg.crop((left, top, left + crop_w, top + crop_h))

    bg = bg.resize((PAGE_BG_W, PAGE_BG_H), Image.LANCZOS)
    bg.save(str(PAGE_BG_OUT), format="BMP")
    print(f"  page_bg.bmp  written ({PAGE_BG_W}x{PAGE_BG_H})")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Building NSIS installer bitmaps...")
    build_background()
    build_page_bg()   # must run after build_background() — reads BG_OUT
    build_sidebar()
    build_header()
    print("Done. Recompile: makensis /DAPP_VERSION=x.x.x /DAUTH_BASE_URL=https://... setup.nsi")
