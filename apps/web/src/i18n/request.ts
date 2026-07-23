import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import { defaultLocale, isLocale, LOCALE_COOKIE } from "./config";

// Cookie-based locale (no i18n routing). The active locale is read from the
// `locale` cookie on every request and falls back to the default.
export default getRequestConfig(async () => {
  const store = await cookies();
  const cookieLocale = store.get(LOCALE_COOKIE)?.value;
  const locale = isLocale(cookieLocale) ? cookieLocale : defaultLocale;

  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
    // Shared formatting presets — components use `useFormatter()`/`getFormatter()`
    // so dates and currency follow the active locale automatically.
    formats: {
      dateTime: {
        short: { day: "numeric", month: "short", year: "numeric" },
        long: { day: "numeric", month: "long", year: "numeric" },
      },
      number: {
        usd: { style: "currency", currency: "USD" },
      },
    },
  };
});
