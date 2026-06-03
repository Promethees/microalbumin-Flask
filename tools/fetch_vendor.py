#!/usr/bin/env python3
"""Download the front-end vendor libraries into static/vendor/.

These third-party assets (jQuery, Chart.js, SweetAlert2, numeric.js, MathJax +
its WOFF fonts) are referenced by templates/index.html as
``static/vendor/...`` but are git-ignored — the source installers fetch them at
install time. A frozen (no-source) build bundles ``static/`` into the binary, so
they must be present **before** PyInstaller runs or the packaged UI ships without
its JS/fonts. tools/package.py calls ensure_vendor() before freezing; this module
is also runnable standalone (``python tools/fetch_vendor.py``).

Idempotent: an already-present file is skipped, so re-runs are cheap and a
partially-populated vendor dir is completed rather than re-downloaded.

The URL set is kept in lockstep with installer-mac/setup.sh (and the Windows /
Linux installers); update all of them together.
"""

import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (url, destination filename under static/vendor/)
_VENDOR_FILES = [
    ('https://code.jquery.com/jquery-3.6.0.min.js', 'jquery-3.6.0.min.js'),
    ('https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js', 'chart.umd.min.js'),
    ('https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.0.0/dist/chartjs-plugin-annotation.min.js',
     'chartjs-plugin-annotation-2.0.0.min.js'),
    ('https://cdn.jsdelivr.net/npm/sweetalert2@11/dist/sweetalert2.all.min.js', 'sweetalert2.all.min.js'),
    ('https://cdnjs.cloudflare.com/ajax/libs/numeric/1.2.6/numeric.min.js', 'numeric-1.2.6.min.js'),
    ('https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js', 'mathjax-tex-mml-chtml.js'),
]

_MATHJAX_FONTS = [
    'MathJax_AMS-Regular', 'MathJax_Main-Regular', 'MathJax_Main-Bold', 'MathJax_Main-Italic',
    'MathJax_Math-Italic', 'MathJax_Math-BoldItalic', 'MathJax_Size1-Regular', 'MathJax_Size2-Regular',
    'MathJax_Size3-Regular', 'MathJax_Size4-Regular', 'MathJax_Calligraphic-Regular',
    'MathJax_Calligraphic-Bold', 'MathJax_Fraktur-Regular', 'MathJax_Fraktur-Bold',
    'MathJax_SansSerif-Regular', 'MathJax_SansSerif-Bold', 'MathJax_SansSerif-Italic',
    'MathJax_Script-Regular', 'MathJax_Typewriter-Regular', 'MathJax_Vector-Regular',
    'MathJax_Vector-Bold', 'MathJax_Zero',
]
_FONT_URL = 'https://cdn.jsdelivr.net/npm/mathjax@3/es5/output/chtml/fonts/woff-v2/{}.woff'


def _download(url, dest):
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return False  # already present
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + '.part'
    with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, 'wb') as f:
        f.write(resp.read())
    os.replace(tmp, dest)
    return True


def ensure_vendor(static_dir=None):
    """Download any missing vendor assets into <static_dir>/vendor/.

    Returns the number of files newly downloaded. Raises on a failed download so a
    frozen build never silently ships an incomplete UI.
    """
    static_dir = static_dir or os.path.join(ROOT, 'static')
    vendor = os.path.join(static_dir, 'vendor')
    fonts = os.path.join(vendor, 'mathjax-fonts')

    fetched = 0
    for url, name in _VENDOR_FILES:
        if _download(url, os.path.join(vendor, name)):
            fetched += 1
            print(f'  fetched {name}')
    for font in _MATHJAX_FONTS:
        if _download(_FONT_URL.format(font), os.path.join(fonts, f'{font}.woff')):
            fetched += 1
    print(f'==> Vendor libraries ready ({fetched} downloaded, '
          f'{len(_VENDOR_FILES) + len(_MATHJAX_FONTS) - fetched} already present).')
    return fetched


if __name__ == '__main__':
    try:
        ensure_vendor()
    except Exception as e:
        sys.exit(f'Vendor download failed: {e}')
