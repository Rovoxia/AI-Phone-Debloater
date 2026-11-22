/**
 * WebADB & Local Bridge Client for AI-Phone-Debloater WebApp Workspace
 * ====================================================================
 * Dual-Mode Android ADB Connector:
 * 1. WebAdbClient: Direct in-browser WebUSB client via @yume-chan/adb.
 * 2. LocalBridgeClient: HTTP client connecting to local bridge_server.py (127.0.0.1:53123).
 */

import { Adb, AdbDaemonTransport } from '@yume-chan/adb';
import { AdbDaemonWebUsbDevice, AdbDaemonWebUsbDeviceManager } from '@yume-chan/adb-daemon-webusb';
import AdbWebCredentialStore from '@yume-chan/adb-credential-web';
import rulesData from '../data/rules-dataset.json';

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
 * Inviolable Tier 4 core OS packages, derived from the generated dataset
 * (cli/rules/critical-do-not-touch.json) so it cannot drift from the CLI's list.
 */
export const CRITICAL_PACKAGES: Set<string> = new Set(
  rulesData.rules.filter((rule) => rule.tier === 4).map((rule) => rule.package)
);

interface ShellResult {
  output: string;
  /** null when the device lacks the shell protocol (Android < 7) and reports no exit code. */
  exitCode: number | null;
}

/**
 * Same rule as the bridge's _pm_succeeded: the exit code decides, then pm's own failure text.
 * Without an exit code, empty output is a failure because pm always prints on success.
 */
function pmSucceeded(res: ShellResult, pkg: string): boolean {
  if (res.exitCode === null ? res.output === '' : res.exitCode !== 0) return false;
  return !/fail|error|exception|unknown package|not installed for/i.test(res.output.replaceAll(pkg, ''));
}

/**
 * Direct in-browser WebUSB ADB Client (Chrome, Edge, Brave, Opera)
 */
export class WebAdbClient {
  private adb: Adb | null = null;
  private currentDevice: DeviceInfo | null = null;

  /** Called when the connection is lost without disconnect() being called (cable unplugged). */
  public onDisconnect: (() => void) | null = null;

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

    let transport: AdbDaemonTransport;
    try {
      const connection = await usbDevice.connect();
      transport = await AdbDaemonTransport.authenticate({
        serial: usbDevice.serial,
        connection,
        credentialStore: new AdbWebCredentialStore(),
      });
    } catch (err) {
      // Release the interface so the next attempt, or desktop adb, can claim it.
      await usbDevice.raw.close().catch(() => {});
      if (err instanceof AdbDaemonWebUsbDevice.DeviceBusyError) {
        throw new Error(
          'The phone is in use by another program, usually the adb server on this computer. Run `adb kill-server` and try again, or connect through the Local Bridge instead.'
        );
      }
      throw err;
    }

