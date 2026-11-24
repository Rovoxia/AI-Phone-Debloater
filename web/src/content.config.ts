/**
 * Content collections. One collection: `blog`, the posts under src/content/blog/*.md.
 *
 * The file name is the URL slug (/blog/<file name>); other pages and public/llms.txt link to the
 * slugs, so do not rename a file. /blog, /blog/<slug>, /rss.xml and the sitemap `lastmod` all read
 * this collection: adding a post means adding one Markdown file and nothing else.
 *
 * Rules for post bodies:
 * - Never type a rule count, a tier table or a package table in Markdown. The post template
 *   (src/pages/blog/[slug].astro) builds them from src/data/rules-dataset.json for `oemIds`.
 * - Write CLI flags and package names in backticks. Outside code, Markdown turns "--" into a dash.
 * - No column alignment (":---") in Markdown tables and no raw HTML: both can emit inline styles,
 *   which the CSP blocks.
 */
import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

/** Display order on /blog. */
export const BLOG_CATEGORIES = ['Brand guides', 'Setup', 'Safety', 'Comparisons'] as const;

/** `oemId` values of rules-dataset.json that a post can render rule tables for. */
export const BLOG_OEM_IDS = [
  'samsung',
  'xiaomi',
  'pixel',
  'oneplus',
  'bbk',
  'motorola',
  'transsion',
  'huawei',
  'universal',
] as const;

const SITE_NAME_SUFFIX = ' | AI Phone Debloater';

const words = (text: string): number => text.trim().split(/\s+/).filter(Boolean).length;

const blog = defineCollection({
  loader: glob({ pattern: '*.md', base: './src/content/blog' }),
  schema: z
    .object({
      /** The visible <h1> and the BlogPosting headline. Sentence case. */
      title: z.string().min(20).max(70),
      /**
       * Text for <title>, Open Graph and the browser tab when `title` is too long for it.
       * At most 60 characters. The " | AI Phone Debloater" suffix is added only if the result
       * still fits in 60, so 39 characters or fewer keeps the brand in the title.
       */
      seoTitle: z.string().min(20).max(60).optional(),
      /** Meta description, card text on /blog and the RSS item text. Unique per post. */
      description: z.string().min(110).max(160),
      /**
       * The direct answer to the question in the title, in plain text. Rendered as the lead
       * paragraph under the <h1>, before anything else, so it can be quoted on its own.
       */
      answer: z.string().refine((text) => words(text) >= 40 && words(text) <= 60, {
        message: '`answer` must be 40 to 60 words',
      }),
      pubDate: z.coerce.date(),
      /** Set it to the day the content last changed. Feeds dateModified, RSS and sitemap lastmod. */
      updatedDate: z.coerce.date(),
      category: z.enum(BLOG_CATEGORIES),
      tags: z.array(z.string().min(2)).min(1).max(8),
      /**
       * Brands the post is about. For each one the template renders the tier counts and the full
       * rule tables from the dataset, and links to /oems/<oemId>.
       */
      oemIds: z.array(z.enum(BLOG_OEM_IDS)).min(1).optional(),
      /**
       * Leave rules out of this post's tables when their package name starts with one of these
       * prefixes. For rule files shared by several brands (`bbk` holds Oppo, Realme and Vivo
       * packages). The template says how many rules were left out and links to the full list.
       */
      excludePackagePrefixes: z.array(z.string().regex(/^[a-z][a-z0-9_.]*\.$/)).optional(),
      /** Render the four-tier overview (names, counts, per-brand breakdown, critical categories). */
      tierOverview: z.boolean().default(false),
      /** Drafts are left out of the build: no page, no index card, no feed item, no sitemap entry. */
      draft: z.boolean().default(false),
    })
    .refine((post) => (post.seoTitle ?? post.title).length <= 60, {
      message: `the <title> text (seoTitle, or title when there is no seoTitle) must be 60 characters or fewer; "${SITE_NAME_SUFFIX}" is appended only when it still fits`,
      path: ['seoTitle'],
    })
    .refine((post) => post.updatedDate.getTime() >= post.pubDate.getTime(), {
      message: 'updatedDate must not be before pubDate',
      path: ['updatedDate'],
    })
    .refine((post) => !(post.tierOverview && post.oemIds?.length), {
      message: 'use either oemIds or tierOverview, not both: each renders its own summary and rule section',
      path: ['tierOverview'],
    })
    .refine((post) => !post.excludePackagePrefixes?.length || Boolean(post.oemIds?.length), {
      message: 'excludePackagePrefixes needs oemIds',
      path: ['excludePackagePrefixes'],
    }),
});

export const collections = { blog };
