#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Phone-Debloater — Connection Layer Data Models
=================================================

Pure data structures for the ADB connection layer. All of these are built on
``enum.Enum`` and ``dataclasses.dataclass`` and contain no behaviour beyond
simple convenience methods — they are intentionally free of any external
dependency so the layer stays stdlib-only.

Usage::

    from .models import DeviceInfo, ConnectionState, DiscoveredService

    dev = DeviceInfo(serial="ABC123DEF", state="device", transport_type="usb")
    print(dev.summary())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List


class ConnectionState(Enum):
    """Lifecycle state of a single ADB transport session."""

    DISCONNECTED = "disconnected"
    INITIALIZING = "initializing"
    DISCOVERING = "discovering"
    DEVICE_FOUND = "device_found"
    WAITING_FOR_AUTHORIZATION = "waiting_for_authorization"
    PAIRING = "pairing"
    PAIRED = "paired"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    UNAUTHORIZED = "unauthorized"
    OFFLINE = "offline"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    CANCELLED = "cancelled"


class TransportType(Enum):
    """Physical/logical transport between host and device."""

    USB = "usb"
    WIRELESS = "wireless"
    EMULATOR = "emulator"
    UNKNOWN = "unknown"

    @classmethod
    def from_serial(cls, serial: str) -> "TransportType":
        if not serial:
            return cls.UNKNOWN
        s = serial.strip()
        if s.startswith("emulator-"):
            return cls.EMULATOR
        if s.startswith("usb:"):
            return cls.USB
        if ":" in s or s.count(".") == 3:
            return cls.WIRELESS
        return cls.USB


class DeviceState(Enum):
    """State reported by ``adb devices`` / ``adb get-state``."""

    DEVICE = "device"
    UNAUTHORIZED = "unauthorized"
    OFFLINE = "offline"
    RECOVERY = "recovery"
    SIDELOAD = "sideload"
    BOOTLOADER = "bootloader"
    UNKNOWN = "unknown"


@dataclass
class DeviceInfo:
    """Snapshot of a single Android device reachable via ADB."""

    serial: str
    state: str = "device"
    transport_type: str = "usb"  # "usb" or "wireless"
    manufacturer: str = ""
    model: str = ""
    release: str = ""
    sdk_int: str = ""
    security_patch: str = ""
    build_id: str = ""
    architecture: str = ""
    physical_id: str = ""
    transport_id: str = ""
    endpoint: str = ""  # "192.168.1.5:5555" if wireless
    last_seen: float = 0.0

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Short human-readable one-line description of the device."""
        transport = self.transport_type or "usb"
        endpoint = f" ({self.endpoint})" if self.endpoint else ""
        name = f"{self.manufacturer} {self.model}".strip() if self.manufacturer else (self.model or self.serial)
        return f"{self.serial} [{transport}]{endpoint} :: {name} ({self.state})"

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict of all fields."""
        return {
            "serial": self.serial,
            "state": self.state,
            "transport_type": self.transport_type,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "release": self.release,
            "sdk_int": self.sdk_int,
            "security_patch": self.security_patch,
            "build_id": self.build_id,
            "architecture": self.architecture,
            "physical_id": self.physical_id,
            "transport_id": self.transport_id,
            "endpoint": self.endpoint,
            "last_seen": self.last_seen,
        }

    def is_authorized(self) -> bool:
        """True when the device state is ``device`` (authorized)."""
        return self.state == "device"

    def is_wireless(self) -> bool:
        """True when the transport type is ``wireless``."""
        return self.transport_type == "wireless"


