#!/usr/bin/env python3
"""
AI-Phone-Debloater — Connection Layer Exceptions
================================================

A flat hierarchy of exception types used throughout the connection layer
(``adb_client``, ``discovery`` and any future transport modules).

All connection-layer failures derive from :class:`ConnectionError` so callers
can catch the whole family with a single ``except`` clause while still being
able to discriminate between, say, a missing ADB binary and an
unauthorized USB device.

Hierarchy::

    ConnectionError
    ├── AdbNotFoundError
    ├── AdbVersionError
    ├── AdbServerError
    ├── DeviceNotFoundError
    ├── DeviceUnauthorizedError
    ├── DeviceOfflineError
    ├── DeviceAmbiguousError
    ├── PairingError
    │   └── PairingTimeoutError
    ├── DiscoveryError
    ├── SecurityValidationError
    └── OperationCancelledError
"""

from __future__ import annotations


class ConnectionError(Exception):
    """Base class for every failure raised by the connection layer.

    Catching this single type is sufficient to handle any connection-layer
    failure. Subclasses exist so callers can react to specific conditions
    (e.g. retry only on :class:`DeviceOfflineError`).
    """


class AdbNotFoundError(ConnectionError):
    """The ADB binary could not be located on the host filesystem.

    Raised by :class:`~connection.adb_client.AdbClient` when none of the
    discovery candidates (explicit path, environment variable, bundled
    platform-tools, system ``PATH`` or standard candidate locations) resolve
    to an existing executable.
    """


class AdbVersionError(ConnectionError):
    """The installed ADB binary is too old for the requested operation.

    Raised when ``adb version`` parses to a build number below the minimum
    required by the connection layer (wireless pairing / TLS transport
    require ADB 41+).
    """


class AdbServerError(ConnectionError):
    """The ADB server responded, but the response indicates a server-side
    failure.

    Covers ``adb`` daemon crashes, protocol errors, unexpected non-zero
    exit codes that are not clearly device-related, and subprocess failures
    such as ``OSError`` while spawning the binary.
    """


class DeviceNotFoundError(ConnectionError):
    """A serial number supplied to an operation does not match any known
    device.

    Raised when ``adb -s <serial>`` reports ``error: device not found`` or
    when the serial is absent from the ``adb devices -l`` listing.
    """


class DeviceUnauthorizedError(ConnectionError):
    """The target device rejected the connection.

    Typically reported by ``adb devices`` as state ``unauthorized``. The
    user must unlock the device and authorise the host RSA key before any
    further operation can succeed.
    """


class DeviceOfflineError(ConnectionError):
    """The target device is present but unreachable.

    Reported by ``adb devices`` as state ``offline``. Often transient —
    re-plugging the cable or waiting a few seconds may recover the device.
    """


class DeviceAmbiguousError(ConnectionError):
    """An operation was requested without a serial, but multiple devices
    are attached.

    Raised by helpers that require a single unambiguous target when the
    ``adb devices`` listing contains more than one entry.
    """


class PairingError(ConnectionError):
    """Base class for all wireless-pairing failures.

    Pairing is the two-step process of obtaining a 6-digit pairing code
    (``adb pair``) and then connecting over the wireless ADB-TLS transport
    (``adb connect``). Any failure along that path raises a
    :class:`PairingError` subclass.
    """


class PairingTimeoutError(PairingError):
    """Pairing did not complete within the allotted time window.

    Raised when the mDNS-published pairing service expires, the user does
    not confirm the prompt on device, or the polling loop exhausts its
    deadline.
    """


class DiscoveryError(ConnectionError):
    """Device/service discovery failed.

    Raised by :class:`~connection.discovery.MdnsDiscovery` and
    :class:`~connection.discovery.LanDiscovery` when no services can be
    enumerated, the ADB mDNS subsystem is unsupported, or the LAN scan
    produces no candidates.
    """


class SecurityValidationError(ConnectionError):
    """A value failed validation against the connection layer's security
    policy.

    Raised by :func:`~connection.discovery.validate_endpoint` and friends
    when an endpoint contains whitespace, control characters, shell
    metacharacters or an out-of-range port — i.e. anything that could be
    abused for command injection or socket misuse.
    """


class OperationCancelledError(ConnectionError):
    """An interactive operation was aborted by the user or by a timeout
    that is best surfaced as a cancellation rather than a hard failure.

    Used for example when a user declines a destructive debloat prompt or
    when a long-running scan is interrupted by ``SIGINT``.
    """


__all__ = [
    "AdbNotFoundError",
    "AdbServerError",
    "AdbVersionError",
    "ConnectionError",
    "DeviceAmbiguousError",
    "DeviceNotFoundError",
    "DeviceOfflineError",
    "DeviceUnauthorizedError",
    "DiscoveryError",
    "OperationCancelledError",
    "PairingError",
    "PairingTimeoutError",
    "SecurityValidationError",
]