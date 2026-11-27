/**
 * The connection to the local bridge as a state machine, and the device monitor that runs from the
 * moment the bridge answers until stop(). The page (src/pages/app.astro) draws the snapshots this
 * emits and decides which phone to open. The only browser APIs used here are timers, the Page
 * Visibility API and the Permissions API, so everything else can be read without the page.
 *
 * Phases:
 *   idle         nothing runs. start() leaves it; stop() returns to it from anywhere.
 *   waiting      asking GET /health until the bridge answers or the wait is over.
 *   blocked      the browser denies this site access to apps on this computer. No request is sent.
 *   unreachable  the wait ended without an answer.
 *   adb_missing  the bridge answers but cannot run adb. /health is asked again every few seconds.
 *   token        the bridge answered 401. tokenProvided() tries again.
 *   ready        the monitor runs: `devices` is adb's list, `link` says whether it is current.
 */
import {
  type BridgeDevice,
  type BridgeError,
  type BridgeHealth,
  type BridgeTransport,
  type LocalBridgeClient,
  type LoopbackPermission,
  loopbackPermissionStatus,
  toBridgeError,
} from './webadb';

export type BridgePhase = 'idle' | 'waiting' | 'blocked' | 'unreachable' | 'adb_missing' | 'token' | 'ready';

export interface BridgeSnapshot {
  phase: BridgePhase;
  /** The last /health answer. null until the bridge has answered in this session. */
  health: BridgeHealth | null;
  /** adb's device list from the last answer, in adb's order. */
  devices: BridgeDevice[];
  /** true once /devices has answered since the phase became 'ready'. Until then `devices` says nothing. */
  listed: boolean;
  /** 'lost': several list requests in a row failed, so `devices` may be out of date. */
  link: 'ok' | 'lost';
  /** Why the last request failed. null after an answer. */
  error: BridgeError | null;
  /** While 'waiting': when the wait ends, in epoch milliseconds. */
  deadline: number;
  /** What the browser says about its permission for requests to this computer. */
  permission: LoopbackPermission;
}

const IDLE: BridgeSnapshot = {
  phase: 'idle',
  health: null,
  devices: [],
  listed: false,
  link: 'ok',
  error: null,
  deadline: 0,
  permission: 'unknown',
};

/** A normal /health request. The bridge answers it by running `adb version`. */
const HEALTH_TIMEOUT_MS = 2000;
/**
 * A /health request the browser may hold while it asks the user for permission to reach apps on
 * this computer. Cutting that request short would dismiss the question, so it gets a minute.
 */
const PROMPT_TIMEOUT_MS = 60_000;
/** Pause after each failed /health request while waiting for the bridge to start. */
const HEALTH_PAUSE_MS = [500, 1000, 1500, 2000, 3000];
/** How long retry() and tokenProvided() wait for /health. The page chooses the wait for start(). */
const RETRY_WAIT_MS = 20_000;
const ADB_RECHECK_MS = 3000;
/** Seconds the bridge may hold GET /devices when it has the 'devices.wait' capability. */
const LONG_POLL_SECONDS = 25;
/** Interval of plain polling, for a bridge without 'devices.wait'. */
const SHORT_POLL_MS = 2000;
/** This many failed list requests in a row and the link counts as lost. */
const LOST_AFTER = 3;
const MAX_BACKOFF_MS = 10_000;

/** Resolves after `ms`, or at once when `signal` aborts. Never rejects. */
function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const done = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', done);
      resolve();
    };
    const timer = setTimeout(done, ms);
    signal.addEventListener('abort', done);
  });
}

/** Resolves when the tab is visible, or at once when `signal` aborts. Never rejects. */
function whenVisible(signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (document.visibilityState !== 'hidden' || signal.aborted) {
      resolve();
      return;
    }
    const done = () => {
      document.removeEventListener('visibilitychange', check);
      signal.removeEventListener('abort', done);
      resolve();
    };
    const check = () => {
      if (document.visibilityState !== 'hidden') done();
    };
    document.addEventListener('visibilitychange', check);
    signal.addEventListener('abort', done);
  });
}

