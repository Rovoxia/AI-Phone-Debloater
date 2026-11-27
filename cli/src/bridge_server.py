#!/usr/bin/env python3
"""
AI-Phone-Debloater — Local ADB Bridge Server
=============================================

Pure-Python (standard library only) HTTP bridge that exposes the engine's
ADB-based debloat operations over localhost so a web front-end can drive the
tool without any third-party dependencies.

Endpoints (API level 2; every route also answers under /api/...):
    GET  /health                                  also reports "api" and "capabilities"
    GET  /devices[?since=N&boot=ID&wait=S]        device list, "revision", "boot_id"; held (long
                                                  poll) while since/boot still match and wait > 0
    GET  /packages?serial=X[&view=disabled|installed]
    GET  /device?serial=X
    GET  /mdns                                    is adb's mDNS discovery up, and what it sees
    POST /execute       {serial, mode, action, packages}
    POST /restore       {serial, packages}
    POST /reconnect     {}                        adb reconnect offline
    POST /pair/code     {host, port, code}        Wi-Fi pairing by six-digit code, then connect
    POST /connect       {host, port}              adb connect, confirmed through the device list
    POST /pair/qr       {}                        start Wi-Fi QR pairing, returns the QR matrix
    GET  /pair/status
    POST /pair/cancel   {}

Every request must be addressed to 127.0.0.1/localhost (Host header) and, when
it carries an Origin, come from an allowed web origin (see ALLOWED_ORIGINS).
Every route except /health also needs the per-session token in X-Bridge-Token.

Every error answer is {"success": false, "error": <text>, "code": <code>} with one of:
    forbidden_host 403, origin_not_allowed 403, unsupported_media_type 415, token_required 401,
    bad_request 400, not_found 404, busy 409, adb_not_found 502, adb_timeout 504, adb_failed 502,
    pair_failed 502, connect_failed 502.
"mdns_unavailable" is not an error: GET /mdns answers 200 with it when adb's mDNS is off.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import math
import os
import re
import secrets
import select
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

# A device model or home directory in a log line must not abort a request.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# ---------------------------------------------------------------------------
# Path resolution (script lives at cli/src/bridge_server.py, or src/ when installed flat)
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent          # cli/src
PROJECT_ROOT = SCRIPT_DIR.parent.parent                # repo root
RULES_DIR = SCRIPT_DIR.parent / "rules"
CRITICAL_FILE = RULES_DIR / "critical-do-not-touch.json"

DEFAULT_PORT = 53123

def load_version() -> str:
    for cand in (PROJECT_ROOT / "VERSION", SCRIPT_DIR.parent / "VERSION", Path.cwd() / "VERSION"):
        if cand.is_file():
            try:
                val = cand.read_text(encoding="utf-8").strip()
                if val:
                    return val
            except (OSError, ValueError):
                pass
    return "1.0.0"

VERSION = load_version()
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

BACKUPS_DIR = Path.home() / "AiPhoneDebloater" / "backups"

# Package name validation (exact regex required by the bridge spec); used with fullmatch.
PACKAGE_RE = re.compile(r"^[a-zA-Z0-9._]+$")

ALLOWED_ACTIONS = ("disable", "uninstall", "enable")
ALLOWED_MODES = ("dry-run", "apply")

# Request gate. The Host check stops DNS rebinding; the Origin check stops other
# websites driving the bridge. Extra origins come from --allow-origin.
_LOOPBACK = r"(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?"
HOST_RE = re.compile(_LOOPBACK, re.IGNORECASE)
ALLOWED_ORIGINS: set[str] = {"https://debloater.rovoxia.com"}

# Per-session token, on top of the Origin check: a local process or page that is not
# the web app this bridge was started for cannot drive the phone. start_bridge
# replaces this import-time value, so a handler is never left without a token.
TOKEN_ENV = "AIPD_BRIDGE_TOKEN"
TOKEN_HEADER = "X-Bridge-Token"
TOKEN_RE = re.compile(r"[A-Za-z0-9._~-]{16,}")  # survives a header and a URL fragment unescaped
BRIDGE_TOKEN = secrets.token_urlsafe(16)

MAX_BODY_BYTES = 1024 * 1024

# Serialises device mutations (snapshot + pm calls) across request threads.
_APPLY_LOCK = threading.Lock()

# The one Wi-Fi QR pairing session. "manager" is set only while its thread waits for the phone.
PAIR_TIMEOUT = 120.0  # seconds to scan the code, as in the CLI's --qr-pair
_PAIR_LOCK = threading.Lock()
_PAIR_IDLE: dict[str, Any] = {"state": "idle", "id": None, "serial": None, "error": None,
                              "connected": False, "needs_connect_port": False, "host": None,
                              "manager": None}
_PAIR: dict[str, Any] = dict(_PAIR_IDLE)

# What /health reports, so the web app can tell this bridge from an older one without
# the device long poll and the pairing and connect routes.
API_LEVEL = 2
CAPABILITIES = ("devices.wait", "pair.code", "connect", "reconnect", "mdns", "pair.qr")

# Device list. One `adb devices -l` serves every request that arrives within
# DEVICES_FRESH_FOR seconds; a held /devices request reads it again every
# DEVICES_POLL_INTERVAL seconds, for at most DEVICES_MAX_WAIT seconds.
DEVICES_FRESH_FOR = 0.8
DEVICES_POLL_INTERVAL = 1.0
DEVICES_MAX_WAIT = 25.0

# Wi-Fi pairing by code and adb connect. Only one of these requests runs at a time.
_WIRELESS_LOCK = threading.Lock()
PAIR_CODE_RE = re.compile(r"[0-9]{6}")  # not \d, which also matches non-ASCII digits
PAIR_CODE_TIMEOUT = 30.0        # adb limits only its TCP connect (10 s), not the exchange after it
PAIR_CONNECT_WAIT = 8.0         # after pairing: how long to look for a connection
PAIR_AUTOCONNECT_GRACE = 2.0    # ... of which adb's own auto-connect gets this head start
PAIR_CONNECT_INTERVAL = 1.0
PAIR_CONNECT_TIMEOUT = 12.0     # ... and one adb connect to a port the phone has just announced
CONNECT_TIMEOUT = 35.0          # adb waits out the OS connect timeout, then 10 s for the handshake
CONNECT_CONFIRM_WAIT = 6.0      # after adb connect: how long the serial may take to reach "device"
CONNECT_CONFIRM_INTERVAL = 0.5

# Set at shutdown, so a held request answers and ends instead of sleeping on.
_STOP = threading.Event()
# Clear only while start_bridge's background `adb start-server` runs. Two adb commands that
# both find no server each try to start one, and the one that loses fails; requests that
# need adb therefore wait for this first.
ADB_WARMUP_TIMEOUT = 30.0
_ADB_READY = threading.Event()
_ADB_READY.set()

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"[bridge] {msg}", flush=True)


def load_critical_packages() -> set[str]:
    """Load the critical (Tier 4) packages that must never be disabled or uninstalled."""
    critical: set[str] = set()
    try:
        with CRITICAL_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        rules = data.get("rules") or data.get("packages") or []
        for entry in rules:
            if isinstance(entry, dict) and isinstance(entry.get("package"), str):
                critical.add(entry["package"])
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return critical


CRITICAL_PACKAGES: set[str] = load_critical_packages()


def is_valid_package(pkg: Any) -> bool:
    return isinstance(pkg, str) and bool(PACKAGE_RE.fullmatch(pkg))


def origin_allowed(origin: str) -> bool:
    # No blanket localhost trust: any local web server could otherwise drive the phone.
    return origin in ALLOWED_ORIGINS


def is_critical(pkg: str) -> bool:
    return pkg in CRITICAL_PACKAGES


def session_token() -> str:
    """Token from AIPD_BRIDGE_TOKEN (set by a launcher that also hands it to the browser), else random."""
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        return secrets.token_urlsafe(16)
    if not TOKEN_RE.fullmatch(token):
        sys.exit(f"[bridge] refusing to start: {TOKEN_ENV} must be at least 16 characters from A-Z a-z 0-9 . _ ~ -")
    return token


def safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text or "unknown")


# ---------------------------------------------------------------------------
# ADB resolution & execution (stdlib-only, mirrors the engine's discovery)
# ---------------------------------------------------------------------------

def discover_adb(explicit: str | None = None) -> str:
    """Resolve the adb executable path through an ordered candidate chain."""
    candidates: list[str] = []

    if explicit:
        candidates.append(explicit)

    env_path = os.environ.get("AI_PHONE_DEBLOATER_ADB_PATH", "").strip()
    if env_path:
        candidates.append(env_path)

    bundled = SCRIPT_DIR.parent / "tools" / "platform-tools"
    candidates.extend([str(bundled / "adb.exe"), str(bundled / "adb")])
    # PATH, one directory at a time. A bare "adb" is never used: on Windows both
    # shutil.which and CreateProcess look in the current working directory
    # first, so a planted adb.exe there would win.
    # Windows names adb.exe outright: before Python 3.12, shutil.which skips PATHEXT for a path with a directory.
    adb_name = "adb.exe" if os.name == "nt" else "adb"
    candidates.extend(os.path.join(d, adb_name) for d in os.get_exec_path())
    candidates.extend(
        [
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
    )

    for cand in candidates:
        # Only a path the user chose may be relative to the working directory.
        if not cand or (not os.path.isabs(cand) and cand not in (explicit, env_path)):
            continue
        p = Path(cand)
        try:
            if p.is_file() and (os.name == "nt" or os.access(str(p), os.X_OK)):
                return str(p)
            resolved = shutil.which(cand)
            if resolved and Path(resolved).is_file() and (os.name == "nt" or os.access(resolved, os.X_OK)):
                return resolved
        except (OSError, ValueError):
            continue

    return str(bundled / "adb")  # not found; run_adb reports this path in a clear error


class AdbError(RuntimeError):
    """adb could not do what was asked. `status` and `code` go into the error response.

    A RuntimeError, so callers that only catch RuntimeError keep working.
    """

    status = 502
    code = "adb_failed"


class AdbNotFoundError(AdbError):
    """The adb executable is missing or cannot be started."""

    code = "adb_not_found"


class AdbTimeoutError(AdbError):
    """An adb command did not finish in time."""

    status = 504
    code = "adb_timeout"


class PairFailedError(AdbError):
    """`adb pair` did not report success."""

    code = "pair_failed"


class ConnectFailedError(AdbError):
    """`adb connect` did not end with the phone in state "device"."""

    code = "connect_failed"


def failure_code(exc: BaseException) -> tuple[int, str]:
    """(HTTP status, error code) for a failed adb call; adb_failed for an error that names none."""
    if isinstance(exc, AdbError):
        return exc.status, exc.code
    return 502, "adb_failed"


def _command_text(cmd: list[str], args: list[str]) -> str:
    """The command line for an error message, with the code of `adb pair HOST:PORT CODE` masked."""
    if args[:1] == ["pair"] and len(args) > 2:
        cmd = [*cmd[:len(cmd) - len(args) + 2], "******"]
    return " ".join(cmd)


def run_adb(args: list[str], adb_path: str, serial: str | None = None,
            timeout: float = 30.0) -> tuple[int, str, str]:
    """Run `adb [-s serial] <args...>` safely (shell=False, stdin=DEVNULL).

    Raises AdbNotFoundError, AdbTimeoutError or AdbError (all RuntimeError) if adb cannot be
    run to the end; a non-zero exit status is returned, not raised.
    """
    cmd = [adb_path]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise AdbNotFoundError(f"adb executable not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired:
        # "from None": the original error text holds the full command, pairing code included.
        raise AdbTimeoutError(f"command timed out after {timeout:g}s: {_command_text(cmd, args)}") from None
    except OSError as exc:
        raise AdbNotFoundError(f"command failed: {_command_text(cmd, args)}: {exc}") from exc
    except ValueError as exc:  # a NUL byte in an argument, for one
        raise AdbError(f"command could not be run: {exc}") from None
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def adb_available(adb_path: str) -> bool:
    try:
        rc, _, _ = run_adb(["version"], adb_path, timeout=10.0)
        return rc == 0
    except RuntimeError:
        return False


def warm_adb_server(adb_path: str | None = None) -> None:
    """Start the adb server (thread body), so that no request has to pay for a cold start.

    A cold server answers only after its first USB scan, which takes seconds. Never raises:
    without adb the bridge still runs and /health reports adb_available false.
    """
    try:
        rc, out, err = run_adb(["start-server"], adb_path or discover_adb(), timeout=ADB_WARMUP_TIMEOUT)
        if rc != 0:
            _log(f"adb server did not start: {err.strip() or out.strip() or f'exit {rc}'}")
    except RuntimeError as exc:
        _log(f"adb server did not start: {exc}")
    finally:
        _ADB_READY.set()


def wait_for_adb() -> None:
    """Wait until the background `adb start-server` has ended. Call right before running adb.

    Only for requests that are about to run an adb command which needs the server; a request
    that is refused, or needs no adb, answers without waiting. The wait latches: if the
    start-up never reports back, one caller sits through the time limit and the flag is set,
    so that later requests go ahead and get adb's own answer instead of waiting again.
    """
    if not _ADB_READY.wait(ADB_WARMUP_TIMEOUT + 5):
        _ADB_READY.set()


# ---------------------------------------------------------------------------
# Device list
# ---------------------------------------------------------------------------

# Every state adb prints as one word, its own "unknown" included. "no permissions" is a
# sentence and is handled apart. A word that is not listed here is reported as "unknown" too.
DEVICE_STATES = frozenset({
    "device", "unauthorized", "authorizing", "connecting", "offline", "recovery",
    "sideload", "bootloader", "rescue", "host", "detached", "unknown",
})
_NO_PERMISSIONS = "no permissions"
_NO_PERMISSIONS_RE = re.compile(r"\sno permissions\b")
_DEVICE_FIELDS = ("product", "model", "device", "transport_id")


def device_transport(serial: str) -> str:
    """usb, wifi or emulator, read off the serial (adb prints no better field).

    wifi is an adb mDNS name or IPv4:port. A colon alone does not make a serial a network
    one: some USB serials hold colons ("00:11:22:33:44:55").
    """
    if serial.startswith("emulator-"):
        return "emulator"
    if "_adb-tls-connect._tcp" in serial or "_adb._tcp" in serial:
        return "wifi"
    host, _, port = serial.rpartition(":")
    if valid_host(host) and port_number(port):
        return "wifi"
    return "usb"


def parse_device_line(line: str) -> dict[str, str] | None:
    """One line of `adb devices [-l]` as a device entry, or None if it is not a device.

    The state is found by its known words, not as "the second word": a serial can hold
    spaces ("(no serial number)", an mDNS name ending in " (2)") and so can the state
    ("no permissions (...); see [...]"). The short form is serial<TAB>state; the long form is
    serial, spaces, state, then optional fields that end with transport_id:N.
    """
    line = line.rstrip()
    # Daemon start-up and version-mismatch notes belong on stderr; old adb mixes them in.
    if not line.strip() or line.lstrip().startswith(("*", "adb server")):
        return None

    serial, tab, rest = line.partition("\t")
    if not tab:
        no_perm = _NO_PERMISSIONS_RE.search(line)
        words = list(re.finditer(r"\S+", line))
        # From the right: nothing after the state is a bare state word, a serial may hold one.
        state_at = next((w.start() for w in reversed(words[1:]) if w.group() in DEVICE_STATES), None)
        if no_perm:
            cut = no_perm.start() + 1
        elif state_at is not None:
            cut = state_at
        elif len(words) > 1:  # a state this code does not know: take the second word
            cut = words[1].start()
        else:
            return None
        serial, rest = line[:cut], line[cut:]
    serial, rest = serial.strip(), rest.strip()
    if not serial or not rest:
        return None

    entry = {"serial": serial, "state": "unknown", "raw_state": "", "detail": "", "model": "",
             "product": "", "device": "", "transport_id": "", "transport": device_transport(serial)}
    if rest.startswith(_NO_PERMISSIONS):
        entry["state"], entry["raw_state"] = "no_permissions", _NO_PERMISSIONS
        rest = rest[len(_NO_PERMISSIONS):]
        end = rest.rfind("]")  # the sentence ends with "see [URL]"; fields may follow it
        if end >= 0:
            detail, fields = rest[:end + 1], rest[end + 1:].split()
        else:
            fields = [w for w in rest.split() if w.startswith("transport_id:")]
            detail = " ".join(w for w in rest.split() if w not in fields)
        entry["detail"] = detail.strip().lstrip(";").strip()
    else:
        raw_state, *fields = rest.split()
        entry["raw_state"] = raw_state
        if raw_state in DEVICE_STATES:
            entry["state"] = raw_state
    for field in fields:  # the unnamed device path (usb:1-1) is skipped
        key, sep, value = field.partition(":")
        if sep and key in _DEVICE_FIELDS:
            entry[key] = value
    return entry


def parse_devices(output: str) -> list[dict[str, str]]:
    """The device entries in the standard output of `adb devices [-l]`.

    Everything up to the "List of devices attached" header is noise. Output without the
    header is not a device list at all, and is reported instead of being read as devices.
    """
    lines = output.splitlines()
    header = next((i for i, line in enumerate(lines) if line.startswith("List of devices")), None)
    if header is None:
        shown = " ".join(output.split())[:200] or "no output"
        raise AdbError(f"adb devices -l printed no device list: {shown}")
    return [entry for line in lines[header + 1:] if (entry := parse_device_line(line))]


def adb_devices(adb_path: str) -> list[dict[str, str]]:
    rc, out, err = run_adb(["devices", "-l"], adb_path, timeout=15.0)
    if rc != 0:
        raise AdbError(f"adb devices -l failed: {err.strip() or out.strip() or f'exit {rc}'}")
    return parse_devices(out)


class DeviceMonitor:
    """The one reader of `adb devices -l`, shared by all request threads.

    Without it every request, and every held long poll once a second, would start its own
    adb process. Here one thread at a time reads the list and the others reuse that reading
    while it is fresh. `revision` goes up whenever the list changes; `boot_id` is new for
    each bridge process, so a revision from an earlier run never matches.
    """

    def __init__(self) -> None:
        self.boot_id = secrets.token_hex(8)
        self._lock = threading.Lock()  # held for one adb call, never while a long poll sleeps
        self._revision = 0
        self._devices: list[dict[str, str]] = []
        self._seen: tuple[Any, ...] | None = None  # the list as one comparable value; None until read
        self._error: RuntimeError | None = None    # set when the last reading failed
        self._read_at: float | None = None         # time.monotonic() of the last reading
        self._stale = False                        # set by invalidate(), cleared when a reading starts

    def invalidate(self) -> None:
        """Make the next snapshot read the list again (after a command that changes it).

        Only sets a flag, without the lock, so it never waits behind a reading in progress.
        """
        self._stale = True

    def snapshot(self, adb_path: str, max_age: float | None = None) -> tuple[list[dict[str, str]], int]:
        """Return (devices, revision); reads the list unless a reading younger than max_age exists.

        A failed reading is shared for as long, so that requests queued behind it do not each
        sit through their own adb timeout.
        """
        if max_age is None:
            max_age = DEVICES_FRESH_FOR
        with self._lock:
            if self._stale or self._read_at is None or time.monotonic() - self._read_at >= max_age:
                self._stale = False
                self._read(adb_path)
            if self._error is not None:
                kind = type(self._error) if isinstance(self._error, AdbError) else AdbError
                raise kind(str(self._error))
            return [dict(device) for device in self._devices], self._revision

    def _read(self, adb_path: str) -> None:
        try:
            devices = adb_devices(adb_path)
        except RuntimeError as exc:
            self._error = exc
        else:
            self._error = None
            seen = tuple(sorted(tuple(sorted(device.items())) for device in devices))
            if seen != self._seen:
                self._seen, self._devices = seen, devices
                self._revision += 1
        self._read_at = time.monotonic()

    def wait_for_change(self, adb_path: str, since: int, wait: float,
                        gone: Callable[[], bool] = lambda: False) -> tuple[list[dict[str, str]], int]:
        """Long poll: return once the revision differs from `since`, or after `wait` seconds.

        Runs in the request thread and sleeps outside the lock. It also ends when `gone`
        reports that the client hung up, and at shutdown.
        """
        deadline = time.monotonic() + wait
        while True:
            devices, revision = self.snapshot(adb_path)
            remaining = deadline - time.monotonic()
            if revision != since or remaining <= 0 or gone():
                return devices, revision
            if _STOP.wait(min(DEVICES_POLL_INTERVAL, remaining)):
                return devices, revision


_MONITOR = DeviceMonitor()


def await_device(adb_path: str, serial: str, seconds: float) -> str:
    """Read the device list until `serial` is in state "device"; return its last state ("" if absent)."""
    deadline = time.monotonic() + seconds
    while True:
        devices, _ = _MONITOR.snapshot(adb_path, max_age=0.0)
        state = next((d["state"] for d in devices if d["serial"] == serial), "")
        if state == "device" or time.monotonic() >= deadline or _STOP.wait(CONNECT_CONFIRM_INTERVAL):
            return state


def adb_disabled_packages(adb_path: str, serial: str) -> list[str]:
    rc, out, err = run_adb(
        ["shell", "pm", "list", "packages", "-d", "--user", "0"],
        adb_path,
        serial=serial,
        timeout=30.0,
    )
    if rc != 0:
        raise AdbError(f"pm list packages -d failed: {err.strip() or out.strip()}")
    pkgs: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkgs.append(line[len("package:"):].strip())
    return pkgs


def adb_device_props(adb_path: str, serial: str) -> dict[str, str]:
    """Read a fixed allow-list of getprop keys. Never accepts a client command."""
    keys = {
        "manufacturer": "ro.product.manufacturer",
        "model": "ro.product.model",
        "androidVersion": "ro.build.version.release",
        "sdkVersion": "ro.build.version.sdk",
    }
    props: dict[str, str] = {}
    for field, key in keys.items():
        try:
            _, out, _ = run_adb(["shell", "getprop", key], adb_path, serial=serial, timeout=10.0)
            props[field] = out.strip()
        except RuntimeError:
            props[field] = ""
    return props


def adb_packages(adb_path: str, serial: str, installed_only: bool = False) -> list[str]:
    rc, out, err = run_adb(
        ["shell", "pm", "list", "packages", *([] if installed_only else ["-u"]), "--user", "0"],
        adb_path,
        serial=serial,
        timeout=30.0,
    )
    if rc != 0:
        raise AdbError(f"pm list packages failed: {err.strip() or out.strip()}")
    pkgs: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkgs.append(line[len("package:"):].strip())
    return pkgs


def _pm_succeeded(rc: int, out: str, err: str, pkg: str = "") -> bool:
    if rc != 0:
        return False
    text = f"{out}\n{err}"
    if pkg:
        text = text.replace(pkg, "")
    return not re.search(r"(?i)failure|error:|exception|unknown package|not installed for", text)


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

def snapshot_path(model: str, ts: str | None = None) -> Path:
    ts = ts or datetime.now().strftime(TIMESTAMP_FORMAT)
    path = BACKUPS_DIR / f"snapshot_{safe_filename(model)}_{ts}.json"
    n = 1
    while path.exists():
        path = BACKUPS_DIR / f"snapshot_{safe_filename(model)}_{ts}_{n}.json"
        n += 1
    return path


def write_snapshot(model: str, packages_meta: list[dict[str, Any]], adb_path: str,
                   serial: str, targeted_pkgs: list[str]) -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime(TIMESTAMP_FORMAT)
    path = snapshot_path(model, ts)
    # A snapshot that could not read the device state is worthless for restore:
    # raise (the caller aborts) instead of recording every package as absent.
    sets = []
    for extra in ([], ["-e"]):
        rc, out, err = run_adb(["shell", "pm", "list", "packages", "--user", "0", *extra], adb_path, serial=serial)
        pkgs = {line[len("package:"):].strip() for line in out.splitlines() if line.startswith("package:")}
        if rc != 0 or not pkgs:
            raise AdbError(f"pm list packages failed: {err.strip() or out.strip() or f'exit {rc}'}")
        sets.append(pkgs)
    user0_set, enabled_set = sets
    meta_by_name: dict[str, dict[str, Any]] = {}
    for m in packages_meta or []:
        if isinstance(m, dict) and m.get("name"):
            meta_by_name[m["name"]] = m
        elif isinstance(m, str):
            meta_by_name[m] = {"name": m}
    entries = []
    for name in targeted_pkgs:
        meta = meta_by_name.get(name, {})
        entries.append({
            "name": name,
            "enabled": name in enabled_set,
            "installed_user0": name in user0_set,
            "tier": meta.get("tier", 0),
            "reason": meta.get("reason", ""),
            "source": meta.get("source", ""),
        })
    snapshot = {
        "created_at": datetime.now().isoformat(),
        "timestamp": ts,
        "device": {"serial": serial, "model": model},
        "package_count": len(entries),
        "packages": entries,
    }
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2)
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# Wi-Fi: mDNS, pairing by code, connect (plain adb calls, no connection package)
# ---------------------------------------------------------------------------

_MDNS_KINDS = (("_adb-tls-connect", "connect"), ("_adb-tls-pairing", "pairing"), ("_adb._tcp", "legacy"))
_BROADCAST = ipaddress.IPv4Address("255.255.255.255")


def valid_host(value: Any) -> str | None:
    """`value` as an IPv4 address in canonical form if a phone can have it, else None.

    Only the canonical form reaches a command line: it cannot start with "-" or hold a space.
    """
    if not isinstance(value, str):  # IPv4Address also takes an int
        return None
    try:
        address = ipaddress.IPv4Address(value)
    except ValueError:
        return None
    if address.is_unspecified or address.is_multicast or address == _BROADCAST:
        return None
    return str(address)


def valid_port(value: Any) -> int | None:
    """`value` if it is an integer from 1 to 65535 (JSON true is not), else None."""
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535:
        return value
    return None


def port_number(text: str) -> int | None:
    """The port that `text` (from adb output) spells, or None. Never raises.

    str.isdigit() alone is not enough before int(): it is true for characters such as "²"
    that int() rejects. The length limit keeps int() away from absurdly long digit strings.
    """
    if text.isascii() and text.isdigit() and len(text) <= 5:
        return valid_port(int(text))
    return None


def phone_host(*texts: Any) -> str | None:
    """The IPv4 address of the first "ip:port" among texts, else None."""
    for text in texts:
        host = valid_host(text.rpartition(":")[0]) if isinstance(text, str) else None
        if host:
            return host
    return None


def adb_mdns_available(adb_path: str) -> bool:
    """True if adb's mDNS discovery runs. `adb mdns check` exits 0 either way: its text decides."""
    _, out, err = run_adb(["mdns", "check"], adb_path, timeout=10.0)
    return "mdns daemon version" in f"{out}\n{err}"


def parse_mdns_services(output: str) -> list[dict[str, Any]]:
    """The adb services in `adb mdns services` output that have an IPv4 address.

    Lines are instance<TAB>service<TAB>ipv4:port. Split on tabs: an instance name can hold spaces.
    """
    services: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip() or line.lstrip().startswith(("List of discovered", "*", "adb server")):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            parts = line.rsplit(None, 2)  # tolerate an adb that pads with spaces
        if len(parts) < 3:
            continue
        name, service_type = "\t".join(parts[:-2]).strip(), parts[-2].strip().rstrip(".")
        host, _, port_text = parts[-1].strip().rpartition(":")
        kind = next((kind for prefix, kind in _MDNS_KINDS if service_type.startswith(prefix)), None)
        host = valid_host(host)
        port = port_number(port_text)
        if name and kind and host and port:
            services.append({"name": name, "type": service_type, "kind": kind, "host": host, "port": port})
    return services


def adb_mdns_services(adb_path: str) -> list[dict[str, Any]]:
    rc, out, err = run_adb(["mdns", "services"], adb_path, timeout=15.0)
    if rc != 0:
        raise AdbError(f"adb mdns services failed: {err.strip() or out.strip() or f'exit {rc}'}")
    return parse_mdns_services(out)


def adb_mdns(adb_path: str) -> dict[str, Any]:
    """The /mdns answer: whether adb's mDNS discovery is up and the adb services it sees."""
    if not adb_mdns_available(adb_path):
        return {"available": False, "services": [], "code": "mdns_unavailable"}
    return {"available": True, "services": adb_mdns_services(adb_path)}


