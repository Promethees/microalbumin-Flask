#!/bin/bash

# Exit on first error
set -e

# Change to the script's directory (repo root)
cd "$(dirname "$0")"

exec > >(tee -a /tmp/easyokapi-setup2.log) 2>&1
echo "Starting setup step 2 at $(date)"

# ── Root check ────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (sudo ./setup-2-install-venv.sh)."
    exit 1
fi

CURRENT_USER="${SUDO_USER:-}"
if [ -z "$CURRENT_USER" ] || [ "$CURRENT_USER" = "root" ]; then
    echo "❌ Unable to determine the invoking user. Run with: sudo ./setup-2-install-venv.sh"
    exit 1
fi
CURRENT_HOME=$(eval echo "~$CURRENT_USER")
PYENV_ROOT="$CURRENT_HOME/.pyenv"
PYTHON_VERSION="3.8.10"
PYTHON_BIN="$PYENV_ROOT/versions/$PYTHON_VERSION/bin/python"
REPO_DIR="$(pwd)"

# ── Preflight ─────────────────────────────────────────────────────────────────
if [ ! -x "$PYTHON_BIN" ]; then
    echo "❌ Python $PYTHON_VERSION not found at $PYTHON_BIN."
    echo "   Please run setup-1-install-pyenv.sh first."
    exit 1
fi
if [ ! -f "$REPO_DIR/requirements.txt" ]; then
    echo "❌ requirements.txt not found. Make sure you are inside the repo root."
    exit 1
fi

# ── Step 1: Create virtual environment ────────────────────────────────────────
echo "Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    su - "$CURRENT_USER" -c "$PYTHON_BIN -m venv $REPO_DIR/venv"
fi

VENV_PIP="$REPO_DIR/venv/bin/pip"
su - "$CURRENT_USER" -c "$VENV_PIP install --upgrade pip"
su - "$CURRENT_USER" -c "$VENV_PIP install -r $REPO_DIR/requirements.txt"
echo "✅ Virtual environment ready."

# ── Pre-compile bytecode for scipy/numpy so first app launch is not slow ──────
echo "Pre-compiling Python bytecode for scientific libraries..."
VENV_PYTHON="$REPO_DIR/venv/bin/python"
su - "$CURRENT_USER" -c "$VENV_PYTHON -m compileall -q $REPO_DIR/venv/lib/python3.8/site-packages/scipy $REPO_DIR/venv/lib/python3.8/site-packages/numpy 2>/dev/null" || true
echo "✅ Bytecode pre-compilation complete."

# ── Step 2: Download front-end vendor libraries ───────────────────────────────
VENDOR_DIR="$REPO_DIR/static/vendor"
FONT_DIR="$VENDOR_DIR/mathjax-fonts"

if [ ! -d "$VENDOR_DIR" ]; then
    echo "Downloading front-end vendor libraries..."
    mkdir -p "$FONT_DIR"

    VENDOR_URLS=(
        "https://code.jquery.com/jquery-3.6.0.min.js|jquery-3.6.0.min.js"
        "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js|chart.umd.min.js"
        "https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.0.0/dist/chartjs-plugin-annotation.min.js|chartjs-plugin-annotation-2.0.0.min.js"
        "https://cdn.jsdelivr.net/npm/sweetalert2@11/dist/sweetalert2.all.min.js|sweetalert2.all.min.js"
        "https://cdnjs.cloudflare.com/ajax/libs/numeric/1.2.6/numeric.min.js|numeric-1.2.6.min.js"
        "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js|mathjax-tex-mml-chtml.js"
    )

    for entry in "${VENDOR_URLS[@]}"; do
        url="${entry%%|*}"
        file="${entry##*|}"
        echo "  Downloading $file..."
        curl -fsSL "$url" -o "$VENDOR_DIR/$file"
    done

    MATHJAX_FONTS=(
        "MathJax_AMS-Regular" "MathJax_Main-Regular" "MathJax_Main-Bold" "MathJax_Main-Italic"
        "MathJax_Math-Italic" "MathJax_Math-BoldItalic" "MathJax_Size1-Regular" "MathJax_Size2-Regular"
        "MathJax_Size3-Regular" "MathJax_Size4-Regular" "MathJax_Calligraphic-Regular"
        "MathJax_Calligraphic-Bold" "MathJax_Fraktur-Regular" "MathJax_Fraktur-Bold"
        "MathJax_SansSerif-Regular" "MathJax_SansSerif-Bold" "MathJax_SansSerif-Italic"
        "MathJax_Script-Regular" "MathJax_Typewriter-Regular" "MathJax_Vector-Regular"
        "MathJax_Vector-Bold" "MathJax_Zero"
    )
    for font in "${MATHJAX_FONTS[@]}"; do
        curl -fsSL "https://cdn.jsdelivr.net/npm/mathjax@3/es5/output/chtml/fonts/woff-v2/${font}.woff" \
            -o "$FONT_DIR/${font}.woff"
    done
    echo "✅ Vendor libraries downloaded."
