/**
 * /rss.xml: RSS 2.0 feed of the guides, written by hand (no @astrojs/rss dependency).
 * Built once as a static file. The items come from the same collection as /blog.
 *
 * Dates: item <pubDate> is the post's `pubDate`; <lastBuildDate> is the newest `updatedDate`,
 * not the build time, so two builds of the same content give the same file.
 */
import type { APIRoute } from 'astro';
import { SITE_LANG, abs } from '../lib/seo';
import { FEED_PATH, FEED_TITLE, getPosts, latestUpdate, postPath } from '../lib/blog';

const FEED_DESCRIPTION =
  'Android debloat guides by phone brand, ADB setup and the safety tiers, from the AI Phone Debloater project.';

function escapeXml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/** RFC 822 date as RSS 2.0 requires, e.g. "Sun, 01 Nov 2026 00:00:00 GMT". */
const rfc822 = (date: Date): string => date.toUTCString();

export const GET: APIRoute = async () => {
  const posts = await getPosts();

  const items = posts
    .map((post) => {
      const url = abs(postPath(post));
      return [
        '    <item>',
        `      <title>${escapeXml(post.data.title)}</title>`,
        `      <link>${escapeXml(url)}</link>`,
        `      <guid isPermaLink="true">${escapeXml(url)}</guid>`,
        `      <pubDate>${rfc822(post.data.pubDate)}</pubDate>`,
        `      <description>${escapeXml(post.data.description)}</description>`,
        `      <category>${escapeXml(post.data.category)}</category>`,
        '    </item>',
      ].join('\n');
    })
    .join('\n');

  const xml = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
    '  <channel>',
    `    <title>${escapeXml(FEED_TITLE)}</title>`,
    `    <link>${escapeXml(abs('/blog'))}</link>`,
    `    <description>${escapeXml(FEED_DESCRIPTION)}</description>`,
    `    <language>${SITE_LANG}</language>`,
    ...(posts.length > 0 ? [`    <lastBuildDate>${rfc822(latestUpdate(posts))}</lastBuildDate>`] : []),
    `    <atom:link href="${escapeXml(abs(FEED_PATH))}" rel="self" type="application/rss+xml" />`,
    items,
    '  </channel>',
    '</rss>',
    '',
  ].join('\n');

  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
};
