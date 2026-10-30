#!/usr/bin/env python3
"""
Syncs version from VERSION file to README.md and repository badges.
Ensures single source of truth: change VERSION, run this or CI, everything updates.
"""
import re
import sys
from pathlib import Path

def sync_version() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    vfile = repo_root / "VERSION"
    if not vfile.is_file():
        print("ERROR: VERSION file not found at repository root.")
        return 1

    version = vfile.read_text(encoding="utf-8").strip()
    if not re.match(r"^\d+\.\d+\.\d+", version):
        print(f"ERROR: Invalid SemVer format in VERSION: '{version}'")
        return 1

    readme_file = repo_root / "README.md"
    if readme_file.is_file():
        content = readme_file.read_text(encoding="utf-8")
        badge = f"[![Version](https://img.shields.io/badge/version-{version}-blue.svg)](VERSION)"
        pattern = r"\[!\[Version\]\(https://img\.shields\.io/badge/version-[^-\)]+-blue\.svg\)\]\(VERSION\)"
        if re.search(pattern, content):
            new_content = re.sub(pattern, badge, content)
        else:
            anchor = '[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg?logo=python)](https://www.python.org/)'
            if anchor in content:
                new_content = content.replace(anchor, f'{badge}\n{anchor}')
            else:
                new_content = content
        if new_content != content:
            readme_file.write_text(new_content, encoding="utf-8")
            print(f"Updated README.md with version {version}")

    print(f"Synced version {version} across repository.")
    return 0

if __name__ == "__main__":
    sys.exit(sync_version())
