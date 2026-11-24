/**
 * Site identity, URL helpers and JSON-LD node builders.
 *
 * Every page emits exactly one <script type="application/ld+json"> through SeoHead.astro. Its
 * @graph is made of the nodes built here, tied together by the @id constants below, so one
 * Organization and one WebSite node are referenced from everywhere instead of being repeated.
 *
 * Only put facts in structured data that are true and visible on the page. There is no
 * aggregateRating, review or user-count builder here on purpose: the project has none to report.
 *
 * Server-side only. Do not import this from a client <script>.
 */

/** Origin from `site` in astro.config.mjs, without a trailing slash. */
export const SITE_URL: string = (import.meta.env.SITE ?? 'https://debloater.rovoxia.com').replace(/\/+$/, '');

export const SITE_NAME = 'AI Phone Debloater';
export const SITE_LANG = 'en';
export const ORG_NAME = 'Rovoxia';
export const ORG_URL = 'https://rovoxia.com';
export const GITHUB_ORG = 'https://github.com/Rovoxia';
export const GITHUB_REPO = 'https://github.com/Rovoxia/AI-Phone-Debloater';
export const LICENSE_URL = 'https://opensource.org/licenses/MIT';

export interface OgImage {
  /** Site-relative path, e.g. "/og-image.png". */
  src: string;
  alt: string;
  width?: number;
  height?: number;
  type?: string;
}

export const DEFAULT_OG_IMAGE: OgImage = {
  src: '/og-image.png',
  alt: 'AI Phone Debloater: remove Android bloatware over ADB, no root',
  width: 1200,
  height: 630,
  type: 'image/png',
};

/** Square PNG logo for Organization.logo and SoftwareApplication.image. */
export const LOGO_PATH = '/logo-512.png';

/** The RSS feed of the guides (src/pages/rss.xml.ts). SeoHead links it from every indexable page. */
export const FEED_PATH = '/rss.xml';
export const FEED_TITLE = `${SITE_NAME} guides`;

/**
 * Canonical site path: no ".html", no "/index", no trailing slash, "/" for the home page.
 * `build.format: 'file'` makes Astro.url.pathname "/app.html" during the build and "/app" in dev;
 * this gives "/app" in both.
 */
