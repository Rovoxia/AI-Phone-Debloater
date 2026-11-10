#!/usr/bin/env python3
"""
Sync VERSION across all repository manifests and metadata files.
Single source of truth is the root `VERSION` file.
Standard library only (zero third-party dependencies).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"


def read_version() -> str:
    if not VERSION_FILE.is_file():
        raise FileNotFoundError(f"Missing root VERSION file at {VERSION_FILE}")
    v = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.match(r"^\d+\.\d+\.\d+", v):
        raise ValueError(f"Invalid SemVer in {VERSION_FILE}: '{v}'")
    return v


def sync_package_json(version: str) -> bool:
    pkg_file = REPO_ROOT / "web" / "package.json"
    if not pkg_file.is_file():
        return False
    try:
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
        if data.get("version") != version:
            data["version"] = version
            pkg_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print(f"[sync] Updated {pkg_file.relative_to(REPO_ROOT)} -> {version}")
            return True
    except Exception as e:
        print(f"[sync] Error updating {pkg_file}: {e}")
    return False


def sync_version_json(version: str) -> bool:
    v_json = REPO_ROOT / "web" / "src" / "data" / "version.json"
    try:
        v_json.parent.mkdir(parents=True, exist_ok=True)
        if not v_json.is_file() or json.loads(v_json.read_text(encoding="utf-8")).get("version") != version:
            v_json.write_text(json.dumps({"version": version}, indent=2) + "\n", encoding="utf-8")
            print(f"[sync] Updated {v_json.relative_to(REPO_ROOT)} -> {version}")
            return True
    except Exception as e:
        print(f"[sync] Error updating {v_json}: {e}")
    return False


def sync_llms_full(version: str) -> bool:
    llms_file = REPO_ROOT / "web" / "public" / "llms-full.txt"
    if not llms_file.is_file():
        return False
    try:
        content = llms_file.read_text(encoding="utf-8")
        updated = re.sub(
            r"^Version:\s*[^\n\r]+",
            f"Version: {version} (tracked in root `VERSION` file)",
            content,
            flags=re.MULTILINE,
        )
        if updated != content:
            llms_file.write_text(updated, encoding="utf-8")
            print(f"[sync] Updated {llms_file.relative_to(REPO_ROOT)} -> {version}")
            return True
    except Exception as e:
        print(f"[sync] Error updating {llms_file}: {e}")
    return False


def sync_all() -> str:
    version = read_version()
    sync_package_json(version)
    sync_version_json(version)
    sync_llms_full(version)
    return version


def main() -> int:
    try:
        version = sync_all()
        print(f"AI-Phone-Debloater version synced: v{version}")
        return 0
    except Exception as e:
        print(f"Error syncing version: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
