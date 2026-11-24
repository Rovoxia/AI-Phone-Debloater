---
title: 'ADB debloat safety tiers: what do Tier 1 to Tier 4 mean?'
seoTitle: ADB Debloat Safety Tiers Explained
description: What Tier 1 Safe, Tier 2 Advanced, Tier 3 Extreme and Tier 4 Critical mean in AI Phone Debloater, how a package gets its tier, and how Tier 4 is enforced.
answer: >-
  AI Phone Debloater sorts every package rule into four tiers. Tier 1 (Safe) is preinstalled apps, ads
  and telemetry that most people can turn off. Tier 2 (Advanced) is optional features to review one by
  one. Tier 3 (Extreme) is a system updater. Tier 4 (Critical) is core Android, which the tool refuses
  to disable or uninstall.
pubDate: 2026-11-01
updatedDate: 2026-11-23
category: Safety
tags: [Safety tiers, Tier 4, Critical packages, ADB]
tierOverview: true
---

## How does a package get its tier?

From a rule file. The project keeps its rules as JSON files, one per phone maker or group of related brands, plus a universal file for apps that ship on many brands and a critical file for the packages that must never be touched. Each rule names one Android package and gives it an app name, a tier, a category, a description and a suggested action.

When the tool looks at a phone, it loads the critical file first, then the universal file, then the file that matches the phone's manufacturer. Every installed package then falls into one of five groups: the four tiers, or Unknown.

**Unknown** means no rule names the package. The tool lists it and leaves it alone. No tier selects an Unknown package.

## What does each tier mean in practice?

**Tier 1, Safe.** Preloaded partner and carrier apps, the manufacturer's ad and telemetry services, and extras such as Bixby and AR Zone. This is the default tier and the place to start.

**Tier 2, Advanced.** Features that work as designed and that some people rely on: wallets, password managers, desktop modes, theme stores, Android Auto, Digital Wellbeing and accessibility services. Nothing here is junk. Turn an entry off only if you know you do not use that feature.

**Tier 3, Extreme.** One rule: the Transsion OTA updater, `com.transsion.otaupdate`, on Tecno, Infinix and itel phones. Disabling it stops system updates until it is switched back on. On any other brand, Tier 3 selects nothing.

**Tier 4, Critical.** The Android framework, System UI, telephony, Settings, the package installer, Wi-Fi and Bluetooth, the keystore and Google Play services. The stock dialer, contacts storage, SMS app, keyboards and launchers are here too. They are Tier 4, not Tier 3: the tool does not offer them for removal at any level.

The table at the top of this page has the current count for each tier.

## Does "Safe" mean nothing will change?

No. Safe means the project judges that the phone keeps working without the package. It does not mean you will not notice. Turn off Bixby and Bixby stops answering. Turn off a manufacturer's app store and the apps you installed from it stop updating there.

A tier is the project's classification, not a promise. That is why every run starts with a list you can read, and why a snapshot is saved before the first change.

## How does the CLI use tiers?

- `--tier 1`, `--tier 2` and `--tier 3` each select exactly that tier. `--tier 2` does not include Tier 1.
- A tier selects only packages that are installed on the phone. A rule for an app you do not have does nothing.
- `--package` limits the plan to the packages you name, and you can repeat it. Together with `--tier`, a named package is used only if it is in that tier.
- `--dry-run` prints the plan and stops. No snapshot is written and nothing changes.
- Without `--dry-run`, the tool shows the plan and asks you to confirm before it acts.

```bash
python cli/src/debloat_engine.py --scan
python cli/src/debloat_engine.py --tier 1 --dry-run
python cli/src/debloat_engine.py --tier 1
```

The scan prints a count for each tier and then every package with its tier, so you can see how your own phone divides up. `--export-json` writes the same result to a file.

The [web app](/app) shows the same tiers next to each package. It has no dry run. It asks you to confirm before every change.

## How is Tier 4 enforced?

In more than one place, so that one missed check is not enough to disable a core package:

1. **The command-line tool** checks named packages against the critical list before it contacts the phone, and again after the rule files are loaded. If a critical package was named, it refuses the whole command and changes nothing.
2. **The plan step** drops any critical package that reaches it and reports it as protected.
3. **The rule loader** ignores a removal rule for a package that is on the critical list.
4. **The local bridge** that serves the web app checks the same list before it runs a change.
5. **The web app** builds its blocked set from the Tier 4 entries of the rule set and does not act on those packages.
6. **The rule validator**, which runs in the project's automated checks, rejects any rule file that gives a tier to a critical package or lists one package twice.

If the critical file is missing or cannot be read, the command-line tool refuses to scan or change anything.

No flag turns Tier 4 off. `--package` with a critical package name is refused, and `--yes` only skips the confirmation prompt.

## What does each action run, and how is it reversed?

| Action | Command on the phone | Reversed by |
|---|---|---|
| Disable (the default) | `pm disable-user --user 0 <package>` | `pm enable --user 0 <package>` |
| Uninstall for your user (`--action uninstall`) | `pm uninstall -k --user 0 <package>` | `cmd package install-existing --user 0 <package>` |

Both act on one Android user, user 0 unless you pass `--user`. Neither one needs root or an unlocked bootloader, and neither writes to the system partition. With `-k`, the uninstall keeps the app's data.

Before the first change the tool saves a snapshot of the affected packages under `~/AiPhoneDebloater/backups/`. If the snapshot cannot be written, the run stops before anything changes. To go back:

```bash
python cli/src/debloat_engine.py --restore
python cli/src/debloat_engine.py --list-snapshots
```

`--restore` with no name uses the newest snapshot for the connected phone.

## Which tier should you start with?

1. Run a scan, then a dry run of Tier 1. Read the list.
2. Apply Tier 1 and use the phone for a day.
3. Read the Tier 2 list for your brand. Pick single packages with `--package`, or in the web app.
4. Leave Tier 3 alone unless you have a Tecno, Infinix or itel phone and a reason to stop its updates.

## Where to go next

- Guides by brand: [Samsung Galaxy](/blog/samsung-galaxy-debloat-guide-one-ui-6), [Xiaomi, Redmi and POCO](/blog/xiaomi-hyperos-debloat-guide), [Google Pixel](/blog/pixel-debloat-guide-stock-android), or [all guides](/blog).
- [Tecno, Infinix and itel](/blog/transsion-debloat-guide-hios-xos): the one place Tier 3 applies.
- [Protected package list](/oems/critical) and [universal package list](/oems/universal).
- [Debloat or factory reset](/blog/debloat-vs-factory-reset).
