import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

function syncVersion() {
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

  // If root VERSION was found, ensure version.json matches it
  if (ver) {
    try {
      const existing = existsSync(versionJsonPath)
        ? JSON.parse(readFileSync(versionJsonPath, 'utf8')).version
        : '';
      if (existing !== ver) {
        writeFileSync(versionJsonPath, JSON.stringify({ version: ver }, null, 2) + '\n', 'utf8');
      }
    } catch {}

    // Auto-sync web/package.json
    try {
      const pkgPath = fileURLToPath(new URL('./package.json', import.meta.url));
      if (existsSync(pkgPath)) {
        const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
        if (pkg.version !== ver) {
          pkg.version = ver;
          writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n', 'utf8');
        }
      }
    } catch {}

    // Auto-sync web/public/llms-full.txt
    try {
      const llmsPath = fileURLToPath(new URL('./public/llms-full.txt', import.meta.url));
      if (existsSync(llmsPath)) {
        const content = readFileSync(llmsPath, 'utf8');
        const updated = content.replace(/^Version:\s*[^\n\r]+(\r?\n)/m, `Version: ${ver} (tracked in root \`VERSION\` file)$1`);
        if (updated !== content) {
          writeFileSync(llmsPath, updated, 'utf8');
        }
      }
    } catch {}
  } else {
    // If root VERSION file was not accessible, read from version.json or package.json
    try {
      if (existsSync(versionJsonPath)) {
        ver = JSON.parse(readFileSync(versionJsonPath, 'utf8')).version;
      }
    } catch {}
  }

  if (!ver) ver = '1.0.0';
  return ver;
}

const localVersion = syncVersion();

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
