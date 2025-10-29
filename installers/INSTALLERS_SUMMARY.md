# Installers Summary

## Overview

This folder contains everything needed to install and run GeoPolitical Domination on any platform.

### Key Innovation: Standalone Installers

The new `gpd-setup-*.cmd` and `gpd-setup-*.sh` files are **completely self-contained**. They require:
- **ONLY ONE FILE** to download and run
- NO other files, dependencies, or manual setup
- Automatic download from GitHub
- Automatic Python and dependency installation
- Automatic game setup and launch

---

## Files in This Package

### 🔧 Standalone Installers (Download These!)

#### Windows
- **File**: `gpd-setup-windows.cmd`
- **Size**: ~8 KB
- **Usage**: Just double-click!
- **What it does**:
  - Checks/installs Python 3
  - Checks/installs Git
  - Downloads the game from GitHub
  - Creates Python virtual environment
  - Installs all dependencies
  - Launches the game with menu
  - Allows playing again without re-downloading

#### macOS/Linux/ChromeOS
- **File**: `gpd-setup-unix.sh`
- **Size**: ~10 KB
- **Usage**: `bash gpd-setup-unix.sh`
- **What it does**:
  - Detects OS (macOS vs Linux)
  - Installs Homebrew (macOS only)
  - Checks/installs Python 3
  - Installs SDL2 graphics libraries
  - Downloads the game from GitHub
  - Creates Python virtual environment
  - Installs all dependencies
  - Launches interactive menu
  - Supports offline and online play modes

### 📖 Documentation

#### README.md
- Main installation guide
- Overview of all installation methods
- Platform requirements
- Quick troubleshooting

#### QUICKSTART.md
- 2-minute quick start guide
- Step-by-step for each platform
- Common troubleshooting
- Where files are installed

#### WINDOWS_GUIDE.md
- Detailed Windows setup
- Manual installation steps
- Comprehensive troubleshooting
- Advanced configurations

#### MACOS_GUIDE.md
- Detailed macOS setup
- Homebrew and Xcode installation
- Manual installation steps
- M1/M2 Mac specific help
- Troubleshooting

#### CHROMEOS_GUIDE.md
- ChromeOS Crostini setup
- Linux installation steps
- Distribution-specific commands
- Performance optimization tips

---

## Installation Flow

### Windows
```
1. User downloads gpd-setup-windows.cmd
2. User double-clicks the file
3. Script checks Python (installs if needed)
4. Script downloads from GitHub
5. Script sets up virtual environment
6. Script installs dependencies
7. Game launches with menu
8. User plays!
```

### macOS/Linux/ChromeOS
```
1. User downloads gpd-setup-unix.sh
2. User opens terminal and runs: bash gpd-setup-unix.sh
3. Script checks Python (installs if needed)
4. Script detects OS and installs appropriate libraries
5. Script downloads from GitHub
6. Script sets up virtual environment
7. Script installs dependencies
8. Game launches with menu
9. User plays!
```

---

## Key Features

### ✅ Fully Automated
- No manual steps required
- No technical knowledge needed
- Everything is automatic

### ✅ Self-Contained
- Just one file to download
- No additional files needed
- No pre-installed dependencies required

### ✅ Cross-Platform
- Single solution for Windows
- Single solution for macOS, Linux, ChromeOS
- Automatic platform detection

### ✅ Error Handling
- Checks for prerequisites
- Provides helpful error messages
- Suggests solutions if problems occur

### ✅ User-Friendly
- Clear prompts at each step
- Progress indication
- Option to play multiple times without re-downloading

### ✅ Offline/Online Support
- Launches interactive menu after setup
- Supports both offline and online play
- Validates Firebase credentials for online mode

---

## Technical Details

### Standalone Installer Architecture

```
gpd-setup-*.cmd / gpd-setup-*.sh
    ↓
Detect OS and Prerequisites
    ↓
Install Missing Dependencies
    ├─ Python 3
    ├─ Git (or use ZIP as fallback)
    └─ Platform-specific libraries
    ↓
Download from GitHub
    ├─ Via Git clone (preferred)
    └─ Via ZIP download (fallback)
    ↓
Extract to User Home Directory
    ~/GeoPoliticalDomination/
    ↓
Create Virtual Environment
    .venv/
    ↓
Install Python Dependencies
    pygame-ce
    google-cloud-firestore
    google-api-core
    requests
    ↓
Launch Game Menu
    ├─ Offline Play
    ├─ Online Play (with credential check)
    └─ Exit
    ↓
Game Runs!
```

