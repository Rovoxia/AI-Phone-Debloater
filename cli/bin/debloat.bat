@echo off
setlocal EnableDelayedExpansion

set "BIN_DIR=%~dp0"
set "CLI_DIR=%BIN_DIR%.."
set "ROOT_DIR=%BIN_DIR%..\.."
cd /d "%ROOT_DIR%"

if exist "%ROOT_DIR%\VERSION" (
    set /p APP_VERSION=<"%ROOT_DIR%\VERSION"
) else (
    echo [ERROR] VERSION file not found at %ROOT_DIR%\VERSION
    exit /b 1
)

title AI-Phone-Debloater v%APP_VERSION%
echo ========================================================
echo   AI-Phone-Debloater v%APP_VERSION% (No Root - Safe Debloat)
echo ========================================================
echo.

:: Detect Python 3
set "PY="
if exist "%CLI_DIR%\tools\python\python.exe" set "PY=%CLI_DIR%\tools\python\python.exe"
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

:: Detect or bootstrap ADB
if exist "%CLI_DIR%\tools\platform-tools\adb.exe" set "PATH=%CLI_DIR%\tools\platform-tools;%PATH%"
where adb >nul 2>&1 || (
    echo [INFO] ADB not found on PATH. Auto-downloading Google Android Platform-Tools...
    if not exist "%CLI_DIR%\tools" mkdir "%CLI_DIR%\tools"
    "%PY%" -c "import urllib.request, zipfile, io, sys; print('[INFO] Fetching platform-tools...'); req=urllib.request.Request('https://dl.google.com/android/repository/platform-tools-latest-windows.zip',headers={'User-Agent':'Mozilla/5.0'}); data=urllib.request.urlopen(req).read(); print('[INFO] Extracting...'); zipfile.ZipFile(io.BytesIO(data)).extractall(sys.argv[1]); print('[OK] Download complete.')" "%CLI_DIR%\tools"
    if exist "%CLI_DIR%\tools\platform-tools\adb.exe" (
        set "PATH=%CLI_DIR%\tools\platform-tools;%PATH%"
        echo [OK] ADB platform-tools installed.
    ) else (
        echo [WARNING] ADB download failed. Install ADB manually or put it on PATH.
    )
)

:: Mode dispatch
if "%~1"=="dump-rules" goto :dump_rules
if "%~1"=="apply-rules" goto :apply_rules

:: Default: launch debloat engine
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
if not defined ENGINE_ARGS pause
exit /b %RC%

:dump_rules
if not exist "scans" mkdir scans
set MODEL=
set /p MODEL="Enter device model (e.g. pixel7a, xiaomi_note10): "
if "%MODEL%"=="" (echo ERROR: Model required. & goto end)
set MFR=
set /p MFR="Enter manufacturer (Xiaomi, Samsung, OnePlus, etc.): "
if "%MFR%"=="" (echo ERROR: Manufacturer required. & goto end)
set DUMP_FILE=scans\%MODEL%.txt

echo Dumping User 0 packages to %DUMP_FILE% ...
adb shell pm list packages -U --user 0 > "%DUMP_FILE%"
if errorlevel 1 (echo ERROR: ADB dump failed. Check device and USB debugging. & goto end)
echo Dump saved: %DUMP_FILE%

echo Generating draft rules for %MFR% ...
"%PY%" cli\tools\scan_to_rules.py --input "%DUMP_FILE%" --manufacturer "%MFR%" --output "cli\rules\%MODEL%.json" --drop-uncategorized
if errorlevel 1 (echo ERROR: Draft generation failed. & goto end)
echo Draft rule file: cli\rules\%MODEL%.json

echo Running validation ...
"%PY%" cli\tests\validate_rules.py
if errorlevel 1 (echo ERROR: Validation failed. Fix Tier-4 collisions before merge. & goto end)
echo Validation passed: Zero collisions.

echo Syncing web dataset ...
"%PY%" cli\generate_rules_dataset.py
if errorlevel 1 (echo ERROR: Dataset sync failed. & goto end)

echo Creating upload package ...
powershell -NoProfile -Command "Compress-Archive -Path 'scans\%MODEL%.txt','cli\rules\%MODEL%.json' -DestinationPath 'scans\%MODEL%-rules.zip' -Force"
echo Upload package: scans\%MODEL%-rules.zip
echo Upload this zip to GitHub for review and dataset build.
goto end

:apply_rules
set MANIFEST=%~2
if "%MANIFEST%"=="" (echo ERROR: Usage: debloat.bat apply-rules <manifest.json> [output.json] & goto end)
if not exist "%MANIFEST%" (echo ERROR: Manifest not found: %MANIFEST% & goto end)
set OUTFILE=%~3
if "%OUTFILE%"=="" set OUTFILE=cli\rules\%MANIFEST%.json

echo Applying manifest %MANIFEST% ...
"%PY%" cli\tools\scan_to_rules.py --input "%MANIFEST%" --manufacturer "auto" --apply-manifest "%MANIFEST%" --output "%OUTFILE%"
if errorlevel 1 (echo ERROR: Apply failed. & goto end)

echo Running validation ...
"%PY%" cli\tests\validate_rules.py
if errorlevel 1 (echo ERROR: Validation failed. & goto end)
echo Validation passed: Zero collisions.

echo Syncing web dataset ...
"%PY%" cli\generate_rules_dataset.py
if errorlevel 1 (echo ERROR: Dataset sync failed. & goto end)
echo SUCCESS.
goto end

:end
if "%~1"=="" pause
exit /b %ERRORLEVEL%
