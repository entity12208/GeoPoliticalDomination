# macOS Installation Guide

## Quick Start
1. Download `gpd-setup-unix.sh`
2. Open Terminal (Applications > Utilities > Terminal)
3. Run: `bash ~/Downloads/gpd-setup-unix.sh`
4. Follow the prompts

That's all! The installer handles everything.

## System Requirements
- macOS 10.13 (High Sierra) or later
- ~500 MB free disk space
- Xcode Command Line Tools (will be auto-installed)
- Homebrew (will be auto-installed if missing)
- Internet connection

## What Gets Installed
- Xcode Command Line Tools (if needed)
- Homebrew (if needed)
- Python 3.13 (if needed)
- SDL2 graphics libraries
- Python libraries (pygame-ce, Firestore SDK, etc.)
- GeoPolitical Domination game files

## Step-by-Step Manual Installation

### 1. Install Xcode Command Line Tools
```
xcode-select --install
```

### 2. Install Homebrew (if not already installed)
```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 3. Install Python 3
```
brew install python@3.13
```

### 4. Install SDL2 (required for graphics)
```
brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf
```

### 5. Clone or Download the Game
**Option A: Using Git (recommended)**
```
git clone https://github.com/entity12208/GeoPoliticalDomination.git
cd GeoPoliticalDomination
```

**Option B: Download as ZIP**
- Go to https://github.com/entity12208/GeoPoliticalDomination
- Click "Code" > "Download ZIP"
- Extract the ZIP file
- Open Terminal in that folder

### 6. Create Virtual Environment
```
python3 -m venv .venv
source .venv/bin/activate
```

### 7. Install Dependencies
```
pip install -r requirements.txt
```

### 8. Run the Game
```
python client_local.py
```

For online play:
```
python client_online.py
```

## Troubleshooting

### Error: "xcode-select: command not found"
Install Xcode Command Line Tools:
```
xcode-select --install
```

### Error: "brew: command not found"
Install Homebrew:
```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Error: "No module named pygame"
Make sure SDL2 is installed:
```
brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf
pip install --upgrade pygame-ce
```

### Error: "python3: command not found"
Install Python:
```
brew install python@3.13
```

### Game window won't open (black window closes immediately)
This usually means SDL2 is not installed. Try:
```
brew install sdl2
pip install --upgrade pygame-ce
```

### M1/M2 Mac Issues
If you have an Apple Silicon Mac:
```
arch -arm64 brew install python@3.13
arch -arm64 python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### For online play, Firebase credentials error
You need a `gpd_secrets.txt` file with Firebase service account JSON. See the main README for setup.

## Advanced Troubleshooting

### Check Python version
```
python3 --version
```

### Check SDL2 installation
```
brew list | grep sdl
```

### Reinstall dependencies
```
pip install --force-reinstall -r requirements.txt
```

### Clear Python cache
```
rm -rf __pycache__
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Still Having Issues?

1. Try updating Homebrew: `brew update && brew upgrade`
2. Check the GitHub repository: https://github.com/entity12208/GeoPoliticalDomination
3. Open an issue on GitHub with your error message

Good luck! 🎮
