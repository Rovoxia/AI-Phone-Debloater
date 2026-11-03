#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Phone-Debloater — Device Identity Verification Subsystem
===========================================================
Extracts, validates, and correlates physical Android device identity across
multiple transports (USB and Wi-Fi) to prevent accidental debloating of the wrong
device and ensure identity consistency throughout sessions.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from .adb_client import AdbClient
from .models import DeviceInfo, TransportType

logger = logging.getLogger("rovoxia.connection.device_identity")


class DeviceIdentityManager:
    """Handles device metadata extraction, physical identity correlation, and safety validation."""

    def __init__(self, adb_client: AdbClient) -> None:
        self.adb = adb_client

    def populate(self, serial: str, state: str = "device") -> DeviceInfo:
        """
        Query system properties and construct a fully populated DeviceInfo instance.
        """
        transport_type = TransportType.from_serial(serial).value
        info = DeviceInfo(
            serial=serial,
            state=state,
            transport_type=transport_type,
            endpoint=serial if transport_type == "wireless" else "",
        )

        if state != "device":
            return info

        props = {
            "manufacturer": "ro.product.manufacturer",
            "model": "ro.product.model",
            "release": "ro.build.version.release",
            "sdk_int": "ro.build.version.sdk",
            "security_patch": "ro.build.version.security_patch",
            "build_id": "ro.build.display.id",
            "architecture": "ro.product.cpu.abi",
        }

        for attr, prop_name in props.items():
            val = self.adb.getprop(prop_name, serial=serial)
            setattr(info, attr, val or "unknown")

        # Resolve physical hardware identifier
        info.physical_id = self.resolve_physical_id(serial, info)
        return info

    def resolve_physical_id(self, serial: str, info: Optional[DeviceInfo] = None) -> str:
        """
        Determine canonical hardware identifier (ro.serialno, ro.boot.serialno, or USB serial).
        For wireless connections, queries ro.serialno so it matches the USB serial of the same phone.
        """
        hw_serial = self.adb.getprop("ro.serialno", serial=serial)
        if hw_serial and hw_serial.lower() not in ("unknown", ""):
            return hw_serial.strip()

        boot_serial = self.adb.getprop("ro.boot.serialno", serial=serial)
        if boot_serial and boot_serial.lower() not in ("unknown", ""):
            return boot_serial.strip()

        wifi_guid = self.adb.getprop("persist.adb.wifi.guid", serial=serial)
        if wifi_guid and wifi_guid.lower() not in ("unknown", ""):
            return wifi_guid.strip()

        # If connected via USB and serial is an alphanumeric hardware serial
        if ":" not in serial and not serial.startswith("emulator-"):
            return serial.strip()

        # Fallback to model + build_id fingerprint
        if info and info.model and info.build_id:
            return f"{info.manufacturer}_{info.model}_{info.build_id}".replace(" ", "_")

        return serial.strip()

    @staticmethod
    def is_same_physical_device(dev1: DeviceInfo, dev2: DeviceInfo) -> bool:
        """
        Determine if two DeviceInfo records (e.g. one USB and one Wi-Fi) correspond to
        the exact same physical device.
        """
        if not dev1 or not dev2:
            return False

        # Direct serial match
        if dev1.serial == dev2.serial:
            return True

        # Physical ID match (e.g. ro.serialno matched on both USB and Wi-Fi)
        if dev1.physical_id and dev2.physical_id and dev1.physical_id == dev2.physical_id:
            return True

        # Disallow false positive match on generic defaults
        if dev1.physical_id in ("unknown", "") or dev2.physical_id in ("unknown", ""):
            return False

        # If both have detailed metadata, check if manufacturer, model, build_id, and architecture match
        if (
            dev1.manufacturer
            and dev2.manufacturer
            and dev1.model
            and dev2.model
            and dev1.build_id
            and dev2.build_id
            and dev1.build_id != "unknown"
            and dev2.build_id != "unknown"
        ):
            return (
                dev1.manufacturer.lower() == dev2.manufacturer.lower()
                and dev1.model.lower() == dev2.model.lower()
                and dev1.build_id == dev2.build_id
                and dev1.architecture == dev2.architecture
            )

        return False

    def verify_consistency(self, target: DeviceInfo) -> Tuple[bool, str]:
        """
        Verify that the device connected at target.serial is still reachable, authorized,
        and matches target identity before destructive debloating operations.
        Returns (is_valid, error_reason).
        """
        if not target or not target.serial:
            return False, "No target device specified"

        # Check ADB device state
        current_state = self.adb.get_device_state(target.serial)
        if current_state == "disconnected":
            return False, f"Target device {target.serial} was disconnected from ADB."
        if current_state != "device":
            return False, (
                f"Target device {target.serial} is in state '{current_state}', not 'device' (authorized)."
            )

        # Check identity attributes if they were previously recorded
        if target.model and target.model != "unknown":
            current_model = self.adb.getprop("ro.product.model", serial=target.serial)
            if current_model and current_model.lower() != target.model.lower():
                return False, (
                    f"Device identity mismatch: expected model '{target.model}', "
                    f"found '{current_model}' on serial {target.serial}."
                )

        if target.physical_id and target.physical_id not in ("unknown", target.serial):
            current_pid = self.resolve_physical_id(target.serial)
            if current_pid and current_pid != target.physical_id:
                return False, (
                    f"Physical hardware mismatch: expected ID '{target.physical_id}', "
                    f"found '{current_pid}' on serial {target.serial}."
                )

        return True, ""
