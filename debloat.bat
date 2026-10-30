@echo off
setlocal EnableExtensions

:: Set working directory to project root
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Read version from VERSION file
set "APP_VERSION="
if exist "%SCRIPT_DIR%VERSION" (
    set /p APP_VERSION=<"%SCRIPT_DIR%VERSION"
)
if not defined APP_VERSION set "APP_VERSION=1.0.0"

title AI-Phone-Debloater v%APP_VERSION%

echo ========================================================
echo   AI-Phone-Debloater v%APP_VERSION% (No Root - Safe Debloat)
echo ========================================================
echo.

:: 1. Check Python
set "PY="
if exist "%SCRIPT_DIR%tools\python\python.exe" (
    set "PY=%SCRIPT_DIR%tools\python\python.exe"
)
if not defined PY (
    for %%p in (python py python3) do (
        if not defined PY (
            %%p -c "import sys" >nul 2>&1
            if not errorlevel 1 set "PY=%%p"
        )
    )
)

:: If Python missing, bootstrap portable Python via setup script
if not defined PY (
    echo Python runtime not found. Bootstrapping portable Python...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\setup-python.ps1"
    if exist "%SCRIPT_DIR%tools\python\python.exe" (
        set "PY=%SCRIPT_DIR%tools\python\python.exe"
    ) else (
        echo [ERROR] Failed to bootstrap Python.
        echo Please install Python 3 from https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

echo [OK] Python runtime: %PY%

:: 2. Check ADB
set "ADB_FOUND="
if exist "%SCRIPT_DIR%tools\platform-tools\adb.exe" set "ADB_FOUND=1"
if not defined ADB_FOUND (
    where adb.exe >nul 2>&1
    if not errorlevel 1 set "ADB_FOUND=1"
)

:: If ADB missing, run setup-adb.ps1
if not defined ADB_FOUND (
    echo ADB not found. Setting up Android platform-tools...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\setup-adb.ps1"
)

:: Export tools to PATH for this process
if exist "%SCRIPT_DIR%tools\platform-tools" (
    set "PATH=%SCRIPT_DIR%tools\platform-tools;%PATH%"
)

echo.
echo Launching debloat engine...
echo.

"%PY%" "%SCRIPT_DIR%scripts\debloat-engine.py" --interactive

echo.
echo ========================================================
echo Debloat engine finished.
echo ========================================================
pause
