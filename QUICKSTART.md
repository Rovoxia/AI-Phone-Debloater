# 🚀 Quickstart Guide — Clean Your Phone with the Universal Phone Debloater

Clean your phone and debloat OEM bloatware at the maximum safe level with this powerful phone debloater in under 2 minutes with **zero personal data loss**.

🌐 **Official Website & Docs:** [https://debloater.rovoxia.com](https://debloater.rovoxia.com)

---

## ⚡ Option A: 1-Click AI Agent Execution (Recommended)

Just copy & paste this prompt into **Claude Code CLI**, **ChatGPT**, **Cursor**, or **Gemini**:

```text
Clone https://github.com/Rovoxia/AI-Phone-Debloater.git and guide me through safely debloating my connected Android phone. Execute the workflow strictly in the following order:

1. Clone & Verify Connection:
   - Clone the repository and enter the directory.
   - Verify that my Android device is connected and authorized via ADB.

2. Device Scan & Breakdown:
   - Run `python scripts/debloat-engine.py scan`.
   - Present a clear summary of my device information and detected bloatware packages.

3. Tier & Dry-Run Prompt (Interactive Check):
   - Clearly ask me which debloat tier I want to use (defaulting to Tier 1 — Safe if I don't specify).
   - Ask if I would like to run a `dry-run` simulation first before making actual changes:
     * If YES: Run the dry-run for the selected tier, show the exact packages that would be removed, and wait for my confirmation to proceed.
     * If NO: Proceed directly to step 4.

4. Auto-Snapshot & Safe Execution:
   - Take an automatic snapshot of the current package states so changes can be easily rolled back.
   - Execute the debloat for the selected tier while ensuring all personal data, app data, and user files remain 100% intact.
   - Show a final summary of the completed actions and where the backup snapshot is saved.
```

The AI agent will detect your phone, verify safety guardrails (0 collisions with critical system packages), simulate the run, and safely debloat your device with an automatic backup snapshot.

---

## 🛠️ Option B: Manual 3-Step Execution (No AI Required)

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
  Double-click `debloat.bat` (or in PowerShell run `.\debloat.bat`)

- **On macOS / Linux:**
  Open terminal and run `./debloat.sh`

*(The launcher will automatically download and configure Google's official ADB platform-tools if not already installed).*

---

### Step 3: Choose What to Do

From the interactive menu:
- Press **`1`** to **Scan & Audit** your phone (lists all apps into Safety Tiers).
- Press **`2`** to **Dry-Run Simulate Tier 1** (shows what will be removed without touching anything).
- Press **`3`** to **Safely Debloat Tier 1** (removes carrier junk, preloaded bloatware, and ad telemetry).
- Press **`4`** to **Deep Debloat Tier 2** (removes Bixby/assistants, OEM cloud sync, and digital wellbeing).
- Press **`5`** to **Extreme Debloat Tier 3** (removes non-essential system utilities).
- Press **`6`** to **Export for AI** (creates a profile to feed Claude, ChatGPT, or Codex).
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
  4. Run launcher, press **`w`**, select **`3`** to pair (or option **`1`** to auto-discover). Or run:
     ```bash
     python scripts/debloat-engine.py wireless <ip>:<port> --pair <code>
     ```

---

### 🛡️ Why Your Data Is 100% Safe:
- We never touch the read-only `/system` partition.
- All operations run on `user 0` using the preservation flag (`-k`).
- Your contacts, WhatsApp messages, photos, accounts, and saved logins are **100% untouched**.