/** 1, 2, 4, 8, then 10 seconds, each cut by up to half at random so tabs do not retry in step. */
function backoff(failures: number): number {
  const ceiling = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** (failures - 1));
  return ceiling * (0.5 + Math.random() * 0.5);
}

export class BridgeSession {
  private readonly client: LocalBridgeClient;
  private readonly onChange: (snapshot: BridgeSnapshot) => void;
  private state: BridgeSnapshot = IDLE;
  /** Goes up whenever the running loops must end. Each loop keeps the value it started with. */
  private run = 0;
  /** Aborted by stop(). The page hands `signal` to its own read requests. */
  private session = new AbortController();
  /** The monitor's request or pause in flight. Aborting it makes the monitor ask again at once. */
  private tick: AbortController | null = null;
  /** The next list request must not be a long poll. */
  private fresh = true;
  private capabilities = new Set<string>();
  private permission: PermissionStatus | null = null;
  private waitMs = RETRY_WAIT_MS;

  constructor(client: LocalBridgeClient, onChange: (snapshot: BridgeSnapshot) => void) {
    this.client = client;
    this.onChange = onChange;
    // A hidden tab does not poll: end the request in flight. The monitor then waits in whenVisible().
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') this.tick?.abort();
    });
  }

  public get snapshot(): BridgeSnapshot {
    return this.state;
  }

  public get active(): boolean {
    return this.state.phase !== 'idle';
  }

  /** Aborts when the session stops. A new one is made by every start(). */
  public get signal(): AbortSignal {
    return this.session.signal;
  }

  /** Whether the bridge reported this capability in /health. Always false for an api level 1 bridge. */
  public has(capability: string): boolean {
    return this.capabilities.has(capability);
  }

  /**
   * Starts over: asks /health for `waitMs`, then runs the monitor. With `interactive` (a start the
   * user asked for) the first list request may ask for the token through
   * LocalBridgeClient.onTokenRequired; no later request does, and none does without it.
   */
  public start(waitMs: number, interactive = true): void {
    this.end();
    this.session = new AbortController();
    this.waitMs = waitMs;
    this.set({ ...IDLE, phase: 'waiting', deadline: Date.now() + waitMs });
    void this.waitForBridge(this.run, interactive);
  }

  /** Ends the monitor and every request the session started. */
  public stop(): void {
    this.end();
    this.set({ ...IDLE });
  }

  /**
   * From 'unreachable' or 'blocked': look for the bridge again. `interactive` as for start():
   * true for the user's "Try again", false when the session retries by itself.
   */
  public retry(interactive = true): void {
    this.start(Math.min(this.waitMs, RETRY_WAIT_MS), interactive);
  }

  /** From 'token', after the page stored a new token: ask the bridge again, without a prompt. */
  public tokenProvided(): void {
    if (this.state.phase !== 'token') return;
    this.run += 1;
    this.tick?.abort();
    this.set({ phase: 'waiting', deadline: Date.now() + RETRY_WAIT_MS, error: null, listed: false });
    void this.waitForBridge(this.run, false);
  }

  /** Asks for the device list now instead of waiting for the long poll or the next interval. */
  public refresh(): void {
    this.fresh = true;
    this.tick?.abort();
  }

  private end(): void {
    this.run += 1;
    this.session.abort();
    this.tick?.abort();
    this.tick = null;
    if (this.permission) this.permission.onchange = null;
    this.permission = null;
    this.capabilities = new Set();
  }

  private set(patch: Partial<BridgeSnapshot>): void {
    const next = { ...this.state, ...patch };
    const keys = Object.keys(patch) as (keyof BridgeSnapshot)[];
    const changed = keys.some((key) =>
      key === 'devices' ? JSON.stringify(next.devices) !== JSON.stringify(this.state.devices) : next[key] !== this.state[key]
    );
    if (!changed) return;
    this.state = next;
    this.onChange(next);
  }

  /**
   * The permission as a live object, when the browser has one. Its change event is the user
   * answering the browser's question or editing the site settings, so the page moves on by itself.
   */
  private async watchPermission(run: number): Promise<PermissionStatus | null> {
    const status = await loopbackPermissionStatus();
    if (!status || this.run !== run) return status;
    if (this.permission) this.permission.onchange = null;
    this.permission = status;
    status.onchange = () => {
      if (this.run !== run) return;
      const phase = this.state.phase;
      this.set({ permission: status.state });
      if ((phase === 'blocked' && status.state !== 'denied') || (phase === 'unreachable' && status.state === 'granted')) {
        // Nobody clicked anything on this page, so a missing token must not open a prompt.
        this.retry(false);
      }
    };
    return status;
  }

  private async waitForBridge(run: number, interactive: boolean): Promise<void> {
    const signal = this.session.signal;
    const status = await this.watchPermission(run);
    if (this.run !== run) return;
    const permission = (): LoopbackPermission => status?.state ?? 'unknown';
    let held = 0;
    for (let attempt = 0; ; attempt += 1) {
      // Denied: the browser would fail the request without sending it.
      if (permission() === 'denied') {
        this.set({ phase: 'blocked', permission: 'denied' });
        return;
      }
      // Unless the permission is already granted, the browser may hold this request while it
      // asks the user. That can happen on any attempt, not only the first: some browsers ask
      // only once something answers on the port.
      const mayAsk = permission() !== 'granted';
      this.set({ permission: permission() });
      const started = Date.now();
      const health = await this.client.checkHealth({ signal, timeoutMs: mayAsk ? PROMPT_TIMEOUT_MS : HEALTH_TIMEOUT_MS });
      if (this.run !== run) return;
      if (health.ok) {
        this.enter(run, health, interactive);
        return;
      }
      // A request that outlasted a normal one was held by the browser for the user's answer. That
      // time is not the bridge being slow, so the wait is extended by it.
      const extra = Math.max(0, Date.now() - started - HEALTH_TIMEOUT_MS);
      const deadline = this.state.deadline + extra;
      const error = health.error ?? null;
      if (permission() === 'denied' || error?.code === 'browser_blocked') {
        this.set({ phase: 'blocked', permission: 'denied', error, deadline });
        return;
      }
      // Two requests in a row held for the whole minute: nobody is answering the question.
      held = error?.code === 'request_timeout' && mayAsk ? held + 1 : 0;
      if (Date.now() >= deadline || held >= 2) {
        this.set({ phase: 'unreachable', permission: permission(), error, deadline });
        return;
      }
      this.set({ permission: permission(), deadline });
      await sleep(HEALTH_PAUSE_MS[Math.min(attempt, HEALTH_PAUSE_MS.length - 1)], signal);
      if (this.run !== run) return;
    }
  }

  /** The bridge answered /health. */
  private enter(run: number, health: BridgeHealth, interactive: boolean): void {
    this.capabilities = new Set(health.capabilities);
    if (health.adbAvailable === false) {
      this.set({ phase: 'adb_missing', health, error: null });
      void this.waitForAdb(run);
      return;
    }
    this.set({ phase: 'ready', health, link: 'ok', error: null, listed: false });
    void this.monitor(run, interactive);
  }

  private async waitForAdb(run: number): Promise<void> {
    const signal = this.session.signal;
    let failures = 0;
    while (this.run === run) {
      await sleep(ADB_RECHECK_MS, signal);
      await whenVisible(signal);
      if (this.run !== run) return;
      const health = await this.client.checkHealth({ signal });
      if (this.run !== run) return;
      if (!health.ok) {
        failures += 1;
        if (failures < LOST_AFTER) continue;
        this.set({ phase: 'unreachable', error: health.error ?? null });
        return;
      }
      failures = 0;
      if (health.adbAvailable !== false) {
        this.enter(run, health, false);
        return;
      }
    }
  }

  /** After a bridge restart the new process may be another version: read its capabilities again. */
  private async readHealth(run: number): Promise<void> {
    const health = await this.client.checkHealth({ signal: this.session.signal });
    if (this.run !== run || !health.ok) return;
    this.capabilities = new Set(health.capabilities);
    this.set({ health });
  }

  /**
   * One request in flight at a time, for as long as the phase is 'ready'. A long poll where the
   * bridge supports it, otherwise a request every two seconds. Nothing is sent while the tab is
   * hidden, and the first request after it shows again is immediate.
   */
  private async monitor(run: number, interactive: boolean): Promise<void> {
    let since: number | null = null;
    let boot: string | null = null;
    let failures = 0;
    let first = interactive;
    this.fresh = true;
    while (this.run === run) {
      await whenVisible(this.session.signal);
      if (this.run !== run) return;
      const tick = new AbortController();
      this.tick = tick;
      const canWait = this.capabilities.has('devices.wait') && since !== null && boot !== null;
      const longPoll = canWait && !this.fresh;
      this.fresh = false;
      const started = Date.now();
      try {
        const list = await this.client.getDevices({
          signal: tick.signal,
          interactive: first,
          ...(longPoll ? { since: since as number, boot: boot as string, wait: LONG_POLL_SECONDS } : {}),
        });
        if (this.run !== run) return;
        first = false;
        failures = 0;
        // A new boot id is a new bridge process. It answered with our token, so only its
        // capabilities need reading again; a 401 would have ended in the catch below.
        const restarted = boot !== null && list.bootId !== null && list.bootId !== boot;
        const news = !longPoll || restarted || list.revision !== since;
        since = list.revision;
        boot = list.bootId;
        this.set({ devices: list.devices, listed: true, link: 'ok', error: null });
        if (restarted) await this.readHealth(run);
        if (this.run !== run) return;
        if (!this.capabilities.has('devices.wait') || since === null || boot === null) {
          await sleep(SHORT_POLL_MS, tick.signal);
        } else if (longPoll && Date.now() - started < 1000) {
          // The bridge is meant to hold a long poll. One answered at once must not become a busy loop.
          await sleep(news ? 300 : 1000, tick.signal);
        }
      } catch (err) {
        if (this.run !== run) return;
        first = false;
        const error = toBridgeError(err);
        this.fresh = true;
        // refresh() or a hidden tab ended the request: go round again.
        if (error.code === 'aborted') continue;
        if (error.code === 'token_required') {
          this.set({ phase: 'token', error });
          return;
        }
        if (error.code === 'adb_not_found') {
          this.set({ phase: 'adb_missing', error });
          void this.waitForAdb(run);
          return;
        }
        failures += 1;
        this.set({ error, link: failures >= LOST_AFTER ? 'lost' : this.state.link });
        await sleep(backoff(failures), tick.signal);
      }
    }
  }
}

