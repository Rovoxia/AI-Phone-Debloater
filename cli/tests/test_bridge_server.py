"""
Unit tests for AI-Phone-Debloater Local ADB Bridge Server (cli/src/bridge_server.py).
Zero third-party pip dependencies; standard library unittest only.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "cli" / "src"))

import bridge_server


class TestBridgeServerHelpers(unittest.TestCase):
    """Test helper functions and security invariants in bridge_server.py."""

    def test_critical_packages_loaded(self):
        """Verify that load_critical_packages loads every entry of the critical rules file."""
        critical = bridge_server.load_critical_packages()
        with (REPO_ROOT / "cli" / "rules" / "critical-do-not-touch.json").open(encoding="utf-8") as fh:
            self.assertEqual(len(critical), len(json.load(fh)["rules"]))
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

    def test_package_trailing_newline_rejected(self):
        """A trailing newline must not slip past validation (and past the critical set)."""
        self.assertFalse(bridge_server.is_valid_package("com.android.systemui\n"))

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

    def _post(self, path, payload, content_type="application/json"):
        """POST a JSON-encoded payload; returns (status, decoded JSON body)."""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def test_cors_options(self):
        """Verify OPTIONS preflight echoes an allowed Origin and permits private-network access."""
        origin = "https://debloater.rovoxia.com"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/health", method="OPTIONS",
                                     headers={"Origin": origin})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), origin)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Private-Network"), "true")
            self.assertIn("GET", resp.headers.get("Access-Control-Allow-Methods", ""))

    def test_foreign_origin_rejected(self):
        """A request from a website that is not allow-listed gets 403 and no CORS grant.

        Localhost origins are not trusted by default either (opt in with --allow-origin).
        """
        for method, origin in (("GET", "https://evil.example"), ("OPTIONS", "https://evil.example"),
                               ("GET", "http://localhost:4321"), ("GET", "http://127.0.0.1:8080")):
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/health", method=method,
                                         headers={"Origin": origin})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 403)
            self.assertIsNone(ctx.exception.headers.get("Access-Control-Allow-Origin"))

    def test_foreign_host_rejected(self):
        """A DNS-rebinding request (Host is not loopback) gets 403."""
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/health",
                                     headers={"Host": f"evil.example:{self.port}"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_post_text_plain_rejected(self):
        """A POST that is not application/json (no CORS preflight needed) gets 415."""
        payload = {"serial": "test-device", "mode": "dry-run", "action": "disable", "packages": []}
        status, _ = self._post("/execute", payload, content_type="text/plain")
        self.assertEqual(status, 415)

    def test_allowed_origin_echoed(self):
        """Allowed origins are echoed back (never '*') together with Vary: Origin."""
        for origin in ("https://debloater.rovoxia.com",):
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/packages", headers={"Origin": origin})
            with self.assertRaises(urllib.error.HTTPError) as ctx:  # 400: no serial, no adb call
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 400)
            self.assertEqual(ctx.exception.headers.get("Access-Control-Allow-Origin"), origin)
            self.assertEqual(ctx.exception.headers.get("Vary"), "Origin")

    def test_url_encoded_serial_decoded(self):
        """A Wi-Fi serial sent as ip%3Aport reaches adb as ip:port."""
        with mock.patch.object(bridge_server, "run_adb", return_value=(0, "Pixel\n", "")) as run_adb, \
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/device?serial=192.168.1.5%3A5555") as resp:
            self.assertEqual(json.loads(resp.read())["serial"], "192.168.1.5:5555")
        self.assertEqual(run_adb.call_args.kwargs["serial"], "192.168.1.5:5555")

    def test_non_dict_body_rejected(self):
        """A JSON body that is not an object gets 400 rather than a dropped connection."""
        status, data = self._post("/execute", ["not", "a", "dict"])
        self.assertEqual(status, 400)
        self.assertFalse(data["success"])

    def test_critical_enable_allowed_disable_refused(self):
        """A critical package can be re-enabled through the bridge but never disabled."""
        payload = {"serial": "test-device", "mode": "dry-run", "action": "enable",
                   "packages": ["com.android.systemui"]}
        _, data = self._post("/execute", payload)
        self.assertEqual(data["results"][0]["status"], "success")
        _, data = self._post("/execute", {**payload, "action": "disable"})
        self.assertEqual(data["results"][0]["status"], "skipped_protected")

    def test_failed_snapshot_aborts_apply(self):
        """If the pre-apply snapshot cannot read the device, no pm command is run."""
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(bridge_server, "BACKUPS_DIR", Path(tmp)), \
                mock.patch.object(bridge_server, "run_adb", return_value=(1, "", "device offline")) as run_adb:
            status, data = self._post("/execute", {"serial": "test-device", "mode": "apply",
                                                   "action": "disable", "packages": ["com.example.app"]})
        self.assertEqual(status, 500)
        self.assertIn("snapshot failed", data["error"])
        self.assertFalse(any("disable-user" in " ".join(c.args[0]) for c in run_adb.call_args_list))

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


    def test_reusable_server_address_reuse(self):
        """Verify ReusableThreadingHTTPServer reuses the address except on Windows, and uses daemon threads."""
        server = bridge_server.ReusableThreadingHTTPServer(("127.0.0.1", 0), bridge_server.BridgeHandler)
        try:
            self.assertEqual(server.allow_reuse_address, os.name != "nt")
            self.assertTrue(server.daemon_threads)
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
