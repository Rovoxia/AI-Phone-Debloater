import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

export async function fetchRemoteVersion() {
  try {
    const res = await fetch('https://raw.githubusercontent.com/Rovoxia/AI-Phone-Debloater/refs/heads/main/VERSION');
    if (!res.ok) {
      console.warn('[build] Remote VERSION fetch failed, falling back to 1.0.0. Status:', res.status);
      return '1.0.0';
    }
    const text = await res.text();
    const v = (typeof text === 'string' ? text : text.toString()).trim();
    if (!v) return '1.0.0';
    console.log('[build] Fetched remote version:', v);
    return v;
  } catch (err) {
    console.warn('[build] VERSION fetch error, using fallback 1.0.0:', err);
    return '1.0.0';
  }
}

const remoteVersion = await fetchRemoteVersion();

export default defineConfig({
  site: 'https://debloat.rovoxia.com',
  integrations: [sitemap()],
  vite: {
    plugins: [tailwindcss()],
    define: {
      '__SITE_VERSION__': JSON.stringify(remoteVersion)
    }
  },
  trailingSlash: 'never'
});