/* ---- What the page shows for a device ------------------------------------------------------ */

export const TRANSPORT_LABEL: Record<BridgeTransport, string> = { usb: 'USB', wifi: 'Wi-Fi', emulator: 'Emulator' };

/**
 * A serial short enough to read. Over Wi-Fi adb may name a phone by its mDNS service, such as
 * "adb-R58M12ABCDE-a1b2c3._adb-tls-connect._tcp": the service type is dropped, and anything still
 * long is cut in the middle. Only for display; requests always carry the whole serial.
 */
export function shortSerial(serial: string): string {
  const name = serial.replace(/\._adb(-tls-connect)?\._tcp\.?/, '');
  return name.length > 28 ? `${name.slice(0, 16)}…${name.slice(-8)}` : name;
}

/**
 * The phone's own serial inside adb's mDNS name "adb-<serial>-<suffix>._adb-tls-connect._tcp",
 * '' for a serial of any other shape.
 */
export function serialInMdnsName(serial: string): string {
  return /^adb-(.+)-[^-.]+\._adb-tls-connect\._tcp\.?( \(\d+\))?$/.exec(serial)?.[1] ?? '';
}

/**
 * What to call a device in the list: the model, which adb prints with underscores for spaces, or
 * the short serial when adb has no model yet (always the case before the phone is authorized).
 */