    const adb = new Adb(transport);
    this.adb = adb;
    // Settles on unplug as well as on close(). disconnect() clears this.adb first,
    // so only an unexpected loss reaches onDisconnect.
    const lost = () => {
      if (this.adb !== adb) return;
      this.adb = null;
      this.currentDevice = null;
      this.onDisconnect?.();
    };
    adb.disconnected.then(lost, lost);

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
    const adb = this.adb;
    this.adb = null;
    this.currentDevice = null;
    try {
      await adb?.close();
    } catch {
      // Ignore close errors
    }
  }

  public async getProp(key: string): Promise<string> {
    if (!this.adb) throw new Error('Not connected');
    return (await this.adb.getProp(key)).trim();
  }

  private async run(command: string): Promise<ShellResult> {
    if (!this.adb) throw new Error('Not connected');

    const shell = this.adb.subprocess.shellProtocol;
    if (shell) {
      const res = await shell.spawnWaitText(command);
      return { output: (res.stdout || res.stderr || '').trim(), exitCode: res.exitCode };
    }
    return {
      output: (await this.adb.subprocess.noneProtocol.spawnWaitText(command)).trim(),
      exitCode: null,
    };
  }

  public async runShell(command: string): Promise<string> {
    return (await this.run(command)).output;
  }

  private async pmList(command: string): Promise<string[]> {
    const output = await this.runShell(command);
    return output
      .split('\n')
      .map((l) => l.trim().replace(/^package:/, ''))
      .filter((pkg) => pkg.length > 0 && /^[a-zA-Z0-9._]+$/.test(pkg));
  }

  /** Every package known for user 0, including ones uninstalled for that user (-u). */
  public listPackages(): Promise<string[]> {
    return this.pmList('pm list packages -u --user 0');
  }

  /** Packages currently installed for user 0. Anything in listPackages() but not here is uninstalled. */
  public listInstalledPackages(): Promise<string[]> {
    return this.pmList('pm list packages --user 0').catch(() => []);
  }

  public listDisabledPackages(): Promise<string[]> {
    return this.pmList('pm list packages -d --user 0').catch(() => []);
  }

  public async execute(
    action: 'disable' | 'uninstall' | 'enable',
    pkg: string
  ): Promise<ExecutionResult> {
    if ((action === 'disable' || action === 'uninstall') && CRITICAL_PACKAGES.has(pkg)) {
      return {
        package: pkg,
        status: 'skipped_protected',
        output: `BLOCKED: Inviolable Tier 4 critical package (${pkg}). Protection invariant enforced.`,
      };
    }

    try {
      if (action === 'enable') {
        // Same order as the CLI's restore_package: put the package back for user 0, then
        // enable it. `pm enable` alone does not bring back a package uninstalled for the user.
        const reinstall = await this.run(`cmd package install-existing --user 0 ${pkg}`);
        const enable = await this.run(`pm enable --user 0 ${pkg}`);
        return {
          package: pkg,
          status: pmSucceeded(reinstall, pkg) && pmSucceeded(enable, pkg) ? 'success' : 'failed',
          output: `${reinstall.output}\n${enable.output}`.trim(),
        };
      }

      const res = await this.run(
        action === 'disable' ? `pm disable-user --user 0 ${pkg}` : `pm uninstall -k --user 0 ${pkg}`
      );
      return {
        package: pkg,
        status: pmSucceeded(res, pkg) ? 'success' : 'failed',
        output: res.output,
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
  private token = '';

  /** Called when the bridge answers 401. Return a token to retry the request once, or '' to give up. */
  public onTokenRequired: () => string = () => '';

  constructor(port: number = 53123) {
    this.baseUrl = `http://127.0.0.1:${port}`;
  }

  public setBaseUrl(url: string) {
    this.baseUrl = url.replace(/\/+$/, '');
  }

  public setToken(token: string) {
    this.token = token;
  }

  // Every call but /health goes through here. The token header is sent only when a token is
  // known, so a bridge that predates tokens (and does not allow the header in CORS) still works.
  private async request(path: string, init: RequestInit & { headers?: Record<string, string> } = {}): Promise<Response> {
    const send = () =>
      fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers: this.token ? { ...init.headers, 'X-Bridge-Token': this.token } : init.headers,
      });
    const sent = this.token;
    let res = await send();
    if (res.status === 401) {
      // Ask once, unless a request that failed alongside this one already got a new token.
      if (this.token === sent) this.token = this.onTokenRequired() || sent;
      if (this.token !== sent) res = await send();
    }
    return res;
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
    const res = await this.request('/devices', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    if (res.status === 401) {
      throw new Error('The bridge needs its session token. Copy the URL the bridge printed in its terminal and open it, or connect again and paste it.');
    }
    if (!res.ok) throw new Error(`Bridge returned HTTP ${res.status}`);
    const data = await res.json();
    return data.devices || [];
  }

  public async listPackages(serial: string): Promise<string[]> {
    const res = await this.request(`/packages?serial=${encodeURIComponent(serial)}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) throw new Error(`Failed to fetch packages: HTTP ${res.status}`);
    const data = await res.json();
    return data.packages || [];
  }

  private async listView(serial: string, view: 'disabled' | 'installed'): Promise<string[]> {
    const res = await this.request(
      `/packages?serial=${encodeURIComponent(serial)}&view=${view}`,
      { method: 'GET', headers: { Accept: 'application/json' } }
    );
    if (!res.ok) return [];
    const data = await res.json();
    // Ignore a bridge that does not understand `view` — it would return every package.
    if (data.view !== view || !Array.isArray(data.packages)) return [];
    return data.packages;
  }

  public listDisabledPackages(serial: string): Promise<string[]> {
    return this.listView(serial, 'disabled');
  }

  /** Packages installed for user 0. Empty when the bridge has no `installed` view. */
  public listInstalledPackages(serial: string): Promise<string[]> {
    return this.listView(serial, 'installed');
  }

  public async getDeviceProps(
    serial: string
  ): Promise<{ manufacturer?: string; model?: string; androidVersion?: string; sdkVersion?: string }> {
    try {
      const res = await this.request(`/device?serial=${encodeURIComponent(serial)}`, {
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

  /** Changes the phone. The bridge's dry-run mode is not used by the web app. */
  public async execute(
    serial: string,
    action: 'disable' | 'uninstall' | 'enable',
    packages: string[]
  ): Promise<ExecutionResult[]> {
    const res = await this.request('/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ serial, mode: 'apply', action, packages }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      throw new Error(err.error || `Execution failed with HTTP ${res.status}`);
    }
    const data = await res.json();
    return data.results || [];
  }

  public async restore(serial: string, packages: string[]): Promise<ExecutionResult[]> {
    const res = await this.request('/restore', {
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

  private async pairCall(path: 'qr' | 'status' | 'cancel'): Promise<any> {
    const res = await this.request(
      `/pair/${path}`,
      path === 'status'
        ? { method: 'GET', headers: { Accept: 'application/json' } }
        : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }
    );
    const data = await res.json().catch(() => ({}));
    if (res.status === 404) throw new Error('This bridge is too old for QR pairing. Run the one-click command again to update it.');
    if (!res.ok) throw new Error(data.error || `Bridge returned HTTP ${res.status}`);
    return data;
  }

  /**
   * Starts Wi-Fi QR pairing on the bridge. `matrix` is the QR code (rows of 0/1, no quiet zone);
   * it encodes the pairing password, so draw it and never log or store it.
   */
  public async startQrPairing(): Promise<QrPairingSession> {
    // The bridge runs one session at a time and answers 409 to a second start. Cancel first, so a
    // session this page no longer shows (after a reload, or from another tab) is replaced.
    await this.pairCall('cancel');
    const data = await this.pairCall('qr');
    if (!Array.isArray(data.matrix) || !data.matrix.every(Array.isArray)) {
      throw new Error('The bridge did not return a QR code.');
    }
    return { id: String(data.id), matrix: data.matrix, timeout: Number(data.timeout) || 120 };
  }

  public getQrPairingStatus(): Promise<QrPairingStatus> {
    return this.pairCall('status');
  }

  public async cancelQrPairing(): Promise<void> {
    await this.pairCall('cancel');
  }
}

export interface QrPairingSession {
  id: string;
  matrix: number[][];
  timeout: number;
}

export interface QrPairingStatus {
  state: 'idle' | 'waiting' | 'paired' | 'failed' | 'expired';
  id: string | null;
  serial: string | null;
  error: string | null;
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
  // Always 'apply' now. 'dry-run' is only found in snapshots stored by older versions.
  mode: 'dry-run' | 'apply';
  packages: string[];
  disabledPackagesBefore: string[];
  results?: ExecutionResult[];
}

const STORAGE_KEY = 'ai_phone_debloater_snapshots_v1';

export function getLocalSnapshots(): DebloatSnapshot[] {
  if (typeof window === 'undefined') return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed.filter((s) => s && Array.isArray(s.packages)) : [];
  } catch {
    return [];
  }
}

/** Adds the snapshot, or replaces the stored one with the same id. False when it could not be written. */
export function saveLocalSnapshot(snapshot: DebloatSnapshot): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const current = getLocalSnapshots();
    const updated = [snapshot, ...current.filter((s) => s.id !== snapshot.id)].slice(0, 50);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    return true;
  } catch {
    // Storage quota exceeded or storage blocked
    return false;
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

export function downloadFile(filename: string, content: string, type: string): void {
  if (typeof window === 'undefined') return;
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function exportSnapshotFile(snapshot: DebloatSnapshot): void {
  downloadFile(
    `snapshot_${snapshot.model.replace(/[^a-zA-Z0-9_-]/g, '_')}_${snapshot.timestamp}.json`,
    JSON.stringify(snapshot, null, 2),
    'application/json'
  );
}
