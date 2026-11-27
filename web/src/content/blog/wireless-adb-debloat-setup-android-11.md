---
title: How to set up wireless ADB for debloating (Android 11+)
seoTitle: Wireless ADB Debloat Setup, Android 11+
description: Pair an Android 11 or newer phone over Wi-Fi with a QR code or a six-digit code, then scan, preview and debloat it with AI Phone Debloater. No USB cable needed.
answer: >-
  On Android 11 or newer, turn on Wireless debugging in Developer options and put the phone and the
  computer on the same Wi-Fi network. Pair them once with a QR code or a six-digit code. AI Phone
  Debloater then scans, previews and applies changes over Wi-Fi with the same commands, snapshot and
  restore as over a USB cable.
pubDate: 2026-11-01
updatedDate: 2026-11-27
category: Setup
tags: [Wireless ADB, Wireless debugging, QR pairing, Android 11]
---

## What do you need?

- A phone with Android 11 or newer. Wireless debugging with a pairing code or a QR code starts with that version.
- The phone and the computer on the same Wi-Fi network.
- Developer options switched on: Settings > About phone, tap Build number seven times.
- AI Phone Debloater on the computer. The command-line tool needs Python 3.11 or newer and ADB. The one-line installers look for both and install them if they are missing.

You do not need a USB cable, root or an unlocked bootloader.

## How do you turn on Wireless debugging?

1. Open Settings > Developer options.
2. Turn on **Wireless debugging**.
3. Open the Wireless debugging screen. It shows the phone's address under "IP address & Port", and two pairing choices: **Pair device with QR code** and **Pair device with pairing code**.

Keep that screen open while you pair.

## Which pairing method should you use?

| Method | Start it with | Use it when |
|---|---|---|
| QR code in the terminal | `--qr-pair` | You run the command-line tool and can point the phone at the screen |
| Six-digit code | Menu option `w`, then `3` | The QR code is hard to scan, or you prefer typing |
| QR code in the browser | "Pair over Wi-Fi with a QR code" in the web app | You use the web app through the local bridge |
| Six-digit code in the browser | "Pair with a pairing code" under "Connect over Wi-Fi" in the web app | You use the web app through the local bridge and prefer typing |
| No pairing | `--wireless` with the address, or "Connect to a paired phone" in the web app | The phone is already paired with this computer |

A phone that is already paired with this computer only needs to connect.

## How do you pair with a QR code from the command line?

1. Run the pairing command:

   ```bash
   python cli/src/debloat_engine.py --qr-pair
   ```

2. The tool prints a QR code in the terminal.
3. On the phone, tap **Pair device with QR code** and scan it.
4. The tool waits up to two minutes for the scan, pairs, and connects. It then prints the connected device.

On some networks the phone's connection port does not reach the computer on its own. The tool then asks you to type the port shown under "IP address & Port" on the Wireless debugging screen.

Press Ctrl+C to cancel a pairing that is still waiting.

## How do you pair with a six-digit code?

1. Start the interactive menu. The launcher with no arguments opens it, and so do the one-line installers:

   ```powershell
   irm https://debloater.rovoxia.com/run.ps1 | iex
   ```

   ```bash
   curl -fsSL https://debloater.rovoxia.com/run.sh | bash
   ```

2. Choose `w` for wireless, then `3` to pair with a code.
3. On the phone, tap **Pair device with pairing code**. A dialog shows a six-digit code and an address in the form IP:port.
4. Type that address and the code into the tool.
5. The tool then asks for the address to connect to. That is the one on the main Wireless debugging screen, under "IP address & Port". It is not the address from the pairing dialog.

In the same wireless menu, `4` searches the network for phones with Wireless debugging on and lets you pick one from a list, so you do not have to type the address. It never connects on its own.

## How do you connect to a phone that is already paired?

Pass the address from the Wireless debugging screen to `--wireless`, together with what you want to do:

```bash
python cli/src/debloat_engine.py --wireless <IP>:<PORT> --scan
```

Read the address from the phone each time you connect rather than reusing an old one.

