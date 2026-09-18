#!/bin/bash
# build-tarball-frozen.sh — package the PyInstaller onedir into a no-source Linux
# tarball. The tarball expands to an EasyOKAPI/ dir holding the frozen onedir
# (EasyOKAPI/EasyOKAPI/) plus the installer + runner; the user runs
# `sudo ./EasyOKAPI/install-frozen.sh`.
#
# Prereq: `python tools/package.py --encode` has produced dist/EasyOKAPI/.
# Env:    APP_VERSION (bare, e.g. 1.5.7).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
APP_NAME="EasyOKAPI"
DIST_BUNDLE="$PROJECT_ROOT/dist/EasyOKAPI"

if [ -z "${APP_VERSION:-}" ]; then
    echo "❌ APP_VERSION is not set."; exit 1
fi
if [ ! -d "$DIST_BUNDLE" ]; then
    echo "❌ Frozen bundle not found at $DIST_BUNDLE. Run: python tools/package.py --encode"; exit 1
fi
VERSION="v${APP_VERSION}"
TARBALL_NAME="${APP_NAME}_linux_${VERSION}.tar.gz"

echo "🚀 Building no-source Linux tarball for $APP_NAME ($VERSION)…"
cd "$PROJECT_ROOT"
rm -f "$TARBALL_NAME"

# ── Stage an EasyOKAPI/ payload dir ──────────────────────────────────────────
STAGE_PARENT="$(mktemp -d)"
STAGE="$STAGE_PARENT/EasyOKAPI"
mkdir -p "$STAGE"
cp -R "$DIST_BUNDLE" "$STAGE/EasyOKAPI"          # the frozen onedir
cp "$SCRIPT_DIR/install-frozen.sh" "$STAGE/"
cp "$SCRIPT_DIR/run-frozen.sh"     "$STAGE/"
cp "$SCRIPT_DIR/uninstall.sh"      "$STAGE/"   # installed to /opt/EasyOKAPI by install-frozen.sh
[ -f "$PROJECT_ROOT/static/okapi.png" ] && cp "$PROJECT_ROOT/static/okapi.png" "$STAGE/"

# Legal documents, at the top of the extracted tarball — install-frozen.sh runs
# unattended, so this is the only place the agreement can be read before the app
# starts. The app also serves both at /legal/<doc> (bundled via easyokapi.spec).
mkdir -p "$STAGE/legal"
cp "$PROJECT_ROOT/legal/EULA.txt"   "$STAGE/legal/"
cp "$PROJECT_ROOT/legal/PRIVACY.md" "$STAGE/legal/"
cp "$PROJECT_ROOT/LICENSE"          "$STAGE/legal/"
chmod +x "$STAGE/install-frozen.sh" "$STAGE/run-frozen.sh" "$STAGE/EasyOKAPI/EasyOKAPI"

echo "📦 Creating tarball: $TARBALL_NAME…"
tar -czf "$PROJECT_ROOT/$TARBALL_NAME" -C "$STAGE_PARENT" EasyOKAPI
rm -rf "$STAGE_PARENT"

echo "✅ $TARBALL_NAME created in $PROJECT_ROOT"
