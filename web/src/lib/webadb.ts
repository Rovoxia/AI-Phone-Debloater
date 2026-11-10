/**
 * WebADB & Local Bridge Client for AI-Phone-Debloater WebApp Workspace
 * ====================================================================
 * Dual-Mode Android ADB Connector:
 * 1. WebAdbClient: Direct in-browser WebUSB client via @yume-chan/adb.
 * 2. LocalBridgeClient: HTTP client connecting to local bridge_server.py (127.0.0.1:53123).
 */

import { Adb, AdbDaemonTransport } from '@yume-chan/adb';
import { AdbDaemonWebUsbDeviceManager } from '@yume-chan/adb-daemon-webusb';
import AdbWebCredentialStore from '@yume-chan/adb-credential-web';

export interface DeviceInfo {
  serial: string;
  manufacturer: string;
  model: string;
  androidVersion: string;
  sdkVersion?: string;
  connectionType: 'webusb' | 'bridge';
}

export interface ExecutionResult {
  package: string;
  status: 'success' | 'failed' | 'skipped_protected';
  output: string;
}

/**
 * Exactly 89 Inviolable Tier 4 Core OS Packages from critical-do-not-touch.json
 */
export const CRITICAL_PACKAGES: Set<string> = new Set([
  'android',
  'com.android.biometrics',
  'com.android.bips',
  'com.android.bluetooth',
  'com.android.browser',
  'com.android.calendar',
  'com.android.carrierconfig',
  'com.android.cellbroadcastreceiver',
  'com.android.contacts',
  'com.android.desktopclock',
  'com.android.documentsui',
  'com.android.emergency',
  'com.android.externalstorage',
  'com.android.inputdevices',
  'com.android.inputmethod.latin',
  'com.android.keychain',
  'com.android.launcher',
  'com.android.launcher3',
  'com.android.location.fused',
  'com.android.mms',
  'com.android.mms.service',
  'com.android.mtp',
  'com.android.networkstack',
  'com.android.nfc',
  'com.android.ons',
  'com.android.packageinstaller',
  'com.android.pacprocessor',
  'com.android.permissioncontroller',
  'com.android.phone',
  'com.android.printspooler',
  'com.android.providers.blockednumber',
  'com.android.providers.calendar',
  'com.android.providers.contacts',
  'com.android.providers.downloads',
  'com.android.providers.downloads.ui',
  'com.android.providers.media',
  'com.android.providers.settings',
  'com.android.providers.telephony',
  'com.android.providers.userdictionary',
  'com.android.provision',
  'com.android.server',
  'com.android.server.activitymanager',
  'com.android.server.appop',
  'com.android.server.backup',
  'com.android.server.connectivity',
  'com.android.server.devicepolicy',
  'com.android.server.display',
  'com.android.server.input',
  'com.android.server.media',
  'com.android.server.net',
  'com.android.server.notification',
  'com.android.server.package',
  'com.android.server.power',
  'com.android.server.storage',
  'com.android.server.telecom',
  'com.android.server.trust',
  'com.android.server.usb',
  'com.android.server.wallpaper',
  'com.android.server.wm',
  'com.android.settings',
  'com.android.settings.intelligence',
  'com.android.sharedstoragebackup',
  'com.android.shell',
  'com.android.smspush',
  'com.android.statementservice',
  'com.android.storagemanager',
  'com.android.systemui',
  'com.android.systemui.plugin',
  'com.android.telecom',
  'com.android.telephonyprovider',
  'com.android.traceur',
  'com.android.vpndialogs',
  'com.android.wallpaper.livepicker',
  'com.android.wallpaperbackup',
  'com.android.wallpapercropper',
  'com.google.android.ext.services',
  'com.google.android.ext.shared',
  'com.google.android.feedback',
  'com.google.android.gms',
  'com.google.android.gsf',
  'com.google.android.networkstack',
  'com.google.android.onetimeinitializer',
  'com.google.android.packageinstaller',
  'com.google.android.partnersetup',
  'com.google.android.permissioncontroller',
  'com.google.android.printservice.recommendation',
  'com.google.android.providers.media.module',
  'com.google.android.syncadapters.contacts',
  'com.google.android.webview'
]);

/**
 * Direct in-browser WebUSB ADB Client (Chrome, Edge, Brave, Opera)
 */
export class WebAdbClient {
  private adb: Adb | null = null;
  private currentDevice: DeviceInfo | null = null;

  public static isSupported(): boolean {
    return typeof navigator !== 'undefined' && 'usb' in navigator;
  }

  public isConnected(): boolean {
    return this.adb !== null;
  }

  public getDevice(): DeviceInfo | null {
    return this.currentDevice;
  }

