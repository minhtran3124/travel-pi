import { NextResponse, type NextRequest } from "next/server";

import { isLocale, LOCALE_COOKIE } from "@/i18n/config";

// Must match i18n/locale.ts:17-21 exactly — same cookie, same attributes.
const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

function isDocumentNavigation(request: NextRequest): boolean {
  if (request.method !== "GET") return false;
  if (request.nextUrl.pathname.startsWith("/api/")) return false;
  const dest = request.headers.get("sec-fetch-dest");
  return dest === "document" || dest === null;
}

function setLocaleCookie(response: NextResponse, locale: string): void {
  response.cookies.set(LOCALE_COOKIE, locale, {
    path: "/",
    maxAge: ONE_YEAR_SECONDS,
    sameSite: "lax",
  });
}

// design.md §4.3 — applies a `?lang=` query param to the locale cookie.
export function applyLangParam(
  request: NextRequest,
  response: NextResponse,
): NextResponse {
  const lang = request.nextUrl.searchParams.get("lang") ?? undefined;

  // Row 1: no lang param.
  if (lang === undefined) return response;

  // Row 2: lang present but not a known locale.
  if (!isLocale(lang)) return response;

  // Row 3: not a document navigation.
  if (!isDocumentNavigation(request)) return response;

  // Row 4: response is already a redirect — set the cookie on it, no second redirect.
  if (response.status >= 300 && response.status < 400) {
    setLocaleCookie(response, lang);
    return response;
  }

  // Row 5: build a redirect to the same URL with only `lang` removed, carry
  // over every cookie already on `response`, then set the locale cookie.
  const redirectUrl = new URL(request.nextUrl);
  redirectUrl.searchParams.delete("lang");
  const redirectResponse = NextResponse.redirect(redirectUrl);
  for (const cookie of response.cookies.getAll()) {
    redirectResponse.cookies.set(cookie);
  }
  setLocaleCookie(redirectResponse, lang);
  return redirectResponse;
}
