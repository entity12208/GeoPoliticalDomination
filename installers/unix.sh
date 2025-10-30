#!/usr/bin/env bash
set -euo pipefail

echo "==============================================="
echo "GeoPoliticalDomination - macOS / Linux installer"
echo "==============================================="
echo

# Helper: choose python command
choose_python() {
  if command -v python >/dev/null 2>&1; then
    echo python
  elif command -v python3 >/dev/null 2>&1; then
    echo python3
  else
    echo ""
  fi
}

PY=$(choose_python)

# 1) Install Python if missing
if [ -z "$PY" ]; then
  echo "Python not found on PATH."
  if [[ "$(uname -s)" == "Darwin" ]]; then
    # macOS
    if command -v brew >/dev/null 2>&1; then
      echo "Homebrew detected. Installing Python..."
      brew update
      brew install python
    else
      echo "Homebrew not found. Installing Homebrew will make this easier."
      echo "You can install Homebrew from https://brew.sh and re-run this script, or install Python manually."
      read -p "Do you want to attempt to install Homebrew now? (y/N): " ans
      if [[ "$ans" =~ ^[Yy]$ ]]; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
        brew install python
      else
        echo "Please install Python (via Homebrew or from python.org), then re-run."
        exit 1
      fi
    fi
  else
    # Linux: detect apt, dnf, yum, pacman
    if command -v apt-get >/dev/null 2>&1; then
      echo "apt-get detected. Installing python3, venv & pip..."
      sudo apt-get update
      sudo apt-get install -y python3 python3-venv python3-pip git
    elif command -v dnf >/dev/null 2>&1; then
      echo "dnf detected. Installing python3, venv & pip..."
      sudo dnf install -y python3 python3-venv python3-pip git
    elif command -v yum >/dev/null 2>&1; then
      echo "yum detected. Installing python3, venv & pip..."
      sudo yum install -y python3 python3-venv python3-pip git
    elif command -v pacman >/dev/null 2>&1; then
      echo "pacman detected. Installing python..."
      sudo pacman -S --noconfirm python python-pip git
    else
      echo "Could not detect package manager. Please install Python 3, pip, venv and git manually."
      exit 1
    fi
  fi

  # re-evaluate python command
  PY=$(choose_python)
  if [ -z "$PY" ]; then
    echo "Python still not found after attempted install. Please ensure Python >=3.8 is installed and on PATH."
    exit 1
  fi
fi

echo "Using $($PY --version 2>&1 | head -n1)"

# 2) Check if we're already in the game directory
if [ -f "client_online.py" ] && [ -f "client_local.py" ]; then
  echo "Already in game directory: $(pwd)"
elif [ -f "../client_online.py" ] && [ -f "../client_local.py" ]; then
  echo "Found game directory in parent folder, navigating there..."
  cd ..
  echo "Now in: $(pwd)"
else
  echo "==============================================="
  echo "Game files not found!"
  echo "==============================================="
  echo
  echo "This installer can download GeoPolitical Domination"
  echo "from GitHub: https://github.com/entity12208/GeoPoliticalDomination"
  echo
  read -p "Would you like to download the game now? (y/N): " download_choice
  
  if [[ "$download_choice" =~ ^[Yy]$ ]]; then
    echo "Downloading latest release from GitHub..."
    
    GITHUB_ZIP_URL="https://github.com/entity12208/GeoPoliticalDomination/archive/refs/heads/main.zip"
    ZIP_FILE="/tmp/gpd_download.zip"
    EXTRACT_DIR="/tmp/gpd_extract"
    
    # Download
    if command -v curl >/dev/null 2>&1; then
      curl -L -o "$ZIP_FILE" "$GITHUB_ZIP_URL"
    elif command -v wget >/dev/null 2>&1; then
      wget -O "$ZIP_FILE" "$GITHUB_ZIP_URL"
    else
      echo "ERROR: Neither curl nor wget found. Please install one and try again."
      exit 1
    fi
    
    if [ ! -f "$ZIP_FILE" ]; then
      echo "ERROR: Download failed. Please check your internet connection."
      exit 1
    fi
    
    echo "Extracting files..."
    mkdir -p "$EXTRACT_DIR"
    unzip -q "$ZIP_FILE" -d "$EXTRACT_DIR"
    
    # Move files from extracted folder to current directory
    EXTRACTED_FOLDER=$(find "$EXTRACT_DIR" -maxdepth 1 -name "GeoPoliticalDomination-*" -type d | head -n 1)
    if [ -n "$EXTRACTED_FOLDER" ]; then
      echo "Moving files to current directory..."
      cp -r "$EXTRACTED_FOLDER"/* "$(pwd)/"
      echo "Download and extraction complete!"
    else
      echo "ERROR: Could not find extracted folder."
      exit 1
    fi
    
    # Clean up
    rm -f "$ZIP_FILE"
    rm -rf "$EXTRACT_DIR"
    
    # Verify files are now present
    if [ -f "client_online.py" ] && [ -f "client_local.py" ]; then
      echo "Game files successfully downloaded!"
    else
      echo "ERROR: Download completed but game files not found. Please check manually."
      exit 1
    fi
  else
    echo "ERROR: Cannot proceed without game files."
    echo "Please download manually from: https://github.com/entity12208/GeoPoliticalDomination"
    echo "Or run this installer from the game directory."
    exit 1
  fi
fi

# 4) venv: use existing or create
if [ -d "venv" ]; then
  echo "Found existing venv. Activating..."
else
  echo "Creating virtual environment 'venv'..."
  $PY -m venv venv
fi

# activate venv for this script's session
# shellcheck disable=SC1091
if [ -f "venv/bin/activate" ]; then
  # shell scripts can source the activate script
  # shellcheck disable=SC1090
  . venv/bin/activate
else
  echo "venv activation script not found. Exiting."
  exit 1
fi

# ensure pip refers to the venv pip
python -m pip --version >/dev/null 2>&1 || (python -m ensurepip --upgrade || true)

# 5) Check requirements.txt and install missing packages (heuristic)
if [ -f requirements.txt ]; then
  echo "Checking requirements.txt for missing packages..."
  MISSING=$(python - <<PY
import re, sys
from pathlib import Path
try:
    import importlib.metadata as md
except:
    try:
        import importlib_metadata as md
    except:
        md = None
p = Path("requirements.txt")
lines = [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.strip().startswith('#')]
def normpkg(line):
    return re.split('[<=>;\\[]', line)[0].strip()
missing=[]
for l in lines:
    pkg=normpkg(l)
    if not pkg:
        continue
    ok = False
    # try distribution metadata
    if md:
        try:
            md.version(pkg)
            ok = True
        except Exception:
            ok = False
    if not ok:
        try:
            __import__(pkg)
            ok = True
        except Exception:
            ok = False
    if not ok:
        missing.append(pkg)
print(",".join(missing))
PY
)
  if [ -n "$MISSING" ]; then
    echo "Missing packages: $MISSING"
    echo "Installing from requirements.txt..."
    python -m pip install -r requirements.txt
  else
    echo "All requirements appear present (heuristic)."
  fi
else
  echo "No requirements.txt found — skipping install."
fi

# 6) Ask user whether to run online or offline
while true; do
  read -p "Play online or offline? [o/f]: " choice
  case "$choice" in
    [Oo]* )
      echo "Launching online client..."
      python client_online.py
      break
      ;;
    [Ff]* )
      echo "Launching offline client..."
      python client_local.py
      break
      ;;
    * )
      echo "Please answer 'o' for online or 'f' for offline."
      ;;
  esac
done

echo "Done."
