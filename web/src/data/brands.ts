/**
 * Brand groups of the rule set, for /oems and /oems/<oemId>.
 *
 * One group per `oemId` in rules-dataset.json. Everything that is a number, a package or an app
 * name is computed from the dataset here; the only typed text is the display copy in COPY (brand
 * and Android-skin names, which come from the rule files' own `manufacturer` and `description`
 * fields, the old /oems anchors, the `--manufacturer` words the engine accepts and the guide
 * links). An `oemId` with no entry in COPY still gets a page, built from the dataset's own
 * `brand` and `oemGroup` strings.
 *
 * Server-side only: it imports the whole dataset. Do not import it from a client <script>.
 */
import rulesData from './rules-dataset.json';
import { TIERS, tierFor, type Tier } from './tiers';

export type Rule = (typeof rulesData.rules)[number];

export interface GuideLink {
  /** "/blog/<slug>" */
  path: string;
  title: string;
}

interface BrandCopy {
  /** Short name: cards, breadcrumbs, the brand filter. "Samsung" */
  name: string;
  /** Subject of the page heading: `${listName} bloatware list`. "Samsung One UI" */
  listName: string;
  /** Subject of <title>; kept short so the full title fits 60 characters. */
  titleName: string;
  /** One line for the brand card on /oems: which phones the rule file is written for. */
  summary: string;
  /** The same as a full sentence, for the brand page. */
  scope: string;
  /** Short name for the Brand column of the /oems table. */
  shortName: string;
  /** Names for the /oems meta description. Empty for the groups that are not a brand. */
  metaNames: string[];
  /** id of the brand's card on /oems. These are the anchors the old page used. */
  anchor: string;
  /** Other old /oems#... anchors that meant this brand. The page script maps them to the filter. */
  legacyAnchors: string[];
  /**
   * Words `--manufacturer` accepts for this rule file (the engine matches the word against the
   * file name and its `manufacturer` field). The first one is used in the example command.
   */
  manufacturers: string[];
  /** The brand's own guide(s). The safety-tiers guide is added for every brand. */
  guides: GuideLink[];
}

const TIERS_GUIDE: GuideLink = {
  path: '/blog/adb-debloat-safety-tiers-explained',
  title: 'ADB debloat safety tiers explained',
};

const COLOROS_GUIDE: GuideLink = {
  path: '/blog/oneplus-oppo-realme-debloat-guide-coloros',
  title: 'OnePlus, Oppo and Realme debloat guide',
};

