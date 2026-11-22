#!/usr/bin/env python3
"""
AI-Phone-Debloater — Engine tests (no device: adb and the connection layer are mocked)
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TEST_DIR = Path(__file__).resolve().parent
CLI_SRC = TEST_DIR.parent / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

import debloat_engine as eng

BLOAT = "com.example.bloat"        # tier 1 rule, app name "Example Bloat"
NORULE = "com.example.norule"      # installed, no rule
CRITICAL = "com.example.critical"  # on the critical list
INSTALLED = (BLOAT, NORULE, CRITICAL)


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


class EngineTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.adb_file = self.tmp / "bin" / ("adb.exe" if os.name == "nt" else "adb")
        self.adb_file.parent.mkdir()
        self.adb_file.write_text("", encoding="utf-8")
        self.adb_file.chmod(0o755)
        rules = self.tmp / "rules"
        rules.mkdir()
        write_json(rules / "critical-do-not-touch.json", {"rules": [{"package": CRITICAL, "name": "Core", "description": "core"}]})
        write_json(rules / "universal-safe-to-remove.json",
                   {"rules": [{"package": BLOAT, "name": "Example Bloat", "tier": 1, "description": "bloat"}]})
        self.rules_dir = rules
        self.backups = self.tmp / "backups"
        self.commands: list[str] = []
        for target in ("ConnectionManager", "ConnectionUI"):
            p = patch.object(eng, target, MagicMock())
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(eng, "run_cmd", self.fake_run_cmd)
        p.start()
        self.addCleanup(p.stop)

    def fake_run_cmd(self, cmd, timeout=30.0, **_kwargs):
        line = " ".join(cmd[1:])
        self.commands.append(line)
        if "pm list packages" in line:
            return 0, "".join(f"package:{name}\n" for name in INSTALLED), ""
        return 0, "Success", ""

    def make_engine(self, **kwargs):
        engine = eng.DebloatEngine(adb_path=str(self.adb_file), rules_dir=self.rules_dir, backups_dir=self.backups,
                                   quiet=True, assume_yes=True, **kwargs)
        engine.connection_mgr.validate_active_device.return_value = (True, "")
        engine.device.model = "TestPhone"
        engine.device.serial = "SERIAL1"
        engine._connected = True
        return engine

    def mutating(self):
        return [c for c in self.commands if "pm list packages" not in c]


class TestPackageFilter(EngineTestCase):
    def test_named_package_only(self):
        engine = self.make_engine(dry_run=True)
        report = engine.debloat_packages([BLOAT])
        self.assertEqual(report["planned"], [BLOAT])
        self.assertEqual(report["failed"], [])
        self.assertEqual(self.mutating(), [])
        self.assertEqual(engine.rules.label(BLOAT), f"{BLOAT} (Example Bloat)")

    def test_critical_is_refused(self):
        engine = self.make_engine()
        with self.assertRaises(eng.DebloatError) as ctx:
            engine.debloat_packages([BLOAT, CRITICAL], action="uninstall")
        self.assertIn(CRITICAL, str(ctx.exception))
        self.assertEqual(self.mutating(), [])

    def test_hard_critical_is_refused_before_device_access(self):
        engine = self.make_engine()
        with self.assertRaises(eng.DebloatError):
            engine.debloat_packages([next(iter(eng.HARDCRITICAL_PACKAGES))])
        self.assertEqual(self.commands, [])

    def test_invalid_name_is_rejected(self):
        engine = self.make_engine()
        with self.assertRaises(eng.DebloatError):
            engine.debloat_packages(["com.example.bloat; reboot"])
        self.assertEqual(self.commands, [])

    def test_no_rule_package_allowed_with_tier_filter(self):
        engine = self.make_engine(dry_run=True)
        self.assertEqual(engine.debloat_packages([NORULE], action="uninstall")["planned"], [NORULE])
        # --tier keeps only the named packages that are in that tier.
        self.assertEqual(engine.debloat_packages([BLOAT, NORULE], tier=1)["planned"], [BLOAT])

    def test_not_installed_is_reported_as_failed(self):
        engine = self.make_engine(dry_run=True)
        with patch("sys.stderr"):
            report = engine.debloat_packages(["com.example.absent"])
        self.assertEqual([f["package"] for f in report["failed"]], ["com.example.absent"])

    def test_main_returns_non_zero_for_critical(self):
        argv = ["--adb-path", str(self.adb_file), "--package", next(iter(eng.HARDCRITICAL_PACKAGES)), "--dry-run", "--yes"]
        err = io.StringIO()
        with patch("sys.stderr", err), patch.object(eng, "SnapshotManager"):  # main() uses the real backups folder
            self.assertEqual(eng.main(argv), 1)
        self.assertIn("Refusing critical", err.getvalue())
        self.assertEqual(self.commands, [])


class TestUser(EngineTestCase):
    def test_user_reaches_adb_command_and_snapshot(self):
        engine = self.make_engine(user=10)
        report = engine.debloat_packages([BLOAT])
        self.assertEqual(self.mutating(), [f"shell pm disable-user --user 10 {BLOAT}"])
        self.assertTrue(all("--user 10" in c for c in self.commands), self.commands)
        snapshot = json.loads(Path(report["snapshot"]).read_text(encoding="utf-8"))
        self.assertEqual(snapshot["user"], 10)

    def test_default_user_is_zero(self):
        self.make_engine().debloat_packages([BLOAT], action="uninstall")
        self.assertEqual(self.mutating(), [f"shell pm uninstall -k --user 0 {BLOAT}"])

    def test_user_argument_must_be_non_negative_int(self):
        self.assertEqual(eng.build_parser().parse_args(["--user", "10"]).user, 10)
        for bad in ("-1", "abc"):
            with self.assertRaises(SystemExit), patch("sys.stderr"):
                eng.build_parser().parse_args(["--user", bad])


class TestSnapshots(EngineTestCase):
    def write_snapshot(self, name, created_at, **extra):
        self.backups.mkdir(exist_ok=True)
        data = {"created_at": created_at, "device": {"model": "TestPhone", "serial": "SERIAL1"}, "package_count": 1,
                "packages": [{"name": BLOAT, "enabled": True, "installed_user0": True}], **extra}
        write_json(self.backups / name, data)
        return str(self.backups / name)

    def test_restore_without_value_uses_newest_snapshot_and_its_user(self):
        newest = self.write_snapshot("snapshot_TestPhone_20260102_000000.json", "2026-01-02T00:00:00", user=10)
        # Written last (newest mtime) but created earlier: created_at decides.
        self.write_snapshot("snapshot_TestPhone_20260101_000000.json", "2026-01-01T00:00:00")
        report = self.make_engine().restore()
        self.assertEqual(report["snapshot"], newest)
        self.assertEqual(report["restored"], [BLOAT])
        self.assertEqual(self.mutating(), [f"shell pm enable --user 10 {BLOAT}"])

    def test_restore_without_value_skips_other_phones_snapshots(self):
        mine = self.write_snapshot("snapshot_TestPhone_20260101_000000.json", "2026-01-01T00:00:00")
        self.write_snapshot("snapshot_Other_20260102_000000.json", "2026-01-02T00:00:00",
                            device={"model": "OtherPhone", "serial": "SERIAL2"})
        self.assertEqual(self.make_engine().restore()["snapshot"], mine)

    def test_old_snapshot_without_user_restores_user_zero(self):
        path = self.write_snapshot("snapshot_TestPhone_20260101_000000.json", "2026-01-01T00:00:00")
        self.make_engine(user=10).restore(path)
        self.assertEqual(self.mutating(), [f"shell pm enable --user 0 {BLOAT}"])

    def test_restore_without_snapshots_fails(self):
        with self.assertRaises(eng.DebloatError):
            self.make_engine().restore()

    def test_list_snapshots_needs_no_device(self):
        self.write_snapshot("snapshot_TestPhone_20260101_000000.json", "2026-01-01T00:00:00")
        newest = self.write_snapshot("snapshot_TestPhone_20260102_000000.json", "2026-01-02T00:00:00")
        with patch.object(eng, "BACKUPS_DIR", self.backups), patch.object(eng, "LOCAL_BACKUPS_DIR", self.tmp / "none"), \
                patch.object(eng, "DebloatEngine", side_effect=AssertionError("no engine needed")), \
                patch("builtins.print") as printed:
            self.assertEqual(eng.main(["--list-snapshots"]), 0)
        lines = [call.args[0] for call in printed.call_args_list]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith(newest), lines)


class TestAdbDiscovery(EngineTestCase):
    def test_cwd_adb_is_not_picked_up(self):
        planted = self.tmp / "cwd"
        planted.mkdir()
        for name in ("adb", "adb.exe"):
            (planted / name).write_text("", encoding="utf-8")
            (planted / name).chmod(0o755)
        old_cwd = os.getcwd()
        os.chdir(planted)
        self.addCleanup(os.chdir, old_cwd)
        # No bundled adb and no standard install locations: only PATH and the working directory are left.
        with patch.dict(os.environ, {"PATH": "."}), patch.object(eng, "SCRIPT_DIR", self.tmp / "nowhere" / "src"), \
                patch.object(eng.AdbClient, "STANDARD_CANDIDATES", ()):
            os.environ.pop("AI_PHONE_DEBLOATER_ADB_PATH", None)
            os.environ.pop("NoDefaultCurrentDirectoryInExePath", None)  # some shells set it, which hides the problem
            if os.name == "nt":
                self.assertIsNotNone(shutil.which("adb"), "precondition: a bare lookup finds the planted adb.exe")
            self.assertIsNone(eng.discover_adb())
            # A path the user chose still works, and so does a real directory on PATH.
            self.assertEqual(Path(eng.discover_adb(str(planted / "adb"))).resolve(), planted / "adb")
            with patch.dict(os.environ, {"PATH": str(self.adb_file.parent)}):
                self.assertEqual(Path(eng.discover_adb()).resolve(), self.adb_file)

    def test_adb_rejects_a_bare_name(self):
        with self.assertRaises(eng.AdbError):
            eng.Adb("adb")


class TestBridgeFlag(unittest.TestCase):
    def test_allow_origin_is_forwarded(self):
        fake = MagicMock()
        with patch.dict(sys.modules, {"bridge_server": fake}):
            rc = eng.main(["--bridge", "--port", "5", "--allow-origin", "http://localhost:4321", "--allow-origin", "https://x.example"])
        self.assertEqual(rc, 0)
        fake.start_bridge.assert_called_once_with(port=5, allow_origins=["http://localhost:4321", "https://x.example"])

    def test_allow_origin_requires_bridge(self):
        with self.assertRaises(SystemExit), patch("sys.stderr"):
            eng.main(["--allow-origin", "http://localhost:4321", "--scan"])


if __name__ == "__main__":
    unittest.main()
