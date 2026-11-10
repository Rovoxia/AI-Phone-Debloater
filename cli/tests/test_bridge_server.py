"""
Unit tests for AI-Phone-Debloater Local ADB Bridge Server (cli/src/bridge_server.py).
Zero third-party pip dependencies; standard library unittest only.
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "cli" / "src"))

import bridge_server


class TestBridgeServerHelpers(unittest.TestCase):
    """Test helper functions and security invariants in bridge_server.py."""

    def test_critical_packages_loaded(self):
        """Verify that load_critical_packages correctly loads exactly 89 Tier 4 packages."""
        critical = bridge_server.load_critical_packages()
        self.assertEqual(len(critical), 89)
        self.assertIn("android", critical)
        self.assertIn("com.android.systemui", critical)
        self.assertIn("com.google.android.gms", critical)

    def test_is_critical_invariant(self):
        """Verify is_critical identifies inviolable packages."""
        self.assertTrue(bridge_server.is_critical("android"))
        self.assertTrue(bridge_server.is_critical("com.android.phone"))
        self.assertFalse(bridge_server.is_critical("com.facebook.katana"))
        self.assertFalse(bridge_server.is_critical("com.miui.msa.global"))

    def test_package_validation(self):
        """Verify package regex filters illegal or command injection strings."""
        self.assertTrue(bridge_server.is_valid_package("com.android.chrome"))
        self.assertTrue(bridge_server.is_valid_package("android"))
        self.assertTrue(bridge_server.is_valid_package("com.samsung.android.bixby.agent"))

        # Injection attempts
        self.assertFalse(bridge_server.is_valid_package("com.example; rm -rf /"))
        self.assertFalse(bridge_server.is_valid_package("com.example && echo test"))
        self.assertFalse(bridge_server.is_valid_package("com.example | ls"))
        self.assertFalse(bridge_server.is_valid_package("`reboot`"))
        self.assertFalse(bridge_server.is_valid_package(""))
        self.assertFalse(bridge_server.is_valid_package(None))
        self.assertFalse(bridge_server.is_valid_package(12345))

    def test_safe_filename(self):
        """Verify filename sanitization prevents problematic characters."""
        self.assertEqual(bridge_server.safe_filename("Pixel_7"), "Pixel_7")
        self.assertEqual(bridge_server.safe_filename("Galaxy S23!"), "Galaxy_S23_")
        self.assertEqual(bridge_server.safe_filename("model/name?*"), "model_name_")


class TestBridgeHttpEndpoints(unittest.TestCase):
    """Test HTTP request routing, CORS, and endpoint responses."""

    def setUp(self):
        self.server = bridge_server.ThreadingHTTPServer(("127.0.0.1", 0), bridge_server.BridgeHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_cors_options(self):
        """Verify OPTIONS preflight request responds with 204 and CORS headers."""
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/health", method="OPTIONS")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("GET", resp.headers.get("Access-Control-Allow-Methods", ""))

    def test_health_endpoint(self):
        """Verify GET /health returns version and status."""
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health") as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertIn("version", data)
            self.assertIn("adb_available", data)

    def test_packages_missing_serial_rejection(self):
        """Verify GET /packages rejects request without serial parameter."""
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/packages")
        self.assertEqual(ctx.exception.code, 400)

    def test_device_missing_serial_rejection(self):
        """Verify GET /device rejects request without serial parameter."""
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/device")
        self.assertEqual(ctx.exception.code, 400)

    def test_invalid_mode_rejection(self):
        """Verify POST /execute rejects payload containing invalid mode."""
        payload = {
            "serial": "test-device",
            "mode": "invalid-mode",
            "action": "disable",
            "packages": ["com.valid.pkg"]
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/execute",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_invalid_package_handled(self):
        """Verify POST /execute marks invalid package names as failed."""
        payload = {
            "serial": "test-device",
            "mode": "dry-run",
            "action": "disable",
            "packages": ["invalid; rm -rf /"]
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/execute",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res_data = json.loads(resp.read().decode("utf-8"))
            results = res_data.get("results", [])
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "failed")
            self.assertIn("invalid package", results[0]["output"])

    def test_critical_package_protected_in_execute(self):
        """Verify POST /execute refuses to mutate Tier 4 critical packages."""
        payload = {
            "serial": "test-device",
            "mode": "dry-run",
            "action": "disable",
            "packages": ["android", "com.android.systemui"]
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/execute",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res_data = json.loads(resp.read().decode("utf-8"))
            results = res_data.get("results", [])
            self.assertEqual(len(results), 2)
            for r in results:
                self.assertEqual(r["status"], "skipped_protected")
                self.assertIn("protected", r["output"])


if __name__ == "__main__":
    unittest.main()
