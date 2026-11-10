#!/usr/bin/env python3
"""
Sync VERSION across all repository manifests and metadata files.
Single source of truth is the root `VERSION` file.
Standard library only (zero third-party dependencies).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"
PKG_FILE = REPO_ROOT / "web" / "package.json"
VERSION_JSON_FILE = REPO_ROOT / "web" / "src" / "data" / "version.json"
LLMS_FILE = REPO_ROOT / "web" / "public" / "llms-full.txt"


def read_version() -> str:
    if not VERSION_FILE.is_file():
        raise FileNotFoundError(f"Missing root VERSION file at {VERSION_FILE}")
    v = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.match(r"^\d+\.\d+\.\d+", v):
        raise ValueError(f"Invalid SemVer in {VERSION_FILE}: '{v}'")
    return v


def sync_package_json(version: str) -> bool:
    if not PKG_FILE.is_file():
        return False
    try:
        data = json.loads(PKG_FILE.read_text(encoding="utf-8"))
        if data.get("version") != version:
            data["version"] = version
            PKG_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print(f"[sync] Updated {PKG_FILE.relative_to(REPO_ROOT)} -> {version}")
            return True
    except (OSError, json.JSONDecodeError):
        print(f"[sync] Error updating {PKG_FILE}", file=sys.stderr)
    return False


def sync_version_json(version: str) -> bool:
    try:
        VERSION_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not VERSION_JSON_FILE.is_file() or json.loads(VERSION_JSON_FILE.read_text(encoding="utf-8")).get("version") != version:
            VERSION_JSON_FILE.write_text(json.dumps({"version": version}, indent=2) + "\n", encoding="utf-8")
            print(f"[sync] Updated {VERSION_JSON_FILE.relative_to(REPO_ROOT)} -> {version}")
            return True
    except (OSError, json.JSONDecodeError):
        print(f"[sync] Error updating {VERSION_JSON_FILE}", file=sys.stderr)
    return False


def sync_llms_full(version: str) -> bool:
    if not LLMS_FILE.is_file():
        return False
    try:
        content = LLMS_FILE.read_text(encoding="utf-8")
        updated = re.sub(
            r"^Version:\s*[^\n\r]+",
            f"Version: {version} (tracked in root `VERSION` file)",
            content,
            flags=re.MULTILINE,
        )
        if updated != content:
            LLMS_FILE.write_text(updated, encoding="utf-8")
            print(f"[sync] Updated {LLMS_FILE.relative_to(REPO_ROOT)} -> {version}")
            return True
    except OSError:
        print(f"[sync] Error updating {LLMS_FILE}", file=sys.stderr)
    return False


def sync_all() -> str:
    version = read_version()
    sync_package_json(version)
    sync_version_json(version)
    sync_llms_full(version)
    return version


def check_all(version: str | None = None) -> list[str]:
    """Verify all manifests match root VERSION without writing to disk."""
    if version is None:
        version = read_version()

    errors: list[str] = []

    if PKG_FILE.is_file():
        try:
            pkg_data = json.loads(PKG_FILE.read_text(encoding="utf-8"))
            if pkg_data.get("version") != version:
                errors.append(f"{PKG_FILE.relative_to(REPO_ROOT)} has version '{pkg_data.get('version')}', expected '{version}'")
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"Failed to read {PKG_FILE.relative_to(REPO_ROOT)}: {e}")

    if VERSION_JSON_FILE.is_file():
        try:
            v_data = json.loads(VERSION_JSON_FILE.read_text(encoding="utf-8"))
            if v_data.get("version") != version:
                errors.append(f"{VERSION_JSON_FILE.relative_to(REPO_ROOT)} has version '{v_data.get('version')}', expected '{version}'")
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"Failed to read {VERSION_JSON_FILE.relative_to(REPO_ROOT)}: {e}")

    if LLMS_FILE.is_file():
        try:
            llms_text = LLMS_FILE.read_text(encoding="utf-8")
            expected_prefix = f"Version: {version}"
            match = re.search(r"^Version:\s*([^\s\(\r\n]+)", llms_text, re.MULTILINE)
            if not match or match.group(1) != version:
                current_v = match.group(1) if match else "missing"
                errors.append(f"{LLMS_FILE.relative_to(REPO_ROOT)} has version '{current_v}', expected '{expected_prefix}'")
        except OSError as e:
            errors.append(f"Failed to read {LLMS_FILE.relative_to(REPO_ROOT)}: {e}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize or check SemVer consistency against root VERSION file.")
    parser.add_argument("--check", action="store_true", help="Check manifests for drift without modifying files (exits 1 on drift)")
    args = parser.parse_args()

    try:
        version = read_version()
        if args.check:
            errors = check_all(version)
            if errors:
                print(f"[ERROR] Version drift detected against root VERSION (v{version}):", file=sys.stderr)
                for err in errors:
                    print(f"  - {err}", file=sys.stderr)
                print("\nRun 'python cli/sync_version.py' to synchronize.", file=sys.stderr)
                return 1
            print(f"[OK] All metadata manifests match root VERSION: v{version}")
            return 0

        sync_all()
        print(f"AI-Phone-Debloater version synced: v{version}")
        return 0
    except (OSError, ValueError) as e:
        print(f"Error syncing version: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