### Windows Implementation
- Uses batch script for entry point (compatible with all Windows versions)
- Calls PowerShell for complex operations when needed
- Automatic execution policy bypass
- Creates virtual environment using Python's venv module
- Handles both Git and ZIP download scenarios

### Unix Implementation
- Universal bash script for macOS, Linux, ChromeOS
- Automatic OS detection via `$OSTYPE`
- Conditional package manager selection (Homebrew vs apt)
- SDL2 installation (required for Pygame graphics)
- Interactive menu after setup
- Proper error handling with `set -e`

---

## Installation Locations

After running an installer, the game is installed to:

| Platform | Location | Example |
|----------|----------|---------|
| Windows | `%USERPROFILE%\GeoPoliticalDomination` | `C:\Users\John\GeoPoliticalDomination` |
| macOS/Linux | `$HOME/GeoPoliticalDomination` | `/Users/john/GeoPoliticalDomination` |
| ChromeOS | `$HOME/GeoPoliticalDomination` | `/home/chronos/user-hash/GeoPoliticalDomination` |

### Directory Structure
```
GeoPoliticalDomination/
├── client_local.py           # Offline game client
├── client_online.py          # Online game client
├── heuristic_bot.py          # AI bot for single player
├── firebase_sync.py          # Firestore controller
├── requirements.txt          # Python dependencies
├── config.txt                # Game configuration
├── rules.txt                 # Game rules
├── pin_overrides.json        # Country pin adjustments
├── .venv/                    # Virtual environment (created by installer)
│   ├── bin/ (Unix) or Scripts/ (Windows)
│   ├── lib/
│   └── ...
└── assets/
    └── countries.geojson     # World map data (auto-downloaded)
```

---

## Uninstallation

### Windows
Simply delete the folder:
```
C:\Users\[YourUsername]\GeoPoliticalDomination
```

### macOS/Linux/ChromeOS
```
rm -rf ~/GeoPoliticalDomination
```

---

## Re-running the Game

### After first installation:

**Windows:**
- Option 1: Run the installer again (`gpd-setup-windows.cmd`)
- Option 2: Navigate to `C:\Users\[YourUsername]\GeoPoliticalDomination` and run `client_local.py`

**macOS/Linux/ChromeOS:**
- Option 1: Run the installer again
- Option 2: From terminal:
  ```
  cd ~/GeoPoliticalDomination
  source .venv/bin/activate
  python3 client_local.py
  ```

---

## Distribution

To distribute these installers:

1. **Minimal Package** (Just installers):
   - Include only `gpd-setup-windows.cmd` and `gpd-setup-unix.sh`
   - Users need nothing else!
   - ~18 KB total

2. **Complete Package** (Recommended):
   - Include installers + all .md documentation files
   - Users have guides if they need help
   - ~60 KB total

3. **GitHub Release**:
   - Upload both installers as release attachments
   - Users can download directly from GitHub
   - Always links to latest code

---

## Troubleshooting the Installer

### Windows: File is .txt instead of .cmd
- The browser may have downloaded it wrong
- Rename it to `.cmd` extension
- Or download again and right-click "Save As"

### Mac/Linux: Permission denied
```
chmod +x gpd-setup-unix.sh
bash gpd-setup-unix.sh
```

### Installer won't find Python
- Python may not be in PATH
- Check: `python3 --version`
- Reinstall Python and check "Add to PATH"

### Dependencies won't install
- Check internet connection
- Try running installer again
- Check you have ~500 MB free disk space

### Game won't start after installation
- Try running the installer again
- Check the platform-specific guide for more details
- Open an issue on GitHub

---

## Future Enhancements

Possible improvements to the installers:
- [ ] Create Windows .exe installer wrapper
- [ ] Create macOS .app installer
- [ ] Add auto-update functionality
- [ ] Create system start menu shortcuts
- [ ] Add desktop shortcut creation
- [ ] Implement update checker
- [ ] Add uninstaller script

---

## Summary

The standalone installers (`gpd-setup-windows.cmd` and `gpd-setup-unix.sh`) represent a significant improvement in user experience:

- ✅ **Zero friction**: Just download one file and run it
- ✅ **Cross-platform**: One solution per OS family
- ✅ **Fully automated**: No user decisions required
- ✅ **Reliable**: Handles errors gracefully
- ✅ **Self-contained**: No dependencies on system configuration

This makes GeoPolitical Domination accessible to users of all technical levels!
