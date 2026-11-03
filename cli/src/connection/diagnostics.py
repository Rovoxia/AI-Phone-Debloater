#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Phone-Debloater — Comprehensive Connection Diagnostics Engine
================================================================
Independently inspects ADB binaries, server daemon health, USB driver & authorization,
network interfaces, mDNS services, and potential AP isolation or VPN interference.
Generates user-friendly summary banners and exportable technical reports.
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from .adb_client import AdbClient
from .discovery import MdnsDiscovery, LanDiscovery
from .models import DiagnosticItem, DiagnosticReport

logger = logging.getLogger("rovoxia.connection.diagnostics")


class ConnectionDiagnostics:
    """Runs end-to-end diagnostic checks on all connection subsystems."""

    def __init__(
        self,
        adb_client: AdbClient,
        mdns_discovery: Optional[MdnsDiscovery] = None,
        lan_discovery: Optional[LanDiscovery] = None,
    ) -> None:
        self.adb = adb_client
        self.mdns = mdns_discovery or MdnsDiscovery(adb_client)
        self.lan = lan_discovery or LanDiscovery()

    def run_all(self) -> DiagnosticReport:
        """Run all diagnostic suites and aggregate the results into a report."""
        items: List[DiagnosticItem] = []
        logs: List[str] = []

        def log(msg: str):
            logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

        log("Starting comprehensive connection diagnostics...")

        # 1. ADB Core Diagnostics
        self._check_adb_binary(items, log)
        self._check_adb_server(items, log)

        # 2. USB Transport Diagnostics
        self._check_usb_subsystem(items, log)

        # 3. Wireless & Network Diagnostics
        self._check_network_and_wireless(items, log)

        # Summarize
        summary = {"OK": 0, "WARN": 0, "FAIL": 0, "INFO": 0}
        for it in items:
            summary[it.status] = summary.get(it.status, 0) + 1

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        report = DiagnosticReport(
            timestamp=now_str,
            items=items,
            summary=summary,
            logs=logs,
        )
        return report

    def _check_adb_binary(self, items: List[DiagnosticItem], log: Any) -> None:
        """Check ADB executable location, accessibility, and version."""
        adb_path = getattr(self.adb, "adb_path", "")
        if not adb_path or not Path(adb_path).is_file():
            items.append(
                DiagnosticItem(
                    category="adb",
                    name="ADB Installation",
                    status="FAIL",
                    message="ADB executable not found on the system.",
                    details="Ensure Android platform-tools is installed or placed in cli/tools/platform-tools.",
                )
            )
            log("FAIL: ADB executable missing.")
            return

        items.append(
            DiagnosticItem(
                category="adb",
                name="ADB Installation",
                status="OK",
                message=f"ADB installed at: {adb_path}",
            )
        )
        log(f"OK: ADB located at {adb_path}")

        # Version check
        try:
            ver_str = self.adb.get_version()
            items.append(
                DiagnosticItem(
                    category="adb",
                    name="ADB Version",
                    status="OK",
                    message=f"ADB version {ver_str} detected.",
                )
            )
            log(f"OK: ADB version {ver_str}")
        except Exception as exc:
            items.append(
                DiagnosticItem(
                    category="adb",
                    name="ADB Version",
                    status="WARN",
                    message=f"Could not parse ADB version: {exc}",
                )
            )
            log(f"WARN: ADB version error: {exc}")

    def _check_adb_server(self, items: List[DiagnosticItem], log: Any) -> None:
        """Check if ADB server daemon is alive and listening on port 5037."""
        running = self.adb.is_server_running()
        if running:
            items.append(
                DiagnosticItem(
                    category="adb",
                    name="ADB Server Daemon",
                    status="OK",
                    message="ADB server daemon is running and communicating on port 5037.",
                )
            )
            log("OK: ADB server daemon is active on port 5037.")
        else:
            # Try to start server
            started = self.adb.start_server()
            if started and self.adb.is_server_running():
                items.append(
                    DiagnosticItem(
                        category="adb",
                        name="ADB Server Daemon",
                        status="OK",
                        message="ADB server daemon was started successfully on port 5037.",
                    )
                )
                log("OK: ADB server daemon started.")
            else:
                items.append(
                    DiagnosticItem(
                        category="adb",
                        name="ADB Server Daemon",
                        status="FAIL",
                        message="ADB server is not responding on port 5037.",
                        details="Another program may be blocking port 5037, or antivirus/security software is blocking adb.exe.",
                    )
                )
                log("FAIL: ADB server could not be started.")

        # Check competing processes if on Windows
        if platform.system() == "Windows":
            try:
                out = subprocess.check_output(
                    ["tasklist", "/FI", "IMAGENAME eq adb.exe"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                count = out.count("adb.exe")
                if count > 1:
                    items.append(
                        DiagnosticItem(
                            category="adb",
                            name="Competing Processes",
                            status="WARN",
                            message=f"Detected {count} running adb.exe processes. This may cause server conflicts.",
                            details="Consider killing competing adb instances via Task Manager or adb kill-server.",
                        )
                    )
                    log(f"WARN: Multiple ({count}) adb.exe instances running.")
            except Exception:
                pass

    def _check_usb_subsystem(self, items: List[DiagnosticItem], log: Any) -> None:
        """Check USB devices, authorization status, and connectivity."""
        try:
            devices = self.adb.list_devices()
        except Exception as exc:
            items.append(
                DiagnosticItem(
                    category="usb",
                    name="Device Enumeration",
                    status="FAIL",
                    message=f"Failed to query connected devices: {exc}",
                )
            )
            log(f"FAIL: list_devices failed: {exc}")
            return

        usb_devices = [
            d for d in devices
            if ":" not in d.get("serial", "") and not d.get("serial", "").startswith("emulator-")
        ]

        if not usb_devices:
            items.append(
                DiagnosticItem(
                    category="usb",
                    name="Connected USB Devices",
                    status="INFO",
                    message="No USB Android devices detected.",
                    details=(
                        "1. Ensure your phone is connected with a USB data cable (not charge-only).\n"
                        "2. Unlock phone and enable 'USB Debugging' in Developer Options.\n"
                        "3. Verify that OEM USB drivers (Google/Samsung/etc.) are installed in Windows Device Manager."
                    ),
                )
            )
            log("INFO: 0 USB devices attached.")
            return

        ready_count = 0
        unauthorized_count = 0
        offline_count = 0

        for dev in usb_devices:
            serial = dev["serial"]
            state = dev.get("state", "unknown").lower()
            model = dev.get("model", "")
            dev_label = f"{model} ({serial})" if model else serial

            if state == "device":
                ready_count += 1
                items.append(
                    DiagnosticItem(
                        category="usb",
                        name=f"Device {serial}",
                        status="OK",
                        message=f"Device {dev_label} is authorized and ready for debloating.",
                    )
                )
                log(f"OK: USB device {dev_label} ready.")
            elif state == "unauthorized":
                unauthorized_count += 1
                items.append(
                    DiagnosticItem(
                        category="usb",
                        name=f"Device {serial}",
                        status="WARN",
                        message=f"Device {dev_label} is UNAUTHORIZED (RSA fingerprint prompt pending).",
                        details="Unlock your phone screen and tap 'Allow' on the 'Allow USB debugging?' dialog.",
                    )
                )
                log(f"WARN: USB device {dev_label} unauthorized.")
            elif state == "offline":
                offline_count += 1
                items.append(
                    DiagnosticItem(
                        category="usb",
                        name=f"Device {serial}",
                        status="WARN",
                        message=f"Device {dev_label} is OFFLINE.",
                        details="Try disconnecting and reconnecting the USB cable, or toggle USB Debugging off and on.",
                    )
                )
                log(f"WARN: USB device {dev_label} offline.")
            else:
                items.append(
                    DiagnosticItem(
                        category="usb",
                        name=f"Device {serial}",
                        status="WARN",
                        message=f"Device {dev_label} is in non-ready state: {state}.",
                    )
                )

    def _check_network_and_wireless(self, items: List[DiagnosticItem], log: Any) -> None:
        """Check host network adapter, mDNS daemon, and visible wireless ADB services."""
        local_ip = self.lan.get_local_ip()
        if local_ip and not local_ip.startswith("127."):
            items.append(
                DiagnosticItem(
                    category="wireless",
                    name="Network Interface",
                    status="OK",
                    message=f"Local host IP interface active: {local_ip}",
                )
            )
            log(f"OK: Primary network interface IP is {local_ip}")
        else:
            items.append(
                DiagnosticItem(
                    category="wireless",
                    name="Network Interface",
                    status="FAIL",
                    message="No active non-loopback network interface detected.",
                    details="Ensure your computer is connected to Wi-Fi or Ethernet.",
                )
            )
            log("FAIL: No valid LAN IP.")
            return

        # Check mDNS capability
        mdns_supported = self.mdns.check_mdns()
        if mdns_supported:
            items.append(
                DiagnosticItem(
                    category="wireless",
                    name="ADB mDNS Discovery Service",
                    status="OK",
                    message="ADB mDNS discovery daemon is active and responsive.",
                )
            )
            log("OK: adb mdns check passed.")
        else:
            items.append(
                DiagnosticItem(
                    category="wireless",
                    name="ADB mDNS Discovery Service",
                    status="WARN",
                    message="Native ADB mDNS discovery is not reporting active.",
                    details="mDNS discovery may be disabled or blocked by Windows Firewall / security software.",
                )
            )
            log("WARN: adb mdns check reported false or inactive.")

        # Query services
        services = self.mdns.discover_services()
        pairing_services = [s for s in services if s.is_pairing]
        connect_services = [s for s in services if s.is_connect]

        if pairing_services:
            items.append(
                DiagnosticItem(
                    category="wireless",
                    name="Pairing Services Detected",
                    status="OK",
                    message=f"Detected {len(pairing_services)} active wireless pairing service(s) on LAN.",
                    details=", ".join(f"{s.name} @ {s.endpoint}" for s in pairing_services),
                )
            )
            log(f"OK: {len(pairing_services)} pairing services visible.")
        else:
            items.append(
                DiagnosticItem(
                    category="wireless",
                    name="Pairing Services",
                    status="INFO",
                    message="No active wireless pairing services detected.",
                    details="Enable 'Wireless debugging' and select 'Pair device with QR code' on your phone to broadcast pairing.",
                )
            )

        if connect_services:
            items.append(
                DiagnosticItem(
                    category="wireless",
                    name="Connection Services Detected",
                    status="OK",
                    message=f"Detected {len(connect_services)} active wireless connection service(s) on LAN.",
                    details=", ".join(f"{s.name} @ {s.endpoint}" for s in connect_services),
                )
            )
            log(f"OK: {len(connect_services)} connect services visible.")
        else:
            items.append(
                DiagnosticItem(
                    category="wireless",
                    name="Connection Services",
                    status="INFO",
                    message="No active wireless connection endpoints detected.",
                )
            )

        # Check for potential VPN or virtual adapter interference
        try:
            hostname = socket.gethostname()
            addrs = socket.gethostbyname_ex(hostname)[2]
            if len(addrs) > 2:
                items.append(
                    DiagnosticItem(
                        category="wireless",
                        name="Multiple Network Adapters",
                        status="INFO",
                        message=f"Found {len(addrs)} active IP addresses ({', '.join(addrs)}).",
                        details="If using a VPN or virtual machine (VMware/Hyper-V), it might isolate mDNS multicast packets from your phone.",
                    )
                )
                log(f"INFO: Multiple IP addresses on host: {addrs}")
        except Exception:
            pass
