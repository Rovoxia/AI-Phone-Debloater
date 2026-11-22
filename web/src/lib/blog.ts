/**
 * The blog: one place that reads the `blog` content collection (src/content.config.ts).
 * Used by /blog, /blog/<slug> and /rss.xml, so the three can never list different posts.
 *
 * Server-side only (it imports astro:content).
 */
import { getCollection, type CollectionEntry } from 'astro:content';

export type Post = CollectionEntry<'blog'>;
export type PostCategory = Post['data']['category'];

/** The post every other post links to. */
export const SAFETY_TIERS_POST_ID = 'adb-debloat-safety-tiers-explained';

export { FEED_PATH, FEED_TITLE } from './seo';

/** Section text for each category on /blog, in display order. */
export const CATEGORY_INFO: { name: PostCategory; id: string; description: string }[] = [
  {
    name: 'Brand guides',
    id: 'brand-guides',
    description:
      'One guide per phone maker. Each lists the rules for that brand, by tier, and says what stops working when a group of them is turned off.',
  },
  {
    name: 'Setup',
    id: 'setup',
    description: 'Getting the phone and the computer talking over ADB.',
  },
  {
    name: 'Safety',
    id: 'safety',
    description: 'How the rules are sorted and which packages are never touched.',
  },
  {
    name: 'Comparisons',
    id: 'comparisons',
    description: 'What debloating does next to the other ways of cleaning up a phone.',
  },
];

/** Published posts, newest first; posts from the same day in title order. */
export async function getPosts(): Promise<Post[]> {
  const posts = await getCollection('blog', (post) => !post.data.draft);
  return posts.sort(
    (a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime() || a.data.title.localeCompare(b.data.title, 'en'),
  );
}

export const postPath = (post: Post): string => `/blog/${post.id}`;

/** "2026-11-01" for <time datetime>, formatDate() and isoDateTime() in src/lib/seo.ts. */
export const ymd = (date: Date): string => date.toISOString().slice(0, 10);

/** The newest `updatedDate` of a list of posts. */
export function latestUpdate(posts: Post[]): Date {
  return new Date(Math.max(...posts.map((post) => post.data.updatedDate.getTime())));
}

/** Words in a Markdown string: syntax, link targets and bare punctuation are not counted. */
export function countWords(markdown: string): number {
  const text = markdown
    .replace(/^```.*$/gm, ' ') // fence lines; the code inside is counted
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1') // links and images: keep the text
    .replace(/^\s*\|?[\s:|-]+\|?\s*$/gm, ' ') // table separator rows
    .replace(/[#>*_`|~]/g, ' ');
  return text.split(/\s+/).filter((word) => /[A-Za-z0-9]/.test(word)).length;
}

/** Words a reader goes through: the lead answer plus the Markdown body. Generated tables are not counted. */
export function postWordCount(post: Post): number {
  return countWords(post.data.answer) + countWords(post.body ?? '');
}

const WORDS_PER_MINUTE = 200;

/** Whole minutes, rounded up, at 200 words a minute. */
export function readingMinutes(wordCount: number): number {
  return Math.max(1, Math.ceil(wordCount / WORDS_PER_MINUTE));
}

/**
 * Up to `limit` posts to show under a post: the safety-tiers post first, then the next posts of
 * the same category (wrapping round, so every post in a category is linked from another one),
 * then the first post of each other category, then whatever is left, in list order.
 */
export function relatedPosts(post: Post, all: Post[], limit = 3): Post[] {
  const others = all.filter((other) => other.id !== post.id);
  const safety = others.filter((other) => other.id === SAFETY_TIERS_POST_ID);
  const sameCategory = all.filter((other) => other.data.category === post.data.category);
  const index = sameCategory.findIndex((other) => other.id === post.id);
  const rotated = [...sameCategory.slice(index + 1), ...sameCategory.slice(0, index)];
  const otherCategories = CATEGORY_INFO.filter((category) => category.name !== post.data.category)
    .map((category) => others.find((other) => other.data.category === category.name))
    .filter((other): other is Post => other !== undefined);
  const picked: Post[] = [];
  for (const candidate of [...safety, ...rotated, ...otherCategories, ...others]) {
    if (!picked.some((p) => p.id === candidate.id)) picked.push(candidate);
    if (picked.length === limit) break;
  }
  return picked;
}

/** `<title>` text and whether the " | AI Phone Debloater" suffix still fits in 60 characters. */
export function postHeadTitle(post: Post, siteName: string): { title: string; withSiteName: boolean } {
  const title = post.data.seoTitle ?? post.data.title;
  return { title, withSiteName: `${title} | ${siteName}`.length <= 60 };
}
