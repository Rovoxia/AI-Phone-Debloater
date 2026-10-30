# 📱 AI-Phone-Debloater — Ultimate Universal Android Debloater (No Root • Zero Data Loss)

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg?logo=python)](https://www.python.org/)
[![Android ADB](https://img.shields.io/badge/Android-ADB-green.svg?logo=android)](https://developer.android.com/tools/releases/platform-tools)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows | macOS | Linux](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![Safety: 100% Fail-Safe](https://img.shields.io/badge/Safety-100%25%20Fail--Safe-brightgreen.svg)]()
[![Zero Data Loss](https://img.shields.io/badge/Data%20Loss-Zero-brightgreen.svg)]()

> **The #1 Open-Source Phone Debloater & Bloatware Remover for Android 5.0 to 15+.**
> Maximize battery life, boost performance, and strip unwanted OEM bloatware, tracking telemetry, and ad daemons with **zero risk of bricking and zero personal data loss**. Works rootless on Samsung One UI, Xiaomi HyperOS, Google Pixel, OnePlus OxygenOS, Oppo, Vivo, Realme, Motorola, and Transsion. Plug in any AI agent (Claude Code, ChatGPT, Codex, Gemini, DeepSeek) or use the 1-click launchers for instant automated debloating.

AI-Phone-Debloater is a fail-safe, rootless Android debloating toolkit and Universal Android Debloater alternative. It operates strictly on `user 0` using standard ADB (`pm disable-user --user 0`, `pm uninstall -k --user 0`). Your `/system` partition is protected by dm-verity and remains untouched, your WhatsApp messages, photos, contacts, and app logins stay 100% intact, and every action is reversible with a 1-click rollback snapshot.

---

## Key Highlights

| Feature | What it means for you |
|---|---|
| 🛡️ **Zero Personal Data Loss** | Operates on `user 0` with the `-k` preservation flag and `disable-user` modes. Your photos, contacts, WhatsApp, and logins stay 100% untouched. |
| 🤖 **AI-Agent Powered** | Plug into Claude Code, ChatGPT, Codex, Gemini, or DeepSeek to analyze your exact device and curate a customized debloat plan using the prompts in `prompts/`. |
| ⚡ **4-Tier Safety Framework** | Safe → Advanced → Extreme → Critical Blacklist. Every package is classified before anything is touched. |
| 🔄 **Instant Rollback / Restore** | One-click snapshot restore brings any app back. No factory reset ever required. |
| 📱 **Cross-OEM Support** | Samsung (One UI), Google (Pixel), Xiaomi (MIUI/HyperOS), OnePlus (OxygenOS), Oppo/Vivo/Realme, Motorola, and Transsion. |
| 💻 **1-Click Launchers** | `debloat.bat` on Windows (auto-bootstraps portable Python if needed), `./debloat.sh` on macOS/Linux. |

---

## 📊 Phone Debloater Comparison Matrix

Why **AI-Phone-Debloater** is the safest, most flexible alternative to Universal Android Debloater (UAD-ng) and ADB AppControl:

| Feature / Capability | AI-Phone-Debloater | Universal Android Debloater (UAD-ng) | ADB AppControl | Manual ADB Commands |
|---|:---:|:---:|:---:|:---:|
| **Root Required?** | ❌ **No (Rootless)** | ❌ No | ❌ No | ❌ No |
| **Personal Data Preserved (`-k`)** | ✅ **100% Guaranteed** | ⚠️ Partial | ❌ No | ⚠️ Only if manual flag typed |
| **AI Agent Integration** | ✅ **Claude, GPT, Gemini** | ❌ None | ❌ None | ❌ None |
| **Automated Pre-Snapshots** | ✅ **Automatic JSON** | ⚠️ Manual export | ⚠️ Pro license only | ❌ None |
| **1-Click Rollback / Restore** | ✅ **Instant 1-Click** | ⚠️ Package by package | ⚠️ Manual | ❌ Manual reinstall |
| **OEM Coverage** | ✅ **320+ Curated Rules** | ✅ Community list | ⚠️ Basic | ❌ None |
| **Zero Dependencies / No Pip** | ✅ **Pure Python Stdlib** | ⚠️ Rust / GUI binary | ⚠️ Windows exe only | ✅ Shell |
| **Critical Blacklist Interception** | ✅ **Engine-enforced (61 pkgs)** | ✅ Rule-enforced | ⚠️ Warning prompt only | ❌ Zero protection |

---

## Architecture

The diagram below shows how AI agents, the Debloat Engine, ADB, and the Android package manager interact. Nothing ever touches the `/system` partition; all changes are confined to the `user 0` profile.

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         YOU (the user)                              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ launches / configures
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AI Agent (Claude Code / ChatGPT / Codex / Gemini / DeepSeek)       │
│  • Reads prompts/ai-debloat-system-prompt.md                        │
│  • Scans device: pm list packages -U, getprop                       │
│  • Classifies packages into 4 safety tiers                          │
│  • Emits a JSON debloat plan                                        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ JSON plan (packages, tier, action)
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Debloat Engine (scripts/debloat-engine.py)                         │
│  • --dry-run  → verify every action before executing                │
│  • --debloat  → run pm disable-user / pm uninstall -k --user 0    │
│  • --restore  → cmd package install-existing / rollback           │
│  • Code-level blacklist checks block Tier-4 packages               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ adb shell pm ...
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ADB (Android Debug Bridge)                                         │
│  adb shell ↔ device over USB (authorized via RSA prompt)           │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ pm uninstall -k --user 0  /  pm disable-user
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Android Package Manager (pm)                                       │
│  user 0 profile only — /system partition is NEVER modified          │
│  APK registration removed; /data/user/0 private data preserved (-k) │
└─────────────────────────────────────────────────────────────────────┘
```

Safety boundary: the engine refuses any package on the critical blacklist (see `rules/critical-do-not-touch.json`) regardless of what an AI agent recommends.

---

## Quickstart Guide

### ⚡ Method 1: Autonomous AI Agent (1-Prompt Auto Debloat)

Copy and paste this prompt into **Claude Code CLI**, **ChatGPT**, **Cursor**, or **Gemini**:

```text
Clone https://github.com/Rovoxia/AI-Phone-Debloater.git and safely debloat my connected Android phone at Tier 1. First run 'python scripts/debloat-engine.py scan', show me the device breakdown, simulate with dry-run, take an auto-snapshot, and execute safe debloat preserving all personal data.
```

The AI agent will detect your phone, audit packages against the 61-package critical blacklist, simulate with dry-run, and execute Tier 1 removal with full data preservation.

---

### 💻 Method 2: Manual 1-Click Launchers (No AI Required)

#### Step 1 — Enable Developer Options & USB Debugging on your phone

Brand-by-brand instructions (the steps are the same on essentially every Android device; only the menu names differ slightly):

1. Open **Settings → About phone**.
2. Tap **Build number** 7 times until you see "You are now a developer."
3. Go back to **Settings → System → Developer options** (on some OEMs it's under **Additional settings** or **System**).
4. Turn on **USB debugging**.
5. Connect the phone to your computer via USB.
6. On the phone, accept the **"Allow USB debugging?"** RSA prompt (check "Always allow from this computer").

### Step 2 — Plug in phone & run the 1-click launcher

**Windows:**
```powershell
.\debloat.bat
```

**macOS / Linux:**
```bash
./debloat.sh
```

The launcher:
1. Checks for Python 3.
2. Ensures ADB is installed (runs `scripts/setup-adb.sh` / `scripts/setup-adb.ps1` if missing).
3. Starts the ADB server and verifies an authorized device.
4. Launches `scripts/debloat-engine.py --interactive`.

### Step 3 — Choose a mode

When the engine starts, pick one of:

| Mode | What it does |
|---|---|
| **Interactive** | Guided menu: scan, review, debloat, restore, or exit. |
| **Scan** | Dumps all packages on the device (`pm list packages -U`) and classifies them by tier. |
| **Debloat** | Applies a debloat plan (after a mandatory `--dry-run` confirmation). |
| **AI Agent export / apply** | Exports a JSON plan for an AI agent, or applies a plan an AI agent produced. |

Every debloat action is preceded by a `--dry-run` so you can review exactly what will happen before anything runs.

---

## How to use with Claude Code / AI Agents

AI-Phone-Debloater ships with a master prompt you give to any AI agent so it can build a device-specific debloat plan for you.

### Step-by-step

1. **Collect your device profile** (run these on your computer with the phone connected):
   ```bash
   adb shell pm list packages -U > scan.txt
   adb shell getprop ro.product.manufacturer ro.product.brand ro.product.model ro.build.fingerprint
   ```

2. **Open the master prompt** at `prompts/ai-debloat-system-prompt.md` and copy its contents.

3. **Paste the prompt + your scan into your AI agent** (Claude Code, ChatGPT, Codex, Gemini, or DeepSeek), e.g.:
   > "Here is my phone's package dump and build profile. Using the attached AI-Phone-Debloater master prompt, produce a debloat plan JSON classifying every package into the 4 safety tiers, then tell me which packages are safe to disable/uninstall and which are blacklisted."

4. **Review the AI's JSON plan.** Every entry must include a `reason`, an `action` (`disable` or `uninstall-keep-data`), and estimated battery/RAM gains. Tier-4 packages must be marked `dangerous: true`.

5. **Apply the plan** with the engine:
   ```bash
   python scripts/debloat-engine.py --dry-run        # verify first
   python scripts/debloat-engine.py --debloat        # then apply
   ```

6. **Restore anything** you change your mind about:
   ```bash
   python scripts/debloat-engine.py --restore <package>
   ```

The full prompt contract (workflow, JSON schema, 4 tiers, blacklist table, output contract) lives in `prompts/ai-debloat-system-prompt.md`.

---

## FAQ & Troubleshooting

### Device unauthorized
`adb devices` shows your phone as `unauthorized`. This means you haven't accepted the RSA debugging prompt on the phone.
- Unlock the phone, look for the **"Allow USB debugging?"** dialog, check "Always allow from this computer," and tap **OK**.
- If you don't see the prompt, revoke USB debugging authorizations in **Developer options → Revoke USB debugging authorizations**, unplug the phone, plug it back in, and re-run the launcher.

### Device not detected
`adb devices` lists nothing.
- Make sure USB debugging is enabled in **Developer options**.
- Try a different USB cable (some cables are charge-only).
- Try a different USB port; on desktops, use a rear port directly on the motherboard.
- For Windows, you may need the Google USB driver or your OEM's driver installed.
- Re-run `scripts/setup-adb.ps1` (Windows) or `scripts/setup-adb.sh` (Mac/Linux) to confirm ADB is installed and the server is running.

### How restore works
Every debloat action uses `pm uninstall -k --user 0` (keeps private data) or `pm disable-user --user 0` (hides the app but keeps it installed). To bring an app back:
- **Disabled apps:** `cmd package install-existing <package>` (or the engine's `--restore`).
- **Uninstalled-with-`-k` apps:** reinstall for user 0; your private data under `/data/user/0` is preserved because `-k` was used, so the app resumes as if nothing happened.
- Never a factory reset required.

### Will this brick my phone?
No. The engine never touches the `/system` partition, never runs `pm uninstall --force`, and refuses any package on the critical blacklist (`rules/critical-do-not-touch.json`). All changes are confined to the `user 0` profile and are fully reversible.

### Will debloating delete my WhatsApp messages, photos, or contacts?
**No. Zero personal data loss.**
The engine operates strictly using `pm uninstall -k --user 0 <package>` or `pm disable-user --user 0 <package>`. The `-k` flag instructs Android's Package Manager to keep application data directories (`/data/user/0/<package>`) completely intact. Furthermore, your personal media, photos, contacts, and personal apps are never included in debloat rules.

### Does debloating void my phone's warranty or trip Knox / SafetyNet?
**No.** Debloating via ADB does NOT unlock the bootloader and does NOT root your phone. Knox counter remains 0x0 (void: 0), SafetyNet / Play Integrity API continues to pass, and banking apps / Google Pay continue to work without issue.

### What Android versions are supported?
Any device running **Android 8.0 (Oreo) through Android 15+** is fully supported, because `pm disable-user --user 0` and `pm uninstall -k --user 0` are standard package-manager commands available from Android 8.0 onward.

---

## 🔍 Supported OEMs & Systems

- **Samsung:** One UI 7, 6, 5, 4 (Galaxy S24/S23/S22/S21, Z Fold/Flip, A-Series)
- **Xiaomi / Redmi / POCO:** HyperOS, MIUI 14, 13, 12 (MSA ads, Joyose, Mi Cloud)
- **Google Pixel:** Android 15, 14, 13 (Pixel 9, 8, 7, 6, Fold)
- **OnePlus:** OxygenOS 15, 14, 13 (OPBugreport, HeyTap, ODM loggers)
- **BBK Electronics:** Oppo ColorOS, Vivo FuntouchOS / OriginOS, Realme UI (Glance lockscreen ads)
- **Motorola:** Hello UI, My UX (Moto Care, Hello You, partner apps)
- **Transsion:** Tecno HiOS, Infinix XOS, Itel (Palm Store, AHA Games, Carlcare)
- **Universal Preloads:** Facebook / Meta, Microsoft, Netflix, Amazon, Carrier Telemetry

---

## 🏷️ Keywords & Search Topics

`android debloater` • `phone debloater` • `universal android debloater` • `uad alternative` • `debloat samsung one ui` • `debloat xiaomi hyperos` • `remove bloatware android no root` • `debloat phone without losing data` • `uninstall system apps android adb` • `best android debloater 2026` • `remove glance lockscreen ads` • `disable bixby samsung` • `debloat oneplus oxygenos` • `android battery optimizer` • `ai phone debloater` • `claude code debloat`

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add OEM package rules and propose package removals.

## Safety

Please read [SAFETY_GUIDELINES.md](SAFETY_GUIDELINES.md) before running the debloat engine on a real device. It explains the Android package architecture, why personal data is safe, the blacklist protections, and emergency rollback procedures.