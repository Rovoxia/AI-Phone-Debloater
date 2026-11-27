"""
Unit tests for AI-Phone-Debloater Local ADB Bridge Server (cli/src/bridge_server.py).
Zero third-party pip dependencies; standard library unittest only.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
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

HEADER = "List of devices attached\n"
PIXEL_USB = "R58M12ABCDE            device usb:1-1 product:shiba model:Pixel_8 device:shiba transport_id:3"
PIXEL_WIFI = "192.168.1.20:41234     device product:shiba model:Pixel_8 device:shiba transport_id:6"
PIXEL_MDNS = ("adb-R58M12ABCDE-a1b2c3._adb-tls-connect._tcp device product:shiba model:Pixel_8 "
              "device:shiba transport_id:7")
NEW_PHONE = "0123456789ABCDEF       unauthorized usb:1-2 transport_id:4"
MDNS_UP = (0, "mdns daemon version [adb discovery 0.0.0]\n", "")
MDNS_OFF = (0, "ERROR: mdns discovery disabled\n", "")
MDNS_HEADER = "List of discovered mdns services\n"
PAIRED = (0, "Successfully paired to 192.168.1.20:37123 [guid=adb-R58M12ABCDE-a1b2c3]\n", "")
PAIR_BODY = {"host": "192.168.1.20", "port": 37123, "code": "123456"}
CONNECT_BODY = {"host": "192.168.1.20", "port": 41234}

# Every wait in the bridge, shrunk so that no test sleeps for long.
FAST = {
    "DEVICES_FRESH_FOR": 0.0, "DEVICES_POLL_INTERVAL": 0.02,
    "CONNECT_CONFIRM_WAIT": 0.4, "CONNECT_CONFIRM_INTERVAL": 0.01,
    "PAIR_CONNECT_WAIT": 0.3, "PAIR_AUTOCONNECT_GRACE": 0.0, "PAIR_CONNECT_INTERVAL": 0.01,
}


class FakeAdb:
    """Stands in for bridge_server.run_adb: scripted answers, every call recorded, no process started.

    `devices` is the body of `adb devices -l` (the header is added). Given a list, each call
    takes the next entry and the last one stays. `answers` maps the first one or two
    arguments ("pair", "mdns check") to (rc, stdout, stderr), an exception to raise, or a
    function of the arguments. Anything else exits 0 with no output.
    """

    def __init__(self, devices=""):
        self.devices = devices
        self.answers = {}
        self.calls = []
        self._lock = threading.Lock()

    def __call__(self, args, adb_path, serial=None, timeout=30.0):
        with self._lock:
            self.calls.append(list(args))
            if args == ["devices", "-l"]:
                answer = self.devices
                if isinstance(answer, list):
                    answer = answer.pop(0) if len(answer) > 1 else answer[0]
                if isinstance(answer, str):
                    answer = (0, HEADER + answer + "\n\n", "")
            else:
                answer = self.answers.get(" ".join(args[:2]), self.answers.get(args[0], (0, "", "")))
        if callable(answer):
            answer = answer(args)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def count(self, *prefix):
        """How many calls started with these arguments."""
        with self._lock:
            return sum(1 for call in self.calls if call[:len(prefix)] == list(prefix))


class FakePairingManager:
    """Stands in for connection.qr_pairing.QrPairingManager; the flow blocks until the test ends it."""

    def __init__(self):
        self.done = threading.Event()
        self.result = None  # what the flow returns, or the exception it raises
        self.cancelled = False
        self.unconnected = None  # an address: the phone is paired, but no connect port was found

    def create_pairing_session(self, ttl_seconds=120.0):
        return SimpleNamespace(session_id="abc123", qr_payload=QR_PAYLOAD)

    def execute_qr_pairing_flow(self, session=None, timeout=120.0, port_prompt_cb=None):
        self.done.wait(10)
        if self.unconnected and port_prompt_cb:  # the real flow asks for the port at this point
            port_prompt_cb(self.unconnected)
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


class TestDeviceListParsing(unittest.TestCase):
    """`adb devices -l` output as the bridge reads it. The samples follow adb's printf formats."""

    def _one(self, line):
        entries = bridge_server.parse_devices(HEADER + line + "\n\n")
        self.assertEqual(len(entries), 1, line)
        return entries[0]

    def test_authorized_device_with_all_fields(self):
        self.assertEqual(self._one(PIXEL_USB), {
            "serial": "R58M12ABCDE", "state": "device", "raw_state": "device", "detail": "",
            "model": "Pixel_8", "product": "shiba", "device": "shiba", "transport_id": "3",
            "transport": "usb",
        })

    def test_unauthorized_and_offline_have_no_fields(self):
        """A phone that has not finished the handshake prints no product, model or device."""
        entry = self._one(NEW_PHONE)
        self.assertEqual((entry["serial"], entry["state"], entry["raw_state"]),
                         ("0123456789ABCDEF", "unauthorized", "unauthorized"))
        self.assertEqual((entry["model"], entry["product"], entry["device"]), ("", "", ""))
        self.assertEqual((entry["transport_id"], entry["transport"]), ("4", "usb"))
        entry = self._one("ZY22ABCDEF             offline transport_id:5")
        self.assertEqual((entry["serial"], entry["state"], entry["model"], entry["transport_id"]),
                         ("ZY22ABCDEF", "offline", "", "5"))

    def test_every_known_state_word(self):
        for state in ("device", "unauthorized", "authorizing", "connecting", "offline", "recovery",
                      "sideload", "bootloader", "rescue", "host", "detached"):
            entry = self._one(f"SERIAL123              {state} transport_id:1")
            self.assertEqual((entry["serial"], entry["state"], entry["raw_state"]), ("SERIAL123", state, state))

    def test_no_permissions_sentence(self):
        """The Linux "no permissions" state is a sentence: it must not come out as state "no"."""
        hint = "(user in plugdev group; are your udev rules wrong?); see [http://developer.android.com/tools/device.html]"
        entry = self._one(f"????????????           no permissions {hint} usb:1-3 transport_id:8")
        self.assertEqual(entry["serial"], "????????????")
        self.assertEqual((entry["state"], entry["raw_state"]), ("no_permissions", "no permissions"))
        self.assertEqual(entry["detail"], hint)
        self.assertEqual((entry["transport_id"], entry["model"]), ("8", ""))
        entry = self._one("0a388e93               no permissions; see [http://developer.android.com/tools/device.html]")
        self.assertEqual((entry["serial"], entry["state"]), ("0a388e93", "no_permissions"))
        self.assertEqual(entry["detail"], "see [http://developer.android.com/tools/device.html]")
        self.assertEqual(entry["transport_id"], "")

    def test_serial_containing_spaces(self):
        entry = self._one("(no serial number)     device product:p model:M device:d transport_id:9")
        self.assertEqual((entry["serial"], entry["state"], entry["model"], entry["transport_id"]),
                         ("(no serial number)", "device", "M", "9"))
        # mDNS renames a second instance with " (2)"; the serial is longer than the 22-column pad.
        serial = "adb-R58M12ABCDE-a1b2c3 (2)._adb-tls-connect._tcp"
        entry = self._one(f"{serial} device product:shiba model:Pixel_8 device:shiba transport_id:10")
        self.assertEqual((entry["serial"], entry["state"], entry["transport"]), (serial, "device", "wifi"))
        self.assertEqual((entry["model"], entry["transport_id"]), ("Pixel_8", "10"))
        # Even a state word inside the serial does not end it: the state is the last such word.
        entry = self._one("my device (2)._adb-tls-connect._tcp unauthorized transport_id:12")
        self.assertEqual((entry["serial"], entry["state"]), ("my device (2)._adb-tls-connect._tcp", "unauthorized"))

    def test_short_form_is_tab_separated(self):
        """`adb devices` without -l prints serial<TAB>state."""
        out = (HEADER + "R58M12ABCDE\tdevice\n0123456789ABCDEF\tunauthorized\n(no serial number)\toffline\n"
               "????????????\tno permissions; see [http://developer.android.com/tools/device.html]\n\n")
        entries = bridge_server.parse_devices(out)
        self.assertEqual([(e["serial"], e["state"]) for e in entries], [
            ("R58M12ABCDE", "device"), ("0123456789ABCDEF", "unauthorized"),
            ("(no serial number)", "offline"), ("????????????", "no_permissions"),
        ])
        self.assertEqual(entries[3]["detail"], "see [http://developer.android.com/tools/device.html]")
        self.assertTrue(all(e["model"] == "" and e["transport_id"] == "" for e in entries))

    def test_daemon_noise_is_not_a_device(self):
        """Start-up and version lines never become devices, wherever adb prints them."""
        out = ("* daemon not running; starting now at tcp:5037\n"
               "adb server version (41) doesn't match this client (39); killing...\n"
               "* daemon started successfully\n"
               + HEADER
               + "* daemon not running. starting it now on port 5037 *\n"
               "* daemon started successfully *\n"
               + PIXEL_USB + "\r\n\r\n")
        entries = bridge_server.parse_devices(out)
        self.assertEqual([e["serial"] for e in entries], ["R58M12ABCDE"])
        self.assertEqual(entries[0]["transport_id"], "3")  # the carriage return is not part of it
        self.assertEqual(bridge_server.parse_devices(HEADER + "\n"), [])

    def test_transport_from_serial(self):
        entry = self._one("emulator-5554          device product:sdk_gphone64_x86_64 "
                          "model:sdk_gphone64_x86_64 device:emu64xa transport_id:1")
        self.assertEqual((entry["serial"], entry["transport"], entry["device"]), ("emulator-5554", "emulator", "emu64xa"))
        entry = self._one(PIXEL_WIFI)
        self.assertEqual((entry["serial"], entry["transport"], entry["state"]), ("192.168.1.20:41234", "wifi", "device"))
        entry = self._one(PIXEL_MDNS)
        self.assertEqual((entry["serial"], entry["transport"]),
                         ("adb-R58M12ABCDE-a1b2c3._adb-tls-connect._tcp", "wifi"))
        self.assertEqual((entry["model"], entry["transport_id"]), ("Pixel_8", "7"))
        self.assertEqual(self._one("adb-R58M12ABCDE._adb._tcp device transport_id:2")["transport"], "wifi")
        self.assertEqual(self._one(PIXEL_USB)["transport"], "usb")

    def test_unknown_state_word(self):
        """A state this bridge does not know is reported as unknown, with adb's word kept."""
        entry = self._one("FUTURE123              fastbootd usb:1-4 transport_id:11")
        self.assertEqual((entry["serial"], entry["state"], entry["raw_state"], entry["transport_id"]),
                         ("FUTURE123", "unknown", "fastbootd", "11"))

    def test_adbs_own_unknown_state_keeps_a_spaced_serial_whole(self):
        """adb itself prints "unknown" for a state it cannot name: it is a state word like the others."""
        entry = self._one("(no serial number)     unknown transport_id:13")
        self.assertEqual((entry["serial"], entry["state"], entry["raw_state"], entry["transport_id"]),
                         ("(no serial number)", "unknown", "unknown", "13"))
        entry = self._one("(no serial number)\tunknown")
        self.assertEqual((entry["serial"], entry["state"], entry["raw_state"]),
                         ("(no serial number)", "unknown", "unknown"))

    def test_usb_serial_with_colons_is_not_wifi(self):
        """wifi is IPv4:port or an adb mDNS name. A colon alone does not make a serial a network one."""
        for serial in ("00:11:22:33:44:55", "ABC:123", "ABC:5555", "192.168.1.20:abc", "192.168.1.20:0",
                       "192.168.1.20:99999", "192.168.1.20:²", "999.1.1.1:5555", ":5555", "R58M12ABCDE"):
            self.assertEqual(bridge_server.device_transport(serial), "usb", serial)
            self.assertEqual(self._one(f"{serial} device transport_id:1")["transport"], "usb", serial)
        for serial in ("192.168.1.20:41234", "10.0.0.7:5555", "127.0.0.1:5555",
                       "adb-R58M12ABCDE-a1b2c3._adb-tls-connect._tcp",
                       "adb-R58M12ABCDE-a1b2c3 (2)._adb-tls-connect._tcp", "adb-R58M12ABCDE._adb._tcp"):
            self.assertEqual(bridge_server.device_transport(serial), "wifi", serial)
            self.assertEqual(self._one(f"{serial} device transport_id:1")["transport"], "wifi", serial)
        self.assertEqual(bridge_server.device_transport("emulator-5554"), "emulator")

    def test_several_devices_keep_adb_order(self):
        out = f"{HEADER}{PIXEL_USB}\n{NEW_PHONE}\n{PIXEL_WIFI}\n{PIXEL_MDNS}\n\n"
        entries = bridge_server.parse_devices(out)
        self.assertEqual([e["state"] for e in entries], ["device", "unauthorized", "device", "device"])
        self.assertEqual([e["transport"] for e in entries], ["usb", "usb", "wifi", "wifi"])

    def test_output_without_header_is_an_error(self):
        """An error message in place of the list is an adb failure, not a device named "error:"."""
        for out in ("", "error: cannot connect to daemon\n", PIXEL_USB + "\n"):
            with self.assertRaises(bridge_server.AdbError) as ctx:
                bridge_server.parse_devices(out)
            self.assertEqual(bridge_server.failure_code(ctx.exception), (502, "adb_failed"))

    def test_adb_devices_failure(self):
        with mock.patch.object(bridge_server, "run_adb", return_value=(1, "", "error: cannot connect to daemon")), \
                self.assertRaises(bridge_server.AdbError) as ctx:
            bridge_server.adb_devices("adb")
        self.assertIn("cannot connect to daemon", str(ctx.exception))


