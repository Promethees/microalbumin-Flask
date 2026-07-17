#!/bin/bash
# migrate-frozen.sh — one-time migration from an old source-based install.
#
# The source build kept its user data (data/ json/ report/ log/ + settings) beside
# the code, at /Applications/EasyOKAPI/code (v1.2.19+) or, before the install-path
# rename, at /Applications/microalbumin-Flask. The frozen build keeps
# user data in a VISIBLE per-user folder (~/Documents/EasyOKAPI, matching
# src/state.py) so on first frozen launch we copy that data across and then
# remove the old install (per the migration decision in ENCODE_BUILD_PLAN.md
# §11.5). The app itself also migrates any earlier hidden app-data dir
# (~/Library/Application Support/EasyOKAPI) into this folder. Idempotent via a
# marker file and best-effort throughout: a failure here must never block launch.

# Data dir first, then the install root to delete once its data is safe. Note
# /Applications/EasyOKAPI (the source install's folder) is NOT the same path as
# /Applications/EasyOKAPI.app (this frozen build), so removing it is safe.
OLD_CODE="/Applications/EasyOKAPI/code"
OLD_ROOT="/Applications/EasyOKAPI"
if [ ! -d "$OLD_CODE" ]; then
    OLD_CODE="/Applications/microalbumin-Flask"
    OLD_ROOT="$OLD_CODE"
fi
APPDATA="$HOME/Documents/EasyOKAPI"
MARKER="$APPDATA/.migrated_from_source"

[ -f "$MARKER" ] && exit 0
mkdir -p "$APPDATA"

if [ -d "$OLD_CODE" ]; then
    for d in data json report log; do
        if [ -d "$OLD_CODE/$d" ]; then
            mkdir -p "$APPDATA/$d"
            # -n: never overwrite anything the frozen app already created/seeded.
            cp -Rn "$OLD_CODE/$d/." "$APPDATA/$d/" 2>/dev/null || true
        fi
    done
    for f in activation.json user_settings.json ai_settings.json .env; do
        if [ -f "$OLD_CODE/$f" ] && [ ! -f "$APPDATA/$f" ]; then
            cp "$OLD_CODE/$f" "$APPDATA/$f" 2>/dev/null || true
        fi
    done
    # Replace the old source install (reclaims its venv/pyenv footprint). The
    # user owns this dir (chowned at source-install time), so no sudo is needed.
    rm -rf "$OLD_ROOT" 2>/dev/null || true
fi

touch "$MARKER"
exit 0
