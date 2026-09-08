import { NextRequest, NextResponse } from "next/server";
import { getRedirectUrl } from "next/experimental/testing/server";
import { describe, expect, it } from "vitest";

import { LOCALE_COOKIE } from "@/i18n/config";

import { applyLangParam } from "./langParam";

// Row 3 — a request must be a document navigation (GET, not /api/*, and
// sec-fetch-dest is "document" or absent) or applyLangParam is a no-op.
// Exactly six cases, per the task brief: (a)-(e) are suppressed and returned
// by identity; (f) is the one case with no sec-fetch-dest header, which is
// still a genuine navigation (curl, link unfurlers) and must redirect.
describe("applyLangParam — row 3: document-navigation suppression", () => {
  it("(a) POST to a page URL is returned untouched", () => {
    const request = new NextRequest("https://example.com/trips?lang=vi", {
      method: "POST",
    });
    const response = NextResponse.next();

    const result = applyLangParam(request, response);

    expect(result).toBe(response);
  });

  it("(b) HEAD is returned untouched", () => {
    const request = new NextRequest("https://example.com/trips?lang=vi", {
      method: "HEAD",
    });
    const response = NextResponse.next();

    const result = applyLangParam(request, response);

    expect(result).toBe(response);
  });

  it("(c) GET /api/be/trips?lang=vi is returned untouched", () => {
    const request = new NextRequest("https://example.com/api/be/trips?lang=vi", {
      method: "GET",
      headers: { "sec-fetch-dest": "document" },
    });
    const response = NextResponse.next();

    const result = applyLangParam(request, response);

    expect(result).toBe(response);
  });

  it("(d) GET with sec-fetch-dest: empty is returned untouched", () => {
    const request = new NextRequest("https://example.com/trips?lang=vi", {
      method: "GET",
      headers: { "sec-fetch-dest": "empty" },
    });
    const response = NextResponse.next();

    const result = applyLangParam(request, response);

    expect(result).toBe(response);
  });

  it("(e) GET with sec-fetch-dest: image is returned untouched", () => {
    const request = new NextRequest("https://example.com/trips?lang=vi", {
      method: "GET",
      headers: { "sec-fetch-dest": "image" },
    });
    const response = NextResponse.next();

    const result = applyLangParam(request, response);

    expect(result).toBe(response);
  });

  it("(f) GET with no sec-fetch-dest header still redirects with the cookie set", () => {
    const request = new NextRequest("https://example.com/trips?lang=vi", {
      method: "GET",
    });
    const response = NextResponse.next();

    const result = applyLangParam(request, response);

    expect(getRedirectUrl(result)).not.toBeNull();
    expect(result.cookies.get(LOCALE_COOKIE)?.value).toBe("vi");
  });
});
