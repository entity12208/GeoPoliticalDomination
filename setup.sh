#!/usr/bin/env bash
# setup.sh — One-command setup for GeoPolitical Domination
# Usage: chmod +x setup.sh && ./setup.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  GeoPolitical Domination — Setup"
echo "========================================"
echo ""

# --- Detect Python ---
PY=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY="$cmd"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "[!] Python not found. Installing..."
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
        echo "[ERROR] Cannot auto-install Python on this system."
        echo "        Please install Python 3.8+ manually, then re-run this script."
        exit 1
    fi
fi

PY_VERSION=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[OK] Using $PY ($PY_VERSION)"

# --- Install system SDL2 libs if on apt-based system (needed by pygame) ---
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
        sudo apt-get update -qq
        sudo apt-get install -y libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libsdl2-gfx-dev 2>/dev/null || true
    fi
fi

# --- Create venv ---
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating virtual environment..."
    "$PY" -m venv "$VENV_DIR" 2>/dev/null || {
        echo "[!] venv module missing, installing..."
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y python3-venv
        fi
        "$PY" -m venv "$VENV_DIR"
    }
fi

# --- Activate venv ---
source "$VENV_DIR/bin/activate"
echo "[OK] Virtual environment active"

# --- Install dependencies ---
echo "[*] Installing Python packages..."
pip install --upgrade pip -q 2>/dev/null || true
pip install -r requirements.txt -q 2>/dev/null || {
    # Fallback: try with --break-system-packages if venv somehow failed
    pip install --break-system-packages -r requirements.txt -q 2>/dev/null || {
        echo "[!] pip install failed. Trying without venv..."
        deactivate 2>/dev/null || true
        "$PY" -m pip install --user -r requirements.txt -q || {
            "$PY" -m pip install --break-system-packages -r requirements.txt -q
        }
    }
}
echo "[OK] Dependencies installed"

# --- Verify pygame works ---
"$PY" -c "import pygame; print(f'[OK] pygame-ce {pygame.ver}')" 2>/dev/null || {
    echo "[!] pygame import failed, trying reinstall..."
    pip install --force-reinstall pygame-ce -q
    "$PY" -c "import pygame; print(f'[OK] pygame-ce {pygame.ver}')"
}

# --- Check for geojson ---
if [ ! -f "$SCRIPT_DIR/assets/countries.geojson" ]; then
    echo ""
    echo "[NOTE] No countries.geojson found in assets/."
    echo "       The game will use a minimal fallback map."
    echo "       For the full world map, place countries.geojson in the assets/ folder."
fi

echo ""
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo ""
echo "To play, run:"
echo "  source .venv/bin/activate"
echo "  python3 client.py"
echo ""
echo "Or just run:  ./play.sh"

# --- Create a convenience play script ---
cat > "$SCRIPT_DIR/play.sh" << 'PLAY_EOF'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi
python3 client.py "$@"
PLAY_EOF
chmod +x "$SCRIPT_DIR/play.sh"
echo ""
echo "Created play.sh for quick launching."
