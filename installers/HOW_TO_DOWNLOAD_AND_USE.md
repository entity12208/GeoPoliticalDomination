# How to Download and Install GeoPolitical Domination

## 🎯 The Easiest Way to Get Started

GeoPolitical Domination now has **one-click installers** for every platform!

Just download a single file for your operating system and run it. Everything else is automatic.

---

## 📥 Step 1: Download Your Installer

### Windows Users 🪟
- **File to download**: `gpd-setup-windows.cmd`
- **Size**: ~4 KB (super tiny!)
- **Download from**: 
  - GitHub releases: https://github.com/entity12208/GeoPoliticalDomination/releases
  - Or ask your friend who set this up

### macOS Users 🍎
- **File to download**: `gpd-setup-unix.sh`
- **Size**: ~6 KB
- **Download from**: 
  - GitHub releases: https://github.com/entity12208/GeoPoliticalDomination/releases
  - Or ask your friend who set this up

### Linux / ChromeOS Users 🐧
- **File to download**: `gpd-setup-unix.sh`
- **Size**: ~6 KB
- **Download from**: 
  - GitHub releases: https://github.com/entity12208/GeoPoliticalDomination/releases
  - Or ask your friend who set this up

---

## 🚀 Step 2: Run Your Installer

### Windows 🪟

**Option A: Double-Click (Easiest)**
1. Find the downloaded `gpd-setup-windows.cmd` file
2. Double-click it
3. A black window will open
4. Follow the prompts
5. Wait for installation to complete (2-5 minutes)
6. Game launches automatically!

**Option B: Right-Click and Run**
1. Right-click `gpd-setup-windows.cmd`
2. Select "Run as administrator"
3. Follow the prompts

### macOS 🍎

1. Open **Terminal** (Applications → Utilities → Terminal)
2. Type or copy-paste this command:
   ```
   bash ~/Downloads/gpd-setup-unix.sh
   ```
3. Press Enter
4. When prompted, enter your password (you won't see it typing, that's normal)
5. Wait for installation to complete (3-7 minutes first time)
6. Game launches automatically!

### Linux / ChromeOS 🐧

1. Open **Terminal**
2. Type or copy-paste this command:
   ```
   bash ~/Downloads/gpd-setup-unix.sh
   ```
3. Press Enter
4. When prompted, enter your password (you won't see it typing, that's normal)
5. Wait for installation to complete (2-5 minutes)
6. Game launches automatically!

---

## 🎮 Step 3: Play the Game!

After installation, you'll see this menu:

```
What would you like to do?

  [1] Offline Play
      Play offline on this computer

  [2] Online Play
      Play with friends online (requires gpd_secrets.txt)

  [3] Exit
```

### For First-Time Players
- Select **[1] Offline Play**
- Choose your color and name
- Click on territories to conquer them
- Have fun! 🎮

### For Online Multiplayer
- Select **[2] Online Play**
- (Note: Your friend who set this up should give you the credentials file)
- Play with friends online!

---

## ⏰ How Long Does It Take?

### First Time
- **Windows**: 2-5 minutes
- **macOS**: 3-7 minutes
- **Linux/ChromeOS**: 2-5 minutes

The first time is longer because it downloads and installs everything.

### Subsequent Times
Much faster! Just running the installer or the game again.

---

## 🎯 What If Something Goes Wrong?

### Windows: Nothing happens when I double-click the file

**Solution 1**: Try this instead:
1. Open **Command Prompt** (search for "cmd" in Windows)
2. Drag the `gpd-setup-windows.cmd` file into the Command Prompt window
3. Press Enter
4. Wait for it to finish

**Solution 2**: Try running as administrator:
1. Right-click `gpd-setup-windows.cmd`
2. Select "Run as administrator"

### Mac/Linux: "Permission denied"

**Solution**:
1. Open Terminal
2. Copy-paste this:
   ```
   chmod +x ~/Downloads/gpd-setup-unix.sh
   bash ~/Downloads/gpd-setup-unix.sh
   ```
3. Press Enter

### Any Platform: Installer takes forever

This is **normal** the first time! It's:
- Downloading Python (if needed)
- Downloading the game from GitHub (~10-50 MB depending on updates)
- Installing dependencies (library files)

Just let it run. Don't close the window!

### Any Platform: Game won't start

1. Make sure you have **internet connection**
2. Try running the installer again
3. Check that you have at least **500 MB free disk space**
4. If still stuck, see the detailed guides below

---

## 📚 Need More Help?

### See the Detailed Guides
- **Windows**: `WINDOWS_GUIDE.md` - Detailed setup, troubleshooting, and manual installation
- **macOS**: `MACOS_GUIDE.md` - Detailed setup, Homebrew help, M1/M2 specific tips
- **Linux/ChromeOS**: `CHROMEOS_GUIDE.md` - Detailed setup, ChromeOS-specific help

### Visit the Project
- **GitHub**: https://github.com/entity12208/GeoPoliticalDomination
- **Report Issues**: https://github.com/entity12208/GeoPoliticalDomination/issues
- **Discussions**: https://github.com/entity12208/GeoPoliticalDomination/discussions

---

## 💾 Where Is the Game Installed?

### Windows 🪟
```
C:\Users\[YourUsername]\GeoPoliticalDomination
```

Example: `C:\Users\John\GeoPoliticalDomination`

### macOS/Linux/ChromeOS 🍎 🐧
```
~/GeoPoliticalDomination
```

Or: `/Users/[YourUsername]/GeoPoliticalDomination` (macOS)
Or: `/home/[YourUsername]/GeoPoliticalDomination` (Linux)

---

## 🎵 Playing Again Later

### Windows 🪟
- Run the installer again: double-click `gpd-setup-windows.cmd`
- OR navigate to your installation folder and run `client_local.py`

### macOS/Linux/ChromeOS 🍎 🐧
- Run the installer again:
  ```
  bash ~/Downloads/gpd-setup-unix.sh
  ```
- OR open Terminal and run:
  ```
  cd ~/GeoPoliticalDomination
  source .venv/bin/activate
  python3 client_local.py
  ```

---

## 🗑️ Want to Uninstall?

### Windows 🪟
Simply delete the folder: `C:\Users\[YourUsername]\GeoPoliticalDomination`

### macOS/Linux/ChromeOS 🍎 🐧
Open Terminal and run:
```
rm -rf ~/GeoPoliticalDomination
```

---

## ✨ Key Benefits

✅ **Smallest download possible** - Just one tiny file (4-6 KB)
✅ **Automatic setup** - No manual configuration needed
✅ **Always latest code** - Downloads from GitHub automatically
✅ **Self-contained** - Won't mess with your system
✅ **Easy to uninstall** - Just delete one folder
✅ **Works everywhere** - Windows, Mac, Linux, ChromeOS

---

## 🚀 You're All Set!

That's it! You're ready to enjoy GeoPolitical Domination! 🎮

If you have any questions or run into issues, check the detailed guides or visit the GitHub repository.

Happy conquering! 🌍