const COPY: Record<string, BrandCopy> = {
  samsung: {
    name: 'Samsung',
    listName: 'Samsung One UI',
    titleName: 'Samsung One UI',
    summary: 'Galaxy phones and tablets running One UI.',
    scope: 'It is written for Samsung Galaxy phones and tablets running One UI.',
    shortName: 'Samsung',
    metaNames: ['Samsung'],
    anchor: 'samsung-oneui',
    legacyAnchors: ['samsung'],
    manufacturers: ['samsung'],
    guides: [{ path: '/blog/samsung-galaxy-debloat-guide-one-ui-6', title: 'Samsung Galaxy debloat guide' }],
  },
  xiaomi: {
    name: 'Xiaomi',
    listName: 'Xiaomi HyperOS and MIUI',
    titleName: 'Xiaomi HyperOS',
    summary: 'Xiaomi, Redmi and POCO phones running MIUI or HyperOS.',
    scope: 'It is written for Xiaomi, Redmi and POCO phones running MIUI or HyperOS.',
    shortName: 'Xiaomi',
    metaNames: ['Xiaomi'],
    anchor: 'xiaomi-miui-hyperos',
    legacyAnchors: ['xiaomi', 'hyperos-debloat', 'hyperos-miui'],
    manufacturers: ['xiaomi', 'redmi', 'poco'],
    guides: [{ path: '/blog/xiaomi-hyperos-debloat-guide', title: 'Xiaomi HyperOS debloat guide' }],
  },
  pixel: {
    name: 'Google Pixel',
    listName: 'Google Pixel',
    titleName: 'Google Pixel',
    summary: 'Pixel phones running stock Android.',
    scope: 'It is written for Google Pixel phones running stock Android.',
    shortName: 'Google Pixel',
    metaNames: ['Pixel'],
    anchor: 'google-pixel',
    legacyAnchors: ['pixel', 'google', 'pixel-nothing', 'vivo-pixel-stock'],
    manufacturers: ['google'],
    guides: [{ path: '/blog/pixel-debloat-guide-stock-android', title: 'Google Pixel debloat guide' }],
  },
  oneplus: {
    name: 'OnePlus',
    listName: 'OnePlus OxygenOS',
    titleName: 'OnePlus OxygenOS',
    summary: 'OnePlus phones running OxygenOS.',
    scope: 'It is written for OnePlus phones running OxygenOS.',
    shortName: 'OnePlus',
    metaNames: ['OnePlus'],
    anchor: 'oneplus-oxygenos',
    legacyAnchors: ['oneplus'],
    manufacturers: ['oneplus'],
    guides: [COLOROS_GUIDE],
  },
  bbk: {
    name: 'Oppo, Vivo and Realme',
    listName: 'Oppo, Vivo and Realme',
    titleName: 'Oppo, Vivo, Realme',
    summary: 'Oppo (ColorOS), Vivo (Funtouch OS, OriginOS) and Realme (Realme UI) phones.',
    scope: 'It is written for Oppo phones running ColorOS, Vivo phones running Funtouch OS or OriginOS, and Realme phones running Realme UI.',
    shortName: 'Oppo / Vivo / Realme',
    metaNames: ['Oppo', 'Vivo'],
    anchor: 'coloros-oxygenos',
    legacyAnchors: ['bbk', 'oppo', 'realme', 'vivo', 'iqoo', 'vivo-funtouch'],
    manufacturers: ['oppo', 'vivo', 'realme', 'iqoo'],
    guides: [
      COLOROS_GUIDE,
      { path: '/blog/vivo-iqoo-debloat-guide-funtouchos', title: 'Vivo and iQOO debloat guide' },
    ],
  },
  motorola: {
    name: 'Motorola',
    listName: 'Motorola',
    titleName: 'Motorola',
    summary: 'Motorola phones running My UX and Hello UI.',
    scope: 'It is written for Motorola phones running My UX and Hello UI.',
    shortName: 'Motorola',
    metaNames: ['Motorola'],
    anchor: 'motorola',
    legacyAnchors: ['moto'],
    manufacturers: ['motorola'],
    guides: [{ path: '/blog/motorola-debloat-guide-myux', title: 'Motorola debloat guide' }],
  },
  transsion: {
    name: 'Tecno, Infinix and itel',
    listName: 'Tecno, Infinix and itel',
    titleName: 'Tecno, Infinix, itel',
    summary: 'Tecno (HiOS), Infinix (XOS) and itel phones.',
    scope: 'It is written for the Transsion brands: Tecno phones running HiOS, Infinix phones running XOS, and itel phones.',
    shortName: 'Tecno / Infinix / itel',
    metaNames: ['Transsion'],
    anchor: 'transsion',
    legacyAnchors: ['tecno', 'infinix', 'itel'],
    manufacturers: ['tecno', 'infinix', 'itel'],
    guides: [{ path: '/blog/transsion-debloat-guide-hios-xos', title: 'Tecno and Infinix debloat guide' }],
  },
  huawei: {
    name: 'Huawei',
    listName: 'Huawei EMUI',
    titleName: 'Huawei EMUI',
    summary: 'Huawei phones running EMUI.',
    scope: 'It is written for Huawei phones running EMUI.',
    shortName: 'Huawei',
    metaNames: ['Huawei'],
    anchor: 'huawei-emui',
    legacyAnchors: ['huawei'],
    manufacturers: ['huawei'],
    guides: [],
  },
  universal: {
    name: 'Universal',
    listName: 'Universal Android',
    titleName: 'Universal Android',
    summary: 'Apps that carriers and partners preload across brands.',
    scope: 'It applies to any Android phone and covers apps that carriers and partners preload across brands.',
    shortName: 'Universal',
    metaNames: [],
    anchor: 'universal',
    legacyAnchors: [],
    manufacturers: [],
    guides: [],
  },
  critical: {
    name: 'Critical system packages',
    listName: 'Critical Android packages',
    titleName: 'Critical Android Packages',
    summary: 'Core Android packages. Never disabled or uninstalled.',
    scope: 'It applies to every Android phone.',
    shortName: 'Core system',
    metaNames: [],
    anchor: 'critical',
    legacyAnchors: [],
    manufacturers: [],
    guides: [],
  },
};

/** Display order. Groups the dataset has but this list does not are appended in dataset order. */
const ORDER = ['samsung', 'xiaomi', 'pixel', 'oneplus', 'bbk', 'motorola', 'transsion', 'huawei', 'universal', 'critical'];

/* ---- Categories -------------------------------------------------------- */

interface CategoryCopy {
  /** Column value: "Ad service" */
  label: string;
  /** In a sentence after a count: "1 ad service", "5 ad services". */
  one: string;
  many: string;
}

