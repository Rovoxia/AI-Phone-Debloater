#!/usr/bin/env python3
"""
Validation script for AI-Phone-Debloater JSON rules.
Verifies JSON syntax, structure, and ensures zero collisions with the critical OS blacklist.
Cross-platform: works identically on Windows, Linux, and macOS.
"""

import glob
import json
import os
import sys
from pathlib import Path

def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    rules_dir = repo_root / "rules"

    rules = list(rules_dir.glob("*.json"))
    if not rules:
        print(f"ERROR: No rule files found in {rules_dir}")
        return 1

    critical_file = rules_dir / "critical-do-not-touch.json"
    if not critical_file.exists():
        print(f"ERROR: Missing critical blacklist file: {critical_file}")
        return 1

    with open(critical_file, "r", encoding="utf-8") as f:
        crit_data = json.load(f)

    crit_pkgs = set()
    entries = crit_data.get("rules", []) or crit_data.get("packages", [])
    for e in entries:
        if isinstance(e, dict) and "package" in e:
            crit_pkgs.add(e["package"])

    print(f"Protected Critical Core Packages: {len(crit_pkgs)}")
    if len(crit_pkgs) == 0:
        print("ERROR: Critical blacklist must not be empty!")
        return 1

    errors = []
    for r in rules:
        try:
            with open(r, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            errors.append(f"Invalid JSON in {r.name}: {exc}")
            continue

        if not ("name" in data or "description" in data):
            errors.append(f"{r.name}: Missing top-level 'name' or 'description'")

        rule_entries = data.get("rules", []) or data.get("packages", [])
        if not rule_entries:
            errors.append(f"{r.name}: Must have a non-empty 'rules' list")

        for idx, entry in enumerate(rule_entries):
            if not isinstance(entry, dict):
                errors.append(f"{r.name}[{idx}]: Entry must be an object")
                continue
            if "package" not in entry:
                errors.append(f"{r.name}[{idx}]: Missing 'package' field")

            pkg = entry.get("package")
            if r != critical_file and pkg in crit_pkgs:
                errors.append(f"SAFETY COLLISION: {pkg} in {r.name} is also in critical-do-not-touch!")

    if errors:
        print("Validation errors encountered:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"Validated {len(rules)} JSON rule files successfully. Zero collisions.")

    # Validate VERSION file
    vfile = repo_root / "VERSION"
    if not vfile.is_file():
        print("ERROR: Missing root VERSION file!")
        return 1
    version = vfile.read_text(encoding="utf-8").strip()
    import re
    if not re.match(r"^\d+\.\d+\.\d+", version):
        print(f"ERROR: VERSION '{version}' is not valid SemVer (e.g. 1.0.0)!")
        return 1
    print(f"Verified VERSION file: v{version}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
