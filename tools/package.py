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
    # Stamp the onedir root with VERSION.txt (vX.Y.Z). It ships inside the
    # installer AND every in-app update bundle, so $INSTDIR\VERSION.txt always
    # reflects the running build — the uninstaller reads it instead of a
    # compile-time constant that goes stale after a binary-swap update.
    _write_version_file(out)
    _bundle_extra_files(out)
    print(f"==> Done. Frozen bundle at: {out}")
    return out


def _bundle_extra_files(bundle_root):
    """Copy installer-managed helpers into the onedir root.

    These ship beside EasyOKAPI.exe so they are laid down by the installer AND
    carried by every in-app update bundle (the binary swap moves the whole onedir):
      - launcher-frozen.ps1: the splash-screen launcher the shortcuts run.
    """
    import shutil
    extras = [os.path.join(ROOT, 'installer-win', 'launcher-frozen.ps1')]
    for src in extras:
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(bundle_root, os.path.basename(src)))
            print(f"==> Bundled {os.path.basename(src)}")


def _write_version_file(bundle_root):
    """Write VERSION.txt (vX.Y.Z) at the onedir root, from src/state.APP_VERSION."""
    import re
    version = '0.0.0'
    try:
        with open(os.path.join(ROOT, 'src', 'state.py'), encoding='utf-8') as f:
            m = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', f.read(), re.M)
        if m:
            version = m.group(1).lstrip('v')
    except Exception:
        pass
    # No trailing newline: the NSIS uninstaller FileReads this verbatim into the
    # displayed version, so a clean single token avoids newline-trimming there.
    with open(os.path.join(bundle_root, 'VERSION.txt'), 'w', encoding='utf-8') as f:
        f.write(f'v{version}')
    print(f"==> Stamped VERSION.txt = v{version}")


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
