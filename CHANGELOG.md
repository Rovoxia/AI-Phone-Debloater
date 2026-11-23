# Changelog

All notable changes to AI-Phone-Debloater are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Web app: device panel with phone art, connection state and live stats (device, Android version, connection, serial, packages, enabled, disabled, uninstalled, bloat found by tier, protected, selected, last snapshot). Unknown values show a dash
- A page per brand at `/oems/<brand>` with that brand's rules grouped by tier, how to apply them and the matching guide, plus `/oems/critical` listing the protected packages and why they are never changed
- `/oems` shows each rule's description, filters by brand and tier, and a filtered view has a linkable URL
- `/rss.xml` feed for the guides; sitemap `lastmod` for blog URLs
- Light/dark theme toggle, skip link, visible keyboard focus and a web manifest with app icons
- Structured data on every page from one graph (Organization, WebSite, SoftwareApplication, FAQPage, Dataset, BlogPosting, BreadcrumbList), and a CI step that fails on invalid JSON-LD
- Copy buttons on the CLI commands of each brand page; RSS feed discovery link on every indexable page
- Web app: deleting a snapshot asks for confirmation, and a note explains that the tool needs JavaScript when it is turned off

### Changed

- Site redesigned on one shared layout and design system that keeps the earlier look (deep navy dark theme, emerald gradient headline, rounded cards with soft shadows, glass navbar, window-style code blocks): fluid type and spacing from 320px to 2560px, light and dark, self-hosted Inter and JetBrains Mono (no request to Google Fonts)
- Home page rebuilt: new heading and product definition, five-step "How it works", three ways to use it with copy buttons, per-brand rule table, "How to undo a change"; FAQ and its structured data come from one source
- Guides are Markdown files in a content collection; tables, lists and code render as real HTML, and tier counts and package tables are generated from the rule set
- All ten guides rewritten against the rule set
- Web app rebuilt on the shared layout: package list becomes cards on narrow screens, activity log and batch bar share one dock, Snapshots is a modal dialog, package status "Installed" is shown as "Enabled"
- `llms.txt` follows the llms.txt convention with links to every page and guide; `robots.txt` reduced to one allow-all group plus the sitemap
- Social share image redrawn
- URLs no longer redirect: pages are built as flat files, so `/app`, `/oems`, `/blog` and guides answer directly instead of redirecting to a trailing slash
- `/_astro/*` assets are served with long-lived immutable caching
- Web app: the dry-run/live mode switch is removed. Every batch and per-package action opens a confirmation dialog that names the action, device and packages, and runs only after it is confirmed. Dry run remains a CLI feature (`--dry-run`)
- Web app: the batch button names the action and count ("Freeze 3 selected") and is disabled when nothing is selected, and while a snapshot restore runs
- Web app: the activity log keeps the newest 800 lines; the CSV export uses the same status words as the table (Enabled, Disabled, Uninstalled)
- Tier badges read "Tier 1: Safe" to screen readers and in copied text
- The master prompt and the wireless guide use the product's and the pairing button's current names

### Fixed

- Home page structured data was invalid JSON and was ignored by search engines
- Guides no longer contain invented tier tables and counts, unmeasured RAM and battery figures, "tested on" lists, the false "enable OEM unlocking" step, or advice to remove the Samsung keyboard, messages app, launcher and a critical package
- Unmeasured performance figures and absolute guarantees removed from the site, `llms.txt`, `llms-full.txt`, `pricing.md`, the share image and six rule descriptions
- `/oems` counts are computed from the rule set (cards now sum to the total and Huawei is listed); features and brands with no rule were removed
- FAQ structured data now matches the visible FAQ
- Huawei rule file used a lower-case manufacturer name
- QR pairing connects only through the phone's `_adb-tls-connect` port. It no longer picks a legacy `_adb._tcp` entry on port 5555, which failed with "target machine actively refused it"
- QR pairing recognises a phone that adb already auto-connected under its mDNS name, retries the connect step for up to 30 seconds while the port appears, and ignores pairing services whose name does not contain the session name
- The "connect port not announced" pairing error gives steps that apply to both the web app and the CLI
- Missing spaces between words and links or numbers on several pages (HTML whitespace compression setting)
- Commands in running text no longer break after a hyphen; in tables they stay on one line and the table scrolls
- Links and keyboard focus no longer land under the sticky header
- With enlarged text, the header, code captions, wide tables and the web app's status line stay inside the page
- With reduced motion, switching theme on the full package list no longer stalls
- Web app: importing a file that is not a snapshot shows a plain message instead of a parser error
- `llms-full.txt` no longer states Knox or Play Integrity outcomes that the project does not check
- README and home page FAQ no longer say debloating never affects OTA updates: the Tier 3 Transsion updater rule stops them. The README CI badge now shows the real workflow status, and the documented one-liners use `curl -fsSL`

## [1.2.0] - 2026-11-22

### Added

- CLI: `--package NAME` (repeatable) limits the plan to named packages; critical packages are refused with a non-zero exit
- CLI: `--restore` with no value restores the newest snapshot of the connected phone; `--list-snapshots` lists snapshots newest first without a device
- CLI: `--user N` targets another Android user, such as a work profile; snapshots record the user and restore uses it (old snapshots restore user 0)
- CLI: `--bridge` accepts `--allow-origin URL` (repeatable) and forwards it to the bridge
- CLI: the plan and confirmation list show the app name beside each package id
- Web app: in bridge mode, "Pair over Wi-Fi (QR)" pairs and connects an Android 11+ phone by scanning a QR code. The bridge gains token-protected `POST /pair/qr`, `GET /pair/status` and `POST /pair/cancel`, which reuse the CLI's QR pairing code
- Web app: the live-run confirmation lists each package with its app name
- Web app: "Export CSV" downloads the currently filtered package list, with spreadsheet formula injection neutralised
- `.github/dependabot.yml` opens update PRs for the SHA-pinned GitHub Actions

