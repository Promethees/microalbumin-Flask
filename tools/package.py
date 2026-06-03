#!/usr/bin/env python3
"""Build the distributable EasyOKAPI artifact.

Behaviour is gated by the build-time flag ``ENCODE_SOURCE`` (read from ``.env`` or
the environment), so the same command serves both shipping modes:

    ENCODE_SOURCE=true   → freeze a no-source PyInstaller onedir bundle
                           (dist/EasyOKAPI/ — no .py on the user's machine)
    ENCODE_SOURCE=false  → produce a plain source tarball (legacy/dev flow)

Usage:
    python tools/package.py            # honour ENCODE_SOURCE (default: true)
    python tools/package.py --source   # force source tarball
    python tools/package.py --encode   # force frozen binary

The freezer choice lives behind one function so a future Nuitka backend can drop in
without touching installers or the updater.
"""

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, 'easyokapi.spec')
DIST = os.path.join(ROOT, 'dist')


def _load_env_file():
    """Populate os.environ from .env without clobbering existing values."""
    env_path = os.path.join(ROOT, '.env')
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _truthy(val):
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on')


def build_encoded():
    """Freeze the app into a no-source onedir bundle via PyInstaller."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("PyInstaller is not installed. Run: pip install -r requirements-build.txt")

    # static/vendor/ (jQuery, Chart.js, MathJax, …) is git-ignored and normally
    # fetched by the installer at runtime. A frozen build bundles static/ into the
    # binary, so the assets must exist *before* PyInstaller runs or the packaged UI
    # ships without its JS/fonts. Populate them first (idempotent).
    print("==> Ensuring front-end vendor libraries are present…")
    import fetch_vendor
    fetch_vendor.ensure_vendor()

    print("==> Building frozen no-source bundle (PyInstaller onedir)…")
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', SPEC]
    subprocess.run(cmd, cwd=ROOT, check=True)
    out = os.path.join(DIST, 'EasyOKAPI')
    print(f"==> Done. Frozen bundle at: {out}")
    return out


def build_source():
    """Produce a plain source tarball (the legacy 'download .py' artifact)."""
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, 'easyokapi-src.tar.gz')
    print("==> Building source tarball (ENCODE_SOURCE=false)…")
    # git archive captures exactly the tracked files, mirroring the server tarball.
    subprocess.run(
        ['git', 'archive', '--format=tar.gz', '-o', out, 'HEAD'],
        cwd=ROOT, check=True,
    )
    print(f"==> Done. Source tarball at: {out}")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--encode', action='store_true', help='Force frozen binary build')
    group.add_argument('--source', action='store_true', help='Force source tarball build')
    args = parser.parse_args()

    _load_env_file()

    if args.encode:
        encode = True
    elif args.source:
        encode = False
    else:
        # Default to encoded unless explicitly disabled.
        encode = _truthy(os.environ.get('ENCODE_SOURCE', 'true'))

    if encode:
        build_encoded()
    else:
        build_source()


if __name__ == '__main__':
    main()
