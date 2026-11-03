#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Phone-Debloater — Connection User Interface
==============================================
Terminal presentation layer for device connection workflows, USB auto-detection,
QR code rendering, multiple-device disambiguation, and diagnostic reports.
Matches the existing ANSI-color palette and styling of Rovoxia Debloater.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, List, Optional

from .exceptions import (
    ConnectionError,
    DeviceAmbiguousError,
    DeviceNotFoundError,
    DeviceOfflineError,
    DeviceUnauthorizedError,
    OperationCancelledError,
    PairingError,
    PairingTimeoutError,
)
from .manager import ConnectionManager
from .models import DeviceInfo


# ANSI Color formatting matching debloat_engine.py
def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                mode.value |= 0x0004
                return kernel32.SetConsoleMode(handle, mode) != 0
        except Exception:
            pass
        return False
    return sys.stdout.isatty()


USE_COLOR = _supports_color()


def _c(text: str, code: str) -> str:
    return f"{code}{text}\033[0m" if USE_COLOR else text


def bold(text: str) -> str:
    return _c(text, "\033[1m")


def dim(text: str) -> str:
    return _c(text, "\033[2m")


def green(text: str) -> str:
    return _c(text, "\033[32m")


def yellow(text: str) -> str:
    return _c(text, "\033[33m")


def red(text: str) -> str:
    return _c(text, "\033[31m")


def cyan(text: str) -> str:
    return _c(text, "\033[36m")


def blue(text: str) -> str:
    return _c(text, "\033[34m")


def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        raise OperationCancelledError("User cancelled input.") from None


