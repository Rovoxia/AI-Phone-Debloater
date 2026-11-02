# AI-Phone-Debloater — Safety Guidelines

Read this document in full before running the debloat engine on a real device. It explains the Android package architecture, why personal data is safe, how the blacklist protects critical packages, and exactly how to recover in every scenario.

---

## 1. Android Package Architecture

Android installs applications as **packages** identified by a reverse-domain name (e.g. `com.google.android.youtube`). The package manager (`pm`, exposed through `adb shell pm`) is the gatekeeper for installation, removal, enabling, and disabling.

### Partitions and what lives where

| Partition | Path | What lives here | User accessible? | Touched by this tool? |
|---|---|---|---|---|
| System | `/system` | Android framework, default system apps, HALs | No (read-only, dm-verity protected) | **Never** |
| Vendor | `/vendor`, `/vendor.x86`, `/vendor_dlkm` | OEM firmware services, kernel modules | No | **Never** |
| User apps (per-UID) | `/data/app/<package>` | Installed APKs per user | Yes | Indirectly (registration only) |
| User private data | `/data/user/0/<package>` | User 0's app data, databases, preferences | Yes | **Preserved** (`-k`) |
| Shared media | `/data/media` | Pictures, videos, downloads | Yes | **Never** |
| Shared misc | `/data/misc` | SharedPreferences, dumpsys state | Partial | **Never** |

### The two boundaries this tool respects

1. **Never touch `/system` or `/vendor`.** On modern Android these are mounted read-only and protected by **dm-verity**. Modifying them requires an unlocked bootloader, root, and a custom recovery (TWRP). Attempting it can trigger a boot loop or permanent brick. AI-Phone-Debloater does none of this.

2. **Only touch the `user 0` profile.** All commands run as `pm <action> --user 0`, which affects only the primary user's registration of a package, not the underlying system image.

---

## 2. `/system` partition vs user profiles (`--user 0`)

### `/system` (read-only, dm-verity)

The `/system` partition holds the Android framework and pre-installed system apps. It is mounted **read-only** and protected by **dm-verity**, a kernel-level verified-boot mechanism that hashes the partition at boot. Any modification to `/system` causes the hash check to fail and the device refuses to boot.

Because of this, you **cannot** delete bloatware from `/system` without root + a custom recovery. AI-Phone-Debloater never attempts it. There is no scenario in which this tool needs write access to `/system`.

### User profiles (`--user 0`)

Android supports multiple users. The primary user is `user 0`. When you "uninstall" an app for a user, Android does **not** delete the APK from `/system` (it can't — it's read-only). Instead it:

1. Unregisters the package for that user (removes it from the launcher, settings, and package list for that user).
2. Optionally removes the app's private data under `/data/user/0/<package>` — unless you pass `-k` (keep data).

This is why debloating via `pm uninstall -k --user 0` is safe, rootless, and fully reversible: you are only changing **user-level registration state**, never the system image.

---

## 3. Deep dive: `pm uninstall -k --user 0` and `pm disable-user --user 0`

### `pm disable-user --user 0 <package>`

- Hides the app from the launcher, app drawer, and settings UI.
- The package stays **installed**; its APK and data remain on disk.
- The app cannot run (components are disabled), but it is fully registered.
- **Most reversible.** Restore with `cmd package install-existing <package>`.
- **Use this by default** for bloatware you're unsure about.

### `pm uninstall -k --user 0 <package>`

- Unregisters the package for `user 0` (apps see it as uninstalled).
- The `-k` flag means **keep data**: the app's private directory under `/data/user/0/<package>` is preserved.
- Because `/system` is read-only, the APK itself usually remains on disk; only the user-level registration is dropped.
- **Reversible.** Reinstall for user 0 and data is still there thanks to `-k`.

### Why apps can be "uninstalled" without root

On modern Android, pre-installed apps live in `/system` or `/product` (read-only). `pm uninstall --user 0` does not delete those read-only APKs. It removes the package from the **current user's** view. That is why no root is required and why it cannot break the OS the way deleting files from `/system` would.

### Restoration: `cmd package install-existing`

To bring a disabled/uninstalled-for-user app back:
```bash
adb shell cmd package install-existing <package>
```
This re-registers the existing (still-present) APK for `user 0`. Because data was preserved (`-k`) or never removed (`disable-user`), the app resumes with its accounts and settings intact.

---

## 4. Why personal data is safe

### Data partition vs APK registration

Personal data — photos, contacts, messages, WhatsApp databases, logins — lives under `/data/user/0/<package>/` (and shared media under `/data/media/`). None of that is part of the package's APK registration.

- `pm disable-user` never touches `/data/user/0` at all.
- `pm uninstall -k` explicitly **keeps** `/data/user/0` thanks to the `-k` flag.

AI-Phone-Debloater **never** runs:
- `pm uninstall --user 0 <package>` (without `-k`) — may drop data.
- `pm uninstall --user 0 --force <package>` — wipes data, no fallback.
- `rm -rf /data/...` or any direct filesystem deletion.

