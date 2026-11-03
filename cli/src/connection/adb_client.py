#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Phone-Debloater — ADB Client
===============================

Thin, stdlib-only wrapper around the Android Debug Bridge (``adb``) binary.
Responsibilities:

* Locate the ``adb`` executable (explicit path, environment variable,
  bundled platform-tools, system ``PATH``, standard candidate locations).
* Spawn ``adb`` safely with ``shell=False``, strict encoding handling and
  redaction of sensitive data (pairing codes / passwords) from logs.
* Manage the ADB server lifecycle (start / kill / health-check / version).
* Enumerate devices and query per-device state.

Everything returns simple tuples / dicts / strings so callers stay decoupled
from ``subprocess`` internals.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .exceptions import (
    AdbNotFoundError,
    AdbServerError,
    AdbVersionError,
    ConnectionError,
    DeviceAmbiguousError,
    DeviceNotFoundError,
)

logger = logging.getLogger("ai_phone_debloater.connection.adb_client")

# Sensitive tokens that should never appear verbatim in logs. When a command
# contains one of these (e.g. ``adb pair`` with a 6-digit code), the token
# is replaced with ``[REDACTED]`` before logging.
SENSITIVE_TOKENS: tuple = ("pair", "connect", "disconnect")


def _redact_command(cmd: List[str]) -> str:
    """Return a human-readable command string with sensitive tokens masked.

    When ``cmd`` contains 'pair', both the endpoint and the pairing code are redacted.
    When ``cmd`` contains 'connect' or 'disconnect', the endpoint is redacted.
    """
    import re
    parts: List[str] = []
    redact_count = 0
    for part in cmd:
        if part == "pair":
            parts.append(part)
            redact_count = 2  # Redact endpoint AND pairing code
            continue
        elif part in ("connect", "disconnect"):
            parts.append(part)
            redact_count = 1  # Redact endpoint
            continue

        if redact_count > 0:
            parts.append("[REDACTED]")
            redact_count -= 1
            continue

        if re.fullmatch(r"\d{6}", str(part)):
            parts.append("[REDACTED]")
            continue

        parts.append(str(part))
    return " ".join(parts)


class _LoggerAdapter:
    """Bridges logging.Logger (*args) and custom Logger (single arg) interfaces."""
    def __init__(self, target) -> None:
        self._target = target

    def _fmt(self, msg: str, *args) -> str:
        if args:
            try:
                return msg % args
            except Exception:
                return f"{msg} {' '.join(str(a) for a in args)}"
        return msg

    def info(self, msg: str, *args) -> None:
        formatted = self._fmt(msg, *args)
        if hasattr(self._target, "info"):
            try:
                self._target.info(formatted)
            except TypeError:
                pass
        elif hasattr(self._target, "verbose_log"):
            self._target.verbose_log(formatted)

    def debug(self, msg: str, *args) -> None:
        formatted = self._fmt(msg, *args)
        if hasattr(self._target, "verbose_log"):
            self._target.verbose_log(formatted)
        elif hasattr(self._target, "debug"):
            try:
                self._target.debug(formatted)
            except TypeError:
                pass

    def warning(self, msg: str, *args) -> None:
        formatted = self._fmt(msg, *args)
        if hasattr(self._target, "warn"):
            try:
                self._target.warn(formatted)
            except TypeError:
                pass
        elif hasattr(self._target, "warning"):
            try:
                self._target.warning(formatted)
            except TypeError:
                pass

    def warn(self, msg: str, *args) -> None:
        self.warning(msg, *args)

    def error(self, msg: str, *args) -> None:
        formatted = self._fmt(msg, *args)
        if hasattr(self._target, "error"):
            try:
                self._target.error(formatted)
            except TypeError:
                pass


class AdbClient:
    """Safe wrapper around the ``adb`` executable.

    Parameters
    ----------
    adb_path:
        Explicit path to the ``adb`` binary. When ``None`` the client runs
        through its discovery chain (environment variable, bundled
        platform-tools, system ``PATH``, standard candidate locations).
    timeout:
        Default command timeout in seconds. Individual calls may override.
    logger:
        Optional :class:`logging.Logger`-like object. When omitted a
        module-level logger is used.
    """

    DEFAULT_TIMEOUT: float = 30.0
    ADB_SERVER_HOST: str = "127.0.0.1"
    ADB_SERVER_PORT: int = 5037

    # Standard candidate locations for the adb binary, used when nothing
    # else resolves. Kept intentionally short — stdlib-only discovery does
    # not scan the whole filesystem.
    STANDARD_CANDIDATES: List[str] = [
        r"C:\platform-tools\adb.exe",
        r"C:\Android\platform-tools\adb.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Android\sdk\platform-tools\adb.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Android\platform-tools\adb.exe"),
        "/usr/local/bin/adb",
        "/usr/bin/adb",
        "/opt/homebrew/bin/adb",
        "/opt/android-sdk/platform-tools/adb",
    ]

    def __init__(
        self,
        adb_path: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        logger=None,
        logger_obj=None,
    ) -> None:
        self.timeout = timeout
        raw_logger = logger or logger_obj or logging.getLogger("ai_phone_debloater.connection.adb_client")
        self._logger = _LoggerAdapter(raw_logger)
        self.adb_path = self._discover_adb(adb_path)
        self._server_started: bool = False

    # ------------------------------------------------------------------
    # Path discovery
    # ------------------------------------------------------------------

    def _discover_adb(self, adb_path: Optional[str]) -> str:
        """Resolve the adb executable path through an ordered candidate chain.

        Order:

        1. Explicit ``adb_path`` argument (must exist on disk or in PATH).
        2. ``AI_PHONE_DEBLOATER_ADB_PATH`` environment variable.
        3. Bundled ``cli/tools/platform-tools/adb(.exe)`` relative to the
           project root or current working directory.
        4. System ``PATH`` via :func:`shutil.which`.
        5. Standard candidate locations (common SDK install dirs).
        """
        candidates: List[str] = []

        # 1. Explicit argument.
        if adb_path:
            candidates.append(adb_path)

        # 2. Environment variable.
        env_path = os.environ.get("AI_PHONE_DEBLOATER_ADB_PATH", "").strip()
        if env_path:
            candidates.append(env_path)

        # 3. Bundled platform-tools, relative to project root or CWD.
        project_root = Path(__file__).resolve().parent.parent.parent
        bundled = [
            str(project_root / "cli" / "tools" / "platform-tools" / "adb.exe"),
            str(project_root / "cli" / "tools" / "platform-tools" / "adb"),
            str(Path.cwd() / "cli" / "tools" / "platform-tools" / "adb.exe"),
            str(Path.cwd() / "cli" / "tools" / "platform-tools" / "adb"),
            str(Path.cwd() / "tools" / "platform-tools" / "adb.exe"),
            str(Path.cwd() / "tools" / "platform-tools" / "adb"),
            str(Path.cwd() / "platform-tools" / "adb.exe"),
            str(Path.cwd() / "platform-tools" / "adb"),
        ]
        candidates.extend(bundled)

        # 4. System PATH.
        candidates.append("adb")

        # 5. Standard candidate locations.
        candidates.extend(self.STANDARD_CANDIDATES)

        for cand in candidates:
            if not cand:
                continue
            if self._is_valid_adb(cand):
                self._logger.info("Using adb: %s", cand)
                return cand

        raise AdbNotFoundError(
            "adb executable not found. Set AI_PHONE_DEBLOATER_ADB_PATH or "
            "install Android platform-tools and add adb to your PATH."
        )

    @staticmethod
    def _is_valid_adb(path: str) -> bool:
        """True when ``path`` resolves to an existing, executable adb binary."""
        try:
            if not path:
                return False
            p = Path(path)
            if p.is_file():
                return os.name == "nt" or os.access(str(p), os.X_OK)
            resolved = shutil.which(path)
            if resolved and Path(resolved).is_file():
                return os.name == "nt" or os.access(resolved, os.X_OK)
            return False
        except (OSError, ValueError):
            return False

    # ------------------------------------------------------------------
    # Safe subprocess execution
    # ------------------------------------------------------------------

    def run_cmd(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        capture: bool = True,
        env: Optional[dict] = None,
    ) -> Tuple[int, str, str]:
        """Execute an arbitrary command list safely.

        Guarantees:

        * ``shell=False`` strictly.
        * ``stdin=subprocess.DEVNULL``.
        * ``text=True`` with ``encoding="utf-8"`` and ``errors="replace"``.
        * Timeouts terminate the process and raise :class:`AdbServerError`
          (or :class:`ConnectionError`).
        * :class:`FileNotFoundError` becomes :class:`AdbNotFoundError`.
        * :class:`OSError` becomes :class:`AdbServerError`.

        Returns ``(returncode, stdout, stderr)``.
        """
        if timeout is None:
            timeout = self.timeout

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        self._logger.debug("> %s", _redact_command(cmd))

        try:
            proc = subprocess.run(
                cmd,
                timeout=timeout,
                capture_output=capture,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=merged_env,
            )
        except subprocess.TimeoutExpired as exc:
            try:
                if exc.process is not None:
                    exc.process.terminate()
                    try:
                        exc.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        exc.process.kill()
            except Exception:
                pass
            raise AdbServerError(
                f"command timed out after {timeout}s: {_redact_command(cmd)}"
            ) from exc
        except FileNotFoundError as exc:
            raise AdbNotFoundError(
                f"executable not found: {cmd[0] if cmd else '<empty>'}"
            ) from exc
        except OSError as exc:
            raise AdbServerError(
                f"failed to execute {cmd[0] if cmd else '<empty>'}: {exc}"
            ) from exc

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        self._logger.debug(
            "< rc=%d out=%r err=%r", proc.returncode, stdout[:200], stderr[:200]
        )
        return proc.returncode, stdout, stderr

    def run_adb(
        self,
        args: List[str],
        timeout: Optional[float] = None,
        serial: Optional[str] = None,
    ) -> Tuple[int, str, str]:
        """Run ``adb [-s serial] <args...>``.

        Prepends the resolved adb binary path and an optional ``-s serial``
        selector before the supplied arguments.
        """
        cmd: List[str] = [self.adb_path]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(args)
        return self.run_cmd(cmd, timeout=timeout)

    def run_shell(
        self,
        command: str,
        timeout: Optional[float] = None,
        serial: Optional[str] = None,
    ) -> Tuple[int, str, str]:
        """Run ``adb [-s serial] shell <command>`` on the device."""
        return self.run_adb(["shell", command], timeout=timeout, serial=serial)

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def start_server(self) -> bool:
        """Start the ADB server. Returns True when the server is reachable
        afterwards."""
        self.run_adb(["start-server"])
        return self.is_server_running()

    def kill_server(self) -> bool:
        """Kill the ADB server. Returns True when no longer reachable."""
        self.run_adb(["kill-server"])
        time.sleep(0.5)
        return not self.is_server_running()

    def is_server_running(self) -> bool:
        """Check whether the ADB server is reachable on localhost:5037.

        Falls back to running ``adb start-server`` (which is a no-op when the
        server is already up) and inspecting its output / exit code.
        """
        import socket

        try:
            with socket.create_connection(
                (self.ADB_SERVER_HOST, self.ADB_SERVER_PORT), timeout=2.0
            ):
                return True
        except OSError:
            pass

        # Fallback: probe via adb itself.
        rc, _, _ = self.run_adb(["get-state"], timeout=5.0)
        return rc == 0

    def get_version(self) -> str:
        """Return the adb version string (e.g. ``1.0.41``) parsed from
        ``adb version`` output."""
        rc, stdout, stderr = self.run_adb(["version"], timeout=10.0)
        if rc != 0:
            raise AdbServerError(
                f"adb version failed (rc={rc}): {stderr.strip() or stdout.strip()}"
            )
        # Typical output:
        #   Android Debug Bridge version 1.0.41
        #   Version 33.0.3-...
        for line in stdout.splitlines():
            line = line.strip()
            if line.lower().startswith("android debug bridge version"):
                parts = line.split()
                if len(parts) >= 5:
                    return parts[4]
        # Fallback: first version-like token anywhere in output.
        import re

        match = re.search(r"(\d+\.\d+\.\d+)", stdout)
        if match:
            return match.group(1)
        raise AdbVersionError(f"could not parse adb version from output: {stdout!r}")

    def check_min_version(self, min_version: str = "1.0.41") -> None:
        """Raise :class:`AdbVersionError` when the installed adb is older than
        ``min_version``. Wireless pairing requires adb >= 1.0.41."""
        installed = self.get_version()

        def parse(ver: str) -> Tuple[int, ...]:
            return tuple(int(part) for part in ver.split(".") if part.isdigit())

        if parse(installed) < parse(min_version):
            raise AdbVersionError(
                f"adb {installed} is too old; >= {min_version} required for "
                "wireless pairing/connect operations"
            )

    # ------------------------------------------------------------------
    # Device listing
    # ------------------------------------------------------------------

    def list_devices(self) -> List[Dict[str, str]]:
        """Run ``adb devices -l`` (without ``-s``) and parse the listing.

        Returns a list of dicts with keys: ``serial``, ``state``, ``model``,
        ``device``, ``product``, ``transport_id``. Missing properties default
        to the empty string.
        """
        rc, stdout, stderr = self.run_adb(["devices", "-l"], timeout=15.0)
        if rc != 0:
            raise AdbServerError(
                f"adb devices -l failed (rc={rc}): {stderr.strip() or stdout.strip()}"
            )

        devices: List[Dict[str, str]] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices attached"):
                continue
            # Format: <serial>\t<state> <prop1>:<val1> <prop2>:<val2> ...
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            props: Dict[str, str] = {}
            for token in parts[2:]:
                if ":" in token:
                    key, _, value = token.partition(":")
                    props[key] = value
            devices.append(
                {
                    "serial": serial,
                    "state": state,
                    "model": props.get("model", ""),
                    "device": props.get("device", ""),
                    "product": props.get("product", ""),
                    "transport_id": props.get("transport_id", ""),
                }
            )
        return devices

    def get_device_state(self, serial: str) -> str:
        """Return the state string for a single serial via ``adb -s <serial>
        get-state``, falling back to the ``list_devices`` listing."""
        try:
            rc, stdout, stderr = self.run_adb(
                ["get-state"], timeout=10.0, serial=serial
            )
            if rc == 0:
                return stdout.strip()
        except (AdbNotFoundError, AdbServerError, ConnectionError):
            pass

        # Fallback: consult the full listing.
        for dev in self.list_devices():
            if dev["serial"] == serial:
                return dev["state"]

        raise DeviceNotFoundError(f"device not found: {serial}")

    def get_device_serial(self, serial: str) -> str:
        """Return the serial for a single device, raising specific errors."""
        dev = self.lookup_device(serial)
        if dev is None:
            raise DeviceNotFoundError(f"device not found: {serial}")
        return dev["serial"]

    def lookup_device(self, serial: str) -> Optional[Dict[str, str]]:
        """Search the device listing for a serial. Returns dict or None."""
        devices = self.list_devices()
        for dev in devices:
            if dev["serial"] == serial:
                return dev
        return None

    def get_device_model(self, serial: str) -> str:
        """Return the model property for a serial, empty string if not found."""
        dev = self.lookup_device(serial)
        if dev is None:
            return ""
        return dev.get("model", "")

    def resolve_serial(self) -> str:
        """Return the single attached device serial, or raise.

        Raises :class:`DeviceNotFoundError` when no device is attached and
        :class:`DeviceAmbiguousError` when more than one device is attached.
        """
        devices = self.list_devices()
        if not devices:
            raise DeviceNotFoundError("no devices attached")
        if len(devices) > 1:
            serials = ", ".join(d["serial"] for d in devices)
            raise DeviceAmbiguousError(
                f"multiple devices attached; specify -s serial: {serials}"
            )
        return devices[0]["serial"]

    def getprop(self, prop: str, serial: Optional[str] = None, timeout: Optional[float] = None) -> str:
        """Query an Android system property via `getprop <prop>`."""
        if not re.match(r"^[A-Za-z0-9._-]+$", prop):
            return ""
        try:
            rc, out, _ = self.run_shell(f"getprop {prop}", timeout=timeout or 10.0, serial=serial)
            return out.strip() if rc == 0 else ""
        except Exception:
            return ""

    def is_device_online(self, serial: str) -> bool:
        """Return True when the device reports state 'device' (authorized)."""
        try:
            return self.get_device_state(serial) == "device"
        except (DeviceNotFoundError, ConnectionError):
            return False

    def close(self) -> None:
        """Placeholder for symmetry with transport layers that hold resources.
        Does nothing here (the ADB server is a long-lived daemon we do not
        own)."""
        self._server_started = False