class ConnectionUI:
    """Renders interactive terminal connection screens and handles user input."""

    def __init__(self, manager: ConnectionManager) -> None:
        self.mgr = manager

    def print_banner(self, title: str) -> None:
        print()
        print(f"{blue(bold(title))}")
        print(f"  {'-' * (len(title) + 2)}")

    def print_connected_device_banner(self, device: DeviceInfo) -> None:
        """Display standardized successful connection card."""
        print()
        print(f"  {green(bold('=' * 58))}")
        print(f"  {green(bold('  DEVICE CONNECTED'))}")
        dev_name = f"{device.manufacturer} {device.model}".strip() or device.serial
        print(f"  {bold('Device:')}      {dev_name}")
        transport_str = (
            f"Wireless ({device.serial})" if device.is_wireless() else f"USB ({device.serial})"
        )
        print(f"  {bold('Connection:')}  {transport_str}")
        print(
            f"  {bold('ADB Status:')}  {green('Authorized')} (Android {device.release or '?'}, SDK {device.sdk_int or '?'})"
        )
        print(f"  {green(bold('=' * 58))}")
        print()

    def select_device_interactive(self, devices: List[DeviceInfo]) -> DeviceInfo:
        """Present interactive selection menu when multiple devices are detected."""
        print()
        print(cyan(bold("Multiple Android devices detected:")))
        for i, d in enumerate(devices, 1):
            name = f"{d.manufacturer} {d.model}".strip() or "Android Device"
            transport = "Wi-Fi" if d.is_wireless() else "USB"
            status = green("Authorized") if d.is_authorized() else yellow(d.state)
            print(f"  [{bold(str(i))}] {name:<25} ({transport}: {d.serial}) — {status}")

        while True:
            choice = ask(f"\nSelect device number (1-{len(devices)}, or 0 to cancel): ").strip()
            if choice == "0":
                raise OperationCancelledError("Device selection cancelled.")
            if choice.isdigit() and 1 <= int(choice) <= len(devices):
                selected = devices[int(choice) - 1]
                if not selected.is_authorized():
                    print(yellow(f"Device {selected.serial} is in state '{selected.state}'. Waiting for authorization..."))
                    selected = self.mgr.connect_usb(selected.serial)
                self.mgr.set_active_device(selected)
                return selected
            print(yellow(f"Invalid selection '{choice}'. Enter 1 to {len(devices)}."))

    def connection_wizard(self) -> Optional[DeviceInfo]:
        """
        Main interactive connection menu presenting the two primary connection options
        (USB and Wi-Fi QR pairing), plus diagnostics and remembered reconnection.
        """
        while True:
            # Check if an authorized device is already connected
            attached = self.mgr.get_attached_devices()
            ready_devices = [d for d in attached if d.is_authorized()]

            if len(ready_devices) == 1:
                print(f"\n  Found ready device: {bold(ready_devices[0].summary())}")
                cont = ask("  Continue with this device? [Y/n]: ").strip().lower()
                if cont in ("", "y", "yes"):
                    self.mgr.set_active_device(ready_devices[0])
                    self.print_connected_device_banner(ready_devices[0])
                    return ready_devices[0]

            if len(ready_devices) > 1:
                return self.select_device_interactive(ready_devices)

            self.print_banner("ROVOXIA DEBLOATER — DEVICE CONNECTION")
            print("  Choose your connection method:\n")
            print(f"  {bold('[1] CONNECT VIA USB')}")
            print(f"      {dim('Plug in your phone with a USB cable.')}")
            print(f"      {dim('Automatic detection and authorization.')}\n")
            print(f"  {bold('[2] CONNECT VIA WI-FI (QR Code Pairing)')}")
            print(f"      {dim('Scan QR code with phone under Wireless debugging.')}")
            print(f"      {dim('No USB cable required.')}\n")
            print(f"  {bold('[3] CONNECT VIA WI-FI (Manual IP:Port / Pairing Code)')}")
            print(f"      {dim('Manual entry for devices already on Wi-Fi.')}\n")
            print(f"  {bold('[4] RECONNECT REMEMBERED DEVICE')}")
            print(f"      {dim('Reconnect to a previously paired phone.')}\n")
            print(f"  {bold('[5] RUN CONNECTION DIAGNOSTICS')}")
            print(f"      {dim('Having trouble connecting? Inspect ADB, USB, and network.')}\n")
            print(f"  {bold('[0] EXIT')}\n")

            try:
                choice = ask("Select option: ").strip()
            except OperationCancelledError:
                return None

            try:
                if choice == "1":
                    dev = self.handle_usb_flow()
                    if dev:
                        return dev
                elif choice == "2":
                    dev = self.handle_qr_flow()
                    if dev:
                        return dev
                elif choice == "3":
                    dev = self.handle_manual_wifi_flow()
                    if dev:
                        return dev
                elif choice == "4":
                    dev = self.handle_reconnect_remembered_flow()
                    if dev:
                        return dev
                elif choice == "5":
                    self.handle_diagnostics_flow()
                elif choice == "0":
                    return None
                else:
                    print(yellow(f"Invalid option '{choice}'"))
            except (ConnectionError, DeviceNotFoundError, DeviceUnauthorizedError, PairingError) as exc:
                print(f"\n  {red('[ERR]')} {exc}")
                print(f"  {dim('Tip: Select [5] to run Connection Diagnostics for troubleshooting.')}\n")
            except OperationCancelledError:
                print(f"\n  {yellow('Operation cancelled.')}\n")

    def handle_usb_flow(self) -> DeviceInfo:
        """Execute USB connection step progress."""
        print(f"\n  {cyan('[1/3]')} Initializing ADB subsystem...")
        self.mgr.initialize()

        print(f"  {cyan('[2/3]')} Detecting connected Android USB devices...")
        dev = self.mgr.connect_usb(
            progress_cb=lambda msg: print(f"        {dim(msg)}")
        )

        print(f"  {cyan('[3/3]')} Verifying authorization state...")
        self.print_connected_device_banner(dev)
        return dev

    def handle_qr_flow(self) -> DeviceInfo:
        """Execute Wireless QR code pairing step progress."""
        print(f"\n  {cyan('[1/5]')} Initializing ADB and mDNS services...")
        self.mgr.initialize()

        print(f"  {cyan('[2/5]')} Preparing Android Wireless Debugging QR code...")
        session, qr_code_str = self.mgr.start_qr_pairing(timeout=120.0)

        print()
        print("  " + cyan(bold("=" * 50)))
        print("  " + cyan(bold("  ANDROID WIRELESS DEBUGGING QR PAIRING")))
        print("  " + cyan(bold("=" * 50)))
        print("  1. On your Android phone, open Settings -> Developer options.")
        print("  2. Turn ON 'Wireless debugging'.")
        print("  3. Tap 'Pair device with QR code' to open the camera scanner.")
        print("  4. Point your phone camera at the QR code below:")
        print()
        print(qr_code_str)
        print()
        print("  " + dim(f"Session ID: {session.session_id} | Code: {session.password}"))
        print("  " + dim("Press Ctrl+C to cancel."))
        print()

        def on_progress(msg: str, remaining: int):
            sys.stdout.write(f"\r  {cyan('[3/5]')} {msg}   ")
            sys.stdout.flush()

        def on_port_prompt(phone_ip: str) -> Optional[int]:
            print()
            print(f"\n  {green(bold('[+] Encrypted pairing confirmed with phone!'))}")
            print(f"  {yellow('Notice: Wi-Fi network did not forward mDNS connection port.')}")
            print(f"  {cyan('Look at your phone screen under Settings -> Wireless debugging:')}")
            try:
                raw_port = ask(f"  Enter the 5-digit port shown under 'IP address & Port' (e.g. 39441): ").strip()
                if ":" in raw_port:
                    raw_port = raw_port.split(":")[-1]
                if raw_port.isdigit() and 1 <= int(raw_port) <= 65535:
                    return int(raw_port)
            except Exception:
                pass
            return None

        print(f"  {cyan('[3/5]')} Waiting for phone to scan QR code...")
        try:
            device = self.mgr.execute_qr_pairing_wait(
                session, timeout=120.0, progress_cb=on_progress, port_prompt_cb=on_port_prompt
            )
            print()
            print(f"  {cyan('[4/5]')} Cryptographic pairing confirmed!")
            print(f"  {cyan('[5/5]')} Connection established and verified.")
            self.print_connected_device_banner(device)
            return device
        except KeyboardInterrupt:
            self.mgr.cancel_qr_pairing()
            print()
            raise OperationCancelledError("QR pairing cancelled by user.")
        finally:
            print()

    def handle_manual_wifi_flow(self) -> Optional[DeviceInfo]:
        """Manual IP:Port or 6-digit code flow."""
        print()
        print(bold("Wireless Debugging Options:"))
        print("  [1] Connect to IP:Port directly (already paired)")
        print("  [2] Pair with 6-digit code, then connect")
        print("  [3] Auto-discover endpoints via mDNS / LAN")
        sub = ask("\nSelect option (1/2/3, Enter to cancel): ").strip()

        if sub == "1":
            ep = ask("Enter device IP:Port (e.g. 192.168.1.100:41235): ").strip()
            if not ep:
                return None
            dev = self.mgr.connect_wifi(ep)
            self.print_connected_device_banner(dev)
            return dev

        elif sub == "2":
            pair_ep = ask("Enter Pairing IP:Port (shown under 'Pair with pairing code'): ").strip()
            code = ask("Enter 6-digit Pairing Code: ").strip()
            if not pair_ep or not code:
                return None
            ok, msg = self.mgr.pair_wireless_code(pair_ep, code)
            if not ok:
                print(red(f"Pairing failed: {msg}"))
                return None
            print(green("Pairing succeeded!"))
            conn_ep = ask("Enter Connection IP:Port (shown on main Wireless debugging screen): ").strip()
            if conn_ep:
                dev = self.mgr.connect_wifi(conn_ep)
                self.print_connected_device_banner(dev)
                return dev

        elif sub == "3":
            print(cyan("Scanning for wireless ADB services via mDNS and LAN..."))
            services = self.mgr.discover_wireless_devices()
            if not services:
                print(yellow("No wireless ADB services discovered on local network."))
                return None
            print("\nDiscovered Wireless Endpoints:")
            for idx, s in enumerate(services, 1):
                print(f"  [{idx}] {s.name} @ {s.endpoint} ({s.service_type})")
            c = ask(f"\nSelect endpoint number (1-{len(services)}): ").strip()
            if c.isdigit() and 1 <= int(c) <= len(services):
                chosen = services[int(c) - 1]
                dev = self.mgr.connect_wifi(chosen.endpoint)
                self.print_connected_device_banner(dev)
                return dev

        return None

    def handle_reconnect_remembered_flow(self) -> Optional[DeviceInfo]:
        """Display remembered devices and attempt auto-reconnect."""
        devices = self.mgr.registry.load_all()
        if not devices:
            print(yellow("\nNo remembered devices found in registry."))
            return None

        print("\nRemembered Devices:")
        for idx, d in enumerate(devices, 1):
            transport_str = f"last seen via {d.last_transport}"
            endpoint_str = f" @ {d.last_endpoint}" if d.last_endpoint else ""
            print(f"  [{idx}] {bold(d.friendly_name)} ({d.manufacturer} {d.model}) — {transport_str}{endpoint_str}")

        sel = ask("\nSelect device number to reconnect (or Enter for most recent): ").strip()
        target = None
        if not sel:
            target = devices[0]
        elif sel.isdigit() and 1 <= int(sel) <= len(devices):
            target = devices[int(sel) - 1]

        if not target:
            return None

        print(cyan(f"Attempting to rediscover and connect to {target.friendly_name}..."))
        dev = self.mgr.reconnect_remembered(physical_id=target.physical_id)
        if dev:
            self.print_connected_device_banner(dev)
            return dev

        print(yellow(f"Could not reconnect to {target.friendly_name}. Please reconnect via USB or Wi-Fi QR."))
        return None

    def handle_diagnostics_flow(self) -> None:
        """Run diagnostics and display report with export option."""
        print(f"\n  {cyan('Running comprehensive connection diagnostics...')}")
        report = self.mgr.run_diagnostics()

        print()
        print("  " + cyan(bold("=" * 60)))
        print("  " + cyan(bold("  ROVOXIA CONNECTION DIAGNOSTICS")))
        print("  " + cyan(bold("=" * 60)))

        for item in report.items:
            if item.status == "OK":
                tag = green("[OK]")
            elif item.status == "WARN":
                tag = yellow("[WARN]")
            elif item.status == "FAIL":
                tag = red("[FAIL]")
            else:
                tag = blue("[INFO]")

            print(f"  {tag:<16} {bold(item.name)}")
            print(f"      {item.message}")
            if item.details:
                for line in item.details.splitlines():
                    print(f"      {dim(line)}")

        print()
        ok_cnt = report.summary.get('OK', 0)
        warn_cnt = report.summary.get('WARN', 0)
        fail_cnt = report.summary.get('FAIL', 0)
        info_cnt = report.summary.get('INFO', 0)
        print(f"  Summary: {green(f'OK: {ok_cnt}')} | "
              f"{yellow(f'WARN: {warn_cnt}')} | "
              f"{red(f'FAIL: {fail_cnt}')} | "
              f"{blue(f'INFO: {info_cnt}')}")
        print()

        try:
            choice = ask("  [c] Copy / Export Diagnostic Report  [Enter] Return to menu: ").strip().lower()
        except OperationCancelledError:
            print()
            return

        if choice in ("c", "copy", "export"):
            out_file = Path.home() / "AiPhoneDebloater" / f"diagnostic_report_{int(time.time())}.txt"
            try:
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(report.to_text(), encoding="utf-8")
                print(green(f"  Diagnostic report written to: {out_file}"))
            except OSError as exc:
                print(yellow(f"  Could not write diagnostic report: {exc}"))
                print("\n" + report.to_text())
        print()
