#!/usr/bin/env bash
set -e

echo "======================================================--"
echo "  AI-Phone-Debloater: Zero-Install Local ADB Bridge"
echo "======================================================--"
echo ""

if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js not found. Please install Node.js."
    exit 1
fi

if [ ! -d "node_modules" ]; then
    echo "[INFO] Installing webapp dependencies..."
    npm install
fi

if [ ! -f "platform-tools/adb" ]; then
    echo "[INFO] Downloading Android Platform-Tools..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        curl -o platform-tools.zip https://dl.google.com/android/repository/platform-tools-latest-darwin.zip
    else
        curl -o platform-tools.zip https://dl.google.com/android/repository/platform-tools-latest-linux.zip
    fi
    unzip -q platform-tools.zip
    rm platform-tools.zip
    chmod +x platform-tools/adb platform-tools/fastboot
fi

export PATH="$PWD/platform-tools:$PATH"

echo ""
echo "======================================================--"
echo "[OK] ADB Connected Devices:"
adb devices
echo "======================================================--"
echo ""
echo "[INFO] Starting Web App server at http://localhost:4321/app ..."
echo ""

if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:4321/app
elif command -v open &> /dev/null; then
    open http://localhost:4321/app
fi

npm run dev
