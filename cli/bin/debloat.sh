#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_DIR="$(cd "$BIN_DIR/.." && pwd)"
ROOT_DIR="$(cd "$BIN_DIR/../.." && pwd)"

# Installed flat layout (VERSION beside bin/) first, then the repo root.
if [ -f "$CLI_DIR/VERSION" ]; then
    APP_VERSION=$(tr -d '\r\n' < "$CLI_DIR/VERSION")
    cd "$CLI_DIR"
elif [ -f "$ROOT_DIR/VERSION" ]; then
    APP_VERSION=$(tr -d '\r\n' < "$ROOT_DIR/VERSION")
    cd "$ROOT_DIR"
else
    echo "[ERROR] VERSION file not found at $CLI_DIR/VERSION or $ROOT_DIR/VERSION" >&2
    exit 1
fi

PY=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
            PY="$cmd"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "[INFO] Python 3.11+ not found. Attempting auto-install via system package manager..."
    OS="$(uname -s)"
    case "$OS" in
        Linux)
            if command -v apt-get >/dev/null 2>&1; then
                sudo apt-get update -qq && sudo apt-get install -y -qq python3 || true
            elif command -v apk >/dev/null 2>&1; then
                sudo apk add python3 || true
            elif command -v pacman >/dev/null 2>&1; then
                sudo pacman -S --needed --noconfirm python || true
            elif command -v dnf >/dev/null 2>&1; then
                sudo dnf install -y python3 || true
            elif command -v yum >/dev/null 2>&1; then
                sudo yum install -y python3 || true
            fi
            ;;
        Darwin)
            if command -v brew >/dev/null 2>&1; then
                brew install python || true
            fi
            ;;
    esac
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            if "$cmd" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
                PY="$cmd"
                break
            fi
        fi
    done
fi

if [ -z "$PY" ]; then
    echo "[ERROR] Python 3.11 or newer is required but was not found. Install it from https://www.python.org/downloads/" >&2
    exit 1
fi
echo "Using Python: $PY"

# Detect or bootstrap ADB
if [ -f "$CLI_DIR/tools/platform-tools/adb" ]; then
    chmod +x "$CLI_DIR/tools/platform-tools/adb" 2>/dev/null || true
    export PATH="$CLI_DIR/tools/platform-tools:$PATH"
fi
if ! command -v adb >/dev/null 2>&1; then
    echo "[INFO] ADB not found on PATH. Auto-downloading Google Android Platform-Tools..."
    OS="$(uname -s)"
    if [ "$OS" = "Darwin" ]; then
        PLATFORM_URL="https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
    else
        PLATFORM_URL="https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
    fi
    mkdir -p "$CLI_DIR/tools"
    "$PY" -c "
import urllib.request, zipfile, io, sys
url = sys.argv[1]; out_dir = sys.argv[2]
print('[INFO] Fetching platform-tools...')
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=60) as resp: data = resp.read()
print('[INFO] Extracting...')
with zipfile.ZipFile(io.BytesIO(data)) as z: z.extractall(out_dir)
print('[OK] Download complete.')
" "$PLATFORM_URL" "$CLI_DIR/tools" || true
    if [ -f "$CLI_DIR/tools/platform-tools/adb" ]; then
        chmod +x "$CLI_DIR/tools/platform-tools/adb" 2>/dev/null || true
        export PATH="$CLI_DIR/tools/platform-tools:$PATH"
        echo "[OK] ADB platform-tools installed."
    else
        echo "[WARNING] ADB download failed. Install Android platform-tools and put adb on PATH, or pass --adb-path." >&2
    fi
fi

echo "AI-Phone-Debloater v$APP_VERSION"

echo "Launching AI-Phone-Debloater v$APP_VERSION..."
if [ "$#" -eq 0 ] && [ ! -t 0 ]; then
    if [ -r /dev/tty ] && [ -w /dev/tty ]; then
        exec "$PY" "$CLI_DIR/src/debloat_engine.py" --interactive </dev/tty
    else
        exec "$PY" "$CLI_DIR/src/debloat_engine.py"
    fi
elif [ "$#" -eq 0 ]; then
    exec "$PY" "$CLI_DIR/src/debloat_engine.py" --interactive
else
    exec "$PY" "$CLI_DIR/src/debloat_engine.py" "$@"
fi
