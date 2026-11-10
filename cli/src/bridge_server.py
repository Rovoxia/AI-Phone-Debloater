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
    GET  /packages?serial=X&view=disabled
    GET  /device?serial=X | /api/device?serial=X
    POST /execute       | /api/execute   {serial, mode, action, packages}
    POST /restore       | /api/restore   {serial, packages}
    POST /shutdown
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path resolution (script lives at cli/src/bridge_server.py)
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent          # cli/src
PROJECT_ROOT = SCRIPT_DIR.parent.parent                # repo root
RULES_DIR = PROJECT_ROOT / "cli" / "rules"
CRITICAL_FILE = RULES_DIR / "critical-do-not-touch.json"

DEFAULT_PORT = 53123
VERSION = "1.0.0"
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

BACKUPS_DIR = Path.home() / "AiPhoneDebloater" / "backups"
LOCAL_BACKUPS_DIR = PROJECT_ROOT / "cli" / "backups"

# Package name validation (exact regex required by the bridge spec).
PACKAGE_RE = re.compile(r"^[a-zA-Z0-9._]+$")

ALLOWED_ACTIONS = ("disable", "uninstall", "enable")
ALLOWED_MODES = ("dry-run", "apply")

# CORS headers applied to every response.
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
    "Access-Control-Max-Age": "86400",
}

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"[bridge] {msg}", flush=True)


def load_version() -> str:
    for cand in (PROJECT_ROOT / "VERSION", SCRIPT_DIR.parent / "VERSION", Path.cwd() / "VERSION"):
        try:
            if cand.is_file():
                val = cand.read_text(encoding="utf-8").strip()
                if val:
                    return val
        except (OSError, ValueError):
            pass
    return VERSION


def load_critical_packages() -> set[str]:
    """Load the 89 critical (Tier 4) packages that must never be modified."""
    critical: set[str] = set()
    try:
        with CRITICAL_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        rules = data.get("rules") or data.get("packages") or []
        for entry in rules:
            if isinstance(entry, dict) and isinstance(entry.get("package"), str):
                critical.add(entry["package"])
    except (OSError, ValueError):
        pass
    return critical


CRITICAL_PACKAGES: set[str] = load_critical_packages()


def is_valid_package(pkg: Any) -> bool:
    return isinstance(pkg, str) and bool(PACKAGE_RE.match(pkg))


def is_critical(pkg: str) -> bool:
    return pkg in CRITICAL_PACKAGES


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

    bundled = [
        str(PROJECT_ROOT / "cli" / "tools" / "platform-tools" / "adb.exe"),
        str(PROJECT_ROOT / "cli" / "tools" / "platform-tools" / "adb"),
        str(Path.cwd() / "cli" / "tools" / "platform-tools" / "adb.exe"),
        str(Path.cwd() / "cli" / "tools" / "platform-tools" / "adb"),
        str(Path.cwd() / "tools" / "platform-tools" / "adb.exe"),
        str(Path.cwd() / "tools" / "platform-tools" / "adb"),
        str(Path.cwd() / "platform-tools" / "adb.exe"),
        str(Path.cwd() / "platform-tools" / "adb"),
    ]
    candidates.extend(bundled)
    candidates.append("adb")
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
        if not cand:
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

    return "adb"  # last resort; subprocess will surface a clear error


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