const CATEGORY: Record<string, CategoryCopy> = {
  adware: { label: 'Ad service', one: 'ad service', many: 'ad services' },
  bloatware: { label: 'Preinstalled app', one: 'preinstalled app', many: 'preinstalled apps' },
  carrier: { label: 'Carrier app', one: 'carrier app', many: 'carrier apps' },
  telemetry: { label: 'Telemetry', one: 'telemetry service', many: 'telemetry services' },
  optional_feature: { label: 'Optional feature', one: 'optional feature', many: 'optional features' },
  voice_assistant: { label: 'Voice assistant', one: 'voice assistant', many: 'voice assistants' },
  framework_core: { label: 'Android framework', one: 'Android framework package', many: 'Android framework packages' },
  telephony_radio_emergency: {
    label: 'Telephony and emergency',
    one: 'telephony, radio or emergency package',
    many: 'telephony, radio and emergency packages',
  },
  settings_providers: {
    label: 'Settings and providers',
    one: 'settings or provider package',
    many: 'settings and provider packages',
  },
  wifi_bluetooth_network: {
    label: 'Wi-Fi, Bluetooth and network',
    one: 'Wi-Fi, Bluetooth or network package',
    many: 'Wi-Fi, Bluetooth and network packages',
  },
  google_play_services: {
    label: 'Google Play services',
    one: 'Google Play services package',
    many: 'Google Play services packages',
  },
  security_keystore: {
    label: 'Security and keystore',
    one: 'security or keystore package',
    many: 'security and keystore packages',
  },
  media_storage_core: {
    label: 'Media and storage',
    one: 'media or storage package',
    many: 'media and storage packages',
  },
  systemui_navigation: {
    label: 'System UI and navigation',
    one: 'System UI or navigation package',
    many: 'System UI and navigation packages',
  },
  package_management_permissions: {
    label: 'Package management',
    one: 'package management or permission package',
    many: 'package management and permission packages',
  },
  biometrics_lockscreen: {
    label: 'Biometrics and lock screen',
    one: 'biometrics or lock screen package',
    many: 'biometrics and lock screen packages',
  },
};

// On the critical list the dataset files a few OEM services under "optional_feature". Their own
// descriptions say the system depends on them, so the label must not read as "optional" there.
const CRITICAL_CATEGORY: Record<string, CategoryCopy> = {
  optional_feature: { label: 'OEM service', one: 'OEM service', many: 'OEM services' },
};

function categoryCopy(id: string, critical = false): CategoryCopy {
  const known = (critical && CRITICAL_CATEGORY[id]) || CATEGORY[id];
  if (known) return known;
  const text = (id || 'other').replace(/_/g, ' ');
  return { label: text.charAt(0).toUpperCase() + text.slice(1), one: `${text} package`, many: `${text} packages` };
}

/** Category of one rule, for a table cell. Tier 4 rules use the critical-list wording. */
export function categoryLabel(rule: Rule): string {
  return categoryCopy(rule.category, tierFor(rule.tier).id === 4).label;
}

/* ---- Actions ----------------------------------------------------------- */

const ACTION_LABEL: Record<string, string> = {
  disable: 'Disable',
  uninstall: 'Uninstall',
  never: 'Never changed',
};

/** Recommended action of one rule, for a table cell. Tier 4 is always "Never changed". */
export function actionLabel(rule: Rule): string {
  if (tierFor(rule.tier).id === 4) return ACTION_LABEL.never;
  const action = rule.recommended_action;
  return ACTION_LABEL[action] ?? action.charAt(0).toUpperCase() + action.slice(1);
}

/* ---- Text helpers ------------------------------------------------------ */

