import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

// Astro hashes the scripts and styles it bundles, but not `<script is:inline>` blocks, which it
// emits as written. Hash those from source so the policy cannot drift from the markup.
// Only a bare `<script is:inline>` is matched: JSON-LD blocks carry a `type` and are data, which
// CSP does not gate. Browsers hash the text after newline normalisation, hence the CRLF replace.
function inlineScriptHashes() {
  const srcDir = fileURLToPath(new URL('./src', import.meta.url));
  const hashes = new Set();
  for (const entry of readdirSync(srcDir, { recursive: true })) {
    if (!entry.endsWith('.astro')) continue;
    const source = readFileSync(path.join(srcDir, entry), 'utf8').replace(/\r\n?/g, '\n');
    for (const [, body] of source.matchAll(/<script\s+is:inline\s*>([\s\S]*?)<\/script>/g)) {
      hashes.add(`sha256-${createHash('sha256').update(body).digest('base64')}`);
    }
  }
  return [...hashes];
}

function readVersion() {
  const versionJsonPath = fileURLToPath(new URL('./src/data/version.json', import.meta.url));

  const candidates = [
    new URL('../VERSION', import.meta.url),
    new URL('./VERSION', import.meta.url),
    path.resolve(process.cwd(), 'VERSION'),
    path.resolve(process.cwd(), '..', 'VERSION')
  ];

  let ver = '';
  for (const candidate of candidates) {
    try {
      const filePath = candidate instanceof URL ? fileURLToPath(candidate) : candidate;
      if (existsSync(filePath)) {
        ver = readFileSync(filePath, 'utf8').trim();
        if (ver) break;
      }
    } catch {}
  }

  // If root VERSION was not accessible, read from version.json
  if (!ver) {
    try {
      ver = JSON.parse(readFileSync(versionJsonPath, 'utf8')).version;
    } catch {}
  }

  if (!ver) ver = '1.0.0';
  return ver;
}

const localVersion = readVersion();

export default defineConfig({
  site: 'https://debloater.rovoxia.com',
  integrations: [sitemap()],
  // Content-Security-Policy. Astro writes it as a <meta http-equiv> into every built page, with a
  // hash for each script and style it emits. It is not applied by `astro dev`: check changes with
  // `npm run build && npm run preview`. Inline on* handlers and style="" attributes are blocked,
  // so use addEventListener and classes. frame-ancestors cannot be set from <meta> and is sent as
  // a header instead (public/_headers, nginx.conf).
  // Do not add `upgrade-insecure-requests`: it would rewrite the bridge URL to https and break /app.
  security: {
    csp: {
      directives: [
        "default-src 'self'",
        "img-src 'self' data:",
        "font-src 'self' https://fonts.gstatic.com",
        // The local bridge, see LocalBridgeClient in src/lib/webadb.ts. Exact origin only.
        "connect-src 'self' http://127.0.0.1:53123",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'"
      ],
      scriptDirective: {
        resources: ["'self'"],
        hashes: inlineScriptHashes()
      },
      styleDirective: {
        // Google Fonts stylesheet, loaded by index, oems, app and 404.
        resources: ["'self'", 'https://fonts.googleapis.com']
      }
    }
  },
  // The site renders no Markdown. Astro's default highlighter (Shiki) writes inline styles, which
  // the CSP blocks, and Astro warns about that pairing on every build unless it is turned off.
  markdown: { syntaxHighlight: false },
  vite: {
    plugins: [tailwindcss()],
    define: {
      '__SITE_VERSION__': JSON.stringify(localVersion)
    }
  },
  trailingSlash: 'never'
});
