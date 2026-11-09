# Roadmap

This document outlines the planned evolution of AI-Phone-Debloater beyond v1.0.0. Items are ordered by priority but may shift based on community feedback, contributor bandwidth, and ecosystem changes.

---

## v1.1 — WebApp Completion & UX Polish (Q1 2026)

**Theme**: Complete the in-browser WebADB workspace and harden the landing experience.

### Must-Have
- [ ] **Finish `/app` WebApp page** — Full WebADB terminal in the browser (currently marked "soon" on landing page)
  - Wireless ADB pairing flow via QR code (Android 11+)
  - Live package scan with tier badges
  - Dry-run / execute / rollback from browser
  - Persistent session via localStorage
- [ ] **Sitemap & SEO hardening** — Ensure all public routes generate in sitemap (currently only index, oems, prompt, runners)
- [ ] **llms.txt continuous sync** — Auto-regenerate on release; add CI step
- [ ] **OEM rule count badge** — Dynamic badge showing live rule count from `cli/rules/`

### Should-Have
- [ ] **Dark/light theme persistence** — Already implemented in index.astro; ensure `/app` inherits it
- [ ] **Copy-to-clipboard feedback** — Toast notifications on all copy actions
- [ ] **Keyboard shortcuts** — `?` for help, `/` for search in rules explorer

### Nice-to-Have
- [ ] **Language selector** — English / Chinese / Spanish for landing page

---

## v1.2 — OEM Expansion & Rules Hardening (Q2 2026)

**Theme**: More devices covered, stricter validation.

### Must-Have
- [ ] **Add new OEM rule databases** (priority order by market share):
  - Nothing Phone (Nothing OS)
  - Fairphone
  - ASUS (ZenUI / ROG Phone)
  - Sony (Xperia)
  - Sharp / FCNT
- [ ] **Automated rule validation in CI** — Already present; extend to PR checks for `cli/rules/*.json`
- [ ] **Per-rule provenance** — Add `source` field to each rule entry (official docs, community report, reverse-engineered)
- [ ] **Rule conflict detector** — Warn when same package appears in multiple OEM files with different tiers

### Should-Have
- [ ] **Community rule submission form** — GitHub issue template with required fields (manufacturer, model, Android version, package, tier, justification)
- [ ] **Rules versioning** — Tag rule database versions independently of engine version

---

## v1.3 — Enterprise & Fleet Features (Q3 2026)

**Theme**: Make the tool viable for IT admins managing device fleets.

### Must-Have
- [ ] **JSON/CSV export of scan results** — For inventory and audit trails
- [ ] **Batch profile support** — Define a "corporate debloat profile" (tier + OEM rules) and apply to multiple devices
- [ ] **Dry-run report as artifact** — Machine-readable output for CI/CD gates

### Should-Have
- [ ] **Ansible / Terraform provider** — Community-contributed integration
- [ ] **Microsoft Intune / MDM integration docs** — Guide for deploying via MDM

---

## v2.0 — AI Agent Native Integration (Q4 2026)

**Theme**: First-class citizen in AI coding workflows.

### Must-Have
- [ ] **MCP (Model Context Protocol) server** — Expose engine as an MCP tool so agents can call `scan`, `dry_run`, `debloat`, `restore` programmatically
- [ ] **Structured pricing.md for agents** — Already free/open-source; document this machine-readably
- [ ] **Agent skill file** — Installable skill for Cursor, Windsurf, Cline with prefilled CLI commands

### Should-Have
- [ ] **LLM-eval suite** — Automated tests for master prompt quality across Claude, GPT, Gemini
- [ ] **Prompt observability** — Log which prompts succeed/fail (opt-in, privacy-preserving)

---

## v2.x — Platform & Ecosystem (2027+)

- [ ] **Web-based rule explorer with search/filter** — Currently in `/oems`; add API endpoint for programmatic access
- [ ] **Community forum / Discussions** — Enable GitHub Discussions; migrate FAQ there
- [ ] **Official Docker image** — `docker run --rm -it ai-phone-debloater` for CI environments
- [ ] **Windows MSI / Homebrew formula** — Native installers for non-Python users
- [ ] **Telemetry opt-in** — Anonymous usage stats (rules applied, success rate) to guide rule prioritization

---

## Contributing to the Roadmap

- **Issues** — File a GitHub issue with the `roadmap` label
- **Discussions** — Use GitHub Discussions (to be enabled) for design debates
- **PRs** — Contributions welcome; see `CONTRIBUTING.md`

## Release Cadence

- **Patch** (v1.x.y) — Bug fixes, rule additions, doc updates — as needed
- **Minor** (v1.y.0) — New features, OEM additions — quarterly target
- **Major** (v2.0.0) — Breaking changes, architecture shifts — when justified

All versions follow SemVer as tracked in the root `VERSION` file.

---

*Last updated: 2026-11-09*