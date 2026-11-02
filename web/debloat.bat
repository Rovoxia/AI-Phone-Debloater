@echo off
title AI-Phone-Debloater Zero-Install Bridge
echo ========================================================
echo   AI-Phone-Debloater: Zero-Install Local ADB Bridge
echo ========================================================
echo.

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found. Please install Node.js (https://nodejs.org/) to run the webapp locally.
    pause
    exit /b 1
)

if not exist "node_modules\" (
    echo [INFO] Installing webapp dependencies (first run only)...
    call npm install
)

if not exist "platform-tools\adb.exe" (
    echo [INFO] Downloading portable Android SDK Platform-Tools (ADB)...
    powershell -Command "Invoke-WebRequest -Uri 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip' -OutFile 'platform-tools.zip'"
    echo [INFO] Extracting ADB...
    powershell -Command "Expand-Archive -Path 'platform-tools.zip' -DestinationPath '.' -Force"
    del platform-tools.zip
)

set "PATH=%CD%\platform-tools;%PATH%"

echo.
echo ========================================================
echo [OK] ADB Ready & Connected Devices:
adb devices
echo ========================================================
echo.
echo [INFO] Starting local Web App server at http://localhost:4321/app ...
echo [INFO] Keep this window open while using the webapp!
echo.

start http://localhost:4321/app
npm run dev
