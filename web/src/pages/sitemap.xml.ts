import type { APIRoute } from 'astro';
import fs from 'node:fs';
import path from 'node:path';

export const GET: APIRoute = async () => {
  const distPath = path.resolve('dist/sitemap-0.xml');
  if (fs.existsSync(distPath)) {
    const xml = fs.readFileSync(distPath, 'utf-8');
    return new Response(xml, {
      headers: { 'Content-Type': 'application/xml; charset=utf-8' },
    });
  }

  // Fallback for dev mode before/without build
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://debloater.rovoxia.com/</loc></url>
  <url><loc>https://debloater.rovoxia.com/app</loc></url>
  <url><loc>https://debloater.rovoxia.com/oems</loc></url>
</urlset>`;

  return new Response(xml, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
};
