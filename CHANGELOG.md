# Changelog

All notable changes to AI-Phone-Debloater are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-11-10

### Added

- In-browser WebApp Workspace at `/app` (`web/src/pages/app.astro`) with direct WebUSB ADB connection via `@yume-chan/adb`
- Universal 1-click Local ADB Bridge for cross-browser support (Firefox, Safari, driver-locked environments):
  - Windows: `irm https://debloater.rovoxia.com/bridge.ps1 | iex`
  - macOS / Linux: `curl -sSL https://debloater.rovoxia.com/bridge.sh | bash`
- Standalone Python standard library bridge server (`cli/src/bridge_server.py`) on `127.0.0.1:53123`
- Defense-in-depth enforcement of 89 Tier 4 critical packages across browser UI, WebADB client, and bridge server
- Pre-mutation snapshot backups with JSON export, import, and 1-click restore
- Interactive execution drawer, dry-run simulation mode, and search filters

## [1.0.1] - 2026-11-10

### Added

- Social media Open Graph poster (`og-image.png` & `og-image.jpg`)
- AI search discovery files (`llms.txt`, `llms-full.txt`, `robots.txt`, `pricing.md`)
- Supported OEMs package matrix sync (352 rules)

## [1.0.0] - 2026-11-03

### Added

- Initial public release of AI-Phone-Debloater
- Cross-platform CLI (`debloat.bat` / `debloat.sh`) with Python/ADB auto-bootstrap
- 10 curated OEM rule databases (324 packages) + critical core blacklist (89 packages)
- 4 safety tiers (Safe/Advanced/Extreme/Critical-hard-blocked)
- User-0 preservation architecture (`pm disable-user`, `pm uninstall -k`)
- Automatic snapshot backups (`~/AiPhoneDebloater/backups/`)
- Interactive TUI dashboard with wireless ADB + QR pairing (Android 11+)
- Astro + Tailwind web dashboard with rule explorer, OEM directory, FAQ
- Zero-Git runners (`run.sh` / `run.ps1`) for one-line installation
- Connection subsystem test suite (28 tests covering QR pairing, mDNS, ADB client, security validation)
- Security vulnerability scanning (Gitleaks)

### Fixed

- TTY stdin detection for `curl ... | bash` launches (redirects to `/dev/tty`)
- Critical package count corrected: 89 unique Tier 4 packages (was 64+61=125)
- Total rule count corrected: 324 packages across 10 OEM rule files (was 320+)
- `debloat.sh` now execs `--interactive </dev/tty` when piped and TTY available
- Zero-Git runner `run.sh.ts` redirects stdin from `/dev/tty` for interactive menu

### Security

- Non-destructive ADB commands only (no root, no `rm -rf /data`)
- Critical packages hard-blocked against all removal attempts
- Input validation on all package names and ADB endpoints
- Shell injection prevention in wireless connection handlers
- Gitleaks secret scanning in CI
# Release v1.0.1

## Changes
```
Merge pull request #20 from Rovoxia/QA
chore(release): bump version to 1.0.1
feat(seo): add raster og-image poster, AI discovery files, and AEO endpoints
feat(web): update SEO and Open Graph metadata across all pages
Merge pull request #19 from Rovoxia/QA
chore(web): fix CHANGELOG duplicates and package counts
Merge pull request #18 from Rovoxia/QA
fix(web): escape remaining backticks in blog content for Astro build
docs: sync changelogs, versions, and user docs with current state
Merge branch 'main' into QA
chore: update CHANGELOG and add 10 new blog posts with getStaticPaths
```

# Release v1.0.2

## Changes
```
Merge pull request #22 from Rovoxia/release/v1.0.2
chore(release): bump version to 1.0.2 and add Twitter/OG image fixes
```

# Release v1.1.0

## Changes
```
Merge pull request #21 from Rovoxia/QA
Merge branch 'main' into QA (resolve version to 1.1.0)
chore(release): bump version to 1.1.0
feat(seo): add 24-bit RGB og-image and progressive JPEG fallback for Twitter cards
fix(ci): resolve ruff lint errors in bridge server and test suite
feat(webapp): add in-browser WebADB workspace and cross-platform 1-click bridge
```
