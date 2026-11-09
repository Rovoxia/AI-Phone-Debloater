# 🚀 Quickstart Guide — AI-Phone-Debloater

Clean your phone and remove preloaded OEM bloatware at the maximum safe level in under 2 minutes with **100% reversible execution** and **zero root required**.

🌐 **Official Website & Docs:** [https://debloater.rovoxia.com](https://debloater.rovoxia.com)  
🤖 **Master AI Prompt Raw Endpoint:** [https://debloater.rovoxia.com/prompt.md](https://debloater.rovoxia.com/prompt.md)

---

## ⚡ Track 1: 1-Click AI Agent Execution (Recommended)

Copy & paste this official master prompt directly into **Claude Code CLI**, **ChatGPT**, **Cursor**, **Windsurf**, or **Gemini**:

```text
Clone https://github.com/Rovoxia/AI-Phone-Debloater.git and guide me through safely debloating my connected Android phone. Execute strictly in this order:

1. Environment & Connection Check:
   - Verify ADB connectivity (python cli/src/debloat_engine.py --scan or adb devices -l).
   - Resolve ADB from PATH, local repo tools, or auto-download Google SDK Platform-Tools if missing.

2. Device Profiling & Classification:
   - Identify device manufacturer, model, and Android OS version.
   - Cross-reference installed packages against cli/rules/*.json and classify into 4 Safety Tiers.

3. Dry-Run Simulation:
   - Default strictly to Tier 1 (Safe Bloat). Run: python cli/src/debloat_engine.py --tier 1 --dry-run
   - Display the proposed changes table and pause for my confirmation before modifying anything.

4. Snapshot & Safe Execution:
   - Create an automated backup snapshot (`~/AiPhoneDebloater/backups/snapshot_<model>_<timestamp>.json`).
   - Execute safe debloat using `disable` (or `uninstall -k`), ensuring all personal files remain intact.
   - Display the restore command for instant rollback.
```

The AI agent will detect your phone, verify safety guardrails (0 collisions with critical system packages), simulate the run, and safely debloat your device with an automated backup snapshot.

---

## ⚡ Track 2: Zero-Git Single-Command Run (No Clone Needed)

Run the debloat engine immediately in your terminal without manual cloning:

### Windows (PowerShell)
```powershell
irm https://debloater.rovoxia.com/run.ps1 | iex
```

### macOS / Linux (Bash / Zsh)
```bash
curl -sSL https://debloater.rovoxia.com/run.sh | bash
```

---

## 🛠️ Track 3: Local Repository Clone & Interactive TUI

### Step 1: Enable USB Debugging on Your Phone
1. Go to **Settings** > **About Phone**.
2. Tap **Build Number** 7 times until you see *"You are now a developer!"*.
3. Go back to **Settings** > **System** (or **Developer Options**).
4. Turn **ON** **USB Debugging**.
5. Connect your phone to your PC via USB cable.
6. When prompted on your phone screen with **"Allow USB Debugging?"**, check **"Always allow from this computer"** and tap **Allow**.

---

### Step 2: Run the 1-Click Launcher

- **On Windows:**
  Double-click `cli\bin\debloat.bat` (or in PowerShell run `.\cli\bin\debloat.bat`)

- **On macOS / Linux:**
  Open terminal and run `bash cli/bin/debloat.sh`

*(The launcher auto-detects ADB on `PATH` or in `cli/tools/platform-tools`.)*

---

### Step 3: Choose Your Action from the Menu

From the interactive menu:
- Press **`1`** to **Scan & Audit** your phone (classifies all installed apps into Safety Tiers).
- Press **`2`** to **Dry-Run Simulate Tier 1** (simulates removal without making any device changes).
- Press **`3`** to **Safely Debloat Tier 1** (removes carrier junk, preloaded bloatware, and ad telemetry).
- Press **`4`** to **Deep Debloat Tier 2** (removes Bixby/assistants, OEM cloud sync, and digital wellbeing).
- Press **`5`** to **Extreme Debloat Tier 3** (removes non-essential stock app utilities).
- Press **`6`** to **Export for AI** (creates a JSON device profile for Claude, ChatGPT, or Cursor).
- Press **`7`** to **List Backups** (shows all timestamped snapshot archives).
- Press **`8`** to **Restore from Backup** (1-click snapshot rollback bringing back any app).
- Press **`9`** to **Restore Single Package** (re-enables/reinstalls any single app).
- Press **`w`** to **Connect via Wireless ADB (Wi-Fi)** (debloat without USB cable).

---

## 📶 Option C: Wireless ADB Debloating (No USB Cable • Wi-Fi)

- **Automatic Discovery:** If Wireless Debugging is active on your phone, the engine automatically detects it via mDNS and auto-connects — no IP address typing needed!
- **First-Time Pairing (Android 11+):**
  1. Make sure phone and PC are connected to the same Wi-Fi.
  2. On phone: **Settings → Developer Options → Wireless Debugging** (turn ON).
  3. Tap **"Pair device with pairing code"** to view the IP:Port and 6-digit code.
  4. Run launcher, press **`w`**, then select **`3`** to pair with the 6-digit code (or **`4`** to auto-discover via mDNS / LAN). After pairing, run:
     ```bash
     python cli/src/debloat_engine.py --wireless <ip>:<port>
     ```

---

### 🛡️ Why Your Data Is 100% Safe:
- We never touch the read-only `/system` partition (`dm-verity` protected).
- All operations run on `user 0` using the preservation flag (`-k`).
- Your contacts, WhatsApp messages, photos, accounts, and saved logins are **100% untouched**.