  public async connect(): Promise<DeviceInfo> {
    const manager = AdbDaemonWebUsbDeviceManager.BROWSER;
    if (!manager) {
      throw new Error(
        'WebUSB is not supported in this browser. Please use Chrome, Edge, Brave, Opera, or connect via our Local ADB Bridge.'
      );
    }

    // Triggers native browser USB device selector dialog
    const usbDevice = await manager.requestDevice();
    if (!usbDevice) {
      throw new Error('No device was selected in the USB picker.');
    }

    const connection = await usbDevice.connect();
    const credentialStore = new AdbWebCredentialStore();

    const transport = await AdbDaemonTransport.authenticate({
      serial: usbDevice.serial,
      connection,
      credentialStore,
    });

    this.adb = new Adb(transport);

    // Retrieve device properties
    let manufacturer = 'Android';
    let model = 'Device';
    let androidVersion = 'Unknown';
    let sdkVersion = '';

    try {
      manufacturer = (await this.getProp('ro.product.manufacturer')) || 'Android';
      model = (await this.getProp('ro.product.model')) || 'Device';
      androidVersion = (await this.getProp('ro.build.version.release')) || 'Unknown';
      sdkVersion = (await this.getProp('ro.build.version.sdk')) || '';
    } catch {
      // Fallback if getProp fails
    }

    this.currentDevice = {
      serial: usbDevice.serial,
      manufacturer,
      model,
      androidVersion,
      sdkVersion,
      connectionType: 'webusb',
    };

    return this.currentDevice;
  }

  public async disconnect(): Promise<void> {
    if (this.adb) {
      try {
        await this.adb.close();
      } catch {
        // Ignore close errors
      }
      this.adb = null;
      this.currentDevice = null;
    }
  }

  public async getProp(key: string): Promise<string> {
    if (!this.adb) throw new Error('Not connected');
    return (await this.adb.getProp(key)).trim();
  }

  public async runShell(command: string): Promise<string> {
    if (!this.adb) throw new Error('Not connected');

    if (this.adb.subprocess.shellProtocol) {
      const res = await this.adb.subprocess.shellProtocol.spawnWaitText(command);
      return (res.stdout || res.stderr || '').trim();
    }
    return (await this.adb.subprocess.noneProtocol.spawnWaitText(command)).trim();
  }

  public async listPackages(): Promise<string[]> {
    const output = await this.runShell('pm list packages -u --user 0');
    return output
      .split('\n')
      .map((l) => l.trim().replace(/^package:/, ''))
      .filter((pkg) => pkg.length > 0 && /^[a-zA-Z0-9._]+$/.test(pkg));
  }

  public async listDisabledPackages(): Promise<string[]> {
    try {
      const output = await this.runShell('pm list packages -d --user 0');
      return output
        .split('\n')
        .map((l) => l.trim().replace(/^package:/, ''))
        .filter((pkg) => pkg.length > 0 && /^[a-zA-Z0-9._]+$/.test(pkg));
    } catch {
      return [];
    }
  }

  public async execute(
    action: 'disable' | 'uninstall' | 'enable',
    pkg: string,
    mode: 'dry-run' | 'apply'
  ): Promise<ExecutionResult> {
    if ((action === 'disable' || action === 'uninstall') && CRITICAL_PACKAGES.has(pkg)) {
      return {
        package: pkg,
        status: 'skipped_protected',
        output: `BLOCKED: Inviolable Tier 4 critical package (${pkg}). Protection invariant enforced.`,
      };
    }

    if (mode === 'dry-run') {
      let cmd = '';
      if (action === 'disable') cmd = `pm disable-user --user 0 ${pkg}`;
      else if (action === 'uninstall') cmd = `pm uninstall -k --user 0 ${pkg}`;
      else cmd = `cmd package install-existing --user 0 ${pkg}`;
      return {
        package: pkg,
        status: 'success',
        output: `[dry-run] would execute: ${cmd}`,
      };
    }

    try {
      let cmd = '';
      if (action === 'disable') {
        cmd = `pm disable-user --user 0 ${pkg}`;
      } else if (action === 'uninstall') {
        cmd = `pm uninstall -k --user 0 ${pkg}`;
      } else {
        cmd = `pm enable --user 0 ${pkg}`;
      }

      const out = await this.runShell(cmd);
      const isSuccess =
        out.toLowerCase().includes('success') ||
        out.toLowerCase().includes('new state') ||
        out.toLowerCase().includes('enabled') ||
        out.toLowerCase().includes('installed') ||
        out === '';

      if (action === 'enable' && !isSuccess) {
        // Fallback for restoring uninstalled packages
        const restoreOut = await this.runShell(`cmd package install-existing --user 0 ${pkg}`);
        const restoreSuccess =
          restoreOut.toLowerCase().includes('installed') ||
          restoreOut.toLowerCase().includes('success');
        return {
          package: pkg,
          status: restoreSuccess ? 'success' : 'failed',
          output: restoreOut || out,
        };
      }

      return {
        package: pkg,
        status: isSuccess ? 'success' : 'failed',
        output: out,
      };
    } catch (err: any) {
      return {
        package: pkg,
        status: 'failed',
        output: err.message || String(err),
      };
    }
  }
}

