#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Phone-Debloater — Wireless QR Pairing Engine
===============================================
Implements Android 11+ Wireless Debugging QR Pairing Protocol:
1. Generates official WPA3/ADB schema payload: `WIFI:T:ADB;S:<instance_name>;P:<password>;;`.
2. Renders high-contrast half-block QR code for terminal display.
3. Monitors mDNS for device `_adb-tls-pairing._tcp` announcement.
4. Completes cryptographic TLS SPAKE2 handshake via `adb pair`.
5. Resolves active `_adb-tls-connect._tcp` endpoint and connects via `adb connect`.
6. Verifies authorized device state.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .adb_client import AdbClient
from .device_identity import DeviceIdentityManager
from .discovery import MdnsDiscovery
from .exceptions import (
    OperationCancelledError,
    PairingError,
    PairingTimeoutError,
)
from .models import DeviceInfo, DiscoveredService, PairingSession
from .qr_generator import (
    generate_android_qr_payload,
    render_qr_for_terminal,
)
from .wireless import WirelessConnectionHandler

logger = logging.getLogger("rovoxia.connection.qr_pairing")


class QrPairingManager:
    """Orchestrates end-to-end QR code pairing and wireless connection."""

    def __init__(
        self,
        adb_client: AdbClient,
        identity_manager: Optional[DeviceIdentityManager] = None,
        wireless_handler: Optional[WirelessConnectionHandler] = None,
        mdns_discovery: Optional[MdnsDiscovery] = None,
        logger_obj: Optional[Any] = None,
    ) -> None:
        self.adb = adb_client
        self.identity = identity_manager or DeviceIdentityManager(adb_client)
        self.wireless = wireless_handler or WirelessConnectionHandler(adb_client, self.identity)
        self.mdns = mdns_discovery or MdnsDiscovery(adb_client)
        self.custom_logger = logger_obj
        self._active_session: Optional[PairingSession] = None
        self._cancel_flag = threading.Event()

    def create_pairing_session(self, ttl_seconds: float = 120.0) -> PairingSession:
        """
        Create a new, cryptographic QR pairing session with a random service instance
        name and one-time password.
        """
        random_id = secrets.token_hex(3)
        service_name = f"AI_Phone_Debloater_Rovoxia_{random_id}"

        # 6-digit numeric pairing password
        password = f"{secrets.randbelow(900000) + 100000:06d}"

        qr_payload = generate_android_qr_payload(service_name, password)
        now = time.time()

        session = PairingSession(
            session_id=random_id,
            service_name=service_name,
            password=password,
            qr_payload=qr_payload,
            created_at=now,
            expires_at=now + ttl_seconds,
            status="pending",
        )
        self._active_session = session
        self._cancel_flag.clear()
        return session

    def render_qr_code(self, session: PairingSession) -> str:
        """Generate terminal string representation of the QR code."""
        return render_qr_for_terminal(session.qr_payload, ec_level="M", quiet_zone=2)

    def cancel(self) -> None:
        """Signal cancellation of any active pairing loop."""
        self._cancel_flag.set()
        if self._active_session:
            self._active_session.status = "cancelled"

    def execute_qr_pairing_flow(
        self,
        session: Optional[PairingSession] = None,
        timeout: float = 120.0,
        progress_cb: Optional[Callable[[str, int], None]] = None,
        port_prompt_cb: Optional[Callable[[str], Optional[int]]] = None,
    ) -> DeviceInfo:
        """
        Full QR pairing and connection lifecycle:
        1. Watch mDNS for incoming pairing announcement matching session.
        2. Pair with device.
        3. Discover connection port.
        4. Connect to device.
        5. Verify authorization and return DeviceInfo.
        """
        if not session:
            session = self.create_pairing_session(ttl_seconds=timeout)

        start_time = time.time()
        logger.info(f"Initiated QR pairing session {session.session_id} (timeout={timeout:g}s)")

        # Record pre-existing pairing and connect services to distinguish new ones
        initial_pairing_services = {
            s.endpoint for s in self.mdns.get_pairing_services()
        }
        initial_connect_services = {
            s.endpoint for s in self.mdns.get_connect_services()
        }
        initial_attached_serials = {
            d.get("serial", "") for d in self.adb.list_devices()
        }

        pairing_service: Optional[DiscoveredService] = None

        # -------------------------------------------------------------------
        # Phase 1: Wait for phone to scan QR code and advertise pairing service
        # -------------------------------------------------------------------
        logger.info("Awaiting QR code scan by Android phone...")
        while (time.time() - start_time) < timeout:
            if self._cancel_flag.is_set():
                session.status = "cancelled"
                raise OperationCancelledError("QR pairing cancelled by user.")

            remaining = int(timeout - (time.time() - start_time))
            if progress_cb:
                progress_cb(f"Waiting for phone to scan QR code... ({remaining}s)", remaining)

            # Query mDNS for pairing services
            current_pairing = self.mdns.get_pairing_services()

            # 1. Match exact service name or prefix
            for s in current_pairing:
                if (
                    session.service_name in s.name
                    or s.name in session.service_name
                    or "AI_Phone_Debloater" in s.name
                    or "Rovoxia" in s.name
                ):
                    pairing_service = s
                    break

            # 2. Match newly appeared pairing service on LAN if name was generic
            if not pairing_service:
                for s in current_pairing:
                    if s.endpoint not in initial_pairing_services:
                        pairing_service = s
                        break

            # 3. Fallback: if only one pairing service exists on the local network, select it
            if not pairing_service and len(current_pairing) == 1:
                pairing_service = current_pairing[0]

            if pairing_service:
                logger.info(
                    f"Phone detected! Pairing service: {pairing_service.name} at {pairing_service.endpoint}"
                )
                break

            time.sleep(1.0)

        if not pairing_service:
            session.status = "timed_out"
            raise PairingTimeoutError(
                f"QR pairing timed out after {timeout:g}s without detecting a phone scan. "
                "Ensure your phone and PC are connected to the same Wi-Fi network."
            )

        # -------------------------------------------------------------------
        # Phase 2: Execute cryptographic pairing
        # -------------------------------------------------------------------
        if progress_cb:
            progress_cb("Phone detected! Establishing encrypted pairing...", int(timeout - (time.time() - start_time)))

        ok, pair_msg = self.wireless.pair_with_code(
            pairing_service.endpoint,
            session.password,
            timeout=25.0,
        )

        if not ok:
            session.status = "failed"
            raise PairingError(f"Pairing handshake failed: {pair_msg}")

        session.status = "paired"
        logger.info(f"Cryptographic pairing confirmed for {pairing_service.address}!")

        # -------------------------------------------------------------------
        # Phase 3: Discover connection service and connect
        # -------------------------------------------------------------------
        if progress_cb:
            progress_cb("Pairing succeeded! Discovering connection port...", int(timeout - (time.time() - start_time)))

        connect_endpoint: Optional[str] = None
        connect_start = time.time()

        # Allow up to 20 seconds for connection service to publish or auto-connect
        while (time.time() - connect_start) < 20.0:
            if self._cancel_flag.is_set():
                raise OperationCancelledError("Operation cancelled.")

            # A. Check if ADB daemon already auto-connected upon successful pairing
            for d in self.adb.list_devices():
                ser = d.get("serial", "")
                st = d.get("state", "")
                if st == "device" and (
                    pairing_service.address in ser
                    or (":" in ser and ser not in initial_attached_serials)
                ):
                    logger.info(f"Device already connected via ADB daemon: {ser}")
                    connect_endpoint = ser
                    break

            if connect_endpoint:
                break

            # B. Check mDNS for connect services
            current_connect = self.mdns.get_connect_services()
            for s in current_connect:
                if (
                    s.address == pairing_service.address
                    or pairing_service.address in s.address
                    or s.address in pairing_service.address
                ):
                    connect_endpoint = s.endpoint
                    break

            if not connect_endpoint:
                for s in current_connect:
                    if s.endpoint not in initial_connect_services:
                        connect_endpoint = s.endpoint
                        break

            if not connect_endpoint and len(current_connect) == 1:
                connect_endpoint = current_connect[0].endpoint

            if connect_endpoint:
                break

            time.sleep(1.0)

        # C. If mDNS did not detect the port, invoke fallback port callback if provided
        if not connect_endpoint and port_prompt_cb:
            custom_port = port_prompt_cb(pairing_service.address)
            if custom_port:
                connect_endpoint = f"{pairing_service.address}:{custom_port}"

        if not connect_endpoint:
            raise PairingError(
                f"Pairing succeeded with {pairing_service.address}, but mDNS connection port "
                f"was not advertised by your Wi-Fi network. Check the port shown under 'IP address & Port' "
                f"on your phone's Wireless debugging screen, and connect via option 2 (Manual IP:Port)."
            )

        # Connect if not already in adb list_devices
        already_attached = any(
            d.get("serial") == connect_endpoint and d.get("state") == "device"
            for d in self.adb.list_devices()
        )
        if not already_attached:
            if progress_cb:
                progress_cb(f"Connecting to wireless debugging endpoint {connect_endpoint}...", 10)

            connected_ok, connect_msg = self.wireless.connect(connect_endpoint, timeout=20.0)
            if not connected_ok:
                time.sleep(1.5)
                connected_ok, connect_msg = self.wireless.connect(connect_endpoint, timeout=20.0)

            if not connected_ok:
                raise PairingError(
                    f"Pairing succeeded but connection to {connect_endpoint} failed: {connect_msg}"
                )

        # -------------------------------------------------------------------
        # Phase 4: Validate authorized device state
        # -------------------------------------------------------------------
        if progress_cb:
            progress_cb("Verifying authorized connection status...", 5)

        info = self.wireless.verify_and_get_info(connect_endpoint)
        session.status = "connected"
        logger.info(f"QR Pairing complete: connected to {info.summary()}")
        return info
