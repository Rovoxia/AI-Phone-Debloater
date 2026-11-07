#!/usr/bin/env python3
"""
AI-Phone-Debloater — USB Transport Handler
==========================================
Manages physical USB Android debugging connections, device enumeration,
authorization state monitoring, and driver/RSA prompt diagnostics.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from .adb_client import AdbClient
from .device_identity import DeviceIdentityManager
from .exceptions import (
    DeviceNotFoundError,
    DeviceOfflineError,
    DeviceUnauthorizedError,
    OperationCancelledError,
)
from .models import DeviceInfo, TransportType

logger = logging.getLogger("rovoxia.connection.usb")


class UsbConnectionHandler:
    """Handles USB discovery, device polling, and authorization monitoring."""

    def __init__(
        self,
        adb_client: AdbClient,
        identity_manager: DeviceIdentityManager | None = None,
        logger_obj: Any | None = None,
    ) -> None:
        self.adb = adb_client
        self.identity = identity_manager or DeviceIdentityManager(adb_client)
        self.custom_logger = logger_obj

    def list_usb_devices(self) -> list[dict[str, str]]:
        """
        Enumerate all attached devices and filter for USB transports
        (excludes emulator-*, IP:Port, etc.).
        """
        all_devs = self.adb.list_devices()
        usb_devs: list[dict[str, str]] = []
        for d in all_devs:
            serial = d.get("serial", "")
            if not serial:
                continue
            tt = TransportType.from_serial(serial)
            if tt == TransportType.USB:
                usb_devs.append(d)
        return usb_devs

    def get_ready_devices(self) -> list[DeviceInfo]:
        """Return all USB devices that are in authorized 'device' state."""
        raw_list = self.list_usb_devices()
        ready = []
        for d in raw_list:
            if d.get("state") == "device":
                info = self.identity.populate(d["serial"], state="device")
                ready.append(info)
        return ready

    def wait_for_authorization(
        self,
        serial: str,
        timeout: float = 45.0,
        poll_interval: float = 1.0,
        progress_cb: Callable[[str, int], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> DeviceInfo:
        """
        Poll an attached device that is currently 'unauthorized' until the user
        accepts the RSA debugging fingerprint prompt on the phone screen.
        """
        start_time = time.time()
        attempt = 0

        logger.info(f"Waiting for user to accept USB debugging prompt for {serial}...")

        while (time.time() - start_time) < timeout:
            if cancel_check and cancel_check():
                raise OperationCancelledError("Authorization wait cancelled by user.")

            attempt += 1
            remaining = int(timeout - (time.time() - start_time))

            # Query current state from ADB listing
            devices = self.adb.list_devices()
            target = next((d for d in devices if d.get("serial") == serial), None)

            if not target:
                raise DeviceNotFoundError(f"Device {serial} was disconnected while awaiting authorization.")

            current_state = target.get("state", "").lower()

            if current_state == "device":
                logger.info(f"Device {serial} is now authorized and ready.")
                return self.identity.populate(serial, state="device")
            elif current_state == "offline":
                logger.debug(f"Device {serial} is temporarily offline. Retrying on next poll.")

            if progress_cb:
                progress_cb(f"Waiting for RSA authorization prompt on phone... ({remaining}s remaining)", remaining)

            time.sleep(poll_interval)

        # Timed out without authorization
        raise DeviceUnauthorizedError(
            f"Device {serial} remains unauthorized after {timeout:g}s. "
            "Please unlock your phone and check the screen for 'Allow USB debugging?'"
        )

    def detect_and_connect(
        self,
        serial: str | None = None,
        timeout: float = 30.0,
        progress_cb: Callable[[str], None] | None = None,
    ) -> DeviceInfo:
        """
        Connect to a USB device:
        1. Discover USB devices.
        2. If specific serial given, find it.
        3. If no devices, raise DeviceNotFoundError.
        4. If 1 device and unauthorized, wait for authorization.
        5. If multiple devices, raise DeviceAmbiguousError (or let caller select).
        6. Return fully populated DeviceInfo.
        """
        if progress_cb:
            progress_cb("Searching for connected USB Android devices...")

        usb_devices = self.list_usb_devices()

        if not usb_devices:
            raise DeviceNotFoundError(
                "No Android devices detected via USB. Please connect your phone with a USB cable "
                "and ensure 'USB debugging' is enabled in Developer Options."
            )

        if serial:
            target = next((d for d in usb_devices if d.get("serial") == serial), None)
            if not target:
                raise DeviceNotFoundError(f"USB device with serial '{serial}' was not found.")
        else:
            ready_devices = [d for d in usb_devices if d.get("state") == "device"]
            if len(ready_devices) == 1:
                target = ready_devices[0]
            elif len(usb_devices) == 1:
                target = usb_devices[0]
            else:
                # Multiple devices attached
                serials = [f"{d['serial']} ({d.get('state', 'unknown')})" for d in usb_devices]
                from .exceptions import DeviceAmbiguousError
                raise DeviceAmbiguousError(
                    f"Multiple USB devices detected: {', '.join(serials)}. Please specify a serial."
                )

        target_serial = target["serial"]
        target_state = target.get("state", "").lower()

        if target_state == "unauthorized":
            if progress_cb:
                progress_cb(f"Device {target_serial} is unauthorized. Please approve prompt on phone...")
            return self.wait_for_authorization(target_serial, timeout=timeout)
        elif target_state == "offline":
            raise DeviceOfflineError(
                f"Device {target_serial} is offline. Try unplugging and re-plugging the USB cable."
            )
        elif target_state != "device":
            raise DeviceUnauthorizedError(
                f"Device {target_serial} is in unsupported state '{target_state}'."
            )

        if progress_cb:
            progress_cb(f"Device ready: querying hardware parameters for {target_serial}...")

        return self.identity.populate(target_serial, state="device")
