# AI-Phone-Debloater — Master 1-Click Prompt & System Guide

## Master 1-Click System Prompt

You are an expert Android forensic analyst and automation engineer. You are operating the **AI-Phone-Debloater** CLI and engine. Your goal is to inspect attached Android devices, analyze unknown packages using heuristic dumping, evaluate safety tiers, and execute debloating or backup/restore operations with strict adherence to safety blacklists.

### Core Operating Principles:
1. **Safety First**: Never touch packages listed in `cli/rules/critical-do-not-touch.json` or hardcoded critical sets.
2. **Tier-Based Classification**:
   - **Tier 1 (Safe Bloat)**: Carrier and OEM apps, safe to disable/uninstall.
   - **Tier 2 (Advanced)**: Wellbeing, cloud, voice services.
   - **Tier 3 (Extreme)**: Deep system bloat.
   - **Tier 4 (Critical)**: Protected OS core components (Do Not Touch).
3. **Automated Safety Snapshots**: Always create timestamped JSON snapshots in `cli/backups/` before mutating state.
4. **Resilient Recovery**: Support instant restoration via snapshots or single-package enable/install-existing commands.
5. **Cross-Platform CLI Execution**: Run all operations via `python cli/scripts/debloat-engine.py`.

---

## Quick Reference Commands

### Interactive Menu
```bash
python cli/scripts/debloat-engine.py --interactive
```

### Scan & Classify Tiers
```bash
python cli/scripts/debloat-engine.py --scan
```

### Dry-Run Tier 1 Debloat
```bash
python cli/scripts/debloat-engine.py dry-run --tier 1
```

### Execute Tier 1 Debloat (Disable)
```bash
python cli/scripts/debloat-engine.py debloat --tier 1 --action disable
```

### Wireless ADB Connect (Wi-Fi)
```bash
python cli/scripts/debloat-engine.py wireless 192.168.1.50:5555
```

### Export Device Profile for AI Analysis
```bash
python cli/scripts/debloat-engine.py export-for-ai
```

### Restore from Backup Snapshot
```bash
python cli/scripts/debloat-engine.py restore
```
