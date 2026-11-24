# AI Phone Debloater pricing

Product: AI Phone Debloater
Price: $0. Free and open source under the MIT License.
Editions: one free edition with every feature. There is no paid plan, subscription, account or license key.
Website: https://debloater.rovoxia.com
Source: https://github.com/Rovoxia/AI-Phone-Debloater

## What is included

- ADB debloat engine with no root needed (Python 3.11+, standard library only, nothing to pip-install)
- Interactive CLI menu, USB and wireless ADB, and QR pairing on Android 11+
- Web app at https://debloater.rovoxia.com/app over WebUSB or a local bridge with a per-session token
- 352 curated rules in four tiers: Tier 1 Safe (196), Tier 2 Advanced (66), Tier 3 Extreme (1) and Tier 4 Critical (89, blocked)
- 89 critical system packages that the engine and the bridge refuse to disable or uninstall
- Master AI prompt for coding agents (`prompt/master-prompt.md`, served at https://debloater.rovoxia.com/prompt.md)
- One-line installers: `irm https://debloater.rovoxia.com/run.ps1 | iex` (Windows) and `curl -fsSL https://debloater.rovoxia.com/run.sh | bash` (macOS, Linux)
- A JSON restore snapshot before each change, and `--restore` to undo it
- No ads, no telemetry, no account
- MIT License: free to use, modify and distribute

## What the tool does and does not do

Changes are made with `pm disable-user` and `pm uninstall -k` for one Android user and can be undone; the system partition is not modified. The tool does not root the phone, unlock the bootloader or flash anything. Official OTA updates keep installing, with one exception: the single Tier 3 rule, the Transsion OTA updater (`com.transsion.otaupdate`), stops system updates while it is disabled. The software is provided "as is" under the MIT License, without warranty.