def adb_pair(adb_path: str, host: str, port: int, code: str) -> str | None:
    """Run `adb pair host:port code`; return the phone's guid, or None if adb printed none.

    Success is exit status 0 and "Successfully paired to": before platform-tools 34.0.5 a
    failed pairing also exits 0, and since then every failure prints the same "protocol
    fault" line, so the message raised here is written for the user and leaves adb's out.

    The code is passed as an argument, the documented form. Without it adb asks for the code
    on standard input, which is not connected here. As an argument it is visible in this
    computer's process list while the command runs; it can be used once and only while the
    phone shows the pairing dialog. It is never put into a message or a log line.
    """
    endpoint = f"{host}:{port}"
    rc, out, err = run_adb(["pair", endpoint, code], adb_path, timeout=PAIR_CODE_TIMEOUT)
    text = f"{out}\n{err}"
    if rc != 0 or "Successfully paired to" not in text:
        raise PairFailedError(
            f"Pairing with {endpoint} did not succeed. Check that the phone still shows the "
            "\"Pair device with pairing code\" dialog, that the IP address and port are the ones in "
            "that dialog (the pairing port differs from the port on the Wireless debugging screen), "
            "that the six-digit code is the current one, and that phone and computer are on the "
            "same Wi-Fi network."
        )
    guid = re.search(r"\[guid=([^\]\s]+)\]", text)
    return guid.group(1) if guid else None


