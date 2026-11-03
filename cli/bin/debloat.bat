@echo off
setlocal EnableExtensions
set "BIN_DIR=%~dp0"
set "CLI_DIR=%BIN_DIR%.."
set "ROOT_DIR=%BIN_DIR%..\.."
cd /d "%ROOT_DIR%"

:: 1. Bootstrap Python 3 if missing (required to run the debloat engine)
if not exist "%CLI_DIR%\tools\python\python.exe" (
    echo [INFO] Python not found in tools folder. Checking system PATH...
    for %%p in (python py python3) do (
        if not defined PY (
            %%p -c "import sys; sys.exit(0 if sys.version_info[0]>=3 else 1)" >nul 2>&1
            if not errorlevel 1 set "PY=%%p" & goto :pyfound
        )
    )
    :pyfound
    if not defined PY (
        echo [ERROR] Python 3 not found on system PATH. Please install Python 3 from https://www.python.org/downloads/
        pause
        exit /b 1
    )
) else (
    set "PY=%CLI_DIR%\tools\python\python.exe"
)
echo [OK] Python runtime: %PY%

:: 2. Check and bootstrap ADB
if exist "%CLI_DIR%\tools\platform-tools\adb.exe" (
    set "PATH=%CLI_DIR%\tools\platform-tools;%PATH%"
)
where adb >nul 2>&1
if errorlevel 1 (
    echo [INFO] ADB not found on system. Auto-downloading Google Android Platform-Tools...
    if not exist "%CLI_DIR%\tools" mkdir "%CLI_DIR%\tools"
    "%PY%" -c "import urllib.request, zipfile, io, sys; print('[INFO] Fetching platform-tools from Google...'); req = urllib.request.urlopen(urllib.request.Request('https://dl.google.com/android/repository/platform-tools-latest-windows.zip', headers={'User-Agent': 'Mozilla/5.0'})); data = urllib.request.urlopen(req).read(); print('[INFO] Extracting platform-tools archive...'); zipfile.ZipFile(io.BytesIO(data)).extractall(sys.argv[1]); print('[OK] Download complete.')" "%CLI_DIR%\tools"
    if exist "%CLI_DIR%\tools\platform-tools\adb.exe" (
        set "PATH=%CLI_DIR%\tools\platform-tools;%PATH%"
        echo [OK] ADB platform-tools installed successfully.
    ) else (
        echo [WARNING] Automatic ADB download failed. Please install ADB manually or put it on PATH.
    )
) else (
    echo [OK] ADB runtime detected.
)

echo.
echo Launching debloat engine...
echo.

set "ENGINE_ARGS=%*"
if defined ENGINE_ARGS (
    "%PY%" "%CLI_DIR%\src\debloat_engine.py" %*
) else (
    "%PY%" "%CLI_DIR%\src\debloat_engine.py" --interactive
)
set "RC=%ERRORLEVEL%"

echo.
echo ========================================================
echo Debloat engine finished.
echo ========================================================
:: Only pause for double-click / interactive launches
if not defined ENGINE_ARGS pause
exit /b %RC%