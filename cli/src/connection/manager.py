#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Phone-Debloater — Centralized Connection Manager
===================================================
The single architectural authority for ADB lifecycle, device identity validation,
USB auto-detection, QR wireless pairing, mDNS discovery, and state machine transitions.
All application modules and debloating operations delegate to this manager.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .adb_client import AdbClient
from .device_identity import DeviceIdentityManager
from .device_registry import DeviceRegistry
from .diagnostics import ConnectionDiagnostics
from .discovery import MdnsDiscovery, LanDiscovery, validate_endpoint
from .exceptions import (
    AdbServerError,
    ConnectionError,
    DeviceAmbiguousError,
    DeviceNotFoundError,
    DeviceOfflineError,
    DeviceUnauthorizedError,
    OperationCancelledError,
    PairingError,
    SecurityValidationError,
)
from .models import (
    ConnectionState,
    DeviceInfo,
    DiagnosticReport,
    DiscoveredService,
    PairingSession,
    RememberedDevice,
    TransportType,
)
from .qr_pairing import QrPairingManager
from .usb import UsbConnectionHandler
from .wireless import WirelessConnectionHandler

logger = logging.getLogger("rovoxia.connection.manager")


class ConnectionManager:
    """Centralized coordinator for all ADB interactions and device connections."""

    def __init__(
        self,
        adb_path: Optional[str] = None,
        timeout: float = 30.0,
        logger_obj: Optional[Any] = None,
        registry: Optional[DeviceRegistry] = None,
    ) -> None:
        self.timeout = float(timeout)
        self.custom_logger = logger_obj
        self._state_lock = threading.RLock()
        self._state = ConnectionState.DISCONNECTED
        self._active_device: Optional[DeviceInfo] = None

        # Core ADB low-level client
        self.adb = AdbClient(adb_path=adb_path, timeout=timeout, logger_obj=logger_obj)

        # Specialized subsystem handlers
        self.identity = DeviceIdentityManager(self.adb)
        self.registry = registry or DeviceRegistry()
        self.mdns = MdnsDiscovery(self.adb, logger_obj=logger_obj)
        self.lan = LanDiscovery(logger_obj=logger_obj)
        self.usb = UsbConnectionHandler(self.adb, self.identity, logger_obj=logger_obj)
        self.wireless = WirelessConnectionHandler(self.adb, self.identity, logger_obj=logger_obj)
        self.qr_pairing = QrPairingManager(
            self.adb, self.identity, self.wireless, self.mdns, logger_obj=logger_obj
        )
        self.diagnostics = ConnectionDiagnostics(self.adb, self.mdns, self.lan)

        self._set_state(ConnectionState.INITIALIZING)
        self.initialize()

    # -----------------------------------------------------------------------
    # State Management
    # -----------------------------------------------------------------------

    @property
    def state(self) -> ConnectionState:
        with self._state_lock:
            return self._state

    def _set_state(self, new_state: ConnectionState) -> None:
        with self._state_lock:
            old_state = self._state
            self._state = new_state
            logger.debug(f"Connection state transition: {old_state.value} -> {new_state.value}")

    @property
    def active_device(self) -> Optional[DeviceInfo]:
        with self._state_lock:
            return self._active_device

    def set_active_device(self, device: Optional[DeviceInfo]) -> None:
        with self._state_lock:
            self._active_device = device
            if device:
                if device.is_authorized():
                    self._set_state(ConnectionState.CONNECTED)
                    # Automatically record in persistent registry
                    try:
                        self.registry.remember(device)
                    except Exception as exc:
                        logger.debug(f"Could not update registry for {device.serial}: {exc}")
                elif device.state == "unauthorized":
                    self._set_state(ConnectionState.UNAUTHORIZED)
                elif device.state == "offline":
                    self._set_state(ConnectionState.OFFLINE)
            else:
                self._set_state(ConnectionState.DISCONNECTED)

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def initialize(self) -> bool:
        """Start or verify the ADB server daemon."""
        with self._state_lock:
            if not self.adb.is_server_running():
                logger.info("Initializing ADB server daemon...")
                self.adb.start_server()
            self._set_state(ConnectionState.DISCONNECTED)
            return self.adb.is_server_running()

    def shutdown(self) -> None:
        """Clean up active connection state and background pairing sessions."""
        with self._state_lock:
            self.qr_pairing.cancel()
            self._active_device = None
            self._set_state(ConnectionState.DISCONNECTED)
            logger.info("Connection manager shut down.")

    # -----------------------------------------------------------------------
    # Device Query & Auto-Priority Detection
    # -----------------------------------------------------------------------

    def get_attached_devices(self) -> List[DeviceInfo]:
        """
        Query all attached ADB devices, deduplicate USB and Wi-Fi transports
        belonging to the same physical phone where possible, and return DeviceInfo records.
        """
        raw_list = self.adb.list_devices()
        devices: List[DeviceInfo] = []

        for d in raw_list:
            serial = d.get("serial", "")
            state = d.get("state", "unknown")
            if not serial:
                continue
            try:
                info = self.identity.populate(serial, state=state)
                devices.append(info)
            except Exception as exc:
                logger.debug(f"Failed to query hardware info for {serial}: {exc}")
                tt = TransportType.from_serial(serial).value
                devices.append(DeviceInfo(serial=serial, state=state, transport_type=tt))

        return devices

    def detect_connected_hardware(self) -> Tuple[List[DeviceInfo], List[Tuple[DeviceInfo, DeviceInfo]]]:
        """
        Identify unique physical devices and detect duplicate transports
        (e.g. phone attached over both USB and Wi-Fi simultaneously).
        Returns (unique_physical_devices, duplicate_pairs).
        """
        all_devs = self.get_attached_devices()
        unique: List[DeviceInfo] = []
        duplicates: List[Tuple[DeviceInfo, DeviceInfo]] = []

        for dev in all_devs:
            found_dup = False
            for u in unique:
                if self.identity.is_same_physical_device(dev, u):
                    duplicates.append((u, dev))
                    found_dup = True
                    break
            if not found_dup:
                unique.append(dev)

        return unique, duplicates

    # -----------------------------------------------------------------------
    # Connection Operations
    # -----------------------------------------------------------------------

    def connect_usb(
        self,
        serial: Optional[str] = None,
        timeout: float = 30.0,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> DeviceInfo:
        """Connect to an Android device over physical USB."""
        with self._state_lock:
            self._set_state(ConnectionState.INITIALIZING)
            try:
                self._set_state(ConnectionState.DISCOVERING)
                device = self.usb.detect_and_connect(
                    serial=serial, timeout=timeout, progress_cb=progress_cb
                )
                self.set_active_device(device)
                return device
            except DeviceUnauthorizedError:
                self._set_state(ConnectionState.UNAUTHORIZED)
                raise
            except DeviceOfflineError:
                self._set_state(ConnectionState.OFFLINE)
                raise
            except Exception as exc:
                self._set_state(ConnectionState.ERROR)
                raise

    def connect_wifi(
        self,
        address: str,
        timeout: float = 15.0,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> DeviceInfo:
        """Connect to a wireless device via HOST:PORT."""
        with self._state_lock:
            self._set_state(ConnectionState.CONNECTING)
            if progress_cb:
                progress_cb(f"Connecting to wireless ADB at {address}...")

            ok, msg = self.wireless.connect(address, timeout=timeout)
            if not ok:
                self._set_state(ConnectionState.ERROR)
                raise ConnectionError(f"Wireless connection failed: {msg}")

            if progress_cb:
                progress_cb("Verifying device authorization...")

            try:
                device = self.wireless.verify_and_get_info(address)
                self.set_active_device(device)
                return device
            except Exception as exc:
                self._set_state(ConnectionState.ERROR)
                raise

    def pair_wireless_code(
        self,
        address: str,
        code: str,
        timeout: float = 20.0,
    ) -> Tuple[bool, str]:
        """Pair with an Android 11+ device using a 6-digit numeric pairing code."""
        with self._state_lock:
            self._set_state(ConnectionState.PAIRING)
            ok, msg = self.wireless.pair_with_code(address, code, timeout=timeout)
            if ok:
                self._set_state(ConnectionState.PAIRED)
            else:
                self._set_state(ConnectionState.ERROR)
            return ok, msg

    def start_qr_pairing(
        self,
        timeout: float = 120.0,
        progress_cb: Optional[Callable[[str, int], None]] = None,
    ) -> Tuple[PairingSession, str]:
        """
        Initiate a QR code pairing session:
        Generates session and returns (session, rendered_terminal_qr_code).
        """
        with self._state_lock:
            self._set_state(ConnectionState.INITIALIZING)
            session = self.qr_pairing.create_pairing_session(ttl_seconds=timeout)
            qr_text = self.qr_pairing.render_qr_code(session)
            self._set_state(ConnectionState.WAITING_FOR_AUTHORIZATION)
            return session, qr_text

    def execute_qr_pairing_wait(
        self,
        session: PairingSession,
        timeout: float = 120.0,
        progress_cb: Optional[Callable[[str, int], None]] = None,
        port_prompt_cb: Optional[Callable[[str], Optional[int]]] = None,
    ) -> DeviceInfo:
        """Wait for phone scan, complete pairing and connection."""
        try:
            device = self.qr_pairing.execute_qr_pairing_flow(
                session=session,
                timeout=timeout,
                progress_cb=progress_cb,
                port_prompt_cb=port_prompt_cb,
            )
            self.set_active_device(device)
            return device
        except OperationCancelledError:
            self._set_state(ConnectionState.CANCELLED)
            raise
        except Exception:
            self._set_state(ConnectionState.ERROR)
            raise

    def cancel_qr_pairing(self) -> None:
        """Cancel an in-flight QR pairing process."""
        self.qr_pairing.cancel()
        self._set_state(ConnectionState.CANCELLED)

    def discover_wireless_devices(self) -> List[DiscoveredService]:
        """Discover connectable wireless ADB services via mDNS and LAN probe."""
        services = self.mdns.get_connect_services()
        if not services:
            # Secondary LAN scan
            lan_endpoints = self.lan.scan_lan_port(5555, timeout=0.2)
            for ep in lan_endpoints:
                host, port = ep.split(":")
                services.append(
                    DiscoveredService(
                        name="LAN-ADB",
                        service_type="_adb._tcp",
                        address=host,
                        port=int(port),
                        raw=ep,
                    )
                )
        return services

    def reconnect_remembered(
        self,
        physical_id: Optional[str] = None,
        timeout: float = 15.0,
    ) -> Optional[DeviceInfo]:
        """
        Attempt automatic rediscovery and reconnection to a previously paired device.
        Never assumes the IP/port remains static.
        """
        with self._state_lock:
            remembered_list = self.registry.load_all()
            if not remembered_list:
                return None

            target_record = None
            if physical_id:
                target_record = next((r for r in remembered_list if r.physical_id == physical_id), None)
            else:
                # Pick the most recently connected device
                target_record = remembered_list[0]

            if not target_record:
                return None

            self._set_state(ConnectionState.RECONNECTING)
            logger.info(f"Attempting reconnection to remembered device: {target_record.friendly_name}")

            # 1. First check if it's currently connected via USB
            for dev in self.get_attached_devices():
                if dev.physical_id == target_record.physical_id and dev.is_authorized():
                    self.set_active_device(dev)
                    return dev

            # 2. Check mDNS for matching wireless device
            connect_services = self.mdns.get_connect_services()
            for s in connect_services:
                # Connect and check identity
                try:
                    dev = self.connect_wifi(s.endpoint, timeout=timeout)
                    if dev.physical_id == target_record.physical_id:
                        return dev
                except Exception:
                    continue

            # 3. Try last known endpoint as fallback
            if target_record.last_endpoint:
                try:
                    dev = self.connect_wifi(target_record.last_endpoint, timeout=timeout)
                    if dev.physical_id == target_record.physical_id:
                        return dev
                except Exception:
                    pass

            self._set_state(ConnectionState.DISCONNECTED)
            return None

    def disconnect_device(self, serial: Optional[str] = None) -> bool:
        """Disconnect the specified device or the active device."""
        with self._state_lock:
            target = serial or (self._active_device.serial if self._active_device else None)
            if not target:
                return False

            if ":" in target:
                self.wireless.disconnect(target)

            if self._active_device and self._active_device.serial == target:
                self._active_device = None
                self._set_state(ConnectionState.DISCONNECTED)

            return True

    # -----------------------------------------------------------------------
    # Device Consistency & Safety Validation
    # -----------------------------------------------------------------------

    def validate_active_device(self) -> Tuple[bool, str]:
        """
        CRITICAL SAFETY CHECK:
        Must be called immediately before ANY package disable, uninstall, or restore.
        Verifies:
        1. An active device is selected.
        2. Device is still physically connected to ADB.
        3. ADB state is still strictly 'device' (authorized).
        4. Hardware parameters (model, physical_id) match expectations.
        """
        with self._state_lock:
            if not self._active_device:
                return False, "No active device is currently selected or connected."

            is_valid, reason = self.identity.verify_consistency(self._active_device)
            if not is_valid:
                self._set_state(ConnectionState.ERROR)
                return False, f"Device validation failed: {reason}"

            return True, ""

    # -----------------------------------------------------------------------
    # Transport Switching (USB <-> Wi-Fi)
    # -----------------------------------------------------------------------

    def switch_transport(self, target_transport: str) -> DeviceInfo:
        """
        Switch active connection between USB and Wi-Fi safely without losing
        device consistency or prematurely closing the existing transport.
        """
        with self._state_lock:
            if not self._active_device:
                raise DeviceNotFoundError("No active device to switch transports for.")

            current = self._active_device
            if current.transport_type.lower() == target_transport.lower():
                return current

            logger.info(f"Switching transport from {current.transport_type} to {target_transport}...")

            if target_transport.lower() == "wireless":
                # Enable TCP/IP on device via current transport
                self.wireless.enable_tcpip(5555, serial=current.serial)
                time.sleep(1.0)

                # Query device IP address over shell
                rc, out, _ = self.adb.run_shell("ip route", serial=current.serial)
                ip_match = None
                for line in out.splitlines():
                    if "src" in line:
                        parts = line.split()
                        if "src" in parts:
                            idx = parts.index("src")
                            if idx + 1 < len(parts):
                                ip_match = parts[idx + 1]
                                break

                if not ip_match:
                    rc, out, _ = self.adb.run_shell("getprop dhcp.wlan0.ipaddress", serial=current.serial)
                    ip_match = out.strip()

                if not ip_match:
                    raise ConnectionError(
                        "Could not automatically detect the phone's Wi-Fi IP address. "
                        "Please check Wi-Fi settings on the phone."
                    )

                new_endpoint = f"{ip_match}:5555"
                new_device = self.connect_wifi(new_endpoint)

                # Verify same physical device
                if not self.identity.is_same_physical_device(current, new_device):
                    self.wireless.disconnect(new_endpoint)
                    raise ConnectionError(
                        "Safety check failed: The wireless device does not match the USB phone!"
                    )

                self.set_active_device(new_device)
                logger.info(f"Successfully switched transport to Wireless: {new_endpoint}")
                return new_device

            elif target_transport.lower() == "usb":
                # Connect USB device matching physical_id
                usb_devs = self.usb.get_ready_devices()
                matching_usb = next(
                    (d for d in usb_devs if self.identity.is_same_physical_device(current, d)),
                    None,
                )
                if not matching_usb:
                    raise DeviceNotFoundError(
                        "No ready USB connection matching the active device was found. "
                        "Please plug in the USB cable and approve any prompts."
                    )

                self.set_active_device(matching_usb)
                logger.info(f"Successfully switched transport to USB: {matching_usb.serial}")
                return matching_usb

            else:
                raise SecurityValidationError(f"Unknown transport type: {target_transport}")

    # -----------------------------------------------------------------------
    # Diagnostics & Status
    # -----------------------------------------------------------------------

    def run_diagnostics(self) -> DiagnosticReport:
        """Run the comprehensive connection diagnostics suite."""
        return self.diagnostics.run_all()

    def get_connection_status(self) -> Dict[str, Any]:
        """Return a structured snapshot of connection health and active device."""
        with self._state_lock:
            return {
                "state": self._state.value,
                "active_device": self._active_device.to_dict() if self._active_device else None,
                "is_connected": self._active_device is not None and self._active_device.is_authorized(),
                "server_running": self.adb.is_server_running(),
            }