else
    echo "Vendor libraries already present — skipping download."
fi

# ── AI Assistant Setup (optional) ─────────────────────────────────────────────
AI_SETTINGS_FILE="$REPO_DIR/ai_settings.json"
if [ -f "$AI_SETTINGS_FILE" ]; then
    echo ""
    echo "  ℹ  AI Assistant settings already found (ai_settings.json)."
    read -p "     Reconfigure? [y/N]: " reconf_choice
    if [[ "${reconf_choice:-n}" =~ ^[Yy]$ ]]; then
        rm -f "$AI_SETTINGS_FILE"
    else
        echo "  Keeping existing AI settings."
    fi
fi

if [ ! -f "$AI_SETTINGS_FILE" ]; then
    echo ""
    echo "  ╔══════════════════════════════════════════════════════════╗"
    echo "  ║   🤖  AI Assistant  (Optional Feature)                  ║"
    echo "  ╠══════════════════════════════════════════════════════════╣"
    echo "  ║  Answers questions about your data in 6 languages:       ║"
    echo "  ║  English · Tiếng Việt · 中文 · Français · 日本語 · Русский ║"
    echo "  ║  Powered by Ollama (local LLM — no internet after setup) ║"
    echo "  ╚══════════════════════════════════════════════════════════╝"
    echo ""
    read -p "  Install AI Assistant? [y/N]: " ai_choice

    if [[ "${ai_choice:-n}" =~ ^[Yy]$ ]]; then
        AI_ENABLED="true"

        # Language selection (multi-select)
        echo ""
        echo "  Choose languages (enter numbers separated by spaces, e.g. 1 2):"
        echo "    1) English   2) Tiếng Việt   3) 中文 (简体)"
        echo "    4) Français  5) 日本語        6) Русский"
        echo ""
        read -p "  Enter numbers [1-6, default=1]: " lang_input
        lang_input="${lang_input:-1}"
        AI_LANGS=()
        for num in $lang_input; do
            case "$num" in
                1) AI_LANGS+=("en") ;;
                2) AI_LANGS+=("vi") ;;
                3) AI_LANGS+=("zh") ;;
                4) AI_LANGS+=("fr") ;;
                5) AI_LANGS+=("ja") ;;
                6) AI_LANGS+=("ru") ;;
            esac
        done
        [ ${#AI_LANGS[@]} -eq 0 ] && AI_LANGS=("en")
        LANG_JSON="["
        _first=1
        for code in "${AI_LANGS[@]}"; do
            [ $_first -eq 0 ] && LANG_JSON+=","
            LANG_JSON+="\"$code\""
            _first=0
        done
        LANG_JSON+="]"
        echo "  ✓ Languages: ${AI_LANGS[*]}"

        # Model selection
        echo ""
        echo "  Choose AI model:"
        echo "    1) qwen2.5:7b  (4.7 GB) — Best multilingual  [recommended]"
        echo "    2) qwen2.5:3b  (1.9 GB) — Lighter, still multilingual"
        echo "    3) llama3.2:3b (2.0 GB) — Good English/French"
        echo "    4) mistral:7b  (4.1 GB) — Good European languages"
        echo ""
        read -p "  Enter number [1-4, default=1]: " model_choice
        case "${model_choice:-1}" in
            2) AI_MODEL="qwen2.5:3b";  AI_MODEL_SIZE="1.9 GB" ;;
            3) AI_MODEL="llama3.2:3b"; AI_MODEL_SIZE="2.0 GB" ;;
            4) AI_MODEL="mistral:7b";  AI_MODEL_SIZE="4.1 GB" ;;
            *) AI_MODEL="qwen2.5:7b";  AI_MODEL_SIZE="4.7 GB" ;;
        esac
        echo "  ✓ Model: $AI_MODEL"

        # Ollama check / install
        echo ""
        _ensure_ollama_running() {
            if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
                systemctl start ollama 2>/dev/null || su - "$CURRENT_USER" -c "ollama serve &>/dev/null &"
                echo "  Waiting for Ollama to start…"
                for _i in $(seq 1 15); do
                    sleep 1
                    curl -sf http://localhost:11434/api/tags &>/dev/null && break || true
                done
            fi
        }
        if command -v ollama &>/dev/null; then
            echo "  ✓ Ollama is installed."
            if ollama list 2>/dev/null | grep -q "^${AI_MODEL}"; then
                echo "  ✓ Model $AI_MODEL is already downloaded."
            else
                read -p "  Download $AI_MODEL now? ($AI_MODEL_SIZE, may take several minutes) [Y/n]: " pull_choice
                if [[ "${pull_choice:-y}" =~ ^[Yy]$ ]]; then
                    _ensure_ollama_running
                    echo "  Downloading $AI_MODEL…"
                    su - "$CURRENT_USER" -c "ollama pull $AI_MODEL"
                    echo "  ✓ Model downloaded."
                else
                    echo "  ℹ  Skipped. You can download it from inside the app (🤖 button → Settings)."
                fi
            fi
        else
            echo "  ⚠  Ollama is not installed."
            read -p "  Install Ollama now? (requires internet) [y/N]: " ollama_install_choice
            if [[ "${ollama_install_choice:-n}" =~ ^[Yy]$ ]]; then
                echo "  Installing Ollama…"
                curl -fsSL https://ollama.com/install.sh | sh
                if command -v ollama &>/dev/null; then
                    echo "  ✓ Ollama installed."
                    read -p "  Download $AI_MODEL now? ($AI_MODEL_SIZE, may take several minutes) [Y/n]: " pull_choice
                    if [[ "${pull_choice:-y}" =~ ^[Yy]$ ]]; then
                        _ensure_ollama_running
                        echo "  Downloading $AI_MODEL…"
                        su - "$CURRENT_USER" -c "ollama pull $AI_MODEL"
                        echo "  ✓ Model downloaded."
                    else
                        echo "  ℹ  Download it later from inside the app (🤖 button → Settings)."
                    fi
                else
                    echo "  ⚠  Ollama install failed. You can install it manually: https://ollama.com"
                fi
            else
                echo "  ℹ  Skipped. Install Ollama later and then download the model from inside the app."
            fi
        fi

    else
        AI_ENABLED="false"
        LANG_JSON='["en"]'
        AI_MODEL="qwen2.5:7b"
        echo "  ℹ  AI Assistant disabled. Enable it any time from the 🤖 button inside the app."
    fi

    printf '{\n  "enabled": %s,\n  "preferred_languages": %s,\n  "model": "%s",\n  "ollama_url": "http://localhost:11434",\n  "first_run_shown": false\n}\n' \
        "$AI_ENABLED" "$LANG_JSON" "$AI_MODEL" > "$AI_SETTINGS_FILE"
    chown "$CURRENT_USER:$CURRENT_USER" "$AI_SETTINGS_FILE"
    echo "  ✓ Saved: ai_settings.json"
fi
echo ""

# ── Step 3: HID udev rule ─────────────────────────────────────────────────────
echo "Installing HID udev rule..."
cat > /etc/udev/rules.d/99-easyokapi-hid.rules <<'UDEV'
# EasyOKAPI – PyBadge colorimeter HID access for all users
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="239a", MODE="0666"
SUBSYSTEM=="usb",    ATTRS{idVendor}=="239a", MODE="0666"
UDEV
udevadm control --reload-rules
udevadm trigger
echo "✅ udev rule installed."

# Fix ownership so the current user can write to the repo
chown -R "$CURRENT_USER:$CURRENT_USER" "$REPO_DIR/venv" "$REPO_DIR/static/vendor"

echo ""
echo "✅ Step 2 complete."
echo "   Next: sudo ./setup-3-run.sh"
read -n 1 -s -r -p "   Press any key to exit..."
echo ""
exit 0