class TestRunAdbAndValidation(unittest.TestCase):
    """How run_adb classifies failures, and what may reach an adb command line."""

    def test_failures_are_classified(self):
        cases = (
            (FileNotFoundError(2, "No such file"), bridge_server.AdbNotFoundError, (502, "adb_not_found")),
            (PermissionError(13, "Permission denied"), bridge_server.AdbNotFoundError, (502, "adb_not_found")),
            (subprocess.TimeoutExpired(["adb"], 5), bridge_server.AdbTimeoutError, (504, "adb_timeout")),
            (ValueError("embedded null byte"), bridge_server.AdbError, (502, "adb_failed")),
        )
        for raised, kind, code in cases:
            with mock.patch.object(bridge_server.subprocess, "run", side_effect=raised), \
                    self.assertRaises(RuntimeError) as ctx:  # still a RuntimeError, as before
                bridge_server.run_adb(["devices", "-l"], "adb-test")
            self.assertIs(type(ctx.exception), kind)
            self.assertEqual(bridge_server.failure_code(ctx.exception), code)
        self.assertEqual(bridge_server.failure_code(RuntimeError("old style")), (502, "adb_failed"))
        self.assertEqual(bridge_server.failure_code(OSError("disk full")), (502, "adb_failed"))

    def test_nonzero_exit_is_returned_not_raised(self):
        done = SimpleNamespace(returncode=1, stdout=None, stderr="error: device offline\n")
        with mock.patch.object(bridge_server.subprocess, "run", return_value=done) as run:
            self.assertEqual(bridge_server.run_adb(["get-state"], "adb-test", serial="a b"),
                             (1, "", "error: device offline\n"))
        self.assertEqual(run.call_args.args[0], ["adb-test", "-s", "a b", "get-state"])
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_pairing_code_never_in_an_error(self):
        """A timed-out or unstartable `adb pair` reports the command without the code."""
        args = ["pair", "192.168.1.20:37123", "654321"]
        for raised in (subprocess.TimeoutExpired(["adb-test", *args], 30), PermissionError(13, "Permission denied")):
            with mock.patch.object(bridge_server.subprocess, "run", side_effect=raised), \
                    self.assertRaises(bridge_server.AdbError) as ctx:
                bridge_server.run_adb(args, "adb-test", timeout=30)
            self.assertNotIn("654321", str(ctx.exception))
            self.assertIn("pair 192.168.1.20:37123 ******", str(ctx.exception))
        with mock.patch.object(bridge_server.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(["adb-test", *args], 30)), \
                self.assertRaises(bridge_server.AdbTimeoutError) as ctx:
            bridge_server.run_adb(args, "adb-test", serial="s", timeout=30)
        # The original error names the whole command: it must not ride along into a traceback.
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)
        self.assertIn("adb-test -s s pair 192.168.1.20:37123 ******", str(ctx.exception))

    def test_valid_host(self):
        for good in ("192.168.1.20", "10.0.0.7", "127.0.0.1", "172.16.254.1"):
            self.assertEqual(bridge_server.valid_host(good), good)
        for bad in ("", "0.0.0.0", "255.255.255.255", "224.0.0.251", "239.1.2.3", "192.168.1", "192.168.1.256",
                    "192.168.1.20 ", " 192.168.1.20", "192.168.1.20\n", "192.168.01.20", "-192.168.1.20",
                    "--help", "-s", "phone.local", "localhost", "::1", "fe80::1", "192.168.1.20:5555",
                    "192.168.1.20/24", "1.2.3.4;reboot", "١٩٢.١٦٨.١.٢٠", 3232235796, 1.5, None, True,
                    ["192.168.1.20"], {"host": "192.168.1.20"}):
            self.assertIsNone(bridge_server.valid_host(bad), repr(bad))

    def test_valid_port(self):
        for good in (1, 5555, 37123, 65535):
            self.assertEqual(bridge_server.valid_port(good), good)
        for bad in (0, -1, 65536, 10**9, "5555", "37123", 5555.0, 1.5, True, False, None, [5555]):
            self.assertIsNone(bridge_server.valid_port(bad), repr(bad))

    def test_port_number_never_raises(self):
        """Port text from adb output: only 1 to 5 ASCII digits in range count, anything else is None."""
        for text, want in (("41234", 41234), ("1", 1), ("65535", 65535), ("00080", 80), ("0", None),
                           ("65536", None), ("", None), ("-1", None), (" 80", None), ("80 ", None),
                           ("5555a", None), ("²", None), ("４１２３４", None), ("٤١٢٣٤", None),
                           ("9" * 5000, None)):
            self.assertEqual(bridge_server.port_number(text), want, text[:12])

    def test_pair_code_pattern(self):
        self.assertTrue(bridge_server.PAIR_CODE_RE.fullmatch("012345"))
        for bad in ("", "12345", "1234567", "12345a", "123 456", " 123456", "123456\n", "-12345", "١٢٣٤٥٦"):
            self.assertIsNone(bridge_server.PAIR_CODE_RE.fullmatch(bad), repr(bad))

    def test_warm_adb_server_never_raises(self):
        """The background start-server sets the ready flag whether adb works, fails or is missing."""
        self.addCleanup(bridge_server._ADB_READY.set)
        for answer in ((0, "", "* daemon started successfully\n"), (1, "", "* failed to start daemon\n"),
                       bridge_server.AdbNotFoundError("adb executable not found: x"),
                       bridge_server.AdbTimeoutError("command timed out")):
            adb = FakeAdb()
            adb.answers["start-server"] = answer
            bridge_server._ADB_READY.clear()
            with mock.patch.object(bridge_server, "run_adb", adb), mock.patch.object(bridge_server, "_log") as log:
                bridge_server.warm_adb_server("adb-test")
            self.assertTrue(bridge_server._ADB_READY.is_set())
            self.assertEqual(adb.calls, [["start-server"]])
            self.assertEqual(log.called, answer != (0, "", "* daemon started successfully\n"))


class TestStartBridge(unittest.TestCase):
    """start_bridge binds first and starts adb on the side."""

    def test_adb_is_warmed_in_the_background_after_the_bind(self):
        events = []
        warmed = threading.Event()

        class FakeServer:
            def __init__(self, address, handler):
                events.append(f"bind {address[0]}")

            def serve_forever(self):
                warmed.wait(5)  # the warm-up thread was started before serving, and is not awaited
                events.append("serve")

            def shutdown(self):
                pass

            def server_close(self):
                events.append("close")

        def warm():
            events.append(f"warm, adb ready: {bridge_server._ADB_READY.is_set()}")
            bridge_server._ADB_READY.set()
            warmed.set()

        token = bridge_server.BRIDGE_TOKEN
        self.addCleanup(setattr, bridge_server, "BRIDGE_TOKEN", token)
        self.addCleanup(bridge_server._STOP.clear)
        self.addCleanup(bridge_server._ADB_READY.set)
        with mock.patch.object(bridge_server, "ReusableThreadingHTTPServer", FakeServer), \
                mock.patch.object(bridge_server, "warm_adb_server", warm), \
                mock.patch.object(bridge_server.signal, "signal"), \
                mock.patch.object(bridge_server, "_log"), \
                mock.patch.dict(os.environ, {bridge_server.TOKEN_ENV: "t" * 16}):
            bridge_server.start_bridge(port=0)
        # Requests that need adb wait while the flag is clear; /health does not.
        self.assertEqual(events, ["bind 127.0.0.1", "warm, adb ready: False", "serve", "close"])
        self.assertTrue(bridge_server._STOP.is_set())  # held requests are told to end

    def test_signal_handler_ends_held_requests_and_stops_the_server(self):
        """Ctrl+C: the handler sets the stop flag (held long polls answer) and shuts the server down."""
        seen = {}
        shut_down = threading.Event()

        class FakeServer:
            def __init__(self, address, handler):
                pass

            def serve_forever(self):
                handler = register.call_args_list[0].args[1]  # what start_bridge registered for SIGINT
                seen["before"] = bridge_server._STOP.is_set()
                handler(2, None)
                seen["after"] = bridge_server._STOP.is_set()
                seen["shut down"] = shut_down.wait(5)
                handler(2, None)  # a second Ctrl+C is ignored
                seen["closed"] = False

            def shutdown(self):
                seen["shutdown calls"] = seen.get("shutdown calls", 0) + 1
                shut_down.set()

            def server_close(self):
                seen["closed"] = True

        token = bridge_server.BRIDGE_TOKEN
        self.addCleanup(setattr, bridge_server, "BRIDGE_TOKEN", token)
        self.addCleanup(bridge_server._STOP.clear)
        self.addCleanup(bridge_server._ADB_READY.set)
        with mock.patch.object(bridge_server, "ReusableThreadingHTTPServer", FakeServer), \
                mock.patch.object(bridge_server, "warm_adb_server", bridge_server._ADB_READY.set), \
                mock.patch.object(bridge_server.signal, "signal") as register, \
                mock.patch.object(bridge_server, "_log"), \
                mock.patch.dict(os.environ, {bridge_server.TOKEN_ENV: "t" * 16}):
            bridge_server.start_bridge(port=0)
        self.assertEqual(seen, {"before": False, "after": True, "shut down": True, "shutdown calls": 1,
                                "closed": True})
        self.assertGreaterEqual(register.call_count, 1)


