#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Phone-Debloater — Comprehensive Connection Subsystem Test Suite
==================================================================
Tests all connection architecture modules using mocked subprocesses and
isolated temporary environments:
- Exception hierarchy
- Data models and transport detection
- QR payload and matrix generation
- ADB client execution, redaction, and discovery
- Network and endpoint security validation
- Device identity correlation across transports
- Persistent device registry
- USB and Wireless handlers
- QR pairing state machine
- Connection diagnostics suite
- Centralized ConnectionManager lifecycle and safety checks
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure cli/src is on sys.path
TEST_DIR = Path(__file__).resolve().parent
CLI_SRC = TEST_DIR.parent / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from connection.adb_client import AdbClient, _redact_command
from connection.device_identity import DeviceIdentityManager
from connection.device_registry import DeviceRegistry
from connection.diagnostics import ConnectionDiagnostics
from connection.discovery import (
    LanDiscovery,
    MdnsDiscovery,
    validate_endpoint,
    validate_ip_address,
    validate_port,
)
from connection.exceptions import (
    AdbNotFoundError,
    AdbServerError,
    AdbVersionError,
    ConnectionError,
    DeviceAmbiguousError,
    DeviceNotFoundError,
    DeviceOfflineError,
    DeviceUnauthorizedError,
    DiscoveryError,
    OperationCancelledError,
    PairingError,
    PairingTimeoutError,
    SecurityValidationError,
)
from connection.manager import ConnectionManager
from connection.models import (
    ConnectionState,
    DeviceInfo,
    DeviceState,
    DiagnosticItem,
    DiagnosticReport,
    DiscoveredService,
    PairingSession,
    RememberedDevice,
    TransportType,
)
from connection.qr_generator import (
    _data_codewords,
    generate_android_qr_payload,
    generate_qr_matrix,
    render_qr_for_terminal,
    render_terminal_double_half_block,
)
from connection.qr_pairing import QrPairingManager
from connection.usb import UsbConnectionHandler
from connection.wireless import WirelessConnectionHandler


class TestConnectionExceptions(unittest.TestCase):
    """Test exception hierarchy and inheritance."""

    def test_inheritance(self):
        self.assertTrue(issubclass(AdbNotFoundError, ConnectionError))
        self.assertTrue(issubclass(AdbServerError, ConnectionError))
        self.assertTrue(issubclass(AdbVersionError, ConnectionError))
        self.assertTrue(issubclass(DeviceNotFoundError, ConnectionError))
        self.assertTrue(issubclass(DeviceUnauthorizedError, ConnectionError))
        self.assertTrue(issubclass(DeviceOfflineError, ConnectionError))
        self.assertTrue(issubclass(DeviceAmbiguousError, ConnectionError))
        self.assertTrue(issubclass(PairingError, ConnectionError))
        self.assertTrue(issubclass(PairingTimeoutError, PairingError))
        self.assertTrue(issubclass(DiscoveryError, ConnectionError))
        self.assertTrue(issubclass(SecurityValidationError, ConnectionError))
        self.assertTrue(issubclass(OperationCancelledError, ConnectionError))


