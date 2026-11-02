#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_DIR="$BIN_DIR/.."
ROOT_DIR="$BIN_DIR/../.."
cd "$ROOT_DIR"

PY=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c 'import sys; exit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1; then
            PY="$cmd"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "[ERROR] Python 3 not found. Please install Python 3."
    exit 1
fi

echo "Using Python: $PY"

# 2. Check and bootstrap ADB
if [ -f "$CLI_DIR/tools/platform-tools/adb" ]; then
    chmod +x "$CLI_DIR/tools/platform-tools/adb" 2>/dev/null || true
    export PATH="$CLI_DIR/tools/platform-tools:$PATH"
fi

if ! command -v adb >/dev/null 2>&1; then
    echo "[INFO] ADB not found on system. Auto-downloading Google Android Platform-Tools..."
    OS="$(uname -s)"
    if [ "$OS" = "Darwin" ]; then
        PLATFORM_URL="https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
    else
        PLATFORM_URL="https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
    fi
    mkdir -p "$CLI_DIR/tools"
    "$PY" -c "
import urllib.request, zipfile, io, sys
url = sys.argv[1]
out_dir = sys.argv[2]
print('[INFO] Fetching platform-tools from Google...')
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    data = resp.read()
print('[INFO] Extracting platform-tools archive...')
with zipfile.ZipFile(io.BytesIO(data)) as z:
    z.extractall(out_dir)
print('[OK] Download complete.')
" "$PLATFORM_URL" "$CLI_DIR/tools" || true

    if [ -f "$CLI_DIR/tools/platform-tools/adb" ]; then
        chmod +x "$CLI_DIR/tools/platform-tools/adb" 2>/dev/null || true
        export PATH="$CLI_DIR/tools/platform-tools:$PATH"
        echo "[OK] ADB platform-tools installed successfully."
    else
        echo "[WARNING] Automatic ADB download failed. Please install ADB manually or put it on PATH."
    fi
else
    echo "[OK] ADB runtime detected."
fi

APP_VERSION="1.0.0"
if [ -f "$ROOT_DIR/VERSION" ]; then
    APP_VERSION=$(tr -d '\r\n' < "$ROOT_DIR/VERSION")
fi

echo "Launching AI-Phone-Debloater v$APP_VERSION..."
if [ "$#" -eq 0 ]; then
    set -- --interactive
fi
exec "$PY" "$CLI_DIR/src/debloat_engine.py" "$@"
