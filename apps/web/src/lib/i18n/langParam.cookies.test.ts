import { NextRequest, NextResponse } from "next/server";
import { getRedirectUrl } from "next/experimental/testing/server";
import { describe, expect, it } from "vitest";

import { LOCALE_COOKIE } from "@/i18n/config";

import { applyLangParam } from "./langParam";

// Row 4 — valid lang, GET, `response` is already a redirect (auth-gate 3xx) →
// set the locale cookie on that existing redirect; do not add a second one.
describe("applyLangParam — row 4: response already a redirect", () => {
  it("sets the cookie on the existing redirect and returns the same instance", () => {
    const request = new NextRequest("https://example.com/trips?lang=vi");
    const loginUrl = new URL("https://example.com/auth/login?next=%2Ftrips%3Flang%3Dvi");
    const response = NextResponse.redirect(loginUrl);

    const result = applyLangParam(request, response);

    expect(result).toBe(response);
    expect(getRedirectUrl(result)).toBe(loginUrl.toString());
    expect(result.cookies.get(LOCALE_COOKIE)?.value).toBe("vi");
  });
});

// Row 5 (cookie carry-over) — Supabase session cookies present on the
// incoming `response` must survive onto the newly built redirect, or the
// user is logged out.
describe("applyLangParam — row 5: cookie carry-over onto the new redirect", () => {
  it("copies every cookie from response onto the redirect", () => {
    const request = new NextRequest("https://example.com/trips?lang=vi");
    const response = NextResponse.next();
    response.cookies.set("sb-access-token", "session-value", {
      path: "/",
      sameSite: "lax",
    });
    response.cookies.set("sb-refresh-token", "refresh-value", {
      path: "/",
      sameSite: "lax",
    });

    const result = applyLangParam(request, response);

    expect(getRedirectUrl(result)).not.toBeNull();
    expect(result.cookies.get("sb-access-token")?.value).toBe("session-value");
    expect(result.cookies.get("sb-refresh-token")?.value).toBe("refresh-value");
    expect(result.cookies.get(LOCALE_COOKIE)?.value).toBe("vi");
  });
});