class TestConnectionModels(unittest.TestCase):
    """Test dataclasses, enums, and transport detection."""

    def test_transport_type_detection(self):
        self.assertEqual(TransportType.from_serial("R5CR10ABCDE"), TransportType.USB)
        self.assertEqual(TransportType.from_serial("192.168.1.100:5555"), TransportType.WIRELESS)
        self.assertEqual(TransportType.from_serial("10.0.0.5:41235"), TransportType.WIRELESS)
        self.assertEqual(TransportType.from_serial("[fe80::1]:5555"), TransportType.WIRELESS)
        self.assertEqual(TransportType.from_serial("emulator-5554"), TransportType.EMULATOR)
        self.assertEqual(TransportType.from_serial("usb:1-2.3"), TransportType.USB)

    def test_device_info_methods(self):
        dev = DeviceInfo(
            serial="192.168.1.50:5555",
            state="device",
            transport_type=TransportType.WIRELESS.value,
            manufacturer="Google",
            model="Pixel 8",
            release="14",
            sdk_int="34",
        )
        self.assertTrue(dev.is_authorized())
        self.assertTrue(dev.is_wireless())
        self.assertIn("Google Pixel 8", dev.summary())
        d = dev.to_dict()
        self.assertEqual(d["serial"], "192.168.1.50:5555")
        self.assertEqual(d["manufacturer"], "Google")

    def test_discovered_service(self):
        s1 = DiscoveredService(
            name="adb-pairing",
            service_type="_adb-tls-pairing._tcp.",
            address="192.168.1.20",
            port=43210,
        )
        self.assertTrue(s1.is_pairing)
        self.assertFalse(s1.is_connect)
        self.assertEqual(s1.endpoint, "192.168.1.20:43210")

        s2 = DiscoveredService(
            name="adb-connect",
            service_type="_adb-tls-connect._tcp.",
            address="192.168.1.20",
            port=38999,
        )
        self.assertFalse(s2.is_pairing)
        self.assertTrue(s2.is_connect)


class TestQrGenerator(unittest.TestCase):
    """Test QR payload generation and terminal rendering."""

    def test_generate_android_qr_payload(self):
        payload = generate_android_qr_payload("studio-rovoxia-1234", "654321")
        self.assertEqual(payload, "WIFI:T:ADB;S:studio-rovoxia-1234;P:654321;;")

    def test_qr_matrix_generation(self):
        payload = generate_android_qr_payload("test-service", "123456")
        matrix = generate_qr_matrix(payload, ec_level="M")
        self.assertIsInstance(matrix, list)
        self.assertGreater(len(matrix), 20)
        self.assertEqual(len(matrix), len(matrix[0]))
        # Finder pattern upper left is black (True)
        self.assertTrue(matrix[0][0])

    def test_render_terminal_double_half_block(self):
        payload = "WIFI:T:ADB;S:test;P:111111;;"
        rendered = render_qr_for_terminal(payload, ec_level="M", quiet_zone=2)
        self.assertIsInstance(rendered, str)
        self.assertGreater(len(rendered), 100)
        # Verify half-block characters
        self.assertTrue(any(c in rendered for c in ("▀", "▄", "█", " ")))

    def test_qr_standards_compliance(self):
        # 1. Byte mode indicator must strictly be 0100 (4), not Kanji 1000 (8)
        data = b"WIFI:T:ADB;S:test;P:123456;;"
        codewords = _data_codewords(data, version=4, total_data_codewords=80)
        # First nibble of first codeword is mode indicator
        mode = (codewords[0] >> 4) & 0x0F
        self.assertEqual(mode, 0x04)  # 0100 = Byte mode

        # 2. Format information placement consistency between primary and redundant copies
        payload = "WIFI:T:ADB;S:studio-rovoxia-1234;P:654321;;"
        matrix = generate_qr_matrix(payload, ec_level="M")
        size = len(matrix)

        # Bit 14 (MSB): primary at (8, 0), redundant at (8, size - 1)
        self.assertEqual(matrix[8][0], matrix[8][size - 1])
        # Bit 0 (LSB): primary at (0, 8), redundant at (size - 1, 8)
        self.assertEqual(matrix[0][8], matrix[size - 1][8])


