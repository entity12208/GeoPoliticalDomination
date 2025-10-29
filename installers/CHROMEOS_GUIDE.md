# ChromeOS / Linux Installation Guide

## Quick Start for ChromeOS
1. Download `gpd-setup-unix.sh`
2. Open Crostini Terminal (or your Linux terminal)
3. Run: `bash ~/Downloads/gpd-setup-unix.sh`
4. Follow the prompts

That's all! The installer handles everything.

## System Requirements
- ChromeOS with Crostini enabled OR Linux system
- ~500 MB free disk space
- sudo access (for package installation)
- Internet connection

## What Gets Installed
- Python 3
- SDL2 graphics libraries
- Python libraries (pygame-ce, Firestore SDK, etc.)
- GeoPolitical Domination game files

## ChromeOS Setup (Crostini)

### 1. Enable Linux Support
1. Open Settings
2. Go to "Advanced" > "Developers"
3. Click "Enable" next to "Linux development environment"
4. Wait for installation to complete

### 2. Open Linux Terminal
- Click the Linux folder icon in your Files app
- Click "Terminal"

### 3. Run the Installer
```
bash ~/Downloads/gpd-setup-unix.sh
```

The installer will handle all Python and dependency setup!

## Step-by-Step Manual Installation

### 1. Update Package Manager
```
sudo apt update
sudo apt upgrade
```

### 2. Install Python 3
```
sudo apt install python3 python3-venv python3-pip
```

### 3. Install SDL2
```
sudo apt install libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
```

### 4. Clone or Download the Game
**Option A: Using Git (recommended)**
```
git clone https://github.com/entity12208/GeoPoliticalDomination.git
cd GeoPoliticalDomination
```

**Option B: Download as ZIP**
- Use a browser or: `wget https://github.com/entity12208/GeoPoliticalDomination/archive/main.zip`
- Extract: `unzip main.zip`

### 5. Create Virtual Environment
```
python3 -m venv .venv
source .venv/bin/activate
```

### 6. Install Dependencies
```
pip install -r requirements.txt
```

### 7. Run the Game
```
python3 client_local.py
```

For online play:
```
python3 client_online.py
```

## Troubleshooting

### ChromeOS: Crostini won't start
1. Go to Settings > Advanced > Developers
2. Click "Disable" then "Enable" Linux
3. Wait for it to finish setting up

### Error: "sudo: command not found"
Try running the command without sudo if it's for your user directory:
```
python3 -m venv .venv
```

### Error: "No module named pygame"
Make sure SDL2 is installed:
```
sudo apt install libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
pip install --upgrade pygame-ce
```

### Error: "python3: command not found"
Install Python:
```
sudo apt install python3 python3-venv python3-pip
```

### Game window won't open
This usually means SDL2 is not installed:
```
sudo apt install libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
pip install --upgrade pygame-ce
```

### For online play, Firebase credentials error
You need a `gpd_secrets.txt` file with Firebase service account JSON. See the main README for setup.

## Linux Distribution Specific

### Ubuntu / Debian
```
sudo apt install python3 python3-venv python3-pip libsdl2-dev libsdl2-image-dev
```

### Fedora / RHEL
```
sudo dnf install python3 python3-pip SDL2-devel SDL2_image-devel SDL2_mixer-devel SDL2_ttf-devel
```

### Arch
```
sudo pacman -S python sdl2 sdl2_image sdl2_mixer sdl2_ttf
```

## Advanced Troubleshooting

### Check Python version
```
python3 --version
```

### Check SDL2 installation
```
ldconfig -p | grep SDL
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

### Performance Issues on ChromeOS
If the game runs slowly:
1. Make sure Linux container has enough resources (Settings > Advanced > Developers > Linux dev environment options)
2. Try closing other applications
3. Check available disk space: `df -h`

## Still Having Issues?

1. Check the GitHub repository: https://github.com/entity12208/GeoPoliticalDomination
2. Open an issue on GitHub with your error message
3. Try the Windows guide if you have access to Windows

Good luck! 🎮
