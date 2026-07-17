#!/bin/bash
# uninstall.sh — removes EasyOKAPI, for BOTH the source install (install.sh) and
# the no-source frozen install (install-frozen.sh). Both live at /opt/EasyOKAPI.
#
# The frozen installer copies this script into the install dir, so it is also the
# uninstaller a frozen user runs:  sudo /opt/EasyOKAPI/uninstall.sh
#
# User data differs between the two: a source install kept data/ json/ report/
# inside $INSTALL_DIR (archived below), while a frozen install keeps them in the
# visible ~/EasyOKAPI data root, which is deliberately left untouched here.

exec > >(tee -a /tmp/easyokapi-uninstall.log) 2>&1
echo "Starting EasyOKAPI uninstall at $(date)"

if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (sudo)."
    exit 1
fi

CURRENT_USER="${SUDO_USER:-}"
CURRENT_HOME=$(eval echo "~$CURRENT_USER")
INSTALL_DIR="/opt/EasyOKAPI"
# Two rules exist in the wild: the source install adds the HID one, the frozen
# install the CDC one (see install.sh / install-frozen.sh). Remove whichever is
# present so an uninstall never orphans a udev rule.
UDEV_RULES=(
    "/etc/udev/rules.d/99-easyokapi-hid.rules"
    "/etc/udev/rules.d/99-easyokapi-cdc.rules"
)
DESKTOP_ENTRY="/usr/share/applications/EasyOKAPI.desktop"