class TestDiscoveryAndSecurityValidation(unittest.TestCase):
    """Test IP and endpoint security validation against injection."""

    def test_validate_ip_address(self):
        self.assertTrue(validate_ip_address("192.168.1.1"))
        self.assertTrue(validate_ip_address("10.0.0.1"))
        self.assertTrue(validate_ip_address("127.0.0.1"))
        self.assertTrue(validate_ip_address("::1"))
        self.assertTrue(validate_ip_address("fe80::1"))

        self.assertFalse(validate_ip_address("192.168.1.999"))
        self.assertFalse(validate_ip_address("example.com"))
        self.assertFalse(validate_ip_address("192.168.1.1; rm -rf /"))
        self.assertFalse(validate_ip_address(""))

    def test_validate_port(self):
        self.assertTrue(validate_port(5555))
        self.assertTrue(validate_port("41235"))
        self.assertFalse(validate_port(0))
        self.assertFalse(validate_port(70000))
        self.assertFalse(validate_port("abc"))

    def test_validate_endpoint_valid(self):
        host, port = validate_endpoint("192.168.1.50:5555")
        self.assertEqual(host, "192.168.1.50")
        self.assertEqual(port, 5555)

        host, port = validate_endpoint("10.0.0.1")
        self.assertEqual(host, "10.0.0.1")
        self.assertEqual(port, 5555)

        host, port = validate_endpoint("[fe80::1]:41235")
        self.assertEqual(host, "fe80::1")
        self.assertEqual(port, 41235)

        # Domain names and mDNS .local hostnames
        host, port = validate_endpoint("android.local:5555")
        self.assertEqual(host, "android.local")
        self.assertEqual(port, 5555)

        host, port = validate_endpoint("pixel-phone.lan:41235")
        self.assertEqual(host, "pixel-phone.lan")
        self.assertEqual(port, 41235)

    def test_validate_endpoint_injection_attempts(self):
        bad_endpoints = [
            "192.168.1.50:5555; rm -rf /",
            "192.168.1.50:5555 & calc.exe",
            "192.168.1.50:5555 | cat /etc/passwd",
            "`reboot`",
            "$(id):5555",
            "192.168.1.50:5555\nreboot",
        ]
        for bad in bad_endpoints:
            with self.assertRaises(SecurityValidationError):
                validate_endpoint(bad)


