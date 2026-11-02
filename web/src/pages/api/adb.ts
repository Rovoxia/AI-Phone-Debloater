import type { APIRoute } from 'astro';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs';
import path from 'node:path';

const execFileAsync = promisify(execFile);

// Packages that must never be uninstalled/disabled by the webapp, even if the UI
// allows it. Defense-in-depth on top of the UI-side tier filtering.
const CRITICAL_BLOCKLIST = new Set([
  'com.android.systemui',
  'com.android.server.telecom',
  'com.android.providers.telephony',
  'android.security.keystore',
  'com.android.server.telephony.Radio',
  'com.android.providers.settings',
  'com.android.bluetooth',
  'android.hardware.bluetooth',
  'com.android.wifi',
  'android.hardware.wifi',
  'android.hardware.usb',
]);

function getAdbPath() {
  const localAdb = path.join(process.cwd(), 'platform-tools', process.platform === 'win32' ? 'adb.exe' : 'adb');
  if (fs.existsSync(localAdb)) return localAdb;
  return 'adb';
}

function adbArgs(serial?: string, extra: string[] = []): string[] {
  const args: string[] = [getAdbPath()];
  if (serial) args.push('-s', serial);
  args.push(...extra);
  return args;
}

function runAdb(args: string[]) {
  return execFileAsync(args[0], args.slice(1));
}

function parseDevices(output: string) {
  return output
    .split('\n')
    .filter((l) => l.trim())
    .slice(1) // skip "List of devices attached*"
    .map((l) => l.split(/\s+/))
    .filter((parts) => parts.length >= 2 && parts[1] === 'device')
    .map((parts) => ({ serial: parts[0], state: parts[1] }));
}

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export const GET: APIRoute = async ({ url }) => {
  const action = url.searchParams.get('action');
  const serial = url.searchParams.get('serial') || undefined;
  const adb = getAdbPath();

  try {
    if (action === 'devices') {
      const { stdout } = await runAdb([adb, 'devices']);
      return json({ devices: parseDevices(stdout) });
    }

    if (action === 'packages') {
      const { stdout } = await runAdb(adbArgs(serial, ['shell', 'pm', 'list', 'packages', '-u', '--user', '0']));
      const packages = stdout
        .split('\n')
        .map((l) => l.trim().replace(/^package:/, ''))
        .filter(Boolean);
      return json({ packages });
    }

    if (action === 'shell') {
      const cmd = (url.searchParams.get('cmd') || '').trim();
      if (!cmd) return json({ success: false, error: 'cmd required' }, 400);
      const { stdout, stderr } = await runAdb([adb, 'shell', cmd]);
      return json({ success: true, stdout, stderr });
    }

    return json({ success: false, error: 'Invalid action' }, 400);
  } catch (err: any) {
    return json({ success: false, error: err.message }, 500);
  }
};

export const POST: APIRoute = async ({ request, url }) => {
  const adb = getAdbPath();
  const serial = url.searchParams.get('serial') || undefined;
  let body: { mode?: string; packages?: string[] };
  try {
    body = await request.json();
  } catch {
    return json({ success: false, error: 'Invalid JSON body' }, 400);
  }

  const { mode, packages } = body;
  if (!Array.isArray(packages) || packages.length === 0) {
    return json({ success: false, error: 'packages required' }, 400);
  }
  if (mode !== 'dry-run' && mode !== 'apply') {
    return json({ success: false, error: 'invalid mode' }, 400);
  }

  // Safety: never touch critical packages, never force, always keep data (-k).
  const blocked = packages.filter((p) => CRITICAL_BLOCKLIST.has(p));
  if (blocked.length > 0) {
    return json({ success: false, error: `Blocked critical package(s): ${blocked.join(', ')}` }, 400);
  }

  const results: string[] = [];
  for (const pkg of packages) {
    try {
      if (mode === 'apply') {
        const { stdout } = await runAdb(adbArgs(serial, ['shell', 'pm', 'uninstall', '-k', '--user', '0', pkg]));
        results.push(`${pkg}: ${stdout.trim() || 'ok'}`);
      } else {
        results.push(`[dry-run] would run: adb ${serial ? `-s ${serial} ` : ''}shell pm uninstall -k --user 0 ${pkg}`);
      }
    } catch (e: any) {
      results.push(`${pkg}: ERROR ${e.message}`);
    }
  }

  return json({ success: true, output: results.join('\n') });
};