Your photos, contacts, WhatsApp, and logins stay 100% untouched because the tool only changes **package registration state** for `user 0`, never the files under `/data`.

### What `-k` actually preserves

When you run `pm uninstall -k --user 0 <package>`:
- Package registration for user 0 is removed.
- `/data/user/0/<package>` (databases, SharedPreferences, files, login tokens) is **kept**.
- If you later reinstall the package for user 0, Android re-links it to that same data directory, so the app resumes exactly as before.

---

## 5. Blacklist breakdown: code-level protection of critical packages

Some packages manage fundamental subsystems (status bar, telephony, radio, settings provider, Bluetooth, Wi-Fi, keystore). Touching them can break calls, networking, or boot. AI-Phone-Debloater protects them with **code-level checks** in `rules/critical-do-not-touch.json` and the debloat engine.

### Blacklisted categories (never remove or disable)

| Package / category | System role | Why it must not be touched |
|---|---|---|
| `com.android.systemui` | Status bar, notification shade, quick settings, recents | Removes the entire UI shell; notifications and settings become inaccessible |
| `com.android.server.telecom` | Telecom service: calls, SMS routing, Bluetooth headset | Breaks calling, SMS, MTP over Bluetooth headset |
| `com.android.providers.telephony` | Cellular provider, SIM card management | Cellular connectivity, calling, carrier profile |
| `android.security.keystore` | Keystore backend, secure storage | Fingerprint unlock breaks, encryption metadata corrupts |
| `com.android.server.telephony.Radio` | RIL: cellular radio backend | Network, carrier settings, signal bars |
| `com.android.providers.settings` | Settings provider DB | Persistent settings corruption, boot loop |
| `com.android.bluetooth.*` / `android.hardware.bluetooth.*` | Bluetooth daemon | BT pairing/audio fails, module init failure |
| `com.android.wifi.*` / `android.hardware.wifi.*` | Wi-Fi daemon | Wi-Fi, hotspot, peer discovery fail |
| `android.hardware.usb.*` | USB composite USB service | MTP/PTP broken, USB host devices die |

### How code-level checks work

The debloat engine loads `rules/critical-do-not-touch.json` before executing anything. Every package in a user's plan is compared against the blacklist:

- If a package **matches** the blacklist, the engine **refuses** the action and logs a hard error, even if an AI agent recommended it.
- Tier-4 packages in any AI-generated plan must be marked `dangerous: true`; the engine treats these as read-only.
- The engine never executes `pm uninstall --force` under any circumstances.

If a user insists on a blacklisted package, the only acceptable action is `pm disable-user` (hides UI, keeps binary), never full removal — and only with explicit acknowledgment that it is recoverable.

---

## 6. Recovery guide: what to do in every scenario

| Scenario | What happened | Recovery |
|---|---|---|
| You disabled an app and want it back | `pm disable-user --user 0 <pkg>` | `adb shell cmd package install-existing <pkg>` (or engine `--restore`) |
| You uninstalled with `-k` and want data back | `pm uninstall -k --user 0 <pkg>` | Reinstall for user 0; `/data/user/0/<pkg>` is preserved so the app resumes with accounts/settings |
| You disabled something and the UI broke | A system UI component was disabled | Boot into safe mode or use `adb shell cmd package enable <pkg>` / `install-existing` |
| The phone won't boot | Should not happen — `/system` is never touched | If it does, it is unrelated to this tool; use your OEM's recovery / factory image |
| You want to undo everything | Multiple packages debloated | Restore each package individually via `--restore <pkg>`, or re-apply a saved plan in reverse |

### Emergency rollback commands

```bash
# Restore a single disabled/uninstalled app
adb shell cmd package install-existing <package>

# Reinstall a package for user 0 (keeps -k preserved data)
adb shell cmd package install-existing --user 0 <package>

# List disabled packages to find what to restore
adb shell pm list packages -d

# List all packages for user 0
adb shell pm list packages -U 0

# Full engine rollback
python scripts/debloat-engine.py --restore <package>
```

### Rollback command

The engine provides `python scripts/debloat-engine.py restore <package>` (or `restore <snapshot>`) to restore any package on demand without a factory reset. Every debloat action recommended by an AI agent must be reversible using this path.

---

## Golden rules (non-negotiable)

1. **Zero data loss.** Never delete, modify, or move SMS, contacts, photos, app data, call logs, or personal files. Commands target packages and system state only.
2. **Dry-run first.** Every debloat command is verified with `--dry-run` before executing. If anything looks risky, ask for confirmation instead of proceeding.
3. **Rollback is always possible.** A rollback can restore any package on demand. No factory reset is ever required.
4. **User data is sacred.** Data lives under `/data/user/0`; system state lives under `/system`, `/vendor`. You only touch the user partition where specified (`--user 0`).
5. **Blacklist is absolute.** Critical packages are protected by code-level checks and are never removed, disabled, or modified without explicit, informed user acknowledgment (disable-only, never uninstall).