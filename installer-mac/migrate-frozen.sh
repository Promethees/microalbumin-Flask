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
# DEFAULT_APPDATA is the canonical location src/state.py resolves to and where
# the .dataroot pointer always lives, even when the data is stored elsewhere.
DEFAULT_APPDATA="$HOME/Documents/EasyOKAPI"
POINTER="$DEFAULT_APPDATA/.dataroot"
SETUP_MARKER="$DEFAULT_APPDATA/.dataroot_setup_done"

# Resolve the active data folder: an existing pointer wins, else the default.
APPDATA="$DEFAULT_APPDATA"
if [ -f "$POINTER" ]; then
    P="$(cat "$POINTER" 2>/dev/null)"
    [ -n "$P" ] && APPDATA="$P"
fi

# First-run data-location chooser — shown once, only before anything is set up.
if [ ! -f "$SETUP_MARKER" ] && [ ! -f "$POINTER" ]; then
    CHOSEN="$(osascript -e 'try' \
        -e 'POSIX path of (choose folder with prompt "Choose where EasyOKAPI should store your measurements, calibration curves and reports. Cancel to use the default in your Documents folder.")' \
        -e 'end try' 2>/dev/null)"
    if [ -n "$CHOSEN" ]; then
        # `choose folder` returns the picked folder; keep our data in an
        # EasyOKAPI subfolder of it so we never litter the chosen location.
        APPDATA="${CHOSEN%/}/EasyOKAPI"
        mkdir -p "$DEFAULT_APPDATA"
        printf '%s' "$APPDATA" > "$POINTER"
    fi
    mkdir -p "$DEFAULT_APPDATA"
    touch "$SETUP_MARKER"
fi

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