def adb_connect(adb_path: str, host: str, port: int, timeout: float | None = None) -> bool:
    """Run `adb connect host:port`; return True if adb says it was already connected.

    adb connect exits 0 whatever happens, so its output decides. Raises ConnectFailedError
    with advice on what to check, since adb's own line rarely says why. No answer in time is
    such a failure too, not an adb fault: an address that drops packets makes adb wait out
    the system's connect timeout, which is the usual way a wrong address fails.
    """
    endpoint = f"{host}:{port}"
    limit = timeout or CONNECT_TIMEOUT
    try:
        rc, out, err = run_adb(["connect", endpoint], adb_path, timeout=limit)
    except AdbTimeoutError:
        raise ConnectFailedError(
            f"No answer from {endpoint} within {limit:g} seconds. Check the IP address and the "
            "port, that phone and computer are on the same network, and that Wireless debugging "
            "is on."
        ) from None
    if rc != 0:  # only when the adb server cannot be reached
        raise AdbError(f"adb connect {endpoint} failed: {err.strip() or out.strip() or f'exit {rc}'}")
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    for line in lines:
        if line.startswith("already connected to "):
            return True
        if line.startswith("connected to "):
            return False
    said = " ".join(lines) or err.strip() or "nothing"
    if "failed to authenticate" in said:
        raise ConnectFailedError(
            f"The phone at {endpoint} did not accept this computer. Pair the phone with this "
            f"computer first, then connect again. (adb: {said})"
        )
    raise ConnectFailedError(
        f"Could not connect to {endpoint}. Check that Wireless debugging is on, that the phone is "
        "paired with this computer, that the port is the one shown under \"IP address & Port\" on "
        "the Wireless debugging screen (not the port from the pairing dialog), and that phone and "
        f"computer are on the same network. (adb: {said})"
    )


