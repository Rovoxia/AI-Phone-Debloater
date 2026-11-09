#!/usr/bin/env python3
"""
AI-Phone-Debloater — Centralized Connection Architecture
=========================================================
Public API surface of the production-grade Android ADB connection system.
Exposes ConnectionManager, connection handlers, models, exceptions,
diagnostics, and terminal UI.
"""

from .adb_client import AdbClient
from .device_identity import DeviceIdentityManager
from .device_registry import DeviceRegistry
from .diagnostics import ConnectionDiagnostics
from .discovery import LanDiscovery, MdnsDiscovery, validate_endpoint, validate_host
from .exceptions import (
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
from .manager import ConnectionManager
from .models import (
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
from .qr_generator import (
    generate_android_qr_payload,
    generate_qr_matrix,
    render_qr_for_terminal,
)
from .qr_pairing import QrPairingManager
from .ui import ConnectionUI
from .usb import UsbConnectionHandler
from .wireless import WirelessConnectionHandler

__all__ = [
    # Subsystems
    "AdbClient",
    "AdbNotFoundError",
    "AdbServerError",
    "AdbVersionError",
    "ConnectionDiagnostics",
    # Exceptions
    "ConnectionError",
    # Manager & UI
    "ConnectionManager",
    # Models & Enums
    "ConnectionState",
    "ConnectionUI",
    "DeviceAmbiguousError",
    "DeviceIdentityManager",
    "DeviceInfo",
    "DeviceNotFoundError",
    "DeviceOfflineError",
    "DeviceRegistry",
    "DeviceState",
    "DeviceUnauthorizedError",
    "DiagnosticItem",
    "DiagnosticReport",
    "DiscoveredService",
    "DiscoveryError",
    "LanDiscovery",
    "MdnsDiscovery",
    "OperationCancelledError",
    "PairingError",
    "PairingSession",
    "PairingTimeoutError",
    "QrPairingManager",
    "RememberedDevice",
    "SecurityValidationError",
    "TransportType",
    "UsbConnectionHandler",
    "WirelessConnectionHandler",
    # QR Code Utilities
    "generate_android_qr_payload",
    "generate_qr_matrix",
    "render_qr_for_terminal",
    "validate_endpoint",
    "validate_host",
]