class TestMdnsParsing(unittest.TestCase):
    """`adb mdns check` and `adb mdns services` output."""

    def test_services_are_split_on_tabs(self):
        out = (MDNS_HEADER
               + "adb-R58M12ABCDE-a1b2c3\t_adb-tls-connect._tcp\t192.168.1.20:41234\n"
               "adb-R58M12ABCDE-a1b2c3\t_adb-tls-pairing._tcp\t192.168.1.20:37123\n"
               "AI Phone Debloater (2)\t_adb-tls-pairing._tcp.\t192.168.1.21:40001\n"
               "adb-R58M12ABCDE\t_adb._tcp\t192.168.1.20:5555\n")
        self.assertEqual(bridge_server.parse_mdns_services(out), [
            {"name": "adb-R58M12ABCDE-a1b2c3", "type": "_adb-tls-connect._tcp", "kind": "connect",
             "host": "192.168.1.20", "port": 41234},
            {"name": "adb-R58M12ABCDE-a1b2c3", "type": "_adb-tls-pairing._tcp", "kind": "pairing",
             "host": "192.168.1.20", "port": 37123},
            {"name": "AI Phone Debloater (2)", "type": "_adb-tls-pairing._tcp", "kind": "pairing",
             "host": "192.168.1.21", "port": 40001},
            {"name": "adb-R58M12ABCDE", "type": "_adb._tcp", "kind": "legacy", "host": "192.168.1.20", "port": 5555},
        ])

    def test_entries_without_ipv4_or_of_another_type_are_omitted(self):
        out = (MDNS_HEADER
               + "adb-A-1\t_adb-tls-connect._tcp\t[fe80::1]:41234\n"
               "adb-B-2\t_adb-tls-connect._tcp\t:41234\n"
               "adb-C-3\t_adb-tls-connect._tcp\t192.168.1.22:0\n"
               "adb-D-4\t_adb-tls-connect._tcp\t192.168.1.22:70000\n"
               "adb-E-5\t_adb-tls-connect._tcp\t192.168.1.22\n"
               "printer\t_ipp._tcp\t192.168.1.30:631\n"
               "* daemon started successfully\n"
               "garbage\n"
               "\n")
        self.assertEqual(bridge_server.parse_mdns_services(out), [])
        self.assertEqual(bridge_server.parse_mdns_services(""), [])

    def test_odd_port_text_is_omitted_without_an_error(self):
        out = (MDNS_HEADER
               + "adb-A-1\t_adb-tls-connect._tcp\t192.168.1.22:²\n"
               + "adb-B-2\t_adb-tls-connect._tcp\t192.168.1.22:" + "9" * 5000 + "\n"
               + "adb-C-3\t_adb-tls-connect._tcp\t192.168.1.22:41234\n")
        self.assertEqual([s["name"] for s in bridge_server.parse_mdns_services(out)], ["adb-C-3"])

    def test_space_padded_output_is_tolerated(self):
        out = MDNS_HEADER + "Galaxy S24 Ultra    _adb-tls-connect._tcp    192.168.1.105:38921\n"
        self.assertEqual(bridge_server.parse_mdns_services(out), [
            {"name": "Galaxy S24 Ultra", "type": "_adb-tls-connect._tcp", "kind": "connect",
             "host": "192.168.1.105", "port": 38921},
        ])

    def test_mdns_check_reads_the_text_not_the_exit_status(self):
        for out, expected in (("mdns daemon version [adb discovery 0.0.0]\n", True),
                              ("mdns daemon version [Openscreen discovery 0.0.0]\n", True),
                              ("mdns daemon version [8817000]\n", True),
                              ("ERROR: mdns discovery disabled\n", False),
                              ("ERROR: mdns daemon unavailable\n", False),
                              ("", False)):
            with mock.patch.object(bridge_server, "run_adb", return_value=(0, out, "")):
                self.assertIs(bridge_server.adb_mdns_available("adb"), expected, out)
        with mock.patch.object(bridge_server, "run_adb", return_value=(1, "", "adb: unknown command mdns\n")):
            self.assertFalse(bridge_server.adb_mdns_available("adb"))


class TestDeviceMonitor(unittest.TestCase):
    """The shared device list: revision, single flight, long poll."""

    def setUp(self):
        self.adb = FakeAdb()
        patcher = mock.patch.object(bridge_server, "run_adb", self.adb)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(bridge_server._STOP.clear)
        self.monitor = bridge_server.DeviceMonitor()

    def test_revision_stays_stable_and_changes_with_the_list(self):
        self.adb.devices = [
            "",                                    # 1: first reading
            "",                                    # 1: nothing changed
            NEW_PHONE,                             # 2: a phone appears
            NEW_PHONE,                             # 2
            NEW_PHONE.replace("unauthorized", "device") + " model:Pixel_8",   # 3: authorized, model known
            NEW_PHONE.replace("unauthorized", "device") + " model:Pixel_8",   # 3
            NEW_PHONE.replace("unauthorized", "device").replace("transport_id:4", "transport_id:9") + " model:Pixel_8",  # 4
            PIXEL_USB + "\n" + NEW_PHONE,          # 5: a second phone
            NEW_PHONE + "\n" + PIXEL_USB,          # 5: the same two in another order
            PIXEL_USB,                             # 6: one leaves
            "",                                    # 7
            "",                                    # 7
        ]
        revisions = [self.monitor.snapshot("adb", max_age=0.0)[1] for _ in range(12)]
        self.assertEqual(revisions, [1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 7, 7])
        self.assertEqual(self.adb.count("devices"), 12)

    def test_boot_id_is_new_for_each_monitor(self):
        other = bridge_server.DeviceMonitor()
        self.assertNotEqual(self.monitor.boot_id, other.boot_id)
        self.assertRegex(self.monitor.boot_id, r"^[0-9a-f]{16}$")

    def test_fresh_reading_is_reused(self):
        self.adb.devices = PIXEL_USB
        first = self.monitor.snapshot("adb", max_age=60.0)
        second = self.monitor.snapshot("adb", max_age=60.0)
        self.assertEqual(first, second)
        self.assertEqual(self.adb.count("devices"), 1)
        first[0][0]["state"] = "tampered"  # a caller's copy, not the shared list
        self.assertEqual(self.monitor.snapshot("adb", max_age=60.0)[0][0]["state"], "device")
        self.monitor.invalidate()
        self.monitor.snapshot("adb", max_age=60.0)
        self.assertEqual(self.adb.count("devices"), 2)

    def test_invalidate_does_not_wait_for_a_reading_in_progress(self):
        """/reconnect and /connect mark the list stale even while adb is slow to list devices."""
        self.adb.devices = PIXEL_USB
        self.monitor.snapshot("adb", max_age=60.0)
        with self.monitor._lock:  # as if a reading were in progress
            marker = threading.Thread(target=self.monitor.invalidate, daemon=True)
            marker.start()
            marker.join(5)
            self.assertFalse(marker.is_alive())
        self.monitor.snapshot("adb", max_age=60.0)
        self.assertEqual(self.adb.count("devices"), 2)

    def test_concurrent_requests_share_one_adb_call(self):
        """Eight threads asking at once start one `adb devices -l`, not eight."""
        release = threading.Event()

        def slow(_args):
            release.wait(5)
            return 0, HEADER + PIXEL_USB + "\n\n", ""

        self.adb.devices = slow
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.monitor.snapshot("adb", max_age=60.0)))
                   for _ in range(8)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 5
        while self.adb.count("devices") < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        release.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(len(results), 8)
        self.assertEqual({revision for _, revision in results}, {1})
        self.assertEqual(self.adb.count("devices"), 1)

    def test_failed_reading_is_shared_and_keeps_its_code(self):
        self.adb.devices = bridge_server.AdbTimeoutError("command timed out after 15s: adb devices -l")
        for _ in range(3):
            with self.assertRaises(bridge_server.AdbTimeoutError) as ctx:
                self.monitor.snapshot("adb", max_age=60.0)
            self.assertEqual(bridge_server.failure_code(ctx.exception), (504, "adb_timeout"))
        self.assertEqual(self.adb.count("devices"), 1)
        self.adb.devices = RuntimeError("an error without a code")
        with self.assertRaises(bridge_server.AdbError) as ctx:
            self.monitor.snapshot("adb", max_age=0.0)
        self.assertEqual(bridge_server.failure_code(ctx.exception), (502, "adb_failed"))
        self.adb.devices = PIXEL_USB  # adb works again: the list is back, as revision 1
        self.assertEqual(self.monitor.snapshot("adb", max_age=0.0)[1], 1)

    def test_long_poll_returns_early_on_change(self):
        self.adb.devices = ["", "", "", NEW_PHONE]
        with mock.patch.multiple(bridge_server, **FAST):
            revision = self.monitor.snapshot("adb")[1]
            started = time.monotonic()
            devices, new_revision = self.monitor.wait_for_change("adb", revision, wait=30.0)
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(new_revision, revision + 1)
        self.assertEqual([d["state"] for d in devices], ["unauthorized"])
        self.assertEqual(self.adb.count("devices"), 4)  # read once per poll, until the change

    def test_long_poll_returns_after_wait_when_unchanged(self):
        self.adb.devices = PIXEL_USB
        with mock.patch.multiple(bridge_server, **FAST):
            revision = self.monitor.snapshot("adb")[1]
            started = time.monotonic()
            devices, same = self.monitor.wait_for_change("adb", revision, wait=0.3)
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.25)
        self.assertLess(elapsed, 10)
        self.assertEqual(same, revision)
        self.assertEqual([d["serial"] for d in devices], ["R58M12ABCDE"])
        self.assertGreater(self.adb.count("devices"), 2)

    def test_long_poll_with_an_old_revision_returns_at_once(self):
        self.adb.devices = PIXEL_USB
        revision = self.monitor.snapshot("adb", max_age=0.0)[1]
        started = time.monotonic()
        self.assertEqual(self.monitor.wait_for_change("adb", revision - 1, wait=30.0)[1], revision)
        self.assertLess(time.monotonic() - started, 10)

    def test_long_poll_ends_when_the_client_is_gone_or_the_bridge_stops(self):
        self.adb.devices = PIXEL_USB
        with mock.patch.multiple(bridge_server, **FAST):
            revision = self.monitor.snapshot("adb")[1]
            started = time.monotonic()
            self.assertEqual(self.monitor.wait_for_change("adb", revision, 30.0, gone=lambda: True)[1], revision)
            bridge_server._STOP.set()
            self.assertEqual(self.monitor.wait_for_change("adb", revision, 30.0)[1], revision)
        self.assertLess(time.monotonic() - started, 10)

    def test_long_poll_does_not_hold_the_lock_while_it_sleeps(self):
        """Another request gets its answer while a long poll is waiting."""
        self.adb.devices = PIXEL_USB
        with mock.patch.multiple(bridge_server, DEVICES_FRESH_FOR=0.0, DEVICES_POLL_INTERVAL=5.0):
            revision = self.monitor.snapshot("adb")[1]
            poll = threading.Thread(target=self.monitor.wait_for_change, args=("adb", revision, 30.0), daemon=True)
            poll.start()
            deadline = time.monotonic() + 5
            while self.adb.count("devices") < 2 and time.monotonic() < deadline:
                time.sleep(0.005)  # the poll has read the list and now sleeps for 5 s
            started = time.monotonic()
            self.assertEqual(self.monitor.snapshot("adb")[1], revision)
            self.assertLess(time.monotonic() - started, 2)
            bridge_server._STOP.set()  # wakes the poll
            poll.join(5)
        self.assertFalse(poll.is_alive())


