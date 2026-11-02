# Claude Code CLI — AI Phone Debloater Workflow

You are running Claude Code CLI **directly inside** the `AI-Phone-Debloater/` repository.
Your mission is to guide the user through an automated, 100% fail-safe debloating pass on their connected Android phone with zero data loss.

---

## ⚡ 1-Click Execution Prompt

```text
Clone https://github.com/Rovoxia/AI-Phone-Debloater.git and guide me through safely debloating my connected Android phone. Execute the workflow strictly in the following order:

1. Clone & Verify Connection:
   - Clone the repository and enter the directory.
   - Verify that my Android device is connected and authorized via ADB (either via USB cable or over Wi-Fi via Wireless Debugging).

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

---

## Repository Layout

```
AI-Phone-Debloater/
├── README.md                              # Main documentation & quickstart
├── SAFETY_GUIDELINES.md                  # Deep technical safety documentation
├── CONTRIBUTING.md                        # Community rules contribution guide
├── LICENSE                                # MIT License
├── debloat.bat                            # Windows 1-click launcher
├── debloat.sh                             # macOS / Linux 1-click launcher
├── requirements.txt                       # Python dependencies (stdlib core)
├── prompts/
│   ├── ai-debloat-system-prompt.md        # Universal Master Prompt for any LLM
│   ├── claude-code-prompt.md              # This file (for Claude Code CLI)
│   └── device-analysis-prompt.md          # Obscure/Unknown package analysis
├── rules/                                 # Complete OEM rule databases (JSON)
│   ├── critical-do-not-touch.json         # Protected Android OS core (Never touched)
│   ├── universal-safe-to-remove.json      # Cross-OEM bloat, Facebook, Microsoft, etc.
│   ├── samsung-oneui.json                 # Samsung One UI (Bixby, AR Zone, GOS)
│   ├── google-pixel.json                  # Pixel UI (Tips, Ambient Services, etc.)
│   ├── xiaomi-miui-hyperos.json           # Xiaomi/Redmi/POCO (MSA ads, Analytics)
│   ├── oneplus-oxygenos.json              # OnePlus (OPBugreport, HeyTap, etc.)
│   ├── bbk-oppo-vivo-realme.json          # Oppo ColorOS, Vivo OriginOS, Realme UI
│   └── motorola.json                      # Motorola Hello UI / My UX bloat
├── scripts/
│   ├── debloat-engine.py                  # Core engine (scan, dry-run, debloat, restore)
│   ├── setup-adb.ps1                      # Windows automatic ADB installer & tester
│   └── setup-adb.sh                       # macOS/Linux automatic ADB installer
└── backups/                               # Safety snapshots saved here automatically
```

---

## Step-by-Step Execution Flow for Claude Code

### Step 1: Verify Connection & Scan Device
Connect via USB or wirelessly over Wi-Fi:
- **USB:** Connect cable, ensure USB debugging is enabled on phone.
- **Wireless (Wi-Fi, Android 11+):** `python scripts/debloat-engine.py wireless <ip>:<port> --pair <code>`

Run the scanner to discover the connected phone and classify all packages:

```bash
python scripts/debloat-engine.py scan
```

Claude will observe:
- Connected device model, manufacturer, and Android version.
- Package counts categorized across Safety Tiers (Tier 1: Safe, Tier 2: Advanced, Tier 3: Extreme, Tier 4: Critical).
- Any unknown or third-party packages.

### Step 2: Export Device Profile for AI Analysis
If the user wants a personalized review or has obscure carrier apps:

```bash
python scripts/debloat-engine.py export-for-ai
```

This generates `device-profile_<model>_<timestamp>.json` and `.md` with complete package states.

### Step 3: Run Simulation (Dry-Run Mode)
Before making ANY changes to the phone, ALWAYS simulate the actions:

```bash
# Preview Tier 1 (Safe Bloatware & Trackers):
python scripts/debloat-engine.py dry-run --tier 1

# Preview Tier 2 (Optional OEM Services):
python scripts/debloat-engine.py dry-run --tier 2
```

Claude reviews the dry-run output with the user, ensuring:
- Zero packages from `critical-do-not-touch.json` are touched.
- The user understands what will be disabled.

### Step 4: Execute Debloat (With Automatic Backup Snapshot)
Once the user confirms approval:

```bash
# Safe Debloat (Disable user 0 - Recommended):
python scripts/debloat-engine.py debloat --tier 1

# Or with specific action:
python scripts/debloat-engine.py debloat --tier 1 --action disable
```

The engine automatically takes a full snapshot backup to `backups/` before running any `pm` commands!

### Step 5: (Optional) Apply a Custom AI Debloat Plan
If an AI agent generated a custom JSON plan:

```bash
python scripts/debloat-engine.py apply-ai-plan my-plan.json --action disable
```

*Note: The engine strictly verifies the plan against `critical-do-not-touch.json`. If any protected package is included, execution is immediately aborted.*

### Step 6: Rollback / Restore at Any Time
If the user wants to revert or bring back an app:

```bash
# Restore an individual app:
python scripts/debloat-engine.py restore --pkg com.samsung.android.bixby.agent

# Restore everything from a snapshot:
python scripts/debloat-engine.py restore <snapshot_filename>

# List all available snapshots:
python scripts/debloat-engine.py list-backups
```

---

## Claude Code Safety Guardrails

| Rule | Enforcement |
|---|---|
| **Never Touch Critical Packages** | Any package in `critical-do-not-touch.json` is hard-blocked. |
| **Dry-Run First** | Always run `dry-run` and show the summary to the user before running `debloat`. |
| **Preserve User Data** | All uninstalls use `-k` to keep app data, or `pm disable-user --user 0`. |
| **Require User Confirmation** | Never run with `--yes` unless the user explicitly requests fully autonomous execution. |
| **Instant Rollback Ready** | Every action is snapshotted to `backups/` for 1-click restore. |