## How do you debloat over Wi-Fi?

Exactly as over a cable. Scan, preview, then apply:

```bash
python cli/src/debloat_engine.py --wireless <IP>:<PORT> --scan
python cli/src/debloat_engine.py --wireless <IP>:<PORT> --tier 1 --dry-run
python cli/src/debloat_engine.py --wireless <IP>:<PORT> --tier 1
```

The dry run prints the packages that Tier 1 would disable and changes nothing. The last command shows the list again, asks you to confirm, saves a snapshot to `~/AiPhoneDebloater/backups/` and then disables the packages. If the snapshot cannot be written, nothing is changed.

If the phone is also plugged in by USB and you leave out `--wireless`, ADB sees two devices. The tool then asks which one to use, or, when it cannot ask, tells you to pass `--serial`. `--switch-transport usb` and `--switch-transport wireless` move the same phone from one connection to the other.

What each tier covers is in [the safety tiers guide](/blog/adb-debloat-safety-tiers-explained). For the packages on your phone, see the guide for your brand, for example [Samsung Galaxy](/blog/samsung-galaxy-debloat-guide-one-ui-6) or [Xiaomi, Redmi and POCO](/blog/xiaomi-hyperos-debloat-guide).

## Can the web app work without a cable?

Yes, through the local bridge. The web app's direct mode uses WebUSB, which is USB only. For Wi-Fi it talks to a small bridge program on your own computer, which uses the computer's ADB.

1. Start the bridge. It opens the [web app](/app) connected to it.

   ```powershell
   irm https://debloater.rovoxia.com/bridge.ps1 | iex
   ```

   ```bash
   curl -fsSL https://debloater.rovoxia.com/bridge.sh | bash
   ```

2. In the web app choose **Pair over Wi-Fi with a QR code**, in the "Local bridge" box.
3. On the phone tap **Pair device with QR code** and scan the code on the computer screen.

The code works for two minutes and for one pairing, and closing the dialog cancels it. Once paired, the phone appears in the app like a phone on a cable.

The "Connect over Wi-Fi" section of the bridge panel has three more ways in:

- **Pair with a pairing code**: on the phone tap **Pair device with pairing code** and type the IP address, the pairing port and the six-digit code it shows.
- **Connect to a paired phone**: type the IP address and port from the main Wireless debugging screen, for a phone that is already paired with this computer.
- **Phones found on this network**: the phones that ADB's own network discovery sees, with a button to connect one that is already paired.

If pairing works but the phone does not announce the port to connect to, the page asks for that port, which is on the main Wireless debugging screen, and finishes the connection.

The page keeps the device list up to date by itself, so a phone that connects later appears without reloading the page. If the phone or the bridge drops out, the page says so, switches off changes until the same phone is back, and keeps your selection. The app asks you to confirm before every change. It has no dry run.

The bridge listens only on your own computer (127.0.0.1), and it runs device requests only when they carry the session token that the start script gives to the web app.

## What if it does not connect?

- Run the diagnostics. They check ADB, USB and wireless and report what they find:

  ```bash
  python cli/src/debloat_engine.py --diagnostics
  ```

- Check that Wireless debugging is still on and that both devices are on the same Wi-Fi network.
- Read the address from the phone again. Use the address on the main Wireless debugging screen to connect, and the one in the pairing dialog to pair.
- If nothing works, use a USB data cable. Every command is the same without `--wireless`.

## How do you undo a change made over Wi-Fi?

The same way as over USB. Snapshots are files on the computer, so the connection type does not matter:

```bash
python cli/src/debloat_engine.py --wireless <IP>:<PORT> --restore
```

`--restore` with no name uses the newest snapshot for the connected phone. `--list-snapshots` shows them all and needs no phone.

When you are done, turn Wireless debugging off again on the phone.

## Where to go next

- [What the safety tiers mean](/blog/adb-debloat-safety-tiers-explained).
- [Debloat or factory reset](/blog/debloat-vs-factory-reset).
- [Package list by brand](/oems), including the [universal rules](/oems/universal) that apply to every phone.