export function normalizePath(pathname: string): string {
  const clean = pathname
    .replace(/[?#].*$/, '')
    .replace(/\.html$/, '')
    .replace(/\/index$/, '')
    .replace(/\/+$/, '');
  return clean === '' ? '/' : clean;
}

/** The current page's canonical path. Pass `Astro.url`. */
export function currentPath(url: URL): string {
  return normalizePath(url.pathname);
}

/** Absolute URL for a site path. Absolute URLs pass through; "/" keeps its slash. */
export function abs(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  const cut = path.search(/[?#]/);
  const pathname = cut === -1 ? path : path.slice(0, cut);
  const suffix = cut === -1 ? '' : path.slice(cut);
  const clean = normalizePath(pathname.startsWith('/') ? pathname : `/${pathname}`);
  return `${SITE_URL}${clean}${suffix}`;
}

/* ---- @id values -------------------------------------------------------- */

export const ORG_ID = `${SITE_URL}/#organization`;
export const WEBSITE_ID = `${SITE_URL}/#website`;
/** The CLI and rule set as a product. Emitted on "/" only; reference it by @id elsewhere. */
export const APP_ID = `${SITE_URL}/#software`;
export const WEBAPP_ID = `${SITE_URL}/app#webapp`;
export const DATASET_ID = `${SITE_URL}/oems#dataset`;
export const BLOG_ID = `${SITE_URL}/blog#blog`;

export const pageId = (path: string): string => `${abs(path)}#webpage`;
export const breadcrumbId = (path: string): string => `${abs(path)}#breadcrumb`;
export const articleId = (path: string): string => `${abs(path)}#article`;
export const faqId = (path: string): string => `${abs(path)}#faq`;

/* ---- Serialisation ----------------------------------------------------- */

export type JsonLdNode = Record<string, unknown>;

/**
 * The string for <script type="application/ld+json" set:html={...} />.
 * "<" is escaped so no text in a node can close the script element.
 */
export function serializeJsonLd(nodes: JsonLdNode[]): string {
  return JSON.stringify({ '@context': 'https://schema.org', '@graph': nodes }).replace(/</g, '\\u003c');
}

/** "2026-11-01" becomes "2026-11-01T00:00:00+00:00"; a full ISO date-time passes through. */
export function isoDateTime(date: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? `${date}T00:00:00+00:00` : date;
}

/** Date for display, always in UTC so the build machine's time zone cannot shift the day. */
export function formatDate(date: string): string {
  return new Date(isoDateTime(date)).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

/* ---- Site graph (every indexable page) --------------------------------- */

export function organizationNode(): JsonLdNode {
  return {
    '@type': 'Organization',
    '@id': ORG_ID,
    name: ORG_NAME,
    url: ORG_URL,
    sameAs: [GITHUB_ORG],
    logo: { '@type': 'ImageObject', url: abs(LOGO_PATH), width: 512, height: 512 },
  };
}

export function websiteNode(): JsonLdNode {
  return {
    '@type': 'WebSite',
    '@id': WEBSITE_ID,
    url: `${SITE_URL}/`,
    name: SITE_NAME,
    inLanguage: SITE_LANG,
    publisher: { '@id': ORG_ID },
  };
}

export interface Crumb {
  name: string;
  /** Site path without trailing slash: "/", "/blog", "/blog/<slug>". */
  path: string;
}

export interface WebPageInput {
  path: string;
  title: string;
  description: string;
  breadcrumbs?: Crumb[];
  /** e.g. "CollectionPage" for the blog index. Default "WebPage". */
  type?: string;
}

export function webPageNode({ path, title, description, breadcrumbs, type = 'WebPage' }: WebPageInput): JsonLdNode {
  return {
    '@type': type,
    '@id': pageId(path),
    url: abs(path),
    name: title,
    description,
    inLanguage: SITE_LANG,
    isPartOf: { '@id': WEBSITE_ID },
    ...(breadcrumbs?.length ? { breadcrumb: { '@id': breadcrumbId(path) } } : {}),
  };
}

/** `items` runs from the home page to the current page; the last item is the current page. */
export function breadcrumbNode(items: Crumb[]): JsonLdNode {
  const current = items[items.length - 1];
  return {
    '@type': 'BreadcrumbList',
    '@id': breadcrumbId(current.path),
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: abs(item.path),
    })),
  };
}

/* ---- Page nodes -------------------------------------------------------- */

/** The product. Home page only. `version` is SITE_VERSION from src/lib/version.ts. */
export function softwareApplicationNode(version: string, description?: string): JsonLdNode {
  return {
    '@type': 'SoftwareApplication',
    '@id': APP_ID,
    name: SITE_NAME,
    url: `${SITE_URL}/`,
    ...(description ? { description } : {}),
    applicationCategory: 'UtilitiesApplication',
    operatingSystem: 'Windows, macOS, Linux',
    softwareRequirements: 'Python 3.11+, ADB, Android phone with USB debugging enabled',
    softwareVersion: version,
    license: LICENSE_URL,
    isAccessibleForFree: true,
    downloadUrl: `${GITHUB_REPO}/releases`,
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    author: { '@id': ORG_ID },
    publisher: { '@id': ORG_ID },
    image: abs(LOGO_PATH),
  };
}

/** The in-browser tool at /app. */
export function webApplicationNode(version: string, description: string): JsonLdNode {
  return {
    '@type': 'WebApplication',
    '@id': WEBAPP_ID,
    name: `${SITE_NAME} web app`,
    url: abs('/app'),
    description,
    applicationCategory: 'UtilitiesApplication',
    operatingSystem: 'Any',
    browserRequirements: 'WebUSB needs a Chromium browser; other browsers use the local bridge',
    softwareVersion: version,
    isAccessibleForFree: true,
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    author: { '@id': ORG_ID },
    isPartOf: { '@id': WEBSITE_ID },
    mainEntityOfPage: { '@id': pageId('/app') },
  };
}

export interface FaqEntry {
  question: string;
  /** Plain text, identical to what the page shows. */
  answer: string;
}

/** FAQPage for the visible FAQ on `path`. Feed it the same array that renders the list. */
export function faqNode(items: FaqEntry[], path = '/'): JsonLdNode {
  return {
    '@type': 'FAQPage',
    '@id': faqId(path),
    isPartOf: { '@id': pageId(path) },
    mainEntity: items.map((item) => ({
      '@type': 'Question',
      name: item.question,
      acceptedAnswer: { '@type': 'Answer', text: item.answer },
    })),
  };
}

export interface HowToStep {
  name: string;
  /** Plain text, identical to the visible step. */
  text: string;
}

/**
 * HowTo for a step list that is visible on `path` as an <ol>. Do not emit it for steps the page
 * does not show, and do not add totalTime unless it was measured.
 */
export function howToNode(name: string, steps: HowToStep[], path = '/'): JsonLdNode {
  return {
    '@type': 'HowTo',
    '@id': `${abs(path)}#howto`,
    name,
    isPartOf: { '@id': pageId(path) },
    step: steps.map((step, index) => ({
      '@type': 'HowToStep',
      position: index + 1,
      name: step.name,
      text: step.text,
    })),
  };
}

export interface BlogPostingInput {
  /** "/blog/<slug>" */
  path: string;
  headline: string;
  description: string;
  /** "YYYY-MM-DD" or a full ISO date-time. */
  datePublished: string;
  dateModified?: string;
  section?: string;
  tags?: string[];
  wordCount?: number;
  image?: OgImage;
}

export function blogPostingNode(post: BlogPostingInput): JsonLdNode {
  const image = post.image ?? DEFAULT_OG_IMAGE;
  return {
    '@type': 'BlogPosting',
    '@id': articleId(post.path),
    headline: post.headline,
    description: post.description,
    image: [abs(image.src)],
    datePublished: isoDateTime(post.datePublished),
    dateModified: isoDateTime(post.dateModified ?? post.datePublished),
    author: { '@id': ORG_ID },
    publisher: { '@id': ORG_ID },
    mainEntityOfPage: { '@id': pageId(post.path) },
    isPartOf: { '@id': BLOG_ID },
    ...(post.section ? { articleSection: post.section } : {}),
    ...(post.tags?.length ? { keywords: post.tags.join(', ') } : {}),
    ...(post.wordCount ? { wordCount: post.wordCount } : {}),
    inLanguage: SITE_LANG,
  };
}

/** The Blog node for /blog. `postPaths` are "/blog/<slug>" in display order. */
export function blogNode(description: string, postPaths: string[]): JsonLdNode {
  return {
    '@type': 'Blog',
    '@id': BLOG_ID,
    url: abs('/blog'),
    name: `${SITE_NAME} guides`,
    description,
    inLanguage: SITE_LANG,
    publisher: { '@id': ORG_ID },
    isPartOf: { '@id': WEBSITE_ID },
    blogPost: postPaths.map((path) => ({ '@id': articleId(path) })),
  };
}

/** An ordered list of site pages, e.g. the posts on /blog or the brand sections on /oems. */
export function itemListNode(id: string, name: string, items: Crumb[]): JsonLdNode {
  return {
    '@type': 'ItemList',
    '@id': id,
    name,
    numberOfItems: items.length,
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      url: abs(item.path),
    })),
  };
}