### Security

- Every page ships a Content-Security-Policy: hash-based scripts and styles, no `unsafe-inline` or `unsafe-eval`, connections limited to the site and the local bridge at `http://127.0.0.1:53123`. Inline `onclick`/`onload` handlers and `style` attributes were replaced, and CI fails if built HTML contains one
- `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` and `Referrer-Policy: strict-origin-when-cross-origin` are set in `web/public/_headers` and `web/nginx.conf`
- Local bridge requires a per-session token (`X-Bridge-Token`) on every route except `GET /health`. The one-liner scripts generate it and pass it to the web app in the URL fragment; a bridge started by hand prints the URL to open
- Engine no longer picks up `adb` from the current working directory unless it is passed with `--adb-path` or `AI_PHONE_DEBLOATER_ADB_PATH`
- All GitHub Actions are pinned to full commit SHAs; the release job token is reduced to `contents: write` and the workflow no longer pushes to `main`
- Local bridge no longer loses its Tier 4 guard in the one-liner install layout: rules are resolved relative to the script, and the bridge refuses to start if the critical list is empty
- Local bridge now rejects requests from unknown origins. `Access-Control-Allow-Origin: *` is replaced by an allowlist (`https://debloater.rovoxia.com`, plus origins opted into with `--allow-origin URL`, for example `http://localhost:4321` for local web development), the `Host` header must be loopback (blocks DNS rebinding), and `POST` requires `Content-Type: application/json`
- Package-name validation in the engine and bridge uses `fullmatch`, so a name with a trailing newline can no longer bypass the critical list
- Removed the unauthenticated bridge `POST /shutdown` route and the `--host` flag; the bridge always binds `127.0.0.1`
- Web app derives its Tier 4 set from `rules-dataset.json` instead of a hand-copied list that had drifted from `critical-do-not-touch.json` by 44 packages in each direction
- Removed the `/api/adb` dev endpoint, which ran arbitrary `adb shell` commands from a query parameter
- `debloat.bat` runs the downloaded Python installer only if it carries a valid Authenticode signature from the Python Software Foundation, and checks its exit code
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
- Web app: the batch run button is no longer hidden behind the collapsed terminal drawer on `/app`, and the drawer now expands
- Mobile menu backdrop covers the screen, so tapping outside the menu closes it
- Reconnecting to a remembered phone, or switching from USB to Wi-Fi, no longer saves a different phone found at the same address to `known_devices.json` or leaves it active; the wrong phone is disconnected
- The legacy snapshot folder resolves beside `src/` in both the repository and the installed layout (was `~/cli/backups` when installed)
- Bridge finds `adb.exe` on `PATH` on Windows with Python 3.11
- Bridge reads the request body before rejecting a `POST`, so the client sees the `403`/`415`/`401` instead of a connection reset on Windows
- `bridge.sh` no longer stops when `python3` is missing (the launcher installs it), reports clearly when neither `unzip` nor `python3` can extract the download, and quotes the temp directory in its cleanup trap
- Rules: Transsion categories `ad`, `browser` and `theme_store` normalised to `adware`, `bloatware` and `optional_feature`; the critical `com.android.calendar` entry no longer duplicates the calendar provider's name and description
- Tier 1/2/3 descriptions in README, QUICKSTART, CONTRIBUTING, `llms.txt`, `llms-full.txt`, the master prompt and the home page now match the rule data (Tier 3 is only the Transsion OTA updater; stock dialer, contacts, SMS, keyboards and launchers are Tier 4)
- Unknown paths return a real 404 in `nginx.conf`; sitemap lists all pages
- Home page sample table, README, SAFETY_GUIDELINES, SECURITY, pricing, `llms.txt` and the master prompt corrected to match the code (Python version, flags, rule counts, tier examples, restore commands)

### Changed

- Bridge listens only on the requested port and exits with a clear message if it is in use (the web app only ever used 53123); `--strict-port` is accepted and ignored
- Bridge `GET /packages` accepts `view=installed`
- `validate_rules.py`, `generate_rules_dataset.py` and `astro.config.mjs` no longer rewrite version files. After editing `VERSION`, run `python cli/sync_version.py`; CI now fails on drift
- Remembered devices are stored in `~/AiPhoneDebloater/known_devices.json`, which survives reinstall (the old registry is not migrated)
- Unit tests run with `python -m unittest discover -s cli/tests` in CI and `test_all.bat`, so new test files run automatically
- A GitHub release is created only when `VERSION` changes on `main` (or by manual dispatch), with generated notes. The workflow no longer appends commit lists to this file; add entries under `[Unreleased]` by hand
- Master prompt (`prompt/master-prompt.md`, served at `/prompt.md`) rewritten for AI agents: classification comes from the engine's JSON scan, the new `--package`, `--restore` and `--list-snapshots` flags are used, approval must come from the user in chat, stop conditions and exit codes are stated, and the plan report no longer asks for invented RAM or battery figures
- CI pins ruff to 0.17.6
- `sync_version.py` also writes and checks the root version in `web/package-lock.json`
- Removed unused helpers from the connection layer (ADB client, device registry, connection manager, wireless handler, `DeviceState`)
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