export function deviceName(entry: Pick<BridgeDevice, 'model' | 'serial'>): string {
  return entry.model ? entry.model.replaceAll('_', ' ') : shortSerial(entry.serial);
}

/**
 * How a ready entry of the list relates to the other ready entries. adb does not merge a phone it
 * reaches over USB, by address and by mDNS name, and neither does the bridge.
 *  - 'same': proven. One entry is the mDNS name of the other's USB serial; `other` is that entry.
 *  - 'maybe': it shares its model with another ready entry, at least one of them over Wi-Fi, and
 *    nothing proves or rules out that they are one phone. Two phones of one model look like this.
 */
export interface EntryRelation {
  kind: 'same' | 'maybe';
  other: BridgeDevice | null;
}

/**
 * Proven to be one phone: one entry is over Wi-Fi under the mDNS name that carries the other
 * entry's USB serial. A shared model proves nothing: two phones of one model share it too.
 */
export function isSamePhone(a: BridgeDevice, b: BridgeDevice): boolean {
  const names = (wifi: BridgeDevice, cable: BridgeDevice) =>
    wifi.transport === 'wifi' && cable.transport === 'usb' && serialInMdnsName(wifi.serial) === cable.serial;
  return names(a, b) || names(b, a);
}

/** The relation of every ready entry that has one, by serial. See EntryRelation. */
export function relateEntries(devices: BridgeDevice[]): Map<string, EntryRelation> {
  const ready = devices.filter((entry) => entry.state === 'device');
  const relations = new Map<string, EntryRelation>();
  for (const entry of ready) {
    const twin = ready.find((other) => other !== entry && isSamePhone(entry, other));
    if (twin) relations.set(entry.serial, { kind: 'same', other: twin });
  }
  const byModel = new Map<string, BridgeDevice[]>();
  for (const entry of ready) {
    if (entry.model) byModel.set(entry.model, [...(byModel.get(entry.model) ?? []), entry]);
  }
  for (const group of byModel.values()) {
    if (group.length < 2 || !group.some((entry) => entry.transport === 'wifi')) continue;
    for (const entry of group) {
      if (!relations.has(entry.serial)) relations.set(entry.serial, { kind: 'maybe', other: null });
    }
  }
  return relations;
}

