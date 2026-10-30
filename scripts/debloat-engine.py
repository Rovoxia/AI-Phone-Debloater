#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Phone-Debloater — Core Debloat Engine
=======================================

Cross-platform (Windows / macOS / Linux) command-line tool for safely
debloating Android devices via ADB. Uses only the Python 3 standard library
(optional colorama/rich integration falls back to pure ANSI terminal colors).

Safety guarantees:
  * Never touches packages in rules/critical-do-not-touch.json or the
    hardcoded system-critical set.
  * Uses `pm disable-user --user 0` (soft disable) or
    `pm uninstall -k --user 0` (remove package for user only; `-k` keeps
    application data & cache).
  * Automatically takes a timestamped safety snapshot before any mutating
    operation so packages can be restored.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Reconfigure stdout/stderr to UTF-8 with replacement to prevent crashes on legacy Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

def load_version() -> str:
    """Read version from root VERSION file, fallback to 1.0.0."""
    vfile = PROJECT_ROOT / "VERSION"
    if vfile.is_file():
        try:
            val = vfile.read_text(encoding="utf-8").strip()
            if val:
                return val
        except Exception:
            pass
    return "1.0.0"

__version__ = load_version()

RULES_DIR_CANDIDATES = [
    PROJECT_ROOT / "rules",
    Path.cwd() / "rules",
    Path("rules"),
    SCRIPT_DIR.parent / "rules",
]
BACKUPS_DIR = PROJECT_ROOT / "backups"
DEFAULT_ADB_PATH_CANDIDATES: List[str] = [
    "adb",  # PATH
    str(PROJECT_ROOT / "tools" / "platform-tools" / "adb.exe"),
    str(PROJECT_ROOT / "tools" / "platform-tools" / "adb"),
    r"C:\platform-tools\adb.exe",
    str(Path.cwd() / "tools" / "platform-tools" / "adb.exe"),
    str(Path.cwd() / "platform-tools" / "adb"),
    str(Path.cwd() / "platform-tools" / "adb.exe"),
    str(Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / "adb"),
    str(Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / "adb.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
]

TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

# Hardcoded system-critical packages (never touched, on any device).
# Conservative superset; rules files may add more.
HARDCRITICAL_PACKAGES: Dict[str, str] = {
    "android": "Android core framework",
    "com.android.systemui": "System UI (nav bar, status bar, notifications)",
    "com.android.phone": "Telephony stack",
    "com.android.server.telecom": "Telecom manager",
    "com.android.settings": "Settings app",
    "com.android.vending": "Google Play Store",
    "com.google.android.gms": "Google Play services",
    "com.android.inputdevices": "Input device service",
    "com.android.location": "Location services",
    "com.android.wifi": "Wi-Fi stack",
    "com.android.wifi.service": "Wi-Fi service",
    "com.android.bluetooth": "Bluetooth stack",
    "com.android.nfc": "NFC service",
    "com.android.browser": "System browser",
    "com.android.documentsui": "Documents UI (file picker)",
    "com.android.calendar": "Calendar provider",
    "com.android.contacts": "Contacts storage",
    "com.android.telephony": "Telephony provider",
    "com.android.providers.contacts": "Contacts provider",
    "com.android.providers.calendar": "Calendar provider",
    "com.android.providers.downloads": "Download provider",
    "com.android.providers.media": "Media provider",
    "com.android.providers.userdictionary": "User dictionary",
    "com.android.providers.settings": "Settings provider",
    "com.android.providers.telephony": "Telephony provider",
    "com.android.shell": "ADB shell itself",
    "com.android.vending.licensing": "Play licensing",
    "com.android.webview": "Android System WebView",
    "com.android.packageinstaller": "Package installer",
    "com.android.launcher": "Home launcher",
    "com.android.launcher3": "Home launcher (AOSP)",
    "com.android.keyguard": "Lock screen",
    "com.android.desktopclock": "Clock / alarm",
    "com.android.messaging": "SMS app",
    "com.android.dialer": "Dialer",
    "com.android.incallui": "In-call UI",
    "com.android.mediacaserver": "Media CAS server",
    "com.android.stk": "SIM toolkit",
    "com.android.carrierconfig": "Carrier config",
    "com.android.emergency": "Emergency services",
    "com.android.sharedstoragebackup": "Shared storage backup",
    "com.android.onetimeinitializer": "OTA / setup",
    "com.android.partnercustomization": "Partner customization",
    "com.android.twilight": "Night light",
    "com.android.printspooler": "Print spooler",
    "com.android.wallpaper": "Wallpaper service",
    "com.android.systemupdate": "System updates",
    "com.android.networkstack": "Network stack",
    "com.android.bips": "BIP services",
    "com.android.ipsec": "IPsec stack",
    "com.android.vpn": "VPN services",
    "com.android.smspush": "SMS push",
    "com.android.cellbroadcastreceiver": "Cell broadcast (emergency alerts)",
    "com.android.ims": "IP Multimedia Subsystem",
    "com.android.ims.rcsservice": "RCS service",
    "com.google.android.webview": "Android System WebView",
    "com.google.android.inputmethod.latin": "Gboard keyboard",
    "com.android.keyboard": "AOSP keyboard",
    "com.samsung.android.oneconnect": "Samsung One Connect",
    "com.samsung.android.scloud": "Samsung cloud service",
    "com.samsung.android.app.samsungshare": "Samsung share service",
    "com.samsung.android.mdxservice": "Samsung mobile device exchange",
    "com.samsung.android.app.rss": "Samsung RSS feed",
    "com.samsung.android.app.sbrowser": "Samsung Internet browser",
    "com.huawei.systemmanager": "Huawei system manager",
    "com.huawei.launcher": "Huawei launcher",
    "com.huawei.android.koobr": "Huawei keyguard",
    "com.huawei.android.appmgr": "Huawei app manager",
    "com.huawei.android.hiaid": "Huawei HIAID service",
    "com.huawei.android.push": "Huawei push framework",
    "com.huawei.android.dialer": "Huawei dialer",
    "com.huawei.android.mms": "Huawei MMS",
    "com.huawei.android.location": "Huawei location",
    "com.huawei.android.messagecenter": "Huawei message center",
    "com.huawei.android.nfc": "Huawei NFC",
    "com.huawei.android.settings": "Huawei settings",
    "com.huawei.android.systemupdate": "Huawei system update",
    "com.huawei.android.ims": "Huawei IMS",
    "com.huawei.android.pushserviced": "Huawei push service",
}

# ---------------------------------------------------------------------------
# Minimal ANSI color helpers (pure stdlib, no third-party deps)
# ---------------------------------------------------------------------------
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                mode.value |= 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
                return kernel32.SetConsoleMode(handle, mode) != 0
        except Exception:
            pass
        return False
    return sys.stdout.isatty()


USE_COLOR = _supports_color()


def _c(text: str, code: str) -> str:
    return f"{code}{text}{Color.RESET}" if USE_COLOR else text


def red(text: str) -> str:
    return _c(text, Color.RED)


def green(text: str) -> str:
    return _c(text, Color.GREEN)


def yellow(text: str) -> str:
    return _c(text, Color.YELLOW)


def blue(text: str) -> str:
    return _c(text, Color.BLUE)


def magenta(text: str) -> str:
    return _c(text, Color.MAGENTA)


def cyan(text: str) -> str:
    return _c(text, Color.CYAN)


def bold(text: str) -> str:
    return _c(text, Color.BOLD)


def dim(text: str) -> str:
    return _c(text, Color.DIM)


# ---------------------------------------------------------------------------
# Logging / output
# ---------------------------------------------------------------------------
class Logger:
    def __init__(self, quiet: bool = False, verbose: bool = False) -> None:
        self.quiet = quiet
        self.verbose = verbose

    def info(self, msg: str) -> None:
        if not self.quiet:
            print(msg)

    def ok(self, msg: str) -> None:
        if not self.quiet:
            print(f"  {green('[OK]')} {msg}")

    def warn(self, msg: str) -> None:
        if not self.quiet:
            print(f"  {yellow('[WARN]')} {msg}")

    def error(self, msg: str) -> None:
        print(f"  {red('[ERR]')} {msg}", file=sys.stderr)

    def verbose_log(self, msg: str) -> None:
        if self.verbose and not self.quiet:
            print(f"  {dim('[DBG]')} {msg}")

    def header(self, msg: str) -> None:
        if not self.quiet:
            print(f"\n{blue(bold(msg))}")
            print("  " + "-" * (len(msg) + 2))

    def section(self, msg: str) -> None:
        if not self.quiet:
            print(f"\n{cyan(bold(msg))}")


class Progress:
    """Clean animated spinner loader for long-running operations."""

    def __init__(self, logger: Logger, label: str = "working") -> None:
        self.logger = logger
        self.label = label
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._chars = ["|", "/", "-", "\\"] if sys.platform == "win32" else ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __enter__(self) -> "Progress":
        if not self.logger.quiet and sys.stdout.isatty():
            self._stop.clear()
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            ch = self._chars[i % len(self._chars)]
            sys.stdout.write(f"\r  {cyan(bold(ch))} {self.label}...")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1
        sys.stdout.write("\r" + " " * (len(self.label) + 20) + "\r")
        sys.stdout.flush()

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.4)


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------
class AdbError(RuntimeError):
    pass


