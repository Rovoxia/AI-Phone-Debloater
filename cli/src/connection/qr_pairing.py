#!/usr/bin/env python3
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
from collections.abc import Callable
from typing import Any

from .adb_client import AdbClient
from .device_identity import DeviceIdentityManager
from .discovery import MdnsDiscovery
from .exceptions import (
    AdbServerError,
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
        identity_manager: DeviceIdentityManager | None = None,
        wireless_handler: WirelessConnectionHandler | None = None,
        mdns_discovery: MdnsDiscovery | None = None,
        logger_obj: Any | None = None,
    ) -> None:
        self.adb = adb_client
        self.identity = identity_manager or DeviceIdentityManager(adb_client)
        self.wireless = wireless_handler or WirelessConnectionHandler(adb_client, self.identity)
        self.mdns = mdns_discovery or MdnsDiscovery(adb_client)
        self.custom_logger = logger_obj
        self._active_session: PairingSession | None = None
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
        session: PairingSession | None = None,
        timeout: float = 120.0,
        progress_cb: Callable[[str, int], None] | None = None,
        port_prompt_cb: Callable[[str], int | None] | None = None,
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

        pairing_service: DiscoveredService | None = None

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

            # 1. Match this session's instance name. The phone advertises the
            #    name from the QR code as is; mDNS may append a suffix such as
            #    " (2)". The reverse test (advertised name inside ours) is not
            #    used: it would accept any short name, like "AI", from another phone.
            for s in current_pairing:
                if session.service_name and session.service_name in s.name:
                    pairing_service = s
                    break

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

        address = pairing_service.address
        serial: str | None = None  # adb serial of the connected phone
        mdns_endpoint = ""  # ip:port behind an mDNS-style serial
        failed_endpoint = ""
        connect_msg = ""
        connect_start = time.time()

        def try_connect(endpoint: str, connect_timeout: float) -> bool:
            nonlocal failed_endpoint, connect_msg
            if progress_cb:
                progress_cb(f"Connecting to wireless debugging endpoint {endpoint}...", 10)
            try:
                ok, connect_msg = self.wireless.connect(endpoint, timeout=connect_timeout)
            except AdbServerError as exc:  # adb connect timed out
                ok, connect_msg = False, str(exc)
            if not ok:
                failed_endpoint = endpoint
            return ok

        # The connect service can appear, or change its port, a few seconds
        # after pairing. Poll for up to 30 seconds, retrying a failed connect.
        while (time.time() - connect_start) < 30.0:
            if self._cancel_flag.is_set():
                raise OperationCancelledError("Operation cancelled.")

            # Only an _adb-tls-connect service at the paired phone's address is
            # a target. A legacy _adb._tcp entry (port 5555) is often advertised
            # with nothing listening, and adb connect to the pairing port hangs.
            tls_services = [
                s for s in self.mdns.get_connect_services()
                if "_adb-tls-connect" in s.service_type
                and s.address == address
                and s.port != pairing_service.port
            ]

            # A. adb may have connected by itself after pairing. It lists the
            #    phone as ip:port, or as "<instance name>.<service type>".
            mdns_serials = {f"{s.name}.{s.service_type}": s.endpoint for s in tls_services}
            for d in self.adb.list_devices():
                ser = d.get("serial", "")
                if d.get("state") == "device" and (
                    ser.rpartition(":")[0] == address or ser in mdns_serials
                ):
                    logger.info(f"Device already connected via ADB daemon: {ser}")
                    serial, mdns_endpoint = ser, mdns_serials.get(ser, "")
                    break

            # B. Otherwise connect to the advertised TLS connect port.
            if not serial:
                serial = next((s.endpoint for s in tls_services if try_connect(s.endpoint, 10.0)), None)

            if serial:
                break

            time.sleep(1.0)

        # C. No connection through mDNS: ask for the port, if the caller can.
        if not serial and port_prompt_cb:
            custom_port = port_prompt_cb(address)
            if custom_port and try_connect(f"{address}:{custom_port}", 20.0):
                serial = f"{address}:{custom_port}"

        if not serial:
            if failed_endpoint:
                problem = f"Pairing succeeded but connection to {failed_endpoint} failed: {connect_msg.rstrip('.')}."
            else:
                problem = (
                    f"Pairing succeeded with {address}, but the phone's connect port "
                    "was not announced on this network."
                )
            raise PairingError(
                f"{problem} Turn Wireless debugging off and on again on the phone and try again, "
                "or use the IP address and port shown on the phone's Wireless debugging screen "
                "(in the CLI: --wireless IP:PORT)."
            )

        # -------------------------------------------------------------------
        # Phase 4: Validate authorized device state
        # -------------------------------------------------------------------
        if progress_cb:
            progress_cb("Verifying authorized connection status...", 5)

        if mdns_endpoint:
            # adb has just listed this serial as "device". It is not host:port,
            # so the endpoint check in verify_and_get_info() would reject it.
            info = self.identity.populate(serial, state="device")
            info.endpoint = mdns_endpoint
        else:
            info = self.wireless.verify_and_get_info(serial)
        session.status = "connected"
        logger.info(f"QR Pairing complete: connected to {info.summary()}")
        return info
