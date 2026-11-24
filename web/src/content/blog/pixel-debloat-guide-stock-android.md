---
title: How to debloat a Google Pixel without root
seoTitle: Google Pixel Debloat Guide (No Root)
description: Most Pixel rules are optional Google features, not junk. See what Tier 1 and Tier 2 turn off on a Pixel, how to pick single packages, and how to restore them.
answer: >-
  A Pixel has little bloatware, so most of its rules in AI Phone Debloater are Tier 2: optional Google
  features such as Android Auto, Digital Wellbeing, Google Wallet and Now Playing. Run Tier 1 for the
  few preloaded apps, then pick Tier 2 packages one at a time. Everything is done over ADB without root
  and can be restored.
pubDate: 2026-11-01
updatedDate: 2026-11-23
category: Brand guides
tags: [Google Pixel, Pixel, Android, Digital Wellbeing]
oemIds: [pixel]
---

## Is there much to remove on a Pixel?

Less than on most phones. The table at the top of this page shows the split: the Pixel rule file has a short Tier 1 (Safe) list and a longer Tier 2 (Advanced) list. Tier 2 is not junk. Each entry is a Google feature that works as designed and that some people use.

So the plan for a Pixel is different from the plan for other brands:

1. Apply Tier 1. It also covers the [universal rules](/oems/universal) for carrier and partner apps.
2. Read the Tier 2 list and turn off single packages you know you do not use.

## What does Tier 1 turn off on a Pixel?

Google Fit, Google News, Google Podcasts, Pixel Tips, Google TV and Sound Amplifier. Each is an ordinary app that you can get back from the snapshot.

Sound Amplifier is an accessibility tool that boosts quiet sounds through headphones. Leave it on if anyone who uses the phone needs it.

## Which Tier 2 features should you keep?

Go through the [full list](#rules) at the end of this page. These need the most thought:

- **Personal Safety.** Car crash detection, safety check and emergency sharing. Keep it if you rely on any of them.
- **Android Accessibility Suite (TalkBack) and Live Transcribe.** The screen reader and live speech-to-text. Keep them if you or anyone who uses the phone needs them.
- **Device Health Services.** The rule file says it works out the battery estimates and the adaptive brightness models. Expect those to stop.
- **Google Wallet.** Contactless payment and passes from the lock screen and quick settings.
- **Android Auto.** Projection to a car display.

The rest is easier to decide:

- **Digital Wellbeing.** It logs app usage, notification counts and unlocks. That logging stops once it is off.
- **Pixel Ambient Services.** This is Now Playing, the song identification on the lock screen.
- **Pixel Recorder, Files by Google, Google Drive, Google Meet and YouTube Music.** Ordinary apps. Check that you have another file manager before you turn off Files by Google.
- **Google Wallpapers, Pixel Live Wallpapers and Cinematic Wallpaper Effects.** Wallpaper pickers and effects.

## What stays protected on a Pixel?

Google Play services, the Play Store, Google Services Framework, Gboard and Android System WebView are Tier 4 (Critical), along with the Android framework, System UI, telephony and Settings. The tool refuses to disable or uninstall them, whatever tier or flag you use. The [protected package list](/oems/critical) has all of them.

Apps with no rule, such as the Pixel Launcher, are listed as Unknown in a scan. No tier selects them.

## How do you debloat a Pixel step by step?

1. **Turn on USB debugging.** Settings > About phone, tap Build number seven times, then Developer options > USB debugging. The bootloader stays locked and nothing else in Developer options has to change.
2. **Connect the phone** with a USB data cable and accept the "Allow USB debugging" prompt.
3. **Scan.** This lists every package with its tier and changes nothing.

   ```bash
   python cli/src/debloat_engine.py --scan
   ```

4. **Preview and apply Tier 1.** The dry run prints the plan. The second command shows it again, asks you to confirm, saves a snapshot and then disables the packages.

   ```bash
   python cli/src/debloat_engine.py --tier 1 --dry-run
   python cli/src/debloat_engine.py --tier 1
   ```

5. **Pick Tier 2 packages by name.** Repeat `--package` for each one. This example previews turning off Android Auto and Digital Wellbeing:

   ```bash
   python cli/src/debloat_engine.py --package com.google.android.projection.gearhead --package com.google.android.apps.wellbeing --dry-run
   ```

   Run it again without `--dry-run` to apply it. If you name a Tier 4 package, the tool refuses the whole command and changes nothing.

No copy of the repository? The one-line installer downloads the tool and opens a menu with the scan, the Tier 1 dry run and the Tier 1 run as options 1, 2 and 3:

```powershell
irm https://debloater.rovoxia.com/run.ps1 | iex
```

```bash
curl -fsSL https://debloater.rovoxia.com/run.sh | bash
```

## Is the web app easier for picking single packages?

For a Pixel, often yes. The [web app](/app) shows every package with its tier and lets you act on the ones you choose. It works over WebUSB in Chrome, Edge and other Chromium browsers, asks you to confirm before every change and saves a snapshot in the browser first. It has no dry run.

## How do you get a feature back?

Restore the newest snapshot for the phone, or one package by hand:

```bash
python cli/src/debloat_engine.py --restore
adb shell pm enable --user 0 com.google.android.apps.wellbeing
```

`pm enable` reverses a disable. If you used `--action uninstall`, the reverse is `adb shell cmd package install-existing --user 0` followed by the package name. `--list-snapshots` shows every snapshot on the computer.

The tool changes package state for your user only. It does not root the phone, unlock the bootloader or write to the system partition, so system updates keep arriving and a factory reset puts every app back.

## Where to go next

- [Pixel package list](/oems/pixel): each Pixel rule with its tier.
- [What the safety tiers mean](/blog/adb-debloat-safety-tiers-explained), and why Tier 2 needs a review.
- [Wireless ADB setup](/blog/wireless-adb-debloat-setup-android-11) for Android 11 and newer.
- [How to debloat a Samsung Galaxy phone](/blog/samsung-galaxy-debloat-guide-one-ui-6), if you also own one.
