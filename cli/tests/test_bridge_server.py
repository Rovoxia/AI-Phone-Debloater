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
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "cli" / "src"))

import bridge_server
from connection.adb_client import AdbClient
from connection.exceptions import (
    OperationCancelledError,
    PairingError,
    PairingTimeoutError,
)
from connection.qr_generator import generate_qr_matrix

QR_PAYLOAD = "WIFI:T:ADB;S:AI_Phone_Debloater_Rovoxia_abc123;P:123456;;"


class FakePairingManager:
    """Stands in for connection.qr_pairing.QrPairingManager; the flow blocks until the test ends it."""

    def __init__(self):
        self.done = threading.Event()
        self.result = None  # what the flow returns, or the exception it raises
        self.cancelled = False

    def create_pairing_session(self, ttl_seconds=120.0):
        return SimpleNamespace(session_id="abc123", qr_payload=QR_PAYLOAD)

    def execute_qr_pairing_flow(self, session=None, timeout=120.0):
        self.done.wait(10)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def finish(self, result):
        self.result = result
        self.done.set()

    def cancel(self):
        self.cancelled = True
        self.finish(OperationCancelledError("QR pairing cancelled by user."))


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

    def test_session_token_from_env(self):
        """AIPD_BRIDGE_TOKEN is used when valid, refused when short or not header-safe, random when unset."""
        with mock.patch.dict(os.environ, {bridge_server.TOKEN_ENV: "a" * 16}):
            self.assertEqual(bridge_server.session_token(), "a" * 16)
        for bad in ("a" * 15, "a" * 16 + " b", "a" * 16 + "#"):
            with mock.patch.dict(os.environ, {bridge_server.TOKEN_ENV: bad}), self.assertRaises(SystemExit):
                bridge_server.session_token()
        with mock.patch.dict(os.environ, {bridge_server.TOKEN_ENV: ""}):
            first, second = bridge_server.session_token(), bridge_server.session_token()
        self.assertNotEqual(first, second)
        self.assertTrue(bridge_server.TOKEN_RE.fullmatch(first))


