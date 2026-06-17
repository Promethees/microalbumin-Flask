#!/bin/bash
# migrate-frozen.sh — one-time migration from an old source-based install.
#
# The source build lived at /Applications/microalbumin-Flask with its user data
# (data/ json/ report/ log/ + settings) beside the code. The frozen build keeps
# user data in a VISIBLE per-user folder (~/Documents/EasyOKAPI, matching
# src/state.py) so on first frozen launch we copy that data across and then
# remove the old install (per the migration decision in ENCODE_BUILD_PLAN.md
# §11.5). The app itself also migrates any earlier hidden app-data dir
# (~/Library/Application Support/EasyOKAPI) into this folder. Idempotent via a
# marker file and best-effort throughout: a failure here must never block launch.

OLD="/Applications/microalbumin-Flask"
APPDATA="$HOME/Documents/EasyOKAPI"
MARKER="$APPDATA/.migrated_from_source"

[ -f "$MARKER" ] && exit 0
mkdir -p "$APPDATA"

if [ -d "$OLD" ]; then
    for d in data json report log; do
        if [ -d "$OLD/$d" ]; then
            mkdir -p "$APPDATA/$d"
            # -n: never overwrite anything the frozen app already created/seeded.
            cp -Rn "$OLD/$d/." "$APPDATA/$d/" 2>/dev/null || true
        fi
    done
    for f in activation.json user_settings.json ai_settings.json .env; do
        if [ -f "$OLD/$f" ] && [ ! -f "$APPDATA/$f" ]; then
            cp "$OLD/$f" "$APPDATA/$f" 2>/dev/null || true
        fi
    done
    # Replace the old source install (reclaims its venv/pyenv footprint). The
    # user owns this dir (chowned at source-install time), so no sudo is needed.
    rm -rf "$OLD" 2>/dev/null || true
fi

touch "$MARKER"
exit 0
