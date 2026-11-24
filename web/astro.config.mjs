import { defineConfig, fontProviders } from 'astro/config';
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

// Sitemap <lastmod> for the blog. The config cannot import the content collection, so read the
// `updatedDate` line of each post's frontmatter (src/content/blog/<slug>.md) directly.
// Returns slug -> ISO date-time; the key "" holds the newest date, used for /blog itself.
function blogLastmod() {
  const dir = fileURLToPath(new URL('./src/content/blog', import.meta.url));
  const dates = new Map();
  if (!existsSync(dir)) return dates;
  for (const file of readdirSync(dir)) {
    if (!file.endsWith('.md')) continue;
    const source = readFileSync(path.join(dir, file), 'utf8');
    const match = source.match(/^updatedDate:\s*["']?(\d{4}-\d{2}-\d{2})/m);
    if (!match || /^draft:\s*true\b/m.test(source)) continue;
    const iso = `${match[1]}T00:00:00.000Z`;
    dates.set(file.slice(0, -'.md'.length), iso);
    if (!dates.has('') || iso > dates.get('')) dates.set('', iso);
  }
  return dates;
}

const blogDates = blogLastmod();

export default defineConfig({
  site: 'https://debloater.rovoxia.com',
  integrations: [
    sitemap({
      serialize(item) {
        const match = new URL(item.url).pathname.match(/^\/blog(?:\/([^/]+))?\/?$/);
        const lastmod = match ? blogDates.get(match[1] ?? '') : undefined;
        return lastmod ? { ...item, lastmod } : item;
      }
    })
  ],
  // Emit /app as app.html, not app/index.html. With `trailingSlash: 'never'` every canonical,
  // sitemap entry and internal link is slash-less; static hosts serve app.html at /app directly,
  // where app/index.html made /app a 308 redirect to /app/. Side effect: during the build
  // Astro.url.pathname ends in ".html", so use currentPath() from src/lib/seo.ts instead.
  build: { format: 'file' },
  // Whitespace in .astro templates follows HTML, not JSX. Astro 7 defaults to 'jsx', which drops
  // the line break between text and an inline element or {expression} on the next source line
  // ("built.See all", "makes352"). With `true` a line break there is one space, as in any HTML
  // file; the output is still minified. The cost is about 1% more HTML after gzip.
  // The other side of the same rule: punctuation that must touch an inline element has to be on
  // the same line as its closing tag (`</code>.`), or it renders with a space before it.
  compressHTML: true,
  // Self-hosted fonts (Astro fonts API). The woff2 files come from the two @fontsource-variable
  // packages, so the build needs no network; Astro copies them to /_astro/fonts/, writes the
  // @font-face CSS with metric-matched fallbacks and adds that CSS to the CSP by hash.
  // Emitted by src/components/Fonts.astro; mapped to --font-sans / --font-mono in global.css.
  fonts: [
    {
      provider: fontProviders.local(),
      name: 'Inter',
      cssVariable: '--font-inter',
      fallbacks: ['ui-sans-serif', 'system-ui', 'sans-serif'],
      options: {
        variants: [
          {
            weight: '100 900',
            style: 'normal',
            display: 'swap',
            src: ['@fontsource-variable/inter/files/inter-latin-wght-normal.woff2']
          }
        ]
      }
    },
    {
      provider: fontProviders.local(),
      name: 'JetBrains Mono',
      cssVariable: '--font-jetbrains-mono',
      fallbacks: ['ui-monospace', 'monospace'],
      options: {
        variants: [
          {
            weight: '100 800',
            style: 'normal',
            display: 'swap',
            src: ['@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2']
          }
        ]
      }
    }
  ],
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
        "font-src 'self'",
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
        resources: ["'self'"]
      }
    }
  },
  // The blog posts are Markdown (src/content/blog). Astro's default highlighter (Shiki) writes
  // inline styles, which the CSP blocks, so code blocks are left as plain <pre><code> and styled
  // by .prose in global.css. Astro also warns about that pairing on every build unless it is off.
  markdown: { syntaxHighlight: false },
  vite: {
    plugins: [tailwindcss()],
    define: {
      '__SITE_VERSION__': JSON.stringify(localVersion)
    }
  },
  trailingSlash: 'never'
});
