@echo off
setlocal

:: Directory of this launcher.
set "SCRIPT_DIR=%~dp0"

:: Resolve the Python interpreter to use.
set "PY="

:: 1. Check for bootstrapped embeddable Python in tools\python\ (zero-dependency path).
if exist "%SCRIPT_DIR%tools\python\python.exe" (
    set "PY=%SCRIPT_DIR%tools\python\python.exe"
)

:: 2. Check for working system Python (python, py, python3).
if not defined PY (
    for %%p in (python py python3) do (
        if not defined PY (
            %%p -c "import sys" >nul 2>&1
            if not errorlevel 1 set "PY=%%p"
        )
    )
)

:: 3. Bootstrap embeddable Python if still missing.
if not defined PY (
    echo.
    echo Python was not found on this system.
    echo Bootstrapping official Python 3.11.9 embeddable package to tools\python\ ...
    set "PY=%SCRIPT_DIR%tools\python\python.exe"
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$ErrorActionPreference = 'Stop'; ^
        $scriptDir = '%SCRIPT_DIR%'; ^
        $outDir = Join-Path $scriptDir 'tools\python'; ^
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null; ^
        $url = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip'; ^
        $zip = Join-Path $outDir 'python-embed.zip'; ^
        Write-Host 'Downloading Python...' -ForegroundColor Cyan; ^
        Invoke-WebRequest -Uri $url -OutFile $zip; ^
        Write-Host 'Extracting...' -ForegroundColor Cyan; ^
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $outDir); ^
        Remove-Item $zip -Force; ^
        $pth = Join-Path $outDir 'python311._pth'; ^
        if (Test-Path $pth) { (Get-Content $pth) -replace '^import site$', 'import site' | Set-Content $pth }"
    if not exist "%SCRIPT_DIR%tools\python\python.exe" (
        echo Python bootstrap failed. Install Python 3 manually and re-run this script.
        pause
        exit /b 1
    )
)

echo Using Python: %PY%

:: Find ADB — check tools first, then PATH.
set "ADB="
if exist "%SCRIPT_DIR%tools\platform-tools\adb.exe" (
    set "ADB=%SCRIPT_DIR%tools\platform-tools\adb.exe"
) else if exist "%SCRIPT_DIR%tools\platform-tools\adb" (
    set "ADB=%SCRIPT_DIR%tools\platform-tools\adb"
) else (
    where adb.exe >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%i in ('where adb.exe') do set "ADB=%%i"
    )
)

:: If ADB still not found, run setup-adb.ps1 and re-check.
if not defined ADB (
    echo ADB not found. Running setup-adb.ps1...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\setup-adb.ps1" >nul
    if exist "%SCRIPT_DIR%tools\platform-tools\adb.exe" (
        set "ADB=%SCRIPT_DIR%tools\platform-tools\adb.exe"
    ) else if exist "%SCRIPT_DIR%tools\platform-tools\adb" (
        set "ADB=%SCRIPT_DIR%tools\platform-tools\adb"
    )
)

if not defined ADB (
    echo ADB setup failed. Cannot find adb.exe.
    echo Install platform-tools and ensure adb.exe is in PATH.
    pause
    exit /b 1
)

echo ADB found: %ADB%

:: Launch the debloat engine with the selected Python and ADB.
echo Launching AI-Phone-Debloater...
set "PATH=%SCRIPT_DIR%tools\platform-tools;%PATH%"
"%PY%" "%SCRIPT_DIR%scripts\debloat-engine.py" --interactive

pause