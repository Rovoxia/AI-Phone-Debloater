---
title: How to debloat OnePlus, Oppo and Realme phones without root
seoTitle: OnePlus, Oppo and Realme Debloat Guide
description: OnePlus phones get one rule file, Oppo and Realme another. See what each turns off on OxygenOS and ColorOS, how to preview it over ADB, and how to undo it.
answer: >-
  Run AI Phone Debloater over ADB with USB debugging on. A OnePlus phone gets rules for logging,
  diagnostics, HeyTap push and tracking services, the OnePlus Store and Game Space. Oppo and Realme
  phones get rules for ColorOS ad feeds, the App Market and HeyTap apps. Preview Tier 1 with a dry run,
  then apply it. A snapshot undoes it.
pubDate: 2026-11-01
updatedDate: 2026-11-23
category: Brand guides
tags: [OnePlus, Oppo, Realme, ColorOS, OxygenOS, HeyTap]
oemIds: [oneplus, bbk]
excludePackagePrefixes: ['com.vivo.', 'com.bbk.']
---

## Which rules does your phone get?

AI Phone Debloater reads the manufacturer name from the phone and loads the rule file that matches it:

- A phone that reports **OnePlus** gets the OnePlus file.
- A phone that reports **Oppo** or **Realme** gets the BBK file, which it shares with Vivo.

Every phone also gets the [universal rules](/oems/universal) for carrier and partner apps. The table at the top of this page has the counts for each file.

No package appears in both files, and a phone gets one of them, not both. The OnePlus file is written for the shared OxygenOS and ColorOS base and already names several HeyTap services, so a OnePlus phone may hold packages from the other file as well. A second scan shows whether it does, and a scan changes nothing:

```bash
python cli/src/debloat_engine.py --scan --manufacturer oppo
```

`--manufacturer` replaces the detected name for that one run. Use `--manufacturer oneplus` to check an Oppo or Realme phone against the OnePlus file.

## What do the OnePlus rules turn off?

Mostly services you never see. In Tier 1 (Safe):

- **Logging and diagnostics:** OnePlus LogKit, OEM LogKit, OPBugreport Lite, OnePlus Diagnostics and the OnePlus ODM diagnostic services.
- **Push and tracking:** OnePlus Push Service, HeyTap Mobile Cloud Push, OPlus Postman Service, HeyTap User Habit Analysis and HeyTap OpenID.
- **Games:** OnePlus Games (Game Space) and COSA Game Acceleration.
- **Promotions:** OnePlus Store, Red Cable Club and the HeyTap lock screen pictorial.

In Tier 2 (Advanced): HeyTap Cloud, HeyTap Account (User Center) and Zen Mode.

**What you may notice:** the Game Space overlay no longer appears in games, the OnePlus Store and Red Cable Club apps are off, and the rotating lock screen stories stop. The rule file says OnePlus Push Service is used mainly for marketing and system update announcements, so those announcements stop too. The system updater itself has no removal rule.

Think before Tier 2. HeyTap Account is the sign-in behind HeyTap services, and HeyTap Cloud is a backup service. Leave both on if you back up to it.

## What do the Oppo and Realme rules turn off?

More of it is visible. In Tier 1 (Safe):

- **Ad feeds:** Smart Assistant, the screen to the left of the home screen; the ColorOS Lockscreen Magazine; and HeyTap Global Search, the swipe-down search widget.
- **Stores and bundled apps:** the Oppo and Realme App Market, HeyTap Browser, HeyTap Music and HeyTap Video.
- **Other:** ColorOS Game Space and Oppo Roaming.

In Tier 2 (Advanced): ColorOS Phone Manager, the system cleaner and storage scanner, and HeyTap Theme Store.

**What you may notice:** swiping right from the home screen and swiping down for search no longer open those panels, the lock screen stops rotating promotional wallpapers, and the App Market stops prompting. Apps you installed from the App Market no longer update there, so keep it if you depend on it. Have another browser installed before you turn off HeyTap Browser.

## What is never touched?

Tier 4 (Critical) protects core Android and Google Play services on every phone. The tool refuses those packages, whatever tier or flag you use. See the [protected package list](/oems/critical).

Anything without a rule is listed as Unknown in a scan, and no tier selects it.

Tier 3 does not apply to these phones. Its only rule is for Tecno, Infinix and itel.

## How do you run it?

1. **Turn on USB debugging.** Settings > About phone, tap Build number seven times, then turn on USB debugging in Developer options. If you cannot find Build number, search Settings for it. The bootloader stays locked.
2. **Connect the phone** with a USB data cable and accept the "Allow USB debugging" prompt.
3. **Get the tool.** Clone the repository, or use a one-line installer, which opens a menu:

   ```powershell
   irm https://debloater.rovoxia.com/run.ps1 | iex
   ```

   ```bash
   curl -fsSL https://debloater.rovoxia.com/run.sh | bash
   ```

4. **Scan, preview, apply.** The first two commands change nothing. The third asks you to confirm and saves a snapshot before it disables anything. In the menu these are options 1, 2 and 3.

   ```bash
   python cli/src/debloat_engine.py --scan
   python cli/src/debloat_engine.py --tier 1 --dry-run
   python cli/src/debloat_engine.py --tier 1
   ```

5. **Review Tier 2 separately.** `--tier 2 --dry-run` lists it. To act on part of it, name the packages:

   ```bash
   python cli/src/debloat_engine.py --package com.heytap.themestore --dry-run
   ```

Prefer a browser? The [web app](/app) does the same over WebUSB in Chromium browsers. It asks before every change and has no dry run.

## How do you undo it?

```bash
python cli/src/debloat_engine.py --restore
```

That restores the newest snapshot for the connected phone. `--list-snapshots` shows them all, and the menu has "Restore from backup" and "Restore single package". By hand, one package comes back with:

```bash
adb shell pm enable --user 0 com.heytap.market
```

The tool changes package state for your user. It does not root the phone, unlock the bootloader or write to the system partition, so a factory reset puts every app back.

## Where to go next

- Package lists: [OnePlus](/oems/oneplus) and [Oppo, Vivo and Realme](/oems/bbk).
- [What the safety tiers mean](/blog/adb-debloat-safety-tiers-explained).
- [How to debloat Vivo and iQOO phones](/blog/vivo-iqoo-debloat-guide-funtouchos), which use the same rule file as Oppo and Realme.
- [Wireless ADB setup](/blog/wireless-adb-debloat-setup-android-11).
