@echo off
setlocal EnableExtensions
set "BIN_DIR=%~dp0"
set "CLI_DIR=%BIN_DIR%.."
set "ROOT_DIR=%BIN_DIR%..\.."
cd /d "%ROOT_DIR%"

:: Read version from VERSION file
if exist "%ROOT_DIR%\VERSION" (
    set /p APP_VERSION=<"%ROOT_DIR%\VERSION"
) else if exist "%CLI_DIR%\VERSION" (
    set /p APP_VERSION=<"%CLI_DIR%\VERSION"
) else (
    echo [ERROR] VERSION file not found at %ROOT_DIR%\VERSION
    exit /b 1
)

title AI-Phone-Debloater v%APP_VERSION%

echo ========================================================
echo   AI-Phone-Debloater v%APP_VERSION% (No Root - Safe Debloat)
echo ========================================================
echo.

:: 1. Detect or bootstrap Python 3
set "PY="
if exist "%CLI_DIR%\tools\python\python.exe" (
    set "PY=%CLI_DIR%\tools\python\python.exe"
)

if not defined PY (
    for %%p in (python python3 py) do (
        if not defined PY (
            %%p -c "import sys; sys.exit(0 if sys.version_info[0]>=3 else 1)" >nul 2>&1
            if not errorlevel 1 set "PY=%%p"
        )
    )
)

:: If Python is not found, auto-bootstrap via PowerShell
if not defined PY (
    echo [INFO] Python 3 not found on system. Auto-downloading Python...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$ErrorActionPreference = 'Stop';" ^
        "$installer = Join-Path $env:TEMP 'python-installer.exe';" ^
        "$url = 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe';" ^
        "Write-Host '[INFO] Downloading official Python 3.12 installer...';" ^
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;" ^
        "(New-Object Net.WebClient).DownloadFile($url, $installer);" ^
        "Write-Host '[INFO] Installing Python silently...';" ^
        "Start-Process -FilePath $installer -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0' -Wait;" ^
        "Remove-Item $installer -Force -ErrorAction SilentlyContinue;" ^
        "Write-Host '[OK] Python installation complete.'"
    )
    echo [INFO] Python 3 installed but not on PATH yet; refreshing PATH...
    set "PATH=%PATH%;C:\Python312;C:\Python312\Scripts;C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312;C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\Scripts"
    for %%p in (python python3 py) do (
        if not defined PY (
            %%p -c "import sys; sys.exit(0 if sys.version_info[0]>=3 else 1)" >nul 2>&1
            if not errorlevel 1 set "PY=%%p"
        )
    )
)

if not defined PY (
    echo [ERROR] Python 3 could not be found or installed.
    echo Please install Python 3 manually from https://www.python.org/downloads/
    pause
    exit /b 1
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
    "%PY%" -c "import urllib.request, zipfile, io, sys; print('[INFO] Fetching platform-tools from Google...'); req = urllib.request.Request('https://dl.google.com/android/repository/platform-tools-latest-windows.zip', headers={'User-Agent': 'Mozilla/5.0'}); data = urllib.request.urlopen(req).read(); print('[INFO] Extracting platform-tools archive...'); zipfile.ZipFile(io.BytesIO(data)).extractall(sys.argv[1]); print('[OK] Download complete.')" "%CLI_DIR%\tools"
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
