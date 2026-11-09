# Security Policy

## Supported Versions

AI-Phone-Debloater is an open-source Android debloating utility. Security updates apply to the latest release branch.

| Version | Supported |
|---------|-----------|
| 1.0.0   | :white_check_mark: |

## Reporting a Vulnerability

AI-Phone-Debloater does not expose network services, process untrusted user input, or run as a server. It operates locally on your machine via ADB commands issued to your own Android device.

If you believe you've found a security issue (for example, a rules-file injection risk, unsafe package-removal bypass, or hard-coded credential exposure), please:

1. **Do not** open a public GitHub issue.
2. Email the maintainer at the address listed in the repository profile or contact the organization at https://rovoxia.com.
3. Include: affected version, Android version/OEM skin, ADB commands involved, and steps to reproduce.

We will acknowledge receipt within 3 business days and provide an initial assessment within 7 business days.

## Safety Architecture (Defense in Depth)

- **Rootless execution only** — operates on Android User 0 via `pm disable-user` / `pm uninstall -k`. Never modifies `/system`, never requires root or an unlocked bootloader.
- **Hard-coded critical blacklist** — 61 core system packages (SystemUI, Telephony, Keystore, package installer, etc.) are permanently blocked in code and cannot be removed by any flag, argument, or AI prompt.
- **Automatic JSON snapshots** — timestamped backup of package state before any mutation; 1-click rollback via `--restore`.
- **Tiered rules** — 4 safety tiers (Tier 1 safe → Tier 4 critical), never exceeded without explicit user confirmation.
- **No pip dependencies** — Python standard library only, reducing supply-chain surface.

## Disclaimer

AI-Phone-Debloater is provided under the MIT License "as is," without warranty. Modifying system packages carries inherent risk. Always back up important data before running Tier 2 or Tier 3 debloating.
