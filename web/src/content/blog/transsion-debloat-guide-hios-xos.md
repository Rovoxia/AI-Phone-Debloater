---
title: How to debloat Tecno, Infinix and itel phones without root
seoTitle: Tecno, Infinix and itel Debloat Guide
description: Turn off lock screen ads, app recommendations, Palm Store and AHA Games on HiOS and XOS over ADB, without root. Why to leave Tier 3 alone, and how to undo.
answer: >-
  Run AI Phone Debloater over ADB with USB debugging on. For Tecno, Infinix and itel phones, Tier 1
  disables the Transsion ad framework, the lock screen magazine, app recommendation popups, Palm Store,
  AHA Games and telemetry. Leave Tier 3 alone: its one rule switches off the system updater. A snapshot lets you undo any of it.
pubDate: 2026-11-01
updatedDate: 2026-11-23
category: Brand guides
tags: [Tecno, Infinix, itel, HiOS, XOS, Transsion]
oemIds: [transsion]
---

## Which phones use the Transsion rules?

Tecno, Infinix and itel are brands of one company, Transsion, and AI Phone Debloater keeps their rules in one file. It reads the manufacturer name from the phone and loads that file for all three, along with the [universal rules](/oems/universal) for carrier and partner apps. The file is written for HiOS on Tecno and XOS on Infinix.

This is the only brand with rules in all three removable tiers. The table at the top of this page has the counts, and the [full list](#rules) is at the end.

## What does Tier 1 turn off?

Tier 1 (Safe) is mostly advertising and the apps that carry it:

- **Ad services:** the Transsion Ads Framework, the Infinix Ad Service, the App Recommendation Service and the Lockscreen Magazine.
- **Stores and games:** Palm Store, under both of its package names, and AHA Games.
- **Bundled apps:** Transsion Browser, Phone Master, Phone Manager, the Transsion Theme Service, Keyboard Manager and the itel Smart Panel.
- **Telemetry:** Transsion Telemetry and Transsion Global Service.

**What you may notice:**

- The lock screen stops showing sponsored content, and the popups that recommend apps to install stop.
- Palm Store is off. Apps you installed from it no longer update there, so keep it if you depend on it.
- Phone Master and Phone Manager, the cleaner and security apps, are off.
- Transsion Browser is off. Have another browser installed first.
- Keyboard Manager is off. The rule file describes it as a keyboard manager bundled with promotional content. Check that your keyboard still works the way you expect after Tier 1. If it does not, switch the package back on:

```bash
adb shell pm enable --user 0 com.transsion.kbmanager
```

## What is in Tier 2?

Tier 2 (Advanced) is optional apps. Some people use them, so go through the list rather than applying it whole:

- **Carlcare.** Transsion's service and repair app. Keep it if you use the warranty service.
- **Everyday apps:** Calendar, File Manager, Music, Notepad, Recorder and Weather. Turn one off only if you already use something else for the job. Disabling an app does not delete its data, but you cannot open your notes or recordings in it until you switch it back on.
- **Wallet.** Transsion's payment app.
- **Extras:** the Voice Assistant, Game Assistant, Hi Party, the Theme Store and the HiOS Center.

To act on part of Tier 2, name the packages. This previews turning off Hi Party and the Theme Store:

```bash
python cli/src/debloat_engine.py --package com.transsion.hiparty --package com.transsion.themestore --dry-run
```

## Why should you leave Tier 3 alone?

Tier 3 (Extreme) has one rule: the Transsion OTA updater, `com.transsion.otaupdate`. Disabling it stops system updates until you switch it back on.

Nothing else in the tool selects it. `--tier 1` and `--tier 2` do not include it, and in the menu it is its own option. If you did disable it, this brings it back:

```bash
adb shell pm enable --user 0 com.transsion.otaupdate
```

## What can the tool never touch?

Tier 4 (Critical): core Android and Google Play services. The tool refuses those packages under any tier or flag, and the [protected package list](/oems/critical) names each one. Apps with no rule are listed as Unknown in a scan, and no tier selects them.

The tool does not root the phone, unlock the bootloader or write to the system partition.

## How do you run it on a Tecno, Infinix or itel phone?

1. **Turn on USB debugging.** Settings > About phone, tap Build number seven times, then Developer options > USB debugging. If you cannot find Build number, search Settings for it.
2. **Connect the phone** with a USB data cable and accept the "Allow USB debugging" prompt.
3. **Download and start the tool.** Windows PowerShell:

   ```powershell
   irm https://debloater.rovoxia.com/run.ps1 | iex
   ```

   macOS or Linux:

   ```bash
   curl -fsSL https://debloater.rovoxia.com/run.sh | bash
   ```

4. **In the menu, choose 1** to scan. Nothing changes.
5. **Choose 2** for a dry run of Tier 1. It prints the plan and changes nothing.
6. **Choose 3** to apply Tier 1. You confirm the list, a snapshot is saved, and the packages are disabled.
7. **Stop there for a day.** Then decide about Tier 2. Option 5 is Tier 3: skip it.

The same steps from a copy of the repository:

```bash
python cli/src/debloat_engine.py --scan
python cli/src/debloat_engine.py --tier 1 --dry-run
python cli/src/debloat_engine.py --tier 1
```

If the scan says that no rule file matches the manufacturer, add `--manufacturer transsion`.

The [web app](/app) works too, over WebUSB in a Chromium browser. It asks before every change and has no dry run.

## How do you undo it?

In the menu, option 8 restores a snapshot and option 9 restores one package. From the command line:

```bash
python cli/src/debloat_engine.py --restore
```

That restores the newest snapshot for the connected phone. `--list-snapshots` shows all of them.

## Where to go next

- [Tecno, Infinix and itel package list](/oems/transsion).
- [What the safety tiers mean](/blog/adb-debloat-safety-tiers-explained), including why Tier 3 exists.
- [Debloat or factory reset](/blog/debloat-vs-factory-reset).
- [Wireless ADB setup](/blog/wireless-adb-debloat-setup-android-11).
