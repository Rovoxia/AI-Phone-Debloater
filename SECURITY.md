# Security Policy

## Supported Versions

AI-Phone-Debloater is an open-source Android debloating utility. Security updates apply to the latest release branch.

| Version | Supported |
|---------|-----------|
| 1.3.x   | :white_check_mark: |
| < 1.3   | :x: |

## Reporting a Vulnerability

AI-Phone-Debloater does not expose network services by default. The optional local WebApp bridge (`python cli/src/bridge_server.py` or `debloat_engine.py --bridge`) listens only on 127.0.0.1 (port 53123 by default) and only accepts browser requests from https://debloater.rovoxia.com or origins you pass with `--allow-origin` (localhost origins are not trusted by default). Every route except `GET /health` also requires a per-session token in the `X-Bridge-Token` header; requests without it get `401`. The one-click scripts (`bridge.sh` / `bridge.ps1`) generate a fresh random token per run, pass it to the bridge in `AIPD_BRIDGE_TOKEN`, and open `https://debloater.rovoxia.com/app?bridge=1#token=<token>`; the token is in the URL fragment, which browsers do not send to servers, and the web app moves it to `sessionStorage` and removes it from the address bar. A bridge started by hand generates a token and prints the URL to open. Treat that URL as a password for the session. A custom `AIPD_BRIDGE_TOKEN` must be at least 16 characters from `A-Z a-z 0-9 . _ ~ -`. It operates locally on your machine via ADB commands issued to your own Android device.

Besides listing devices and packages, freezing, uninstalling and restoring packages, and Wi-Fi QR pairing, a caller that holds the session token can make the bridge run `adb pair` (`POST /pair/code`) and `adb connect` (`POST /connect`) against an IPv4 address and port it supplies, and `adb reconnect offline` (`POST /reconnect`), which affects every tool that uses the same adb server. `GET /mdns` reports what adb's mDNS discovery sees. The bridge accepts only an IPv4 address, a port from 1 to 65535 and a six-digit pairing code, and does not log the pairing code. The full route list is in the docstring at the top of `cli/src/bridge_server.py`.

If you believe you've found a security issue (for example, a rules-file injection risk, unsafe package-removal bypass, or hard-coded credential exposure), please:

1. **Do not** open a public GitHub issue.
2. Email the maintainer at the address listed in the repository profile or contact the organization at https://rovoxia.com.
3. Include: affected version, Android version/OEM skin, ADB commands involved, and steps to reproduce.

We will acknowledge receipt within 3 business days and provide an initial assessment within 7 business days.

## Safety Architecture (Defense in Depth)

- **Rootless execution only** — operates on Android User 0 via `pm disable-user` / `pm uninstall -k`. Never modifies `/system`, never requires root or an unlocked bootloader.
- **Critical blacklist** — 89 core system packages (SystemUI, Telephony, Keystore, package installer, etc.), loaded from `cli/rules/critical-do-not-touch.json`, are permanently blocked in code and cannot be removed by any flag, argument, or AI prompt.
- **Automatic JSON snapshots** — timestamped backup of package state before any mutation (unless `--no-backup` is passed); 1-click rollback via `--restore`.
- **Tiered rules** — 4 safety tiers (Tier 1 safe → Tier 4 critical), never exceeded without explicit user confirmation.
- **Bridge gate** — loopback `Host` check, web-origin allowlist and per-session token on the local bridge.
- **No pip dependencies** — Python standard library only, reducing supply-chain surface.

## Disclaimer

AI-Phone-Debloater is provided under the MIT License "as is," without warranty. Modifying system packages carries inherent risk. Always back up important data before running Tier 2 or Tier 3 debloating.
