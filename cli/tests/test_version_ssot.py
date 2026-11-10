"""
Unit tests for Single-Source-of-Truth (SSOT) Version System.
Ensures zero drift across Python engine, bridge server, web manifests, and docs.
Standard library only (zero third-party dependencies).
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "cli"))
sys.path.insert(0, str(REPO_ROOT / "cli" / "src"))

import bridge_server
import debloat_engine
import sync_version


class TestVersionSSOT(unittest.TestCase):
    """Test suite ensuring root VERSION is strictly observed everywhere."""

    def setUp(self):
        self.version_file = REPO_ROOT / "VERSION"
        self.assertTrue(self.version_file.is_file(), "Root VERSION file must exist")
        self.version = self.version_file.read_text(encoding="utf-8").strip()

    def test_semver_format(self):
        """Verify root VERSION strictly adheres to Semantic Versioning (SemVer 2.0)."""
        pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$"
        self.assertRegex(
            self.version,
            pattern,
            f"VERSION '{self.version}' is not valid SemVer (e.g., 1.0.0 or 1.1.1-alpha.1)",
        )

    def test_debloat_engine_version_sync(self):
        """Verify debloat_engine.__version__ matches root VERSION."""
        self.assertEqual(
            debloat_engine.__version__,
            self.version,
            f"debloat_engine.__version__ ({debloat_engine.__version__}) != VERSION ({self.version})",
        )

    def test_bridge_server_version_sync(self):
        """Verify bridge_server.VERSION matches root VERSION."""
        self.assertEqual(
            bridge_server.VERSION,
            self.version,
            f"bridge_server.VERSION ({bridge_server.VERSION}) != VERSION ({self.version})",
        )

    def test_web_package_json_version_sync(self):
        """Verify web/package.json version matches root VERSION."""
        pkg_file = REPO_ROOT / "web" / "package.json"
        self.assertTrue(pkg_file.is_file(), "web/package.json must exist")
        pkg_data = json.loads(pkg_file.read_text(encoding="utf-8"))
        self.assertEqual(
            pkg_data.get("version"),
            self.version,
            f"web/package.json version ({pkg_data.get('version')}) != VERSION ({self.version})",
        )

    def test_web_version_json_sync(self):
        """Verify web/src/data/version.json matches root VERSION."""
        v_json_file = REPO_ROOT / "web" / "src" / "data" / "version.json"
        self.assertTrue(v_json_file.is_file(), "web/src/data/version.json must exist")
        v_data = json.loads(v_json_file.read_text(encoding="utf-8"))
        self.assertEqual(
            v_data.get("version"),
            self.version,
            f"web/src/data/version.json version ({v_data.get('version')}) != VERSION ({self.version})",
        )

    def test_llms_full_version_sync(self):
        """Verify web/public/llms-full.txt contains the exact root VERSION."""
        llms_file = REPO_ROOT / "web" / "public" / "llms-full.txt"
        self.assertTrue(llms_file.is_file(), "web/public/llms-full.txt must exist")
        content = llms_file.read_text(encoding="utf-8")
        match = re.search(r"^Version:\s*([^\s\(\r\n]+)", content, re.MULTILINE)
        self.assertIsNotNone(match, "web/public/llms-full.txt must contain a 'Version:' line")
        self.assertEqual(
            match.group(1),
            self.version,
            f"web/public/llms-full.txt version ({match.group(1)}) != VERSION ({self.version})",
        )

    def test_sync_version_check_all_clean(self):
        """Verify sync_version.check_all() returns 0 errors against current workspace."""
        errors = sync_version.check_all()
        self.assertEqual(errors, [], f"Expected zero version drift errors, got: {errors}")

    def test_sync_version_drift_detection(self):
        """Verify sync_version.check_all() detects simulated version mismatch."""
        dummy_version = "99.99.99"
        errors = sync_version.check_all(dummy_version)
        self.assertGreaterEqual(
            len(errors),
            2,
            "Expected drift errors to be raised when checking mismatched version",
        )


if __name__ == "__main__":
    unittest.main()
