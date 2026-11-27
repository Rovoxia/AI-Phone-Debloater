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
 * Why a bridge call failed. The first group is sent by the bridge in the `code` field of an error
 * answer (api level 2); the second group is set by this client and never sent by the bridge.
 */
export type BridgeErrorCode =
  | 'forbidden_host'
  | 'origin_not_allowed'
  | 'unsupported_media_type'
  | 'token_required'
  | 'bad_request'
  | 'not_found'
  | 'busy'
  | 'adb_not_found'
  | 'adb_timeout'
  | 'adb_failed'
  | 'pair_failed'
  | 'connect_failed'
  /** No answer, and the browser does not report that it blocked the request. */
  | 'bridge_unreachable'
  /** No answer, and the browser's permission for local apps is denied for this site. */
  | 'browser_blocked'
  /** No answer within the time limit of the request. */
  | 'request_timeout'
  /** The route does not exist on this bridge (404): it predates the feature. */
  | 'bridge_too_old'
  /** The caller's own AbortSignal ended the request. */
  | 'aborted'
  /** An error answer without a known code, as a bridge older than api level 2 sends. */
  | 'unknown';

const BRIDGE_CODES: ReadonlySet<string> = new Set([
  'forbidden_host', 'origin_not_allowed', 'unsupported_media_type', 'token_required', 'bad_request', 'not_found',
  'busy', 'adb_not_found', 'adb_timeout', 'adb_failed', 'pair_failed', 'connect_failed',
]);

/** Every failed LocalBridgeClient call throws one of these. `message` is the bridge's own `error` text when it sent one. */
export class BridgeError extends Error {
  public readonly code: BridgeErrorCode;
  /** HTTP status of the bridge's answer, 0 when there was no answer. */
  public readonly status: number;

  constructor(code: BridgeErrorCode, message: string, status = 0, options?: ErrorOptions) {
    super(message, options);
    this.name = 'BridgeError';
    this.code = code;
    this.status = status;
  }
}

/** Any thrown value as a BridgeError, so callers can read `code` without a type test. */
export function toBridgeError(err: unknown): BridgeError {
  if (err instanceof BridgeError) return err;
  return new BridgeError('unknown', err instanceof Error ? err.message : String(err), 0, { cause: err });
}

/** The browser's answer about its permission for requests to this computer. 'unknown': it cannot be asked. */
export type LoopbackPermission = PermissionState | 'unknown';

/**
 * The browser's Local Network Access permission for loopback targets, as a live status object
 * (its `change` event fires when the user answers the prompt or edits the site settings).
 * null when the browser has no such permission or cannot be asked about it.
 *
 * The current name is `loopback-network`. Chromium 142 to 144 know only the older
 * `local-network-access`, so that name is tried on exactly those versions and nowhere else: a
 * browser that does not know a permission name is expected to throw, but the older name is not
 * safe to probe blindly on every browser.
 */
export async function loopbackPermissionStatus(): Promise<PermissionStatus | null> {
  if (typeof navigator === 'undefined' || !navigator.permissions?.query) return null;
  const brands =
    (navigator as Navigator & { userAgentData?: { brands?: { brand: string; version: string }[] } }).userAgentData
      ?.brands ?? [];
  const chromium = Number(brands.find((entry) => entry.brand === 'Chromium')?.version);
  const names = chromium >= 142 && chromium <= 144 ? ['loopback-network', 'local-network-access'] : ['loopback-network'];
  for (const name of names) {
    try {
      return await navigator.permissions.query({ name: name as PermissionName });
    } catch {
      // This browser does not know the name.
    }
  }
  return null;
}

export async function queryLoopbackPermission(): Promise<LoopbackPermission> {
  return (await loopbackPermissionStatus())?.state ?? 'unknown';
}

/** What every LocalBridgeClient method accepts as its last argument. */
export interface BridgeRequestOptions {
  /** Ends the request when it aborts; the call then throws a BridgeError with code 'aborted'. */
  signal?: AbortSignal;
  /**
   * false: a 401 is thrown as 'token_required' without calling onTokenRequired. Background
   * polling uses it, so a bridge that lost its token cannot open one prompt per request.
   */
  interactive?: boolean;
}

