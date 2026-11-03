import type { APIRoute } from 'astro';

export const GET: APIRoute = async () => {
  const robots = `User-agent: *
Allow: /

Sitemap: https://debloater.rovoxia.com/sitemap.xml
Sitemap: https://debloater.rovoxia.com/sitemap-index.xml
Sitemap: https://debloater.rovoxia.com/sitemap-0.xml
`;

  return new Response(robots, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
