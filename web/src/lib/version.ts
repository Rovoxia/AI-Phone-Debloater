/**
 * Single Source of Truth Version Module
 * =====================================
 * Dynamically resolves application SemVer from root `VERSION` file,
 * Vite compile-time definition (__SITE_VERSION__), or web/package.json.
 */
import pkg from '../../package.json';

declare const __SITE_VERSION__: string | undefined;

export const SITE_VERSION: string =
  typeof __SITE_VERSION__ !== 'undefined' && __SITE_VERSION__
    ? __SITE_VERSION__
    : pkg.version || '1.0.0';

export function getVersion(): string {
  return SITE_VERSION;
}
