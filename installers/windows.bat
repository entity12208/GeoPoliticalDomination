@echo off
setlocal enabledelayedexpansion

:: Debug log
set "DEBUGLOG=%TEMP%\geopolitical_setup_debug.log"
echo --- START %DATE% %TIME% --- > "%DEBUGLOG%"

echo =====================================================>> "%DEBUGLOG%"
echo GeoPoliticalDomination - Windows setup helper (debug) >> "%DEBUGLOG%"
echo =====================================================>> "%DEBUGLOG%"

:: Helper to log messages
:log
echo [%DATE% %TIME%] %* >> "%DEBUGLOG%"
echo %* 
goto :eof

:: Improved fail handler
:fail
set "MSG=%~1"
if not defined MSG set "MSG=(no message provided)"
echo. 
echo *** ERROR: %MSG%
echo Errorlevel: %ERRORLEVEL%
echo Current dir: %CD%
echo Debug log path: %DEBUGLOG%
echo.
echo --- Last 64 lines of debug log --- 
for /f "tokens=*" %%L in ('powershell -NoProfile -Command "Get-Content -Tail 64 -Path '%DEBUGLOG%' -ErrorAction SilentlyContinue"') do @echo %%L
echo.
pause
endlocal
exit /b 1

:: start logging and echo
call :log "Starting setup script."

:: Try to detect Python command
set "PYCMD="
for %%x in (python python3) do (
    where %%x >nul 2>nul
    if !ERRORLEVEL! EQU 0 if not defined PYCMD (
        set "PYCMD=%%x"
        call :log "Detected python executable: %%x"
    )
)

:: Detect if we're in repo (basic check)
set "IN_REPO=0"
if exist "client_online.py" if exist "client_local.py" (
    set "IN_REPO=1"
    call :log "client_online.py & client_local.py found -> IN_REPO=1"
) else (
    call :log "Not in repo (client_online.py / client_local.py missing)"
)

:: Detect if venv active
set "VENV_ACTIVE=0"
if defined VIRTUAL_ENV (
    set "VENV_ACTIVE=1"
    call :log "VIRTUAL_ENV set -> venv appears active: %VIRTUAL_ENV%"
)

:: Function to check requirements (will set REQ_OK)
:check_requirements
set "REQ_OK=0"
if not exist "requirements.txt" (
    set "REQ_OK=1"
    call :log "requirements.txt not found -> treat as OK"
    goto :eof
)
if not defined PYCMD (
    if defined VIRTUAL_ENV (
        if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
            set "PYCMD=%VIRTUAL_ENV%\Scripts\python.exe"
            call :log "Using venv python at %PYCMD% for requirements check"
        )
    )
)
if not defined PYCMD (
    call :log "No python available to check requirements"
    set "REQ_OK=0"
    goto :eof
)

:: Write small python script to TEMP to check missing packages
set "PYCHK=%TEMP%\check_reqs_dbg.py"
(
    echo import re,sys
    echo from pathlib import Path
    echo try:
    echo     import importlib.metadata as md
    echo except Exception:
    echo     md=None
    echo p=Path("requirements.txt")
    echo if not p.exists():
    echo     print("")
    echo     sys.exit(0)
    echo lines=[l.strip() for l in p.read_text().splitlines() if l.strip() and not l.strip().startswith("#")]
    echo def norm(l): return re.split('[<=>;\\[]', l)[0].strip()
    echo missing=[]
    echo for l in lines:
    echo     pkg=norm(l)
    echo     if not pkg: continue
    echo     ok=False
    echo     if md:
    echo         try:
    echo             md.version(pkg); ok=True
    echo         except Exception:
    echo             ok=False
    echo     if not ok:
    echo         try:
    echo             __import__(pkg); ok=True
    echo         except Exception:
    echo             ok=False
    echo     if not ok:
    echo         missing.append(pkg)
    echo print(",".join(missing))
) > "%PYCHK%"

call :log "Running requirements-check using %PYCMD% (script %PYCHK%)"
for /f "usebackq delims=" %%R in (`"%PYCMD%" "%PYCHK%" 2^>>"%DEBUGLOG%" ^| tee -a "%DEBUGLOG%"`) do set "MISSING=%%R"
if not defined MISSING set "MISSING="
if "%MISSING%"=="" (
    set "REQ_OK=1"
    call :log "No missing packages detected (heuristic)."
) else (
    set "REQ_OK=0"
    call :log "Missing packages: %MISSING%"
)
del "%PYCHK%" 2>>"%DEBUGLOG%" || call :log "Couldn't delete temp check script"

:: If already in repo + venv active + requirements OK -> skip to play prompt
if "%IN_REPO%"=="1" (
    if "%VENV_ACTIVE%"=="1" (
        if "%REQ_OK%"=="1" (
            call :log "Already in repo, venv active, and requirements satisfied -> skipping setup steps."
            goto choose_play
        ) else (
            call :log "In repo and venv active but requirements missing -> will install."
        )
    )
)

:: If not in repo, we're probably in the installers directory - go up one level
if "%IN_REPO%"=="0" (
    call :log "Repository not found in current directory."
    :: Check if we're in installers subdirectory
    if exist "..\client_online.py" if exist "..\client_local.py" (
        call :log "Found repo in parent directory - moving there."
        cd .. 2>>"%DEBUGLOG%" || call :fail "Failed to change to parent directory."
        set "IN_REPO=1"
    ) else (
        call :log "Game files not found locally. Offering to download from GitHub."
        echo.
        echo =====================================================
        echo Game files not found!
        echo =====================================================
        echo.
        echo This installer can download GeoPolitical Domination 
        echo from GitHub: https://github.com/entity12208/GeoPoliticalDomination
        echo.
        choice /C YN /M "Would you like to download the game now?"
        if !ERRORLEVEL!==1 (
            call :download_from_github
            if exist "client_online.py" if exist "client_local.py" (
                set "IN_REPO=1"
                call :log "Successfully downloaded game from GitHub"
            ) else (
                call :fail "Download completed but game files not found. Please check manually."
            )
        ) else (
            call :fail "Cannot proceed without game files. Download manually or run from game directory."
        )
    )
)

