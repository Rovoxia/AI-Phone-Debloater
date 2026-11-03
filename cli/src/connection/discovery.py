#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Phone-Debloater — Device Discovery
=====================================

Discovery of Android devices over the network, built entirely on the Python
standard library:

* :func:`validate_ip_address` / :func:`validate_port` / :func:`validate_endpoint`
  — security-first endpoint validation (IPv4/IPv6 via ``ipaddress``, port
  range checks, command-injection character rejection).
* :class:`MdnsDiscovery` — enumerates ADB mDNS services (pairing / connect)
  via ``adb mdns``.
* :class:`LanDiscovery` — probes the local /24 subnet for hosts listening on
  the ADB wireless port (default 5555) using a bounded thread pool.

All network operations are bounded by timeouts and never execute a shell.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

from .adb_client import _LoggerAdapter
from .exceptions import (
    ConnectionError,
    DiscoveryError,
    SecurityValidationError,
)
from .models import DiscoveredService

logger = logging.getLogger("ai_phone_debloater.connection.discovery")

# Characters that have no place in a host:port endpoint and are commonly
# abused for command injection. Rejecting them up front keeps every code path
# that consumes an endpoint safe for subprocess execution.
_FORBIDDEN_ENDPOINT_CHARS = set(" \t\n\r\v\f;|&$()<>`!\\'\"[]{}")

# Regex for splitting ``host:port`` — host may be an IPv6 literal in brackets.
_ENDPOINT_RE = re.compile(r"^(?:\[(?P<ipv6>[^\]]+)\]|(?P<host>[^:]+)):(?P<port>.+)$")


# ---------------------------------------------------------------------------
# Endpoint validation
# ---------------------------------------------------------------------------

def validate_ip_address(ip: str) -> bool:
    """Return True when ``ip`` is a syntactically valid IPv4 or IPv6 address.

    Uses :mod:`ipaddress` (stdlib) so malformed addresses such as
    ``999.999.999.999`` or ``zzzz`` are rejected without any socket activity.
    """
    if not isinstance(ip, str) or not ip.strip():
        return False
    try:
        ipaddress.ip_address(ip.strip())
        return True
    except ValueError:
        return False


def validate_port(port: int) -> bool:
    """Return True when ``port`` is an integer in the valid range 1..65535."""
    try:
        if isinstance(port, bool):
            return False
        p = int(port)
        return 1 <= p <= 65535
    except (ValueError, TypeError):
        return False


def validate_endpoint(endpoint: str) -> Tuple[str, int]:
    """Validate a ``host:port`` endpoint and return ``(host, port)``.

    Raises :class:`SecurityValidationError` when:

    * the format is not ``host:port`` (IPv6 literals must be bracketed,
      e.g. ``[::1]:5555``),
    * the host contains whitespace or command-injection characters,
    * the port is not an integer in 1..65535,
    * the IP address is not valid IPv4/IPv6.
    """
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise SecurityValidationError("endpoint must be a non-empty 'host:port' string")

    endpoint = endpoint.strip()

    if ":" not in endpoint:
        if validate_ip_address(endpoint):
            return endpoint, 5555
        raise SecurityValidationError(
            f"invalid endpoint format (expected host:port): {endpoint!r}"
        )

    match = _ENDPOINT_RE.match(endpoint)
    if not match:
        raise SecurityValidationError(
            f"invalid endpoint format (expected host:port): {endpoint!r}"
        )

    host = match.group("ipv6") or match.group("host")
    port_str = match.group("port")

    if not host or not port_str:
        raise SecurityValidationError(
            f"invalid endpoint format (expected host:port): {endpoint!r}"
        )

    # Reject whitespace and command-injection characters in the host.
    if any(ch in _FORBIDDEN_ENDPOINT_CHARS for ch in host):
        raise SecurityValidationError(
            f"endpoint host contains forbidden characters: {host!r}"
        )

    # Port must be a plain decimal integer — no signs, hex, or extras.
    if not re.fullmatch(r"\d+", port_str):
        raise SecurityValidationError(
            f"invalid port (must be an integer 1-65535): {port_str!r}"
        )
    port = int(port_str)
    if not validate_port(port):
        raise SecurityValidationError(
            f"port out of range 1-65535: {port}"
        )

    if not validate_ip_address(host):
        raise SecurityValidationError(
            f"invalid IP address: {host!r}"
        )

    return host, port


# ---------------------------------------------------------------------------
# mDNS discovery
# ---------------------------------------------------------------------------

