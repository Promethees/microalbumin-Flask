#!/bin/bash
# setup.sh — EasyOKAPI first-run installer
# Called by EasyOKAPI.app on first launch:
#   sudo bash <app>/Contents/Resources/setup.sh <access_token>
# Merges install-tools-clone-repo.command + install-venv.command into one step.

exec > >(tee -a /tmp/easyokapi-setup.log) 2>&1
echo "EasyOKAPI setup started at $(date)"

# ── Helpers ───────────────────────────────────────────────────────────────────
RESET="\033[0m"; BOLD="\033[1m"; GREEN="\033[32m"; CYAN="\033[36m"; RED="\033[31m"
print_step() { echo -e "\n  ${BOLD}${CYAN}▶  $1${RESET}"; }
print_ok()   { echo -e "  ${GREEN}✔  $1${RESET}"; }
print_fail() { echo -e "  ${RED}✗  $1${RESET}"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OKAPI_ICON="$SCRIPT_DIR/okapi.png"
_icon() { [ -f "$OKAPI_ICON" ] && echo "with icon POSIX file \"$OKAPI_ICON\"" || echo "with icon note"; }

# ── Validate args and privileges ──────────────────────────────────────────────
ACCESS_TOKEN="$1"
if [ -z "$ACCESS_TOKEN" ]; then
    print_fail "No access token provided."
    osascript -e "display dialog \"No access token received. Please launch EasyOKAPI and try again.\" buttons {\"OK\"} with title \"EasyOKAPI Setup\" $(_icon)"
    exit 1
fi
if [ "$EUID" -ne 0 ]; then
    print_fail "Must be run with sudo."
    exit 1
fi

CURRENT_USER=$(stat -f '%Su' /dev/console 2>/dev/null)
[ -z "$CURRENT_USER" ] && CURRENT_USER="$SUDO_USER"

# Substituted by CI/CD at build time:
AUTH_BASE_URL="__AUTH_BASE_URL__"
VERSION_TAG="__APP_VERSION__"

HOMEBREW_PREFIX="/Users/$CURRENT_USER/homebrew"
REPO_NAME="microalbumin-Flask"
INSTALL_DIR="/Applications/$REPO_NAME"

# ── Banner ────────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "  ${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${CYAN}║  ⬡  HTBiotec · EasyOKAPI · First-run Setup║${RESET}"
echo -e "  ${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── Step 1 / 5 : Homebrew ─────────────────────────────────────────────────────
print_step "1 / 5  Homebrew"
if ! command -v "$HOMEBREW_PREFIX/bin/brew" &>/dev/null; then
    echo "  Installing Homebrew to $HOMEBREW_PREFIX …"
    mkdir -p "$HOMEBREW_PREFIX"
    chmod u+rwx "$HOMEBREW_PREFIX"
    curl -fsSL https://github.com/Homebrew/brew/tarball/master \
        | tar -xzf - -C "$HOMEBREW_PREFIX" --strip-components 1
    if [ $? -ne 0 ]; then
        print_fail "Homebrew download failed."
        osascript -e "display dialog \"Homebrew installation failed. Check your internet connection and try again.\" buttons {\"OK\"} with title \"EasyOKAPI Setup\" $(_icon)"
        exit 1
    fi
    chown -R "$CURRENT_USER:staff" "$HOMEBREW_PREFIX"
    chmod -R u+rwx "$HOMEBREW_PREFIX"
    eval "$($HOMEBREW_PREFIX/bin/brew shellenv)"
    su - "$CURRENT_USER" -c "$HOMEBREW_PREFIX/bin/brew update" 2>/dev/null
fi
print_ok "Homebrew ready."

# ── Step 2 / 5 : Git & pyenv ──────────────────────────────────────────────────
print_step "2 / 5  Git & pyenv"
if ! command -v git &>/dev/null; then
    echo "  Installing Git …"
    su - "$CURRENT_USER" -c "$HOMEBREW_PREFIX/bin/brew install git"
    [ $? -ne 0 ] && { print_fail "Git install failed."; exit 1; }
fi
if ! command -v pyenv &>/dev/null && [ ! -f "$HOMEBREW_PREFIX/bin/pyenv" ]; then
    echo "  Installing pyenv …"
    su - "$CURRENT_USER" -c "$HOMEBREW_PREFIX/bin/brew install pyenv"
    [ $? -ne 0 ] && { print_fail "pyenv install failed."; exit 1; }
fi
eval "$(pyenv init --path)" 2>/dev/null
eval "$(pyenv init -)"      2>/dev/null
print_ok "Git and pyenv ready."

# ── Step 3 / 5 : Python 3.8.10 ───────────────────────────────────────────────
print_step "3 / 5  Python 3.8.10  (this may take 3–5 minutes)"
if ! pyenv versions 2>/dev/null | grep -q "3.8.10"; then
    echo "  Building Python 3.8.10 via pyenv …"
    export CFLAGS="-I$(xcrun --show-sdk-path)/usr/include"
    export LDFLAGS="-L$(xcrun --show-sdk-path)/usr/lib"
    su - "$CURRENT_USER" -c 'eval "$(pyenv init --path)"; pyenv install 3.8.10'
    if [ $? -ne 0 ]; then
        print_fail "Python 3.8.10 install failed."
        osascript -e "display dialog \"Python 3.8.10 could not be built. Check the log at /tmp/easyokapi-setup.log for details.\" buttons {\"OK\"} with title \"EasyOKAPI Setup\" $(_icon)"
        exit 1
    fi
fi
print_ok "Python 3.8.10 ready."

# ── Step 4 / 5 : Download application ────────────────────────────────────────
print_step "4 / 5  Downloading EasyOKAPI"

# ── Data-archive layout helpers ───────────────────────────────────────────────
# The persistent backup keeps the data/ tree purely subfolder-based: loose files
# at the data root are stashed under data/root/ (the app forbids a real 'root'
# subfolder so there is no collision). On restore the staging folder is dissolved
# back into the data root.
_archive_stash_root() {  # $1 = path to a data/ directory
    [ -d "$1" ] || return 0
    if [ -n "$(find "$1" -maxdepth 1 -type f -print -quit 2>/dev/null)" ]; then
        mkdir -p "$1/root"
        find "$1" -maxdepth 1 -type f -exec mv -f {} "$1/root/" \;
    fi
}
_archive_unstash_root() {  # $1 = path to a data/ directory
    [ -d "$1/root" ] || return 0
    find "$1/root" -mindepth 1 -maxdepth 1 -exec mv -f {} "$1/" \;
    rmdir "$1/root" 2>/dev/null || rm -rf "$1/root"
}

# Back up user data if reinstalling
BACKUP_DIR=""
if [ -d "$INSTALL_DIR" ] && [ "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    CURRENT_VERSION="Unknown"
    [ -f "$INSTALL_DIR/VERSION.txt" ] && CURRENT_VERSION=$(cat "$INSTALL_DIR/VERSION.txt")
    CHOICE=$(osascript \
        -e "Tell application \"System Events\" to display dialog \"An existing installation was found (version $CURRENT_VERSION).\n\nOverwrite and reinstall?\" buttons {\"Cancel\", \"Reinstall\"} default button \"Cancel\" with title \"EasyOKAPI Setup\" $(_icon)" \
        -e 'button returned of result' 2>/dev/null)
    if [ "$CHOICE" != "Reinstall" ]; then
        echo "  Reinstall cancelled — keeping existing installation."
        exit 0
    fi
    echo "  Backing up user data (data/, json/, report/) …"
    # Persistent backup folder (also written by uninstall.command and offered
    # for import at the end of this installer). Cleared first so it only holds
    # the most recent installation's data.
    BACKUP_DIR="/Users/$CURRENT_USER/EasyOKAPI_data"
    rm -rf "$BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    for d in data json report; do
        [ -d "$INSTALL_DIR/$d" ] && cp -r "$INSTALL_DIR/$d" "$BACKUP_DIR/$d"
    done
    _archive_stash_root "$BACKUP_DIR/data"
    chown -R "$CURRENT_USER:staff" "$BACKUP_DIR"
    echo "  Removing existing installation …"
    rm -rf "$INSTALL_DIR" || { print_fail "Could not remove existing install."; exit 1; }
fi

ARCHIVE_TMP="/tmp/easyokapi_app_$$.tar.gz"
echo "  Downloading application archive …"
curl -L --fail -o "$ARCHIVE_TMP" "$AUTH_BASE_URL/api/download?token=$ACCESS_TOKEN&version=$VERSION_TAG"
if [ $? -ne 0 ] || [ ! -s "$ARCHIVE_TMP" ]; then
    print_fail "Download failed."
    osascript -e "display dialog \"Download failed. Please check your access token and internet connection.\" buttons {\"OK\"} with title \"EasyOKAPI Setup\" $(_icon)"
    rm -f "$ARCHIVE_TMP"; exit 1
fi

echo "  Extracting …"
mkdir -p "$INSTALL_DIR"
tar -xzf "$ARCHIVE_TMP" -C "$INSTALL_DIR" --strip-components=1
if [ $? -ne 0 ]; then
    print_fail "Extraction failed."
    osascript -e "display dialog \"Failed to extract the application archive.\" buttons {\"OK\"} with title \"EasyOKAPI Setup\" $(_icon)"
    rm -f "$ARCHIVE_TMP"; exit 1
fi
rm -f "$ARCHIVE_TMP"
chown -R "$CURRENT_USER:staff" "$INSTALL_DIR"

echo "$VERSION_TAG" > "$INSTALL_DIR/VERSION.txt"
# Write activation.json. The access token doubles as the license token, but it is
# only valid for 30 minutes — persisting it raw means the AI proxy and in-app
# updates break (/api/download -> 401) once it expires. Exchange it now, while it
# is still fresh, for a permanent activation token (no expiry). Fall back to the
# raw token if the exchange fails; the app retries the exchange on startup.
LICENSE_TOKEN="$ACCESS_TOKEN"
if _resp=$(curl -fsS -X POST "$AUTH_BASE_URL/api/activate" \
        -H "Content-Type: application/json" \
        -d "{\"token\": \"$ACCESS_TOKEN\"}" 2>/dev/null); then
    _perm=$(printf '%s' "$_resp" | sed -n 's/.*"license_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    if [ -n "$_perm" ]; then LICENSE_TOKEN="$_perm"; fi
fi
printf '{\n  "license_token": "%s"\n}\n' "$LICENSE_TOKEN" > "$INSTALL_DIR/activation.json"
chown "$CURRENT_USER:staff" "$INSTALL_DIR/activation.json"

echo "  Cleaning development artefacts …"
rm -rf "$INSTALL_DIR/.git" "$INSTALL_DIR/.gitignore" 2>/dev/null
for d in tests .github installer-mac installer-win installer-linux; do
    [ -d "$INSTALL_DIR/$d" ] && rm -rf "$INSTALL_DIR/$d"
done
rm -f "$INSTALL_DIR"/*.bat \
      "$INSTALL_DIR/generate-tree.sh" \
      "$INSTALL_DIR/BUILD_MAC.md" \
      "$INSTALL_DIR/Rule.md" 2>/dev/null

# Restore user data
if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
    echo "  Restoring user data …"
    for d in data json report; do
        if [ -d "$BACKUP_DIR/$d" ]; then
            # Copy CONTENTS into the destination (src/.), not the folder itself —
            # "cp -r src dest" nests src INTO an existing dest, giving data/data.
            mkdir -p "$INSTALL_DIR/$d"
            cp -r "$BACKUP_DIR/$d/." "$INSTALL_DIR/$d/"
            chown -R "$CURRENT_USER:staff" "$INSTALL_DIR/$d"
        fi
    done
    _archive_unstash_root "$INSTALL_DIR/data"
    chown -R "$CURRENT_USER:staff" "$INSTALL_DIR/data" 2>/dev/null
    # Keep $BACKUP_DIR as a persistent safety backup rather than deleting it.
    print_ok "User data restored. A backup copy is kept at $BACKUP_DIR"
fi
print_ok "Application downloaded to $INSTALL_DIR."

# ── Step 5 / 5 : Python virtual environment ───────────────────────────────────
print_step "5 / 5  Python environment & dependencies"
cd "$INSTALL_DIR"

eval "$(pyenv init --path)" 2>/dev/null
eval "$(pyenv init -)"      2>/dev/null
pyenv global 3.8.10

PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
if [ "$PY_VER" != "3.8.10" ]; then
    print_fail "Python 3.8.10 expected but found $PY_VER."
    osascript -e "display dialog \"Python version mismatch ($PY_VER). Run setup again or check pyenv.\" buttons {\"OK\"} with title \"EasyOKAPI Setup\" $(_icon)"
    exit 1
fi

if [ ! -f "venv/bin/activate" ]; then
    echo "  Creating virtual environment …"
    rm -rf venv
    python3 -m venv venv
    [ ! -f "venv/bin/activate" ] && { print_fail "venv creation failed."; exit 1; }
fi
source venv/bin/activate

echo "  Upgrading pip …"
python3 -m ensurepip --upgrade -q
pip install --upgrade pip -q

echo "  Installing Python requirements …"
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    print_fail "pip install failed."
    osascript -e "display dialog \"Failed to install Python requirements. Check /tmp/easyokapi-setup.log for details.\" buttons {\"OK\"} with title \"EasyOKAPI Setup\" $(_icon)"
    exit 1
fi

echo "  Pre-compiling bytecode …"
python3 -m compileall -q \
    venv/lib/python3.8/site-packages/scipy \
    venv/lib/python3.8/site-packages/numpy 2>/dev/null || true

# Front-end vendor libraries
echo "  Downloading front-end vendor libraries …"
VENDOR_DIR="$INSTALL_DIR/static/vendor"
FONT_DIR="$VENDOR_DIR/mathjax-fonts"
mkdir -p "$FONT_DIR"

declare -a VENDOR_FILES=(
    "https://code.jquery.com/jquery-3.6.0.min.js|jquery-3.6.0.min.js"
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js|chart.umd.min.js"
    "https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.0.0/dist/chartjs-plugin-annotation.min.js|chartjs-plugin-annotation-2.0.0.min.js"
    "https://cdn.jsdelivr.net/npm/sweetalert2@11/dist/sweetalert2.all.min.js|sweetalert2.all.min.js"
    "https://cdnjs.cloudflare.com/ajax/libs/numeric/1.2.6/numeric.min.js|numeric-1.2.6.min.js"
    "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js|mathjax-tex-mml-chtml.js"
)
for entry in "${VENDOR_FILES[@]}"; do
    url="${entry%%|*}"; file="${entry##*|}"
    echo "    $file"
    curl -fsSL "$url" -o "$VENDOR_DIR/$file"
    if [ $? -ne 0 ]; then
        print_fail "Failed to download $file."
        osascript -e "display dialog \"Failed to download vendor library: $file\" buttons {\"OK\"} with title \"EasyOKAPI Setup\" $(_icon)"
        exit 1
    fi
done

declare -a MATHJAX_FONTS=(
    MathJax_AMS-Regular MathJax_Main-Regular MathJax_Main-Bold MathJax_Main-Italic
    MathJax_Math-Italic MathJax_Math-BoldItalic MathJax_Size1-Regular MathJax_Size2-Regular
    MathJax_Size3-Regular MathJax_Size4-Regular MathJax_Calligraphic-Regular
    MathJax_Calligraphic-Bold MathJax_Fraktur-Regular MathJax_Fraktur-Bold
    MathJax_SansSerif-Regular MathJax_SansSerif-Bold MathJax_SansSerif-Italic
    MathJax_Script-Regular MathJax_Typewriter-Regular MathJax_Vector-Regular
    MathJax_Vector-Bold MathJax_Zero
)
for font in "${MATHJAX_FONTS[@]}"; do
    echo "    ${font}.woff"
    curl -fsSL \
        "https://cdn.jsdelivr.net/npm/mathjax@3/es5/output/chtml/fonts/woff-v2/${font}.woff" \
        -o "$FONT_DIR/${font}.woff"
    if [ $? -ne 0 ]; then
        print_fail "Failed to download MathJax font: ${font}.woff"
        osascript -e "display dialog \"Failed to download MathJax font: ${font}.woff\" buttons {\"OK\"} with title \"EasyOKAPI Setup\" $(_icon)"
        exit 1
    fi
done
print_ok "Vendor libraries downloaded."

chown -R "$CURRENT_USER:staff" "$INSTALL_DIR"

# ── Offer to import data from a previous installation ─────────────────────────
# Only when this was a fresh install (no in-installer restore happened) but a
# leftover backup from a prior uninstall is present. After an overwrite the data
# was already restored above, so there is nothing more to do.
PERSIST_BACKUP="/Users/$CURRENT_USER/EasyOKAPI_data"
if [ -z "$BACKUP_DIR" ] && [ -d "$PERSIST_BACKUP" ]; then
    IMPORT=$(osascript \
        -e "display dialog \"A backup of measurement data, calibration curves, and reports from a previous EasyOKAPI installation was found at:\n\n$PERSIST_BACKUP\n\nImport it into this version now?\" buttons {\"Not now\", \"Import previous data\"} default button \"Import previous data\" with title \"EasyOKAPI Setup\" $(_icon)" \
        -e 'button returned of result' 2>/dev/null)
    if [ "$IMPORT" = "Import previous data" ]; then
        for d in data json report; do
            if [ -d "$PERSIST_BACKUP/$d" ]; then
                mkdir -p "$INSTALL_DIR/$d"
                cp -r "$PERSIST_BACKUP/$d/." "$INSTALL_DIR/$d/"
            fi
        done
        _archive_unstash_root "$INSTALL_DIR/data"
        chown -R "$CURRENT_USER:staff" "$INSTALL_DIR"
        print_ok "Previous data imported from $PERSIST_BACKUP"
    fi
fi

# ── Offer to import the bundled sample measurement data ───────────────────────
# sample_data/ ships in the source tarball as example CSVs. The app lists
# immediate subfolders of data/ as data folders, so importing copies it to
# data/sample_data/. The source copy is removed afterwards either way.
if [ -d "$INSTALL_DIR/sample_data" ]; then
    SAMPLE=$(osascript \
        -e "display dialog \"EasyOKAPI includes a set of sample measurement files.\n\nImport them into your data folder (as a 'sample_data' folder) so you can explore the app right away?\" buttons {\"No\", \"Import sample data\"} default button \"Import sample data\" with title \"EasyOKAPI Setup\" $(_icon)" \
        -e 'button returned of result' 2>/dev/null)
    if [ "$SAMPLE" = "Import sample data" ]; then
        mkdir -p "$INSTALL_DIR/data/sample_data"
        cp -r "$INSTALL_DIR/sample_data/." "$INSTALL_DIR/data/sample_data/"
        chown -R "$CURRENT_USER:staff" "$INSTALL_DIR/data"
        print_ok "Sample data imported into data/sample_data."
    fi
    rm -rf "$INSTALL_DIR/sample_data"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}${GREEN}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${GREEN}║  ✔  EasyOKAPI setup complete!             ║${RESET}"
echo -e "  ${BOLD}${GREEN}╚══════════════════════════════════════════╝${RESET}"
echo ""
echo "Setup completed at $(date)"

# Mention the persistent data backup location on the final dialog if one exists.
BACKUP_NOTE=""
[ -d "$PERSIST_BACKUP" ] && BACKUP_NOTE="\n\nA backup of your measurement data is kept at:\n$PERSIST_BACKUP"
osascript -e "display dialog \"EasyOKAPI is ready!\n\nLaunch it anytime by clicking EasyOKAPI in your Applications folder or Launchpad.$BACKUP_NOTE\" buttons {\"Done\"} default button \"Done\" with title \"EasyOKAPI Setup Complete\" $(_icon)"
exit 0