class TestBridgeHttpEndpoints(unittest.TestCase):
    """Test HTTP request routing, CORS, and endpoint responses."""

    def setUp(self):
        self.server = bridge_server.ThreadingHTTPServer(("127.0.0.1", 0), bridge_server.BridgeHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.auth = {bridge_server.TOKEN_HEADER: bridge_server.BRIDGE_TOKEN}

    def tearDown(self):
        bridge_server.cancel_pairing()
        bridge_server._PAIR.update(state="idle", id=None, serial=None, error=None)
        self.server.shutdown()
        self.server.server_close()

    def _send(self, req):
        """Send a request; returns (status, decoded JSON body) for success and HTTP errors alike."""
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def _get(self, path, headers=None):
        """GET with the given headers (default: the session token)."""
        return self._send(urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                                 headers=self.auth if headers is None else headers))

    def _post(self, path, payload, content_type="application/json", headers=None):
        """POST a JSON-encoded payload, with the session token unless other headers are given."""
        return self._send(urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": content_type, **(self.auth if headers is None else headers)},
        ))

    def test_token_missing_rejected(self):
        """Without X-Bridge-Token every route but /health answers 401 and never reaches adb."""
        payload = {"serial": "test-device", "mode": "apply", "action": "disable", "packages": ["com.example.app"]}
        with mock.patch.object(bridge_server, "run_adb") as run_adb:
            for path in ("/devices", "/packages?serial=x", "/device?serial=x", "/nope"):
                status, data = self._get(path, headers={})
                self.assertEqual(status, 401, path)
                self.assertFalse(data["success"])
            for path in ("/execute", "/restore", "/nope"):
                status, data = self._post(path, payload, headers={})
                self.assertEqual(status, 401, path)
                self.assertFalse(data["success"])
        run_adb.assert_not_called()

    def test_token_wrong_rejected(self):
        """A wrong token (a prefix, a longer one, other case, a non-ASCII one) answers 401, with CORS headers."""
        token = bridge_server.BRIDGE_TOKEN
        payload = {"serial": "s", "mode": "dry-run", "action": "disable", "packages": ["com.example.app"]}
        with mock.patch.object(bridge_server, "run_adb") as run_adb:
            for wrong in ("x" * len(token), token[:-1], token + "x", token.swapcase(), "t\u00f6ken"):
                headers = {bridge_server.TOKEN_HEADER: wrong}
                self.assertEqual(self._get("/devices", headers=headers)[0], 401, wrong)
                status, data = self._post("/execute", payload, headers=headers)
                self.assertEqual(status, 401, wrong)
                self.assertNotIn("results", data)
        run_adb.assert_not_called()
        origin = "https://debloater.rovoxia.com"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/devices", headers={"Origin": origin})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 401)
        self.assertEqual(ctx.exception.headers.get("Access-Control-Allow-Origin"), origin)

    def test_token_right_accepted(self):
        """The right token reaches the route."""
        listing = "List of devices attached\nABC123 device product:p model:Pixel_7\n"
        with mock.patch.object(bridge_server, "run_adb", return_value=(0, listing, "")):
            status, data = self._get("/devices")
        self.assertEqual(status, 200)
        self.assertEqual(data["devices"][0]["serial"], "ABC123")
        status, data = self._post("/execute", {"serial": "ABC123", "mode": "dry-run", "action": "disable",
                                               "packages": ["com.example.app"]})
        self.assertEqual(status, 200)
        self.assertEqual(data["results"][0]["status"], "success")

    def test_token_does_not_bypass_gate(self):
        """A valid token does not help a foreign origin or a rebound Host: _gate still answers 403."""
        for extra in ({"Origin": "https://evil.example"}, {"Host": "evil.example"}):
            status, _ = self._get("/devices", headers={**self.auth, **extra})
            self.assertEqual(status, 403)

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
            self.assertIn(bridge_server.TOKEN_HEADER, resp.headers.get("Access-Control-Allow-Headers", ""))

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
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/packages",
                                         headers={"Origin": origin, **self.auth})
            with self.assertRaises(urllib.error.HTTPError) as ctx:  # 400: no serial, no adb call
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 400)
            self.assertEqual(ctx.exception.headers.get("Access-Control-Allow-Origin"), origin)
            self.assertEqual(ctx.exception.headers.get("Vary"), "Origin")

    def test_url_encoded_serial_decoded(self):
        """A Wi-Fi serial sent as ip%3Aport reaches adb as ip:port."""
        with mock.patch.object(bridge_server, "run_adb", return_value=(0, "Pixel\n", "")) as run_adb, \
                urllib.request.urlopen(urllib.request.Request(
                    f"http://127.0.0.1:{self.port}/device?serial=192.168.1.5%3A5555", headers=self.auth)) as resp:
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
        """Verify GET /health needs no token, says that one is required and never reveals it."""
        for path in ("/health", "/api/health"):
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as resp:
                self.assertEqual(resp.status, 200)
                body = resp.read().decode("utf-8")
                self.assertNotIn(bridge_server.BRIDGE_TOKEN, body + str(resp.headers))
            data = json.loads(body)
            self.assertEqual(data.get("status"), "ok")
            self.assertIn("version", data)
            self.assertIn("adb_available", data)
            self.assertIs(data.get("token_required"), True)

    def test_packages_missing_serial_rejection(self):
        """Verify GET /packages rejects request without serial parameter."""
        self.assertEqual(self._get("/packages")[0], 400)

    def test_device_missing_serial_rejection(self):
        """Verify GET /device rejects request without serial parameter."""
        self.assertEqual(self._get("/device")[0], 400)

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
            headers={"Content-Type": "application/json", **self.auth}
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
            headers={"Content-Type": "application/json", **self.auth}
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
            headers={"Content-Type": "application/json", **self.auth}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res_data = json.loads(resp.read().decode("utf-8"))
            results = res_data.get("results", [])
            self.assertEqual(len(results), 2)
            for r in results:
                self.assertEqual(r["status"], "skipped_protected")
                self.assertIn("protected", r["output"])


    # -- Wi-Fi QR pairing ---------------------------------------------------

    def _start_pairing(self):
        """POST /pair/qr against a fake manager; returns (fake, status, body)."""
        fake = FakePairingManager()
        with mock.patch.object(bridge_server, "new_pairing_manager", return_value=fake):
            status, data = self._post("/pair/qr", {})
        return fake, status, data

    def _pair_state(self, expected):
        """Poll /pair/status until the pairing thread has recorded `expected`."""
        deadline = time.monotonic() + 5
        while True:
            status, data = self._get("/pair/status")
            self.assertEqual(status, 200)
            if data["state"] == expected or time.monotonic() > deadline:
                self.assertEqual(data["state"], expected)
                return data
            time.sleep(0.02)

    def test_pair_routes_need_token(self):
        """All three pairing routes answer 401 without the token, and no session is started."""
        with mock.patch.object(bridge_server, "new_pairing_manager") as factory:
            self.assertEqual(self._get("/pair/status", headers={})[0], 401)
            for path in ("/pair/qr", "/pair/cancel"):
                status, data = self._post(path, {}, headers={})
                self.assertEqual(status, 401, path)
                self.assertNotIn("matrix", data)
        factory.assert_not_called()
        self.assertEqual(self._get("/pair/status")[1],
                         {"state": "idle", "id": None, "serial": None, "error": None})

    def test_pair_start_returns_matrix(self):
        """Starting returns the session's QR as rows of 0/1; a second start while it runs gets 409."""
        _, status, data = self._start_pairing()
        self.assertEqual(status, 200)
        self.assertEqual(data["matrix"], [[int(c) for c in row] for row in generate_qr_matrix(QR_PAYLOAD)])
        self.assertEqual((data["state"], data["id"], data["timeout"]), ("waiting", "abc123", 120))
        self.assertEqual(self._get("/pair/status")[1]["state"], "waiting")
        with mock.patch.object(bridge_server, "new_pairing_manager") as factory:
            status, data = self._post("/pair/qr", {})
        self.assertEqual(status, 409)
        self.assertNotIn("matrix", data)
        factory.assert_not_called()

    def test_pair_status_paired(self):
        """When the flow returns a device, status is paired with its serial, and a new session may start."""
        fake, _, _ = self._start_pairing()
        fake.finish(SimpleNamespace(serial="192.168.1.5:5555"))
        data = self._pair_state("paired")
        self.assertEqual((data["serial"], data["error"]), ("192.168.1.5:5555", None))
        self.assertEqual(self._start_pairing()[1], 200)

    def test_pair_status_failed_and_expired(self):
        """A pairing error ends in failed, a scan timeout in expired, both with the reason."""
        for error, state in ((PairingError("Pairing handshake failed: wrong password"), "failed"),
                             (PairingTimeoutError("QR pairing timed out"), "expired")):
            fake, _, _ = self._start_pairing()
            fake.finish(error)
            data = self._pair_state(state)
            self.assertEqual((data["serial"], data["error"]), (None, str(error)))

    def test_pair_cancel(self):
        """Cancel stops the waiting session and leaves idle; with nothing running it is a no-op."""
        fake, _, _ = self._start_pairing()
        status, data = self._post("/pair/cancel", {})
        self.assertEqual((status, data["state"]), (200, "idle"))
        self.assertTrue(fake.cancelled)
        self.assertEqual(self._post("/pair/cancel", {})[1]["state"], "idle")
        self.assertEqual(self._start_pairing()[1], 200)

    def test_pair_start_failure_reported(self):
        """If the session cannot start (no adb, say) the route answers 502 and stays idle."""
        with mock.patch.object(bridge_server, "new_pairing_manager",
                               side_effect=RuntimeError("adb executable not found: x")):
            status, data = self._post("/pair/qr", {})
        self.assertEqual(status, 502)
        self.assertIn("adb executable not found", data["error"])
        self.assertEqual(self._get("/pair/status")[1]["state"], "idle")

    def test_pair_uses_only_the_bridge_adb(self):
        """The pairing code never falls back to an adb other than the one the bridge resolved."""
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("connection.adb_client.shutil.which", return_value=sys.executable), \
                self.assertRaises(RuntimeError):
            bridge_server.new_pairing_manager(str(Path(tmp) / "adb"))

    def test_pair_end_to_end_with_real_pairing_code(self):
        """The real QrPairingManager, driven from the bridge's thread, pairs with the password in the QR."""
        calls = []

        def run_adb(_client, args, timeout=None, serial=None):
            calls.append(args)
            if args == ["mdns", "services"]:
                name = f"AI_Phone_Debloater_Rovoxia_{bridge_server._PAIR['id']}"
                return 0, f"List of discovered mdns services\n{name}\t_adb-tls-pairing._tcp\t192.168.1.5:37123\n", ""
            if args[0] == "pair":
                return 0, "Successfully paired to 192.168.1.5:37123 [guid=adb-test]\n", ""
            if args == ["devices", "-l"]:
                return 0, "List of devices attached\n192.168.1.5:5555 device product:p model:Pixel_7\n", ""
            return 0, "device\n", ""  # get-state, getprop

        made = []
        real_factory = bridge_server.new_pairing_manager

        def factory(adb_path):
            made.append(real_factory(adb_path))
            return made[0]

        with tempfile.TemporaryDirectory() as tmp:
            adb = Path(tmp) / "adb"
            adb.write_text("")
            adb.chmod(0o755)
            with mock.patch.object(bridge_server, "discover_adb", return_value=str(adb)), \
                    mock.patch.object(bridge_server, "new_pairing_manager", side_effect=factory), \
                    mock.patch.object(AdbClient, "run_adb", run_adb):
                status, data = self._post("/pair/qr", {})
                self.assertEqual(status, 200)
                self.assertEqual(self._pair_state("paired")["serial"], "192.168.1.5:5555")
        session = made[0]._active_session
        self.assertRegex(session.qr_payload, r"^WIFI:T:ADB;S:AI_Phone_Debloater_Rovoxia_[0-9a-f]{6};P:\d{6};;$")
        self.assertEqual(data["matrix"], [[int(c) for c in row] for row in generate_qr_matrix(session.qr_payload)])
        self.assertIn(["pair", "192.168.1.5:37123", session.password], calls)
        self.assertEqual(made[0].adb.adb_path, str(adb))

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