:: Skip download function definition during normal flow
goto :skip_download_function

:download_from_github
call :log "Starting GitHub download..."
echo Downloading latest release from GitHub...
set "DOWNLOAD_DIR=%CD%"
set "ZIP_FILE=%TEMP%\gpd_download.zip"
set "GITHUB_ZIP_URL=https://github.com/entity12208/GeoPoliticalDomination/archive/refs/heads/main.zip"

powershell -Command "Try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%GITHUB_ZIP_URL%' -OutFile '%ZIP_FILE%' -UseBasicParsing; Exit 0 } Catch { Write-Host $_.Exception.Message; Exit 1 }" >> "%DEBUGLOG%" 2>&1
if not exist "%ZIP_FILE%" (
    echo Download failed. Please check your internet connection.
    call :log "Download failed - ZIP file not created"
    goto :eof
)

echo Extracting files...
powershell -Command "Try { Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%TEMP%\gpd_extract' -Force; Exit 0 } Catch { Write-Host $_.Exception.Message; Exit 1 }" >> "%DEBUGLOG%" 2>&1

:: Move files from extracted folder to current directory
for /d %%D in ("%TEMP%\gpd_extract\GeoPoliticalDomination-*") do (
    call :log "Moving files from %%D to %DOWNLOAD_DIR%"
    xcopy "%%D\*" "%DOWNLOAD_DIR%\" /E /I /Y >> "%DEBUGLOG%" 2>&1
)

:: Clean up
del "%ZIP_FILE%" 2>>"%DEBUGLOG%"
rd /s /q "%TEMP%\gpd_extract" 2>>"%DEBUGLOG%"

echo Download and extraction complete!
call :log "Download completed successfully"
goto :eof

:skip_download_function

call :log "Current working dir: %CD%"

:: Ensure PYCMD is defined/usable
if not defined PYCMD (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PYCMD=python"
        call :log "Detected python on PATH"
    ) else (
        where winget >nul 2>nul
        if %ERRORLEVEL%==0 (
            call :log "winget available -> attempting install of Python"
            winget install --id Python.Python.3 -e --silent >> "%DEBUGLOG%" 2>&1 || call :fail "winget failed to install Python."
            set "PYCMD=python"
        ) else (
            call :log "winget not available -> attempting direct download of python installer"
            set "PY_EXE=%TEMP%\python-installer.exe"
            powershell -Command "Try { Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile '%PY_EXE%'; Exit 0 } Catch { Exit 1 }" >> "%DEBUGLOG%" 2>&1
            if exist "%PY_EXE%" (
                "%PY_EXE%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_pip=1 >> "%DEBUGLOG%" 2>&1 || call :fail "Python installer failed; see debug log."
                set "PYCMD=python"
            ) else (
                call :fail "Could not find or install Python. Install manually and re-run."
            )
        )
    )
)

:: verify python works
%PYCMD% --version >> "%DEBUGLOG%" 2>&1 || call :fail "Python not usable after install attempt."

call :log "Python available: "
%PYCMD% --version 2>>"%DEBUGLOG%" | findstr /r /c:"Python" || call :log "Python version output may be in debug log."

:: venv handling
if exist "venv\Scripts\activate.bat" (
    call :log "venv found."
    if defined VIRTUAL_ENV (
        call :log "venv already active in this session."
    ) else (
        call :log "Activating venv..."
        call venv\Scripts\activate.bat >> "%DEBUGLOG%" 2>&1 || call :fail "Failed to activate venv (see debug log)."
        set "VENV_ACTIVE=1"
    )
) else (
    call :log "No venv found -> creating one."
    %PYCMD% -m venv venv >> "%DEBUGLOG%" 2>&1 || call :fail "Failed to create venv."
    call venv\Scripts\activate.bat >> "%DEBUGLOG%" 2>&1 || call :fail "Failed to activate newly created venv."
    set "VENV_ACTIVE=1"
)

:: ensure pip
python -m pip --version >> "%DEBUGLOG%" 2>&1 || (python -m ensurepip --upgrade >> "%DEBUGLOG%" 2>&1 || call :log "ensurepip didn't run cleanly")

:: Install requirements if missing
call :check_requirements
if "%REQ_OK%"=="1" (
    call :log "Requirements satisfied."
) else (
    call :log "Installing requirements from requirements.txt"
    python -m pip install -r requirements.txt >> "%DEBUGLOG%" 2>&1 || call :fail "pip install failed (see debug log)."
    call :log "pip install completed"
)

:choose_play
echo.
echo Choose play mode:
choice /C O F /M "Do you want to play online (O) or offline (F)? (O=online, F=offline)"
if %ERRORLEVEL%==1 (
    call :log "Launching python client_online.py"
    python client_online.py >> "%DEBUGLOG%" 2>&1 || call :fail "client_online.py crashed or returned non-zero (see debug log)."
) else (
    call :log "Launching python client_local.py"
    python client_local.py >> "%DEBUGLOG%" 2>&1 || call :fail "client_local.py crashed or returned non-zero (see debug log)."
)

call :log "Process finished successfully."
endlocal
exit /b 0
