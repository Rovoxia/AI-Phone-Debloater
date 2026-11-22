---
title: How to debloat a Samsung Galaxy phone without root
seoTitle: Samsung Galaxy Debloat Guide (No Root)
description: Turn off Bixby, AR Emoji, Samsung Free and other preinstalled One UI apps over ADB, without root. Every Samsung rule by tier, and how to undo a change.
answer: >-
  Turn on USB debugging, connect the phone to a computer and run AI Phone Debloater. Preview Tier 1 with a
  dry run, then apply it. That disables Bixby, AR Emoji, Samsung Free, Game Launcher and Samsung's
  telemetry services, along with carrier and partner apps. The phone is not rooted, and a snapshot saved
  first lets you undo every change.
pubDate: 2026-11-01
updatedDate: 2026-11-23
category: Brand guides
tags: [Samsung, Galaxy, One UI, Bixby]
oemIds: [samsung]
---

## What does debloating a Galaxy phone change?

AI Phone Debloater changes the state of an app for your user profile on the phone. For each app you approve it runs one of two Android package-manager commands:

- `pm disable-user` turns the app off. It stays installed but cannot run, so its background services stop. This is the default.
- `pm uninstall -k` removes the app for your user only and keeps its data. You get this with `--action uninstall`.

Both are undone with one command. The tool does not root the phone, does not unlock the bootloader and does not write to the system partition, so the apps stay on the system image. A factory reset turns them back on, and a system update can turn some of them back on too.

Whether any of this matters for Knox or for your warranty is for Samsung to say. What this guide can state is what the tool does, and that is the two commands above.

## Which Samsung apps do the rules cover?