export interface BridgeHealth {
  ok: boolean;
  version?: string;
  adbAvailable?: boolean;
  tokenRequired?: boolean;
  /** Contract level of the bridge. 1: a bridge from before `api` was reported. 0: no answer. */
  api: number;
  /** Feature names such as 'devices.wait' or 'pair.code'. Empty for an api level 1 bridge. */
  capabilities: string[];
  /** Why there was no usable answer. Only when `ok` is false. */
  error?: BridgeError;
}

export type BridgeDeviceState =
  | 'device'
  | 'unauthorized'
  | 'authorizing'
  | 'connecting'
  | 'offline'
  | 'no_permissions'
  | 'recovery'
  | 'sideload'
  | 'bootloader'
  | 'rescue'
  | 'host'
  | 'detached'
  | 'unknown';

const DEVICE_STATES: readonly BridgeDeviceState[] = [
  'device', 'unauthorized', 'authorizing', 'connecting', 'offline', 'no_permissions', 'recovery', 'sideload',
  'bootloader', 'rescue', 'host', 'detached', 'unknown',
];

export type BridgeTransport = 'usb' | 'wifi' | 'emulator';

/** One line of `adb devices -l` as the bridge reports it. Only state 'device' is usable. */
export interface BridgeDevice {
  /** Exactly what `adb -s` accepts. It may contain spaces. */
  serial: string;
  state: BridgeDeviceState;
  /** The state text adb printed. */
  rawState: string;
  /** The rest of adb's "no permissions" sentence, otherwise ''. */
  detail: string;
  /** '' when adb does not print it, which is always the case for unauthorized and offline devices. */
  model: string;
  product: string;
  device: string;
  transportId: string;
  transport: BridgeTransport;
}

export interface DeviceList {
  devices: BridgeDevice[];
  /** Increases whenever the list changes. null from a bridge older than api level 2. */
  revision: number | null;
  /** New for every bridge process. null from a bridge older than api level 2. */
  bootId: string | null;
}

export interface DeviceListOptions extends BridgeRequestOptions {
  /** With `boot` and `wait`: the bridge holds the request until the list differs from this revision. */
  since?: number;
  boot?: string;
  /** Seconds the bridge may hold the request, 0 to 25. */
  wait?: number;
}

export interface MdnsService {
  name: string;
  type: string;
  kind: 'connect' | 'pairing' | 'legacy';
  host: string;
  port: number;
}

export interface MdnsResult {
  /** false: adb reports no running mDNS daemon, so nothing can be discovered. */
  available: boolean;
  services: MdnsService[];
}

export interface PairResult {
  paired: boolean;
  guid: string | null;
  /** true: the phone is also connected and `serial` names it. */
  connected: boolean;
  serial: string | null;
  /** true: paired, but the connect port is unknown; ask for it and call connect(). */
  needsConnectPort: boolean;
  host: string | null;
}

export interface ConnectResult {
  connected: boolean;
  serial: string;
  /** true: adb was already connected to this address. */
  already: boolean;
}

