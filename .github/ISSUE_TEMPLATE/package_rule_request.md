---
name: Package Debloat Rule Request
about: Propose adding or updating an OEM bloatware package rule
title: "[RULE]: Add <package.name> (<OEM>)"
labels: ["rule-request", "enhancement"]
assignees: ""
---

### Package Details
- **Package Name (e.g., `com.example.bloat`):**
- **App Display Name:**
- **OEM / Manufacturer:** (Samsung, Xiaomi, Pixel, OnePlus, BBK, Motorola, Transsion, etc.)
- **Device Model & Android Version:**

### Classification
- [ ] Tier 1: Safe Bloatware / Adware / Telemetry (zero impact on core functions)
- [ ] Tier 2: Advanced (replaces stock app like browser/notes, safe if alternative installed)
- [ ] Tier 3: Extreme (removes features like AOD or voice assistants)

### Recommended Action
- [ ] Disable (`pm disable-user --user 0`)
- [ ] Uninstall (`pm uninstall -k --user 0`)

### Why should this be debloated?
Explain what this package does and why removing it improves battery, privacy, or performance:
