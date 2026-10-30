# Contributing to AI-Phone-Debloater

Thank you for helping make AI-Phone-Debloater safer and broader in OEM coverage. Contributions come primarily in the form of **new OEM package rules** (JSON files in `rules/`) and improvements to the debloat engine, scripts, and documentation.

Because this tool touches device package state, every contribution is reviewed for safety first. Please read [SAFETY_GUIDELINES.md](SAFETY_GUIDELINES.md) before submitting.

---

## 1. How to contribute new OEM package rules

OEM-specific bloat lists live in `rules/`. Each file is a JSON rule set describing packages that are safe to disable or uninstall for a given manufacturer or device family.

### Steps

1. **Fork the repo** and create a feature branch: `git checkout -b add/oem-<vendor>-rules`.
2. **Add a new rule file** in `rules/` named `<vendor>-safe-to-remove.json` (lowercase, hyphenated), e.g. `rules/google-pixel-safe-to-remove.json`.
3. **Follow the rule JSON schema** below (section 2). Every package must carry a `tier`, `action`, `reason`, and a `dangerous` flag.
4. **Never include blacklisted/critical packages.** Cross-check against `rules/critical-do-not-touch.json` and the Tier-4 table in SAFETY_GUIDELINES.md. The CI rejects any rule that references a critical package.
5. **Provide evidence.** In the pull request, list the OEM, device models, and Android versions you verified the rule against, plus the command used to gather packages:
   ```bash
   adb shell pm list packages -U > scan.txt
   ```
6. **Run validation locally** (see section 3) before opening the PR.
7. **Open a pull request** describing the OEM coverage, tiers used, and any packages you deliberately excluded.

### Where rules are used

The debloat engine loads rule files from `rules/` and merges them with the device scan to produce a per-device debloat plan. Rule files are also consumed by AI agents via the master prompt in `prompts/ai-debloat-system-prompt.md`.

---

## 2. Rule JSON schema and validation requirements

### Rule file structure

```json
{
  "description": "Human-readable description of what this rule covers",
  "rule": "<unique-rule-id>",
  "oem": "Samsung",
  "models": ["SM-G991B", "SM-S901B"],
  "android_versions": ["13", "14"],
  "categories": {
    "tier1-bloatware": [
      {
        "name": "com.samsung.android.bixbyvision",
        "tier": "Tier1",
        "action": "disable",
        "reason": "Bixby vision feature most users do not need",
        "expected_battery_gain": "2-5 min",
        "expected_ram_gain": "5-15 MB",
        "dangerous": false
      }
    ],
    "tier2-advanced": [],
    "tier3-extreme": [],
    "tier4-do-not-touch": []
  }
}
```

### Field reference

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | string | Yes | One- or two-sentence description of the rule's scope. |
| `rule` | string | Yes | Unique machine-readable rule id (kebab-case), e.g. `universal-safe-to-remove`. |
| `oem` | string | No | Target OEM (Samsung, Google, Xiaomi, OnePlus, Oppo, Vivo, Realme, Motorola, …). |
| `models` | string[] | No | Example device models this rule was verified on. |
| `android_versions` | string[] | No | Android versions this rule was verified on. |
| `categories` | object | Yes | Object whose keys are tier names and whose values are arrays of package entries. |

### Package entry schema

Each entry inside a category array must be an object with:

| Field | Type | Required | Allowed values / notes |
|---|---|---|---|
| `name` | string | Yes | Full package name, e.g. `com.samsung.android.bixbyvision`. |
| `tier` | string | Yes | `Tier1`, `Tier2`, `Tier3`, or `Tier4-do-not-touch`. |
| `action` | string | Yes | `disable` or `uninstall-keep-data`. `uninstall` (without `-k`) is not allowed. |
| `reason` | string | Yes | Non-empty one-line purpose statement. |
| `expected_battery_gain` | string | No | Human-readable estimate, e.g. `2-5 min`. |
| `expected_ram_gain` | string | No | Human-readable estimate, e.g. `5-15 MB`. |
| `dangerous` | boolean | Yes | `true` for Tier4 / blacklisted packages, `false` otherwise. |

### Validation requirements

All of the following are enforced by CI (see `.github/workflows/ci.yml`):

