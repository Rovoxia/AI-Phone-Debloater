#!/usr/bin/env python3
"""
AI-Phone-Debloater — Core Debloat Engine
=======================================

Cross-platform (Windows / macOS / Linux) command-line tool for safely
debloating Android devices via ADB.
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
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from connection import ConnectionError, ConnectionManager, ConnectionUI
except ImportError:
    from .connection import ConnectionError, ConnectionManager, ConnectionUI

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

__version__ = load_version()

RULES_DIR_CANDIDATES = [
    PROJECT_ROOT / "cli" / "rules",
    PROJECT_ROOT / "rules",
    Path.cwd() / "rules",
    Path("rules"),
    SCRIPT_DIR.parent / "rules",
]
BACKUPS_DIR = Path.home() / "AiPhoneDebloater" / "backups"
LOCAL_BACKUPS_DIR = PROJECT_ROOT / "cli" / "backups"

TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

# Device manufacturer (first word of ro.product.manufacturer) -> word used in the OEM rule files.
MANUFACTURER_ALIASES: dict[str, str] = {"redmi": "xiaomi", "poco": "xiaomi", "iqoo": "vivo"}

def _load_hardcritical_packages() -> dict[str, str]:
    """Load critical packages from the canonical JSON file, with minimal fallback."""
    for cand in RULES_DIR_CANDIDATES:
        crit_file = cand / "critical-do-not-touch.json"
        if crit_file.is_file():
            try:
                with open(crit_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                rules = data.get("rules") or data.get("packages") or []
                res = {}
                for r in rules:
                    if isinstance(r, dict) and "package" in r:
                        res[r["package"]] = r.get("description") or r.get("name") or "critical system package"
                if res:
                    return res
            except (OSError, ValueError):
                pass
    # Minimal fallback if JSON cannot be loaded
    return {
        "android": "Android core framework",
        "com.android.systemui": "System UI",
        "com.android.phone": "Telephony stack",
        "com.android.server.telecom": "Telecom manager",
        "com.android.settings": "Settings app",
        "com.android.packageinstaller": "Package installer",
        "com.google.android.gms": "Google Play services",
        "com.android.shell": "ADB shell itself",
    }

HARDCRITICAL_PACKAGES: dict[str, str] = _load_hardcritical_packages()

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

def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"): return False
    if os.environ.get("FORCE_COLOR"): return True
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                mode.value |= 0x0004
                return kernel32.SetConsoleMode(handle, mode) != 0
        except (OSError, AttributeError):
            pass
        return False
    return sys.stdout.isatty()

USE_COLOR = _supports_color()

def _c(text: str, code: str) -> str:
    return f"{code}{text}{Color.RESET}" if USE_COLOR else text

def red(text: str): return _c(text, Color.RED)
def green(text: str): return _c(text, Color.GREEN)
def yellow(text: str): return _c(text, Color.YELLOW)
def blue(text: str): return _c(text, Color.BLUE)
def magenta(text: str): return _c(text, Color.MAGENTA)
def cyan(text: str): return _c(text, Color.CYAN)
def bold(text: str): return _c(text, Color.BOLD)
def dim(text: str): return _c(text, Color.DIM)

class Logger:
    def __init__(self, quiet=False, verbose=False):
        self.quiet = quiet
        self.verbose = verbose
    def info(self, msg):
        if not self.quiet: print(msg)
    def ok(self, msg):
        if not self.quiet: print(f"  {green('[OK]')} {msg}")
    def warn(self, msg):
        if not self.quiet: print(f"  {yellow('[WARN]')} {msg}")
    def error(self, msg):
        print(f"  {red('[ERR]')} {msg}", file=sys.stderr)
    def verbose_log(self, msg):
        if self.verbose and not self.quiet: print(f"  {dim('[DBG]')} {msg}")
    def header(self, msg):
        if not self.quiet: print(f"\n{blue(bold(msg))}\n  " + "-" * (len(msg) + 2))
    def section(self, msg):
        if not self.quiet: print(f"\n{cyan(bold(msg))}")

class Progress:
    def __init__(self, logger, label="working"):
        self.logger = logger
        self.label = label
        self._stop = threading.Event()
        self._thread = None
        self._chars = ["|", "/", "-", "\\"] if sys.platform == "win32" else ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    def __enter__(self):
        if not self.logger.quiet and sys.stdout.isatty():
            self._stop.clear()
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self
    def _spin(self):
        i = 0
        while not self._stop.is_set():
            ch = self._chars[i % len(self._chars)]
            sys.stdout.write(f"\r  {cyan(bold(ch))} {self.label}...")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1
        sys.stdout.write("\r" + " " * (len(self.label) + 20) + "\r")
        sys.stdout.flush()
    def __exit__(self, *exc):
        self._stop.set()
        if self._thread: self._thread.join(timeout=0.4)

class DebloatError(RuntimeError): pass
class AdbError(DebloatError): pass

# Android package names: dot-separated Java identifiers ("android" has no dot).
# Anything else is rejected before it can reach a device shell command line.
PACKAGE_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")

def is_valid_package(pkg) -> bool:
    return isinstance(pkg, str) and bool(PACKAGE_RE.match(pkg))

def validate_package(pkg) -> str:
    if not is_valid_package(pkg):
        raise DebloatError(f"Invalid package name: {pkg!r}")
    return pkg

def pm_succeeded(rc, out, err, pkg="") -> bool:
    """pm/cmd often exit 0 (or adb shell v1 always returns 0) while printing a failure."""
    if rc != 0: return False
    text = f"{out}\n{err}"
    if pkg: text = text.replace(pkg, "")
    return not re.search(r"(?i)failure|error:|exception|unknown package|not installed for", text)

def safe_filename(text) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text or "unknown")

def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        raise DebloatError("No interactive input available (stdin closed). Use command-line flags (e.g. --serial, --yes).") from None

def run_cmd(cmd, timeout=30.0, check=False, capture=True, env=None):
    full_env = os.environ.copy()
    if env: full_env.update(env)
    printable = " ".join(str(c) for c in cmd)
    try:
        # stdin=DEVNULL: "adb shell" would otherwise swallow our own piped stdin (answers to prompts).
        proc = subprocess.run(cmd, capture_output=capture, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=full_env, check=False)
    except FileNotFoundError as exc:
        raise AdbError(f"executable not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"command timed out after {timeout:g}s: {printable}") from exc
    except OSError as exc:
        raise AdbError(f"command failed: {printable}: {exc}") from exc
    stdout, stderr = proc.stdout or "", proc.stderr or ""
    if check and proc.returncode != 0:
        raise AdbError(f"command exited {proc.returncode}: {printable}\nstdout: {stdout}\nstderr: {stderr}")
    return proc.returncode, stdout, stderr

class Adb:
    def __init__(self, adb_path=None, serial=None, timeout=30.0, logger=None, connection_mgr=None):
        self.logger = logger or Logger()
        self.timeout = timeout
        self.serial = serial or None
        if adb_path:
            resolved = shutil.which(adb_path) or (adb_path if Path(adb_path).is_file() else None)
            if not resolved:
                raise AdbError(f"adb not found at --adb-path {adb_path}")
            self.adb_path = resolved
        else:
            # Delegate to ConnectionManager's AdbClient for discovery
            self.connection_mgr = connection_mgr
            if connection_mgr:
                self.adb_path = connection_mgr.adb.adb_path
            else:
                raise AdbError("adb not found. Install Android platform-tools, put adb on PATH, set AI_PHONE_DEBLOATER_ADB_PATH or pass --adb-path.")
        if not self.adb_path:
            raise AdbError("adb not found. Install Android platform-tools, put adb on PATH, set AI_PHONE_DEBLOATER_ADB_PATH or pass --adb-path.")

    def _base(self):
        base = [self.adb_path]
        if self.serial: base += ["-s", self.serial]
        return base

    def _run(self, cmd, timeout=None):
        self.logger.verbose_log("$ " + subprocess.list2cmdline([str(c) for c in cmd]))
        rc, out, err = run_cmd(cmd, timeout=timeout or self.timeout)
        if rc != 0: self.logger.verbose_log(f"exit {rc}: {(err or out).strip()[:300]}")
        return rc, out, err

    def shell(self, command: str, timeout=None):
        return self._run(self._base() + ["shell", command], timeout=timeout)

    def devices(self):
        # No "-s": listing must not depend on (or fail because of) the selected serial.
        rc, out, err = self._run([self.adb_path, "devices", "-l"])
        if rc != 0: raise AdbError(f"adb devices failed: {err or out}")
        devices = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"): continue
            parts = line.split()
            if len(parts) < 2: continue
            info = {"serial": parts[0], "state": parts[1]}
            for token in parts[2:]:
                if ":" in token:
                    k, _, v = token.partition(":")
                    info[k] = v
            devices.append(info)
        return devices

    def connect_wireless(self, address: str):
        return self._run([self.adb_path, "connect", address])

    def pair_wireless(self, address: str, code: str):
        return self._run([self.adb_path, "pair", address, code])

    def getprop(self, prop: str, timeout=None):
        if not re.match(r"^[A-Za-z0-9._-]+$", prop): raise DebloatError(f"Invalid property name: {prop!r}")
        try:
            rc, out, _ = self.shell(f"getprop {prop}", timeout=timeout)
        except AdbError as exc:
            self.logger.verbose_log(f"getprop {prop} failed: {exc}")
            return ""
        return out.strip() if rc == 0 else ""

    @staticmethod
    def _parse_packages(out):
        pkgs = []
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                pkgs.append(line[len("package:"):].strip())
        return pkgs

    def pm_list_packages(self, user=None, disabled=False, enabled=False, uninstalled=False, filter_text=None):
        args = ["pm", "list", "packages"]
        if disabled: args.append("-d")
        if enabled: args.append("-e")
        if uninstalled: args.append("-u")
        if user is not None: args += ["--user", str(int(user))]
        if filter_text: args.append(validate_package(filter_text))
        rc, out, err = self.shell(args)
        pkgs = self._parse_packages(out)
        if rc != 0 or (not pkgs and re.search(r"(?i)error|exception|failure", f"{out}\n{err}")):
            raise AdbError(f"pm list packages failed: {(err or out).strip()}")
        return pkgs

    def pm_path(self, package: str):
        _rc, out, _ = self.shell(f"pm path {validate_package(package)}")
        m = re.search(r"package:([^\s]+)", out)
        return m.group(1) if m else ""

    def disable_user(self, package: str, timeout=None):
        return self.shell(f"pm disable-user --user 0 {validate_package(package)}", timeout=timeout)

    def uninstall_user(self, package: str, timeout=None):
        return self.shell(f"pm uninstall -k --user 0 {validate_package(package)}", timeout=timeout)

    def enable(self, package: str, timeout=None):
        return self.shell(f"pm enable --user 0 {validate_package(package)}", timeout=timeout)

    def install_existing(self, package: str, timeout=None):
        validate_package(package)
        rc, out, err = self.shell(f"cmd package install-existing --user 0 {package}", timeout=timeout)
        if pm_succeeded(rc, out, err, package): return rc, out, err
        # Older Android releases only expose install-existing through "pm".
        return self.shell(f"pm install-existing --user 0 {package}", timeout=timeout)

    def _exact_listed(self, package, **kwargs):
        try:
            return package in self.pm_list_packages(filter_text=package, **kwargs)
        except AdbError:
            return False

    def is_installed_user(self, package: str, user=0):
        return self._exact_listed(package, user=user)

    def is_installed_any_user(self, package: str):
        return self._exact_listed(package, uninstalled=True)

class RuleSet:
    def __init__(self, logger=None):
        self.logger = logger or Logger()
        self.critical = set(HARDCRITICAL_PACKAGES.keys())
        self.critical_reasons = dict(HARDCRITICAL_PACKAGES)

    def __init__(self, logger=None):
        self.logger = logger or Logger()
        self.critical = set(HARDCRITICAL_PACKAGES.keys())
        self.critical_reasons = dict(HARDCRITICAL_PACKAGES)
        self.safe = {}
        self.loaded_files = []

    def _load_json(self, path: Path):
        if not path.is_file(): return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            self.logger.error(f"Cannot read rule file {path}: {exc}")
            return None
        if not isinstance(data, dict):
            self.logger.error(f"Rule file {path} is not a JSON object; ignored")
            return None
        return data

    @staticmethod
    def _entries(data):
        entries = data.get("rules") or data.get("packages") or []
        return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []

    def find_rules_dir(self):
        for cand in RULES_DIR_CANDIDATES:
            if cand.is_dir(): return cand
        return None

    def _add_critical(self, pkg, reason):
        self.critical.add(pkg)
        self.critical_reasons[pkg] = reason
        self.safe.pop(pkg, None)

    def _add_safe(self, pkg, tier, reason, source):
        if pkg in self.critical: return
        self.safe[pkg] = {"tier": tier, "reason": reason, "source": source}

    @staticmethod
    def _entry_tier(entry, source):
        raw = entry.get("tier")
        if raw is None:
            raise ValueError(f"{source}: {entry.get('package')} has no tier specified (must be 1, 2 or 3)")
        try:
            tier = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{source}: {entry.get('package')} has invalid tier {raw!r} (must be 1, 2 or 3)")
        if tier not in (1, 2, 3):
            raise ValueError(f"{source}: {entry.get('package')} has invalid tier {raw!r} (must be 1, 2 or 3)")
        return tier

    @staticmethod
    def _matches_manufacturer(path: Path, data, manufacturer: str):
        # ro.product.manufacturer is e.g. "samsung", "Xiaomi", "TECNO MOBILE LIMITED": use the first word.
        words = manufacturer.strip().lower().split()
        if not words: return False
        mfr = MANUFACTURER_ALIASES.get(words[0], words[0])
        haystack = f"{path.stem} {data.get('manufacturer', '')} {data.get('name', '')}".lower()
        return re.search(rf"\b{re.escape(mfr)}\b", haystack) is not None

    def load(self, rules_dir=None, manufacturer=None):
        # Reset so a second load (reconnect / other device) does not mix rule sets.
        self.__init__(self.logger)
        rules_dir = Path(rules_dir) if rules_dir else self.find_rules_dir()
        if not rules_dir or not rules_dir.is_dir():
            raise DebloatError("Rules directory not found (expected cli/rules next to the engine).")
        self.logger.verbose_log(f"Rules directory: {rules_dir}")
        crit_path = rules_dir / "critical-do-not-touch.json"
        data = self._load_json(crit_path)
        if data and self._entries(data):
            self.loaded_files.append(str(crit_path))
            for entry in self._entries(data):
                pkg = entry.get("package")
                if isinstance(pkg, str) and pkg: self._add_critical(pkg, entry.get("description", "critical"))
        else:
            self.logger.error(f"Critical blacklist missing or invalid: {crit_path}. Disable/uninstall will be refused.")
        univ_path = rules_dir / "universal-safe-to-remove.json"
        data = self._load_json(univ_path)
        if data:
            self.loaded_files.append(str(univ_path))
            for entry in self._entries(data):
                pkg = entry.get("package")
                if not is_valid_package(pkg): continue
                try:
                    tier = self._entry_tier(entry, univ_path.name)
                except ValueError as exc:
                    self.logger.error(str(exc))
                    continue
                if tier is not None:
                    self._add_safe(pkg, tier, entry.get("description", ""), univ_path.name)
        oem_files = []
        for rf in sorted(rules_dir.glob("*.json")):
            if rf.name in ("critical-do-not-touch.json", "universal-safe-to-remove.json"): continue
            data = self._load_json(rf)
            if data: oem_files.append((rf, data))
        if manufacturer:
            matched = [(rf, d) for rf, d in oem_files if self._matches_manufacturer(rf, d, manufacturer)]
            if not matched:
                self.logger.warning(f"No OEM rule file matches manufacturer '{manufacturer}'; using universal rules only.")
            oem_files = matched
        for rf, data in oem_files:
            self.loaded_files.append(str(rf))
            self.logger.verbose_log(f"OEM rules: {rf.name}")
            for entry in self._entries(data):
                pkg = entry.get("package")
                if not is_valid_package(pkg): continue
                if pkg in self.critical:
                    self.logger.verbose_log(f"{rf.name}: {pkg} is on the critical blacklist; rule ignored")
                    continue
                try:
                    tier = self._entry_tier(entry, rf.name)
                except ValueError as exc:
                    self.logger.error(str(exc))
                    continue
                reason = entry.get("description", entry.get("reason", ""))
                self._add_safe(pkg, tier, reason, rf.name)

    def is_critical(self, pkg): return pkg in self.critical
    def critical_reason(self, pkg): return self.critical_reasons.get(pkg, "critical")
    def tier_for(self, pkg):
        info = self.safe.get(pkg)
        return int(info["tier"]) if info else None
    def classify(self, pkg):
        if self.is_critical(pkg): return 4, self.critical_reason(pkg), "critical"
        info = self.safe.get(pkg)
        if info: return int(info["tier"]), info["reason"], info["source"]
        return 0, "not categorized", "unknown"

class DeviceInfo:
    def __init__(self, adb, logger):
        self.adb = adb
        self.logger = logger
        self.serial = ""
        self.state = ""
        self.manufacturer = ""
        self.model = ""
        self.release = ""
        self.security_patch = ""
        self.build_id = ""
        self.architecture = ""
        self.sdk_int = ""

    def populate(self):
        props = {
            "manufacturer": "ro.product.manufacturer",
            "model": "ro.product.model",
            "release": "ro.build.version.release",
            "security_patch": "ro.build.version.security_patch",
            "build_id": "ro.build.display.id",
            "architecture": "ro.product.cpu.abi",
            "sdk_int": "ro.build.version.sdk",
        }
        for k, p in props.items():
            setattr(self, k, self.adb.getprop(p) or "unknown")

    def summary(self):
        return f"{bold(self.manufacturer)} {self.model} (Android {self.release}, SDK {self.sdk_int})"

    def to_dict(self):
        return {
            "serial": self.serial, "state": self.state, "manufacturer": self.manufacturer,
            "model": self.model, "release": self.release, "security_patch": self.security_patch,
            "build_id": self.build_id, "architecture": self.architecture, "sdk_int": self.sdk_int
        }

class SnapshotManager:
    def __init__(self, backups_dir, logger):
        self.backups_dir = backups_dir
        self.logger = logger
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def snapshot_path(self, model, ts=None):
        ts = ts or datetime.now().strftime(TIMESTAMP_FORMAT)
        path = self.backups_dir / f"snapshot_{safe_filename(model)}_{ts}.json"
        n = 1
        while path.exists():  # two snapshots in the same second must not overwrite each other
            path = self.backups_dir / f"snapshot_{safe_filename(model)}_{ts}_{n}.json"
            n += 1
        return path

    def create(self, device, packages_meta, adb, targeted_pkgs=None):
        """Record the pre-change state (user 0) of the packages about to be changed."""
        ts = datetime.now().strftime(TIMESTAMP_FORMAT)
        path = self.snapshot_path(device.model, ts)
        enabled_set = set(adb.pm_list_packages(user=0, enabled=True))
        user0_set = set(adb.pm_list_packages(user=0))
        meta_by_name = {}
        for pkg in packages_meta or []:
            if isinstance(pkg, dict) and pkg.get("name"): meta_by_name[pkg["name"]] = pkg
            elif isinstance(pkg, str): meta_by_name[pkg] = {"name": pkg}
        names = list(targeted_pkgs) if targeted_pkgs is not None else list(meta_by_name)
        entries = []
        for name in names:
            meta = meta_by_name.get(name, {})
            entries.append({
                "name": name, "enabled": name in enabled_set, "installed_user0": name in user0_set,
                "tier": meta.get("tier", 0), "reason": meta.get("reason", ""), "source": meta.get("source", "")
            })
        snapshot = {"created_at": datetime.now().isoformat(), "timestamp": ts, "device": device.to_dict(), "package_count": len(entries), "packages": entries}
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh: json.dump(snapshot, fh, indent=2)
        os.replace(tmp, path)
        self.logger.ok(f"Snapshot written: {path}")
        return path

    def load(self, path):
        try:
            with Path(path).open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise DebloatError(f"Cannot read snapshot {path}: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("packages"), list):
            raise DebloatError(f"Not a valid snapshot file: {path}")
        return data

    @property
    def snapshot_search_dirs(self):
        dirs = [self.backups_dir]
        if LOCAL_BACKUPS_DIR.exists() and LOCAL_BACKUPS_DIR != self.backups_dir:
            dirs.append(LOCAL_BACKUPS_DIR)
        return dirs

    def list_backups(self):
        results = []
        seen = set()
        for b_dir in self.snapshot_search_dirs:
            if not b_dir.exists(): continue
            for path in sorted(b_dir.glob("snapshot_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                if path.name in seen: continue
                seen.add(path.name)
                try:
                    with path.open("r", encoding="utf-8") as fh: data = json.load(fh)
                    if not isinstance(data, dict): raise TypeError("not a JSON object")
                    results.append({"path": str(path), "name": path.name, "created_at": data.get("created_at"), "device": data.get("device") or {}, "package_count": data.get("package_count")})
                except (OSError, ValueError) as exc:
                    self.logger.warning(f"Skipping unreadable snapshot {path.name}: {exc}")
        results.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return results

    def find_backup(self, ident):
        ident = str(ident or "").strip()
        if not ident: return None
        p = Path(ident)
        if p.is_file(): return p
        matches = []
        for b_dir in self.snapshot_search_dirs:
            cand = b_dir / ident
            if cand.is_file(): return cand
            m = sorted(b_dir.glob("snapshot_*.json"), key=lambda q: q.stat().st_mtime, reverse=True)
            matches.extend([q for q in m if ident in q.name])
        seen = set()
        unique = []
        for q in matches:
            if q.name not in seen:
                seen.add(q.name)
                unique.append(q)
        if len(unique) > 1:
            raise DebloatError(f"'{ident}' matches {len(unique)} snapshots; be more specific: " + ", ".join(q.name for q in unique[:5]))
        return unique[0] if unique else None

class DebloatEngine:
    def __init__(self, adb_path=None, serial=None, rules_dir=None, backups_dir=BACKUPS_DIR, quiet=False, verbose=False, dry_run=False, timeout=30.0,
                 assume_yes=False, manufacturer=None):
        self.logger = Logger(quiet, verbose)
        self.dry_run = dry_run
        self.timeout = timeout
        self.rules_dir = rules_dir
        self.manufacturer_override = manufacturer
        self.connection_mgr = ConnectionManager(adb_path=adb_path, timeout=timeout, logger_obj=self.logger)
        self.connection_ui = ConnectionUI(self.connection_mgr)
        self.adb = Adb(self.connection_mgr.adb.adb_path, serial or os.environ.get("ANDROID_SERIAL"), timeout, self.logger)
        self.device = DeviceInfo(self.adb, self.logger)
        self.rules = RuleSet(self.logger)
        self.snapshot_mgr = SnapshotManager(Path(backups_dir), self.logger)
        self._confirmed = bool(assume_yes)
        self._connected = False
        self._rules_loaded = False
        self.last_scan: list[dict[str, Any]] | None = None

    @staticmethod
    def _tty():
        try:
            if sys.stdin is None or not sys.stdin.isatty(): return False
            if sys.platform == "win32":
                # isatty() is also True for NUL on Windows; only a real console has a console mode.
                import ctypes
                import msvcrt
                handle = msvcrt.get_osfhandle(sys.stdin.fileno())
                return bool(ctypes.windll.kernel32.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(ctypes.c_uint32())))
            return True
        except (AttributeError, ValueError, OSError):
            return False

    def ensure_connected(self):
        if not self._connected: self.connect()

    def ensure_ready(self):
        self.ensure_connected()
        if not self._rules_loaded: self.load_rules(self.manufacturer_override)

    

    def auto_discover(self):
        """Interactive only: the user must pick/confirm the endpoint, never auto-connect to an unknown LAN host."""
        if not self._tty():
            return None
        try:
            services = self.connection_mgr.discover_wireless_devices()
        except OSError as exc:
            self.logger.warning(f"Wireless discovery failed: {exc}")
            return None
        if not services:
            self.logger.info("No wireless ADB devices found.")
            return None
        self.logger.info(f"Found {len(services)} wireless device(s):")
        for i, s in enumerate(services, 1): print(f"  [{i}] {s.name} @ {s.endpoint}")
        choice = ask(f"Select wireless device number (1-{len(services)}, Enter to cancel): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(services):
            return services[int(choice) - 1].endpoint
        if choice: self.logger.warning(f"Invalid selection '{choice}'")
        return None

    def connect_wireless(self, address):
        address = (address or "").strip()
        if not re.match(r"^[A-Za-z0-9._\-\[\]:]+$", address):
            self.logger.error(f"Invalid wireless address: {address!r} (expected IP:Port)")
            return False
        if ":" not in address: address += ":5555"
        try:
            dev = self.connection_mgr.connect_wifi(address, timeout=self.timeout)
        except ConnectionError as exc:
            self.logger.error(f"Wireless connection failed: {exc}")
            return False
        self.logger.ok(f"Connected to wireless ADB: {address}")
        self.adb.serial = dev.serial
        self._connected = False
        return True

    def pair_wireless(self, address, code):
        if not re.match(r"^[A-Za-z0-9._\-\[\]:]+$", address or "") or not re.match(r"^\d{6}$", (code or "").strip()):
            self.logger.error("Pairing needs IP:Port and the 6-digit pairing code.")
            return False
        ok, msg = self.connection_mgr.pair_wireless_code(address, code.strip(), timeout=20.0)
        if ok:
            self.logger.ok(f"Successfully paired with {address}")
            return True
        self.logger.error(f"Pairing failed: {msg}")
        return False

    def connect(self):
        self.logger.header("ADB Discovery & Device Detection")
        self._connected = False
        self._rules_loaded = False

        dev = None
        if self.adb.serial:
            target = self.adb.serial
            with Progress(self.logger, f"Connecting to specified device {target}"):
                try:
                    if ":" in target:
                        dev = self.connection_mgr.connect_wifi(target, timeout=self.timeout)
                    else:
                        dev = self.connection_mgr.connect_usb(serial=target, timeout=self.timeout)
                except Exception as exc:
                    raise AdbError(f"Failed to connect to specified device '{target}': {exc}") from exc
        else:
            # Centralized auto-detection priority:
            with Progress(self.logger, "Searching for connected ADB devices"):
                attached = self.connection_mgr.get_attached_devices()

            ready = [d for d in attached if d.is_authorized()]

            if len(ready) == 1:
                dev = ready[0]
                self.connection_mgr.set_active_device(dev)
            elif len(ready) > 1:
                if not self._tty():
                    raise AdbError(
                        "Multiple devices attached; pass --serial (one of: "
                        + ", ".join(d.serial for d in ready)
                        + ")"
                    )
                dev = self.connection_ui.select_device_interactive(ready)
            elif attached:
                # Devices attached but in unauthorized or offline state
                unauth = [d for d in attached if d.state == "unauthorized"]
                if unauth:
                    raise AdbError(
                        f"Device {unauth[0].serial} is unauthorized. Accept the USB debugging prompt on the phone."
                    )
                raise AdbError(
                    "No usable device: "
                    + ", ".join(f"{d.serial} is {d.state}" for d in attached)
                    + ". If 'unauthorized', accept the USB debugging prompt on the phone."
                )
            else:
                # 0 devices attached
                if self._tty():
                    self.logger.info("No Android devices currently detected.")
                    dev = self.connection_ui.connection_wizard()
                    if not dev:
                        raise AdbError("No device connected. Operation cancelled.")
                else:
                    # Non-interactive fallback: attempt to reconnect remembered device
                    remembered = self.connection_mgr.reconnect_remembered(timeout=10.0)
                    if remembered and remembered.is_authorized():
                        dev = remembered
                    else:
                        raise AdbError(
                            "No ADB devices found. Connect via USB (with USB debugging enabled) or Wi-Fi (--wireless IP:Port)."
                        )

        if not dev or not dev.is_authorized():
            raise AdbError(
                f"Device {dev.serial if dev else 'unknown'} is in state '{dev.state if dev else 'unknown'}', not ready."
            )

        self.connection_mgr.set_active_device(dev)
        self.adb.serial = dev.serial
        self.device.serial = dev.serial
        self.device.state = dev.state
        self.device.manufacturer = dev.manufacturer or "unknown"
        self.device.model = dev.model or "unknown"
        self.device.release = dev.release or "unknown"
        self.device.sdk_int = dev.sdk_int or "unknown"
        self.device.security_patch = dev.security_patch or "unknown"
        self.device.build_id = dev.build_id or "unknown"
        self.device.architecture = dev.architecture or "unknown"

        self._connected = True
        self.logger.ok(f"Connected: {self.device.summary()}")

    def switch_transport(self, target_transport: str):
        """Switch active connection between USB and Wi-Fi."""
        self.ensure_connected()
        with Progress(self.logger, f"Switching connection transport to {target_transport}"):
            new_dev = self.connection_mgr.switch_transport(target_transport)
        self.adb.serial = new_dev.serial
        self.device.serial = new_dev.serial
        self.device.state = new_dev.state
        self.logger.ok(f"Transport switched to {target_transport}: {new_dev.serial}")
        return new_dev

    def load_rules(self, manufacturer=None):
        manufacturer = manufacturer or self.manufacturer_override
        mfr = manufacturer or (self.device.manufacturer if self.device.manufacturer not in ("", "unknown") else None)
        with Progress(self.logger, "Loading OEM debloat rule databases"): self.rules.load(self.rules_dir, manufacturer=mfr)
        self._rules_loaded = True
        self.logger.ok(f"Rules loaded ({len(self.rules.loaded_files)} file(s){', OEM: ' + mfr if mfr else ''})")

    def scan(self):
        self.ensure_ready()
        self.logger.section("Scanning installed packages")
        with Progress(self.logger, "Querying package manager"):
            # Two calls total (all + enabled, both for user 0 which every action targets)
            # instead of one "pm list" per package.
            raw = sorted(set(self.adb.pm_list_packages(user=0)))
            enabled_set = set(self.adb.pm_list_packages(user=0, enabled=True))
        results = []
        for name in raw:
            tier, reason, source = self.rules.classify(name)
            results.append({"name": name, "enabled": name in enabled_set, "installed_any_user": True, "tier": tier, "reason": reason, "source": source, "critical": self.rules.is_critical(name)})
        results.sort(key=lambda p: (-p["tier"], p["name"]))
        self.last_scan = results
        self._print_scan(results)
        return results

    def _print_scan(self, results):
        if self.logger.quiet: return
        counts = {1: 0, 2: 0, 3: 0, 4: 0, 0: 0}
        for p in results: counts[p["tier"]] = counts.get(p["tier"], 0) + 1
        self.logger.section("Safety Tier Summary")
        print(f"  {green('Tier 1 (Safe Bloat):')}     {counts.get(1, 0)}")
        print(f"  {yellow('Tier 2 (Advanced):')}       {counts.get(2, 0)}")
        print(f"  {magenta('Tier 3 (Extreme):')}        {counts.get(3, 0)}")
        print(f"  {red('Tier 4 (CRITICAL):')}       {counts.get(4, 0)} (protected)")
        print(f"  {dim('Unknown:')}            {counts.get(0, 0)}")
        self.logger.section("Detailed Listing")
        styles = {4: ("CRITICAL", red), 1: ("Tier 1", green), 2: ("Tier 2", yellow), 3: ("Tier 3", magenta)}
        for p in results:
            text, paint = styles.get(p["tier"], ("Unknown", dim))
            label = paint(f"{text:<10}")  # pad before colouring: ANSI codes break width formatting
            status = "enabled" if p["enabled"] else "disabled"
            print(f"  {label} {p['name']:<45} {status:<12} {p['reason']}")

    def _confirm(self, msg):
        if self._confirmed: return True
        return ask(f"{msg} [y/N]: ").strip().lower() in ("y", "yes")

    def execute_plan(self, packages, action="disable", require_confirm=True, auto_snapshot=True, packages_meta=None):
        if action not in ("disable", "uninstall"):
            raise DebloatError(f"Unknown action: {action}")
        report = {"action": action, "total": len(packages), "dry_run": self.dry_run, "cancelled": False,
                  "executed": [], "failed": [], "skipped_protected": []}
        actionable, seen = [], set()
        for pkg in packages:
            if pkg in seen: continue
            seen.add(pkg)
            if not is_valid_package(pkg):
                report["failed"].append({"package": str(pkg), "error": "invalid package name"})
                self.logger.error(f"Refusing invalid package name: {pkg!r}")
                continue
            if self.rules.is_critical(pkg):
                report["skipped_protected"].append({"package": pkg, "reason": "critical"})
                self.logger.warning(f"Protected (critical), skipped: {pkg}")
                continue
            actionable.append(pkg)
        if not actionable:
            self.logger.info("Nothing to do.")
            return report
        show = print if (require_confirm and not self._confirmed) else self.logger.info  # the user must see what they confirm
        show(f"\nTarget Packages for {action}:")
        for p in actionable: show(f"  - {p}")
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would {action} {len(actionable)} package(s) for user 0. No snapshot written, no changes made.")
            report["planned"] = list(actionable)
            return report
        if require_confirm and not self._confirm(f"Proceed with {action} on {len(actionable)} package(s)?"):
            self.logger.warning("Cancelled; no changes made.")
            report["cancelled"] = True
            return report

        # Pre-mutation safety check: verify active device with ConnectionManager
        is_valid, reason = self.connection_mgr.validate_active_device()
        if not is_valid:
            raise DebloatError(f"Safety verification failed before {action}: {reason}")
        if auto_snapshot:
            try:
                report["snapshot"] = str(self.snapshot_mgr.create(self.device, packages_meta or actionable, self.adb, targeted_pkgs=actionable))
            except (OSError, DebloatError) as exc:
                raise DebloatError(f"Safety snapshot failed, aborting before any change: {exc}") from exc
        else:
            self.logger.warning("No backup snapshot (--no-backup); restore will need the package names.")
        for pkg in actionable:
            try:
                rc, out, err = self.adb.uninstall_user(pkg, self.timeout) if action == "uninstall" else self.adb.disable_user(pkg, self.timeout)
            except AdbError as exc:
                rc, out, err = -1, "", str(exc)
            if pm_succeeded(rc, out, err, pkg):
                report["executed"].append({"package": pkg, "status": "success"})
                self.logger.ok(f"{action}: {pkg}")
            else:
                msg = (err.strip() or out.strip() or f"exit {rc}")
                report["failed"].append({"package": pkg, "error": msg})
                self.logger.error(f"{action} FAILED: {pkg}: {msg}")
        self.logger.info(f"Done: {len(report['executed'])} succeeded, {len(report['failed'])} failed, {len(report['skipped_protected'])} protected.")
        return report

    def debloat_tier(self, tier, action="disable", **kwargs):
        if tier not in (1, 2, 3): raise DebloatError(f"Invalid tier: {tier}")
        results = self.scan()  # scan() connects and loads rules (honouring --manufacturer) once
        candidates = [p for p in results if p["tier"] == tier and not p["critical"]]
        # Already-disabled packages need no "disable" (and would record a misleading snapshot).
        pkgs = [p["name"] for p in candidates if action == "uninstall" or p["enabled"]]
        if not pkgs:
            self.logger.info(f"No packages to {action} for Tier {tier}.")
            return {"action": action, "total": 0, "dry_run": self.dry_run, "cancelled": False, "executed": [], "failed": [], "skipped_protected": []}
        return self.execute_plan(pkgs, action=action, packages_meta=results, **kwargs)

    def export_scan(self, results, out_path=None):
        if out_path:
            path = Path(out_path)
        else:
            ts = datetime.now().strftime(TIMESTAMP_FORMAT)
            path = self.snapshot_mgr.backups_dir / f"scan_{safe_filename(self.device.model)}_{ts}.json"
        try:
            if path.parent: path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                json.dump({"device": self.device.to_dict(), "generated_at": datetime.now().isoformat(), "packages": results}, f, indent=2)
        except OSError as exc:
            raise DebloatError(f"Cannot write export {path}: {exc}") from exc
        self.logger.ok(f"Exported: {path}")
        return path

    def export_for_ai(self):
        results = self.scan()
        ts = datetime.now().strftime(TIMESTAMP_FORMAT)
        base = self.snapshot_mgr.backups_dir / f"device-profile_{safe_filename(self.device.model)}_{ts}"
        json_path = self.export_scan(results, base.with_suffix(".json"))
        md_path = base.with_suffix(".md")
        d = self.device
        lines = [f"# Device profile: {d.manufacturer} {d.model}", "",
                 f"- Android {d.release} (SDK {d.sdk_int}), security patch {d.security_patch}, build {d.build_id}, ABI {d.architecture}", "",
                 "| Package | Tier | Enabled | Reason |", "|---|---|---|---|"]
        for p in results:
            tier = "CRITICAL" if p["tier"] == 4 else (str(p["tier"]) if p["tier"] else "unknown")
            lines.append(f"| {p['name']} | {tier} | {'yes' if p['enabled'] else 'no'} | {str(p['reason']).replace('|', '/')} |")
        try:
            md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            raise DebloatError(f"Cannot write {md_path}: {exc}") from exc
        self.logger.ok(f"Exported: {md_path}")
        return json_path, md_path

    def restore_package(self, pkg, enable=True):
        """Undo "pm uninstall -k --user 0" (install-existing) and/or "pm disable-user" (enable). Returns (ok, message)."""
        validate_package(pkg)
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would restore {pkg} (install-existing{' + enable' if enable else ''}).")
            return True, "dry-run"
        is_valid, reason = self.connection_mgr.validate_active_device()
        if not is_valid:
            return False, f"Safety check failed: {reason}"
        try:
            if not self.adb.is_installed_user(pkg, 0):
                rc, out, err = self.adb.install_existing(pkg, self.timeout)
                if not pm_succeeded(rc, out, err, pkg):
                    return False, f"install-existing failed: {(err or out).strip() or f'exit {rc}'}"
            if enable:
                rc, out, err = self.adb.enable(pkg, self.timeout)
                if not pm_succeeded(rc, out, err, pkg):
                    return False, f"enable failed: {(err or out).strip() or f'exit {rc}'}"
        except AdbError as exc:
            return False, str(exc)
        return True, ""

    def restore(self, ident, action="auto", selected_pkgs=None):
        snap_path = self.snapshot_mgr.find_backup(ident)
        if not snap_path: raise DebloatError(f"Backup not found: {ident}")
        data = self.snapshot_mgr.load(snap_path)
        self.ensure_connected()
        snap_dev = data.get("device") or {}
        if snap_dev.get("serial") and snap_dev.get("serial") != self.device.serial and snap_dev.get("model") != self.device.model:
            self.logger.warning(f"Snapshot was taken on {snap_dev.get('manufacturer', '?')} {snap_dev.get('model', '?')} ({snap_dev.get('serial')}), "
                             f"restoring to {self.device.model} ({self.device.serial}).")
        entries = [e for e in data.get("packages", []) if isinstance(e, dict)]
        if selected_pkgs is not None:
            sel_set = set(selected_pkgs)
            entries = [e for e in entries if e.get("name") in sel_set]
        report = {"snapshot": str(snap_path), "restored": [], "failed": [], "skipped": []}
        for entry in entries:
            pkg = entry.get("name")
            if not is_valid_package(pkg):
                report["failed"].append({"package": str(pkg), "error": "invalid package name"})
                self.logger.error(f"Skipping invalid package name in snapshot: {pkg!r}")
                continue
            if entry.get("installed_user0", True) is False:
                report["skipped"].append(pkg)  # was not installed for user 0 before the change
                continue
            # Restore the recorded pre-change state: a package that was already disabled stays disabled.
            ok, msg = self.restore_package(pkg, enable=bool(entry.get("enabled", True)))
            if ok:
                report["restored"].append(pkg)
                self.logger.ok(f"Restored: {pkg}")
            else:
                report["failed"].append({"package": pkg, "error": msg})
                self.logger.error(f"Restore FAILED: {pkg}: {msg}")
        self.logger.info(f"Restore: {len(report['restored'])} restored, {len(report['failed'])} failed, {len(report['skipped'])} skipped.")
        return report

    def list_backups(self):
        return self.snapshot_mgr.list_backups()

    def _reconnect_wireless(self, address):
        if address and self.connect_wireless(address):
            self.ensure_ready()

    def _interactive_restore(self):
        backups = self.list_backups()
        if not backups:
            self.logger.info("No backup snapshots found.")
            return
        print("\nAvailable Backup Snapshots:")
        for idx, b in enumerate(backups, 1):
            dev = b.get("device") or {}
            print(f"  [{idx}] {b['name']} — {dev.get('manufacturer', '?')} {dev.get('model', '?')} ({b['package_count']} pkgs, {b['created_at']})")
        sel = ask("\nSelect backup number or press Enter for most recent: ").strip()
        if not sel:
            target = backups[0]["path"]
        elif sel.isdigit():
            i = int(sel) - 1
            target = backups[i]["path"] if 0 <= i < len(backups) else None
        else:
            found = self.snapshot_mgr.find_backup(sel)
            target = str(found) if found else None
        if not target:
            self.logger.warning("Invalid selection.")
            return
        data = self.snapshot_mgr.load(Path(target))
        pkgs = [p for p in data.get("packages", []) if isinstance(p, dict)]
        print(f"\nPackages in snapshot ({len(pkgs)}):")
        for p_idx, p_entry in enumerate(pkgs, 1):
            print(f"  [{p_idx}] {p_entry.get('name')} (Tier {p_entry.get('tier', '?')}) — {p_entry.get('reason', '')}")
        print("\nRestore options:")
        print("  [a] Restore ALL packages")
        print("  [s] Select specific packages by number (e.g. 1,3,5)")
        sub_sel = ask("Choose option [a/s] (default 'a'): ").strip().lower()
        if sub_sel == "s":
            nums_str = ask("Enter package numbers separated by comma: ").strip()
            chosen_indices = [int(n.strip()) - 1 for n in nums_str.split(",") if n.strip().isdigit()]
            chosen_pkgs = [pkgs[i].get("name") for i in chosen_indices if 0 <= i < len(pkgs)]
            if chosen_pkgs:
                self.restore(target, action="auto", selected_pkgs=chosen_pkgs)
            else:
                self.logger.warning("No valid packages selected.")
        elif sub_sel in ("", "a"):
            self.restore(target, action="auto")
        else:
            self.logger.warning("Invalid option; nothing restored.")

    def interactive(self):
        self.logger.header(f"AI-Phone-Debloater v{__version__} — Interactive Mode")
        try:
            self.ensure_ready()
        except DebloatError as exc:
            self.logger.warning(f"Initial connection: {exc}")
            self.logger.info("Tip: Select 'w' to connect wirelessly.")

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
            print(f"{bold('w')}  Wireless ADB connect / QR pairing (Wi-Fi)")
            print(f"{bold('d')}  Run connection diagnostics")
            print(f"{bold('s')}  Switch connection transport (USB <-> Wi-Fi)")
            print(f"{bold('c')}  Device connection wizard / select device")
            print(f"{bold('0')}  Exit")
            try:
                choice = input("\nSelect: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                if choice == "1": self.scan()
                elif choice == "2":
                    old = self.dry_run
                    self.dry_run = True
                    try:
                        self.debloat_tier(1, action="disable", require_confirm=False, auto_snapshot=True)
                    finally:
                        self.dry_run = old
                elif choice == "3": self.debloat_tier(1, action="disable", require_confirm=True, auto_snapshot=True)
                elif choice == "4": self.debloat_tier(2, action="disable", require_confirm=True, auto_snapshot=True)
                elif choice == "5": self.debloat_tier(3, action="disable", require_confirm=True, auto_snapshot=True)
                elif choice == "6": self.export_for_ai()
                elif choice == "7":
                    backups = self.list_backups()
                    if not backups: self.logger.info("No backup snapshots found.")
                    for b in backups: print(f"  {b['name']} ({b['package_count']} pkgs, {b['created_at']})")
                elif choice == "8": self._interactive_restore()
                elif choice == "9":
                    pkg = ask("Package name: ").strip()
                    if not pkg:
                        self.logger.warning("No package name entered")
                        continue
                    self.ensure_connected()
                    ok, msg = self.restore_package(pkg, enable=True)
                    if ok: self.logger.ok(f"Restored {pkg}")
                    else: self.logger.error(f"Restore FAILED: {pkg}: {msg}")
                elif choice.lower() == "w":
                    print("\nWireless ADB Setup:")
                    print("  1) Pair via QR code (Android 11+ Wireless Debugging)")
                    print("  2) Connect directly to IP:Port")
                    print("  3) Pair with 6-digit code and connect")
                    print("  4) Auto-discover endpoints via mDNS / LAN")
                    sub = ask("\nSelect (1/2/3/4, Enter to cancel): ").strip()
                    if sub == "1":
                        dev = self.connection_ui.handle_qr_flow()
                        if dev:
                            self._connected = False
                            self.ensure_ready()
                    elif sub == "2":
                        self._reconnect_wireless(ask("IP:Port: ").strip())
                    elif sub == "3":
                        pa = ask("Pairing IP:Port: ").strip()
                        pc = ask("Pairing Code: ").strip()
                        if pa and pc and self.pair_wireless(pa, pc):
                            self._reconnect_wireless(ask("Connect IP:Port: ").strip())
                    elif sub == "4":
                        self._reconnect_wireless(self.auto_discover())
                elif choice.lower() == "d":
                    self.connection_ui.handle_diagnostics_flow()
                elif choice.lower() == "s":
                    target = ask("Switch to transport [usb/wireless]: ").strip().lower()
                    if target in ("usb", "wireless"):
                        try:
                            self.switch_transport(target)
                        except (OSError, AdbError) as exc:
                            self.logger.error(f"Switch transport failed: {exc}")
                    else:
                        self.logger.warning("Invalid transport. Enter 'usb' or 'wireless'.")
                elif choice.lower() == "c":
                    dev = self.connection_ui.connection_wizard()
                    if dev:
                        self._connected = False
                        self.ensure_ready()
                elif choice == "0": break
                elif choice: self.logger.warning(f"Unknown option '{choice}'")
            except (DebloatError, OSError) as exc: self.logger.error(str(exc))
            except KeyboardInterrupt: print(); break

def build_parser():
    p = argparse.ArgumentParser(description="AI-Phone-Debloater Core Engine")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--interactive", "-i", action="store_true", help="Interactive menu (default when no action is given)")
    p.add_argument("--scan", "-s", action="store_true", help="Scan and classify installed packages")
    p.add_argument("--tier", type=int, choices=[1, 2, 3], help="Target safety tier (1=Safe, 2=Advanced, 3=Extreme)")
    p.add_argument("--action", choices=["disable", "uninstall"], default=None, help="Debloat action for --tier (default: disable)")
    p.add_argument("--wireless", "-w", help="Connect to wireless ADB device (IP:Port)")
    p.add_argument("--qr-pair", action="store_true", help="Connect wirelessly via Android 11+ QR code pairing")
    p.add_argument("--diagnostics", action="store_true", help="Run comprehensive connection diagnostics (ADB, USB, Wireless)")
    p.add_argument("--switch-transport", choices=["usb", "wireless"], help="Switch active connection between USB and Wi-Fi")
    p.add_argument("--manufacturer", "-m", help="Force OEM rules (e.g., samsung, xiaomi, oneplus)")
    p.add_argument("--dry-run", action="store_true", help="Simulate without making changes")
    p.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    p.add_argument("--verbose", "-v", action="store_true", help="Show debug info")
    p.add_argument("--no-backup", action="store_true", help="Skip automatic backup snapshot")
    p.add_argument("--export-json", nargs="?", const=True, metavar="PATH", help="Export scan results as JSON (optionally to PATH)")
    p.add_argument("--serial", help="ADB serial of the device to use when several are attached (default: $ANDROID_SERIAL)")
    p.add_argument("--adb-path", help="Path to the adb executable (default: PATH, bundled platform-tools, $AI_PHONE_DEBLOATER_ADB_PATH)")
    p.add_argument("--yes", "-y", action="store_true", help="Do not ask for confirmation (required for --tier without a terminal)")
    p.add_argument("--restore", metavar="SNAPSHOT", help="Restore packages from a backup snapshot (file name, path or unique part of the name)")
    return p

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    export_path = args.export_json if isinstance(args.export_json, str) else None
    export = bool(args.export_json)
    if args.restore and (args.tier or args.scan or export):
        parser.error("--restore cannot be combined with --scan/--tier/--export-json")
    if args.action and not args.tier:
        parser.error("--action requires --tier")
    has_action = bool(args.scan or args.tier or args.restore or export or args.diagnostics or args.qr_pair or args.switch_transport)
    if not has_action and not args.interactive and not DebloatEngine._tty():
        parser.error("no action given and stdin is not a terminal; use --scan, --tier N, --diagnostics, --qr-pair or --restore SNAPSHOT")

    logger = Logger(args.quiet, args.verbose)
    try:
        engine = DebloatEngine(adb_path=args.adb_path, serial=args.serial, quiet=args.quiet, verbose=args.verbose,
                               dry_run=args.dry_run, assume_yes=args.yes, manufacturer=args.manufacturer)
        if args.diagnostics:
            engine.connection_ui.handle_diagnostics_flow()
            return 0
        if args.qr_pair:
            dev = engine.connection_ui.handle_qr_flow()
            return 0 if dev else 1
        if args.switch_transport:
            engine.ensure_connected()
            engine.switch_transport(args.switch_transport)
            return 0
        if args.wireless and not engine.connect_wireless(args.wireless):
            return 1
        if args.restore:
            report = engine.restore(args.restore)
            return 1 if report["failed"] else 0
        if args.tier:
            report = engine.debloat_tier(args.tier, action=args.action or "disable", auto_snapshot=not args.no_backup)
            if export and engine.last_scan is not None:
                engine.export_scan(engine.last_scan, export_path)
            return 1 if (report.get("failed") or report.get("cancelled")) else 0
        if args.scan or export:
            results = engine.scan()
            if export: engine.export_scan(results, export_path)
            return 0
        engine.interactive()
        return 0
    except DebloatError as exc:
        logger.error(str(exc))
        return 1
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130

if __name__ == "__main__":
    sys.exit(main())