export interface DeviceAdvice {
  /** The state in words, for the badge. */
  label: string;
  /** Badge class from global.css, '' for the neutral badge. */
  badge: '' | 'badge-ok' | 'badge-warn' | 'badge-alert' | 'badge-danger' | 'badge-info';
  /** What the user has to do. '' when the device is ready. */
  help: string;
  /** Whether `adb reconnect offline` (POST /reconnect) can help in this state. */
  canReset: boolean;
}

const NOT_BOOTED: Partial<Record<BridgeDevice['state'], string>> = {
  recovery: 'Recovery mode',
  sideload: 'Sideload mode',
  bootloader: 'Bootloader',
  rescue: 'Rescue mode',
};

/**
 * `retry`: whether the page offers a Retry button with this bridge (it has the 'reconnect'
 * capability). The help never names a button that is not there.
 */
export function describeDevice(entry: BridgeDevice, retry: boolean): DeviceAdvice {
  const cable = entry.transport === 'usb';
  // What to try when the phone shows no prompt; '' when the page has nothing to suggest.
  const noPrompt = [retry ? 'Choose Retry' : '', cable ? 'unplug the cable and plug it in again' : '']
    .filter(Boolean)
    .join(', or ');
  switch (entry.state) {
    case 'device':
      return { label: 'Ready', badge: 'badge-ok', help: '', canReset: false };
    case 'unauthorized':
    case 'authorizing':
      return {
        label: entry.state === 'authorizing' ? 'Authorizing' : 'Needs your approval',
        badge: 'badge-warn',
        help:
          'Unlock the phone and tap Allow on the "Allow USB debugging?" prompt. This page continues by itself once you allow it.' +
          (noPrompt ? ` No prompt on the phone? ${noPrompt[0].toUpperCase()}${noPrompt.slice(1)}.` : ''),
        canReset: true,
      };
    case 'offline':
      return {
        label: 'Offline',
        badge: 'badge-alert',
        help:
          'adb sees this phone, but the phone does not answer. ' +
          (cable
            ? 'Unplug the cable and plug it in again, or turn USB debugging off and on'
            : 'Check that Wireless debugging is still on and that the phone is on the same Wi-Fi network') +
          (retry ? ', then choose Retry.' : '.'),
        canReset: true,
      };
    case 'no_permissions':
      return {
        label: 'No permission',
        badge: 'badge-danger',
        // adb's own reason (entry.detail) is shown and announced by the page, after this text.
        help: 'This computer does not let adb use the USB connection to the phone. On Linux, install the Android platform-tools udev rules and plug the cable in again.',
        canReset: false,
      };
    case 'connecting':
      return { label: 'Connecting', badge: 'badge-info', help: 'adb is still connecting to this phone. Wait a moment.', canReset: false };
    case 'recovery':
    case 'sideload':
    case 'bootloader':
    case 'rescue':
      return {
        label: NOT_BOOTED[entry.state] ?? 'Not booted',
        badge: 'badge-alert',
        help: 'The phone is not booted into Android. Restart it normally; it then shows up here as ready by itself.',
        canReset: false,
      };
    default:
      return {
        label: 'Not usable',
        badge: '',
        help: `adb reports the state "${entry.rawState || entry.state}", which this page cannot work with. Unplug the cable and plug it in again.`,
        canReset: false,
      };
  }
}

