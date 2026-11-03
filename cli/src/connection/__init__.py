#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
from .discovery import LanDiscovery, MdnsDiscovery, validate_endpoint
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
    # Manager & UI
    "ConnectionManager",
    "ConnectionUI",
    # Subsystems
    "AdbClient",
    "DeviceIdentityManager",
    "DeviceRegistry",
    "ConnectionDiagnostics",
    "UsbConnectionHandler",
    "WirelessConnectionHandler",
    "QrPairingManager",
    "MdnsDiscovery",
    "LanDiscovery",
    "validate_endpoint",
    # QR Code Utilities
    "generate_android_qr_payload",
    "generate_qr_matrix",
    "render_qr_for_terminal",
    # Exceptions
    "ConnectionError",
    "AdbNotFoundError",
    "AdbVersionError",
    "AdbServerError",
    "DeviceNotFoundError",
    "DeviceUnauthorizedError",
    "DeviceOfflineError",
    "DeviceAmbiguousError",
    "PairingError",
    "PairingTimeoutError",
    "DiscoveryError",
    "SecurityValidationError",
    "OperationCancelledError",
    # Models & Enums
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
