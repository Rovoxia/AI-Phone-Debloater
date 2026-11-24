---
title: How to debloat Vivo and iQOO phones without root
seoTitle: Vivo and iQOO Debloat Guide (No Root)
description: Turn off Jovi Home, the lock screen poster, V-Appstore and other preinstalled Vivo apps over ADB, without root. The Vivo rules by tier and how to restore them.
answer: >-
  Turn on USB debugging, connect the phone and run AI Phone Debloater. On Vivo and iQOO phones its Tier 1
  rules disable the Jovi assistant, the Jovi Home feed, the lock screen poster, Vivo Global Search,
  V-Appstore, Vivo Browser, Game Center and EasyShare. Preview the list with a dry run first. A snapshot
  saved before the change restores every app.
pubDate: 2026-11-01
updatedDate: 2026-11-23
category: Brand guides
tags: [Vivo, iQOO, FuntouchOS, OriginOS, Jovi]
oemIds: [bbk]
excludePackagePrefixes: ['com.coloros.', 'com.heytap.', 'com.oppo.']
---

## Does the tool know Vivo and iQOO phones?

Yes. AI Phone Debloater reads the manufacturer name from the phone. Vivo matches the BBK rule file, which Vivo shares with Oppo and Realme, and iQOO is treated as Vivo. The file is written for FuntouchOS and OriginOS on the Vivo side.

The tool loads the whole file. That does no harm: a rule for an app that is not installed does nothing. This guide leaves out the rules for Oppo and Realme packages and lists the rest. The [BBK package list](/oems/bbk) has all of them.

If a scan reports that no rule file matches your phone, run it again with `--manufacturer vivo`.

## What do the Vivo rules turn off, and what will you notice?

Almost every Vivo rule in Tier 1 (Safe) is something you can see on the phone:

- **Jovi Home (HiBoard).** The feed on the screen to the left of the home screen.
- **Vivo Lockscreen Poster.** The rotating lock screen wallpapers with headlines stop.
- **Vivo Global Search.** The system search bar.
- **Jovi Voice Assistant.** Vivo's own assistant. Keep it if you talk to it.
- **V-Appstore.** Vivo's app store. Apps you installed from it no longer update there, so keep it if you depend on it.
- **Vivo Browser.** Have another browser installed first.
- **Vivo Game Center.** The game store and its floating overlay in games.
- **Vivo EasyShare.** File transfer between Vivo phones. Keep it if you are about to move to a new Vivo phone.

Tier 2 (Advanced) needs more thought:

- **iTheme.** The theme store.
- **Vivo iManager.** The rule file describes it as a background system manager that kills apps to free memory, runs security scans and logs battery statistics. With it off, the cleaning and scanning features of the iManager app stop.

On top of these, the [universal rules](/oems/universal) cover partner and carrier apps that ship on many brands. The table at the top of this page has the counts.

## What does the tool not touch on a Vivo phone?

- **Tier 4 (Critical):** core Android and Google Play services. The tool refuses these packages, whatever tier or flag you use. See the [protected package list](/oems/critical).
- **Anything without a rule:** a scan lists it as Unknown, and no tier selects it. That is the case for the home screen launcher, for example.
- **The system itself:** no root, no bootloader unlock, no write to the system partition. The apps stay on the system image and are switched off for your user.

Tier 3 has one rule, and it is for Tecno, Infinix and itel phones, so it does not apply here.

## How do you debloat a Vivo or iQOO phone?

1. **Turn on USB debugging.** Open Settings > About phone and tap Build number seven times. If you cannot find it, search Settings for Build number. Then open Developer options and turn on USB debugging.
2. **Connect the phone** to the computer with a USB data cable. Unlock it and accept the "Allow USB debugging" prompt.
3. **Start the tool.** On Windows, in PowerShell:

   ```powershell
   irm https://debloater.rovoxia.com/run.ps1 | iex
   ```

   On macOS or Linux:

   ```bash
   curl -fsSL https://debloater.rovoxia.com/run.sh | bash
   ```

   Either one downloads the command-line tool and opens a menu.
4. **Choose 1 to scan.** You get every installed package with its tier and whether it is enabled.
5. **Choose 2 for a Tier 1 dry run.** It prints what would be disabled and changes nothing.
6. **Choose 3 to apply Tier 1.** The tool shows the list, asks you to confirm, writes a snapshot and then disables the packages.

From a copy of the repository the same three steps are:

```bash
python cli/src/debloat_engine.py --scan
python cli/src/debloat_engine.py --tier 1 --dry-run
python cli/src/debloat_engine.py --tier 1
```

To keep one of the Tier 1 apps, apply the tier and then restore that one package. To turn off a single app and nothing else, name it:

```bash
python cli/src/debloat_engine.py --package com.vivo.magazine --dry-run
```

The [web app](/app) is the other route: it runs in a Chromium browser over WebUSB, shows the same tiers and asks before every change. It has no dry run.

## How do you bring an app back?

The quickest way is the menu: option 8 restores a snapshot and option 9 restores one package. From the command line:

```bash
python cli/src/debloat_engine.py --restore
python cli/src/debloat_engine.py --list-snapshots
```

`--restore` with no name uses the newest snapshot for the connected phone. Or use ADB directly:

```bash
adb shell pm enable --user 0 com.vivo.appstore
```

A factory reset also switches everything back on, and a system update can switch some packages back on.

## Where to go next

- [Oppo, Vivo and Realme package list](/oems/bbk).
- [What the safety tiers mean](/blog/adb-debloat-safety-tiers-explained).
- [How to debloat OnePlus, Oppo and Realme phones](/blog/oneplus-oppo-realme-debloat-guide-coloros), for the other half of the same rule file.
- [Debloat or factory reset](/blog/debloat-vs-factory-reset).
