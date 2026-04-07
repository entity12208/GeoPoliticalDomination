@echo off
REM setup.bat — One-command installer for GeoPolitical Domination on Windows
REM
REM Install from PowerShell:
REM   irm https://raw.githubusercontent.com/entity12208/GeoPoliticalDomination/main/setup.bat -OutFile setup.bat; .\setup.bat
REM
REM Or if you already have the repo, just double-click this file.

setlocal enabledelayedexpansion

echo ========================================
echo   GeoPolitical Domination — Setup
echo ========================================
echo.

REM --- Detect if we're in an existing install ---
set "INSTALL_DIR=%~dp0"
if exist "%INSTALL_DIR%client.py" (
    echo [*] Running from existing install: %INSTALL_DIR%
    goto :setup_venv
)

REM --- Fresh install ---
set "INSTALL_DIR=%USERPROFILE%\GeoPoliticalDomination"
echo [*] Fresh install to: %INSTALL_DIR%

REM --- Check for Python ---
where python >nul 2>&1
if %errorlevel% neq 0 (
    where python3 >nul 2>&1
    if %errorlevel% neq 0 (
        echo [!] Python not found.
        echo     Please install Python 3.8+ from https://www.python.org/downloads/
        echo     IMPORTANT: Check "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1
    )
    set "PY=python3"
) else (
    set "PY=python"
)

REM --- Verify Python version ---
%PY% -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)" 2>nul
if %errorlevel% neq 0 (
    echo [!] Python 3.8+ required. Please update Python.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('%PY% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PY_VER=%%i
echo [OK] Python %PY_VER%

REM --- Download latest release ---
echo.
echo [*] Downloading latest release...

set "TEMP_ZIP=%TEMP%\gpd_download.zip"
set "TEMP_DIR=%TEMP%\gpd_extract"
set "API_URL=https://api.github.com/repos/entity12208/GeoPoliticalDomination/releases/latest"

REM Try to get release zip URL via Python (more reliable than curl on Windows)
for /f "tokens=*" %%u in ('%PY% -c "import urllib.request,json; d=json.loads(urllib.request.urlopen('%API_URL%').read()); print(d.get('zipball_url',''))" 2^>nul') do set "ZIP_URL=%%u"

if "!ZIP_URL!"=="" (
    echo [!] No releases found, downloading main branch...
    set "ZIP_URL=https://github.com/entity12208/GeoPoliticalDomination/archive/refs/heads/main.zip"
) else (
    echo [OK] Found latest release
)

echo [*] Downloading...
%PY% -c "import urllib.request; urllib.request.urlretrieve('!ZIP_URL!', r'%TEMP_ZIP%'); print('[OK] Downloaded')"
if %errorlevel% neq 0 (
    echo [ERROR] Download failed.
    pause
    exit /b 1
)

echo [*] Extracting...
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
%PY% -c "import zipfile; zipfile.ZipFile(r'%TEMP_ZIP%').extractall(r'%TEMP_DIR%'); print('[OK] Extracted')"

REM Find the extracted folder
for /d %%d in ("%TEMP_DIR%\*") do set "EXTRACTED=%%d"
if not defined EXTRACTED (
    echo [ERROR] Extraction failed.
    pause
    exit /b 1
)

REM Copy to install dir
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
xcopy /s /e /y /q "%EXTRACTED%\*" "%INSTALL_DIR%\" >nul
del "%TEMP_ZIP%" 2>nul
rmdir /s /q "%TEMP_DIR%" 2>nul
echo [OK] Installed to %INSTALL_DIR%

:setup_venv
cd /d "%INSTALL_DIR%"

REM --- Check Python again (in case we came from existing install) ---
where python >nul 2>&1
if %errorlevel% neq 0 (
    set "PY=python3"
) else (
    set "PY=python"
)

REM --- Verify client.py exists ---
if not exist "client.py" (
    echo [ERROR] client.py not found in %INSTALL_DIR%
    pause
    exit /b 1
)

REM --- Create venv ---
if not exist ".venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment...
    %PY% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        echo         Try: %PY% -m pip install --user virtualenv
        pause
        exit /b 1
    )
)

REM --- Activate venv ---
call .venv\Scripts\activate.bat
echo [OK] Virtual environment active

REM --- Install dependencies ---
echo [*] Installing Python packages...
pip install --upgrade pip -q 2>nul
if exist "requirements.txt" (
    pip install -r requirements.txt -q
) else (
    pip install pygame-ce requests -q
)
if %errorlevel% neq 0 (
    echo [!] pip install failed, retrying...
    pip install pygame-ce requests -q
)
echo [OK] Dependencies installed

REM --- Verify pygame ---
python -c "import pygame; print(f'[OK] pygame-ce {pygame.ver}')" 2>nul
if %errorlevel% neq 0 (
    echo [!] pygame import failed, reinstalling...
    pip install --force-reinstall pygame-ce -q
    python -c "import pygame; print(f'[OK] pygame-ce {pygame.ver}')"
)

REM --- Create play.bat ---
(
    echo @echo off
    echo cd /d "%%~dp0"
    echo if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat
    echo python client.py %%*
) > "%INSTALL_DIR%\play.bat"

echo.
echo ========================================
echo   Setup complete!
echo ========================================
echo.
echo   To play, run:
echo     cd %INSTALL_DIR%
echo     play.bat
echo.
echo   Or double-click play.bat in:
echo     %INSTALL_DIR%
echo.
pause