def connect_endpoint(adb_path: str, host: str, port: int, timeout: float | None = None) -> dict[str, Any]:
    """`adb connect host:port`, confirmed: the device list must show that serial in state "device"."""
    serial = f"{host}:{port}"
    already = adb_connect(adb_path, host, port, timeout)
    state = await_device(adb_path, serial, CONNECT_CONFIRM_WAIT)
    if state == "unauthorized":
        raise ConnectFailedError(
            f"adb reached {serial}, but the phone has not authorized this computer. Unlock the "
            "phone and accept the debugging prompt, or pair the phone again."
        )
    if state != "device":
        found = f"adb lists the phone as {state}" if state else "the phone is not in adb's device list"
        raise ConnectFailedError(
            f"adb reported a connection to {serial}, but {found}. Turn Wireless debugging off and "
            "on again on the phone, then connect with the port it shows afterwards."
        )
    _log(f"connected to {serial}")
    return {"connected": True, "serial": serial, "already": already}


def connect_after_pairing(adb_path: str, host: str, pair_port: int, guid: str | None) -> str | None:
    """Return the adb serial of the phone just paired once it is in state "device", else None.

    adb connects a phone it has just paired by itself when its mDNS sees the phone's connect
    service, and then lists it under the mDNS name. That gets a head start; after it, a
    connect service announced for this phone is used directly. Once adb lists the phone under
    its mDNS name in any state, its own connection is under way: an `adb connect` to ip:port
    on top of it would list the same phone a second time, so none is run and the wait goes
    on until that entry is ready or the time is up. Without mDNS and without such an entry
    nothing can happen, and None is returned at once.
    """
    mdns_up = adb_mdns_available(adb_path)
    started = time.monotonic()
    while True:
        services: list[dict[str, Any]] = []
        if mdns_up:  # this phone's connect services; the pairing port is never one of them
            services = [s for s in adb_mdns_services(adb_path)
                        if s["kind"] == "connect" and s["host"] == host and s["port"] != pair_port]
        names = {f"{s['name']}.{s['type']}" for s in services}  # how adb lists an auto-connected phone
        devices, _ = _MONITOR.snapshot(adb_path, max_age=0.0)
        auto_connecting = False  # listed under the mDNS name, but not ready yet
        for device in devices:
            serial = device["serial"]
            by_name = bool(guid and serial.startswith(guid)) or serial in names
            ip, _, port = serial.rpartition(":")
            by_address = ip == host and port_number(port) not in (None, pair_port)
            if device["state"] == "device" and (by_name or by_address):
                return serial
            auto_connecting = auto_connecting or by_name
        if not mdns_up and not auto_connecting:
            return None
        if not auto_connecting and time.monotonic() - started >= PAIR_AUTOCONNECT_GRACE:
            for service in services:
                try:
                    return connect_endpoint(adb_path, host, service["port"], PAIR_CONNECT_TIMEOUT)["serial"]
                except ConnectFailedError:
                    # Refused, or no answer in time. The port can change right after pairing, so
                    # look again, but not past the overall wait: one attempt can take a while.
                    if time.monotonic() - started >= PAIR_CONNECT_WAIT:
                        return None
        if time.monotonic() - started >= PAIR_CONNECT_WAIT or _STOP.wait(PAIR_CONNECT_INTERVAL):
            return None


def pair_by_code(adb_path: str, host: str, port: int, code: str) -> dict[str, Any]:
    """The /pair/code answer: pair, then try to connect. A failed connect is not a failed pairing."""
    guid = adb_pair(adb_path, host, port, code)
    _log(f"paired with {host}:{port}{f' ({guid})' if guid else ''}")
    serial = None
    try:
        serial = connect_after_pairing(adb_path, host, port, guid)
    except RuntimeError as exc:  # the pairing stands: the page asks for the connect port
        _log(f"paired, but the connection could not be completed: {exc}")
    return {"paired": True, "guid": guid, "connected": serial is not None, "serial": serial,
            "needs_connect_port": serial is None, "host": host}


# ---------------------------------------------------------------------------
# Wi-Fi QR pairing (Android 11+), driven by the CLI's connection package
# ---------------------------------------------------------------------------

def new_pairing_manager(adb_path: str) -> Any:
    """Return the CLI's QrPairingManager, bound to the adb this bridge resolved.

    The connection package is imported here, not at the top, so the rest of the
    bridge keeps working without it.
    """
    from connection.adb_client import AdbClient
    from connection.exceptions import AdbNotFoundError as ClientNotFoundError
    from connection.qr_pairing import QrPairingManager

    try:
        client = AdbClient(adb_path=adb_path)
    except ClientNotFoundError:
        client = None
    # AdbClient searches on its own when the path is unusable, and that search
    # tries a bare "adb" (the current directory, on Windows). Never run that one.
    if client is None or client.adb_path != adb_path:
        raise AdbNotFoundError(f"adb executable not found: {adb_path}")
    return QrPairingManager(client)


def pair_status() -> dict[str, Any]:
    with _PAIR_LOCK:
        return {key: value for key, value in _PAIR.items() if key != "manager"}


def cancel_pairing() -> None:
    """Stop the waiting session, if any. Its thread ends within a poll or one adb call."""
    with _PAIR_LOCK:
        if _PAIR["manager"] is not None:
            _PAIR["manager"].cancel()
            _PAIR.update(_PAIR_IDLE)


