#!/usr/bin/env python3
"""
AI-Phone-Debloater — Local ADB Bridge Server
=============================================

Pure-Python (standard library only) HTTP bridge that exposes the engine's
ADB-based debloat operations over localhost so a web front-end can drive the
tool without any third-party dependencies.

Endpoints:
    GET  /health        | /api/health
    GET  /devices       | /api/devices
    GET  /packages?serial=X   | /api/packages?serial=X
    GET  /packages?serial=X&view=disabled|installed
    GET  /device?serial=X | /api/device?serial=X
    POST /execute       | /api/execute   {serial, mode, action, packages}
    POST /restore       | /api/restore   {serial, packages}
    POST /pair/qr       | /api/pair/qr       {}  start Wi-Fi QR pairing, returns the QR matrix
    GET  /pair/status   | /api/pair/status
    POST /pair/cancel   | /api/pair/cancel   {}

Every request must be addressed to 127.0.0.1/localhost (Host header) and, when
it carries an Origin, come from an allowed web origin (see ALLOWED_ORIGINS).
Every route except /health also needs the per-session token in X-Bridge-Token.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
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
_PAIR: dict[str, Any] = {"state": "idle", "id": None, "serial": None, "error": None, "manager": None}

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


def run_adb(args: list[str], adb_path: str, serial: str | None = None,
            timeout: float = 30.0) -> tuple[int, str, str]:
    """Run `adb [-s serial] <args...>` safely (shell=False, stdin=DEVNULL)."""
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
        raise RuntimeError(f"adb executable not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"command timed out after {timeout}s: {' '.join(cmd)}") from exc
    except OSError as exc:
        raise RuntimeError(f"command failed: {' '.join(cmd)}: {exc}") from exc
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def adb_available(adb_path: str) -> bool:
    try:
        rc, _, _ = run_adb(["version"], adb_path, timeout=10.0)
        return rc == 0
    except RuntimeError:
        return False


def adb_devices(adb_path: str) -> list[dict[str, str]]:
    rc, out, err = run_adb(["devices", "-l"], adb_path, timeout=15.0)
    if rc != 0:
        raise RuntimeError(f"adb devices -l failed: {err.strip() or out.strip()}")
    devices: list[dict[str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        info = {"serial": parts[0], "state": parts[1], "model": "", "product": ""}
        for token in parts[2:]:
            if ":" in token:
                k, _, v = token.partition(":")
                if k == "model":
                    info["model"] = v
                elif k == "product":
                    info["product"] = v
        devices.append(info)
    return devices


def adb_disabled_packages(adb_path: str, serial: str) -> list[str]:
    rc, out, err = run_adb(
        ["shell", "pm", "list", "packages", "-d", "--user", "0"],
        adb_path,
        serial=serial,
        timeout=30.0,
    )
    if rc != 0:
        raise RuntimeError(f"pm list packages -d failed: {err.strip() or out.strip()}")
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
        raise RuntimeError(f"pm list packages failed: {err.strip() or out.strip()}")
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
            raise RuntimeError(f"pm list packages failed: {err.strip() or out.strip() or f'exit {rc}'}")
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
# Wi-Fi QR pairing (Android 11+), driven by the CLI's connection package
# ---------------------------------------------------------------------------

def new_pairing_manager(adb_path: str) -> Any:
    """Return the CLI's QrPairingManager, bound to the adb this bridge resolved.

    The connection package is imported here, not at the top, so the rest of the
    bridge keeps working without it.
    """
    from connection.adb_client import AdbClient
    from connection.exceptions import AdbNotFoundError
    from connection.qr_pairing import QrPairingManager

    try:
        client = AdbClient(adb_path=adb_path)
    except AdbNotFoundError:
        client = None
    # AdbClient searches on its own when the path is unusable, and that search
    # tries a bare "adb" (the current directory, on Windows). Never run that one.
    if client is None or client.adb_path != adb_path:
        raise RuntimeError(f"adb executable not found: {adb_path}")
    return QrPairingManager(client)


def pair_status() -> dict[str, Any]:
    with _PAIR_LOCK:
        return {key: _PAIR[key] for key in ("state", "id", "serial", "error")}


def cancel_pairing() -> None:
    """Stop the waiting session, if any. Its thread ends within a poll or one adb call."""
    with _PAIR_LOCK:
        if _PAIR["manager"] is not None:
            _PAIR["manager"].cancel()
            _PAIR.update(state="idle", id=None, serial=None, error=None, manager=None)


def _pair_worker(manager: Any, session: Any) -> None:
    """Thread body: wait for the scan, pair, connect, then record the outcome."""
    from connection.exceptions import ConnectionError as AdbConnectionError
    from connection.exceptions import OperationCancelledError, PairingTimeoutError

    outcome: dict[str, Any] = {"state": "failed", "error": "pairing stopped unexpectedly"}
    try:
        info = manager.execute_qr_pairing_flow(session=session, timeout=PAIR_TIMEOUT)
        outcome = {"state": "paired", "serial": info.serial}
    except PairingTimeoutError as exc:
        outcome = {"state": "expired", "error": str(exc)}
    except OperationCancelledError:
        outcome = {"state": "idle", "id": None}
    except (AdbConnectionError, OSError, RuntimeError, ValueError) as exc:
        outcome = {"state": "failed", "error": str(exc)}
    finally:  # whatever happened, the session must leave "waiting"
        with _PAIR_LOCK:
            current = _PAIR["manager"] is manager  # else cancelled meanwhile: that state stands
            if current:
                _PAIR.update(outcome, manager=None)
        if current:
            # The outcome holds no secret: adb never echoes the pairing password.
            _log(f"QR pairing {outcome['state']}: {outcome.get('serial') or outcome.get('error') or ''}")


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
            self._send_json(403, {"success": False, "error": "forbidden Host header"})
            return False
        if origin is not None and not origin_allowed(origin):
            self._send_json(403, {"success": False, "error": "origin not allowed (see --allow-origin)"})
            return False
        self._origin = origin
        if self.command == "POST" and self.headers.get_content_type() != "application/json":
            self._send_json(415, {"success": False, "error": "Content-Type must be application/json"})
            return False
        return True

    def _token_ok(self) -> bool:
        """Reject (and answer) a request that does not carry the session token. Call after _gate."""
        supplied = self.headers.get(TOKEN_HEADER) or ""
        # Bytes: compare_digest raises on a non-ASCII str, and a header may hold one.
        if hmac.compare_digest(supplied.encode("utf-8"), BRIDGE_TOKEN.encode("utf-8")):
            return True
        self._send_json(401, {"success": False,
                              "error": f"missing or wrong {TOKEN_HEADER} header (open the URL the bridge printed)"})
        return False

    def _send_cors(self) -> None:
        if self._origin:
            self.send_header("Access-Control-Allow-Origin", self._origin)
        self.send_header("Vary", "Origin")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)

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
            self._send_json(400, {"success": False, "error": "invalid request path"})
            return
        path = url.path.rstrip("/")
        params = dict(parse_qsl(url.query))
        is_health = path in ("/health", "/api/health")
        # /health stays open so the web app can tell "not running" from "token needed".
        if not is_health and not self._token_ok():
            return

        adb_path = discover_adb()

        if is_health:
            self._send_json(200, {
                "status": "ok",
                "version": VERSION,
                "adb_available": adb_available(adb_path),
                "adb_path": adb_path,
                "token_required": True,
            })
        elif path in ("/devices", "/api/devices"):
            try:
                devices = adb_devices(adb_path)
                self._send_json(200, {"devices": devices})
            except RuntimeError as exc:
                self._send_json(502, {"success": False, "error": str(exc)})
        elif path in ("/packages", "/api/packages"):
            serial = params.get("serial", "")
            if not serial:
                self._send_json(400, {"success": False, "error": "serial query parameter is required"})
                return
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
                self._send_json(502, {"success": False, "error": str(exc)})
        elif path in ("/pair/status", "/api/pair/status"):
            self._send_json(200, pair_status())
        elif path in ("/device", "/api/device"):
            serial = params.get("serial", "")
            if not serial:
                self._send_json(400, {"success": False, "error": "serial query parameter is required"})
                return
            try:
                props = adb_device_props(adb_path, serial)
                self._send_json(200, {"serial": serial, **props})
            except RuntimeError as exc:
                self._send_json(502, {"success": False, "error": str(exc)})
        else:
            self._send_json(404, {"success": False, "error": "not found"})

    def do_POST(self) -> None:
        raw = self._read_body()  # before _gate and _token_ok can answer; parsed only after both pass
        if not self._gate():
            return
        path = self.path.split("?", 1)[0].rstrip("/")
        if not self._token_ok():
            return
        body = self._parse_body(raw)
        if body is None:
            self._send_json(400, {"success": False, "error": "body must be a JSON object"})
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
        elif path in ("/pair/qr", "/api/pair/qr"):
            self._handle_pair_start()
        elif path in ("/pair/cancel", "/api/pair/cancel"):
            cancel_pairing()
            self._send_json(200, {"success": True, **pair_status()})
        else:
            self._send_json(404, {"success": False, "error": "not found"})

    # -- action handlers ---------------------------------------------------

    def _handle_execute(self, body: dict[str, Any]) -> None:
        serial = body.get("serial", "")
        mode = body.get("mode", "")
        action = body.get("action", "")
        packages = body.get("packages", [])

        if not serial or not isinstance(serial, str):
            self._send_json(400, {"success": False, "error": "serial is required (string)"})
            return
        if mode not in ALLOWED_MODES:
            self._send_json(400, {"success": False, "error": f"mode must be one of {ALLOWED_MODES}"})
            return
        if action not in ALLOWED_ACTIONS:
            self._send_json(400, {"success": False, "error": f"action must be one of {ALLOWED_ACTIONS}"})
            return
        if not isinstance(packages, list) or not all(isinstance(p, str) for p in packages):
            self._send_json(400, {"success": False, "error": "packages must be a list of strings"})
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
            self._send_json(500, {"success": False, "error": f"snapshot failed, aborting: {exc}"})
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
            self._send_json(400, {"success": False, "error": "serial is required (string)"})
            return
        if not isinstance(packages, list) or not all(isinstance(p, str) for p in packages):
            self._send_json(400, {"success": False, "error": "packages must be a list of strings"})
            return

        adb_path = discover_adb()
        results: list[dict[str, str]] = []
        for pkg in packages:
            if not is_valid_package(pkg):
                results.append({"package": str(pkg), "status": "failed", "output": "invalid package name"})
                continue
            # No critical guard: reinstalling a package for user 0 is recovery.
            shell_cmd = f"cmd package install-existing --user 0 {pkg}"
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
            running = _PAIR["manager"] is not None
            error = ""
            if not running:
                try:
                    from connection.qr_generator import generate_qr_matrix

                    manager = new_pairing_manager(discover_adb())
                    session = manager.create_pairing_session(ttl_seconds=PAIR_TIMEOUT)
                    matrix = [[int(cell) for cell in row] for row in generate_qr_matrix(session.qr_payload)]
                except (ImportError, OSError, RuntimeError, ValueError) as exc:  # no connection package, no adb
                    error = str(exc) or type(exc).__name__
                else:
                    _PAIR.update(state="waiting", id=session.session_id, serial=None, error=None, manager=manager)
                    threading.Thread(target=_pair_worker, args=(manager, session), daemon=True).start()
        if running:
            self._send_json(409, {"success": False, "error": "a pairing session is already running; cancel it first"})
        elif error:
            _log(f"QR pairing could not start: {error}")
            self._send_json(502, {"success": False, "error": f"QR pairing could not start: {error}"})
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

    stop_event = threading.Event()

    def handle_signal(sig_num: int, _frame: Any) -> None:
        if not stop_event.is_set():
            stop_event.set()
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
