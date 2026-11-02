# AI-Phone-Debloater

Safe, AI-powered Android debloater and forensic analysis engine.

🌐 **Official Website:** [https://debloater.rovoxia.com](https://debloater.rovoxia.com)

## Professional Repository Structure

```text
AI-Phone-Debloater/
├── cli/                          # CLI Application & Engine
│   ├── bin/                      # Launchers (debloat.bat, debloat.sh)
│   ├── src/                      # Python source code
│   │   └── debloat_engine.py     # Core debloat & ADB engine
│   ├── rules/                    # Safety tier & OEM rule JSON databases
│   ├── tools/                    # Optional local platform-tools/python (not in repo; used by launchers if present)
│   ├── backups/                  # Safety snapshots (.gitignored)
│   └── tests/                    # Rule validation test suite
├── web/                          # Astro + Tailwind web dashboard (npm run build)
├── prompt/                       # AI Prompts & Forensic Guides
│   └── master-prompt.md          # Master 1-click prompt for any AI agent
├── QUICKSTART.md                 # Quickstart guide
├── SAFETY_GUIDELINES.md          # Safety principles & blacklists
├── CONTRIBUTING.md               # Contribution guide
├── VERSION                       # Global version tracker (v1.0.0)
└── README.md                     # Main documentation
```

---

## Quick Start

### Windows (1-Click Launcher)
Run `cli\bin\debloat.bat`

### macOS / Linux
```bash
bash cli/bin/debloat.sh
```

ADB (Android platform-tools) must be installed and on `PATH`, or placed in `cli/tools/platform-tools`; the launchers add that folder to `PATH` if it exists. They do not download it.

### CLI flags
Extra arguments to a launcher are passed to the engine (no arguments starts `--interactive`):

```bash
bash cli/bin/debloat.sh --scan
bash cli/bin/debloat.sh --tier 1 --action disable --dry-run
python cli/src/debloat_engine.py --help
```

Flags: `--interactive/-i`, `--scan/-s`, `--tier {1,2,3}`, `--action {disable,uninstall}`, `--wireless/-w IP:PORT`, `--serial`, `--adb-path`, `--yes/-y`, `--restore SNAPSHOT`, `--manufacturer/-m`, `--dry-run`, `--quiet/-q`, `--verbose/-v`, `--no-backup`, `--output/-o`, `--export-json`, `--version`. Scripted `--tier` without a terminal requires `--yes`. `--manufacturer` loads only the matching OEM file.

### Tests
```bash
python cli/tests/validate_rules.py
```
