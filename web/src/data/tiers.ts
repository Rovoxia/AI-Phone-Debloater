/**
 * Safety tiers: the single source for tier names, descriptions and counts.
 *
 * Names match the CLI (`debloat_engine.py`: Tier 1 Safe, Tier 2 Advanced, Tier 3 Extreme,
 * Tier 4 Critical). Counts are read from rules-dataset.json and never typed. Use this module for
 * every tier label, badge, card and sentence on the site, and for any JSON-LD that names a tier.
 *
 * This file imports the full rules dataset. Server-side (frontmatter) use is free; in a client
 * <script> only import it where the dataset is bundled already (the /app script).
 */
import rulesData from './rules-dataset.json';
import { ICONS, iconSvg } from '../lib/icons';

export type TierId = 1 | 2 | 3 | 4;

/** Icon names from src/lib/icons.ts. The icon is the badge's non-colour cue. */
export type TierIcon = 'circle-check' | 'circle-alert' | 'triangle-alert' | 'lock';

export interface Tier {
  id: TierId;
  /** "Tier 1" */
  label: string;
  /** "Safe" */
  name: string;
  /** "Tier 1 · Safe" */
  title: string;
  /** CSS class for badges and accents: "tier-1" ... "tier-4". */
  className: string;
  icon: TierIcon;
  /** Number of rules in this tier, from the dataset. */
  count: number;
  /** False for Tier 4: no code path may disable or uninstall these packages. */
  removable: boolean;
  /** One short line: who the tier is for. */
  audience: string;
  /** One or two sentences, plain text, safe to quote on its own. */
  description: string;
}

const { stats, rules } = rulesData;

const TIER_3_RULES = rules.filter((rule) => rule.tier === 3);
const TRANSSION_OTA = 'com.transsion.otaupdate';

// The Tier 3 wording below (and the OTA answer in faq.ts) names the one Tier 3 rule. If the rule
// set changes, fail the build so the copy is rewritten instead of going stale.
if (TIER_3_RULES.length !== 1 || TIER_3_RULES[0].package !== TRANSSION_OTA) {
  throw new Error(
    `src/data/tiers.ts: expected exactly one Tier 3 rule (${TRANSSION_OTA}) but the dataset has ` +
      `${TIER_3_RULES.length}. Update the Tier 3 description here and the OTA answer in src/data/faq.ts.`,
  );
}

/** The only Tier 3 rule today. */
export const TIER_3_RULE = TIER_3_RULES[0];

function tier(id: TierId, name: string, icon: TierIcon, count: number, audience: string, description: string): Tier {
  return {
    id,
    label: `Tier ${id}`,
    name,
    title: `Tier ${id} · ${name}`,
    className: `tier-${id}`,
    icon,
    count,
    removable: id !== 4,
    audience,
    description,
  };
}

export const TIERS: Tier[] = [
  tier(
    1,
    'Safe',
    'circle-check',
    stats.tier1Count,
    'The default. For any user.',
    'Carrier apps, preloaded partner apps such as Facebook, Netflix and Amazon, OEM ad services and telemetry, and OEM extras such as Bixby and AR Zone. The project classifies these as safe to disable on any phone.',
  ),
  tier(
    2,
    'Advanced',
    'circle-alert',
    stats.tier2Count,
    'Review each one first.',
    'Optional OEM and Google features that some people use, such as Samsung Wallet and Samsung Pass, DeX, Link to Windows, theme stores, Android Auto and Digital Wellbeing. Safe to disable if you do not use the feature.',
  ),
  tier(
    3,
    'Extreme',
    'triangle-alert',
    stats.tier3Count,
    'Experts only.',
    `System updaters. Today that is one rule, the Transsion OTA updater (${TRANSSION_OTA}) on Tecno, Infinix and itel phones. Disabling it stops system updates until it is enabled again.`,
  ),
  tier(
    4,
    'Critical',
    'lock',
    stats.tier4CriticalCount,
    'Nobody. Hard-blocked.',
    'Core Android packages such as the Android framework, System UI, telephony, Settings, the package installer and Google Play services. AI Phone Debloater never disables or uninstalls them, whatever tier, flag or prompt is used.',
  ),
];

export const TIER_BY_ID: Record<TierId, Tier> = {
  1: TIERS[0],
  2: TIERS[1],
  3: TIERS[2],
  4: TIERS[3],
};

/** Tiers 1 to 3: the ones a plan can act on. */
export const REMOVABLE_TIERS: Tier[] = TIERS.filter((t) => t.removable);

/** Tier for a rule's `tier` value. Anything that is not 1, 2 or 3 is treated as Tier 4. */
export function tierFor(value: number | null | undefined): Tier {
  return value === 1 || value === 2 || value === 3 ? TIER_BY_ID[value] : TIER_BY_ID[4];
}

/** Rule counts for copy and structured data. Read them from here, never type them. */
export const RULE_STATS = {
  /** Every rule, including the critical list. */
  total: stats.totalRules,
  /** Rules a plan can act on: tiers 1 to 3. */
  removable: stats.tier1Count + stats.tier2Count + stats.tier3Count,
  /** Protected packages: Tier 4. */
  critical: stats.tier4CriticalCount,
  tier1: stats.tier1Count,
  tier2: stats.tier2Count,
  tier3: stats.tier3Count,
} as const;

if (RULE_STATS.removable + RULE_STATS.critical !== RULE_STATS.total) {
  throw new Error('src/data/tiers.ts: tier counts in rules-dataset.json do not add up to totalRules.');
}

/* ---- Tier badge -------------------------------------------------------- */

export interface TierBadgeOptions {
  /** Show "Tier 1" only, without the name. For dense tables. */
  compact?: boolean;
  /**
   * Draw the icon as a <use> of the page's tier sprite instead of a full inline <svg>. For tables
   * with hundreds of rows. The page must render <TierSprite /> once (it calls tierSpriteHtml()).
   */
  sprite?: boolean;
}

/** id of a tier's <symbol> in the sprite written by tierSpriteHtml(). */
const spriteId = (id: TierId): string => `tier-icon-${id}`;

/**
 * The tier badge markup, as a string. Server-side, use <TierBadge tier={n} /> (it calls this).
 * In a client script, assign the result to innerHTML: it contains no user data.
 *
 * The text is always "Tier 1: Safe". The ": " is real text for screen readers, textContent and
 * copy/paste; it is visually hidden, and the full badge draws a middle dot in its place (CSS,
 * .tier-name::before). The compact badge hides the name as well.
 */
export function tierBadgeHtml(value: number | null | undefined, options: TierBadgeOptions = {}): string {
  const t = tierFor(value);
  const icon = options.sprite
    ? `<svg class="icon" aria-hidden="true"><use href="#${spriteId(t.id)}"/></svg>`
    : iconSvg(t.icon);
  const name = options.compact
    ? `<span class="sr-only">: ${t.name}</span>`
    : `<span class="sr-only">: </span><span class="tier-name">${t.name}</span>`;
  return `<span class="tier ${t.className}">${icon}<span>${t.label}</span>${name}</span>`;
}

/**
 * The four tier icons as <symbol>s in one hidden <svg>, for badges drawn with `sprite: true`.
 * Server-side, use <TierSprite /> once per page. The stroke styling of the <use> copies is in
 * global.css (.tier .icon).
 */
export function tierSpriteHtml(): string {
  const symbols = TIERS.map((t) => `<symbol id="${spriteId(t.id)}" viewBox="0 0 24 24">${ICONS[t.icon]}</symbol>`);
  return `<svg class="hidden" aria-hidden="true">${symbols.join('')}</svg>`;
}
