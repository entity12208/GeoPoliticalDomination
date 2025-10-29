# Quick Start Guide

## 🚀 One-Click Installation (No Other Files Needed!)

### Windows
1. Download `gpd-setup-windows.cmd`
2. Double-click it
3. Follow the prompts
4. Done! The game will launch automatically

### macOS
1. Download `gpd-setup-unix.sh`
2. Open Terminal
3. Run: `bash ~/Downloads/gpd-setup-unix.sh`
4. Follow the prompts
5. Done! The game will launch automatically

### Linux / ChromeOS
1. Download `gpd-setup-unix.sh`
2. Open Terminal
3. Run: `bash ~/Downloads/gpd-setup-unix.sh`
4. Follow the prompts (enter your password if prompted)
5. Done! The game will launch automatically

---

## ⏱️ Installation Time
- **Windows**: 2-5 minutes
- **macOS**: 3-7 minutes (first time may take longer)
- **Linux/ChromeOS**: 2-5 minutes

---

## 🎮 Playing the Game

When the installer finishes, you'll see a menu:

```
What would you like to do?

  [1] Offline Play
      Play offline on this computer

  [2] Online Play
      Play with friends online (requires gpd_secrets.txt)

  [3] Exit
```

Choose **[1]** to play offline immediately!

---

## 🆘 Troubleshooting

### Windows: The file won't run
- Make sure you downloaded it as `.cmd` file, not `.txt`
- Try right-clicking it and selecting "Run as administrator"
- If that doesn't work, open Command Prompt and drag the file into it

### Mac/Linux: Permission denied
Run this first:
```
chmod +x gpd-setup-unix.sh
bash gpd-setup-unix.sh
```

### Installation takes a very long time
- This is normal the first time (downloading and installing dependencies)
- Subsequent runs will be faster

### Game won't start
- Make sure you have internet connection (for initial download)
- Try running the installer again
- Check the detailed guide for your platform

---

## 📍 Where Is the Game Installed?

After installation, the game is located in:
- **Windows**: `C:\Users\[YourUsername]\GeoPoliticalDomination`
- **macOS/Linux**: `~/GeoPoliticalDomination`

To run the game again later:
- **Windows**: Run `gpd-setup-windows.cmd` again OR navigate to the game folder and run `client_local.py`
- **macOS/Linux**: Run the installer again OR run: `cd ~/GeoPoliticalDomination && bash.venv/bin/activate && python3 client_local.py`

---

## 💡 Tips

- The first installation takes longer because it downloads and installs everything
- Subsequent runs are much faster
- The game stores everything in one folder, so you can move or delete it easily
- To uninstall, just delete the game folder

---

## 📚 Need More Help?

See the detailed guides:
- **Windows**: `WINDOWS_GUIDE.md`
- **macOS**: `MACOS_GUIDE.md`
- **Linux/ChromeOS**: `CHROMEOS_GUIDE.md`

Or visit: https://github.com/entity12208/GeoPoliticalDomination

Enjoy! 🎮
