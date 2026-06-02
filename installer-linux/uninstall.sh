#!/bin/bash

exec > >(tee -a /tmp/easyokapi-uninstall.log) 2>&1
echo "Starting EasyOKAPI uninstall at $(date)"

if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (sudo)."
    exit 1
fi

CURRENT_USER="${SUDO_USER:-}"
CURRENT_HOME=$(eval echo "~$CURRENT_USER")
INSTALL_DIR="/opt/EasyOKAPI"
UDEV_RULE="/etc/udev/rules.d/99-easyokapi-hid.rules"
DESKTOP_ENTRY="/usr/share/applications/EasyOKAPI.desktop"

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

# ── Remove udev rule ──────────────────────────────────────────────────────────
if [ -f "$UDEV_RULE" ]; then
    rm -f "$UDEV_RULE"
    udevadm control --reload-rules
    udevadm trigger
    echo "✅ udev rule removed."
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
