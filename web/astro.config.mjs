import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

function getVersion() {
  const candidates = [
    new URL('../VERSION', import.meta.url),
    new URL('./VERSION', import.meta.url),
    path.resolve(process.cwd(), 'VERSION'),
    path.resolve(process.cwd(), '..', 'VERSION')
  ];

  for (const candidate of candidates) {
    try {
      const filePath = candidate instanceof URL ? fileURLToPath(candidate) : candidate;
      if (existsSync(filePath)) {
        const v = readFileSync(filePath, 'utf8').trim();
        if (v) return v;
      }
    } catch {}
  }

  try {
    const pkgPath = fileURLToPath(new URL('./package.json', import.meta.url));
    if (existsSync(pkgPath)) {
      const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
      if (pkg.version) return pkg.version;
    }
  } catch {}

  return '1.0.0';
}

const localVersion = getVersion();

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