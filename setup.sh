#!/usr/bin/env bash
# setup.sh — One-command installer & setup for GeoPolitical Domination
#
# Install from anywhere:
#   curl -fsSL https://raw.githubusercontent.com/entity12208/GeoPoliticalDomination/main/setup.sh | bash
#
# Or if you already have the repo:
#   chmod +x setup.sh && ./setup.sh
#
set -e

REPO_URL="https://github.com/entity12208/GeoPoliticalDomination"
REPO_API="https://api.github.com/repos/entity12208/GeoPoliticalDomination/releases/latest"
INSTALL_DIR="${GPD_INSTALL_DIR:-$HOME/GeoPoliticalDomination}"

echo "========================================"
echo "  GeoPolitical Domination — Setup"
echo "========================================"
echo ""

# --- Detect if we're running from an existing install ---
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "bash" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd 2>/dev/null || echo "")"
fi
IN_REPO=false
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/client.py" ]; then
    IN_REPO=true
    INSTALL_DIR="$SCRIPT_DIR"
    echo "[*] Running from existing install: $INSTALL_DIR"
else
    echo "[*] Fresh install to: $INSTALL_DIR"
fi

# --- Detect Python 3.8+ ---
PY=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" 2>/dev/null; then
            PY="$cmd"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "[!] Python 3.8+ not found. Installing..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y python3 python3-venv python3-pip
        PY=python3
    elif command -v brew &>/dev/null; then
        brew install python
        PY=python3
    elif command -v pacman &>/dev/null; then
        sudo pacman -Sy --noconfirm python python-pip
        PY=python3
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3 python3-pip
        PY=python3
    else
        echo "[ERROR] Cannot auto-install Python. Please install Python 3.8+ manually."
        exit 1
    fi
fi

PY_VERSION=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[OK] Python $PY_VERSION"

# --- Install SDL2 dev libs on Debian/Ubuntu ---
if command -v apt-get &>/dev/null; then
    NEED_SDL=false
    for lib in libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev; do
        if ! dpkg -s "$lib" &>/dev/null 2>&1; then
            NEED_SDL=true
            break
        fi
    done
    if $NEED_SDL; then
        echo "[*] Installing SDL2 development libraries..."
        sudo apt-get update -qq 2>/dev/null || true
        sudo apt-get install -y libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libsdl2-gfx-dev 2>/dev/null || true
    fi
fi

# --- Download latest release if not in existing repo ---
if ! $IN_REPO; then
    echo ""
    echo "[*] Downloading latest release..."

    # Need curl or wget
    if ! command -v curl &>/dev/null && ! command -v wget &>/dev/null; then
        echo "[!] Installing curl..."
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y curl
        elif command -v brew &>/dev/null; then
            brew install curl
        fi
    fi

    # Get the latest release info
    RELEASE_JSON=""
    if command -v curl &>/dev/null; then
        RELEASE_JSON=$(curl -fsSL "$REPO_API" 2>/dev/null || echo "")
    elif command -v wget &>/dev/null; then
        RELEASE_JSON=$(wget -qO- "$REPO_API" 2>/dev/null || echo "")
    fi

    ZIP_URL=""
    TAG=""
    if [ -n "$RELEASE_JSON" ]; then
        ZIP_URL=$("$PY" -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('zipball_url',''))" <<< "$RELEASE_JSON" 2>/dev/null || echo "")
        TAG=$("$PY" -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('tag_name',''))" <<< "$RELEASE_JSON" 2>/dev/null || echo "")
    fi

    if [ -z "$ZIP_URL" ]; then
        echo "[!] No releases found, downloading main branch..."
        ZIP_URL="${REPO_URL}/archive/refs/heads/main.zip"
        TAG="main"
    else
        echo "[OK] Latest release: $TAG"
    fi

    TEMP_ZIP=$(mktemp /tmp/gpd_XXXXXX.zip)
    echo "[*] Downloading..."
    if command -v curl &>/dev/null; then
        curl -fSL "$ZIP_URL" -o "$TEMP_ZIP"
    else
        wget -q "$ZIP_URL" -O "$TEMP_ZIP"
    fi

    echo "[*] Extracting..."
    TEMP_DIR=$(mktemp -d /tmp/gpd_extract_XXXXXX)
    "$PY" -c "
