# Organisation logos — `static/logos/`

Marks for the organisation row on the landing page. Listed in
`organizations.json`, read by `get_organizations()` in `src/community.py`,
rendered by the `.trusted` section of `templates/landing.html`.

## How they are drawn

They are **not** drawn as images. Each mark is a CSS `mask-image`, and the
colour comes from the page:

```css
.org-mark {
    background-color: var(--ink-3);   /* the page's muted ink, dark-theme aware */
    mask-image: var(--mark);          /* the file below */
    mask-size: contain;
}
```

Only the file's **alpha channel** is used. Every visible pixel becomes one flat
ink, so a row of institutions reads as one system instead of a row of clashing
brand palettes, and it re-tints itself in dark mode with no second asset. The
file is never recoloured on disk.

## What a usable file looks like

| Requirement | Why |
|---|---|
| **Transparent background** | The alpha channel *is* the artwork. A white or coloured background renders as a solid ink rectangle. |
| Square-ish, at least 256×256 (PNG) or any size (SVG) | Rendered at 40px, 32px on phones. Retina wants the headroom. |
| Solid, opaque shape | Anti-aliased edges are fine. Soft drop shadows and gradients become muddy grey haze. |
| Full lockup is fine | The mark is shown **alone** when a logo exists — the organisation's name goes to screen readers only, because institutional logos almost always carry their own wordmark and a visible label beside one prints the name twice. |
| SVG or PNG | Both work. SVG is preferred — it masks crisply at any size, and internal `fill` colours are irrelevant since only alpha is read. |
| Real extension | `.png` must actually be a PNG. A WebP renamed to `.png` is served as `image/png`, and lossy WebP carries no alpha at all, so it masks as a solid ink rectangle. |

The mark is drawn 62px tall (46px on phones), and its **width follows the file's
own aspect ratio** — `_logo_aspect()` in `src/community.py` reads the PNG `IHDR`
or the SVG `viewBox` and passes it to CSS as `--ratio`. A masked span has no
intrinsic size, so without this a tall emblem and a wide lockup would be forced
into the same box. Nothing to configure; it is read from the file.

Emblems with circular text need that height to stay legible. A plain wide
wordmark would survive at 40px; a university seal will not.

A multi-colour logo is fine as a source: colour is discarded. A logo that is
*defined* by its colours (say, two tones of equal darkness that separate only by
hue) will flatten into an unreadable blob — crop or simplify it first.

## Adding one

1. Drop the file here, e.g. `hcmus.png`.
2. Add an entry to `organizations.json`:

   ```json
   {
     "name": "Full institution name, used as the link title",
     "short": "What prints beside the mark",
     "logo": "logos/hcmus.png",
     "url": "https://example.edu"
   }
   ```

3. That is all — the row is a centred flex line that wraps, so the number of
   entries does not need any layout change.

**A missing file is safe.** `get_organizations()` checks that the path resolves
to a real file under `static/` and blanks it otherwise, so a typo or a
not-yet-added logo degrades to the wordmark rather than rendering an empty box.
That is deliberate: a `mask-image` that fails to load behaves differently across
engines — a solid coloured rectangle in some, nothing at all in others.

## Before you add someone else's logo

Using an institution's mark under a "developed and used at" heading is an
endorsement claim. Get written permission from anyone outside HCMUS–VNU before their logo
ships, and keep the note with the entry. Some institutions also publish brand
guidelines that restrict recolouring — which is exactly what this section does.

## Currently expected

| File | Organisation | State |
|---|---|---|
| `hcmus.png` | University of Science, VNU-HCM | ✓ 384×384 grey+alpha |
| `ais.png` | Australian International School | ✓ 500×549 RGBA, as supplied |

`hcmus.png` was **derived, not supplied as-is**: the original file was a lossy
WebP with a `.png` extension and no alpha channel, which masks as a solid
rectangle. Alpha was keyed from luminance (the mark is dark navy on a light
ground), then the result was stored at 384px as greyscale+alpha — colour
channels are dead weight when only alpha is read. If a vector or genuinely
transparent original ever turns up, replace it; the derived edges are one
generation down from the source.

Until a file lands, that organisation shows as a wordmark instead. The section
renders and is live either way.
