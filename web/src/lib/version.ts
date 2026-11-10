/**
 * Single Source of Truth Version Module
 * =====================================
 * Resolves application SemVer directly from web/package.json.
 * Changing version in package.json automatically propagates across
 * the entire site, components, and pages.
 */
import pkg from '../../package.json';

export const SITE_VERSION: string = pkg.version || '1.1.1';

export function getVersion(): string {
  return SITE_VERSION;
}
