import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import { readFileSync } from 'node:fs';

const localVersion = readFileSync(new URL('../VERSION', import.meta.url), 'utf8').trim() || '1.0.0';

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