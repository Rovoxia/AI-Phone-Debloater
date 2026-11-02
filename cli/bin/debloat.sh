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

if [ -d "$CLI_DIR/tools/platform-tools" ]; then
    export PATH="$CLI_DIR/tools/platform-tools:$PATH"
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