/**
 * Local ADB Bridge Client connecting to localhost:53123
 */
export class LocalBridgeClient {
  private baseUrl: string;

  constructor(port: number = 53123) {
    this.baseUrl = `http://127.0.0.1:${port}`;
  }

  public setBaseUrl(url: string) {
    this.baseUrl = url.replace(/\/+$/, '');
  }

  public async checkHealth(): Promise<{ ok: boolean; version?: string; adbAvailable?: boolean }> {
    try {
      const res = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(2000),
      });
      if (res.ok) {
        const data = await res.json();
        return { ok: true, version: data.version, adbAvailable: data.adb_available };
      }
      return { ok: false };
    } catch {
      return { ok: false };
    }
  }

  public async getDevices(): Promise<Array<{ serial: string; model: string; state: string }>> {
    const res = await fetch(`${this.baseUrl}/devices`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) throw new Error(`Bridge returned HTTP ${res.status}`);
    const data = await res.json();
    return data.devices || [];
  }

  public async listPackages(serial: string): Promise<string[]> {
    const res = await fetch(`${this.baseUrl}/packages?serial=${encodeURIComponent(serial)}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) throw new Error(`Failed to fetch packages: HTTP ${res.status}`);
    const data = await res.json();
    return data.packages || [];
  }

  public async listDisabledPackages(serial: string): Promise<string[]> {
    const res = await fetch(
      `${this.baseUrl}/packages?serial=${encodeURIComponent(serial)}&view=disabled`,
      { method: 'GET', headers: { Accept: 'application/json' } }
    );
    if (!res.ok) return [];
    const data = await res.json();
    // Ignore a bridge that does not understand `view` — it would return every package.
    if (data.view !== 'disabled' || !Array.isArray(data.packages)) return [];
    return data.packages;
  }

  public async getDeviceProps(
    serial: string
  ): Promise<{ manufacturer?: string; model?: string; androidVersion?: string; sdkVersion?: string }> {
    try {
      const res = await fetch(`${this.baseUrl}/device?serial=${encodeURIComponent(serial)}`, {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(8000),
      });
      if (!res.ok) return {};
      return await res.json();
    } catch {
      return {};
    }
  }

  public async execute(
    serial: string,
    mode: 'dry-run' | 'apply',
    action: 'disable' | 'uninstall' | 'enable',
    packages: string[]
  ): Promise<ExecutionResult[]> {
    const res = await fetch(`${this.baseUrl}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ serial, mode, action, packages }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      throw new Error(err.error || `Execution failed with HTTP ${res.status}`);
    }
    const data = await res.json();
    return data.results || [];
  }

  public async restore(serial: string, packages: string[]): Promise<ExecutionResult[]> {
    const res = await fetch(`${this.baseUrl}/restore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ serial, packages }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      throw new Error(err.error || `Restore failed with HTTP ${res.status}`);
    }
    const data = await res.json();
    return data.results || [];
  }
}

/**
 * Snapshot representation for state backup and rollbacks
 */
export interface DebloatSnapshot {
  id: string;
  timestamp: string;
  model: string;
  manufacturer: string;
  serial: string;
  action: 'disable' | 'uninstall' | 'enable';
  mode: 'dry-run' | 'apply';
  packages: string[];
  disabledPackagesBefore: string[];
  results?: ExecutionResult[];
}

const STORAGE_KEY = 'ai_phone_debloater_snapshots_v1';

export function getLocalSnapshots(): DebloatSnapshot[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveLocalSnapshot(snapshot: DebloatSnapshot): void {
  if (typeof window === 'undefined') return;
  try {
    const current = getLocalSnapshots();
    const updated = [snapshot, ...current.filter((s) => s.id !== snapshot.id)].slice(0, 50);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  } catch {
    // Ignore storage quota errors
  }
}

export function deleteLocalSnapshot(id: string): void {
  if (typeof window === 'undefined') return;
  try {
    const current = getLocalSnapshots();
    const updated = current.filter((s) => s.id !== id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  } catch {
    // Ignore
  }
}

export function exportSnapshotFile(snapshot: DebloatSnapshot): void {
  if (typeof window === 'undefined') return;
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `snapshot_${snapshot.model.replace(/[^a-zA-Z0-9_-]/g, '_')}_${snapshot.timestamp}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
