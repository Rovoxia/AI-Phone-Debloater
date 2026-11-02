# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- **Run CLI / Interactive Dashboard:** `python cli/src/debloat_engine.py --interactive`
- **Scan Device Packages:** `python cli/src/debloat_engine.py --scan`
- **Run Rule Validation Tests:** `python cli/tests/validate_rules.py`
- **Windows Launcher:** `cli\bin\debloat.bat`
- **Unix Launcher:** `bash cli/bin/debloat.sh`
- **Build Web Dashboard:** `cd web && npm install && npm run build`

## Architecture & Structure

Monorepo with three main packages:

- **`cli/`**: Core CLI application & engine
  - `src/debloat_engine.py`: Central engine handling ADB discovery (USB/wireless/mDNS/LAN), device probing, safety tier classification, execution plans, backup snapshots, and terminal interactive menus.
  - `rules/`: JSON databases defining safety tiers (critical blacklists, universal safe-to-remove packages, and OEM-specific rules).
  - `bin/`: Cross-platform launchers with auto-bootstrapping for Python and ADB platform-tools.
  - `tests/`: Validation suites (`validate_rules.py`).
  - `backups/`: Snapshot storage (gitignored).
- **`web/`**: Astro-based web dashboard with Tailwind CSS.
- **`prompt/`**: AI prompting guides and forensic analysis prompts.
- **`VERSION`**: Global version tracker file.

## Details worth knowing

- **Engine is a single stdlib-only Python file** (`cli/src/debloat_engine.py`, no `requirements.txt`). Main classes: `Adb` (subprocess wrapper), `RuleSet`, `DeviceInfo`, `SnapshotManager`, `DebloatEngine`. Useful flags: `--tier 1|2|3`, `--action disable|uninstall`, `--dry-run`, `--no-backup`, `--manufacturer`, `--wireless IP:PORT`, `--export-json`.
- **Safety tiers**: 1 = safe, 2 = advanced, 3 = extreme, 4 = critical (never touch). `RuleSet.load` seeds `HARDCRITICAL_PACKAGES` (hardcoded in the engine) and then adds `critical-do-not-touch.json`. A package in the critical set is dropped from the safe/OEM maps and ignored by `_add_safe`, so critical always wins. Entries with no `tier` get one from their `category` (`_tier_from_category`).
- **Rule file schema**: top-level `name` or `description`, plus a non-empty `rules` (or `packages`) list. Each entry needs `package`. `validate_rules.py` fails if any package in another rules file also appears in `critical-do-not-touch.json`, and it checks that `VERSION` is SemVer.
- **Backup and restore**: before changes the engine writes `cli/backups/snapshot_<model>_<timestamp>.json`, which `restore()` reads (gitignored).
- **Web**: `web/src/data/rules-dataset.json` is a precomputed snapshot of the rules (counts per tier and OEM, plus entries). It is imported by `index.astro`, `app.astro` and `RulesExplorer.astro`. Nothing in the repo regenerates it, so update it by hand when rules change. `web/src/pages/` also serves `install.sh` and `install.ps1` as `.ts` endpoints and an `api/adb.ts` route.
- **No linter or unit-test framework** exists. `validate_rules.py` is the only test.
- **CI is stale**: `.github/workflows/ci.yml` runs `tests/validate_rules.py` and `scripts/debloat-engine.py`, which don't exist in this layout (the real paths are `cli/tests/validate_rules.py` and `cli/src/debloat_engine.py`). `README.md` also still lists `web/index.html` and a `cli/tools/` folder. Check the real tree before trusting either.
- ADB is searched on `PATH`, then `cli/tools/platform-tools/` (gitignored, bootstrapped by the launchers), then a few Windows locations.
