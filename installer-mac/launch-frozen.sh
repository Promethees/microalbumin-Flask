#!/bin/bash
# launch-frozen.sh — launcher for the no-source (PyInstaller) macOS build.
#
# Unlike launch.sh (the source build), this needs no sudo, pyenv, or venv: the
# frozen binary embeds the Python runtime and all dependencies, and creates its
# own writable per-user data folders in a visible ~/Documents/EasyOKAPI folder
# on first run. It only migrates data from an older source install, then execs
# the bundled binary.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$SCRIPT_DIR/EasyOKAPI/EasyOKAPI"

# One-time migration from a previous source-based install (best-effort; never
# blocks launch).
if [ -f "$SCRIPT_DIR/migrate-frozen.sh" ]; then
    bash "$SCRIPT_DIR/migrate-frozen.sh" 2>/dev/null || true
fi

if [ ! -x "$BIN" ]; then
    osascript -e 'display dialog "EasyOKAPI application binary not found. Please reinstall from the DMG." buttons {"OK"} default button "OK" with title "EasyOKAPI"'
    exit 1
fi

# Loopback alias avoids editing /etc/hosts (which would need sudo). The binary
# opens the default browser itself.
exec "$BIN" --port 5099 --alias 127.0.0.1
