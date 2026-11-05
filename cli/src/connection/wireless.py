#!/usr/bin/env python3
"""
AI-Phone-Debloater — Wireless TCP/IP Transport Handler
======================================================
Manages manual and mDNS-resolved ADB connections over Wi-Fi, port switching,
pairing via 6-digit codes, and endpoint state validation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .adb_client import AdbClient
from .device_identity import DeviceIdentityManager
from .discovery import validate_endpoint
from .exceptions import (
    ConnectionError,
    DeviceNotFoundError,
    DeviceUnauthorizedError,
    SecurityValidationError,
)
from .models import DeviceInfo, TransportType

logger = logging.getLogger("rovoxia.connection.wireless")


class WirelessConnectionHandler:
    """Handles ADB TCP/IP connection, disconnection, and PIN pairing."""

    def __init__(
        self,
        adb_client: AdbClient,
        identity_manager: DeviceIdentityManager | None = None,
        logger_obj: Any | None = None,
    ) -> None:
        self.adb = adb_client
        self.identity = identity_manager or DeviceIdentityManager(adb_client)
        self.custom_logger = logger_obj

    def connect(self, address: str, timeout: float = 15.0) -> tuple[bool, str]:
        """
        Connect to a wireless device via `adb connect HOST:PORT`.
        Validates endpoint before executing command.
        Note: `adb connect` exits 0 even on failure, so output must be inspected.
        """
        host, port = validate_endpoint(address)
        endpoint = f"{host}:{port}"

        logger.info(f"Connecting to wireless ADB at {endpoint}...")
        rc, out, err = self.adb.run_adb(["connect", endpoint], timeout=timeout)
        output = (out.strip() or err.strip()).lower()

        if rc == 0 and ("connected to" in output or "already connected to" in output):
            logger.info(f"Successfully connected to wireless ADB endpoint {endpoint}")
            return True, f"Connected to {endpoint}"

        error_msg = out.strip() or err.strip() or f"Connection failed (exit code {rc})"
        logger.warning(f"Wireless connection to {endpoint} failed: {error_msg}")
        return False, error_msg

    def disconnect(self, address: str | None = None, timeout: float = 10.0) -> bool:
        """Disconnect from a specific wireless device or all TCP/IP devices."""
        args = ["disconnect"]
        if address:
            host, port = validate_endpoint(address)
            args.append(f"{host}:{port}")

        rc, _out, _err = self.adb.run_adb(args, timeout=timeout)
        return rc == 0

    def pair_with_code(self, address: str, code: str, timeout: float = 20.0) -> tuple[bool, str]:
        """
        Pair with an Android 11+ device using a 6-digit numeric pairing code.
        Format: `adb pair HOST:PORT CODE`.
        """
        host, port = validate_endpoint(address)
        clean_code = code.strip()

        if not re.match(r"^\d{6}$", clean_code):
            raise SecurityValidationError("Pairing code must be exactly 6 numeric digits.")

        endpoint = f"{host}:{port}"
        logger.info(f"Pairing with wireless device at {endpoint}...")

        rc, out, err = self.adb.run_adb(["pair", endpoint, clean_code], timeout=timeout)
        output = (out.strip() or err.strip()).lower()

        if rc == 0 and "successfully paired" in output:
            logger.info(f"Successfully paired with {endpoint}")
            return True, f"Successfully paired with {endpoint}"

        error_msg = out.strip() or err.strip() or f"Pairing failed (exit code {rc})"
        logger.warning(f"Pairing with {endpoint} failed: {error_msg}")
        return False, error_msg

    def enable_tcpip(self, port: int = 5555, serial: str | None = None) -> bool:
        """
        Restart adbd on the target device listening on TCP/IP on the specified port.
        Used when transitioning from USB to Wi-Fi.
        """
        if not (1 <= port <= 65535):
            raise SecurityValidationError(f"Invalid port: {port}")

        logger.info(f"Switching device {serial or 'default'} to TCP/IP port {port}...")
        rc, out, err = self.adb.run_adb(["tcpip", str(port)], serial=serial, timeout=15.0)
        return rc == 0 and ("restarting in tcp mode" in (out + err).lower() or rc == 0)

    def list_wireless_devices(self) -> list[dict[str, str]]:
        """List currently connected wireless ADB devices."""
        all_devs = self.adb.list_devices()
        return [
            d for d in all_devs
            if TransportType.from_serial(d.get("serial", "")) == TransportType.WIRELESS
        ]

    def verify_and_get_info(self, endpoint: str) -> DeviceInfo:
        """
        Confirm that the wireless device at endpoint is in 'device' state and
        retrieve full device hardware metadata.
        """
        host, port = validate_endpoint(endpoint)
        target = f"{host}:{port}"

        state = self.adb.get_device_state(target)
        if state == "disconnected":
            raise DeviceNotFoundError(f"Device at {target} is not connected to ADB.")
        if state == "unauthorized":
            raise DeviceUnauthorizedError(
                f"Device at {target} is connected but unauthorized. Please check screen."
            )
        if state != "device":
            raise ConnectionError(f"Device at {target} is in state '{state}', expected 'device'.")

        return self.identity.populate(target, state="device")
