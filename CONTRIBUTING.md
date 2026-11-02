# Contributing to AI-Phone-Debloater

Thank you for helping make AI-Phone-Debloater safer, broader in OEM coverage, and more efficient. Contributions come primarily in the form of **curated OEM package rules** (JSON files in `cli/rules/`) and improvements to the debloat engine, CLI launchers, and documentation.

Because this tool modifies Android device package state, every contribution is reviewed for safety first. Please read [SAFETY_GUIDELINES.md](SAFETY_GUIDELINES.md) before submitting.

---

## 1. How to contribute new OEM package rules

OEM-specific bloat lists live in `cli/rules/`. Each file is a JSON rule set describing packages that are safe to disable or uninstall for a given manufacturer or device family.

### Steps

1. **Fork the repo** and create a feature branch: `git checkout -b add/oem-<vendor>-rules`.
2. **Add or update a rule file** in `cli/rules/` named `<vendor>-<skin>.json` (lowercase, hyphenated), e.g. `cli/rules/motorola.json` or `cli/rules/sony-xperia.json`.
3. **Follow the rule JSON schema** below. Every package entry must include `package`, `tier`, and a descriptive `description`.
4. **Never include blacklisted/critical packages.** Cross-check against `cli/rules/critical-do-not-touch.json` and the Tier-4 table in [SAFETY_GUIDELINES.md](SAFETY_GUIDELINES.md). The CI validation test rejects any rule that references a critical package.
5. **Provide evidence.** In your pull request, list the OEM, device models, and Android versions you verified the package on:
   ```bash
   adb shell pm list packages -U --user 0 > scan.txt
   ```
6. **Run validation locally** (see section 3) before opening the PR.
7. **Open a pull request** describing the OEM coverage, tiers assigned, and any packages you deliberately excluded.

---

## 2. Rule JSON Schema & Field Reference

### Rule File Structure

```json
{
  "manufacturer": "Samsung",
  "version": "1.0.0",
  "description": "Comprehensive bloatware rules for Samsung Galaxy devices running One UI.",
  "rule": "samsung-oneui",
  "rules": [
    {
      "package": "com.samsung.android.bixby.agent",
      "name": "Bixby Voice Agent",
      "tier": 1,
      "category": "voice_assistant",
      "description": "Primary Bixby voice assistant background service that consumes CPU cycles listening for voice commands.",
      "safe_to_remove": true,
      "recommended_action": "disable"
    }
  ]
}
```

### Field Reference

| Field | Type | Required | Description |
|---|---|---|---|
| `package` | string | **Yes** | Full Android package identifier (e.g., `com.miui.msa.global`). Validated against package regex. |
| `name` | string | Optional | Human-readable app or service name. |
| `tier` | integer | **Yes** | Safety tier: `1` (Safe Bloat), `2` (Advanced), `3` (Extreme). |
| `category` | string | Optional | Functional category (e.g., `adware`, `telemetry`, `voice_assistant`, `cloud`, `carrier`). |
| `description` | string | **Yes** | Clear explanation of what the app does and why it is classified at this tier. |
| `safe_to_remove` | boolean | Optional | `true` if safe to disable or uninstall for user 0. |
| `recommended_action` | string | Optional | `disable` (preferred) or `uninstall`. |

---

## 3. Local Validation & Testing

Before submitting a pull request, run the automated test suite locally:

```bash
# 1. Run Rule Validation Test (Checks JSON syntax, structure, and 0 collisions with Critical Blacklist)
python cli/tests/validate_rules.py

# 2. Compile Python Sources (Syntax & type checking)
python -m py_compile cli/src/debloat_engine.py cli/tests/validate_rules.py

# 3. Test CLI Engine Simulation
python cli/src/debloat_engine.py --help
python cli/src/debloat_engine.py --dry-run --tier 1

# 4. Lint Shell Launchers (Linux/macOS)
bash -n cli/bin/debloat.sh

# 5. Build Web Dashboard (if web files modified)
npm --prefix web run build
```

These checks run automatically in GitHub Actions CI on Ubuntu, Windows, and macOS.

---

## 4. Safety Guidelines for Proposing Package Rules

### Safety Tier Assignment

- **Tier 1 (Safe Bloat — Default):** Carrier apps, preloaded sponsor apps (Netflix, Facebook, Amazon, LinkedIn), OEM ad daemons (`com.miui.msa.global`), tracking loggers. Disabling carries zero negative impact on OS stability.
- **Tier 2 (Advanced Debloat):** OEM cloud sync, secondary voice assistants (Bixby, Celia), Digital Wellbeing, AR Zone / sticker apps. Safe to disable if user does not rely on that specific ecosystem feature.
- **Tier 3 (Extreme / Replacement Required):** Stock Dialer, Contacts, Keyboard, Launcher. **Strict requirement:** User must have a working third-party replacement installed and configured before touching these.
- **Tier 4 (Critical Core — HARD BLOCKED):** Never propose packages in `cli/rules/critical-do-not-touch.json` or core Android subsystems (`com.android.systemui`, telephony stack, keystore, package installer).

### Data Preservation Invariants

- All package modifications must use `pm disable-user --user 0` or `pm uninstall -k --user 0`.
- Direct file deletion (`rm -rf`) and `pm uninstall` without `-k` are strictly prohibited.
- Every action must be 100% reversible via `cmd package install-existing` or `python cli/src/debloat_engine.py --restore <SNAPSHOT>`.

---

## 5. Submitting a Pull Request

1. Ensure your branch is up to date with `main`.
2. Run `python cli/tests/validate_rules.py` locally and verify output shows `Zero collisions`.
3. Open a pull request with a descriptive title and summary of changes.
4. A maintainer will review your rules for OEM accuracy, tier classification, and safety invariants.

---

## Code of Conduct

Be respectful, prioritize device safety over aggressiveness, and when in doubt about an unknown package, classify it cautiously or leave it untouched. Non-destructive, 100% reversible changes and zero bootloop risk are our absolute commitments.
