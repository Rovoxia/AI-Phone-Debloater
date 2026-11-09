# Changelog

All notable changes to AI-Phone-Debloater are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Enterprise CI/CD pipeline with full cross-platform testing
- Docker images for CLI and Web dashboard published to GHCR
- Connection subsystem test suite (28 tests covering QR pairing, mDNS, ADB client, security validation)
- Security vulnerability scanning (Gitleaks + govulncheck)
- Web dashboard preview smoke test in CI

### Fixed
- TTY stdin detection for `curl ... | bash` launches (redirects to `/dev/tty`)
- Critical package count corrected: 89 unique Tier 4 packages (was 64+61=125)
- Total rule count corrected: 324 packages across 10 OEM rule files (was 320+)
- `debloat.sh` now execs `--interactive </dev/tty` when piped and TTY available
- Zero-Git runner `run.sh.ts` redirects stdin from `/dev/tty` for interactive menu

### Changed
- CI pipeline upgraded from basic lint+test to full lint, validation, test, security, Docker, release, deploy
- Version file (`VERSION`) is now single source of truth consumed by engine and web build

## [1.0.0] - 2026-11-03

### Added
- Initial public release
- Cross-platform CLI (`debloat.bat` / `debloat.sh`) with Python/ADB auto-bootstrap
- 10 curated OEM rule databases (324 packages) + critical core blacklist (89 packages)
- 4 safety tiers (Safe/Advanced/Extreme/Critical-hard-blocked)
- User-0 preservation architecture (`pm disable-user`, `pm uninstall -k`)
- Automatic snapshot backups (`~/AiPhoneDebloater/backups/`)
- Interactive TUI dashboard with wireless ADB + QR pairing (Android 11+)
- Astro + Tailwind web dashboard with rule explorer, OEM directory, FAQ
- Zero-Git runners (`run.sh` / `run.ps1`) for one-line installation

### Security
- Non-destructive ADB commands only (no root, no `rm -rf /data`)
- Critical packages hard-blocked against all removal attempts
- Input validation on all package names and ADB endpoints
- Shell injection prevention in wireless connection handlers
# Release v1.0.0

## Changes
```

```

# Release v1.0.0

## Changes
```

```

# Release v1.0.0

## Changes
```
Merge pull request #17 from Rovoxia/QA
fix(ci): configure GH_TOKEN and write permissions for release workflow
docs: update changelog for v1.0.0
Merge pull request #16 from Rovoxia/QA
chore: remove skills-lock.json from tracking, add to gitignore
chore: remove local agent/skill folders from tracking, add to gitignore
feat(web): add blog engine, newsletter API, AI SEO assets, and marketing governance files
docs: update changelog for v1.0.0
Merge pull request #15 from Rovoxia/QA
fix(ci): use devs@rovoxia.com for changelog commits
fix(ci): use dev@rovoxia.com for changelog commits
fix(ci): make tag pushes trigger release with automatic changelog
Merge pull request #14 from Rovoxia/QA
Revert "fix(engine): remove duplicate RuleSet.__init__ stub causing ruff F811"
fix(engine): remove duplicate RuleSet.__init__ stub causing ruff F811
fix(lint): remove duplicate __init__ in RuleSet causing ruff F811
fix(ci): fix yaml indentation for final-status job
refactor: untangle codebase — single source of truth for critical rules and version
Merge pull request #13 from Rovoxia/QA
fix(ci): remove release/deploy jobs; separate release.yml handles releases only
Merge pull request #12 from Rovoxia/QA
Hide Start Debloating CTA on phone and tablet
feat(ci): add automated release on PR merge to main; skip if VERSION already released
Merge pull request #11 from Rovoxia/QA
fix(ci): remove docker job and Dockerfiles (GHCR lowercase tag fail); simplify release chain
Merge pull request #10 from Rovoxia/QA
fix(ci): bump NODE_VERSION to 22 LTS for Astro 7.4.7
fix(web): upgrade astro 5.18.2→7.4.7 to resolve 5 npm audit vulns (XSS/RCE/SSRF)
fix(ci): run gitleaks binary directly, drop govulncheck
fix(tests): grant executable bit to temporary mock adb binaries on posix
fix(web): replace single-item loop with direct command check in run.sh
fix(ci): set git executable bit on python scripts with shebangs
Fix ruff lint across entire cli/ tree
ci: enterprise CI/CD pipeline with full automation
Merge pull request #9 from Rovoxia/QA
docs: correct critical count and rule count
fix(shell): restore interactive TTY stdin for piped curl|bash launches
Merge pull request #8 from Rovoxia/QA
fix(engine): inject ConnectionManager into Adb for correct adb_path discovery
Merge pull request #7 from Rovoxia/QA
fix(sh): default to --scan when piped (non-interactive) instead of --interactive
Merge pull request #6 from Rovoxia/QA
fix(sh): add Python auto-install via pkg-mgr, same bootstrap as bat
Merge pull request #5 from Rovoxia/QA
fix(sh): align Python error message with bat fix
fix(bat): simplify Python detection; no nested if/goto
Merge pull request #4 from Rovoxia/QA
fix(runners): strip redundant Python bootstrap from run.ps1/run.sh; delegate to debloat.bat/sh
Merge pull request #3 from Rovoxia/QA
fix(bin): fix debloat.bat label scope and add automatic Python bootstrap
fix(bat): bootstrap Python via system PATH instead of tools/python folder
Merge pull request #2 from Rovoxia/QA
fix(connection): sync critical packages, delegate wireless discovery to ConnectionManager, OTA build-id tolerance
Merge pull request #1 from Rovoxia/QA
fix(connection): prevent pairing port as connect port, add regression tests
fix(connection): support domain endpoints, resilient mDNS parsing, and update broadcast name
fix(connection): align QR generator with ISO 18004 and improve mDNS discovery
fix(connection): isolate DeviceRegistry in ConnectionManager tests
feat(cli): implement centralized Android ADB connection system
fix: update exact rule count to 324 and remove SEO/AEO references
docs: optimize README for SEO and Answer Engine Optimization (AEO)
fix(web): align Android trademark notice cleanly to the right beside back-to-top button
fix(web): add Rovoxia link to footer copyright and balance trademark alignment
fix(web): link footer items to FAQ and auto-open accordion targets
fix(web): audit footer targets and enhance OEM rules explorer filtering
feat(web): add OEM rules explorer, animated 404, sitemaps, and SEO optimizations
fix: shell injection in web ADB API route
refactor: complete codebase audit cleanup
refactor: track version via main VERSION file and remove tools/.version
refactor: remove redundant backup migration blocks and simplify snapshot search
fix: preserve tools directory across runs unless version bumped
refactor: remove install.ps1/sh endpoints in favor of run.ps1/sh
fix: migrate json snapshots only and prevent stray file copy
revert: keep installer file copy standard without custom backup filters
fix: prevent backups directory extraction in install directory
chore: ignore all backup folders and snapshot json files
fix: store rollback snapshots in persistent user home directory
feat: preserve backup snapshots on update and refresh ADB on VERSION bump
fix: auto-download Google platform-tools when ADB missing in launchers
docs: add single click button to open raw AI prompt in README
revert: restore original website index.astro
feat: make safety tiers interactive on web and add warning notice to README
docs: add architecture flow poster to README, set OG image & link master prompt
docs: redesign README with comprehensive SEO/AEO and polish markdown docs
feat: streamline rules, enhance safety notice & WebApp CTA, untrack CLAUDE.md
Update repository
```