# The frozen installer puts this script INSIDE the directory it is about to
# delete. bash reads a script lazily, so removing it mid-run can truncate
# execution — copy to /tmp and re-exec from there first. The copy's $0 is outside
# $INSTALL_DIR, so this fires at most once. (Mirrors installer-mac/uninstall.command.)
case "$(cd "$(dirname "$0")" && pwd)" in
    "$INSTALL_DIR"|"$INSTALL_DIR"/*)
        _SELF_TMP="/tmp/easyokapi-uninstall-$$.sh"
        cp "$0" "$_SELF_TMP" && chmod +x "$_SELF_TMP" && exec bash "$_SELF_TMP" "$@"
        ;;
esac

# ── Helper: confirm ───────────────────────────────────────────────────────────
prompt_confirm() {
    local title="$1" msg="$2"
    if command -v zenity &>/dev/null; then
        zenity --question --title="$title" --text="$msg" 2>/dev/null
        return $?
    elif command -v whiptail &>/dev/null; then
        whiptail --yesno "$msg" 10 60 --title "$title" 3>&1 1>&2 2>&3
        return $?
    else
        read -rp "$msg [y/N]: " _ans
        [[ "$_ans" =~ ^[Yy]$ ]]
        return $?
    fi
}

# ── Release this machine's license seat ───────────────────────────────────────
# A license is activated on a limited number of machines, and a seat stays taken
# until it is released. Deleting the software does not free it, so a user who
# uninstalls and moves to a new machine would be refused — the cap is held by a
# machine that no longer exists. Hand the seat back before removing anything.
#
# Python is not usable here (it is part of what we are deleting), so this is a
# plain HTTP call. The stored activation token is the credential and names its own
# seat, so no hardware fingerprint has to be recomputed in shell.
#
# Strictly best-effort: no network, no token, or a server that says no (a revoked
# or banned license may not be released) never blocks the uninstall.
AI_SERVICE_URL="${AI_SERVICE_URL:-https://www.easyokapi.cbbiotec.vn}"

_read_license_token() {  # $1 = directory that may hold activation.json
    [ -f "$1/activation.json" ] || return 1
    local tok
    tok=$(grep -o '"license_token"[[:space:]]*:[[:space:]]*"[^"]*"' "$1/activation.json" \
          | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
    [ -n "$tok" ] && printf '%s' "$tok"
}

_release_license_seat() {
    # The data root is ~/EasyOKAPI unless the user relocated it, in which case a
    # pointer file beside the default location holds the real path (the pointer
    # lives outside the data folder precisely so it survives this).
    local pointer="$CURRENT_HOME/.easyokapi_dataroot"
    local data_root="$CURRENT_HOME/EasyOKAPI"
    if [ -f "$pointer" ]; then
        local moved
        moved=$(tr -d ' \t\r\n' < "$pointer" 2>/dev/null)
        [ -n "$moved" ] && data_root="$moved"
    fi

    # A frozen install keeps activation.json in the data root; a source install
    # keeps it in the install directory (there, script_dir IS the project root).
    local token=""
    local _d
    for _d in "$data_root" "$INSTALL_DIR"; do
        token=$(_read_license_token "$_d") && [ -n "$token" ] && break
        token=""
    done
    if [ -z "$token" ]; then
        echo "No license token found — nothing to deactivate."
        return 0
    fi

    echo "Deactivating this machine's license..."
    local body
    body=$(curl -fsS -m 15 -X POST \
                -H 'Content-Type: application/json' \
                -d "{\"license_token\":\"$token\"}" \
                "$AI_SERVICE_URL/api/license/release" 2>/dev/null)
    case "$body" in
        *'"status":"success"'*|*'"status": "success"'*)
            echo "✅ License seat released — you can activate EasyOKAPI on another machine."
            ;;
        "")
            echo "⚠️  Could not reach the license server; this machine still holds its seat."
            echo "    Sign in at $AI_SERVICE_URL and deactivate this machine from your account to free it."
            ;;
        *)
            echo "⚠️  License server declined the deactivation: $body"
            ;;
    esac
}

_release_license_seat

# ── Data-archive layout helper ────────────────────────────────────────────────
# Keep the archived data/ tree purely subfolder-based: loose files sitting
# directly in the data root are stashed under data/root/ (the app forbids a real
# 'root' subfolder so there is no collision). The reinstall dissolves it back.
_archive_stash_root() {  # $1 = path to a data/ directory
    [ -d "$1" ] || return 0
    if [ -n "$(find "$1" -maxdepth 1 -type f -print -quit 2>/dev/null)" ]; then
        mkdir -p "$1/root"
        find "$1" -maxdepth 1 -type f -exec mv -f {} "$1/root/" \;
    fi
}

# ── Preserve user data before removing application directory ──────────────────
if [ -d "$INSTALL_DIR" ]; then
    USER_DATA_DEST="$CURRENT_HOME/EasyOKAPI_data"
    DATA_SAVED=0
    for _dir in data json report; do
        if [ -d "$INSTALL_DIR/$_dir" ]; then
            mkdir -p "$USER_DATA_DEST"
            cp -r "$INSTALL_DIR/$_dir" "$USER_DATA_DEST/$_dir"
            chown -R "$CURRENT_USER:$CURRENT_USER" "$USER_DATA_DEST"
            DATA_SAVED=1
        fi
    done
    _archive_stash_root "$USER_DATA_DEST/data"
    chown -R "$CURRENT_USER:$CURRENT_USER" "$USER_DATA_DEST" 2>/dev/null
    if [ "$DATA_SAVED" -eq 1 ]; then
        echo "✅ User data (data/, json/, report/) preserved at $USER_DATA_DEST"
    fi
fi

# ── Remove application directory ──────────────────────────────────────────────
if [ -d "$INSTALL_DIR" ]; then
    echo "Removing $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to remove $INSTALL_DIR."
        exit 1
    fi
    echo "✅ Application directory removed."
else
    echo "Application directory $INSTALL_DIR not found — skipping."
fi

# ── Remove udev rules ─────────────────────────────────────────────────────────
_udev_removed=0
for _rule in "${UDEV_RULES[@]}"; do
    if [ -f "$_rule" ]; then
        rm -f "$_rule"
        echo "✅ udev rule removed: $_rule"
        _udev_removed=1
    fi
done
if [ "$_udev_removed" -eq 1 ]; then
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger 2>/dev/null || true
fi

# ── Remove desktop entry ──────────────────────────────────────────────────────
if [ -f "$DESKTOP_ENTRY" ]; then
    rm -f "$DESKTOP_ENTRY"
    update-desktop-database /usr/share/applications/ 2>/dev/null || true
    echo "✅ Desktop entry removed."
fi

# ── Optionally remove Python 3.8.10 from pyenv ───────────────────────────────
PYENV_ROOT="$CURRENT_HOME/.pyenv"
PYENV_BIN="$PYENV_ROOT/bin/pyenv"
if [ -x "$PYENV_BIN" ] && su - "$CURRENT_USER" -c "$PYENV_BIN versions 2>/dev/null | grep -q 3.8.10"; then
    if prompt_confirm "EasyOKAPI Uninstall" "Remove Python 3.8.10 from pyenv?"; then
        su - "$CURRENT_USER" -c "$PYENV_BIN uninstall -f 3.8.10"
        echo "✅ Python 3.8.10 removed from pyenv."
    fi
fi

echo ""
echo "✅ EasyOKAPI has been uninstalled."
echo "Uninstall script completed at $(date)"
exit 0
