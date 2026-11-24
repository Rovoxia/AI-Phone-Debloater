---
title: How to debloat a Motorola phone without root
seoTitle: Motorola Debloat Guide (No Root)
description: Turn off Moto telemetry, survey notifications, the Hello You feed and carrier setup apps over ADB, without root. Keep Moto gestures. Rules by tier, plus undo.
answer: >-
  Run AI Phone Debloater over ADB with USB debugging on. On a Motorola phone, Tier 1 disables the Moto
  Care telemetry services, Motorola's survey and marketing notifications, the Hello You feed, Moto
  Gametime and carrier setup apps. Moto gestures and Peek Display are Tier 2, so they stay on
  unless you choose them. A snapshot makes every change reversible.
pubDate: 2026-11-01
updatedDate: 2026-11-23
category: Brand guides
tags: [Motorola, Moto, My UX, Hello UI]
oemIds: [motorola]
---

## What is there to turn off on a Motorola phone?

Not a great deal that you can see. The Motorola rule file, written for My UX and Hello UI, is mostly background services, and that is the reason to run it: these are services you would not find by looking through the app list.

The table at the top of this page has the counts per tier. The [full list](#rules) at the end names every package.

**Tier 1 (Safe)** covers:

- **Telemetry and diagnostics.** Moto Care Telemetry and Moto Care Internal Diagnostics, which the rule file describes as collecting battery statistics, app crashes and hardware usage data and sending crash dumps to Lenovo and Motorola servers. Also Motorola Mobile Kit and Motorola Audio Monitor.
- **Notifications.** Motorola Notifications, which sends satisfaction surveys, feedback questionnaires and product marketing.
- **Feeds and extras.** Hello You (Moto Discover), Moto Gametime, Moto Device Help and Moto Signature.
- **Carrier and partner installers.** Motorola Carrier Setup and Apps Brasil, the partner app installer on Latin America carrier models.

Carrier and partner apps themselves, such as a carrier's account app or a preloaded Facebook, are in the [universal rules](/oems/universal), which the tool loads on every phone.

## What will you notice after Tier 1?

- **Motorola stops sending surveys and promotions** as notifications.
- **The Hello You feed is off.**
- **The Moto Gametime overlay no longer appears in games.** That is the panel with game shortcuts, screen capture and notification blocking.
- **Moto Device Help is off.** It holds the troubleshooting guides and the hardware tests. Keep it if you use those tests.
- **Moto Signature is off.**

Motorola Audio Monitor is the one to watch. The rule file describes it as an audio environment analysis service used for automated profile switching. If something that adapts to your surroundings stops working after Tier 1, switch this package back on:

```bash
adb shell pm enable --user 0 com.motorola.audiomonitor
```

## Which Moto features are in Tier 2?

Moto's own features. Leave Tier 2 alone unless you are sure you do not use them:

- **Moto Actions.** The gestures: chop twice for the flashlight, twist for the camera.
- **Moto Display (Peek Display).** Notifications that light up on the lock screen when the phone moves.
- **Motorola FM Radio.**
- **Moto Family Space.** The restricted space for children or guests.

`--tier 1` never selects these. Tier 2 is a separate run, and you can take it one package at a time.

## What stays protected?

Tier 4 (Critical) is core Android and Google Play services. The tool refuses to disable or uninstall those packages, whatever tier or flag you use. The [protected package list](/oems/critical) has every one. Tier 3 has a single rule, for Tecno, Infinix and itel phones, so it does nothing here.

The tool does not root the phone, unlock the bootloader or write to the system partition. It switches apps off for your user, and the apps stay on the system image.

## How do you debloat a Motorola phone step by step?

1. **Turn on USB debugging.** Settings > About phone, tap Build number seven times. Then Developer options > USB debugging.
2. **Connect the phone** with a USB data cable and accept the "Allow USB debugging" prompt. A charge-only cable will not work.
3. **Scan first.**

   ```bash
   python cli/src/debloat_engine.py --scan
   ```

   The scan prints a count for each tier and then every package with its tier. It changes nothing.
4. **Preview Tier 1.**

   ```bash
   python cli/src/debloat_engine.py --tier 1 --dry-run
   ```

5. **Apply Tier 1.** You are shown the list and asked to confirm. A snapshot goes to `~/AiPhoneDebloater/backups/` before anything is disabled, and the run stops if the snapshot cannot be written.

   ```bash
   python cli/src/debloat_engine.py --tier 1
   ```

6. **Optional: one Tier 2 package.** This previews turning off the FM radio and nothing else:

   ```bash
   python cli/src/debloat_engine.py --package com.motorola.android.fmradio --dry-run
   ```

These commands are for a copy of the repository. Without one, a single line downloads the tool and opens a menu where options 1, 2 and 3 are the scan, the dry run and the Tier 1 run:

```powershell
irm https://debloater.rovoxia.com/run.ps1 | iex
```

```bash
curl -fsSL https://debloater.rovoxia.com/run.sh | bash
```

You can also use the [web app](/app) in a Chromium browser. It asks before every change and saves its own snapshot, and it has no dry run.

## How do you undo it?

```bash
python cli/src/debloat_engine.py --restore
```

This restores the newest snapshot for the connected phone. Each package goes back to the state it was in before the run. To choose another snapshot, run `--list-snapshots` and pass its name to `--restore`.

A factory reset switches every preinstalled app back on, and a system update can switch some back on.

## Where to go next

- [Motorola package list](/oems/motorola).
- [What the safety tiers mean](/blog/adb-debloat-safety-tiers-explained).
- [Wireless ADB setup](/blog/wireless-adb-debloat-setup-android-11), for Android 11 and newer.
- [How to debloat a Google Pixel](/blog/pixel-debloat-guide-stock-android).