The table at the top of this page counts the Samsung rules in each tier, and the [full list](#rules) at the end names every package. In short:

**Tier 1 (Safe)** covers:

- **Bixby:** the voice agent, the "Hi Bixby" wake-up listener, Bixby Vision, and the parts that tie Bixby to Settings and to the side key.
- **AR extras:** AR Zone, AR Emoji Studio and Editor, AR Emoji Stickers and Live Stickers.
- **Samsung apps and feeds:** Samsung Free (Samsung News), Samsung Tips, Samsung Members, Samsung Kids and Samsung Checkout.
- **Game services:** Gaming Hub (Game Launcher) and Game Optimizing Service.
- **Background services:** the diagnostic monitor agent, Customization Service, Samsung Visit In, the Knox analytics uploader, the Knox BBC agent and Hiya Smart Call caller ID.

**Tier 2 (Advanced)** covers features that some people use every day: Samsung Wallet (Samsung Pay), Samsung Pass, DeX, Link to Windows, Call and Text on Other Devices, Galaxy Store, Galaxy Themes, SmartThings Find, Modes and Routines, Game Booster, Smart Switch, Samsung Core Services, the Quick Share media server, and the Knox attestation and cloud MDM services used on managed phones.

Tier 3 does not apply to a Galaxy. Its only rule is for Tecno, Infinix and itel phones.

On top of the Samsung file, the tool loads the [universal rules](/oems/universal): preloaded partner apps such as Facebook, Netflix and the Microsoft Office apps, and carrier apps.

## What will you notice after Tier 1?

- **Bixby stops responding.** The voice assistant, the "Hi Bixby" hotword and Bixby Vision in the camera are off. One rule, `com.samsung.systemui.bixby2`, covers the hook between the side key and Bixby.
- **The leftmost home screen panel loses its feed.** That panel is Samsung Free.
- **AR camera modes are gone.** AR Zone holds AR Doodle, Deco Pic, Quick Measure and AR Emoji.
- **Game Launcher no longer opens.** Game Optimizing Service, which the rule file describes as a service that throttles CPU and GPU frequency per app, stops running as well.
- **Unknown callers are no longer looked up by Hiya.** If you rely on that caller ID, leave `com.samsung.android.smartcallprovider` on.
- **Samsung Members, Samsung Tips and Samsung Kids disappear** from the app list.
- **Buying themes and fonts may stop working.** The rule file describes Samsung Checkout as the billing part of Galaxy Store themes and fonts.

If you miss one of these, restore that one package. You do not have to undo the rest.

## What should you check before Tier 2?

Each Tier 2 rule is a feature. Turn it off only if you do not use it:

- **Samsung Wallet (Samsung Pay):** contactless payment and stored cards in Samsung Wallet.
- **Samsung Pass:** saved passwords and their autofill.
- **SmartThings Find:** Samsung's offline finding network. Keep it if you rely on Find My Mobile.
- **DeX and Link to Windows:** the desktop mode, and the link to a Windows PC.
- **Galaxy Store and Galaxy Themes:** keep Galaxy Store if you install or update apps from it.
- **Modes and Routines:** your automations stop running.
- **Knox Attestation and the Knox cloud MDM client:** leave both alone on a phone managed by an employer.

## What does the tool leave alone on a Galaxy?

Tier 4 (Critical) is a fixed list that the tool refuses to disable or uninstall, whatever tier or flag you use. Besides core Android and Google Play services, it holds some Samsung packages, among them Samsung Internet, Samsung Cloud and Samsung One Connect. See the [protected package list](/oems/critical).

Samsung Keyboard, Samsung Messages, the Phone app and the One UI home screen have no rule at all, so no tier selects them.

## How do you debloat a Samsung Galaxy step by step?

1. **Turn on USB debugging.** Open Settings > About phone and tap Build number seven times. If Build number is not on that screen, search Settings for it. Then open Developer options and turn on USB debugging. Nothing else in Developer options has to change, and the bootloader stays locked.
2. **Connect the phone** to the computer with a USB data cable, unlock it and accept the "Allow USB debugging" prompt.
3. **Start the tool.** The one-line installers download the command-line tool into `~/.ai-phone-debloater` and open a menu. The launcher looks for Python 3.11 or newer and for ADB, and installs them if they are missing.

   ```powershell
   irm https://debloater.rovoxia.com/run.ps1 | iex
   ```

   ```bash
   curl -fsSL https://debloater.rovoxia.com/run.sh | bash
   ```

   The commands in the next steps are for a copy of the repository (`git clone https://github.com/Rovoxia/AI-Phone-Debloater.git`). The menu has the same actions under numbers.
4. **Scan.** The scan lists every installed package with its tier and whether it is enabled. It changes nothing. Menu option 1.

   ```bash
   python cli/src/debloat_engine.py --scan
   ```

5. **Preview Tier 1.** A dry run prints the packages that would be disabled and stops there. Menu option 2.

   ```bash
   python cli/src/debloat_engine.py --tier 1 --dry-run
   ```

6. **Apply Tier 1.** The tool shows the list again and asks you to confirm. Before the first change it writes a snapshot to `~/AiPhoneDebloater/backups/`. If the snapshot cannot be written, it stops and changes nothing. Menu option 3.

   ```bash
   python cli/src/debloat_engine.py --tier 1
   ```

7. **Use the phone for a day, then look at Tier 2.** Preview it the same way. To turn off only some of it, name the packages instead of the tier:

   ```bash
   python cli/src/debloat_engine.py --tier 2 --dry-run
   python cli/src/debloat_engine.py --package com.samsung.android.themestore --package com.sec.android.app.dexonpc --dry-run
   ```

`--tier 2` selects Tier 2 only. It does not include Tier 1.

## Can you do it from the browser instead?

Yes. The [web app](/app) connects to the phone over WebUSB in a Chromium browser such as Chrome or Edge. Other browsers reach the phone through a small local bridge that the app tells you how to start. The app lists your packages with their tiers, asks you to confirm before every change and saves a snapshot in the browser first. It has no dry run: the confirmation dialog is the preview.

No cable? See [wireless ADB setup](/blog/wireless-adb-debloat-setup-android-11).

## How do you undo a change?

Restore the newest snapshot for the connected phone:

```bash
python cli/src/debloat_engine.py --restore
```

A restore puts each package back in the state the snapshot recorded. An app that was already off before you started stays off.

To pick an older snapshot, list them and pass a name. Listing needs no phone.

```bash
python cli/src/debloat_engine.py --list-snapshots
python cli/src/debloat_engine.py --restore <snapshot name>
```

To bring back one app without the tool, use ADB. The first command is for an app that was disabled, the second for one that was uninstalled for your user:

```bash
adb shell pm enable --user 0 com.samsung.android.bixby.agent
adb shell cmd package install-existing --user 0 com.samsung.android.arzone
```

## Where to go next

- [Samsung package list](/oems/samsung): every Samsung rule with its tier.
- [What the safety tiers mean](/blog/adb-debloat-safety-tiers-explained), and how Tier 4 is enforced.
- [Debloat or factory reset](/blog/debloat-vs-factory-reset): what each one does to the phone.
