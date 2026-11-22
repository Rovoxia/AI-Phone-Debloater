import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

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
  vite: {
    plugins: [tailwindcss()],
    define: {
      '__SITE_VERSION__': JSON.stringify(localVersion)
    }
  },
  trailingSlash: 'never'
});
