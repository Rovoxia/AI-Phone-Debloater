# Changelog

All notable changes to AI-Phone-Debloater are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Automated release pipeline on tag push (`v*`) with changelog generation
- Release workflow updates changelog.md and creates GitHub Release

### Fixed

- Release workflow first-release guard disabled via version comparison
- Release workflow tag trigger added for automatic changelog + GitHub Release creation

## [1.0.0] - 2026-11-09

### Added

- Initial public release of AI-Phone-Debloater
- Cross-platform CLI (`debloat.bat` / `debloat.sh`) with Python/ADB auto-bootstrap
- 10 curated OEM rule databases (352 packages) + critical core blacklist (89 packages)
- 4 safety tiers (Safe/Advanced/Extreme/Critical-hard-blocked)
- User-0 preservation architecture (`pm disable-user`, `pm uninstall -k`)
- Automatic snapshot backups (`~/AiPhoneDebloater/backups/`)
- Interactive TUI dashboard with wireless ADB + QR pairing (Android 11+)
- Astro + Tailwind web dashboard with rule explorer, OEM directory, FAQ
- Zero-Git runners (`run.sh` / `run.ps1`) for one-line installation
- Connection subsystem test suite (28 tests covering QR pairing, mDNS, ADB client, security validation)
- Security vulnerability scanning (Gitleaks)
- Web dashboard preview smoke test in CI
- Enterprise CI/CD pipeline with full cross-platform testing

### Fixed

- TTY stdin detection for `curl ... | bash` launches (redirects to `/dev/tty`)
- Critical package count corrected: 89 unique Tier 4 packages (was 64+61=125)
- Total rule count corrected: 352 packages across 10 OEM rule files (was 320+)
- `debloat.sh` now execs `--interactive </dev/tty` when piped and TTY available
- Zero-Git runner `run.sh.ts` redirects stdin from `/dev/tty` for interactive menu

### Security

- Non-destructive ADB commands only (no root, no `rm -rf /data`)
- Critical packages hard-blocked against all removal attempts
- Input validation on all package names and ADB endpoints
- Shell injection prevention in wireless connection handlers
- Gitleaks secret scanning in CI

### Changed

- Version file (`VERSION`) is now single source of truth consumed by engine and web build
- CI pipeline upgraded to full lint, validation, test, security, release automation

## [1.0.0] - 2026-11-03

### Added

- Initial public release
- Cross-platform CLI (`debloat.bat` / `debloat.sh`) with Python/ADB auto-bootstrap
- 10 curated OEM rule databases (352 packages) + critical core blacklist (89 packages)
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
