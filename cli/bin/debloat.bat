@echo off
setlocal EnableDelayedExpansion

set "BIN_DIR=%~dp0"
set "CLI_DIR=%BIN_DIR%.."
set "ROOT_DIR=%BIN_DIR%..\.."

:: Installed flat layout (VERSION beside bin\) first, then the repo root.
:: Paths stay quoted inside ( ) blocks: an unquoted ")" from a folder like "name (1)" ends the block.
if exist "%CLI_DIR%\VERSION" (
    set /p APP_VERSION=<"%CLI_DIR%\VERSION"
    cd /d "%CLI_DIR%"
) else if exist "%ROOT_DIR%\VERSION" (
    set /p APP_VERSION=<"%ROOT_DIR%\VERSION"
    cd /d "%ROOT_DIR%"
) else (
    echo [ERROR] VERSION file not found at "%CLI_DIR%\VERSION" or "%ROOT_DIR%\VERSION"
    exit /b 1
)

title AI-Phone-Debloater v%APP_VERSION%
echo ========================================================
echo   AI-Phone-Debloater v%APP_VERSION% (No Root - Safe Debloat)
echo ========================================================
echo.

:: Detect Python 3.11+
set "PY="
if exist "%CLI_DIR%\tools\python\python.exe" set "PY=%CLI_DIR%\tools\python\python.exe"
if not defined PY (
    for %%p in (python python3 py) do (
        if not defined PY (
            %%p -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
            if not errorlevel 1 set "PY=%%p"
        )
    )
)
:: If Python is not found, auto-bootstrap via PowerShell
if not defined PY (
    echo [INFO] Python 3.11 or newer not found on system. Auto-downloading Python 3.12...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$ErrorActionPreference = 'Stop';" ^
        "$installer = Join-Path $env:TEMP 'python-installer.exe';" ^
        "$url = 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe';" ^
        "Write-Host '[INFO] Downloading official Python 3.12 installer...';" ^
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;" ^
        "(New-Object Net.WebClient).DownloadFile($url, $installer);" ^
        "if ((Get-AuthenticodeSignature $installer).Status -ne 'Valid') { Remove-Item $installer -Force; Write-Host '[ERROR] Python installer signature is not valid; not running it.'; exit 1 };" ^
        "Write-Host '[INFO] Installing Python silently...';" ^
        "$p = Start-Process -FilePath $installer -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0' -Wait -PassThru;" ^
        "Remove-Item $installer -Force -ErrorAction SilentlyContinue;" ^
        "if ($p.ExitCode -notin 0, 3010) { Write-Host ('[ERROR] Python installer failed with exit code ' + $p.ExitCode); exit 1 };" ^
        "Write-Host '[OK] Python installation complete.'"
    set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts"
    for %%p in (python python3 py) do (
        if not defined PY (
            %%p -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
            if not errorlevel 1 set "PY=%%p"
        )
    )
)

if not defined PY (
    echo [ERROR] Python 3.11 or newer could not be found or installed.
    echo Please install Python 3.11 or newer manually from https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python runtime: %PY%

:: Detect or bootstrap ADB
if exist "%CLI_DIR%\tools\platform-tools\adb.exe" set "PATH=%CLI_DIR%\tools\platform-tools;%PATH%"
where adb >nul 2>&1 || (
    echo [INFO] ADB not found on PATH. Auto-downloading Google Android Platform-Tools...
    if not exist "%CLI_DIR%\tools" mkdir "%CLI_DIR%\tools"
    "%PY%" -c "import urllib.request, zipfile, io, sys; print('[INFO] Fetching platform-tools...'); req=urllib.request.Request('https://dl.google.com/android/repository/platform-tools-latest-windows.zip',headers={'User-Agent':'Mozilla/5.0'}); data=urllib.request.urlopen(req, timeout=60).read(); print('[INFO] Extracting...'); zipfile.ZipFile(io.BytesIO(data)).extractall(sys.argv[1]); print('[OK] Download complete.')" "%CLI_DIR%\tools"
    if exist "%CLI_DIR%\tools\platform-tools\adb.exe" (
        set "PATH=%CLI_DIR%\tools\platform-tools;%PATH%"
        echo [OK] ADB platform-tools installed.
    ) else (
        echo [WARNING] ADB download failed. Install Android platform-tools and put adb on PATH, or pass --adb-path.
    )
)

:: Launch debloat engine: all arguments pass straight through, none means --interactive.
:: The call stays outside ( ) blocks so an argument containing ")" cannot end one.
echo Launching debloat engine...
echo.
set "ENGINE_ARGS=%*"
set "DEFAULT_ARG="
if not defined ENGINE_ARGS set "DEFAULT_ARG=--interactive"
"%PY%" "%CLI_DIR%\src\debloat_engine.py" %* %DEFAULT_ARG%
set "RC=%ERRORLEVEL%"
echo.
echo ========================================================
echo Debloat engine finished.
echo ========================================================
if not defined ENGINE_ARGS pause
exit /b %RC%