def run_cmd(
    cmd: List[str],
    timeout: float = 30.0,
    check: bool = False,
    capture: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str, str]:
    """Run a command robustly with timeout and UTF-8 decoding."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=full_env,
        )
    except FileNotFoundError as exc:
        raise AdbError(f"executable not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, (bytes, bytearray)) else str(exc.stdout or "")
        err = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, (bytes, bytearray)) else str(exc.stderr or "")
        raise AdbError(f"command timed out after {timeout}s: {' '.join(cmd)}\n{out}{err}") from exc
    except Exception as exc:  # noqa: BLE001
        raise AdbError(f"command failed: {' '.join(cmd)}: {exc}") from exc
    if check and proc.returncode != 0:
        raise AdbError(
            f"command exited {proc.returncode}: {' '.join(cmd)}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    return proc.returncode, proc.stdout, proc.stderr


class Adb:
    def __init__(
        self,
        adb_path: Optional[str] = None,
        serial: Optional[str] = None,
        timeout: float = 30.0,
        logger: Optional[Logger] = None,
    ) -> None:
        self.logger = logger or Logger()
        self.timeout = timeout
        self.serial = serial
        self.adb_path = adb_path or self._discover_adb()
        if not self.adb_path:
            raise AdbError(
                "adb not found. Install Android platform-tools or pass --adb-path."
            )
        self.logger.verbose_log(f"adb path: {self.adb_path}")

    @staticmethod
    def _discover_adb() -> Optional[str]:
        env_path = os.environ.get("AI_PHONE_DEBLOATER_ADB_PATH")
        candidates: List[str] = []
        if env_path:
            candidates.append(env_path)
        candidates.extend(DEFAULT_ADB_PATH_CANDIDATES)
        for cand in candidates:
            if not cand:
                continue
            path = Path(cand)
            if shutil.which(str(path)):
                return str(shutil.which(str(path)))
            if path.exists():
                return str(path)
        return None

    def _base(self) -> List[str]:
        base = [self.adb_path]
        if self.serial:
            base += ["-s", self.serial]
        return base

    def shell(self, command: str, timeout: Optional[float] = None) -> Tuple[int, str, str]:
        cmd = self._base() + ["shell", command]
        return run_cmd(cmd, timeout=timeout or self.timeout)

    def devices(self) -> List[Dict[str, str]]:
        """Return list of attached devices with serial + state."""
        rc, out, err = run_cmd(self._base() + ["devices", "-l"], timeout=self.timeout)
        if rc != 0:
            raise AdbError(f"adb devices failed: {err or out}")
        devices: List[Dict[str, str]] = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            info: Dict[str, str] = {"serial": parts[0], "state": parts[1]}
            for token in parts[2:]:
                if ":" in token:
                    k, _, v = token.partition(":")
                    info[k] = v
            devices.append(info)
        return devices

    def connect_wireless(self, address: str) -> Tuple[int, str, str]:
        """Connect to device over Wi-Fi (e.g. 192.168.1.50:5555)."""
        cmd = [self.adb_path, "connect", address]
        return run_cmd(cmd, timeout=self.timeout)

    def pair_wireless(self, address: str, code: str) -> Tuple[int, str, str]:
        """Pair with device using Android 11+ pairing code (e.g. 192.168.1.50:port, code)."""
        cmd = [self.adb_path, "pair", address, code]
        return run_cmd(cmd, timeout=self.timeout)

    def tcpip(self, port: int = 5555) -> Tuple[int, str, str]:
        """Switch connected USB device to wireless ADB port (adb tcpip 5555)."""
        cmd = self._base() + ["tcpip", str(port)]
        return run_cmd(cmd, timeout=self.timeout)

    def getprop(self, prop: str, timeout: Optional[float] = None) -> str:
        rc, out, err = self.shell(f"getprop {prop}", timeout=timeout)
        if rc != 0:
            self.logger.verbose_log(f"getprop {prop} failed rc={rc}: {err}")
            return ""
        return out.strip()

    def pm_list_packages(
        self,
        user: Optional[int] = None,
        disabled: bool = False,
        enabled: bool = False,
    ) -> List[str]:
        args: List[str] = ["pm", "list", "packages"]
        if disabled:
            args.append("-d")
        if enabled:
            args.append("-e")
        if user is not None:
            args += ["--user", str(user)]
        rc, out, err = self.shell(" ".join(args))
        if rc != 0:
            raise AdbError(f"pm list packages failed: {err or out}")
        pkgs: List[str] = []
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                pkgs.append(line[len("package:") :].strip())
        return pkgs

    def pm_path(self, package: str) -> str:
        rc, out, err = self.shell(f"pm path {package}")
        if rc != 0:
            return ""
        m = re.search(r"package:([^\s]+)", out)
        return m.group(1) if m else ""

    def disable_user(self, package: str, timeout: Optional[float] = None) -> Tuple[int, str, str]:
        return self.shell(f"pm disable-user --user 0 {package}", timeout=timeout)

    def uninstall_user(self, package: str, timeout: Optional[float] = None) -> Tuple[int, str, str]:
        return self.shell(f"pm uninstall -k --user 0 {package}", timeout=timeout)

    def enable(self, package: str, timeout: Optional[float] = None) -> Tuple[int, str, str]:
        return self.shell(f"pm enable {package}", timeout=timeout)

    def install_existing(self, package: str, timeout: Optional[float] = None) -> Tuple[int, str, str]:
        rc, out, err = self.shell(f"cmd package install-existing {package}", timeout=timeout)
        # Fallback to legacy pm command if cmd is unavailable or unsupported (API < 26)
        if rc != 0 or "Unknown command" in err or "Unknown command" in out or "not found" in err:
            legacy_rc, legacy_out, legacy_err = self.shell(f"pm install-existing {package}", timeout=timeout)
            if legacy_rc == 0 or "installed" in legacy_out.lower():
                return legacy_rc, legacy_out, legacy_err
        return rc, out, err

    def is_enabled(self, package: str) -> bool:
        rc, out, err = self.shell(f"pm list packages -e --user 0 {package}")
        return rc == 0 and f"package:{package}" in out

    def is_installed_user(self, package: str, user: int = 0) -> bool:
        rc, out, err = self.shell(f"pm list packages --user {user} {package}")
        return rc == 0 and f"package:{package}" in out

    def is_installed_any_user(self, package: str) -> bool:
        rc, out, err = self.shell(f"pm list packages {package}")
        return rc == 0 and f"package:{package}" in out


# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------
class RuleSet:
    def __init__(self, logger: Optional[Logger] = None) -> None:
        self.logger = logger or Logger()
        self.critical: set[str] = set(HARDCRITICAL_PACKAGES.keys())
        self.critical_reasons: Dict[str, str] = dict(HARDCRITICAL_PACKAGES)
        self.safe: Dict[str, Dict[str, Any]] = {}
        self.oem: Dict[str, Dict[str, Any]] = {}
        self.loaded_files: List[str] = []

    def _load_json(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            self.logger.verbose_log(f"rule file not found: {path}")
            return None
        except json.JSONDecodeError as exc:
            self.logger.warn(f"skipping invalid rule file {path}: {exc}")
            return None
        except Exception as exc:  # noqa: BLE001
            self.logger.warn(f"could not read rule file {path}: {exc}")
            return None

    def find_rules_dir(self) -> Optional[Path]:
        for cand in RULES_DIR_CANDIDATES:
            if cand.is_dir():
                return cand
        return None

    def _add_critical(self, pkg: str, reason: str) -> None:
        self.critical.add(pkg)
        self.critical_reasons[pkg] = reason
        self.safe.pop(pkg, None)
        self.oem.pop(pkg, None)

    def _add_safe(self, pkg: str, tier: int, reason: str, source: str) -> None:
        if pkg in self.critical:
            return
        self.safe[pkg] = {"tier": tier, "reason": reason, "source": source}

    @staticmethod
    def _tier_from_category(category: str) -> int:
        cat = category.lower()
        if "telemetry" in cat or "ad" in cat or "tracker" in cat:
            return 1
        if "bloat" in cat or "carrier" in cat:
            return 1
        if "wellbeing" in cat or "voice" in cat or "cloud" in cat or "feedback" in cat:
            return 2
        return 3

    def load(
        self,
        rules_dir: Optional[Path] = None,
        manufacturer: Optional[str] = None,
    ) -> None:
        rules_dir = rules_dir or self.find_rules_dir()
        if not rules_dir:
            self.logger.warn("no rules directory found; using hardcoded critical set only")
            return

        # 1. critical-do-not-touch (always loaded)
        critical_path = rules_dir / "critical-do-not-touch.json"
        data = self._load_json(critical_path)
        if data:
            self.loaded_files.append(str(critical_path))
            entries = data.get("rules", []) or data.get("packages", [])
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("package", "")
                if not name:
                    continue
                reason = (
                    entry.get("description", "")
                    or entry.get("reason", "")
                    or entry.get("name", "")
                    or f"rule: critical-do-not-touch ({entry.get('category','')})"
                )
                self._add_critical(name, reason)

        # 2. universal-safe-to-remove — uses "rules" array with per-entry tier/category
        universal_path = rules_dir / "universal-safe-to-remove.json"
        data = self._load_json(universal_path)
        if data:
            self.loaded_files.append(str(universal_path))
            for entry in data.get("rules", []):
                if not isinstance(entry, dict):
                    continue
                name = entry.get("package", "")
                tier = int(entry.get("tier", self._tier_from_category(entry.get("category", ""))))
                reason = (
                    entry.get("description", "")
                    or f"universal-safe-to-remove ({entry.get('category','')})"
                )
                self._add_safe(name, tier, reason, "universal-safe-to-remove")

        # 3. All OEM & device-specific rule files in rules_dir
        for rule_file in sorted(rules_dir.glob("*.json")):
            if rule_file.name in ("critical-do-not-touch.json", "universal-safe-to-remove.json"):
                continue
            data = self._load_json(rule_file)
            if not data:
                continue
            self.loaded_files.append(str(rule_file))
            entries = data.get("rules", []) or data.get("packages", [])
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("package", "")
                if not name:
                    continue
                tier = int(entry.get("tier", self._tier_from_category(entry.get("category", ""))))
                reason = (
                    entry.get("description", "")
                    or entry.get("reason", "")
                    or entry.get("name", f"OEM rule ({rule_file.stem})")
                )
                self.oem[name] = {"tier": tier, "reason": reason, "source": rule_file.name}
                self._add_safe(name, tier, reason, rule_file.name)

    def is_critical(self, package: str) -> bool:
        return package in self.critical

    def critical_reason(self, package: str) -> str:
        return self.critical_reasons.get(package, "hardcoded system-critical")

    def tier_for(self, package: str) -> Optional[int]:
        info = self.safe.get(package) or self.oem.get(package)
        if info:
            return int(info.get("tier", 3))
        return None

    def classify(self, package: str) -> Tuple[int, str, str]:
        """Return (tier, reason, source). Tier 4 = critical, 0 = unknown."""
        if self.is_critical(package):
            return 4, self.critical_reason(package), "critical-do-not-touch / hardcoded"
        info = self.safe.get(package) or self.oem.get(package)
        if info:
            return int(info.get("tier", 3)), str(info.get("reason", "")), str(info.get("source", ""))
        return 0, "not categorized in rules", "unknown"

    def packages_by_tier(self, tier: int) -> List[str]:
        return [pkg for pkg, info in self.safe.items() if int(info.get("tier", 0)) == tier]


# ---------------------------------------------------------------------------
# Device info
# ---------------------------------------------------------------------------
class DeviceInfo:
    def __init__(self, adb: Adb, logger: Logger) -> None:
        self.adb = adb
        self.logger = logger
        self.serial: str = ""
        self.state: str = ""
        self.manufacturer: str = ""
        self.model: str = ""
        self.release: str = ""
        self.security_patch: str = ""
        self.build_id: str = ""
        self.architecture: str = ""
        self.sdk_int: str = ""

    def populate(self) -> None:
        props = {
            "manufacturer": "ro.product.manufacturer",
            "model": "ro.product.model",
            "release": "ro.build.version.release",
            "security_patch": "ro.build.version.security_patch",
            "build_id": "ro.build.display.id",
            "architecture": "ro.product.cpu.abi",
            "sdk_int": "ro.build.version.sdk",
        }
        for key, prop in props.items():
            val = self.adb.getprop(prop)
            setattr(self, key, val or "unknown")
            self.logger.verbose_log(f"getprop {prop} = {getattr(self, key)}")

    def summary(self) -> str:
        return (
            f"{bold(self.manufacturer)} {self.model} "
            f"(Android {self.release}, SDK {self.sdk_int}, {self.architecture})"
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "serial": self.serial,
            "state": self.state,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "release": self.release,
            "security_patch": self.security_patch,
            "build_id": self.build_id,
            "architecture": self.architecture,
            "sdk_int": self.sdk_int,
        }


# ---------------------------------------------------------------------------
# Snapshot / backup
# ---------------------------------------------------------------------------
class SnapshotManager:
    def __init__(self, backups_dir: Path, logger: Logger) -> None:
        self.backups_dir = backups_dir
        self.logger = logger
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def snapshot_path(self, model: str, timestamp: Optional[str] = None) -> Path:
        ts = timestamp or datetime.now().strftime(TIMESTAMP_FORMAT)
        safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", model or "unknown")
        return self.backups_dir / f"snapshot_{safe_model}_{ts}.json"

    def create(
        self,
        device: DeviceInfo,
        packages: List[Dict[str, Any]],
        adb: Adb,
    ) -> Path:
        """Record every package with enabled/disabled/installed status + path."""
        ts = datetime.now().strftime(TIMESTAMP_FORMAT)
        path = self.snapshot_path(device.model, ts)
        entries: List[Dict[str, Any]] = []
        total = len(packages)
        for idx, pkg in enumerate(packages, 1):
            name = pkg.get("name") if isinstance(pkg, dict) else str(pkg)
            enabled = adb.is_enabled(name)
            installed = adb.is_installed_any_user(name)
            path_str = adb.pm_path(name) if (enabled or installed) else ""
            entries.append(
                {
                    "name": name,
                    "enabled": enabled,
                    "installed_any_user": installed,
                    "package_path": path_str,
                    "disabled": installed and not enabled,
                    "tier": pkg.get("tier", 0) if isinstance(pkg, dict) else 0,
                    "reason": pkg.get("reason", "") if isinstance(pkg, dict) else "",
                    "source": pkg.get("source", "") if isinstance(pkg, dict) else "",
                }
            )
            if idx % 10 == 0 or idx == total:
                self.logger.verbose_log(f"snapshot progress {idx}/{total}")
        snapshot = {
            "created_at": datetime.now().isoformat(),
            "timestamp": ts,
            "device": device.to_dict(),
            "package_count": len(entries),
            "packages": entries,
        }
        with path.open("w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2, ensure_ascii=False)
        self.logger.ok(f"snapshot written: {path} ({len(entries)} packages)")
        return path

    @staticmethod
    def load(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def list_backups(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if not self.backups_dir.exists():
            return results
        for path in sorted(
            self.backups_dir.glob("snapshot_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                data = self.load(path)
            except Exception:  # noqa: BLE001
                continue
            results.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "created_at": data.get("created_at", ""),
                    "device": data.get("device", {}),
                    "package_count": data.get("package_count", 0),
                }
            )
        return results

    def find_backup(self, identifier: str) -> Optional[Path]:
        if not self.backups_dir.exists():
            return None
        direct = Path(identifier)
        if direct.exists():
            return direct
        candidate = self.backups_dir / identifier
        if candidate.exists():
            return candidate
        for path in sorted(self.backups_dir.glob("snapshot_*.json")):
            if identifier in path.name:
                return path
        return None


# ---------------------------------------------------------------------------
# Engine core
# ---------------------------------------------------------------------------
class DebloatEngine:
    def __init__(
        self,
        adb_path: Optional[str] = None,
        serial: Optional[str] = None,
        rules_dir: Optional[Path] = None,
        backups_dir: Path = BACKUPS_DIR,
        quiet: bool = False,
        verbose: bool = False,
        dry_run: bool = False,
        timeout: float = 30.0,
    ) -> None:
        self.logger = Logger(quiet=quiet, verbose=verbose)
        self.dry_run = dry_run
        self.timeout = timeout
        self.adb = Adb(
            adb_path=adb_path,
            serial=serial,
            timeout=timeout,
            logger=self.logger,
        )
        self.device = DeviceInfo(self.adb, self.logger)
        self.rules = RuleSet(logger=self.logger)
        self.snapshot_mgr = SnapshotManager(backups_dir, self.logger)
        self._confirmed = False

    # -- wireless -----------------------------------------------------------
    def discover_wireless(self) -> List[Dict[str, str]]:
        """Discover wireless devices via ADB mDNS/Bonjour (Android 11+)."""
        self.logger.info("Searching for wireless ADB devices via mDNS/Bonjour...")
        rc, out, err = run_cmd([self.adb_path, "mdns", "services"], timeout=self.timeout)
        devices = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            # Parse mDNS discovery output: "device_name (ip:port)" or just "ip:port"
            parts = line.replace("(", " ").replace(")", " ").split()
            if len(parts) >= 2:
                addr = parts[-1]
                if ":" in addr and addr.count(".") >= 3:
                    devices.append({"serial": addr, "state": "device", "name": parts[0]})
        return devices

    def auto_discover(self) -> Optional[str]:
        """Automatically discover and return connection address.
        Tries mDNS discovery first, then falls back to user input."""
        # Try mDNS/Bonjour discovery first (Android 11+ wireless debugging)
        try:
            w_devices = self.discover_wireless()
            if w_devices:
                self.logger.info(f"Found {len(w_devices)} wireless device(s) via mDNS/Bonjour:")
                for i, d in enumerate(w_devices, 1):
                    print(f"  [{i}] {d.get('name', d['serial'])} @ {d['serial']}")
                if len(w_devices) == 1:
                    return w_devices[0]["serial"]
                choice = input("Select wireless device number (Enter for first): ").strip()
                if not choice:
                    return w_devices[0]["serial"]
                idx = int(choice) - 1
                if 0 <= idx < len(w_devices):
                    return w_devices[idx]["serial"]
        except Exception:
            pass
        return None

    def connect_wireless(self, address: str) -> bool:
        self.logger.info(f"Connecting to wireless ADB device at {address}...")
        rc, out, err = self.adb.connect_wireless(address)
        if rc == 0 and ("connected to" in out.lower() or "already connected" in out.lower()):
            self.logger.ok(f"Connected to wireless ADB: {address}")
            self.adb.serial = address
            return True
        self.logger.error(f"Wireless connection failed: {out.strip() or err.strip()}")
        return False

    def pair_wireless(self, address: str, code: str) -> bool:
        self.logger.info(f"Pairing with wireless device {address} using code...")
        rc, out, err = self.adb.pair_wireless(address, code)
        if rc == 0 and "successfully paired" in out.lower():
            self.logger.ok(f"Successfully paired with {address}")
            return True
        self.logger.error(f"Wireless pairing failed: {out.strip() or err.strip()}")
        return False

    # -- lifecycle ----------------------------------------------------------
    def connect(self) -> None:
        self.logger.header("ADB Discovery & Device Detection")
        with Progress(self.logger, "Searching for connected ADB devices"):
            devices = self.adb.devices()
        if not devices:
            w_addr = self.auto_discover()
            if w_addr and self.connect_wireless(w_addr):
                devices = self.adb.devices()
        if not devices:
            raise AdbError(
                "No ADB devices found. Connect via USB (enable USB debugging) or over Wi-Fi (adb connect <ip>:<port> or use 'w' in menu)."
            )
        if len(devices) == 1:
            dev = devices[0]
        else:
            self.logger.info("Multiple devices detected:")
            for i, d in enumerate(devices, 1):
                print(f"  [{i}] {d['serial']} ({d['state']})")
            choice = input("Select device number: ").strip()
            try:
                idx = int(choice) - 1
                dev = devices[idx]
            except Exception:
                raise AdbError("Invalid selection.")
        self.adb.serial = dev["serial"]
        self.device.serial = dev["serial"]
        self.device.state = dev.get("state", "device")
        if self.device.state != "device":
            if self.device.state == "unauthorized":
                raise AdbError(
                    f"Device {self.device.serial} is unauthorized. Unlock phone screen and check 'Always allow from this computer' on the USB debugging prompt."
                )
            elif self.device.state == "offline":
                raise AdbError(
                    f"Device {self.device.serial} is offline. Reconnect the USB cable or toggle USB debugging off and on."
                )
            else:
                raise AdbError(
                    f"Device {self.device.serial} is not ready (state={self.device.state}). Expected 'device'."
                )
        with Progress(self.logger, f"Querying hardware parameters for {self.device.serial}"):
            self.device.populate()
        self.logger.ok(f"Connected: {self.device.summary()}")

    def load_rules(self, manufacturer: Optional[str] = None) -> None:
        mfr = manufacturer or (
            self.device.manufacturer if self.device.manufacturer != "unknown" else None
        )
        with Progress(self.logger, "Loading OEM debloat rule databases"):
            self.rules.load(rules_dir=None, manufacturer=mfr)
        self.logger.ok(f"Rules loaded ({len(self.rules.loaded_files)} file(s))")
        for f in self.rules.loaded_files:
            self.logger.verbose_log(f"  rule file: {f}")

    # -- scan ---------------------------------------------------------------
    def scan(self) -> List[Dict[str, Any]]:
        self.logger.section("Scanning installed packages")
        with Progress(self.logger, "Querying package manager and enabled states"):
            raw = self.adb.pm_list_packages(user=0)
            enabled_set = set(self.adb.pm_list_packages(user=0, enabled=True))
            all_system_set = set(self.adb.pm_list_packages())

        self.logger.info(f"Found {len(raw)} packages for user 0 ({len(enabled_set)} enabled)")
        results: List[Dict[str, Any]] = []
        for name in raw:
            tier, reason, source = self.rules.classify(name)
            enabled = name in enabled_set
            installed = name in all_system_set
            results.append(
                {
                    "name": name,
                    "enabled": enabled,
                    "installed_any_user": installed,
                    "tier": tier,
                    "reason": reason,
                    "source": source,
                    "critical": self.rules.is_critical(name),
                }
            )
        results.sort(key=lambda p: (-(p["tier"]), p["name"]))
        self._print_scan(results)
        return results

    def _print_scan(self, results: List[Dict[str, Any]]) -> None:
        tier_counts: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 0: 0}
        for p in results:
            tier_counts[p["tier"]] = tier_counts.get(p["tier"], 0) + 1
        self.logger.section("Safety Tier Summary")
        print(f"  {green('Tier 1 (Safe Bloat):')}     {tier_counts.get(1, 0)}")
        print(f"  {yellow('Tier 2 (Advanced):')}       {tier_counts.get(2, 0)}")
        print(f"  {magenta('Tier 3 (Extreme):')}        {tier_counts.get(3, 0)}")
        print(f"  {red('Tier 4 (CRITICAL):')}       {tier_counts.get(4, 0)}  (protected)")
        print(f"  {dim('Unknown:')}            {tier_counts.get(0, 0)}")
        self.logger.section("Detailed Listing")
        for p in results:
            tier = p["tier"]
            if tier == 4:
                label = red("CRITICAL")
            elif tier == 1:
                label = green("Tier 1")
            elif tier == 2:
                label = yellow("Tier 2")
            elif tier == 3:
                label = magenta("Tier 3")
            else:
                label = dim("Unknown")
            status = "enabled" if p["enabled"] else ("disabled" if p["installed_any_user"] else "not-installed")
            crit_marker = "  [PROTECTED]" if p["critical"] else ""
            print(f"  {label:12} {p['name']:<45} {status:<16} {p['reason']}{crit_marker}")

    # -- safety checks ------------------------------------------------------
    def is_protected(self, package: str) -> Tuple[bool, str]:
        if self.rules.is_critical(package):
            return True, self.rules.critical_reason(package)
        return False, ""

    # -- snapshot -----------------------------------------------------------
    def take_snapshot(self, packages: List[Dict[str, Any]]) -> Path:
        self.logger.section("Safety Snapshot")
        return self.snapshot_mgr.create(self.device, packages, self.adb)

    # -- execution ----------------------------------------------------------
    def _confirm(self, message: str) -> bool:
        if self._confirmed:
            return True
        resp = input(f"{message} [y/N]: ").strip().lower()
        return resp in ("y", "yes")

    def execute_plan(
        self,
        packages: List[str],
        action: str = "disable",
        require_confirm: bool = True,
        auto_snapshot: bool = True,
        packages_meta: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "action": action,
            "total": len(packages),
            "skipped_protected": [],
            "skipped_unknown": [],
            "executed": [],
            "failed": [],
            "snapshot": None,
        }

        actionable: List[str] = []
        for pkg in packages:
            protected, reason = self.is_protected(pkg)
            if protected:
                report["skipped_protected"].append({"package": pkg, "reason": reason})
                self.logger.warn(f"SKIP (protected): {pkg} — {reason}")
                continue
            actionable.append(pkg)

        if not actionable:
            self.logger.info("No actionable packages after safety filtering.")
            return report

        self.logger.section(f"Planned {action} operations ({len(actionable)} packages)")
        for pkg in actionable:
            meta = next((m for m in (packages_meta or []) if m.get("name") == pkg), {})
            tier = meta.get("tier", 0)
            reason = meta.get("reason", "")
            print(f"  [{action}] {pkg:<45} tier={tier} {reason}")

        if self.dry_run:
            self.logger.info("[DRY-RUN] No commands executed.")
            report["executed"] = [{"package": p, "status": "dry-run"} for p in actionable]
            return report

        if require_confirm and not self._confirm(f"Proceed with {action} on {len(actionable)} package(s)?"):
            self.logger.info("Aborted by user.")
            return report

        if auto_snapshot and packages_meta:
            snap = self.take_snapshot(packages_meta)
            report["snapshot"] = str(snap)

        for pkg in actionable:
            if action == "uninstall":
                rc, out, err = self.adb.uninstall_user(pkg, timeout=self.timeout)
                verified = (rc == 0) and (not self.adb.is_installed_user(pkg, user=0))
            else:
                rc, out, err = self.adb.disable_user(pkg, timeout=self.timeout)
                verified = (rc == 0) and (not self.adb.is_enabled(pkg))
            if rc == 0:
                status_str = "success" if verified else "success (unverified state)"
                report["executed"].append(
                    {"package": pkg, "status": status_str, "output": out.strip()}
                )
                self.logger.ok(f"{action}: {pkg}")
            else:
                report["failed"].append(
                    {"package": pkg, "error": err.strip() or out.strip()}
                )
                self.logger.error(f"{action} FAILED: {pkg} — {err.strip() or out.strip()}")
        return report

    # -- debloat by tier ----------------------------------------------------
    def debloat_tier(
        self,
        tier: int,
        action: str = "disable",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        self.connect()
        self.load_rules()
        results = self.scan()
        packages = [p["name"] for p in results if p["tier"] == tier and not p["critical"]]
        if not packages:
            self.logger.info(f"No packages found for Tier {tier}.")
            return {
                "action": action,
                "tier": tier,
                "total": 0,
                "executed": [],
                "failed": [],
                "skipped_protected": [],
            }
        return self.execute_plan(packages, action=action, packages_meta=results, **kwargs)

    # -- export for AI ------------------------------------------------------
    def export_for_ai(self, out_dir: Optional[Path] = None) -> Tuple[Path, Path]:
        self.connect()
        self.load_rules()
        results = self.scan()
        out_dir = out_dir or PROJECT_ROOT
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime(TIMESTAMP_FORMAT)
        safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", self.device.model or "unknown")
        base = f"device-profile_{safe_model}_{ts}"
        json_path = out_dir / f"{base}.json"
        md_path = out_dir / f"{base}.md"

        profile = {
            "exported_at": datetime.now().isoformat(),
            "device": self.device.to_dict(),
            "rules_loaded": self.rules.loaded_files,
            "packages": results,
        }
        with json_path.open("w", encoding="utf-8") as fh:
            json.dump(profile, fh, indent=2, ensure_ascii=False)

        lines: List[str] = []
        lines.append(f"# Device Package Profile — {self.device.summary()}")
        lines.append(f"- Serial: {self.device.serial}")
        lines.append(f"- State: {self.device.state}")
        lines.append(f"- Android: {self.device.release} (SDK {self.device.sdk_int})")
        lines.append(f"- Security patch: {self.device.security_patch}")
        lines.append(f"- Build: {self.device.build_id}")
        lines.append(f"- Architecture: {self.device.architecture}")
        lines.append(f"- Exported: {profile['exported_at']}")
        lines.append("")
        lines.append("## Safety Tiers")
        tier_labels = {
            4: "CRITICAL (Do Not Touch)",
            1: "Tier 1 — Safe Bloat",
            2: "Tier 2 — Advanced Debloat",
            3: "Tier 3 — Extreme Debloat",
            0: "Unknown (uncategorized)",
        }
        for tier in (4, 1, 2, 3, 0):
            tier_pkgs = [p for p in results if p["tier"] == tier]
            if not tier_pkgs:
                continue
            lines.append(f"### {tier_labels[tier]} ({len(tier_pkgs)})")
            for p in tier_pkgs:
                status = "enabled" if p["enabled"] else "disabled"
                lines.append(f"- `{p['name']}` — {status} — {p['reason']} ({p['source']})")
            lines.append("")
        with md_path.open("w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

        self.logger.ok(f"JSON profile: {json_path}")
        self.logger.ok(f"Markdown profile: {md_path}")
        return json_path, md_path

    # -- apply AI plan ------------------------------------------------------
    def apply_ai_plan(self, plan_path: Path, action: str = "disable") -> Dict[str, Any]:
        self.logger.section(f"Applying AI plan: {plan_path}")
        if not plan_path.exists():
            raise AdbError(f"plan file not found: {plan_path}")
        with plan_path.open("r", encoding="utf-8") as fh:
            plan = json.load(fh)
        packages: List[str] = []
        if isinstance(plan, dict):
            packages = plan.get("packages", []) or plan.get("debloat", []) or []
        elif isinstance(plan, list):
            packages = [str(p) for p in plan]
        else:
            raise AdbError("unrecognized plan format")
        self.connect()
        self.load_rules()
        blocked = [p for p in packages if self.rules.is_critical(p)]
        if blocked:
            self.logger.error("Plan contains CRITICAL packages — aborting:")
            for p in blocked:
                print(f"  {red('BLOCKED')} {p} — {self.rules.critical_reason(p)}")
            raise AdbError("AI plan references protected packages; refusing to execute.")
        meta = [
            {"name": p, "tier": self.rules.tier_for(p) or 0, "reason": "", "source": "ai-plan"}
            for p in packages
        ]
        return self.execute_plan(packages, action=action, packages_meta=meta)

    # -- restore ------------------------------------------------------------
    def restore(self, identifier: str, action: str = "auto") -> Dict[str, Any]:
        self.logger.section(f"Restore: {identifier}")
        snap_path = self.snapshot_mgr.find_backup(identifier)
        if not snap_path:
            raise AdbError(f"backup snapshot not found: {identifier}")
        data = self.snapshot_mgr.load(snap_path)
        packages = data.get("packages", [])
        self.connect()
        report: Dict[str, Any] = {
            "snapshot": str(snap_path),
            "restored": [],
            "failed": [],
            "skipped": [],
        }
        for entry in packages:
            pkg = entry.get("name", "")
            was_enabled = entry.get("enabled", False)
            was_installed = entry.get("installed_any_user", False)
            if action == "auto":
                if was_enabled:
                    do = "enable"
                elif was_installed:
                    do = "install-existing"
                else:
                    report["skipped"].append(
                        {"package": pkg, "reason": "not present in snapshot"}
                    )
                    continue
            elif action == "enable":
                do = "enable"
            elif action == "install-existing":
                do = "install-existing"
            else:
                do = "enable"
            if self.dry_run:
                report["restored"].append({"package": pkg, "status": f"dry-run {do}"})
                continue
            if do == "enable":
                rc, out, err = self.adb.enable(pkg, timeout=self.timeout)
                verified = (rc == 0) and self.adb.is_enabled(pkg)
            else:
                rc, out, err = self.adb.install_existing(pkg, timeout=self.timeout)
                verified = (rc == 0) and self.adb.is_installed_user(pkg, user=0)
            if rc == 0:
                status_str = f"{do}: success" if verified else f"{do}: success (unverified state)"
                report["restored"].append(
                    {"package": pkg, "status": status_str, "output": out.strip()}
                )
                self.logger.ok(f"restored {do}: {pkg}")
            else:
                report["failed"].append(
                    {"package": pkg, "error": err.strip() or out.strip(), "action": do}
                )
                self.logger.error(f"restore {do} FAILED: {pkg} — {err.strip() or out.strip()}")
        return report

    def restore_pkg(self, package: str) -> Dict[str, Any]:
        self.connect()
        report: Dict[str, Any] = {"package": package, "restored": False, "attempts": []}
        for do in ("enable", "install-existing"):
            if do == "enable":
                rc, out, err = self.adb.enable(package, timeout=self.timeout)
                verified = (rc == 0) and self.adb.is_enabled(package)
            else:
                rc, out, err = self.adb.install_existing(package, timeout=self.timeout)
                verified = (rc == 0) and self.adb.is_installed_user(package, user=0)
            report["attempts"].append(
                {"action": do, "rc": rc, "output": out.strip(), "error": err.strip(), "verified": verified}
            )
            if rc == 0:
                report["restored"] = True
                self.logger.ok(f"restored {do}: {package}")
                return report
        self.logger.error(f"could not restore: {package}")
        return report

    # -- list backups -------------------------------------------------------
    def list_backups(self) -> List[Dict[str, Any]]:
        return self.snapshot_mgr.list_backups()

    # -- interactive --------------------------------------------------------
    def interactive(self) -> None:
        self.logger.header(f"AI-Phone-Debloater v{__version__} — Interactive Mode")
        try:
            self.connect()
            self.load_rules()
        except AdbError as exc:
            self.logger.warn(f"Initial connection: {exc}")
            self.logger.info("Tip: If using Wi-Fi without USB, select 'w' below to connect wirelessly.")

        while True:
            print()
            print(f"{bold('1')}  Scan device & show tiers")
            print(f"{bold('2')}  Dry-run Tier 1 debloat")
            print(f"{bold('3')}  Debloat Tier 1 (disable)")
            print(f"{bold('4')}  Debloat Tier 2 (disable)")
            print(f"{bold('5')}  Debloat Tier 3 (disable)")
            print(f"{bold('6')}  Export profile for AI")
            print(f"{bold('7')}  List backups")
            print(f"{bold('8')}  Restore from backup")
            print(f"{bold('9')}  Restore single package")
            print(f"{bold('w')}  Wireless ADB connect / pair (Wi-Fi)")
            print(f"{bold('0')}  Exit")
            choice = input("\nSelect: ").strip()
            try:
                if choice == "1":
                    self.scan()
                elif choice == "2":
                    old_dry = self.dry_run
                    self.dry_run = True
                    try:
                        self.debloat_tier(1, action="disable", require_confirm=False, auto_snapshot=False)
                    finally:
                        self.dry_run = old_dry
                elif choice == "3":
                    self.debloat_tier(1, action="disable", require_confirm=True, auto_snapshot=True)
                elif choice == "4":
                    self.debloat_tier(2, action="disable", require_confirm=True, auto_snapshot=True)
                elif choice == "5":
                    self.debloat_tier(3, action="disable", require_confirm=True, auto_snapshot=True)
                elif choice == "6":
                    self.export_for_ai()
                elif choice == "7":
                    backups = self.list_backups()
                    if not backups:
                        self.logger.info("No backups found.")
                    for b in backups:
                        dev = b.get("device", {})
                        print(
                            f"  {b['name']}  ({dev.get('manufacturer','?')} {dev.get('model','?')}, "
                            f"{b['package_count']} pkgs, {b['created_at']})"
                        )
                elif choice == "8":
                    ident = input("Backup filename/identifier: ").strip()
                    self.restore(ident, action="auto")
                elif choice == "9":
                    pkg = input("Package name: ").strip()
                    self.restore_pkg(pkg)
                elif choice.lower() == "w":
                    print("\nWireless ADB (Wi-Fi) Setup:")
                    print("  1) Auto-discover via mDNS (searches Wi-Fi automatically)")
                    print("  2) Connect to known IP:Port (e.g. 192.168.1.50:5555)")
                    print("  3) Pair Android 11+ Wireless Debugging (IP:Port + Pairing Code)")
                    print("  4) Switch connected USB phone to Wi-Fi mode (adb tcpip 5555)")
                    subc = input("\nSelect (1/2/3/4): ").strip()
                    if subc == "1":
                        w_addr = self.auto_discover()
                        if w_addr:
                            self.logger.ok(f"Found wireless device: {w_addr}")
                            if self.connect_wireless(w_addr):
                                self.connect()
                                self.load_rules()
                        else:
                            self.logger.warn("No wireless devices detected via mDNS.")
                            self.logger.info("Tip: Ensure Wireless debugging is turned ON in Developer options.")
                    elif subc == "2":
                        addr = input("Device IP:Port (e.g. 192.168.1.50:5555): ").strip()
                        if addr:
                            if self.connect_wireless(addr):
                                self.connect()
                                self.load_rules()
                    elif subc == "3":
                        p_addr = input("Pairing IP:Port (from phone Wireless debugging screen): ").strip()
                        p_code = input("6-digit Pairing Code: ").strip()
                        if p_addr and p_code:
                            if self.pair_wireless(p_addr, p_code):
                                c_addr = input("Connect IP:Port (from main Wireless debugging screen): ").strip()
                                if c_addr:
                                    if self.connect_wireless(c_addr):
                                        self.connect()
                                        self.load_rules()
                    elif subc == "4":
                        rc, out, err = self.adb.tcpip(5555)
                        if rc == 0:
                            self.logger.ok("TCPIP port 5555 enabled. Disconnect USB cable, then select option 1 or 2 to connect via Wi-Fi.")
                        else:
                            self.logger.error(f"Failed to enable TCPIP: {out or err}")
                elif choice == "0":
                    break
                else:
                    self.logger.warn("Invalid choice.")
            except AdbError as exc:
                self.logger.error(str(exc))
            except KeyboardInterrupt:
                print()
                break


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="debloat-engine.py",
        description="AI-Phone-Debloater core engine — safe Android debloating via ADB.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--adb-path", help="Path to adb executable (default: auto-discover)")
    p.add_argument("--serial", help="ADB device serial (for multi-device setups)")
    p.add_argument("--rules-dir", type=Path, help="Directory containing rule JSON files")
    p.add_argument("--backups-dir", type=Path, default=BACKUPS_DIR, help="Backup snapshot directory")
    p.add_argument("--timeout", type=float, default=30.0, help="ADB command timeout in seconds")
    p.add_argument("-q", "--quiet", action="store_true", help="Suppress informational output")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose debug output")
    p.add_argument("--wireless", "-w", help="Connect to wireless ADB device address (e.g. 192.168.1.50:5555)")
    p.add_argument("--auto-discover", action="store_true", help="Automatically discover wireless ADB devices via mDNS/Bonjour")
    p.add_argument("--dry-run", action="store_true", help="Simulate operations without executing")
    p.add_argument("--interactive", "-i", action="store_true", help="Launch interactive terminal menu")
    p.add_argument("--scan", "-s", action="store_true", help="Scan device and classify packages into safety tiers")
    p.add_argument("--export-for-ai", action="store_true", help="Export device package profile to JSON + Markdown")
    p.add_argument("--list-backups", action="store_true", help="List available backup snapshots")

    sub = p.add_subparsers(dest="command", required=False)

    wl = sub.add_parser("wireless", help="Connect or pair with wireless ADB device over Wi-Fi")
    wl.add_argument("address", help="Device IP and port (e.g. 192.168.1.50:5555)")
    wl.add_argument("--pair", help="6-digit pairing code for Android 11+ Wireless Debugging")
    wl.add_argument("--tcpip", action="store_true", help="Enable TCPIP mode on USB device first")

    sub.add_parser("scan", help="Scan device and classify packages into safety tiers")

    dry = sub.add_parser("dry-run", help="Simulate debloat operations (show what would run)")
    dry.add_argument("--tier", type=int, choices=[1, 2, 3], default=1, help="Tier to simulate (default: 1)")

    deb = sub.add_parser("debloat", help="Execute debloat for a tier")
    deb.add_argument("--tier", type=int, choices=[1, 2, 3], required=True, help="Tier to debloat")
    deb.add_argument("--action", choices=["disable", "uninstall"], default="disable", help="Operation (default: disable)")
    deb.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    sub.add_parser("export-for-ai", help="Export device package profile to JSON + Markdown")

    apply_ai = sub.add_parser("apply-ai-plan", help="Validate and execute an AI-generated debloat plan")
    apply_ai.add_argument("plan", type=Path, help="Path to plan JSON file")
    apply_ai.add_argument("--action", choices=["disable", "uninstall"], default="disable")

    restore = sub.add_parser("restore", help="Restore packages from a backup snapshot")
    restore.add_argument("snapshot", nargs="?", help="Snapshot file path or identifier")
    restore.add_argument("--action", choices=["auto", "enable", "install-existing"], default="auto")
    restore.add_argument("--pkg", help="Restore a single package by name (alternative to snapshot)")

    sub.add_parser("list-backups", help="List available backup snapshots")

    sub.add_parser("interactive", help="Interactive menu for non-technical users")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        engine = DebloatEngine(
            adb_path=args.adb_path,
            serial=args.serial,
            rules_dir=args.rules_dir,
            backups_dir=args.backups_dir,
            quiet=args.quiet,
            verbose=args.verbose,
            dry_run=args.dry_run,
            timeout=args.timeout,
        )

        if getattr(args, "wireless", None):
            engine.connect_wireless(args.wireless)

        if getattr(args, "auto_discover", False):
            w_addr = engine.auto_discover()
            if w_addr:
                engine.logger.ok(f"Auto-discovered wireless device: {w_addr}")
                engine.connect_wireless(w_addr)
                engine.connect()
                engine.load_rules()
                engine.logger.ok(f"Device ready: {engine.device.summary()}")
                return 0
            engine.logger.error("No wireless devices found via mDNS/Bonjour discovery.")
            return 1

        if args.command == "wireless":
            if args.pair:
                if not engine.pair_wireless(args.address, args.pair):
                    return 1
            if engine.connect_wireless(args.address):
                engine.connect()
                engine.load_rules()
                return 0
            return 1
        elif args.command == "scan" or getattr(args, "scan", False):
            engine.connect()
            engine.load_rules()
            engine.scan()
        elif args.command == "dry-run":
            engine.dry_run = True
            engine.debloat_tier(args.tier, action="disable", require_confirm=False, auto_snapshot=False)
        elif args.command == "debloat":
            engine._confirmed = bool(args.yes)
            engine.debloat_tier(args.tier, action=args.action, require_confirm=not args.yes, auto_snapshot=True)
        elif args.command == "export-for-ai" or getattr(args, "export_for_ai", False):
            engine.export_for_ai()
        elif args.command == "apply-ai-plan":
            engine.apply_ai_plan(args.plan, action=args.action)
        elif args.command == "restore":
            if args.pkg:
                engine.restore_pkg(args.pkg)
            else:
                ident = args.snapshot or input("Snapshot identifier: ").strip()
                engine.restore(ident, action=args.action)
        elif args.command == "list-backups" or getattr(args, "list_backups", False):
            backups = engine.list_backups()
            if not backups:
                engine.logger.info("No backups found.")
            for b in backups:
                dev = b.get("device", {})
                print(f"  {b['name']}  ({dev.get('manufacturer','?')} {dev.get('model','?')}, {b['package_count']} pkgs, {b['created_at']})")
        elif args.command == "interactive" or getattr(args, "interactive", False) or not args.command:
            engine.interactive()
        else:
            parser.error(f"unknown command: {args.command}")
        return 0
    except AdbError as exc:
        print(f"{red('ERROR:')} {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"{red('UNEXPECTED ERROR:')} {exc}", file=sys.stderr)
        if getattr(args, "verbose", False):
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
