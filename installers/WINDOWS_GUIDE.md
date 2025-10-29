# Windows Installation Guide

## Quick Start
1. Download `gpd-setup-windows.cmd`
2. Double-click it
3. Follow the prompts

That's all! The installer handles everything.

## System Requirements
- Windows 7 or later
- ~500 MB free disk space
- Internet connection (for initial download)

## What Gets Installed
- Python 3.13 (if not already present)
- Python libraries (pygame-ce, Firestore SDK, etc.)
- GeoPolitical Domination game files
- Game launcher menu

## Step-by-Step Manual Installation

If you prefer to install manually or the one-click installer doesn't work:

### 1. Install Python
- Go to https://www.python.org/downloads/
- Download Python 3.13 or later
- Run the installer
- **IMPORTANT**: Check "Add Python to PATH"

### 2. Clone or Download the Game
**Option A: Using Git (recommended)**
```
git clone https://github.com/entity12208/GeoPoliticalDomination.git
cd GeoPoliticalDomination
```

**Option B: Download as ZIP**
- Go to https://github.com/entity12208/GeoPoliticalDomination
- Click "Code" > "Download ZIP"
- Extract the ZIP file

### 3. Create Virtual Environment
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If you get an error about execution policy, try:
```
powershell -ExecutionPolicy Bypass -Command ".\.venv\Scripts\Activate.ps1"
```

### 4. Install Dependencies
```
pip install -r requirements.txt
```

### 5. Run the Game
```
python client_local.py
```

For online play:
```
python client_online.py
```

## Troubleshooting

### Error: "Python is not installed"
- Make sure Python is installed from https://www.python.org/downloads/
- Make sure "Add Python to PATH" was checked during installation
- Restart Windows after installing Python

### Error: "ExecutionPolicy" when activating venv
Try using this command instead:
```
powershell -ExecutionPolicy Bypass -Command ".\.venv\Scripts\Activate.ps1"
```

### Error: "No module named pygame"
Make sure you've run:
```
pip install -r requirements.txt
```

### Error: "pygame not found" when running the game
Try:
```
pip install --upgrade pygame-ce
```

### Game window won't open
- Make sure you're using Python 3.10 or later
- Try running with: `python -u client_local.py`

### For online play, Firebase credentials error
- You need a `gpd_secrets.txt` file with Firebase service account JSON
- See the main README for Firebase setup instructions

## Advanced Troubleshooting

### Run Python in verbose mode
```
python -v client_local.py
```

### Check Python installation
```
python --version
pip list
```

### Reinstall dependencies
```
pip install --force-reinstall -r requirements.txt
```

### Clear Python cache
```
rmdir /s /q __pycache__
rmdir /s /q .venv
```

Then reinstall the virtual environment (steps 3-4 above).

## Still Having Issues?

1. Check the GitHub repository: https://github.com/entity12208/GeoPoliticalDomination
2. Open an issue on GitHub with your error message
3. Try the Unix-based guide if available (some games work better on one platform)

Good luck! 🎮