def _pair_worker(manager: Any, session: Any) -> None:
    """Thread body: wait for the scan, pair, connect, then record the outcome."""
    from connection.exceptions import ConnectionError as AdbConnectionError
    from connection.exceptions import OperationCancelledError, PairingTimeoutError

    unconnected: list[str] = []  # the phone's address, once it is paired but could not be connected

    def note_missing_port(address: str) -> None:
        # The flow calls this when the phone is paired and no connect port led to a connection.
        # The CLI asks the user for the port here; the web app asks on its own page and then
        # calls /connect, so this only records that the point was reached.
        unconnected.append(address)

    outcome: dict[str, Any] = {"state": "failed", "error": "pairing stopped unexpectedly"}
    try:
        info = manager.execute_qr_pairing_flow(session=session, timeout=PAIR_TIMEOUT,
                                               port_prompt_cb=note_missing_port)
        outcome = {"state": "paired", "serial": info.serial, "connected": True,
                   "host": phone_host(getattr(info, "endpoint", ""), info.serial)}
    except PairingTimeoutError as exc:
        outcome = {"state": "expired", "error": str(exc)}
    except OperationCancelledError:
        outcome = {"state": "idle", "id": None}
    except (AdbConnectionError, OSError, RuntimeError, ValueError) as exc:
        if unconnected:
            outcome = {"state": "paired", "needs_connect_port": True, "host": valid_host(unconnected[0])}
        else:
            outcome = {"state": "failed", "error": str(exc)}
    finally:  # whatever happened, the session must leave "waiting"
        with _PAIR_LOCK:
            current = _PAIR["manager"] is manager  # else cancelled meanwhile: that state stands
            if current:
                # First, so that a page which sees the outcome and asks for the device list
                # at once gets a fresh reading, not one from before the phone connected.
                _MONITOR.invalidate()
                _PAIR.update({**_PAIR_IDLE, "id": _PAIR["id"], **outcome})
        if current:
            # The outcome holds no secret: adb never echoes the pairing password.
            detail = outcome.get("serial") or outcome.get("error") or ""
            if outcome.get("needs_connect_port"):
                detail = f"connect port needed for {outcome.get('host') or 'the phone'}"
            _log(f"QR pairing {outcome['state']}: {detail}")


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "AI-Phone-DebloaterBridge/1.0"

    _origin: str | None = None  # validated Origin of the current request, set by _gate

    def log_request(self, code: Any = "-", size: Any = "-") -> None:
        # Keep the bridge quiet; only log error responses to stderr.
        if isinstance(code, int) and code >= 400:
            super().log_request(code, size)

    # -- request plumbing ---------------------------------------------------

    def _gate(self) -> bool:
        """Reject (and answer) requests that fail the Host/Origin/Content-Type checks."""
        self._origin = None
        origin = self.headers.get("Origin")
        if not HOST_RE.fullmatch(self.headers.get("Host") or ""):
            self._send_error(403, "forbidden_host", "forbidden Host header")
            return False
        if origin is not None and not origin_allowed(origin):
            self._send_error(403, "origin_not_allowed", "origin not allowed (see --allow-origin)")
            return False
        self._origin = origin
        if self.command == "POST" and self.headers.get_content_type() != "application/json":
            self._send_error(415, "unsupported_media_type", "Content-Type must be application/json")
            return False
        return True

    def _token_ok(self) -> bool:
        """Reject (and answer) a request that does not carry the session token. Call after _gate."""
        supplied = self.headers.get(TOKEN_HEADER) or ""
        # Bytes: compare_digest raises on a non-ASCII str, and a header may hold one.
        if hmac.compare_digest(supplied.encode("utf-8"), BRIDGE_TOKEN.encode("utf-8")):
            return True
        self._send_error(401, "token_required",
                         f"missing or wrong {TOKEN_HEADER} header (open the URL the bridge printed)")
        return False

    def _send_cors(self) -> None:
        if self._origin:
            self.send_header("Access-Control-Allow-Origin", self._origin)
        self.send_header("Vary", "Origin")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors()
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # The client left (closed tab, aborted fetch, often during a held /devices
            # request). There is nobody to answer, and it is not worth a traceback.
            self.close_connection = True

    def _send_error(self, status: int, code: str, message: str) -> None:
        """Answer with an error: the text for people, the code for the web app to branch on."""
        self._send_json(status, {"success": False, "error": message, "code": code})

    def _send_failure(self, exc: BaseException, prefix: str = "") -> None:
        """Answer with the status and code that a failed adb call carries."""
        status, code = failure_code(exc)
        self._send_error(status, code, f"{prefix}{exc}")

    def _client_gone(self) -> bool:
        """True once the client has closed the connection of a request that is being held."""
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            return bool(readable) and self.connection.recv(1, socket.MSG_PEEK) == b""
        except (OSError, ValueError):
            return True

    def _read_body(self) -> bytes | None:
        """Read the request body, or None if it is missing or oversized.

        Called before any rejection: closing a socket that still holds unread data
        can reset the connection, and the client would then never see the status.
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        return self.rfile.read(length) if 0 < length <= MAX_BODY_BYTES else None

    @staticmethod
    def _parse_body(raw: bytes | None) -> dict[str, Any] | None:
        """Return the JSON object in raw, or None if it is missing or not an object."""
        try:
            body = json.loads(raw) if raw else None
        except (ValueError, RecursionError):
            return None
        return body if isinstance(body, dict) else None

    # -- routing -----------------------------------------------------------

    def do_OPTIONS(self) -> None:
        if not self._gate():
            return
        self.send_response(204)
        self._send_cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", f"Content-Type, Authorization, X-Requested-With, {TOKEN_HEADER}")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._gate():
            return
        try:
            url = urlsplit(self.path)
        except ValueError:
            self._send_error(400, "bad_request", "invalid request path")
            return
        path = url.path.rstrip("/")
        params = dict(parse_qsl(url.query))
        is_health = path in ("/health", "/api/health")
        # /health stays open so the web app can tell "not running" from "token needed".
        if not is_health and not self._token_ok():
            return

        adb_path = discover_adb()

        if is_health:  # answers during the adb warm-up too: `adb version` needs no server
            self._send_json(200, {
                "status": "ok",
                "version": VERSION,
                "adb_available": adb_available(adb_path),
                "adb_path": adb_path,
                "token_required": True,
                "api": API_LEVEL,
                "capabilities": list(CAPABILITIES),
            })
        elif path in ("/devices", "/api/devices"):
            self._handle_devices(adb_path, params)
        elif path in ("/packages", "/api/packages"):
            serial = params.get("serial", "")
            if not serial:
                self._send_error(400, "bad_request", "serial query parameter is required")
                return
            wait_for_adb()
            try:
                if params.get("view") == "disabled":
                    pkgs = adb_disabled_packages(adb_path, serial)
                    self._send_json(200, {"view": "disabled", "packages": pkgs})
                elif params.get("view") == "installed":
                    pkgs = adb_packages(adb_path, serial, installed_only=True)
                    self._send_json(200, {"view": "installed", "packages": pkgs})
                else:
                    pkgs = adb_packages(adb_path, serial)
                    self._send_json(200, {"view": "all", "packages": pkgs})
            except RuntimeError as exc:
                self._send_failure(exc)
        elif path in ("/pair/status", "/api/pair/status"):
            self._send_json(200, pair_status())
        elif path in ("/device", "/api/device"):
            serial = params.get("serial", "")
            if not serial:
                self._send_error(400, "bad_request", "serial query parameter is required")
                return
            wait_for_adb()
            try:
                props = adb_device_props(adb_path, serial)
                self._send_json(200, {"serial": serial, **props})
            except RuntimeError as exc:
                self._send_failure(exc)
        elif path in ("/mdns", "/api/mdns"):
            wait_for_adb()
            try:
                self._send_json(200, adb_mdns(adb_path))
            except RuntimeError as exc:
                self._send_failure(exc)
        else:
            self._send_error(404, "not_found", "not found")

    def do_POST(self) -> None:
        raw = self._read_body()  # before _gate and _token_ok can answer; parsed only after both pass
        if not self._gate():
            return
        path = self.path.split("?", 1)[0].rstrip("/")
        if not self._token_ok():
            return
        body = self._parse_body(raw)
        if body is None:
            self._send_error(400, "bad_request", "body must be a JSON object")
            return

        if path in ("/execute", "/api/execute"):
            if body.get("mode") == "apply":
                with _APPLY_LOCK:
                    self._handle_execute(body)
            else:
                self._handle_execute(body)
        elif path in ("/restore", "/api/restore"):
            with _APPLY_LOCK:
                self._handle_restore(body)
        elif path in ("/reconnect", "/api/reconnect"):
            self._handle_reconnect()
        elif path in ("/pair/code", "/api/pair/code"):
            self._handle_pair_code(body)
        elif path in ("/connect", "/api/connect"):
            self._handle_connect(body)
        elif path in ("/pair/qr", "/api/pair/qr"):
            self._handle_pair_start()
        elif path in ("/pair/cancel", "/api/pair/cancel"):
            cancel_pairing()
            self._send_json(200, {"success": True, **pair_status()})
        else:
            self._send_error(404, "not_found", "not found")

    # -- action handlers ---------------------------------------------------

    def _handle_devices(self, adb_path: str, params: dict[str, str]) -> None:
        """Answer with the device list; hold the request while the client's revision is current.

        A client that sends the revision and boot_id it last saw, and wait > 0, gets its answer
        when the list changes or the wait runs out. Anything else is answered at once.
        """
        try:
            since: int | None = int(params.get("since", ""))
        except ValueError:
            since = None
        try:
            wait = float(params.get("wait", "") or 0)
        except ValueError:
            wait = 0.0
        wait = 0.0 if math.isnan(wait) else min(max(wait, 0.0), DEVICES_MAX_WAIT)
        monitor = _MONITOR
        wait_for_adb()
        try:
            if since is not None and wait > 0 and params.get("boot") == monitor.boot_id:
                devices, revision = monitor.wait_for_change(adb_path, since, wait, self._client_gone)
            else:
                devices, revision = monitor.snapshot(adb_path)
        except RuntimeError as exc:
            self._send_failure(exc)
            return
        self._send_json(200, {"devices": devices, "revision": revision, "boot_id": monitor.boot_id})

    def _handle_reconnect(self) -> None:
        """`adb reconnect offline`: resets offline and unauthorized transports, not the adb server."""
        wait_for_adb()
        try:
            rc, out, err = run_adb(["reconnect", "offline"], discover_adb(), timeout=15.0)
            if rc != 0:
                raise AdbError(f"adb reconnect offline failed: {err.strip() or out.strip() or f'exit {rc}'}")
        except RuntimeError as exc:
            self._send_failure(exc)
            return
        _MONITOR.invalidate()
        self._send_json(200, {"success": True})

    def _endpoint(self, body: dict[str, Any]) -> tuple[str, int] | None:
        """Return the validated (host, port) of a pairing or connect request, or answer 400."""
        host, port = valid_host(body.get("host")), valid_port(body.get("port"))
        if host is None:
            self._send_error(400, "bad_request", "host must be the phone's IPv4 address, for example 192.168.1.20")
        elif port is None:
            self._send_error(400, "bad_request", "port must be an integer from 1 to 65535")
        else:
            return host, port
        return None

    def _wireless(self, action: Callable[[], dict[str, Any]]) -> None:
        """Run one pairing or connect action at a time and answer with its result or its error."""
        if not _WIRELESS_LOCK.acquire(blocking=False):
            self._send_error(409, "busy", "another pairing or connect request is still running; wait for it to finish")
            return
        failure: RuntimeError | None = None
        result: dict[str, Any] = {}
        try:
            wait_for_adb()
            result = action()
        except RuntimeError as exc:
            failure = exc
        finally:
            _WIRELESS_LOCK.release()
        _MONITOR.invalidate()
        if failure is not None:
            # The first sentence is enough for the console; neither it nor the rest holds the code.
            _log(f"{self.path.split('?', 1)[0]} failed ({failure_code(failure)[1]}): {str(failure).split('. ')[0]}")
            self._send_failure(failure)
        else:
            self._send_json(200, {"success": True, **result})

    def _handle_pair_code(self, body: dict[str, Any]) -> None:
        """Pair over Wi-Fi with the six-digit code from the phone, then try to connect.

        The code goes to adb and nowhere else: not into a log line, not into an answer.
        """
        endpoint = self._endpoint(body)
        if endpoint is None:
            return
        code = body.get("code")
        if not isinstance(code, str) or not PAIR_CODE_RE.fullmatch(code):
            self._send_error(400, "bad_request", "code must be a string of exactly 6 digits")
            return
        self._wireless(lambda: pair_by_code(discover_adb(), *endpoint, code))

    def _handle_connect(self, body: dict[str, Any]) -> None:
        """`adb connect` to the address and connect port shown on the Wireless debugging screen."""
        endpoint = self._endpoint(body)
        if endpoint is not None:
            self._wireless(lambda: connect_endpoint(discover_adb(), *endpoint))

    def _handle_execute(self, body: dict[str, Any]) -> None:
        serial = body.get("serial", "")
        mode = body.get("mode", "")
        action = body.get("action", "")
        packages = body.get("packages", [])

        if not serial or not isinstance(serial, str):
            self._send_error(400, "bad_request", "serial is required (string)")
            return
        if mode not in ALLOWED_MODES:
            self._send_error(400, "bad_request", f"mode must be one of {ALLOWED_MODES}")
            return
        if action not in ALLOWED_ACTIONS:
            self._send_error(400, "bad_request", f"action must be one of {ALLOWED_ACTIONS}")
            return
        if not isinstance(packages, list) or not all(isinstance(p, str) for p in packages):
            self._send_error(400, "bad_request", "packages must be a list of strings")
            return

        adb_path = discover_adb()
        results: list[dict[str, str]] = []
        planned: list[str] = []

        # Partition packages: critical (protected) vs actionable.
        # Enabling a critical package is recovery, so only disable/uninstall are blocked.
        actionable: list[str] = []
        seen: set[str] = set()
        for pkg in packages:
            if pkg in seen:
                continue
            seen.add(pkg)
            if not is_valid_package(pkg):
                results.append({"package": str(pkg), "status": "failed", "output": "invalid package name"})
                continue
            if action != "enable" and is_critical(pkg):
                results.append({"package": pkg, "status": "skipped_protected", "output": "critical package, protected"})
                _log(f"skipped protected package: {pkg}")
                continue
            actionable.append(pkg)

        if mode == "dry-run":
            for pkg in actionable:
                if action == "disable":
                    cmd = f"adb -s {serial} shell pm disable-user --user 0 {pkg}"
                elif action == "uninstall":
                    cmd = f"adb -s {serial} shell pm uninstall -k --user 0 {pkg}"
                else:
                    cmd = f"adb -s {serial} shell pm enable --user 0 {pkg}"
                planned.append(cmd)
                results.append({"package": pkg, "status": "success", "output": "dry-run (planned)"})
            self._send_json(200, {
                "success": True,
                "mode": "dry-run",
                "action": action,
                "planned": planned,
                "results": results,
            })
            return

        # ---- apply mode --------------------------------------------------
        wait_for_adb()  # a dry run above needs no adb and never waits
        # Pre-mutation snapshot.
        model = "unknown"
        try:
            _, out, _ = run_adb(["shell", "getprop", "ro.product.model"], adb_path, serial=serial, timeout=10.0)
            if out.strip():
                model = out.strip()
        except RuntimeError:
            pass

        try:
            snap = write_snapshot(model, [], adb_path, serial, actionable)
            _log(f"snapshot written: {snap}")
        except (OSError, RuntimeError) as exc:
            _log(f"snapshot failed, nothing changed: {exc}")
            # No code of its own exists for this answer: an adb failure keeps its code, and a
            # snapshot file that cannot be written is reported as adb_failed too.
            self._send_error(500, failure_code(exc)[1], f"snapshot failed, aborting: {exc}")
            return

        for pkg in actionable:
            if action == "disable":
                shell_cmd = f"pm disable-user --user 0 {pkg}"
            elif action == "uninstall":
                shell_cmd = f"pm uninstall -k --user 0 {pkg}"
            else:
                shell_cmd = f"pm enable --user 0 {pkg}"
            try:
                rc, out, err = run_adb(["shell", shell_cmd], adb_path, serial=serial)
                if _pm_succeeded(rc, out, err, pkg):
                    results.append({"package": pkg, "status": "success", "output": (out or err or "").strip()})
                    _log(f"{action} ok: {pkg}")
                else:
                    results.append({"package": pkg, "status": "failed", "output": (err.strip() or out.strip() or f"exit {rc}")})
                    _log(f"{action} failed: {pkg}: {err.strip() or out.strip()}")
            except RuntimeError as exc:
                results.append({"package": pkg, "status": "failed", "output": str(exc)})
                _log(f"{action} error: {pkg}: {exc}")

        self._send_json(200, {"success": True, "mode": "apply", "action": action, "results": results})

    def _handle_restore(self, body: dict[str, Any]) -> None:
        serial = body.get("serial", "")
        packages = body.get("packages", [])
        if not serial or not isinstance(serial, str):
            self._send_error(400, "bad_request", "serial is required (string)")
            return
        if not isinstance(packages, list) or not all(isinstance(p, str) for p in packages):
            self._send_error(400, "bad_request", "packages must be a list of strings")
            return

        adb_path = discover_adb()
        results: list[dict[str, str]] = []
        for pkg in packages:
            if not is_valid_package(pkg):
                results.append({"package": str(pkg), "status": "failed", "output": "invalid package name"})
                continue
            # No critical guard: reinstalling a package for user 0 is recovery.
            shell_cmd = f"cmd package install-existing --user 0 {pkg}"
            wait_for_adb()  # returns at once after the first time
            try:
                rc, out, err = run_adb(["shell", shell_cmd], adb_path, serial=serial, timeout=30.0)
                if _pm_succeeded(rc, out, err, pkg):
                    results.append({"package": pkg, "status": "success", "output": (out or err or "").strip()})
                else:
                    # Fallback to pm install-existing on older Android releases.
                    rc2, out2, err2 = run_adb(["shell", f"pm install-existing --user 0 {pkg}"], adb_path, serial=serial, timeout=30.0)
                    if _pm_succeeded(rc2, out2, err2, pkg):
                        results.append({"package": pkg, "status": "success", "output": (out2 or err2 or "").strip()})
                    else:
                        results.append({"package": pkg, "status": "failed", "output": (err2.strip() or out2.strip() or f"exit {rc2}")})
            except RuntimeError as exc:
                results.append({"package": pkg, "status": "failed", "output": str(exc)})
        self._send_json(200, {"success": True, "results": results})

    def _handle_pair_start(self) -> None:
        """Start the one QR pairing session in a daemon thread and answer with its QR matrix.

        The matrix encodes the pairing password: it goes only into this response, never a log.
        """
        with _PAIR_LOCK:
            busy = _PAIR["manager"] is not None
        if not busy:
            # The session's thread runs adb at once. Waiting happens outside _PAIR_LOCK, so
            # that /pair/status and /pair/cancel still answer; a refused start does not wait.
            wait_for_adb()
        with _PAIR_LOCK:
            running = _PAIR["manager"] is not None
            error = ""
            code = "pair_failed"  # unless adb itself is the reason
            if not running:
                try:
                    from connection.qr_generator import generate_qr_matrix

                    manager = new_pairing_manager(discover_adb())
                    session = manager.create_pairing_session(ttl_seconds=PAIR_TIMEOUT)
                    matrix = [[int(cell) for cell in row] for row in generate_qr_matrix(session.qr_payload)]
                except (ImportError, OSError, RuntimeError, ValueError) as exc:  # no connection package, no adb
                    error = str(exc) or type(exc).__name__
                    if isinstance(exc, AdbError):
                        code = exc.code
                else:
                    _PAIR.update({**_PAIR_IDLE, "state": "waiting", "id": session.session_id, "manager": manager})
                    threading.Thread(target=_pair_worker, args=(manager, session), daemon=True).start()
        if running:
            self._send_error(409, "busy", "a pairing session is already running; cancel it first")
        elif error:
            _log(f"QR pairing could not start: {error}")
            self._send_error(502, code, f"QR pairing could not start: {error}")
        else:
            _log("QR pairing started: waiting for the phone to scan the code")
            self._send_json(200, {"success": True, "state": "waiting", "id": session.session_id,
                                  "matrix": matrix, "timeout": int(PAIR_TIMEOUT)})


# ---------------------------------------------------------------------------
# Server & Lifecycle
# ---------------------------------------------------------------------------

class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with immediate address reuse (POSIX only)."""

    # On Windows SO_REUSEADDR would let a second bridge bind the same port.
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def start_bridge(port: int = DEFAULT_PORT, allow_origins: tuple[str, ...] | list[str] = ()) -> None:
    """Start the bridge on 127.0.0.1:``port``; exits non-zero if it cannot start safely."""
    if not CRITICAL_PACKAGES:
        sys.exit(f"[bridge] refusing to start: no critical packages loaded from {CRITICAL_FILE}")
    ALLOWED_ORIGINS.update(o.rstrip("/") for o in allow_origins)
    global BRIDGE_TOKEN
    BRIDGE_TOKEN = session_token()
    try:
        httpd = ReusableThreadingHTTPServer(("127.0.0.1", port), BridgeHandler)
    except (OSError, OverflowError) as err:
        sys.exit(f"[bridge] port {port} in use — is the bridge already running? ({err})")

    _log(f"AI-Phone-Debloater Local ADB Bridge running at http://127.0.0.1:{port} (v{VERSION})")
    # The token rides in the fragment, which browsers never send to a server or a proxy log.
    _log("Open this URL to connect (it carries this session's token, so do not share it):")
    for origin in sorted(ALLOWED_ORIGINS):
        _log(f"  {origin}/app?bridge=1#token={BRIDGE_TOKEN}")

    # The port is bound and announced; now start the adb server without making anyone wait
    # for it. Requests that need adb queue behind this (_ADB_READY), /health does not.
    _STOP.clear()
    _ADB_READY.clear()
    try:
        threading.Thread(target=warm_adb_server, name="adb-start-server", daemon=True).start()
    except RuntimeError:  # no thread to spare: the first adb command starts the server instead
        _ADB_READY.set()

    stop_event = threading.Event()

    def handle_signal(sig_num: int, _frame: Any) -> None:
        if not stop_event.is_set():
            stop_event.set()
            _STOP.set()  # held /devices requests answer now; their threads are daemons anyway
            _log(f"Received signal {sig_num}, shutting down bridge server...")
            threading.Thread(target=httpd.shutdown, daemon=True).start()

    # Register POSIX & Windows termination signals
    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is not None:
            try:
                signal.signal(sig, handle_signal)
            except (ValueError, OSError):
                pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _log("KeyboardInterrupt received, stopping...")
    finally:
        _STOP.set()
        httpd.server_close()
        _log("bridge server stopped")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="AI-Phone-Debloater Local ADB Bridge HTTP Server")
    parser.add_argument("--port", "-p", type=int, default=DEFAULT_PORT, help=f"HTTP server port (default: {DEFAULT_PORT})")
    parser.add_argument("--allow-origin", action="append", default=[], metavar="URL",
                        help="Extra web origin allowed to call the bridge, e.g. https://my-fork.example (repeatable)")
    parser.add_argument("--strict-port", action="store_true", help=argparse.SUPPRESS)  # no-op, kept for old launch scripts
    parser.add_argument("--version", "-v", action="version", version=f"AI-Phone-Debloater Bridge Server v{VERSION}")
    args = parser.parse_args()

    try:
        start_bridge(port=args.port, allow_origins=args.allow_origin)
        return 0
    except (OSError, RuntimeError) as exc:
        _log(f"Server error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
