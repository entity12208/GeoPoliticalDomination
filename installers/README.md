# GeoPolitical Domination - Installation Guide

A turn-based strategy game where you compete to conquer territories on a world map. Manage money, armies, and diplomacy to dominate!

## 🚀 Quick Start

### Option 1: One-Click Installer (Recommended)
Just download and run the single installer for your platform - it handles EVERYTHING:

- **Windows**: Download `gpd-setup-windows.cmd` and double-click it
- **macOS/Linux/ChromeOS**: Download `gpd-setup-unix.sh`, open terminal, and run `bash gpd-setup-unix.sh`

That's it! The installer will:
1. Download the game from GitHub
2. Install Python dependencies
3. Set up the game
4. Launch it automatically

### Option 2: Manual Installation

If you prefer to install manually, see the platform-specific guides below.

---

## 📋 Platform Guides

### Windows
- **Requirements**: Windows 7 or later
- **What you need**: Nothing! (Python will be installed if missing)
- **Installation time**: ~2-5 minutes

**Steps**:
1. Download `gpd-setup-windows.cmd`
2. Double-click the file
3. Follow the prompts
4. Game will launch automatically

See `WINDOWS_GUIDE.md` for troubleshooting and manual installation.

### macOS
- **Requirements**: macOS 10.13 or later
- **What you need**: Nothing! (Python and Homebrew will be installed if missing)
- **Installation time**: ~3-7 minutes

**Steps**:
1. Download `gpd-setup-unix.sh`
2. Open Terminal and navigate to the Downloads folder
3. Run: `bash gpd-setup-unix.sh`
4. Game will launch automatically

See `MACOS_GUIDE.md` for troubleshooting and manual installation.

### ChromeOS / Linux
- **Requirements**: ChromeOS with Crostini or Linux system
- **What you need**: Nothing! (Dependencies will be installed automatically)
- **Installation time**: ~2-5 minutes

**Steps**:
1. Download `gpd-setup-unix.sh`
2. Open Terminal
3. Run: `bash gpd-setup-unix.sh`
4. Game will launch automatically

See `CHROMEOS_GUIDE.md` for ChromeOS-specific setup.

---

## 🎮 Playing the Game

Once installed, you can play:
- **Offline**: Play solo or with friends on the same computer
- **Online**: Play with friends online (requires Firebase credentials)

When you launch the game, you'll see a menu to choose your game mode.

### Online Play Setup
To play online:
1. You need a Firebase project
2. Create a service account JSON file
3. Save it as `gpd_secrets.txt` in the game directory
4. Select "Online Play" from the menu

See the platform guides for detailed Firebase setup instructions.

---

## 🆘 Troubleshooting

### The installer won't run
- **Windows**: Make sure you download as `.cmd` file, not `.txt`. If it won't run, open Command Prompt and drag the file into it.
- **macOS/Linux**: Make sure Terminal can find the file. Try: `bash ~/Downloads/gpd-setup-unix.sh`

### Python not found
- The installers should automatically install Python if needed
- If it doesn't, visit https://www.python.org/downloads/ and install Python 3.13+
- Make sure to check "Add Python to PATH" during installation

### Game won't start
- Check that you have pygame-ce installed (the installer handles this)
- Try running the launcher again
- Check the platform-specific guide for your OS

### For more help
- See the detailed `WINDOWS_GUIDE.md`, `MACOS_GUIDE.md`, or `CHROMEOS_GUIDE.md`
- Visit the GitHub repository: https://github.com/entity12208/GeoPoliticalDomination

---

## 📁 What Gets Installed

The installer will download and set up:
- **Game files**: The complete GeoPolitical Domination game
- **Python libraries**: pygame-ce, google-cloud-firestore, requests, etc.
- **Virtual environment**: Isolated Python setup for the game
- **Launcher**: Interactive menu to choose offline or online play

Everything is self-contained and won't interfere with other applications.

---

## 🗑️ Uninstalling

To remove the game:
- **Windows**: Just delete the game folder
- **macOS/Linux/ChromeOS**: Run `rm -rf ~/GeoPoliticalDomination`

---

## 📝 License

See the GitHub repository for license information.

## 🎯 Repository

- **GitHub**: https://github.com/entity12208/GeoPoliticalDomination
- **Issues**: https://github.com/entity12208/GeoPoliticalDomination/issues

Enjoy the game! 🎮