/** How adb reaches a device, from the shape of its serial. The same rule as the bridge's `transport` field. */
export function transportOfSerial(serial: string): BridgeTransport {
  if (serial.startsWith('emulator-')) return 'emulator';
  const overNetwork =
    /^(\d{1,3}(\.\d{1,3}){3}|\[[0-9a-fA-F:.]+\]):\d+$/.test(serial) || /_adb(-tls-connect)?\._tcp/.test(serial);
  return overNetwork ? 'wifi' : 'usb';
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function toDevice(raw: any): BridgeDevice | null {
  const serial = text(raw?.serial);
  // A bridge older than api level 2 can turn an adb daemon banner line into an entry named "*".
  if (!serial || serial === '*') return null;
  // The same older bridge reports adb's second word, so "no permissions" arrives as "no".
  const named = raw.state === 'no' ? 'no_permissions' : raw.state;
  const state = DEVICE_STATES.includes(named) ? (named as BridgeDeviceState) : 'unknown';
  const transport = text(raw.transport);
  return {
    serial,
    state,
    rawState: text(raw.raw_state) || (raw.state === 'no' ? 'no permissions' : text(raw.state)),
    detail: text(raw.detail),
    model: text(raw.model),
    product: text(raw.product),
    device: text(raw.device),
    transportId: text(raw.transport_id),
    transport:
      transport === 'usb' || transport === 'wifi' || transport === 'emulator' ? transport : transportOfSerial(serial),
  };
}

interface CallOptions extends BridgeRequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  timeoutMs: number;
  /** false: no token header and no 401 handling. Only /health. */
  auth?: boolean;
  /** What the route does, for the message of a 404 from a bridge that predates it. */
  feature?: string;
}

