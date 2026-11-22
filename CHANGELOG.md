# Changelog

All notable changes to AI-Phone-Debloater are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- Local bridge no longer loses its Tier 4 guard in the one-liner install layout: rules are resolved relative to the script, and the bridge refuses to start if the critical list is empty
- Local bridge now rejects requests from unknown origins. `Access-Control-Allow-Origin: *` is replaced by an allowlist (`https://debloater.rovoxia.com`, `http://localhost:*`, `http://127.0.0.1:*`, plus `--allow-origin URL`), the `Host` header must be loopback (blocks DNS rebinding), and `POST` requires `Content-Type: application/json`
- Package-name validation in the engine and bridge uses `fullmatch`, so a name with a trailing newline can no longer bypass the critical list
- Removed the unauthenticated bridge `POST /shutdown` route and the `--host` flag; the bridge always binds `127.0.0.1`
- Web app derives its Tier 4 set from `rules-dataset.json` instead of a hand-copied list that had drifted from `critical-do-not-touch.json` by 44 packages in each direction
- Removed the `/api/adb` dev endpoint, which ran arbitrary `adb shell` commands from a query parameter
- `debloat.bat` verifies the Authenticode signature of the downloaded Python installer and checks its exit code
- `adb` and `rules/` are no longer loaded from the current working directory
- `VERSION` is validated with a strict SemVer `fullmatch`, and `release.yml` passes the tag to shell steps through `env` instead of inline interpolation
- Installer one-liners use `curl -fsSL`, so an HTTP error page is no longer handed to `unzip`

### Fixed

- Web app: dismissing the confirm dialog by its backdrop left a stale handler that ran the previous package set on the next "Apply live"; the dialog is now a native `<dialog>` with a single close path
- Web app: per-row Freeze/Uninstall in Live mode now asks for confirmation
- Web app: command success is decided by exit code and output, so `Failure [not installed for 0]` is no longer reported as success
- Web app: a live run aborts if its snapshot cannot be saved, and results are written to the correct snapshot
- Web app: packages uninstalled for user 0 show as "Uninstalled"; restore reinstalls then enables, and leaves packages that were disabled before the snapshot alone
- Web app: `?bridge=1` waits up to 20 seconds for the bridge; busy USB interface, unplugged device and multiple bridge devices are handled
- `bridge.sh` aborted on start with `BRIDGE_PORT: unbound variable`; `bridge.ps1` threw in `finally` and hid the bridge output
- Bridge one-liners start through the launcher, so `adb` is downloaded when missing
- `run.sh` no longer leaks its temp directory; served scripts no longer contain a literal CR/LF
- Launchers require Python 3.11+ (the code already did) and report it clearly; `debloat.bat` works from a folder whose name contains `)`
- Missing `adb` now gives a one-line error instead of a traceback
- Every `adb` timeout and missing-binary error in the connection layer raised `AttributeError`
- Reconnect no longer connects to other phones found over mDNS; QR pairing no longer falls back to a different phone or matches an address by substring
- `is_same_physical_device` returned true for two different phones of the same model
- Diagnostics reported "ADB not installed" when `adb` was on `PATH`, and aborted when mDNS discovery failed
- Bridge: URL-encoded serials (wireless devices) are decoded; malformed bodies return `400`; a failed snapshot aborts the apply; critical packages can be enabled and restored; error responses are logged
- Engine refuses to plan or apply changes when the critical list cannot be loaded
- Unknown paths return a real 404 in `nginx.conf`; sitemap lists all pages
- Home page sample table, README, SAFETY_GUIDELINES, SECURITY, pricing, `llms.txt` and the master prompt corrected to match the code (Python version, flags, rule counts, tier examples, restore commands)

### Changed

- Bridge listens only on the requested port and exits with a clear message if it is in use (the web app only ever used 53123); `--strict-port` is accepted and ignored
- Bridge `GET /packages` accepts `view=installed`
- `validate_rules.py`, `generate_rules_dataset.py` and `astro.config.mjs` no longer rewrite version files. After editing `VERSION`, run `python cli/sync_version.py`; CI now fails on drift
- Remembered devices are stored in `~/AiPhoneDebloater/known_devices.json`, which survives reinstall (the old registry is not migrated)
- `test_all.bat` runs the same test scripts as CI
- Contributors target the `QA` branch (CONTRIBUTING)

### Removed

- Launcher modes `dump-rules` and `apply-rules`, which called a script that is not in the repository
- Newsletter form and `/api/newsletter`, which never worked on the static site
- Hand-written `/sitemap.xml`; use `/sitemap-index.xml`

## [1.1.1] - 2026-11-10

### Added

- Single-Source-of-Truth (SSOT) versioning architecture centered on root `VERSION`
- Dedicated standard-library `cli/sync_version.py` utility with `--check` verification gate
- Comprehensive SSOT test suite (`cli/tests/test_version_ssot.py`) validating SemVer formatting and multi-manifest consistency
- Added `sync-version` and `check-version` npm scripts in `web/package.json`
- Automatic version sync hooks in `cli/generate_rules_dataset.py`, `cli/tests/validate_rules.py`, and `web/astro.config.mjs`
- `ReusableThreadingHTTPServer` socket reuse (`allow_reuse_address`) and graceful signal termination in `cli/src/bridge_server.py`

### Changed

- Python CLI engine (`debloat_engine.py`) and Local ADB Bridge (`bridge_server.py`) resolve application version dynamically from root `VERSION`
- Centralized web components (`Navbar`, `Footer`, `404`, `index.astro`) to consume `SITE_VERSION` from `web/src/lib/version.ts`
- Added `--port`, `--host`, and `--strict-port` command line arguments to `bridge_server.py`

### Fixed

- Robust compile-time version injection via Vite define (`__SITE_VERSION__`) in `astro.config.mjs`
- Fixed stale `v1.0.0` header badge in Cloudflare Pages build sandbox caused by runtime relative path resolution

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

# Release v1.1.1

## Changes
```
Merge pull request #23 from Rovoxia/QA
fix(cli): resolve nested list command crash in adb shell and restore python bootstrap in debloat.bat
feat: add CI version drift gate, SSOT test suite, npm scripts, and graceful bridge shutdown
refactor(cli): simplify command string formatting in adb runner
docs: update changelog for v1.1.1 SSOT version architecture
fix(web): prioritize __SITE_VERSION__ Vite compile-time constant in version module
refactor(cli): narrow exception handling and enhance logger compatibility
feat(core): centralize version resolution via package.json and sync_version utility
chore(release): bump version to 1.1.1 and inject version at build time
```
