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
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\setup-python.ps1"
    if not errorlevel 1 if exist "%SCRIPT_DIR%tools\python\python.exe" set "PY=%SCRIPT_DIR%tools\python\python.exe"
    if not defined PY (
        echo Python bootstrap failed.
        echo Install Python 3 manually from https://www.python.org/downloads/
        echo and ensure it is added to your PATH, then re-run this script.
        echo.
        pause
        exit /b 1
    )
)

echo Using Python: %PY%

:: Run setup-adb.ps1 if adb is not found.
where adb.exe >nul 2>&1
if not errorlevel 1 (
    echo ADB found in PATH.
) else (
    echo ADB not found. Running setup-adb.ps1...
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\setup-adb.ps1"
    if not errorlevel 1 (
        echo ADB ready.
    ) else (
        echo ADB setup failed.
        pause
        exit /b 1
    )
)

:: Launch the debloat engine with the bootstrapped/embedded Python.
echo Launching AI-Phone-Debloater...
"%PY%" "%SCRIPT_DIR%scripts\debloat-engine.py" --interactive

pause