/**
 * Local ADB Bridge Client connecting to 127.0.0.1:53123. Written against the bridge contract at
 * api level 2 and still usable with an older bridge: see BridgeHealth.api.
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

  /**
   * One request with a time limit, joined with the caller's signal. Every failure to get an
   * answer becomes a BridgeError: 'aborted', 'request_timeout', 'browser_blocked' or
   * 'bridge_unreachable'. Returns the response and its JSON body ({} when it has none).
   */
  private async exchange(
    path: string,
    init: RequestInit,
    timeoutMs: number,
    external?: AbortSignal
  ): Promise<{ res: Response; data: Record<string, any> }> {
    const timeout = AbortSignal.timeout(timeoutMs);
    let signal: AbortSignal = timeout;
    let release = () => {};
    if (external) {
      if (typeof AbortSignal.any === 'function') {
        signal = AbortSignal.any([external, timeout]);
      } else {
        // Browsers from before AbortSignal.any: relay both signals by hand, and take the
        // listeners off again when the request ends so they do not pile up on `external`.
        const joined = new AbortController();
        const listeners = new AbortController();
        for (const source of [external, timeout]) {
          if (source.aborted) joined.abort(source.reason);
          else source.addEventListener('abort', () => joined.abort(source.reason), { signal: listeners.signal });
        }
        signal = joined.signal;
        release = () => listeners.abort();
      }
    }
    try {
      const res = await fetch(`${this.baseUrl}${path}`, { ...init, signal });
      const data = await res.json().catch((err: unknown) => {
        // A complete answer that is not JSON has no fields. A body that never arrived whole (a
        // signal fired, or the connection broke) is no answer at all: after a request that
        // changes the phone, reading it as "no results" would hide that the result is unknown.
        if (err instanceof SyntaxError && !signal.aborted) return {};
        throw err;
      });
      return { res, data: data && typeof data === 'object' && !Array.isArray(data) ? data : {} };
    } catch (err) {
      if (external?.aborted) throw new BridgeError('aborted', 'The request was cancelled.', 0, { cause: err });
      if (timeout.aborted) {
        const seconds = Math.round(timeoutMs / 1000);
        throw new BridgeError('request_timeout', `The local bridge did not answer within ${seconds} seconds.`, 0, { cause: err });
      }
      // fetch() gives the same TypeError for "nothing is listening" and "the browser refused to
      // send it". The permission state is the only way to tell the two apart.
      if ((await queryLoopbackPermission()) === 'denied') {
        throw new BridgeError(
          'browser_blocked',
          'This browser is blocking this page from reaching apps on this computer, so the local bridge cannot be reached.',
          0,
          { cause: err }
        );
      }
      throw new BridgeError('bridge_unreachable', 'The local bridge did not answer. Check that it is still running.', 0, { cause: err });
    } finally {
      release();
    }
  }

  // Every call goes through here. The token header is sent only when a token is known, so a
  // bridge that predates tokens (and does not allow the header in CORS) still works.
  private async call(path: string, options: CallOptions): Promise<Record<string, any>> {
    const method = options.method ?? 'GET';
    const send = () => {
      const headers: Record<string, string> =
        method === 'POST' ? { 'Content-Type': 'application/json' } : { Accept: 'application/json' };
      if (options.auth !== false && this.token) headers['X-Bridge-Token'] = this.token;
      const init: RequestInit = { method, headers };
      if (method === 'POST') init.body = JSON.stringify(options.body ?? {});
      return this.exchange(path, init, options.timeoutMs, options.signal);
    };

    const sent = this.token;
    let { res, data } = await send();
    if (res.status === 401 && options.auth !== false && options.interactive !== false) {
      // Ask once, unless a request that failed alongside this one already got a new token.
      if (this.token === sent) this.token = this.onTokenRequired() || sent;
      if (this.token !== sent) ({ res, data } = await send());
    }
    if (res.ok) return data;

    const said = text(data.error);
    if (res.status === 401) {
      throw new BridgeError(
        'token_required',
        'The bridge needs its session token. Copy the URL the bridge printed in its terminal window and paste it here.',
        401
      );
    }
    if (res.status === 404 && options.feature) {
      throw new BridgeError(
        'bridge_too_old',
        `This bridge is too old for ${options.feature}. Run the one-click command again to update it.`,
        404
      );
    }
    const code = BRIDGE_CODES.has(data.code) ? (data.code as BridgeErrorCode) : 'unknown';
    throw new BridgeError(code, said || `The bridge answered with HTTP ${res.status}.`, res.status);
  }

  /**
   * GET /health needs no token. Never throws: a failure is `ok: false` with the reason in `error`.
   * `timeoutMs` is 2 seconds unless the caller expects the browser to hold the request while it
   * asks the user for permission.
   */
  public async checkHealth(options: BridgeRequestOptions & { timeoutMs?: number } = {}): Promise<BridgeHealth> {
    try {
      const data = await this.call('/health', {
        timeoutMs: options.timeoutMs ?? 2000,
        signal: options.signal,
        auth: false,
      });
      return {
        ok: true,
        version: text(data.version) || undefined,
        adbAvailable: typeof data.adb_available === 'boolean' ? data.adb_available : undefined,
        tokenRequired: typeof data.token_required === 'boolean' ? data.token_required : undefined,
        api: Number.isInteger(data.api) ? data.api : 1,
        capabilities: Array.isArray(data.capabilities) ? data.capabilities.filter((item) => typeof item === 'string') : [],
      };
    } catch (err) {
      return { ok: false, api: 0, capabilities: [], error: toBridgeError(err) };
    }
  }

  /**
   * GET /devices. With `since`, `boot` and `wait` it is a long poll, which only a bridge with the
   * 'devices.wait' capability understands; the time limit is always longer than `wait`.
   */
  public async getDevices(options: DeviceListOptions = {}): Promise<DeviceList> {
    const wait = Math.max(0, Math.min(25, Math.floor(options.wait ?? 0)));
    const query = new URLSearchParams();
    if (options.since !== undefined) query.set('since', String(options.since));
    if (options.boot !== undefined) query.set('boot', options.boot);
    if (wait > 0) query.set('wait', String(wait));
    const suffix = query.toString();
    const data = await this.call(suffix ? `/devices?${suffix}` : '/devices', {
      // A held request takes `wait` plus up to 15 seconds of `adb devices -l`. One that is not
      // held may be the first after the bridge started, which waits for the adb server to come
      // up (bounded at 35 seconds on the bridge). Both limits stay above the bridge's own, so
      // its error text arrives instead of a client timeout.
      timeoutMs: wait > 0 ? (wait + 20) * 1000 : 50000,
      signal: options.signal,
      interactive: options.interactive,
    });
    const devices = Array.isArray(data.devices) ? data.devices : [];
    return {
      devices: devices.map(toDevice).filter((entry): entry is BridgeDevice => entry !== null),
      revision: Number.isInteger(data.revision) ? data.revision : null,
      bootId: text(data.boot_id) || null,
    };
  }

  /** POST /reconnect: `adb reconnect offline`, which resets offline and unauthorized transports. */
  public async reconnectOffline(options: BridgeRequestOptions = {}): Promise<void> {
    await this.call('/reconnect', { method: 'POST', timeoutMs: 20000, feature: 'resetting a connection', ...options });
  }

  /**
   * GET /mdns: the wireless debugging services adb sees on the network. The bridge runs
   * `adb mdns check` (up to 10 seconds) and `adb mdns services` (up to 15), so the limit is 30.
   * A timeout here says nothing about the bridge itself: only discovery did not answer.
   */
  public async getMdnsServices(options: BridgeRequestOptions = {}): Promise<MdnsResult> {
    const data = await this.call('/mdns', { timeoutMs: 30000, feature: 'finding phones on the network', ...options });
    const services = Array.isArray(data.services) ? data.services : [];
    return {
      available: data.available === true,
      services: services
        .filter(
          (item: any) =>
            item && typeof item.host === 'string' && Number.isInteger(item.port) &&
            (item.kind === 'connect' || item.kind === 'pairing' || item.kind === 'legacy')
        )
        .map((item: any) => ({ name: text(item.name), type: text(item.type), kind: item.kind, host: item.host, port: item.port })),
    };
  }

  /**
   * POST /pair/code: `adb pair host:port code`. `code` is the six digits the phone shows; it is a
   * secret for as long as the phone's pairing dialog is open, so never log or store it.
   */
  public async pairWithCode(host: string, port: number, code: string, options: BridgeRequestOptions = {}): Promise<PairResult> {
    const data = await this.call('/pair/code', {
      method: 'POST',
      body: { host, port, code },
      // After pairing the bridge also waits for the phone to connect.
      timeoutMs: 90000,
      feature: 'pairing with a code',
      ...options,
    });
    return {
      paired: data.paired === true,
      guid: text(data.guid) || null,
      connected: data.connected === true,
      serial: text(data.serial) || null,
      needsConnectPort: data.needs_connect_port === true,
      host: text(data.host) || null,
    };
  }

  /** POST /connect: `adb connect host:port`, confirmed by the bridge through the device list. */
  public async connect(host: string, port: number, options: BridgeRequestOptions = {}): Promise<ConnectResult> {
    const data = await this.call('/connect', {
      method: 'POST',
      body: { host, port },
      timeoutMs: 45000,
      feature: 'connecting by address',
      ...options,
    });
    return { connected: data.connected === true, serial: text(data.serial) || `${host}:${port}`, already: data.already === true };
  }

  public async listPackages(serial: string, options: BridgeRequestOptions = {}): Promise<string[]> {
    const data = await this.call(`/packages?serial=${encodeURIComponent(serial)}`, { timeoutMs: 45000, ...options });
    return Array.isArray(data.packages) ? data.packages : [];
  }

  private async listView(serial: string, view: 'disabled' | 'installed', options: BridgeRequestOptions): Promise<string[]> {
    let data: Record<string, any>;
    try {
      data = await this.call(`/packages?serial=${encodeURIComponent(serial)}&view=${view}`, { timeoutMs: 45000, ...options });
    } catch (err) {
      // An error answer means "this view is not known": the caller treats that as no data.
      // No answer at all is a real failure.
      if (toBridgeError(err).status > 0) return [];
      throw err;
    }
    // Ignore a bridge that does not understand `view` — it would return every package.
    if (data.view !== view || !Array.isArray(data.packages)) return [];
    return data.packages;
  }

  public listDisabledPackages(serial: string, options: BridgeRequestOptions = {}): Promise<string[]> {
    return this.listView(serial, 'disabled', options);
  }

  /** Packages installed for user 0. Empty when the bridge has no `installed` view. */
  public listInstalledPackages(serial: string, options: BridgeRequestOptions = {}): Promise<string[]> {
    return this.listView(serial, 'installed', options);
  }

  /** Never throws: properties that cannot be read are left out. */
  public async getDeviceProps(
    serial: string,
    options: BridgeRequestOptions = {}
  ): Promise<{ manufacturer?: string; model?: string; androidVersion?: string; sdkVersion?: string }> {
    try {
      return await this.call(`/device?serial=${encodeURIComponent(serial)}`, { timeoutMs: 8000, ...options });
    } catch {
      return {};
    }
  }

  /**
   * Changes the phone. The bridge's dry-run mode is not used by the web app. The time limit stays
   * above the bridge's worst case: before the first package it may wait for the adb server to come
   * up and for another apply to finish, then reads a property and writes its snapshot (two adb
   * commands of 30 seconds); each package is one adb command of 30 seconds. When the limit is
   * reached all the same, the phone may or may not have been changed: the error says
   * 'request_timeout' and the caller must treat the result as unknown, not as a failure.
   */
  public async execute(
    serial: string,
    action: 'disable' | 'uninstall' | 'enable',
    packages: string[],
    options: BridgeRequestOptions = {}
  ): Promise<ExecutionResult[]> {
    const data = await this.call('/execute', {
      method: 'POST',
      body: { serial, mode: 'apply', action, packages },
      timeoutMs: 150000 + 35000 * packages.length,
      ...options,
    });
    return Array.isArray(data.results) ? data.results : [];
  }

  /** Changes the phone: up to two adb commands per package. The time limit is as for execute(). */
  public async restore(serial: string, packages: string[], options: BridgeRequestOptions = {}): Promise<ExecutionResult[]> {
    const data = await this.call('/restore', {
      method: 'POST',
      body: { serial, packages },
      timeoutMs: 150000 + 65000 * packages.length,
      ...options,
    });
    return Array.isArray(data.results) ? data.results : [];
  }

  private pairCall(path: 'qr' | 'status' | 'cancel', options: BridgeRequestOptions): Promise<Record<string, any>> {
    return this.call(`/pair/${path}`, {
      method: path === 'status' ? 'GET' : 'POST',
      timeoutMs: 15000,
      feature: 'QR pairing',
      ...options,
    });
  }

  /**
   * Starts Wi-Fi QR pairing on the bridge. `matrix` is the QR code (rows of 0/1, no quiet zone);
   * it encodes the pairing password, so draw it and never log or store it.
   */
  public async startQrPairing(options: BridgeRequestOptions = {}): Promise<QrPairingSession> {
    // The bridge runs one session at a time and answers 409 to a second start. Cancel first, so a
    // session this page no longer shows (after a reload, or from another tab) is replaced.
    await this.pairCall('cancel', options);
    const data = await this.pairCall('qr', options);
    if (!Array.isArray(data.matrix) || !data.matrix.every(Array.isArray)) {
      throw new BridgeError('unknown', 'The bridge did not return a QR code.');
    }
    return { id: String(data.id), matrix: data.matrix, timeout: Number(data.timeout) || 120 };
  }

  public async getQrPairingStatus(options: BridgeRequestOptions = {}): Promise<QrPairingStatus> {
    const data = await this.pairCall('status', options);
    const serial = text(data.serial) || null;
    return {
      state: data.state,
      id: data.id == null ? null : String(data.id),
      serial,
      error: text(data.error) || null,
      // A bridge older than api level 2 has no `connected`: there, "paired" with a serial means
      // the phone was also connected.
      connected: typeof data.connected === 'boolean' ? data.connected : data.state === 'paired' && serial !== null,
      needsConnectPort: data.needs_connect_port === true,
      host: text(data.host) || null,
    };
  }

  public async cancelQrPairing(options: BridgeRequestOptions = {}): Promise<void> {
    await this.pairCall('cancel', options);
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
  /** true: the paired phone is connected and `serial` names it. */
  connected: boolean;
  /** true: paired, but the connect port was not announced; ask for it and call connect(). */
  needsConnectPort: boolean;
  /** The phone's IPv4 address when the bridge knows it. */
  host: string | null;
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
