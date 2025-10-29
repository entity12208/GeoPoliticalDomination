---
description: Repository Information Overview
alwaysApply: true
---

# GeoPolitical Domination (GPD) - Complete Project Information

## Summary
GeoPolitical Domination is a turn-based strategy game built with Python 3.13 and Pygame-CE. Players compete to conquer territories on a world map by managing money, armies, and diplomatic actions. The project supports local single/multiplayer and online multiplayer via Firebase/Firestore synchronization with a heuristic AI bot for single-player gameplay.

## Repository Structure
**Single Python Application** with multiple client implementations:
- **client_local.py** — Local-only game client with bot support
- **client_online.py** — Online multiplayer client with Firestore sync
- **heuristic_bot.py** — Local AI decision engine
- **firebase_sync.py** — Firestore controller for online game state
- **assets/** — Contains countries.geojson (world map data)
- **installers/** — Complete installation package for all platforms
- **config.txt, rules.txt, pin_overrides.json** — Game configuration files

## Language & Runtime
**Language**: Python  
**Version**: 3.13.9  
**Package Manager**: pip  
**Build System**: None (standard Python application)

## Dependencies
**Main Libraries**:
- pygame-ce — Graphics and UI rendering
- google-cloud-firestore — Online multiplayer state sync
- google-api-core — Google Cloud API support
- requests — HTTP client for GeoJSON data

**Installation**: Virtual environment with pip

## Build & Installation
```bash
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# macOS/Linux/ChromeOS Bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Standalone Installers (NEW!)
**One-file installers that download, setup, and run everything from GitHub:**

### Windows
- **File**: `installers/gpd-setup-windows.cmd` (3.7 KB)
- **Usage**: Double-click and follow prompts
- **Automatic setup**: Python, dependencies, GitHub clone, virtual environment
- **Launches**: Interactive menu for offline/online play

### macOS/Linux/ChromeOS
- **File**: `installers/gpd-setup-unix.sh` (5.8 KB)
- **Usage**: `bash gpd-setup-unix.sh`
- **Auto-detect OS**: Homebrew (macOS) vs apt (Linux)
- **Installs**: SDL2 graphics libraries, Python dependencies
- **Launches**: Interactive menu for offline/online play

## Main Entry Points
- **client_local.py** — Recommended for single/local multiplayer (no credentials needed)
- **client_online.py** — Online multiplayer (requires gpd_secrets.txt with Firebase service account)

## Configuration Files
- **config.txt** — UI defaults and player settings
- **rules.txt** — Game rule definitions
- **pin_overrides.json** — Country pin location adjustments
- **gpd_secrets.txt** — Firebase service account JSON (online mode only)
- **assets/countries.geojson** — World map polygons (auto-downloaded if missing)

## Key Modules
- **firebase_sync.py** — FirebaseController class handles Firestore transactions, game creation, state submission, listeners
- **heuristic_bot.py** — AI decision function for local gameplay

## Installation Package
**Location**: `installers/` directory (41 KB total)

**Included Files**:
- 2 Standalone installers (Windows + Unix for all platforms)
- 6 Comprehensive guides (README, QUICKSTART, platform-specific GUIDEs)
- 1 Technical summary (INSTALLERS_SUMMARY)
- 1 User download guide (HOW_TO_DOWNLOAD_AND_USE)

**Features**:
- Zero-file distribution (just download one installer per platform)
- Automatic Python/dependency installation
- GitHub auto-download with Git or ZIP fallback
- Isolated virtual environment
- Interactive play menu (offline/online selection)
- Comprehensive error handling
- Cross-platform support: Windows, macOS, Linux, ChromeOS

## No Testing Framework
Smoke checks via module imports recommended. Game validation through interactive play.

## Supported Platforms
- Windows 7+
- macOS 10.13+
- Linux (all distributions)
- ChromeOS with Crostini enabled

## Notes
- Project is intentionally compact and self-contained
- Online mode requires valid Firebase service account credentials
- GeoJSON map auto-downloads (requires requests library)
- Installation package enables zero-friction user onboarding
- Virtual environment isolates all dependencies