/** "a", "a and b", "a, b and c" */
export function joinList(items: string[]): string {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** "1 rule", "44 rules" */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** The first candidate that is at most `max` characters, else the last one. */
export function firstThatFits(candidates: string[], max: number): string {
  return candidates.find((text) => text.length <= max) ?? candidates[candidates.length - 1];
}

/* ---- Brand groups ------------------------------------------------------ */

export interface TierCount {
  tier: Tier;
  count: number;
}

export interface CategoryCount extends CategoryCopy {
  id: string;
  count: number;
}

export interface Brand extends BrandCopy {
  /** `oemId` in the dataset and the page slug. */
  id: string;
  /** "/oems/<id>" */
  path: string;
  /** The group's rules, by tier and then in dataset order. */
  rules: Rule[];
  count: number;
  /** The tiers this group has rules in, lowest first. */
  tiers: TierCount[];
  /** Largest category first. */
  categories: CategoryCount[];
  /** Rules whose recommended action is "disable" / "uninstall". */
  disableCount: number;
  uninstallCount: number;
  /** Rule file names, e.g. "samsung-oneui.json". */
  sourceFiles: string[];
  /** True when every rule is Tier 4: the group is the protected list, not a debloat list. */
  critical: boolean;
  /** The brand's guide(s) followed by the safety-tiers guide. */
  allGuides: GuideLink[];
}

function fallbackCopy(id: string, sample: Rule): BrandCopy {
  const name = sample.brand || id;
  return {
    name,
    listName: sample.oemGroup || name,
    titleName: name,
    summary: `${sample.oemGroup || name} phones.`,
    scope: `It is written for ${sample.oemGroup || name} phones.`,
    shortName: name,
    metaNames: [name],
    anchor: id,
    legacyAnchors: [],
    manufacturers: [],
    guides: [],
  };
}

function buildBrand(id: string, groupRules: Rule[]): Brand {
  const copy = COPY[id] ?? fallbackCopy(id, groupRules[0]);
  const rules = groupRules
    .map((rule, index) => ({ rule, index }))
    .sort((a, b) => tierFor(a.rule.tier).id - tierFor(b.rule.tier).id || a.index - b.index)
    .map((entry) => entry.rule);

  const tiers = TIERS.map((tier) => ({
    tier,
    count: rules.filter((rule) => tierFor(rule.tier).id === tier.id).length,
  })).filter((entry) => entry.count > 0);

  const critical = tiers.length === 1 && tiers[0].tier.id === 4;

  const categoryCounts = new Map<string, number>();
  for (const rule of rules) categoryCounts.set(rule.category, (categoryCounts.get(rule.category) ?? 0) + 1);
  const categories = [...categoryCounts.entries()]
    .map(([categoryId, count]) => ({ id: categoryId, count, ...categoryCopy(categoryId, critical) }))
    .sort((a, b) => b.count - a.count);

  const removable = rules.filter((rule) => tierFor(rule.tier).id !== 4);

  return {
    ...copy,
    id,
    path: `/oems/${id}`,
    rules,
    count: rules.length,
    tiers,
    categories,
    disableCount: removable.filter((rule) => rule.recommended_action === 'disable').length,
    uninstallCount: removable.filter((rule) => rule.recommended_action === 'uninstall').length,
    sourceFiles: [...new Set(rules.map((rule) => rule.sourceFile))],
    critical,
    allGuides: [...copy.guides, TIERS_GUIDE],
  };
}

const grouped = new Map<string, Rule[]>();
for (const rule of rulesData.rules) {
  const list = grouped.get(rule.oemId);
  if (list) list.push(rule);
  else grouped.set(rule.oemId, [rule]);
}

const orderedIds = [...ORDER.filter((id) => grouped.has(id)), ...[...grouped.keys()].filter((id) => !ORDER.includes(id))];

/** Every brand group in the dataset, in display order. Their counts add up to the dataset total. */
export const BRANDS: Brand[] = orderedIds.map((id) => buildBrand(id, grouped.get(id) as Rule[]));

export const BRAND_BY_ID: Record<string, Brand> = Object.fromEntries(BRANDS.map((brand) => [brand.id, brand]));

const brandTotal = BRANDS.reduce((sum, brand) => sum + brand.count, 0);
if (brandTotal !== rulesData.rules.length) {
  throw new Error(`src/data/brands.ts: brand groups hold ${brandTotal} rules but the dataset has ${rulesData.rules.length}.`);
}

/** Every rule, in the order /oems lists them: brand order, then tier, then dataset order. */
export const ALL_RULES: Rule[] = BRANDS.flatMap((brand) => brand.rules);

/** Old /oems#<anchor> values (and the brand ids themselves) mapped to a brand id. */
export const ANCHOR_TO_BRAND: Record<string, string> = Object.fromEntries(
  BRANDS.flatMap((brand) => [brand.id, brand.anchor, ...brand.legacyAnchors].map((anchor) => [anchor, brand.id])),
);

/** "25 in Tier 1 (Safe) and 19 in Tier 2 (Advanced)"; "all 4 in Tier 2 (Advanced)" for a single tier. */
export function tierSplitText(brand: Brand): string {
  if (brand.tiers.length === 1) {
    const only = brand.tiers[0];
    return `${brand.count === 1 ? '' : 'all '}${only.count} in ${only.tier.label} (${only.tier.name})`;
  }
  return joinList(brand.tiers.map((entry) => `${entry.count} in ${entry.tier.label} (${entry.tier.name})`));
}

/** "25 Tier 1, 19 Tier 2": the short form for meta descriptions. */
export function tierSplitShort(brand: Brand): string {
  return brand.tiers.map((entry) => `${entry.count} ${entry.tier.label}`).join(', ');
}

/** "17 optional features, 12 preinstalled apps and 9 telemetry services" */
export function categorySplitText(brand: Brand): string {
  return joinList(brand.categories.map((entry) => plural(entry.count, entry.one, entry.many)));
}

/** Up to `limit` app names from the group's rules, lowest tier first. */
export function exampleNames(brand: Brand, limit = 3): string[] {
  return brand.rules
    .map((rule) => rule.name)
    .filter((name): name is string => Boolean(name))
    .slice(0, limit);
}