import zipfile
with zipfile.ZipFile('$TEMP_ZIP', 'r') as z:
    z.extractall('$TEMP_DIR')
"
    EXTRACTED=$(find "$TEMP_DIR" -maxdepth 1 -mindepth 1 -type d | head -1)
    if [ -z "$EXTRACTED" ] || [ ! -d "$EXTRACTED" ]; then
        echo "[ERROR] Extraction failed."
        rm -f "$TEMP_ZIP"; rm -rf "$TEMP_DIR"
        exit 1
    fi

    mkdir -p "$INSTALL_DIR"
    # Copy all files including hidden ones
    (cd "$EXTRACTED" && find . -maxdepth 1 ! -name '.' -exec cp -a {} "$INSTALL_DIR/" \;)
    rm -f "$TEMP_ZIP"; rm -rf "$TEMP_DIR"
    echo "[OK] Installed to $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

if [ ! -f "client.py" ]; then
    echo "[ERROR] client.py not found in $INSTALL_DIR — something went wrong."
    exit 1
fi

# --- Create venv (with robust fallback) ---
VENV_DIR="$INSTALL_DIR/.venv"
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    rm -rf "$VENV_DIR" 2>/dev/null || true
    echo "[*] Creating virtual environment..."

    VENV_OK=false
    # Try current python, then common versioned pythons
    for VENV_PY in "$PY" python3.13 python3.12 python3.11 python3; do
        if command -v "$VENV_PY" &>/dev/null; then
            if "$VENV_PY" -m venv "$VENV_DIR" 2>/dev/null; then
                VENV_OK=true
                echo "[OK] venv created with $VENV_PY"
                break
            fi
            rm -rf "$VENV_DIR" 2>/dev/null || true
        fi
    done

    if ! $VENV_OK; then
        echo "[!] venv failed — installing python3-venv..."
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y "python${PY_VERSION}-venv" 2>/dev/null || \
            sudo apt-get install -y python3-venv 2>/dev/null || true
        fi
        "$PY" -m venv "$VENV_DIR" || {
            echo "[ERROR] Cannot create virtual environment."
            echo "        Try: sudo apt install python${PY_VERSION}-venv"
            exit 1
        }
    fi
fi

# --- Activate venv and install packages ---
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
echo "[OK] Virtual environment active"

echo "[*] Installing Python packages..."
pip install --upgrade pip -q 2>/dev/null || true
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    pip install -r "$INSTALL_DIR/requirements.txt" -q || pip install pygame-ce requests -q
else
    pip install pygame-ce requests -q
fi
echo "[OK] Dependencies installed"

# --- Verify ---
python3 -c "import pygame; print(f'[OK] pygame-ce {pygame.ver}')" 2>/dev/null || {
    echo "[!] pygame import failed, reinstalling..."
    pip install --force-reinstall pygame-ce -q
    python3 -c "import pygame; print(f'[OK] pygame-ce {pygame.ver}')"
}

# --- Geojson check ---
if [ ! -f "$INSTALL_DIR/assets/countries.geojson" ]; then
    echo ""
    echo "[NOTE] No countries.geojson in assets/. The game will use a fallback map."
fi

# --- Create play.sh ---
cat > "$INSTALL_DIR/play.sh" << 'PLAY_EOF'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi
python3 client.py "$@"
PLAY_EOF
chmod +x "$INSTALL_DIR/play.sh"

echo ""
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo ""
echo "  To play:"
echo "    cd $INSTALL_DIR && ./play.sh"
echo ""
