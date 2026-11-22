# Contributing to AI-Phone-Debloater

Thank you for helping make AI-Phone-Debloater safer, broader in OEM coverage, and more efficient. Contributions come primarily in the form of **curated OEM package rules** (JSON files in `cli/rules/`) and improvements to the debloat engine, CLI launchers, and documentation.

Because this tool modifies Android device package state, every contribution is reviewed for safety first. Please read [SAFETY_GUIDELINES.md](SAFETY_GUIDELINES.md) before submitting.

---

## 1. How to contribute new OEM package rules

OEM-specific bloat lists live in `cli/rules/`. Each file is a JSON rule set describing packages that are safe to disable or uninstall for a given manufacturer or device family.

### Steps

1. **Fork the repo** and create a feature branch from `QA`: `git checkout -b add/oem-<vendor>-rules QA`.
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

Entries in `critical-do-not-touch.json` carry no `tier` field and are treated as Tier 4. They use `"recommended_action": "never"` and carry an extra `severity` key (e.g. `"CRITICAL_BRICK_RISK"`).

---

## 3. Local Validation & Testing

Before submitting a pull request, run the automated test suite locally:

```bash
# 1. Run Rule Validation Test (Checks JSON syntax, structure, and 0 collisions with Critical Blacklist)
python cli/tests/validate_rules.py

# 2. Run all unit tests (engine, connection, bridge server, version SSOT) and the version check
python -m unittest discover -s cli/tests
python cli/sync_version.py --check   # after changing VERSION, run: python cli/sync_version.py
# Single test:
python -m unittest discover -s cli/tests -k test_package_validation

# 3. Compile Python Sources (Syntax & type checking)
python -m py_compile cli/src/debloat_engine.py cli/src/bridge_server.py cli/tests/validate_rules.py cli/tests/test_connection.py cli/tests/test_bridge_server.py

# 4. Lint Python (ruff, same command as CI)
pip install ruff==0.17.6 && ruff check cli/src/debloat_engine.py cli/tests/

# 5. Test CLI Engine Simulation
python cli/src/debloat_engine.py --help
python cli/src/debloat_engine.py --dry-run --tier 1

# 6. Lint Shell Launchers (Linux/macOS)
bash -n cli/bin/debloat.sh
shellcheck cli/bin/debloat.sh

# 7. Build Web Dashboard (if web files modified)
npm --prefix web run build

# 8. Verify web dataset is in sync with cli/rules/*.json (run after changing cli/rules/*)
python cli/generate_rules_dataset.py
git diff --exit-code web/src/data/rules-dataset.json
```

These checks run automatically in GitHub Actions CI on Ubuntu, Windows, and macOS (Python 3.11 + Node 22), across the `lint`, `validate`, `test`, `web-test`, and `security` jobs.

### Changelog and releases

The release workflow (`.github/workflows/release.yml`) creates a GitHub release `v<VERSION>` with generated notes when a push to `main` changes the root `VERSION` file, or on manual dispatch. It does not edit `CHANGELOG.md`: add your entry under `## [Unreleased]` in `CHANGELOG.md` by hand in the same pull request.

To release:

1. Edit `VERSION`.
2. Run `python cli/sync_version.py`.
3. Move the `## [Unreleased]` entries in `CHANGELOG.md` under a new heading for that version.
4. Merge to `main`.

---

## 4. Safety Guidelines for Proposing Package Rules

### Safety Tier Assignment

- **Tier 1 (Safe Bloat — Default):** Carrier apps, preloaded sponsor apps (Netflix, Facebook, Amazon, LinkedIn), OEM ad daemons (`com.miui.msa.global`), telemetry, and OEM extras nobody needs (Bixby, AR Emoji, game hubs, duplicate OEM cloud apps). Disabling carries zero negative impact on OS stability.
- **Tier 2 (Advanced Debloat):** Optional OEM or Google features some users rely on: wallets and Samsung Pass, DeX, Link to Windows, theme stores, Android Auto, Digital Wellbeing, Modes and Routines, accessibility services, OEM accounts/cloud, stock notes/recorder/file apps. Safe to disable if the user does not use that feature.
- **Tier 3 (Extreme):** Packages whose removal costs something real even for users who never open them, such as system updaters (today only `com.transsion.otaupdate`). Stock Dialer, Contacts, SMS, Keyboard and Launcher are Tier 4 and must not be added to OEM files.
- **Tier 4 (Critical Core — HARD BLOCKED):** Never propose packages in `cli/rules/critical-do-not-touch.json` or core Android subsystems (`com.android.systemui`, telephony stack, keystore, package installer).

### Data Preservation Invariants

- All package modifications must use `pm disable-user --user 0` or `pm uninstall -k --user 0`.
- Direct file deletion (`rm -rf`) and `pm uninstall` without `-k` are strictly prohibited.
- Every action must be 100% reversible via `cmd package install-existing` or `python cli/src/debloat_engine.py --restore <SNAPSHOT>`.

---

## 5. Submitting a Pull Request

1. Ensure your branch is up to date with `QA` and open the pull request against `QA` (QA is merged to `main`).
2. Run `python cli/tests/validate_rules.py` locally and verify output shows `Zero collisions`.
3. Open a pull request with a descriptive title and summary of changes.
4. A maintainer will review your rules for OEM accuracy, tier classification, and safety invariants.

---

## Code of Conduct

Be respectful, prioritize device safety over aggressiveness, and when in doubt about an unknown package, classify it cautiously or leave it untouched. Non-destructive, 100% reversible changes and zero bootloop risk are our absolute commitments.