def adb_packages(adb_path: str, serial: str) -> list[str]:
    rc, out, err = run_adb(
        ["shell", "pm", "list", "packages", "-u", "--user", "0"],
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
    enabled_set = set()
    user0_set = set()
    try:
        _, out, _ = run_adb(["shell", "pm", "list", "packages", "--user", "0"], adb_path, serial=serial)
        user0_set = {line[len("package:"):].strip() for line in out.splitlines() if line.startswith("package:")}
    except RuntimeError:
        pass
    try:
        _, out, _ = run_adb(["shell", "pm", "list", "packages", "--user", "0", "-e"], adb_path, serial=serial)
        enabled_set = {line[len("package:"):].strip() for line in out.splitlines() if line.startswith("package:")}
    except RuntimeError:
        pass
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
# HTTP handler
# ---------------------------------------------------------------------------

class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "AI-Phone-DebloaterBridge/1.0"

    def log_message(self, fmt: str, *args) -> None:
        # Keep the bridge quiet; only log errors to stderr.
        if args and ("404" in fmt or "500" in fmt or "Error" in fmt):
            super().log_message(fmt, *args)

    # -- request plumbing ---------------------------------------------------

    def _send_json(self, status: int, payload: dict[str, Any], extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def _parse_body(self) -> dict[str, Any] | None:
        raw = self._read_body()
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _cors_preflight(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    # -- routing -----------------------------------------------------------

    def do_OPTIONS(self) -> None:
        self._cors_preflight()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        params: dict[str, str] = {}
        if query:
            for part in query.split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k] = v

        adb_path = discover_adb()

        if path in ("/health", "/api/health"):
            self._send_json(200, {
                "status": "ok",
                "version": load_version(),
                "adb_available": adb_available(adb_path),
                "adb_path": adb_path,
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
            if not is_valid_package(serial) and ":" not in serial:
                # serials can be IP:Port for wireless; only validate plain serials
                pass
            try:
                if params.get("view") == "disabled":
                    pkgs = adb_disabled_packages(adb_path, serial)
                    self._send_json(200, {"view": "disabled", "packages": pkgs})
                else:
                    pkgs = adb_packages(adb_path, serial)
                    self._send_json(200, {"view": "all", "packages": pkgs})
            except RuntimeError as exc:
                self._send_json(502, {"success": False, "error": str(exc)})
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
        path = self.path.split("?", 1)[0].rstrip("/")
        body = self._parse_body()
        if body is None:
            self._send_json(400, {"success": False, "error": "invalid JSON body"})
            return

        if path in ("/execute", "/api/execute"):
            self._handle_execute(body)
        elif path in ("/restore", "/api/restore"):
            self._handle_restore(body)
        elif path == "/shutdown":
            self._send_json(200, {"success": True, "message": "shutting down"})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self._send_json(404, {"success": False, "error": "not found"})

    # -- action handlers ---------------------------------------------------

    def _handle_execute(self, body: dict[str, Any]) -> None:
        serial = body.get("serial", "")
        mode = body.get("mode", "")
        action = body.get("action", "")
        packages = body.get("packages", [])

        if not serial:
            self._send_json(400, {"success": False, "error": "serial is required"})
            return
        if mode not in ALLOWED_MODES:
            self._send_json(400, {"success": False, "error": f"mode must be one of {ALLOWED_MODES}"})
            return
        if action not in ALLOWED_ACTIONS:
            self._send_json(400, {"success": False, "error": f"action must be one of {ALLOWED_ACTIONS}"})
            return
        if not isinstance(packages, list):
            self._send_json(400, {"success": False, "error": "packages must be a list"})
            return

        adb_path = discover_adb()
        results: list[dict[str, str]] = []
        planned: list[str] = []

        # Partition packages: critical (protected) vs actionable.
        actionable: list[str] = []
        seen: set[str] = set()
        for pkg in packages:
            if pkg in seen:
                continue
            seen.add(pkg)
            if not is_valid_package(pkg):
                results.append({"package": str(pkg), "status": "failed", "output": "invalid package name"})
                continue
            if is_critical(pkg):
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
        except OSError as exc:
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
        if not serial:
            self._send_json(400, {"success": False, "error": "serial is required"})
            return
        if not isinstance(packages, list):
            self._send_json(400, {"success": False, "error": "packages must be a list"})
            return

        adb_path = discover_adb()
        results: list[dict[str, str]] = []
        for pkg in packages:
            if not is_valid_package(pkg):
                results.append({"package": str(pkg), "status": "failed", "output": "invalid package name"})
                continue
            if is_critical(pkg):
                results.append({"package": pkg, "status": "skipped_protected", "output": "critical package, protected"})
                continue
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


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def find_free_port(start: int = DEFAULT_PORT) -> int:
    for port in range(start, start + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError(f"could not find a free port starting at {start}")


def start_bridge(port: int = DEFAULT_PORT) -> None:
    """Start the bridge server on ``port`` (falls back to a free port if busy)."""
    actual_port = port
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), BridgeHandler)
    except OSError:
        actual_port = find_free_port(port)
        _log(f"port {port} busy, using {actual_port}")
        httpd = ThreadingHTTPServer(("127.0.0.1", actual_port), BridgeHandler)

    _log(f"AI-Phone-Debloater Local ADB Bridge running at http://127.0.0.1:{actual_port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        _log("bridge server stopped")


if __name__ == "__main__":
    start_bridge(DEFAULT_PORT)
