---
name: Bug Report
about: Report a problem with the debloat engine, OEM rules, or launchers
title: "[Bug] <short description>"
labels: ["bug", "triage"]
assignees: ""
---

## 🐛 Bug Report

### What happened?
Clear and concise description of the bug.

### What did you expect to happen?

### How to reproduce (steps)
1. 
2. 
3. 

### Environment
- **OS (PC):** Windows 10/11, macOS, Linux distro
- **Python version:** `python --version` →
- **ADB version:** `adb version` →
- **Phone manufacturer / model:** e.g. Samsung Galaxy S24, Xiaomi 14
- **Android version / skin:** e.g. Android 14, One UI 6
- **Launcher used:** `debloat.bat` / `debloat.sh` / `python scripts/debloat-engine.py`

### Device state
- USB debugging authorized: yes/no
- Device rooted: yes/no
- Bootloader unlocked: yes/no

### Logs / output
Paste the command output or attach a log. Use `python scripts/debloat-engine.py --dry-run` first and include its output.

```
<output here>
```

### Checklist
- [ ] I read [SAFETY_GUIDELINES.md](SAFETY_GUIDELINES.md)
- [ ] I searched existing issues to avoid duplicates
- [ ] I included the exact `adb` command that failed (if any)
