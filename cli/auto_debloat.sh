#!/usr/bin/env bash
# AI-Phone-Debloater auto rule pipeline
# Modes:
#   dump    dump packages -> draft rules -> validate -> sync
#   apply   apply categorization manifest -> validate -> sync
#   check   validate + sync only (no device needed)
set -euo pipefail

MODE="${1:-dump}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "== AI-Phone-Debloater Auto Dumper =="

# --- Shared checks ---
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    echo "ERROR: python not found on PATH."
    exit 1
fi
PY_BIN=""
if command -v python3 >/dev/null 2>&1; then PY_BIN=python3; else PY_BIN=python; fi

# --- MODE: dump ---
if [ "$MODE" = "dump" ]; then
    if ! command -v adb >/dev/null 2>&1; then
        echo "ERROR: adb not found on PATH. Install Android Platform-Tools or add adb to PATH."
        exit 1
    fi
    echo "Using adb from PATH: $(command -v adb)"

    mkdir -p scans
    read -rp "Enter device model (e.g. pixel7a, xiaomi_note10): " MODEL
    if [ -z "$MODEL" ]; then echo "ERROR: Model name required."; exit 1; fi
    read -rp "Enter manufacturer (Xiaomi, Samsung, OnePlus, etc.): " MFR
    if [ -z "$MFR" ]; then echo "ERROR: Manufacturer required."; exit 1; fi
    DUMP_FILE="scans/${MODEL}.txt"

    echo "Dumping User 0 packages to $DUMP_FILE ..."
    adb shell pm list packages -U --user 0 > "$DUMP_FILE"
    echo "Dump saved: $DUMP_FILE"

    echo "Generating draft rules for $MFR ..."
    "$PY_BIN" cli/tools/scan_to_rules.py \
        --input "$DUMP_FILE" \
        --manufacturer "$MFR" \
        --output "cli/rules/${MODEL}.json" \
        --drop-uncategorized
    echo "Draft rule file: cli/rules/${MODEL}.json"

    echo "Running rule validation ..."
    "$PY_BIN" cli/tests/validate_rules.py
    echo "Validation passed: Zero collisions."

    echo "Syncing web rules dataset ..."
    "$PY_BIN" cli/generate_rules_dataset.py

    echo ""
    echo "SUCCESS: Rules updated and web dataset in sync."
    echo "Next step: open PR from QA branch targeting main."
    exit 0
fi

# --- MODE: apply ---
if [ "$MODE" = "apply" ]; then
    MANIFEST="${2:-}"
    if [ -z "$MANIFEST" ]; then echo "ERROR: Usage: auto_debloat.sh apply <manifest.json> [output.json]"; exit 1; fi
    if [ ! -f "$MANIFEST" ]; then echo "ERROR: Manifest file not found: $MANIFEST"; exit 1; fi
    OUTFILE="${3:-cli/rules/${MANIFEST}.json}"

    echo "Applying categorization manifest $MANIFEST ..."
    "$PY_BIN" cli/tools/scan_to_rules.py \
        --input "$MANIFEST" \
        --manufacturer "auto" \
        --apply-manifest "$MANIFEST" \
        --output "$OUTFILE"

    echo "Running rule validation ..."
    "$PY_BIN" cli/tests/validate_rules.py
    echo "Validation passed: Zero collisions."

    echo "Syncing web rules dataset ..."
    "$PY_BIN" cli/generate_rules_dataset.py

    echo ""
    echo "SUCCESS: Rules updated and web dataset in sync."
    exit 0
fi

# --- MODE: check ---
if [ "$MODE" = "check" ]; then
    echo "Running rule validation ..."
    "$PY_BIN" cli/tests/validate_rules.py
    echo "Validation passed: Zero collisions."

    echo "Syncing web rules dataset ..."
    "$PY_BIN" cli/generate_rules_dataset.py

    echo ""
    echo "SUCCESS: Web dataset in sync."
    exit 0
fi

echo "ERROR: Unknown mode '$MODE'. Use dump, apply, or check."
exit 1