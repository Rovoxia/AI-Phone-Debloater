#!/usr/bin/env python3
"""
Validation script for AI-Phone-Debloater JSON rules.
Verifies JSON syntax, structure, and ensures zero collisions with the critical OS blacklist.
Cross-platform: works identically on Windows, Linux, and macOS.
"""

import json
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    rules_dir = repo_root / "cli" / "rules"

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

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(repo_root / "cli" / "src"))
    import importlib
    hard_crit = set(importlib.import_module("debloat_engine").HARDCRITICAL_PACKAGES)

    errors = []
    seen = {}  # package -> file name
    for r in rules:
        try:
            with open(r, "r", encoding="utf-8") as f:
                data = json.load(f)
        except ValueError as exc:
            errors.append(f"Invalid JSON in {r.name}: {exc!r}")
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
            if r != critical_file:
                tier = entry.get("tier")
                if type(tier) is not int or tier not in (1, 2, 3):
                    errors.append(f"{r.name}[{idx}] ({pkg}): invalid tier {tier!r} (must be 1, 2 or 3)")
            if pkg is not None:
                if pkg in seen:
                    where = "within" if seen[pkg] == r.name else "also in " + seen[pkg] + " and"
                    errors.append(f"DUPLICATE: {pkg} {where} {r.name}")
                else:
                    seen[pkg] = r.name
            if r != critical_file and pkg in hard_crit:
                errors.append(f"HARDCRITICAL COLLISION: {pkg} in {r.name} is in engine HARDCRITICAL_PACKAGES (silently dropped)!")
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

    # Synchronize version metadata across manifests
    sys.path.insert(0, str(repo_root / "cli"))
    try:
        from sync_version import sync_all
        sync_all()
    except (ImportError, OSError, ValueError) as e:
        print(f"WARNING: Could not sync version metadata: {e}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