@dataclass
class DiscoveredService:
    """A single mDNS / LAN-discovered network service."""

    name: str
    service_type: str
    address: str
    port: int
    raw: str = ""

    @property
    def is_pairing(self) -> bool:
        """True when the service advertises an ADB-TLS pairing endpoint."""
        return "_adb-tls-pairing" in self.service_type

    @property
    def is_connect(self) -> bool:
        """True when the service advertises an ADB connect endpoint.

        Pairing services (``_adb-tls-pairing``) are excluded. Connecting to a
        pairing port with ``adb connect`` hangs: that socket only speaks the
        SPAKE2 pairing handshake.
        """
        if self.is_pairing or "_adb-tls-pairing" in self.service_type:
            return False
        st = self.service_type
        return "_adb-tls-connect" in st or st == "_adb._tcp" or st.endswith("._adb._tcp")

    @property
    def endpoint(self) -> str:
        """``address:port`` form, suitable for ``adb connect``."""
        return f"{self.address}:{self.port}"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "service_type": self.service_type,
            "address": self.address,
            "port": self.port,
            "endpoint": self.endpoint,
            "raw": self.raw,
            "is_pairing": self.is_pairing,
            "is_connect": self.is_connect,
        }


@dataclass
class PairingSession:
    """An in-flight wireless pairing session between host and device."""

    session_id: str
    service_name: str
    password: str
    qr_payload: str
    created_at: float
    expires_at: float
    status: str = "pending"

    def is_expired(self) -> bool:
        """True when the pairing session's expiry time has passed."""
        return self.expires_at > 0 and datetime.now().timestamp() > self.expires_at

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "service_name": self.service_name,
            "password": self.password,
            "qr_payload": self.qr_payload,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "is_expired": self.is_expired(),
        }


@dataclass
class DiagnosticItem:
    """A single entry in a device diagnostic report."""

    category: str
    name: str
    status: str  # "OK", "WARN", "FAIL", "INFO"
    message: str
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class DiagnosticReport:
    """A device diagnostic report produced by scanning one or more devices."""

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    items: List[DiagnosticItem] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)

    def to_text(self) -> str:
        """Render the report as a plain-text block for console/log output."""
        lines: List[str] = [
            f"Diagnostic Report — {self.timestamp}",
            "-" * 60,
        ]
        for item in self.items:
            lines.append(f"[{item.status}] {item.category}/{item.name}: {item.message}")
            if item.details:
                lines.append(f"      {item.details}")
        if self.summary:
            lines.append("")
            lines.append("Summary:")
            for key, value in sorted(self.summary.items()):
                lines.append(f"  {key}: {value}")
        if self.logs:
            lines.append("")
            lines.append("Logs:")
            for log in self.logs:
                lines.append(f"  {log}")
        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "items": [item.to_dict() for item in self.items],
            "summary": self.summary,
            "logs": self.logs,
        }


@dataclass
class RememberedDevice:
    """A previously connected device, persisted for auto-reconnect."""

    physical_id: str
    friendly_name: str
    manufacturer: str
    model: str
    last_transport: str
    last_endpoint: str
    last_connected: str
    auto_reconnect: bool = True

    def to_dict(self) -> dict:
        return {
            "physical_id": self.physical_id,
            "friendly_name": self.friendly_name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "last_transport": self.last_transport,
            "last_endpoint": self.last_endpoint,
            "last_connected": self.last_connected,
            "auto_reconnect": self.auto_reconnect,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RememberedDevice":
        """Rebuild a :class:`RememberedDevice` from a serialized dict."""
        return cls(
            physical_id=d.get("physical_id", ""),
            friendly_name=d.get("friendly_name", ""),
            manufacturer=d.get("manufacturer", ""),
            model=d.get("model", ""),
            last_transport=d.get("last_transport", ""),
            last_endpoint=d.get("last_endpoint", ""),
            last_connected=d.get("last_connected", ""),
            auto_reconnect=bool(d.get("auto_reconnect", True)),
        )


__all__ = [
    "ConnectionState",
    "TransportType",
    "DeviceState",
    "DeviceInfo",
    "DiscoveredService",
    "PairingSession",
    "DiagnosticItem",
    "DiagnosticReport",
    "RememberedDevice",
]
