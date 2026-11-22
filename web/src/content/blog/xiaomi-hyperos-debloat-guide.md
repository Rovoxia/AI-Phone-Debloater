---
title: How to debloat Xiaomi, Redmi and POCO phones without root
seoTitle: Xiaomi, Redmi and POCO Debloat Guide
description: Turn off MIUI System Ads, analytics, GetApps and other preinstalled HyperOS and MIUI apps over ADB, without root. All Xiaomi rules by tier, with the undo steps.
answer: >-
  Turn on USB debugging, including the two extra Xiaomi switches, connect the phone to a computer and run
  AI Phone Debloater. Its Tier 1 rules disable the MIUI System Ads service, analytics and logging
  services, GetApps and Xiaomi's bundled browser, video, music and payment apps. Nothing is rooted, and a
  snapshot taken first restores every app.
pubDate: 2026-11-01
updatedDate: 2026-11-23
category: Brand guides
tags: [Xiaomi, Redmi, POCO, HyperOS, MIUI]
oemIds: [xiaomi]
---

## Which phones does this guide cover?

Phones that report Xiaomi, Redmi or POCO as their manufacturer. AI Phone Debloater reads the manufacturer from the phone and treats Redmi and POCO as Xiaomi, so all three get the same rule file, written for MIUI and HyperOS. If a scan finds almost no Xiaomi packages, run it again with `--manufacturer xiaomi`.

## What do the Xiaomi rules turn off?

Most Xiaomi rules are Tier 1 (Safe). The table at the top of this page has the counts, and the [full list](#rules) at the end has every package. They fall into four groups:

- **Ads.** MIUI System Ads (`com.miui.msa.global`), which the rule file describes as the service that shows popups and banners inside system apps such as Themes, Security and File Manager. Also Wallpaper Carousel on the lock screen, Mi Credit, the Yellow Pages directory and Mi Weather.
- **Analytics and logging.** MIUI Analytics, the MIUI background daemon, Mi Bug Report, Services and Feedback, and Joyose.
- **Bundled apps.** GetApps, Mi Browser, Mi Video, Mi Music, Mi Pay, Mi Scanner, ShareMe, Mi Compass, Quick Apps and the Clean Master engine.
- **Xiaomi Cloud.** Cloud backup, the cloud service and its system package, and Mi Cloud Sync.

Mi Notes is in Tier 2 (Advanced), because some people keep their notes in it. Tier 3 does not apply: its only rule is for Tecno, Infinix and itel phones.

The tool also loads the [universal rules](/oems/universal) for partner and carrier apps that ship on many brands.

## Do you use Xiaomi Cloud? Read this first

The Xiaomi Cloud packages are in Tier 1, so `--tier 1` turns them off with everything else. Photos, contacts, messages, notes and bookmarks then stop syncing to Xiaomi's servers. Files already on the phone are not touched.

If you want to keep Xiaomi Cloud, apply Tier 1 and then switch these four back on:

```bash
adb shell pm enable --user 0 com.miui.cloudbackup
adb shell pm enable --user 0 com.miui.cloudservice
adb shell pm enable --user 0 com.miui.cloudservice.syspack
adb shell pm enable --user 0 com.miui.micloudsync
```

The menu's "Restore single package" option does the same for one package at a time. In the [web app](/app) you choose packages one by one, so you can leave these four out from the start.

## What else will you notice?

- **Fewer ads in system apps.** That is what the MIUI System Ads rule is for. The rules do not cover every ad setting, so an app can still show its own promotions.
- **No Wallpaper Carousel** on the lock screen.
- **GetApps is off.** Apps you installed from it no longer update there. Keep it if you depend on it.
- **Mi Browser, Mi Video and Mi Music are off.** Have another browser and player installed before you start.
- **Caller ID from Yellow Pages stops.**
- **The cleaner inside the Security app may stop working.** Clean Master is the engine behind it.
- **Mi Weather, Mi Compass, Mi Scanner and ShareMe are off.**
- **Quick Apps no longer open.**

Anything without a rule, which includes the system launcher and the Security app, shows up as Unknown in the scan. No tier selects it. Core Android and Google Play services are on the [protected list](/oems/critical), which the tool refuses to touch.

## How do you set up a Xiaomi phone for ADB?

Xiaomi phones need more than the usual switch:

1. Open Settings > About phone and tap the MIUI version or OS version seven times. On other brands this is the Build number.
2. Open Developer options and turn on **USB debugging**.
3. In the same list, turn on **Install via USB** and **USB debugging (Security settings)**.
4. Connect the phone with a USB data cable, unlock it and accept the "Allow USB debugging" prompt.

The bootloader stays locked. The tool does not root the phone and does not write to the system partition.

## How do you run the debloat?

Start the tool with a one-line installer. It downloads the command-line tool into `~/.ai-phone-debloater` and opens a menu:

```powershell
irm https://debloater.rovoxia.com/run.ps1 | iex
```

```bash
curl -fsSL https://debloater.rovoxia.com/run.sh | bash
```

Then work through these in order. The commands are for a copy of the repository; the menu numbers do the same thing.

| Step | Command | Menu |
|---|---|---|
| See what is installed, with tiers | `python cli/src/debloat_engine.py --scan` | 1 |
| Preview Tier 1 without changing anything | `python cli/src/debloat_engine.py --tier 1 --dry-run` | 2 |
| Apply Tier 1 after you confirm | `python cli/src/debloat_engine.py --tier 1` | 3 |
| Preview one package | `python cli/src/debloat_engine.py --package com.miui.notes --dry-run` | none |

Before the first change the tool writes a snapshot to `~/AiPhoneDebloater/backups/`. If it cannot write the snapshot, it stops and changes nothing.

By default every package in the plan is disabled with `pm disable-user`, which is the easier state to reverse. `--action uninstall` runs `pm uninstall -k` instead, which removes the app for your user and keeps its data.

## How do you undo it?

```bash
python cli/src/debloat_engine.py --restore
```

With no file name, `--restore` uses the newest snapshot for the connected phone. `--list-snapshots` shows the others, and you can pass one by name. A restore puts each package back in its recorded state.

A system update can switch some packages back on. If that happens, run the dry run again and see what it lists.

## Where to go next

- [Xiaomi package list](/oems/xiaomi): every rule for MIUI and HyperOS.
- [What the safety tiers mean](/blog/adb-debloat-safety-tiers-explained).
- [Wireless ADB setup](/blog/wireless-adb-debloat-setup-android-11), if you would rather not use a cable.
- [Debloat or factory reset](/blog/debloat-vs-factory-reset): a reset brings all of these apps back.
