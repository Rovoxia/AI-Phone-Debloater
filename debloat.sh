#!/usr/bin/env bash
# debloat.sh - 1-click launcher for AI-Phone-Debloater on Unix/Linux/macOS.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check Python 3.
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
    echo ""
    echo "Python 3 was not found on this system."
    echo "Please install Python 3 from https://www.python.org/downloads/ (or via your package manager: brew, apt, dnf)"
    echo "and ensure it is added to your PATH, then re-run this script."
    echo ""
    exit 1
fi

echo "Using Python: $PY"

# Check ADB; run setup-adb.sh if missing.
if ! command -v adb >/dev/null 2>&1; then
    echo "ADB not found in PATH. Running setup-adb.sh..."
    bash "$SCRIPT_DIR/scripts/setup-adb.sh" || {
        echo "ADB setup failed." >&2
        exit 1
    }
fi

# Launch the debloat engine.
echo "Launching AI-Phone-Debloater..."
"$PY" "$SCRIPT_DIR/scripts/debloat-engine.py" --interactive