export interface DatasetInput {
  name: string;
  description: string;
  /** SITE_VERSION */
  version: string;
  /** Rule file names from the dataset's `sourceFile` field, e.g. "samsung-oneui.json". */
  files: string[];
  keywords?: string[];
  /** "YYYY-MM-DD" or ISO date-time. Leave out if no real date is known. */
  dateModified?: string;
}

/** The rule set shown on /oems. Each rule file becomes a DataDownload pointing at GitHub. */
export function datasetNode(input: DatasetInput): JsonLdNode {
  return {
    '@type': 'Dataset',
    '@id': DATASET_ID,
    name: input.name,
    description: input.description,
    url: abs('/oems'),
    version: input.version,
    license: LICENSE_URL,
    isAccessibleForFree: true,
    inLanguage: SITE_LANG,
    creator: { '@id': ORG_ID },
    isPartOf: { '@id': WEBSITE_ID },
    mainEntityOfPage: { '@id': pageId('/oems') },
    ...(input.keywords?.length ? { keywords: input.keywords } : {}),
    ...(input.dateModified ? { dateModified: isoDateTime(input.dateModified) } : {}),
    distribution: input.files.map((file) => ({
      '@type': 'DataDownload',
      name: file,
      encodingFormat: 'application/json',
      contentUrl: `https://raw.githubusercontent.com/Rovoxia/AI-Phone-Debloater/main/cli/rules/${file}`,
    })),
  };
}
