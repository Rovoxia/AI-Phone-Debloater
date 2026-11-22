/**
 * The FAQ: the single source for the visible list on the home page and for its FAQPage JSON-LD.
 *
 * Render `answerHtml` in the page and pass FAQ straight to faqNode() from src/lib/seo.ts, which
 * reads `question` and `answer`. `answer` is `answerHtml` with the tags removed, so the two can
 * never drift apart.
 *
 * Writing rules for answers:
 * - Answer first, and name the product in the first sentence, so the answer stands alone when an
 *   answer engine quotes it.
 * - Only what the code does. No performance figures, no warranty or banking-app promises, no
 *   claims about other tools.
 * - Counts come from the dataset through tiers.ts.
 * - Inline tags only: <code>, <strong>, <em>, <a href>. No block elements.
 */
import { RULE_STATS, TIERS, TIER_3_RULE } from './tiers';

export interface FaqItem {
  /** Stable anchor: the item renders as <details id={id}>, linkable as /#<id>. */
  id: string;
  question: string;
  /** Trusted static markup for the page (set:html). */
  answerHtml: string;
  /** Plain text for JSON-LD. Derived from answerHtml. */
  answer: string;
}

function toText(html: string): string {
  return html
    .replace(/<[^>]+>/g, '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim();
}

function item(id: string, question: string, answerHtml: string): FaqItem {
  return { id, question, answerHtml, answer: toText(answerHtml) };
}

const tierSentence = TIERS.map((t) =>
  t.removable
    ? `<strong>${t.label} (${t.name})</strong> has ${t.count} ${t.count === 1 ? 'rule' : 'rules'}. ${t.description}`
    : `<strong>${t.label} (${t.name})</strong> protects ${t.count} packages. ${t.description}`,
).join(' ');

export const FAQ: FaqItem[] = [
  item(
    'root',
    'Do I need root access to debloat my phone?',
    "No. AI Phone Debloater does not need root or an unlocked bootloader. It uses standard ADB package-manager commands (<code>pm disable-user</code> and <code>pm uninstall -k</code>) that change an app's state for one Android user profile, user 0 by default, and it never writes to the system partition.",
  ),
  item(
    'backup',
    'What should I back up before debloating, and how do I stay safe?',
    `AI Phone Debloater saves a snapshot of package states before it changes anything, and it refuses to touch ${RULE_STATS.critical} critical system packages. A snapshot records which packages were installed and enabled, not your files, so back up photos and other important data first. Start with Tier 1, and in the CLI run <code>--dry-run</code> to preview a plan before you apply it.`,
  ),
  item(
    'restore-apps',
    'Can I restore an app after removing it?',
    'Yes. AI Phone Debloater writes a snapshot before every change, and the CLI restores it with <code>--restore</code>. A single app can also be brought back over ADB: <code>adb shell cmd package install-existing --user 0 &lt;package&gt;</code> for an uninstalled app, or <code>adb shell pm enable --user 0 &lt;package&gt;</code> for a disabled one. System apps stay on the read-only system image; they are only removed for the user profile.',
  ),
  item(
    'benefits',
    'What are the benefits of debloating an Android phone?',
    'Disabling preinstalled apps stops their background services, which frees memory and reduces background battery and data use. It also turns off the OEM and carrier advertising and telemetry services that the rules cover. The gain depends on the phone and on what was running; AI Phone Debloater does not publish measurements.',
  ),
  item(
    'comparison',
    'What does AI Phone Debloater do that a manual ADB debloat does not?',
    `AI Phone Debloater checks every package against ${RULE_STATS.total} curated rules: ${RULE_STATS.removable} removal rules in three safety tiers and ${RULE_STATS.critical} critical system packages that it refuses to touch. It saves a restore snapshot before each change, and it runs three ways: a Python CLI, a web app in the browser, and a prompt for AI coding agents. It is free, MIT-licensed and needs no root.`,
  ),
  item(
    'ota',
    'Will debloating affect OTA system updates?',
    `No, with one exception. AI Phone Debloater changes package state for a user profile and never modifies the read-only system partition, so official over-the-air updates keep downloading and installing. The exception is the single Tier 3 rule, the Transsion OTA updater (<code>${TIER_3_RULE.package}</code>) on Tecno, Infinix and itel phones: disabling it stops system updates until you enable it again.`,
  ),
  item(
    'safety-tiers',
    'What are the package safety tiers?',
    `AI Phone Debloater sorts every rule into four safety tiers. ${tierSentence}`,
  ),
  item(
    'adb-setup',
    'How do I enable USB debugging (ADB) on my Android phone?',
    'To use AI Phone Debloater, turn on USB debugging. Open <strong>Settings &gt; About phone</strong> and tap <strong>Build number</strong> seven times to unlock Developer options (on Xiaomi phones, tap the MIUI or OS version instead). Then open <strong>Developer options</strong>, turn on <strong>USB debugging</strong>, connect the phone by USB and accept the &quot;Allow USB debugging&quot; prompt. On Xiaomi phones also turn on <em>Install via USB</em> and <em>USB debugging (Security settings)</em>.',
  ),
  item(
    'oem-rules',
    'How do the OEM debloat rules work across phone brands?',
    `AI Phone Debloater reads the phone's manufacturer over ADB (<code>ro.product.manufacturer</code>) and loads the universal rules plus the rule files that match that brand; if the manufacturer is unknown, it loads every OEM file. The rules cover Samsung, Xiaomi, Google Pixel, OnePlus, Oppo, Realme, Vivo, Motorola, Huawei and Transsion (Tecno, Infinix, itel). Every rule is listed in the <a href="/oems">package list by OEM</a>.`,
  ),
];
