@echo off
setlocal EnableExtensions
set "BIN_DIR=%~dp0"
set "CLI_DIR=%BIN_DIR%.."
set "ROOT_DIR=%BIN_DIR%..\.."
cd /d "%ROOT_DIR%"

:: Read version from VERSION file
set "APP_VERSION=1.0.0"
if exist "%ROOT_DIR%\VERSION" (
    set /p APP_VERSION=<"%ROOT_DIR%\VERSION"
)

title AI-Phone-Debloater v%APP_VERSION%

echo ========================================================
echo   AI-Phone-Debloater v%APP_VERSION% (No Root - Safe Debloat)
echo ========================================================
echo.

:: 1. Check Python
set "PY="
if exist "%CLI_DIR%\tools\python\python.exe" (
    set "PY=%CLI_DIR%\tools\python\python.exe"
)
if not defined PY (
    for %%p in (python py python3) do (
        if not defined PY (
            %%p -c "import sys; sys.exit(0 if sys.version_info[0]>=3 else 1)" >nul 2>&1
            if not errorlevel 1 set "PY=%%p"
        )
    )
)

if not defined PY (
    echo [ERROR] Python 3 not found. Please install Python 3 from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [OK] Python runtime: %PY%

:: 2. Check ADB
if exist "%CLI_DIR%\tools\platform-tools" (
    set "PATH=%CLI_DIR%\tools\platform-tools;%PATH%"
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
