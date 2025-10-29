@echo off
REM GeoPolitical Domination - Standalone Windows Installer
REM This file installs and runs the complete game from GitHub with NO other files needed!
REM Simply double-click this file and follow the prompts.

setlocal enabledelayedexpansion

REM Colors and formatting
set "REPO_URL=https://github.com/entity12208/GeoPoliticalDomination.git"
set "INSTALL_DIR=%USERPROFILE%\GeoPoliticalDomination"
set "TEMP_DIR=%TEMP%\gpd-setup-temp"

cls
echo ================================================================
echo  GeoPolitical Domination - Standalone Installer for Windows
echo ================================================================
echo.
echo This installer will:
echo   1. Download the game from GitHub
echo   2. Install Python (if needed^)
echo   3. Set up the game environment
echo   4. Launch the game
echo.
echo Installation directory: %INSTALL_DIR%
echo.
pause

REM Step 1: Check Python
echo [1/5] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3 is not installed or not in PATH
    echo.
    echo Please install Python 3.13+ from https://www.python.org/downloads/
    echo IMPORTANT: Check "Add Python to PATH" during installation
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo.

REM Step 2: Check Git
echo [2/5] Checking Git installation...
git --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Git not found. Will download ZIP instead.
    set "USE_ZIP=1"
) else (
    git --version
    set "USE_ZIP=0"
)
echo.

REM Step 3: Download game
echo [3/5] Downloading game from GitHub...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

if !USE_ZIP! equ 1 (
    echo Downloading as ZIP file...
    if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"
    cd /d "%TEMP_DIR%"
    
    powershell -Command "iwr https://github.com/entity12208/GeoPoliticalDomination/archive/main.zip -OutFile main.zip" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to download game
        pause
        exit /b 1
    )
    
    tar -xf main.zip
    if errorlevel 1 (
        echo [ERROR] Failed to extract game files
        pause
        exit /b 1
    )
    
    xcopy "GeoPoliticalDomination-main\*" "%INSTALL_DIR%" /E /I /Y >nul
    if errorlevel 1 (
        echo [ERROR] Failed to copy game files
        pause
        exit /b 1
    )
) else (
    cd /d "%INSTALL_DIR%" 2>nul
    if errorlevel 1 (
        git clone "%REPO_URL%" "%INSTALL_DIR%" >nul 2>&1
    ) else (
        git pull >nul 2>&1
    )
    if errorlevel 1 (
        echo [ERROR] Failed to download game with Git
        pause
        exit /b 1
    )
)
echo Game downloaded successfully!
echo.

REM Step 4: Set up environment
echo [4/5] Setting up Python environment...
cd /d "%INSTALL_DIR%"

REM Create virtual environment
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate venv and install dependencies
echo Installing dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
if exist "requirements.txt" (
    pip install -r requirements.txt -q
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
)
echo Environment set up successfully!
echo.

REM Step 5: Launch game
echo [5/5] Launching game...
echo.
python client_local.py

REM After game closes, ask to open launcher or exit
echo.
echo.
echo Game closed. Would you like to launch it again?
echo.
echo [1] Play again
echo [2] Exit
echo.
set /p "choice=Enter your choice (1 or 2): "

if "%choice%"=="1" (
    python client_local.py
    goto :eof
) else (
    echo Goodbye!
    exit /b 0
)
