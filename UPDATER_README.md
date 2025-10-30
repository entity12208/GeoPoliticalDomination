# GeoPolitical Domination - Updater Guide

## 🔄 Auto-Updater System

The GPD updater automatically checks for new releases from GitHub and allows you to easily update your game.

### Repository
https://github.com/entity12208/GeoPoliticalDomination

---

## 📥 Using the Updater

### Method 1: Automatic (via Client Online)

1. Launch the online client:
   ```bash
   python client_online.py
   ```

2. If an update is available, you'll see a **yellow notification box** in the bottom-right corner:
   - Shows current version → latest version
   - Click **"Update Now"** to launch the updater
   - Click **"Ignore"** to dismiss the notification

3. The updater will open in a new window
   - Your game will continue running
   - Close the game before updating

### Method 2: Manual (Standalone)

1. Run the updater directly:
   ```bash
   python updater.py
   ```

2. You'll see:
   - List of all available releases
   - Current version
   - Options to install latest or specific version

3. Choose your option:
   - `L` - Install latest release
   - `1-N` - Install specific release by number
   - `Q` - Quit without updating

4. Confirm the update when prompted

---

## 🛡️ Safety Features

### Automatic Backups

Before updating, the updater **automatically backs up** these files:
- `config.txt`
- `gpd_secrets.txt`
- `pin_overrides.json`
- `version.txt`

Backups are saved to: `backup_before_update/`

### Preserved Configuration

Your personal settings are **never overwritten**:
- Player credentials
- Custom configurations
- Pin overrides

---

## 📦 What Gets Updated

The updater downloads and extracts:
- ✅ All game code files (`client_*.py`, `firebase_sync.py`, etc.)
- ✅ Bot AI files (`heuristic_bot.py`, `bot_playstyles.py`)
- ✅ Installer scripts (`installers/`)
- ✅ Assets (if included in release)
- ✅ Requirements and documentation

The updater **preserves**:
- ❌ Your config files
- ❌ Your secrets/credentials
- ❌ Your virtual environment
- ❌ Custom pin overrides

---

## 🔍 Version Tracking

Your current version is stored in `version.txt`:
```
v1.0.0
```

This file is:
- Created by the updater
- Used to check for new versions
- Automatically updated after successful updates

---

## 🚨 Troubleshooting

### Update Check Fails

**Problem**: "Failed to fetch releases"

**Solutions**:
1. Check your internet connection
2. Verify GitHub is accessible: https://github.com/entity12208/GeoPoliticalDomination
3. Wait a moment and try again (GitHub API rate limits)

### Download Fails

**Problem**: Download stops or fails during extraction

**Solutions**:
1. Check available disk space
2. Verify you have write permissions in the game directory
3. Try again (connection may have been interrupted)
4. Download manually from GitHub and extract

### Updater Won't Launch

**Problem**: "Updater not available" message

**Solutions**:
1. Verify `updater.py` exists in game directory
2. Check Python installation is working
3. Try running manually: `python updater.py`

### Version Mismatch

**Problem**: Updater shows wrong current version

**Solutions**:
1. Check `version.txt` exists
2. Manually edit `version.txt` to correct version (e.g., `v1.0.0`)
3. If file is missing, updater will show "unknown"

---

## 🌐 Installers with Auto-Download

Both installers now support downloading the game from GitHub:

### Windows
```batch
.\installers\windows.bat
```

### macOS/Linux/ChromeOS
```bash
bash installers/unix.sh
```

If game files aren't found, installers will:
1. Detect missing files
2. Offer to download from GitHub
3. Extract automatically
4. Set up dependencies
5. Launch the game

---

## 📋 Update Process Flow

```
1. Check for updates (automatic in client_online.py)
   ↓
2. Display notification if update available
   ↓
3. User clicks "Update Now"
   ↓
4. Updater launches in new window
   ↓
5. User selects version to install
   ↓
6. Updater backs up config files
   ↓
7. Download release from GitHub
   ↓
8. Extract files (preserving configs)
   ↓
9. Restore backed-up configs
   ↓
10. Update version.txt
   ↓
11. Restart game with new version
```

---

## 🛠️ Advanced Usage

### Silent Update Check

Check for updates programmatically:

```python
import updater

info = updater.silent_check()
if info['update_available']:
    print(f"Update available: {info['current']} → {info['latest']}")
```

### Download Specific Release

```python
import updater

releases = updater.fetch_releases()
if releases:
    specific_release = releases[2]  # 3rd release
    updater.download_and_extract_release(specific_release)
```

---

## 🎮 Recommended Workflow

1. **Regular Play**: Launch game normally
2. **Update Notification**: Note when updates appear
3. **Update When Convenient**: Update between gaming sessions
4. **Backup Important Data**: Keep backups of custom configurations
5. **Test After Update**: Verify game works after updating

---

## 📌 Important Notes

- **Close the game** before running updates
- Updates may take a few minutes depending on connection speed
- **Internet required** for update checks and downloads
- Old backups in `backup_before_update/` are overwritten each update
- GitHub releases must be published for updater to detect them

---

## 🆘 Support

If you encounter issues:

1. Check `version.txt` for current version
2. Look in `backup_before_update/` for recent backups
3. Review error messages in updater output
4. Manually download from GitHub if updater fails
5. Report issues on GitHub repository

---

## 📚 Related Documentation

- `README.md` - Main game documentation
- `CHANGELOG.md` - Feature changelog and version history
- `README_for_Developers.md` - Developer documentation

---

**Last Updated**: v2.1  
**Repository**: https://github.com/entity12208/GeoPoliticalDomination