class MdnsDiscovery:
    """Discover ADB services advertised via mDNS (wireless pairing / connect).

    Requires an :class:`~connection.adb_client.AdbClient` to issue the
    ``adb mdns`` subcommands.
    """

    def __init__(self, adb_client, logger=None, logger_obj=None) -> None:
        self.adb_client = adb_client
        raw = logger or logger_obj or logging.getLogger("ai_phone_debloater.connection.discovery")
        self._logger = _LoggerAdapter(raw)

    def check_mdns(self) -> bool:
        """Return True when the device/host ADB supports mDNS.

        Runs ``adb mdns check`` and treats a zero exit code as supported.
        """
        try:
            rc, stdout, stderr = self.adb_client.run_adb(["mdns", "check"], timeout=10.0)
        except ConnectionError as exc:
            self._logger.warning("mdns check failed: %s", exc)
            return False
        supported = rc == 0
        self._logger.debug("mdns check rc=%s supported=%s out=%r err=%r", rc, supported, stdout[:200], stderr[:200])
        return supported

    def discover_services(self) -> List[DiscoveredService]:
        """Run ``adb mdns services`` and parse the advertised services.

        Output format (one service per line)::

            <service_instance_name> <service_type> <ip>:<port>

        Example::

            Pixel 7._adb-tls-pairing._tcp 192.168.1.5:44364
            Pixel 7._adb-tls-connect._tcp 192.168.1.5:5555

        Trailing dots are stripped from ``service_type`` (e.g.
        ``_adb-tls-pairing._tcp.`` -> ``_adb-tls-pairing._tcp``).

        Returns a (possibly empty) list of :class:`DiscoveredService` objects.
        """
        try:
            rc, stdout, stderr = self.adb_client.run_adb(
                ["mdns", "services"], timeout=15.0
            )
        except ConnectionError as exc:
            raise DiscoveryError(f"mdns services query failed: {exc}") from exc

        if rc != 0:
            raise DiscoveryError(
                f"adb mdns services failed (rc={rc}): {stderr.strip() or stdout.strip()}"
            )

        services: List[DiscoveredService] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List of"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            name, service_type, endpoint = parts[0], parts[1], parts[2]
            # Strip trailing dots from the service type.
            service_type = service_type.rstrip(".")
            raw = line
            try:
                address, port_str = endpoint.rsplit(":", 1)
                port = int(port_str)
            except (ValueError, IndexError):
                address, port = endpoint, 0
            services.append(
                DiscoveredService(
                    name=name,
                    service_type=service_type,
                    address=address,
                    port=port,
                    raw=raw,
                )
            )
        self._logger.debug("discovered %d mdns service(s)", len(services))
        return services

    def get_pairing_services(self) -> List[DiscoveredService]:
        """Return discovered services where :attr:`DiscoveredService.is_pairing`
        is True (ADB-TLS pairing endpoints)."""
        return [s for s in self.discover_services() if s.is_pairing]

    def get_connect_services(self) -> List[DiscoveredService]:
        """Return discovered services where :attr:`DiscoveredService.is_connect`
        is True (ADB-TLS connect endpoints)."""
        return [s for s in self.discover_services() if s.is_connect]


# ---------------------------------------------------------------------------
# LAN discovery
# ---------------------------------------------------------------------------

class LanDiscovery:
    """Probe the local LAN for hosts running an ADB wireless daemon."""

    def __init__(self, logger=None, logger_obj=None) -> None:
        raw = logger or logger_obj or logging.getLogger("ai_phone_debloater.connection.discovery")
        self._logger = _LoggerAdapter(raw)

    def get_local_ip(self) -> str:
        """Return the host's LAN IPv4 address using a dummy UDP socket.

        Connects a throwaway UDP socket to a public address and reads the
        local bound address — no packets are actually sent. Falls back to
        ``127.0.0.1`` when the host has no routable interface.
        """
        ip = "127.0.0.1"
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Google DNS — reachable, but we never actually transmit.
            sock.connect(("8.8.8.8", 53))
            ip = sock.getsockname()[0]
        except OSError:
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except OSError:
                pass
        finally:
            sock.close()
        self._logger.debug("local LAN ip: %s", ip)
        return ip

    def _local_subnet(self) -> str:
        """Return the /24 prefix (first three octets) of the local IP."""
        local_ip = self.get_local_ip()
        octets = local_ip.split(".")
        if len(octets) != 4:
            return "192.168.1."
        return f"{octets[0]}.{octets[1]}.{octets[2]}."

    def _probe(self, ip: str, port: int, timeout: float) -> Optional[str]:
        """Attempt a TCP connect to ``ip:port``; return ``ip:port`` on success."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((ip, port))
            return f"{ip}:{port}"
        except OSError:
            return None
        finally:
            sock.close()

    def scan_lan_port(
        self,
        port: int = 5555,
        timeout: float = 0.2,
        max_workers: int = 64,
    ) -> List[str]:
        """Multithreaded TCP probe of the local /24 subnet.

        Attempts a TCP connect to ``port`` (default 5555) on every address
        in the host's /24 subnet and returns the list of ``ip:port`` strings
        for hosts that accepted the connection.

        Parameters
        ----------
        port:
            TCP port to probe (1..65535).
        timeout:
            Per-probe connect timeout in seconds.
        max_workers:
            Maximum number of concurrent probe threads.

        Returns a list of ``ip:port`` strings for responsive hosts.
        """
        if not validate_port(port):
            raise SecurityValidationError(f"invalid scan port: {port!r}")
        if timeout <= 0:
            raise SecurityValidationError("timeout must be positive")

        prefix = self._local_subnet()
        targets = [f"{prefix}{i}" for i in range(1, 255)]

        found: List[str] = []
        lock = threading.Lock()

        def _task(ip: str) -> Optional[str]:
            result = self._probe(ip, port, timeout)
            if result:
                with lock:
                    found.append(result)
                self._logger.debug("lan host responded: %s", result)
            return result

        workers = max(1, min(max_workers, len(targets)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_task, ip) for ip in targets]
            for _ in as_completed(futures):
                pass  # results are collected inside _task via the lock

        found.sort()
        self._logger.info("lan scan found %d host(s) on port %d", len(found), port)
        return found


__all__ = [
    "validate_ip_address",
    "validate_port",
    "validate_endpoint",
    "MdnsDiscovery",
    "LanDiscovery",
]
