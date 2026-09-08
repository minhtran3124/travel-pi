import { NextRequest, NextResponse } from "next/server";
import { getRedirectUrl } from "next/experimental/testing/server";
import { describe, expect, it } from "vitest";

import { LOCALE_COOKIE } from "@/i18n/config";

import { applyLangParam } from "./langParam";

// Row 1 — no `lang` param → return `response` untouched (identity).
describe("applyLangParam — row 1: no lang param", () => {
  it("returns the same response instance", () => {
    const request = new NextRequest("https://example.com/trips");
    const response = NextResponse.next();

    const result = applyLangParam(request, response);

    expect(result).toBe(response);
  });
});

// Row 2 — `lang` present but not a known locale → return `response` untouched.
describe("applyLangParam — row 2: unknown lang value", () => {
  it("returns the same response instance and sets no cookie", () => {
    const request = new NextRequest("https://example.com/trips?lang=xx");
    const response = NextResponse.next();

    const result = applyLangParam(request, response);

    expect(result).toBe(response);
    expect(result.cookies.get(LOCALE_COOKIE)).toBeUndefined();
  });
});

// Row 5 — valid lang, GET, normal (non-redirect) response → redirect to the
// same URL with `lang` stripped, and the locale cookie set on the redirect.
describe("applyLangParam — row 5: valid lang on a normal response", () => {
  it("redirects to the same URL without lang and sets the locale cookie", () => {
    const request = new NextRequest("https://example.com/trips?lang=vi&foo=bar");
    const response = NextResponse.next();

    const result = applyLangParam(request, response);

    const redirectUrl = getRedirectUrl(result);
    expect(redirectUrl).not.toBeNull();
    const url = new URL(redirectUrl!);
    expect(url.pathname).toBe("/trips");
    expect(url.searchParams.get("lang")).toBeNull();
    expect(url.searchParams.get("foo")).toBe("bar");

    const cookie = result.cookies.get(LOCALE_COOKIE);
    expect(cookie?.value).toBe("vi");
  });
});