1. **Valid JSON.** Every file under `rules/` must parse as JSON.
2. **Required top-level keys.** `description`, `rule`, and `categories` must be present.
3. **Required entry keys.** Every package entry must have `name`, `tier`, `action`, `reason`, and `dangerous`.
4. **Allowed values.** `tier` ∈ {Tier1, Tier2, Tier3, Tier4-do-not-touch}; `action` ∈ {disable, uninstall-keep-data}; `dangerous` must be a boolean.
5. **No critical packages.** No entry's `name` may appear in `rules/critical-do-not-touch.json` or match the Tier-4 blacklist in SAFETY_GUIDELINES.md.
6. **Non-empty reason.** `reason` must be a non-empty string.
7. **`uninstall-keep-data` implies data preservation.** This is the only destructive-sounding action permitted, and it always pairs with `-k`.

### Example: invalid entry (rejected by CI)

```json
{
  "name": "com.android.systemui",
  "tier": "Tier4-do-not-touch",
  "action": "uninstall",
  "reason": "frees up ram",
  "dangerous": false
}
```
Rejected because: `action` is `uninstall` (not `uninstall-keep-data`), `dangerous` is `false` for a Tier4 package, and `com.android.systemui` is on the critical blacklist.

---

## 3. Local validation

Before opening a PR, run:

```bash
# JSON syntax + schema validation (same checks as CI)
python -m json.tool rules/<your-file>.json > /dev/null

# Debloat engine dry-run (no device needed)
python scripts/debloat-engine.py --dry-run --rules rules/<your-file>.json

# Shell / PowerShell lint
bash -n scripts/setup-adb.sh
pwsh -NoProfile -Command "Invoke-ScriptAnalyzer -Path scripts/setup-adb.ps1"   # Windows/PowerShell Core
```

CI will re-run these on Ubuntu, Windows, and macOS.

---

## 4. Safety guidelines for proposing package removals

### Tier assignment rules

- **Tier1** — Pure bloatware/adware that adds no core functionality when disabled. Immediate battery/RAM savings. Default action: `disable`, optionally `uninstall-keep-data`.
- **Tier2** — Advanced bloat (OEM services, voice assistants, digital wellbeing, cloud sync). Disable or uninstall depending on whether functionality is missed.
- **Tier3** — Replaceable core apps (dialer, messaging, keyboard, launcher, gallery). Only remove after confirming a replacement is in place; removal without replacement can break the phone.
- **Tier4-do-not-touch** — Critical system packages. Mark `dangerous: true`. Never propose removal or disabling except as `disable-user` with explicit user acknowledgment.

### General rules for every entry

- Every entry must have a non-empty `reason` and a valid `action`.
- Do not propose removal of a package unless you can state its purpose and the expected effect on battery, RAM, or cold-start speed.
- If two packages do the same job (e.g. two stock PDF readers), pick only one and note the other as "dropped — redundant."
- If a package's purpose is unknown, mark it `unknown`, do not propose removal, and append heuristics for manual review.
- Flag duplicates and conflicts; do not submit overlapping rules from two different OEM files for the same package unless versions differ.

### Packages you must never propose removing

Any package in `rules/critical-do-not-touch.json` or the Tier-4 blacklist table in SAFETY_GUIDELINES.md:
- `com.android.systemui`, `com.android.server.telecom`, `com.android.providers.telephony`, `android.security.keystore`, `com.android.server.telephony.Radio`, `com.android.providers.settings`, `android.hardware.bluetooth.*`, `android.hardware.wifi.*`, `android.hardware.usb.*`, and similar core subsystem packages.

### Data safety

- Proposals must use `pm disable-user` or `pm uninstall -k --user 0` only. Never propose `pm uninstall` without `-k`, never `pm uninstall --force`, and never direct filesystem deletion under `/data`.
- Every proposal must be reversible without a factory reset (via `cmd package install-existing` or `python scripts/debloat-engine.py restore`).

---

## 5. Submitting a pull request

1. Ensure your branch is up to date with the default branch.
2. Run local validation (section 3).
3. In the PR description, include:
   - OEM and device models covered.
   - Tiers used and how many packages per tier.
   - Any packages excluded and why.
   - Confirmation that no blacklisted package is included.
4. A maintainer will review for safety, schema conformance, and OEM accuracy before merging.

---

## Code of conduct

Be respectful, prioritize device safety over aggressiveness, and when in doubt, classify a package as `unknown` rather than proposing removal. Zero data loss and zero bricking risk are non-negotiable.