class TestAdbClient(unittest.TestCase):
    """Test AdbClient command execution and credential redaction."""

    def test_command_redaction(self):
        cmd = ["adb", "pair", "192.168.1.50:41235", "123456"]
        redacted = _redact_command(cmd)
        self.assertNotIn("123456", redacted)
        self.assertIn("[REDACTED]", redacted)

        connect_cmd = ["adb", "connect", "192.168.1.50:5555"]
        redacted_conn = _redact_command(connect_cmd)
        self.assertNotIn("192.168.1.50:5555", redacted_conn)
        self.assertIn("[REDACTED]", redacted_conn)

    @patch("shutil.which")
    def test_discover_adb_explicit(self, mock_which):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            temp_adb = f.name
        try:
            client = AdbClient(adb_path=temp_adb)
            self.assertEqual(client.adb_path, temp_adb)
        finally:
            os.remove(temp_adb)

    @patch("subprocess.run")
    def test_run_adb_shell_false(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "List of devices attached\nR5CR10ABCDE device\n"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_adb = f.name
        try:
            client = AdbClient(adb_path=temp_adb)
            rc, out, err = client.run_adb(["devices"])
            self.assertEqual(rc, 0)
            self.assertIn("R5CR10ABCDE", out)
            # Verify shell=False was strictly enforced
            kwargs = mock_run.call_args[1]
            self.assertFalse(kwargs.get("shell", False))
            self.assertEqual(kwargs.get("stdin"), subprocess.DEVNULL)
        finally:
            os.remove(temp_adb)

    @patch("subprocess.run")
    def test_list_devices_parsing(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = (
            "List of devices attached\n"
            "R5CR10ABCDE            device product:e1sxxx model:SM_S921B device:e1s\n"
            "192.168.1.100:5555     device product:pixel8 model:Pixel_8 device:shiba\n"
            "emulator-5554          offline\n"
        )
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_adb = f.name
        try:
            client = AdbClient(adb_path=temp_adb)
            devices = client.list_devices()
            self.assertEqual(len(devices), 3)
            self.assertEqual(devices[0]["serial"], "R5CR10ABCDE")
            self.assertEqual(devices[0]["state"], "device")
            self.assertEqual(devices[0].get("model"), "SM_S921B")
            self.assertEqual(devices[1]["serial"], "192.168.1.100:5555")
            self.assertEqual(devices[2]["state"], "offline")
        finally:
            os.remove(temp_adb)


class TestDeviceIdentity(unittest.TestCase):
    """Test device hardware identification and multi-transport correlation."""

    def test_same_physical_device_correlation(self):
        mock_client = MagicMock()
        mgr = DeviceIdentityManager(mock_client)

        dev_usb = DeviceInfo(
            serial="R5CR10ABCDE",
            state="device",
            transport_type="usb",
            physical_id="R5CR10ABCDE",
            manufacturer="Samsung",
            model="SM-S921B",
        )

        dev_wifi = DeviceInfo(
            serial="192.168.1.105:41235",
            state="device",
            transport_type="wireless",
            physical_id="R5CR10ABCDE",
            manufacturer="Samsung",
            model="SM-S921B",
        )

        dev_different = DeviceInfo(
            serial="988A10XYZ",
            state="device",
            transport_type="usb",
            physical_id="988A10XYZ",
            manufacturer="Google",
            model="Pixel 8",
        )

        self.assertTrue(mgr.is_same_physical_device(dev_usb, dev_wifi))
        self.assertFalse(mgr.is_same_physical_device(dev_usb, dev_different))

    def test_verify_consistency_authorized(self):
        mock_client = MagicMock()
        mock_client.get_device_state.return_value = "device"
        mock_client.getprop.side_effect = lambda prop, **kw: "SM-S921B" if "model" in prop else "R5CR10ABCDE"

        mgr = DeviceIdentityManager(mock_client)
        dev = DeviceInfo(
            serial="R5CR10ABCDE",
            state="device",
            physical_id="R5CR10ABCDE",
            model="SM-S921B",
        )

        is_valid, reason = mgr.verify_consistency(dev)
        self.assertTrue(is_valid)
        self.assertEqual(reason, "")

    def test_verify_consistency_disconnected_or_unauthorized(self):
        mock_client = MagicMock()
        mock_client.get_device_state.return_value = "disconnected"

        mgr = DeviceIdentityManager(mock_client)
        dev = DeviceInfo(serial="R5CR10ABCDE", state="device")

        is_valid, reason = mgr.verify_consistency(dev)
        self.assertFalse(is_valid)
        self.assertIn("disconnected", reason)


class TestDeviceRegistry(unittest.TestCase):
    """Test remembered device persistent registry."""

    def test_remember_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reg_file = Path(tmpdir) / "test_known_devices.json"
            registry = DeviceRegistry(registry_file=reg_file)

            dev = DeviceInfo(
                serial="R5CR10ABCDE",
                state="device",
                physical_id="SERIAL-12345",
                manufacturer="Samsung",
                model="SM-S921B",
                transport_type="usb",
            )

            record = registry.remember(dev, friendly_name="Galaxy S24")
            self.assertEqual(record.friendly_name, "Galaxy S24")
            self.assertTrue(reg_file.is_file())

            # Load back
            loaded = registry.get("SERIAL-12345")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.friendly_name, "Galaxy S24")
            self.assertEqual(loaded.model, "SM-S921B")

            # Update friendly name
            registry.set_friendly_name("SERIAL-12345", "Work Phone")
            self.assertEqual(registry.get("SERIAL-12345").friendly_name, "Work Phone")

            # Forget
            self.assertTrue(registry.forget("SERIAL-12345"))
            self.assertIsNone(registry.get("SERIAL-12345"))


class TestUsbHandler(unittest.TestCase):
    """Test USB connection handler."""

    def test_list_usb_devices(self):
        mock_client = MagicMock()
        mock_client.list_devices.return_value = [
            {"serial": "R5CR10ABCDE", "state": "device", "model": "SM-S921B"},
            {"serial": "192.168.1.100:5555", "state": "device"},
            {"serial": "emulator-5554", "state": "device"},
        ]

        handler = UsbConnectionHandler(mock_client)
        usb_list = handler.list_usb_devices()
        self.assertEqual(len(usb_list), 1)
        self.assertEqual(usb_list[0]["serial"], "R5CR10ABCDE")

    def test_wait_for_authorization_timeout(self):
        mock_client = MagicMock()
        mock_client.list_devices.return_value = [{"serial": "R5CR10ABCDE", "state": "unauthorized"}]
        mock_client.get_device_state.return_value = "unauthorized"

        handler = UsbConnectionHandler(mock_client)
        with self.assertRaises(DeviceUnauthorizedError):
            handler.wait_for_authorization("R5CR10ABCDE", timeout=0.1, poll_interval=0.05)


class TestWirelessHandler(unittest.TestCase):
    """Test wireless connection and pairing."""

    def test_connect_success(self):
        mock_client = MagicMock()
        mock_client.run_adb.return_value = (0, "connected to 192.168.1.50:5555\n", "")

        handler = WirelessConnectionHandler(mock_client)
        ok, msg = handler.connect("192.168.1.50:5555")
        self.assertTrue(ok)
        self.assertIn("Connected", msg)

    def test_connect_failure_with_rc_zero(self):
        mock_client = MagicMock()
        # adb connect returns rc=0 on failure with text 'cannot connect to ...'
        mock_client.run_adb.return_value = (0, "cannot connect to 192.168.1.50:5555: No connection could be made", "")

        handler = WirelessConnectionHandler(mock_client)
        ok, msg = handler.connect("192.168.1.50:5555")
        self.assertFalse(ok)
        self.assertIn("cannot connect", msg)

    def test_pair_with_code_invalid_pin(self):
        mock_client = MagicMock()
        handler = WirelessConnectionHandler(mock_client)

        with self.assertRaises(SecurityValidationError):
            handler.pair_with_code("192.168.1.50:41235", "123")  # Not 6 digits

        with self.assertRaises(SecurityValidationError):
            handler.pair_with_code("192.168.1.50:41235", "12345a")  # Non-numeric


class TestQrPairingManager(unittest.TestCase):
    """Test QR pairing session creation and mDNS flow."""

    def test_create_pairing_session(self):
        mock_client = MagicMock()
        mgr = QrPairingManager(mock_client)
        session = mgr.create_pairing_session(ttl_seconds=60.0)

        self.assertIsInstance(session, PairingSession)
        self.assertTrue(session.service_name.startswith("AI_Phone_Debloater_Rovoxia_"))
        self.assertEqual(len(session.password), 6)
        self.assertTrue(session.password.isdigit())
        self.assertIn(f"S:{session.service_name}", session.qr_payload)
        self.assertIn(f"P:{session.password}", session.qr_payload)

    def test_mdns_discovery_with_spaces_in_name(self):
        mock_client = MagicMock()
        mock_client.run_adb.return_value = (
            0,
            "List of discovered mdns services\n"
            "Samsung Galaxy S24 Ultra    _adb-tls-connect._tcp    192.168.1.105:38921\n"
            "AI_Phone_Debloater_Rovoxia 123    _adb-tls-pairing._tcp    192.168.1.105:41235\n",
            "",
        )
        discovery = MdnsDiscovery(mock_client)
        services = discovery.discover_services()
        self.assertEqual(len(services), 2)

        s1 = services[0]
        self.assertEqual(s1.name, "Samsung Galaxy S24 Ultra")
        self.assertEqual(s1.service_type, "_adb-tls-connect._tcp")
        self.assertEqual(s1.address, "192.168.1.105")
        self.assertEqual(s1.port, 38921)
        self.assertTrue(s1.is_connect)
        self.assertFalse(s1.is_pairing)

        s2 = services[1]
        self.assertEqual(s2.name, "AI_Phone_Debloater_Rovoxia 123")
        self.assertEqual(s2.service_type, "_adb-tls-pairing._tcp")
        self.assertEqual(s2.address, "192.168.1.105")
        self.assertEqual(s2.port, 41235)
        self.assertTrue(s2.is_pairing)
        self.assertFalse(s2.is_connect)


class TestDiscoveredServiceFlags(unittest.TestCase):
    """Regression: pairing port must never be used as connect port."""

    def test_pairing_port_is_not_connect_port(self):
        svc = DiscoveredService(
            name="phone", service_type="_adb-tls-pairing._tcp",
            address="192.168.1.50", port=41235,
        )
        self.assertTrue(svc.is_pairing)
        self.assertFalse(svc.is_connect)

    def test_connect_service_is_not_pairing_port(self):
        svc = DiscoveredService(
            name="phone", service_type="_adb-tls-connect._tcp",
            address="192.168.1.50", port=38921,
        )
        self.assertTrue(svc.is_connect)
        self.assertFalse(svc.is_pairing)


class TestConnectionDiagnostics(unittest.TestCase):
    """Test Connection Diagnostics suite."""

    def test_diagnostics_run_all(self):
        mock_client = MagicMock()
        mock_client.adb_path = sys.executable  # Existing file
        mock_client.get_version.return_value = "1.0.41"
        mock_client.is_server_running.return_value = True
        mock_client.list_devices.return_value = [
            {"serial": "R5CR10ABCDE", "state": "device", "model": "SM-S921B"}
        ]

        mock_mdns = MagicMock()
        mock_mdns.check_mdns.return_value = True
        mock_mdns.discover_services.return_value = []

        mock_lan = MagicMock()
        mock_lan.get_local_ip.return_value = "192.168.1.10"

        diag = ConnectionDiagnostics(mock_client, mdns_discovery=mock_mdns, lan_discovery=mock_lan)
        report = diag.run_all()

        self.assertIsInstance(report, DiagnosticReport)
        self.assertGreaterEqual(report.summary.get("OK", 0), 4)
        report_text = report.to_text()
        self.assertIn("ADB Installation", report_text)
        self.assertIn("1.0.41", report_text)


class TestConnectionManager(unittest.TestCase):
    """Test central ConnectionManager coordination and safety checks."""

    @patch("connection.manager.AdbClient")
    def test_state_transitions_and_pre_mutation_safety(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.is_server_running.return_value = True
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager(adb_path="dummy_adb", registry=MagicMock())
        self.assertEqual(mgr.state, ConnectionState.DISCONNECTED)

        # 1. Pre-mutation validation fails when no device is connected
        is_valid, reason = mgr.validate_active_device()
        self.assertFalse(is_valid)
        self.assertIn("No active device", reason)

        # 2. Set active device
        dev = DeviceInfo(
            serial="R5CR10ABCDE",
            state="device",
            physical_id="R5CR10ABCDE",
            model="SM-S921B",
        )
        mgr.set_active_device(dev)
        self.assertEqual(mgr.state, ConnectionState.CONNECTED)
        self.assertEqual(mgr.active_device, dev)

        # 3. Pre-mutation validation succeeds when device is authorized
        mock_client.get_device_state.return_value = "device"
        mock_client.getprop.side_effect = lambda prop, **kw: "SM-S921B" if "model" in prop else "R5CR10ABCDE"

        is_valid, reason = mgr.validate_active_device()
        self.assertTrue(is_valid)
        self.assertEqual(reason, "")

        # 4. Disconnect device
        mgr.disconnect_device("R5CR10ABCDE")
        self.assertEqual(mgr.state, ConnectionState.DISCONNECTED)
        self.assertIsNone(mgr.active_device)


if __name__ == "__main__":
    unittest.main()