class TestBridgeHttpEndpoints(unittest.TestCase):
    """Test HTTP request routing, CORS, and endpoint responses."""

    def setUp(self):
        # No test may start a real adb: every adb call of the bridge goes to this fake
        # unless the test patches run_adb itself. The device list starts fresh each time.
        self.adb = FakeAdb()
        for patcher in (mock.patch.object(bridge_server, "run_adb", self.adb),
                        mock.patch.object(bridge_server, "_MONITOR", bridge_server.DeviceMonitor()),
                        mock.patch.multiple(bridge_server, **FAST)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.server = bridge_server.ThreadingHTTPServer(("127.0.0.1", 0), bridge_server.BridgeHandler)
        self.port = self.server.server_address[1]
        # A short poll interval: shutdown() in tearDown returns within one interval.
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01},
                                       daemon=True)
        self.thread.start()
        self.auth = {bridge_server.TOKEN_HEADER: bridge_server.BRIDGE_TOKEN}

    def tearDown(self):
        bridge_server.cancel_pairing()
        bridge_server._PAIR.update(bridge_server._PAIR_IDLE)
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
                         {"state": "idle", "id": None, "serial": None, "error": None,
                          "connected": False, "needs_connect_port": False, "host": None})

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

    # -- error codes ---------------------------------------------------------

    def test_error_codes_of_gate_token_and_routing(self):
        """Each rejection keeps its text and status and adds the code the web app branches on."""
        cases = (
            (self._get("/devices", headers={**self.auth, "Host": "evil.example"}), 403, "forbidden_host"),
            (self._get("/devices", headers={**self.auth, "Origin": "https://evil.example"}), 403, "origin_not_allowed"),
            (self._post("/connect", CONNECT_BODY, content_type="text/plain"), 415, "unsupported_media_type"),
            (self._get("/devices", headers={}), 401, "token_required"),
            (self._post("/pair/code", PAIR_BODY, headers={bridge_server.TOKEN_HEADER: "wrong"}), 401, "token_required"),
            (self._get("/nope"), 404, "not_found"),
            (self._post("/nope", {}), 404, "not_found"),
            (self._post("/execute", ["not", "an", "object"]), 400, "bad_request"),
            (self._post("/reconnect", None), 400, "bad_request"),
            (self._get("/packages"), 400, "bad_request"),
            (self._get("/device"), 400, "bad_request"),
            (self._post("/execute", {"serial": "s", "mode": "nope", "action": "disable", "packages": []}),
             400, "bad_request"),
            (self._post("/restore", {"serial": "", "packages": []}), 400, "bad_request"),
        )
        for (status, data), want_status, want_code in cases:
            self.assertEqual((status, data.get("code")), (want_status, want_code))
            self.assertIs(data["success"], False)
            self.assertTrue(data["error"])
        self.assertEqual(self.adb.calls, [])

    def test_error_codes_of_adb_failures(self):
        """A missing adb, a timeout and a failed command are told apart, on every adb route."""
        cases = ((bridge_server.AdbNotFoundError("adb executable not found: x"), 502, "adb_not_found"),
                 (bridge_server.AdbTimeoutError("command timed out after 15s: adb devices -l"), 504, "adb_timeout"),
                 ((1, "", "error: cannot connect to daemon\n"), 502, "adb_failed"),
                 ((0, "garbage, no header\n", ""), 502, "adb_failed"))
        for answer, want_status, want_code in cases:
            self.adb.devices = answer
            status, data = self._get("/devices")
            self.assertEqual((status, data["code"], data["success"]), (want_status, want_code, False))
            self.assertNotIn("devices", data)
        for answer, want_status, want_code in cases[:3]:
            with mock.patch.object(bridge_server, "run_adb",
                                   side_effect=answer if isinstance(answer, Exception) else None,
                                   return_value=answer):
                for path in ("/packages?serial=x", "/packages?serial=x&view=disabled", "/mdns"):
                    status, data = self._get(path)
                    if path == "/mdns" and not isinstance(answer, Exception):
                        continue  # a failing `adb mdns check` only means "not available"
                    self.assertEqual((status, data["code"]), (want_status, want_code), path)
                status, data = self._post("/reconnect", {})
                self.assertEqual((status, data["code"]), (want_status, want_code))

    def test_error_responses_carry_cors_headers(self):
        """The web app can read the code of an error: CORS headers are on error answers too."""
        origin = "https://debloater.rovoxia.com"
        self.adb.devices = bridge_server.AdbNotFoundError("adb executable not found: x")
        for req in (
            urllib.request.Request(f"http://127.0.0.1:{self.port}/devices", headers={"Origin": origin, **self.auth}),
            urllib.request.Request(f"http://127.0.0.1:{self.port}/pair/code", data=b"{}",
                                   headers={"Origin": origin, "Content-Type": "application/json", **self.auth}),
            urllib.request.Request(f"http://127.0.0.1:{self.port}/nope", headers={"Origin": origin, **self.auth}),
        ):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.headers.get("Access-Control-Allow-Origin"), origin)
            self.assertIn("code", json.loads(ctx.exception.read()))

    def test_snapshot_failure_keeps_status_500_and_has_a_code(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(bridge_server, "BACKUPS_DIR", Path(tmp)), \
                mock.patch.object(bridge_server, "run_adb",
                                  side_effect=bridge_server.AdbTimeoutError("command timed out")):
            status, data = self._post("/execute", {"serial": "test-device", "mode": "apply",
                                                   "action": "disable", "packages": ["com.example.app"]})
        self.assertEqual((status, data["code"]), (500, "adb_timeout"))
        self.assertIn("snapshot failed", data["error"])

    def test_new_routes_need_token(self):
        """The new routes answer 401 without the token and start no adb command."""
        self.assertEqual(self._get("/mdns", headers={})[0], 401)
        self.assertEqual(self._get("/devices?since=1&boot=x&wait=20", headers={})[0], 401)
        for path, body in (("/reconnect", {}), ("/pair/code", PAIR_BODY), ("/connect", CONNECT_BODY)):
            status, data = self._post(path, body, headers={})
            self.assertEqual((status, data["code"]), (401, "token_required"), path)
        self.assertEqual(self.adb.calls, [])

    def test_preflight_for_new_post_routes(self):
        origin = "https://debloater.rovoxia.com"
        for path in ("/reconnect", "/pair/code", "/connect", "/api/connect"):
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="OPTIONS",
                                         headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 204)
                self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), origin)
                self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods", ""))
                allowed = resp.headers.get("Access-Control-Allow-Headers", "")
                self.assertIn("Content-Type", allowed)
                self.assertIn(bridge_server.TOKEN_HEADER, allowed)

    # -- /health, /devices -----------------------------------------------------

    def test_health_reports_api_level_and_capabilities(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health") as resp:
            data = json.loads(resp.read())
        self.assertEqual(data["api"], 2)
        self.assertEqual(data["capabilities"],
                         ["devices.wait", "pair.code", "connect", "reconnect", "mdns", "pair.qr"])
        self.assertEqual((data["status"], data["token_required"], data["adb_available"]), ("ok", True, True))

    def test_health_does_not_wait_for_the_adb_warm_up(self):
        """While the background start-server runs, /health still answers at once."""
        bridge_server._ADB_READY.clear()
        self.addCleanup(bridge_server._ADB_READY.set)
        started = time.monotonic()
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health") as resp:
            self.assertEqual(resp.status, 200)
        self.assertLess(time.monotonic() - started, 10)
        with mock.patch.object(bridge_server, "ADB_WARMUP_TIMEOUT", -4.9):  # the other routes wait: 0.1 s here
            self.assertEqual(self._get("/devices")[0], 200)

    def test_adb_route_is_held_until_the_warm_up_ends(self):
        """A request that needs adb waits for the background start-server; one that does not, answers."""
        bridge_server._ADB_READY.clear()
        self.addCleanup(bridge_server._ADB_READY.set)
        answers = []
        request = threading.Thread(target=lambda: answers.append(self._get("/devices")), daemon=True)
        request.start()
        request.join(0.3)
        self.assertTrue(request.is_alive())   # held ...
        self.assertEqual(self.adb.calls, [])  # ... before any adb command
        self.assertEqual(self._get("/pair/status")[0], 200)
        self.assertEqual(self._post("/pair/cancel", {})[0], 200)
        self.assertEqual(self._get("/nope")[0], 404)
        self.assertTrue(request.is_alive())
        self.assertFalse(bridge_server._ADB_READY.is_set())
        bridge_server._ADB_READY.set()  # the warm-up ends
        request.join(10)
        self.assertFalse(request.is_alive())
        self.assertEqual(answers[0][0], 200)
        self.assertEqual(self.adb.calls, [["devices", "-l"]])

    def test_warm_up_wait_latches_after_one_timeout(self):
        """If the warm-up never reports back, one request waits out the limit and no later one does."""
        bridge_server._ADB_READY.clear()
        self.addCleanup(bridge_server._ADB_READY.set)
        with mock.patch.object(bridge_server, "ADB_WARMUP_TIMEOUT", -4.9):  # the wait is this plus 5 s: 0.1 s
            started = time.monotonic()
            self.assertEqual(self._get("/devices")[0], 200)
            self.assertGreaterEqual(time.monotonic() - started, 0.08)
        self.assertTrue(bridge_server._ADB_READY.is_set())
        started = time.monotonic()  # with the real limit of 35 s: answered at once, the flag is set
        self.assertEqual(self._get("/mdns")[0], 200)
        self.assertLess(time.monotonic() - started, 10)

    def test_only_requests_that_run_adb_wait_for_the_warm_up(self):
        """Each adb route waits once, after validation and before its first adb command; other answers never wait."""
        waits = []  # how many adb commands had run when the wait was made

        def apply_body(mode):
            return {"serial": "s", "mode": mode, "action": "disable", "packages": ["com.example.app"]}

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(bridge_server, "BACKUPS_DIR", Path(tmp)), \
                mock.patch.object(bridge_server, "wait_for_adb", lambda: waits.append(len(self.adb.calls))):
            for run_adb_route in (
                lambda: self._get("/devices"),
                lambda: self._get("/devices?since=1&boot=x&wait=5"),
                lambda: self._get("/packages?serial=s"),
                lambda: self._get("/packages?serial=s&view=disabled"),
                lambda: self._get("/device?serial=s"),
                lambda: self._get("/mdns"),
                lambda: self._post("/reconnect", {}),
                lambda: self._post("/pair/code", PAIR_BODY),
                lambda: self._post("/connect", CONNECT_BODY),
                lambda: self._post("/restore", {"serial": "s", "packages": ["com.example.app"]}),
                lambda: self._post("/execute", apply_body("apply")),
            ):
                self.adb.calls.clear()
                waits.clear()
                status = run_adb_route()[0]
                self.assertEqual(waits, [0], status)
                self.assertTrue(self.adb.calls)

            self.adb.calls.clear()
            waits.clear()
            self.assertEqual(self._start_pairing()[1], 200)  # its thread runs adb at once
            self.assertEqual(waits, [0])

            self.adb.calls.clear()
            waits.clear()
            self.assertTrue(bridge_server._WIRELESS_LOCK.acquire(blocking=False))
            try:
                busy_connect = self._post("/connect", CONNECT_BODY)[0]
            finally:
                bridge_server._WIRELESS_LOCK.release()
            answers = [
                busy_connect,                                              # 409
                self._start_pairing()[1],                                  # 409: a session is running
                self._get("/pair/status")[0],
                self._post("/pair/cancel", {})[0],
                self._send(urllib.request.Request(f"http://127.0.0.1:{self.port}/health"))[0],
                self._get("/nope")[0],
                self._post("/nope", {})[0],
                self._get("/packages")[0],                                 # 400s: refused before adb
                self._get("/device")[0],
                self._post("/pair/code", {**PAIR_BODY, "host": "phone.local"})[0],
                self._post("/pair/code", {**PAIR_BODY, "code": "12345"})[0],
                self._post("/connect", {**CONNECT_BODY, "port": 0})[0],
                self._post("/execute", apply_body("nope"))[0],
                self._post("/restore", {"serial": "", "packages": []})[0],
                self._post("/restore", {"serial": "s", "packages": ["not a package"]})[0],  # nothing to run
                self._post("/execute", apply_body("dry-run"))[0],
                self._get("/devices", headers={})[0],                      # 401
            ]
            self.assertEqual(answers, [409, 409, 200, 200, 200, 404, 404, 400, 400, 400, 400, 400, 400, 400,
                                       200, 200, 401])
            self.assertEqual(waits, [])
            self.assertEqual(self.adb.count("devices") + self.adb.count("shell"), 0)

    def test_device_list_is_read_again_after_commands_that_change_it(self):
        """After /reconnect, a pairing or connect request and a QR outcome, /devices is no cached answer."""

        def qr_outcome():
            fake, _, _ = self._start_pairing()
            fake.finish(SimpleNamespace(serial="192.168.1.5:5555"))
            self._pair_state("paired")

        self.adb.devices = PIXEL_USB
        self.adb.answers["connect"] = (0, "failed to connect to 192.168.1.20:41234\n", "")
        self.adb.answers["pair"] = (1, "", "error: protocol fault (couldn't read status message): No error\n")
        with mock.patch.object(bridge_server, "DEVICES_FRESH_FOR", 60.0):
            self._get("/devices")
            self._get("/devices")
            self.assertEqual(self.adb.count("devices"), 1)  # within the minute, the reading is reused
            for change in (lambda: self._post("/reconnect", {}),
                           lambda: self._post("/connect", CONNECT_BODY),
                           lambda: self._post("/pair/code", PAIR_BODY),
                           qr_outcome):
                change()
                before = self.adb.count("devices")
                self._get("/devices")
                self.assertEqual(self.adb.count("devices"), before + 1)
                self._get("/devices")
                self.assertEqual(self.adb.count("devices"), before + 1)  # and reused again after that

    def test_devices_shape(self):
        self.adb.devices = f"{PIXEL_USB}\n{NEW_PHONE}\n{PIXEL_WIFI}"
        for path in ("/devices", "/api/devices"):
            status, data = self._get(path)
            self.assertEqual(status, 200)
            self.assertEqual(sorted(data), ["boot_id", "devices", "revision"])
            self.assertEqual(data["devices"][0], {
                "serial": "R58M12ABCDE", "state": "device", "raw_state": "device", "detail": "",
                "model": "Pixel_8", "product": "shiba", "device": "shiba", "transport_id": "3",
                "transport": "usb",
            })
            self.assertEqual([(d["serial"], d["state"], d["transport"]) for d in data["devices"][1:]],
                             [("0123456789ABCDEF", "unauthorized", "usb"), ("192.168.1.20:41234", "device", "wifi")])
            self.assertEqual((data["revision"], data["boot_id"]), (1, bridge_server._MONITOR.boot_id))

    def test_devices_revision_over_http(self):
        self.adb.devices = ["", "", NEW_PHONE, NEW_PHONE.replace("unauthorized", "device")]
        revisions = [self._get("/devices")[1]["revision"] for _ in range(5)]
        self.assertEqual(revisions, [1, 1, 2, 3, 3])

    def _poll(self, query):
        """GET /devices with a query; returns (seconds it took, body)."""
        started = time.monotonic()
        status, data = self._get(f"/devices?{query}")
        self.assertEqual(status, 200)
        return time.monotonic() - started, data

    def test_long_poll_returns_early_on_change(self):
        """A held request answers as soon as a phone appears, well before its wait is over."""
        self.adb.devices = ["", "", "", "", NEW_PHONE]
        first = self._get("/devices")[1]
        took, data = self._poll(f"since={first['revision']}&boot={first['boot_id']}&wait=25")
        self.assertLess(took, 10)
        self.assertEqual(data["revision"], first["revision"] + 1)
        self.assertEqual(data["boot_id"], first["boot_id"])
        self.assertEqual([d["state"] for d in data["devices"]], ["unauthorized"])
        self.assertEqual(self.adb.count("devices"), 5)

    def test_long_poll_returns_after_wait_when_unchanged(self):
        self.adb.devices = PIXEL_USB
        first = self._get("/devices")[1]
        took, data = self._poll(f"since={first['revision']}&boot={first['boot_id']}&wait=0.3")
        self.assertGreaterEqual(took, 0.25)
        self.assertLess(took, 10)
        self.assertEqual((data["revision"], data["boot_id"]), (first["revision"], first["boot_id"]))
        self.assertEqual(len(data["devices"]), 1)
        self.assertGreater(self.adb.count("devices"), 3)

    def test_long_poll_answers_immediately_when_boot_or_since_differ(self):
        """A revision from another bridge process, an old revision or no wait: no holding."""
        self.adb.devices = PIXEL_USB
        first = self._get("/devices")[1]
        rev, boot = first["revision"], first["boot_id"]
        for query in (f"since={rev}&boot=0000000000000000&wait=25",   # another bridge process
                      f"since={rev}&wait=25",                         # no boot id
                      f"since={rev - 1}&boot={boot}&wait=25",         # the list changed meanwhile
                      f"since={rev + 5}&boot={boot}&wait=25",
                      f"boot={boot}&wait=25",                         # no revision
                      f"since=abc&boot={boot}&wait=25",
                      f"since={rev}&boot={boot}",                     # no wait
                      f"since={rev}&boot={boot}&wait=0",
                      f"since={rev}&boot={boot}&wait=-5",
                      f"since={rev}&boot={boot}&wait=soon",
                      f"since={rev}&boot={boot}&wait=nan"):
            before = self.adb.count("devices")
            took, data = self._poll(query)
            self.assertLess(took, 10, query)
            self.assertEqual(self.adb.count("devices") - before, 1, query)  # one reading, no polling
            self.assertEqual((data["revision"], data["boot_id"]), (rev, boot), query)

    def test_long_poll_wait_is_clamped(self):
        """wait above 25 s is cut to 25 s."""
        self.adb.devices = PIXEL_USB
        first = self._get("/devices")[1]
        waits = []
        real = bridge_server.DeviceMonitor.wait_for_change

        def spy(monitor, adb_path, since, wait, gone=lambda: False):
            waits.append(wait)
            return real(monitor, adb_path, since, 0.0, gone)

        with mock.patch.object(bridge_server.DeviceMonitor, "wait_for_change", spy):
            for wait in ("999", "25.5", "inf", "1e400", "25", "3.5"):
                self._poll(f"since={first['revision']}&boot={first['boot_id']}&wait={wait}")
        self.assertEqual(waits, [25.0, 25.0, 25.0, 25.0, 25.0, 3.5])

    def test_long_poll_client_disconnect_ends_quietly(self):
        """A client that hangs up during a held request ends the polling, without a traceback."""
        self.adb.devices = PIXEL_USB
        first = self._get("/devices")[1]
        finished = threading.Event()
        real = bridge_server.BridgeHandler._handle_devices

        def tracked(handler, adb_path, params):
            try:
                real(handler, adb_path, params)
            finally:
                finished.set()

        with mock.patch.object(bridge_server.BridgeHandler, "_handle_devices", tracked), \
                mock.patch.object(self.server, "handle_error") as handle_error:
            before = self.adb.count("devices")
            sock = socket.create_connection(("127.0.0.1", self.port))
            sock.sendall((f"GET /devices?since={first['revision']}&boot={first['boot_id']}&wait=25 HTTP/1.1\r\n"
                          f"Host: 127.0.0.1:{self.port}\r\n"
                          f"{bridge_server.TOKEN_HEADER}: {bridge_server.BRIDGE_TOKEN}\r\n\r\n").encode("ascii"))
            deadline = time.monotonic() + 5
            while self.adb.count("devices") < before + 3 and time.monotonic() < deadline:
                time.sleep(0.005)  # the request is being held and polls
            self.assertFalse(finished.is_set())
            started = time.monotonic()
            sock.close()
            self.assertTrue(finished.wait(10))
            self.assertLess(time.monotonic() - started, 10)
            time.sleep(0.05)  # let the request thread leave the handler
            handle_error.assert_not_called()

    def test_devices_stays_usable_after_an_adb_failure(self):
        self.adb.devices = [bridge_server.AdbTimeoutError("command timed out"), PIXEL_USB]
        self.assertEqual(self._get("/devices")[0], 504)
        status, data = self._get("/devices")
        self.assertEqual((status, data["revision"], len(data["devices"])), (200, 1, 1))

    # -- /reconnect, /mdns -----------------------------------------------------

    def test_reconnect(self):
        """POST /reconnect runs `adb reconnect offline` and nothing that restarts the server."""
        self.adb.answers["reconnect"] = (0, "reconnecting 0123456789ABCDEF\n", "")
        for path in ("/reconnect", "/api/reconnect"):
            self.assertEqual(self._post(path, {}), (200, {"success": True}))
        self.assertEqual(self.adb.calls, [["reconnect", "offline"]] * 2)
        self.adb.answers["reconnect"] = (1, "", "error: cannot connect to daemon\n")
        status, data = self._post("/reconnect", {})
        self.assertEqual((status, data["code"], data["success"]), (502, "adb_failed", False))
        self.assertIn("cannot connect to daemon", data["error"])

    def test_mdns_available(self):
        self.adb.answers["mdns check"] = MDNS_UP
        self.adb.answers["mdns services"] = (0, MDNS_HEADER
                                             + "adb-R58M12ABCDE-a1b2c3\t_adb-tls-connect._tcp\t192.168.1.20:41234\n"
                                             "adb-R58M12ABCDE-a1b2c3\t_adb-tls-pairing._tcp\t192.168.1.20:37123\n"
                                             "adb-OLD\t_adb._tcp\t192.168.1.30:5555\n"
                                             "adb-V6ONLY-zzzzzz\t_adb-tls-connect._tcp\t[fe80::1]:40000\n", "")
        for path in ("/mdns", "/api/mdns"):
            status, data = self._get(path)
            self.assertEqual(status, 200)
            self.assertEqual(data, {"available": True, "services": [
                {"name": "adb-R58M12ABCDE-a1b2c3", "type": "_adb-tls-connect._tcp", "kind": "connect",
                 "host": "192.168.1.20", "port": 41234},
                {"name": "adb-R58M12ABCDE-a1b2c3", "type": "_adb-tls-pairing._tcp", "kind": "pairing",
                 "host": "192.168.1.20", "port": 37123},
                {"name": "adb-OLD", "type": "_adb._tcp", "kind": "legacy", "host": "192.168.1.30", "port": 5555},
            ]})

    def test_mdns_unavailable(self):
        """No mDNS daemon is not an error: 200, available false, no services, and no services query."""
        for answer in (MDNS_OFF, (0, "ERROR: mdns daemon unavailable\n", ""), (1, "", "adb: unknown command mdns\n")):
            self.adb.answers["mdns check"] = answer
            status, data = self._get("/mdns")
            self.assertEqual(status, 200)
            self.assertEqual((data["available"], data["services"]), (False, []))
            self.assertEqual(data.get("code"), "mdns_unavailable")
        self.assertEqual(self.adb.count("mdns", "services"), 0)
        self.adb.answers["mdns check"] = MDNS_UP
        self.adb.answers["mdns services"] = (1, "", "error: closed\n")
        status, data = self._get("/mdns")
        self.assertEqual((status, data["code"]), (502, "adb_failed"))

    # -- /pair/code ------------------------------------------------------------

    def test_pair_code_validation(self):
        """Only an IPv4 address, an integer port and six digits ever reach the adb command line."""
        bad_bodies = [{}, {"host": "192.168.1.20"}, {"host": "192.168.1.20", "port": 37123}]
        bad_bodies += [{**PAIR_BODY, "host": host} for host in (
            "", "phone.local", "localhost", "0.0.0.0", "255.255.255.255", "224.0.0.251", "::1", "192.168.1",
            "192.168.1.20 ", "192.168.1.20:37123", "-s", "--help", "192.168.1.20;reboot", 3232235796, None,
            ["192.168.1.20"])]
        bad_bodies += [{**PAIR_BODY, "port": port} for port in (0, -1, 65536, "37123", 37123.5, True, None, [1])]
        bad_bodies += [{**PAIR_BODY, "code": code} for code in (
            "", "12345", "1234567", "12345a", "123 456", "123456\n", " 123456", "-12345", "--help", 123456,
            None, ["123456"], "١٢٣٤٥٦")]
        for body in bad_bodies:
            status, data = self._post("/pair/code", body)
            self.assertEqual((status, data.get("code"), data.get("success")), (400, "bad_request", False), body)
            self.assertNotIn("123456", data["error"])
        self.assertEqual(self.adb.calls, [])

    def test_pair_code_connected_by_adb_itself(self):
        """adb connects the phone it has just paired and lists it under its mDNS name: use that serial."""
        self.adb.answers.update({"pair": PAIRED, "mdns check": MDNS_UP})
        self.adb.answers["mdns services"] = (
            0, MDNS_HEADER + "adb-R58M12ABCDE-a1b2c3\t_adb-tls-connect._tcp\t192.168.1.20:41234\n", "")
        self.adb.devices = PIXEL_USB.replace("R58M12ABCDE ", "OTHERPHONE  ") + "\n" + PIXEL_MDNS
        with mock.patch.object(bridge_server, "_log") as log:
            status, data = self._post("/pair/code", PAIR_BODY)
        self.assertEqual(status, 200)
        self.assertEqual(data, {
            "success": True, "paired": True, "guid": "adb-R58M12ABCDE-a1b2c3", "connected": True,
            "serial": "adb-R58M12ABCDE-a1b2c3._adb-tls-connect._tcp", "needs_connect_port": False,
            "host": "192.168.1.20",
        })
        self.assertEqual(self.adb.calls[0], ["pair", "192.168.1.20:37123", "123456"])
        self.assertEqual(self.adb.count("connect"), 0)
        self.assertNotIn("123456", str(log.call_args_list))  # the code is never logged

    def test_pair_code_connects_to_announced_port(self):
        """Not connected by adb itself: the bridge uses the phone's mDNS connect service, not the pairing port."""
        self.adb.answers.update({"pair": (0, "Successfully paired to 192.168.1.20:37123\n", ""),
                                 "mdns check": MDNS_UP})
        self.adb.answers["mdns services"] = (
            0, MDNS_HEADER
            + "adb-OTHER-zzzzzz\t_adb-tls-connect._tcp\t192.168.1.99:40000\n"
            "adb-R58M12ABCDE-a1b2c3\t_adb-tls-pairing._tcp\t192.168.1.20:37123\n"
            "adb-R58M12ABCDE-a1b2c3\t_adb-tls-connect._tcp\t192.168.1.20:37123\n"
            "adb-R58M12ABCDE\t_adb._tcp\t192.168.1.20:5555\n"
            "adb-R58M12ABCDE-a1b2c3\t_adb-tls-connect._tcp\t192.168.1.20:41234\n", "")

        def connect(args):
            self.adb.devices = PIXEL_WIFI
            return 0, f"connected to {args[1]}\n", ""

        self.adb.answers["connect"] = connect
        status, data = self._post("/pair/code", PAIR_BODY)
        self.assertEqual(status, 200)
        self.assertEqual(data, {
            "success": True, "paired": True, "guid": None, "connected": True,
            "serial": "192.168.1.20:41234", "needs_connect_port": False, "host": "192.168.1.20",
        })
        self.assertEqual([c for c in self.adb.calls if c[0] == "connect"], [["connect", "192.168.1.20:41234"]])
        self.assertEqual(self._get("/devices")[1]["devices"][0]["serial"], "192.168.1.20:41234")

    def test_pair_code_waits_for_adbs_own_connection(self):
        """Listed under its mDNS name but not ready: adb is connecting, so no second transport is opened."""
        mdns_serial = "adb-R58M12ABCDE-a1b2c3._adb-tls-connect._tcp"
        offline = f"{mdns_serial} offline transport_id:7"
        self.adb.answers["mdns services"] = (
            0, MDNS_HEADER + "adb-R58M12ABCDE-a1b2c3\t_adb-tls-connect._tcp\t192.168.1.20:41234\n", "")
        no_guid = (0, "Successfully paired to 192.168.1.20:37123\n", "")
        cases = ((PAIRED, MDNS_UP, "adb-R58M12ABCDE-a1b2c3"),   # recognised by the guid from adb pair
                 (no_guid, MDNS_UP, None),                      # recognised by the mDNS service name
                 (PAIRED, MDNS_OFF, "adb-R58M12ABCDE-a1b2c3"))  # listed although `mdns check` says no
        # The grace period is 0 here, so a manual connect would run at once if nothing held it back.
        with mock.patch.object(bridge_server, "PAIR_CONNECT_WAIT", 30.0):  # ends on "device", long before
            for paired, mdns, guid in cases:
                self.adb.calls.clear()
                self.adb.answers.update({"pair": paired, "mdns check": mdns})
                self.adb.devices = [offline, offline.replace(" offline ", " authorizing "), PIXEL_MDNS]
                status, data = self._post("/pair/code", PAIR_BODY)
                self.assertEqual(status, 200)
                self.assertEqual(data, {
                    "success": True, "paired": True, "guid": guid, "connected": True, "serial": mdns_serial,
                    "needs_connect_port": False, "host": "192.168.1.20",
                })
                self.assertEqual(self.adb.count("connect"), 0)
                self.assertEqual(self.adb.count("devices"), 3)  # offline, authorizing, device

    def test_pair_code_adbs_own_connection_never_ready(self):
        """The mDNS-named entry never reaches "device": still no manual connect, and the port is asked for."""
        self.adb.answers.update({"pair": PAIRED, "mdns check": MDNS_UP})
        self.adb.answers["mdns services"] = (
            0, MDNS_HEADER + "adb-R58M12ABCDE-a1b2c3\t_adb-tls-connect._tcp\t192.168.1.20:41234\n", "")
        for state in ("offline", "connecting", "authorizing", "unauthorized"):
            self.adb.calls.clear()
            self.adb.devices = f"adb-R58M12ABCDE-a1b2c3._adb-tls-connect._tcp {state} transport_id:7"
            self.assertEqual(self._post("/pair/code", PAIR_BODY), (200, {
                "success": True, "paired": True, "guid": "adb-R58M12ABCDE-a1b2c3", "connected": False,
                "serial": None, "needs_connect_port": True, "host": "192.168.1.20",
            }), state)
            self.assertEqual(self.adb.count("connect"), 0, state)
            self.assertGreater(self.adb.count("devices"), 1, state)  # it kept looking until the wait ran out

    def test_pair_code_unready_address_entry_does_not_hold_back_the_connect(self):
        """Only the mDNS name means adb is connecting by itself; an ip:port entry counts when ready, no more."""
        self.adb.answers.update({"pair": PAIRED, "mdns check": MDNS_UP})
        self.adb.answers["mdns services"] = (
            0, MDNS_HEADER + "adb-R58M12ABCDE-a1b2c3\t_adb-tls-connect._tcp\t192.168.1.20:41234\n", "")
        self.adb.devices = "192.168.1.20:40000     offline transport_id:5"  # an earlier port of this phone

        def connect(args):
            self.adb.devices = PIXEL_WIFI
            return 0, f"connected to {args[1]}\n", ""

        self.adb.answers["connect"] = connect
        status, data = self._post("/pair/code", PAIR_BODY)
        self.assertEqual((status, data["connected"], data["serial"]), (200, True, "192.168.1.20:41234"))
        self.assertEqual([c for c in self.adb.calls if c[0] == "connect"], [["connect", "192.168.1.20:41234"]])

    def test_pair_code_gives_adb_its_head_start(self):
        """Inside the grace period the bridge runs no adb connect of its own, even to an announced port."""
        self.adb.answers.update({"pair": PAIRED, "mdns check": MDNS_UP})
        self.adb.answers["mdns services"] = (
            0, MDNS_HEADER + "adb-R58M12ABCDE-a1b2c3\t_adb-tls-connect._tcp\t192.168.1.20:41234\n", "")
        with mock.patch.object(bridge_server, "PAIR_AUTOCONNECT_GRACE", 60.0):
            status, data = self._post("/pair/code", PAIR_BODY)
        self.assertEqual((status, data["paired"], data["connected"], data["needs_connect_port"]),
                         (200, True, False, True))
        self.assertEqual(self.adb.count("connect"), 0)
        self.assertGreater(self.adb.count("mdns", "services"), 1)  # it kept looking for the whole wait

    def test_pair_code_announced_port_without_an_answer(self):
        """A connect that gets no answer in time means "look again", and never past the overall wait."""
        want = {"success": True, "paired": True, "guid": "adb-R58M12ABCDE-a1b2c3", "connected": False,
                "serial": None, "needs_connect_port": True, "host": "192.168.1.20"}
        self.adb.answers.update({"pair": PAIRED, "mdns check": MDNS_UP})
        self.adb.answers["mdns services"] = (
            0, MDNS_HEADER + "adb-R58M12ABCDE-a1b2c3\t_adb-tls-connect._tcp\t192.168.1.20:41234\n"
            "adb-R58M12ABCDE-a1b2c3 (2)\t_adb-tls-connect._tcp\t192.168.1.20:41235\n", "")
        no_answer = bridge_server.AdbTimeoutError("command timed out after 12s: adb connect")
        tried = []

        def connect(args):  # two attempts get no answer, the third one connects
            tried.append(args[1])
            if len(tried) < 3:
                raise no_answer
            self.adb.devices = PIXEL_WIFI
            return 0, f"connected to {args[1]}\n", ""

        self.adb.answers["connect"] = connect
        with mock.patch.object(bridge_server, "PAIR_CONNECT_WAIT", 30.0):  # ends on the connection
            status, data = self._post("/pair/code", PAIR_BODY)
        self.assertEqual((status, data["connected"], data["serial"]), (200, True, "192.168.1.20:41234"))
        self.assertEqual(tried, ["192.168.1.20:41234", "192.168.1.20:41235", "192.168.1.20:41234"])

        # With the overall wait used up by the first attempt, the second port is not tried any more.
        self.adb.calls.clear()
        self.adb.devices = ""
        self.adb.answers["connect"] = no_answer
        with mock.patch.object(bridge_server, "PAIR_CONNECT_WAIT", 0.0):
            self.assertEqual(self._post("/pair/code", PAIR_BODY), (200, want))
        self.assertEqual([call for call in self.adb.calls if call[0] == "connect"],
                         [["connect", "192.168.1.20:41234"]])

    def test_pair_code_survives_serials_with_odd_port_text(self):
        """A listed "ip:port" whose port is no number ("²" passes str.isdigit) must not kill the request."""
        self.adb.answers.update({"pair": PAIRED, "mdns check": MDNS_OFF})
        self.adb.devices = ("192.168.1.20:²        device transport_id:9\n"
                            "192.168.1.20:99999999 device transport_id:10\n"
                            f"192.168.1.20:{'9' * 5000} device transport_id:11")
        status, data = self._post("/pair/code", PAIR_BODY)
        self.assertEqual((status, data["paired"], data["connected"], data["needs_connect_port"]),
                         (200, True, False, True))
        self.assertFalse(bridge_server._WIRELESS_LOCK.locked())

    def test_pair_code_paired_but_not_connected(self):
        """Paired without a connection is still a success: the page then asks for the connect port."""
        want = {"success": True, "paired": True, "guid": "adb-R58M12ABCDE-a1b2c3", "connected": False,
                "serial": None, "needs_connect_port": True, "host": "192.168.1.20"}
        self.adb.answers.update({"pair": PAIRED, "mdns check": MDNS_OFF})
        self.adb.devices = PIXEL_USB  # another phone, on a cable
        self.assertEqual(self._post("/pair/code", PAIR_BODY), (200, want))
        self.assertEqual(self.adb.count("mdns", "services") + self.adb.count("connect"), 0)

        # mDNS runs, but this phone's connect port is never announced: a short wait, then the same answer.
        self.adb.answers["mdns check"] = MDNS_UP
        self.adb.answers["mdns services"] = (
            0, MDNS_HEADER + "adb-R58M12ABCDE-a1b2c3\t_adb-tls-pairing._tcp\t192.168.1.20:37123\n"
            "adb-OTHER-zzzzzz\t_adb-tls-connect._tcp\t192.168.1.99:40000\n", "")
        self.assertEqual(self._post("/pair/code", PAIR_BODY), (200, want))
        self.assertEqual(self.adb.count("connect"), 0)
        self.assertGreater(self.adb.count("mdns", "services"), 1)

        # The announced port refuses: still paired, still asking for the port.
        self.adb.answers["mdns services"] = (
            0, MDNS_HEADER + "adb-R58M12ABCDE-a1b2c3\t_adb-tls-connect._tcp\t192.168.1.20:41234\n", "")
        self.adb.answers["connect"] = (0, "failed to connect to 192.168.1.20:41234\n", "")
        self.assertEqual(self._post("/pair/code", PAIR_BODY), (200, want))
        self.assertGreater(self.adb.count("connect"), 0)

        # adb breaks after the pairing: the pairing stands.
        self.adb.answers["mdns check"] = bridge_server.AdbTimeoutError("command timed out")
        self.assertEqual(self._post("/pair/code", PAIR_BODY), (200, want))

    def test_pair_code_failure(self):
        """No "Successfully paired to", or a non-zero exit: pair_failed, with advice and without the code."""
        for answer in ((1, "", "error: protocol fault (couldn't read status message): No error\n"),
                       (0, "Failed: Wrong password or connection was dropped.\n", ""),   # adb before 34.0.5
                       (1, "Successfully paired to 192.168.1.20:37123 [guid=adb-x]\n", ""),
                       (0, "", "")):
            self.adb.calls.clear()
            self.adb.answers["pair"] = answer
            with mock.patch.object(bridge_server, "_log") as log:
                status, data = self._post("/pair/code", PAIR_BODY)
            self.assertEqual((status, data["code"], data["success"]), (502, "pair_failed", False))
            self.assertIn("192.168.1.20:37123", data["error"])
            self.assertIn("six-digit code", data["error"])
            self.assertNotIn("123456", json.dumps(data) + str(log.call_args_list))
            self.assertEqual(self.adb.calls, [["pair", "192.168.1.20:37123", "123456"]])  # no connect attempt

    def test_pair_code_adb_errors(self):
        for answer, want in ((bridge_server.AdbTimeoutError("command timed out after 30s: adb pair 192.168.1.20:37123 ******"),
                              (504, "adb_timeout")),
                             (bridge_server.AdbNotFoundError("adb executable not found: x"), (502, "adb_not_found"))):
            self.adb.answers["pair"] = answer
            status, data = self._post("/pair/code", PAIR_BODY)
            self.assertEqual((status, data["code"]), want)
            self.assertNotIn("123456", data["error"])

    def test_wireless_requests_run_one_at_a_time(self):
        """A second pairing or connect request while one runs gets 409 busy and starts no adb command."""
        self.assertTrue(bridge_server._WIRELESS_LOCK.acquire(blocking=False))
        try:
            for path, body in (("/pair/code", PAIR_BODY), ("/connect", CONNECT_BODY)):
                status, data = self._post(path, body)
                self.assertEqual((status, data["code"], data["success"]), (409, "busy", False), path)
        finally:
            bridge_server._WIRELESS_LOCK.release()
        self.assertEqual(self.adb.calls, [])
        self.adb.answers["connect"] = (0, "failed to connect to 192.168.1.20:41234\n", "")
        self.assertEqual(self._post("/connect", CONNECT_BODY)[1]["code"], "connect_failed")  # the lock was freed
        self.assertFalse(bridge_server._WIRELESS_LOCK.locked())

    # -- /connect --------------------------------------------------------------

    def test_connect_validation(self):
        for body in ({}, {"host": "192.168.1.20"}, {"port": 41234}, {**CONNECT_BODY, "host": "phone.local"},
                     {**CONNECT_BODY, "host": "-s"}, {**CONNECT_BODY, "host": "0.0.0.0"},
                     {**CONNECT_BODY, "port": "41234"}, {**CONNECT_BODY, "port": 0}, {**CONNECT_BODY, "port": 70000}):
            status, data = self._post("/connect", body)
            self.assertEqual((status, data["code"]), (400, "bad_request"), body)
        self.assertEqual(self.adb.calls, [])

    def test_connect_success(self):
        """`connected to` plus the serial in state device: success, and /devices shows the phone."""
        self.adb.answers["connect"] = (0, "connected to 192.168.1.20:41234\n", "")
        self.adb.devices = PIXEL_WIFI
        for path in ("/connect", "/api/connect"):
            self.assertEqual(self._post(path, CONNECT_BODY), (200, {
                "success": True, "connected": True, "serial": "192.168.1.20:41234", "already": False}))
        self.assertEqual(self.adb.calls[0], ["connect", "192.168.1.20:41234"])
        data = self._get("/devices")[1]
        self.assertEqual([(d["serial"], d["state"]) for d in data["devices"]], [("192.168.1.20:41234", "device")])

    def test_connect_already_connected(self):
        self.adb.answers["connect"] = (0, "already connected to 192.168.1.20:41234\n", "")
        self.adb.devices = PIXEL_WIFI
        self.assertEqual(self._post("/connect", CONNECT_BODY), (200, {
            "success": True, "connected": True, "serial": "192.168.1.20:41234", "already": True}))

    def test_connect_waits_for_state_device(self):
        """The serial may be offline for a moment after `connected to`: wait for it, within limits."""
        self.adb.answers["connect"] = (0, "connected to 192.168.1.20:41234\n", "")
        self.adb.devices = ["", PIXEL_WIFI.replace(" device ", " offline "), PIXEL_WIFI]
        status, data = self._post("/connect", CONNECT_BODY)
        self.assertEqual((status, data["connected"], data["serial"]), (200, True, "192.168.1.20:41234"))
        self.assertEqual(self.adb.count("devices"), 3)

    def test_connect_failure_with_exit_status_0(self):
        """adb connect exits 0 when it fails: the text decides, and the answer says what to check."""
        refused = ("cannot connect to 192.168.1.20:41234: No connection could be made because the "
                   "target machine actively refused it. (10061)")
        for said in ("failed to connect to 192.168.1.20:41234",
                     refused,
                     "failed to connect to '192.168.1.20:41234': Connection refused",
                     "failed to authenticate to 192.168.1.20:41234",
                     ""):
            self.adb.calls.clear()
            self.adb.answers["connect"] = (0, said + "\n", "")
            self.adb.devices = PIXEL_WIFI  # even if a stale entry is listed
            status, data = self._post("/connect", CONNECT_BODY)
            self.assertEqual((status, data["code"], data["success"]), (502, "connect_failed", False), said)
            self.assertIn("192.168.1.20:41234", data["error"])
            self.assertIn("pair", data["error"].lower())
            if said:
                self.assertIn(said, data["error"])
            self.assertEqual(self.adb.count("devices"), 0)
        self.assertIn("pairing dialog", self._post("/connect", CONNECT_BODY)[1]["error"])

    def test_connect_not_confirmed_by_device_list(self):
        """`connected to` is not enough: the serial must reach state device."""
        self.adb.answers["connect"] = (0, "connected to 192.168.1.20:41234\n", "")
        for listing, word in ((PIXEL_WIFI.replace(" device ", " offline "), "offline"),
                              (PIXEL_WIFI.replace(" device ", " unauthorized "), "authorized"),
                              (PIXEL_USB, "not in adb's device list")):
            self.adb.devices = listing
            status, data = self._post("/connect", CONNECT_BODY)
            self.assertEqual((status, data["code"]), (502, "connect_failed"), listing)
            self.assertIn(word, data["error"])

    def test_connect_adb_errors(self):
        for answer, want in (((1, "", "error: cannot connect to daemon\n"), (502, "adb_failed")),
                             (bridge_server.AdbNotFoundError("adb executable not found: x"), (502, "adb_not_found"))):
            self.adb.answers["connect"] = answer
            status, data = self._post("/connect", CONNECT_BODY)
            self.assertEqual((status, data["code"]), want)
        # A device list that cannot be read while confirming is still an adb failure of its own.
        self.adb.answers["connect"] = (0, "connected to 192.168.1.20:41234\n", "")
        self.adb.devices = bridge_server.AdbTimeoutError("command timed out after 15s: adb devices -l")
        status, data = self._post("/connect", CONNECT_BODY)
        self.assertEqual((status, data["code"]), (504, "adb_timeout"))

    def test_connect_without_an_answer_in_time_is_a_connect_failure(self):
        """An address that drops packets makes adb connect run into its time limit: connect_failed, with advice."""
        raw = "command timed out after 35s: adb-test connect 192.168.1.20:41234"
        self.adb.answers["connect"] = bridge_server.AdbTimeoutError(raw)
        status, data = self._post("/connect", CONNECT_BODY)
        self.assertEqual((status, data["code"], data["success"]), (502, "connect_failed", False))
        self.assertIn("No answer from 192.168.1.20:41234 within 35 seconds", data["error"])
        self.assertIn("same network", data["error"])
        self.assertIn("Wireless debugging", data["error"])
        self.assertNotIn("command timed out", data["error"])  # no raw command line for the user
        self.assertNotIn("adb-test", data["error"])
        self.assertEqual(self.adb.count("devices"), 0)
        with self.assertRaises(bridge_server.ConnectFailedError) as ctx:
            bridge_server.adb_connect("adb-test", "192.168.1.20", 41234, timeout=12.0)
        self.assertIn("within 12 seconds", str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)

    # -- /pair/status: connection fields -----------------------------------------

    def test_pair_status_connection_fields(self):
        """connected, needs_connect_port and host are false, false, null except in state paired."""
        blank = {"connected": False, "needs_connect_port": False, "host": None}
        fake, _, _ = self._start_pairing()
        status = self._get("/pair/status")[1]
        self.assertEqual(status, {"state": "waiting", "id": "abc123", "serial": None, "error": None, **blank})
        fake.finish(SimpleNamespace(serial="192.168.1.5:5555"))
        self.assertEqual(self._pair_state("paired"), {
            "state": "paired", "id": "abc123", "serial": "192.168.1.5:5555", "error": None,
            "connected": True, "needs_connect_port": False, "host": "192.168.1.5"})

        # Connected under adb's mDNS name: the address comes from the endpoint, or is unknown.
        fake, _, _ = self._start_pairing()
        self.assertEqual(self._get("/pair/status")[1], {"state": "waiting", "id": "abc123", "serial": None,
                                                        "error": None, **blank})
        fake.finish(SimpleNamespace(serial="adb-R58M12ABCDE-a1b2c3._adb-tls-connect._tcp",
                                    endpoint="192.168.1.5:41234"))
        data = self._pair_state("paired")
        self.assertEqual((data["connected"], data["host"]), (True, "192.168.1.5"))
        fake, _, _ = self._start_pairing()
        fake.finish(SimpleNamespace(serial="adb-R58M12ABCDE-a1b2c3._adb-tls-connect._tcp"))
        data = self._pair_state("paired")
        self.assertEqual((data["connected"], data["needs_connect_port"], data["host"]), (True, False, None))

        for error, state in ((PairingError("Pairing handshake failed: wrong password"), "failed"),
                             (PairingTimeoutError("QR pairing timed out"), "expired")):
            fake, _, _ = self._start_pairing()
            fake.finish(error)
            data = self._pair_state(state)
            self.assertEqual({key: data[key] for key in blank}, blank)
        self._start_pairing()
        self.assertEqual(self._post("/pair/cancel", {})[1], {
            "success": True, "state": "idle", "id": None, "serial": None, "error": None, **blank})

    def test_pair_status_paired_without_connect_port(self):
        """Paired, but no connect port led to a connection: paired, not failed, and the page is told to ask."""
        fake, _, _ = self._start_pairing()
        fake.unconnected = "192.168.1.5"
        fake.finish(PairingError("Pairing succeeded with 192.168.1.5, but the phone's connect port "
                                 "was not announced on this network."))
        self.assertEqual(self._pair_state("paired"), {
            "state": "paired", "id": "abc123", "serial": None, "error": None,
            "connected": False, "needs_connect_port": True, "host": "192.168.1.5"})
        self.assertEqual(self._start_pairing()[1], 200)  # a new session may start

    def test_pair_qr_already_running_is_busy(self):
        self._start_pairing()
        with mock.patch.object(bridge_server, "new_pairing_manager") as factory:
            status, data = self._post("/pair/qr", {})
        self.assertEqual((status, data["code"]), (409, "busy"))
        factory.assert_not_called()

    def test_pair_qr_start_failure_codes(self):
        for error, code in ((bridge_server.AdbNotFoundError("adb executable not found: x"), "adb_not_found"),
                            (ImportError("No module named 'connection'"), "pair_failed")):
            with mock.patch.object(bridge_server, "new_pairing_manager", side_effect=error):
                status, data = self._post("/pair/qr", {})
            self.assertEqual((status, data["code"], data["success"]), (502, code, False))

    def test_pair_qr_real_flow_without_connect_port(self):
        """The real QrPairingManager: paired, no connect service on the network, so the port is asked for."""

        def run_adb(_client, args, timeout=None, serial=None):
            if args == ["mdns", "services"]:
                name = f"AI_Phone_Debloater_Rovoxia_{bridge_server._PAIR['id']}"
                return 0, f"{MDNS_HEADER}{name}\t_adb-tls-pairing._tcp\t192.168.1.5:37123\n", ""
            if args[0] == "pair":
                return 0, "Successfully paired to 192.168.1.5:37123 [guid=adb-test]\n", ""
            if args == ["devices", "-l"]:
                return 0, HEADER + PIXEL_USB + "\n", ""  # only another phone, on a cable
            self.fail(f"unexpected adb call: {args[0]}")

        clock = mock.MagicMock()  # the flow's 30 s search for a connect port takes no real time
        clock.now = 0.0
        clock.time.side_effect = lambda: clock.now
        clock.sleep.side_effect = lambda seconds: setattr(clock, "now", clock.now + seconds)
        with tempfile.TemporaryDirectory() as tmp:
            adb = Path(tmp) / "adb"
            adb.write_text("")
            adb.chmod(0o755)
            with mock.patch.object(bridge_server, "discover_adb", return_value=str(adb)), \
                    mock.patch.object(AdbClient, "run_adb", run_adb), \
                    mock.patch("connection.qr_pairing.time", clock):
                self.assertEqual(self._post("/pair/qr", {})[0], 200)
                data = self._pair_state("paired")
        self.assertEqual((data["serial"], data["error"]), (None, None))
        self.assertEqual((data["connected"], data["needs_connect_port"], data["host"]), (False, True, "192.168.1.5"))
        self.assertEqual(clock.now, 30.0)

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
