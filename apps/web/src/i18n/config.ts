// Locale configuration shared across server + client. No UI strings here.
export const locales = ["en", "vi"] as const;

export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";

// Cookie that persists the user's chosen locale (no URL-based routing).
export const LOCALE_COOKIE = "locale";

export function isLocale(value: string | undefined): value is Locale {
  return value != null && (locales as readonly string[]).includes(value);
}