/**
 * The phone to open without asking, or null when the user has to choose or wait.
 *  - `want` (a phone the user chose, just paired or just connected): only that one, once it is
 *    ready. Never another phone in its place.
 *  - exactly one device listed and it is ready: that one.
 *  - otherwise the phone opened last in this tab (`remembered`), when it is ready.
 * `skip` holds serials that already failed to open; they wait for the user.
 */
export function pickDevice(
  devices: BridgeDevice[],
  want: string,
  remembered: string,
  skip: ReadonlySet<string>
): BridgeDevice | null {
  const ready = devices.filter((entry) => entry.state === 'device' && !skip.has(entry.serial));
  if (want) return ready.find((entry) => entry.serial === want) ?? null;
  if (devices.length === 1) return ready[0] ?? null;
  return ready.find((entry) => entry.serial === remembered) ?? null;
}

/* ---- Wi-Fi form values, checked the way the bridge checks them ------------------------------ */

/** An IPv4 literal that is not unspecified, multicast or broadcast; null otherwise. */
export function parseIpv4(input: string): string | null {
  const value = input.trim();
  const parts = value.split('.');
  if (parts.length !== 4) return null;
  if (!parts.every((part) => /^(0|[1-9]\d{0,2})$/.test(part) && Number(part) <= 255)) return null;
  const first = Number(parts[0]);
  if (value === '0.0.0.0' || value === '255.255.255.255' || (first >= 224 && first <= 239)) return null;
  return value;
}

/** An integer from 1 to 65535; null otherwise. */
export function parsePort(input: string): number | null {
  const value = input.trim();
  if (!/^[1-9]\d{0,4}$/.test(value)) return null;
  const port = Number(value);
  return port <= 65535 ? port : null;
}

/** Exactly six digits, spaces ignored; null otherwise. */
export function parsePairingCode(input: string): string | null {
  const value = input.replace(/\s+/g, '');
  return /^\d{6}$/.test(value) ? value : null;
}

/** "192.168.1.20:37123", the form the phone shows, split into its two fields; null for anything else. */
export function splitHostPort(input: string): { host: string; port: string } | null {
  const match = /^\s*(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})\s*$/.exec(input);
  return match ? { host: match[1], port: match[2] } : null;
}
