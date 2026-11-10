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
    echo "[ERROR] Python 3 not found. Install from https://www.python.org/downloads/"
    exit 1
fi
echo "Using Python: $PY"

if [ -f "$ROOT_DIR/VERSION" ]; then
    APP_VERSION=$(tr -d '\r\n' < "$ROOT_DIR/VERSION")
else
    echo "[ERROR] VERSION file not found at $ROOT_DIR/VERSION" >&2
    exit 1
fi

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
with urllib.request.urlopen(req) as resp: data = resp.read()
print('[INFO] Extracting...')
with zipfile.ZipFile(io.BytesIO(data)) as z: z.extractall(out_dir)
print('[OK] Download complete.')
" "$PLATFORM_URL" "$CLI_DIR/tools" || true
    if [ -f "$CLI_DIR/tools/platform-tools/adb" ]; then
        chmod +x "$CLI_DIR/tools/platform-tools/adb" 2>/dev/null || true
        export PATH="$CLI_DIR/tools/platform-tools:$PATH"
        echo "[OK] ADB platform-tools installed."
    else
        echo "[WARNING] ADB download failed. Install ADB manually or put it on PATH."
    fi
fi

echo "AI-Phone-Debloater v$APP_VERSION"

MODE="${1:-}"
if [ "$MODE" = "dump-rules" ]; then
    mkdir -p scans
    read -rp "Enter device model (e.g. pixel7a, xiaomi_note10): " MODEL
    if [ -z "$MODEL" ]; then echo "ERROR: Model required."; exit 1; fi
    read -rp "Enter manufacturer (Xiaomi, Samsung, OnePlus, etc.): " MFR
    if [ -z "$MFR" ]; then echo "ERROR: Manufacturer required."; exit 1; fi
    DUMP_FILE="scans/${MODEL}.txt"
    echo "Dumping User 0 packages to $DUMP_FILE ..."
    adb shell pm list packages -U --user 0 > "$DUMP_FILE"
    echo "Dump saved: $DUMP_FILE"
    echo "Generating draft rules for $MFR ..."
    "$PY" cli/tools/scan_to_rules.py --input "$DUMP_FILE" --manufacturer "$MFR" --output "cli/rules/${MODEL}.json" --drop-uncategorized
    echo "Draft rule file: cli/rules/${MODEL}.json"
    echo "Running validation ..."
    "$PY" cli/tests/validate_rules.py
    echo "Validation passed: Zero collisions."
    echo "Syncing web dataset ..."
    "$PY" cli/generate_rules_dataset.py
    echo "Creating upload package ..."
    if command -v zip >/dev/null 2>&1; then
        zip -r "scans/${MODEL}-rules.zip" "scans/${MODEL}.txt" "cli/rules/${MODEL}.json"
    else
        "$PY" -c "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1],'w'); [z.write(f) for f in sys.argv[2:]]" "scans/${MODEL}-rules.zip" "scans/${MODEL}.txt" "cli/rules/${MODEL}.json"
    fi
    echo "Upload package: scans/${MODEL}-rules.zip"
    echo "Upload this zip to GitHub for review and dataset build."
    exit 0
elif [ "$MODE" = "apply-rules" ]; then
    MANIFEST="${2:-}"
    if [ -z "$MANIFEST" ]; then echo "ERROR: Usage: debloat.sh apply-rules <manifest.json> [output.json]"; exit 1; fi
    if [ ! -f "$MANIFEST" ]; then echo "ERROR: Manifest not found: $MANIFEST"; exit 1; fi
    OUTFILE="${3:-cli/rules/${MANIFEST}.json}"
    echo "Applying manifest $MANIFEST ..."
    "$PY" cli/tools/scan_to_rules.py --input "$MANIFEST" --manufacturer "auto" --apply-manifest "$MANIFEST" --output "$OUTFILE"
    echo "Running validation ..."
    "$PY" cli/tests/validate_rules.py
    echo "Syncing web dataset ..."
    "$PY" cli/generate_rules_dataset.py
    echo "SUCCESS."
    exit 0
fi

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
