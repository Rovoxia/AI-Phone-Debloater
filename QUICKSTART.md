# 🚀 Quickstart Cheat Sheet (3 Steps)

Get your Android phone debloated at the maximum safe level in under 2 minutes with **zero personal data loss**.

---

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
- Press **`2`** to **Dry-Run Simulate** (shows what will be removed without touching anything).
- Press **`3`** to **Safely Debloat Tier 1** (removes carrier junk, preloaded bloatware, and ad telemetry).
- Press **`4`** to **Deep Debloat Tier 2** (removes Bixby/assistants, OEM cloud sync, and digital wellbeing).
- Press **`5`** to **Export for AI** (creates a profile to feed Claude, ChatGPT, or Codex).
- Press **`6`** to **Restore / Revert** (1-click snapshot rollback bringing back any app).

---

### 🛡️ Why Your Data Is 100% Safe:
- We never touch the read-only `/system` partition.
- All operations run on `user 0` using the preservation flag (`-k`).
- Your contacts, WhatsApp messages, photos, accounts, and saved logins are **100% untouched**.
