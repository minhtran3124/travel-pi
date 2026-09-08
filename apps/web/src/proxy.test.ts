// @vitest-environment node
//
// The first test that actually loads proxy.ts, so the composition of
// updateSession + applyLangParam is covered by something other than a grep
// (see task 6.2 brief). @supabase/ssr is mocked so `getClaims()` invokes the
// `setAll()` cookie callback with a rotated `sb-*-auth-token` cookie — that is
// what makes session-cookie rotation observable without a real Supabase call.
//
// Under jsdom, `NextResponse.next({ request })` (used inside updateSession)
// throws on `Headers`, hence the node environment override above.
import { NextRequest, NextResponse } from "next/server";
import { getRedirectUrl } from "next/experimental/testing/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const ROTATED_COOKIE_NAME = "sb-project-auth-token";
const ROTATED_COOKIE_VALUE = "rotated-session-value";
const ROTATED_COOKIE_OPTIONS = {
  httpOnly: true,
  maxAge: 3600,
  path: "/",
  sameSite: "lax" as const,
};

// Mutable per-test knob: whether getClaims() resolves an authenticated
// subject. Read by the createServerClient mock below.
let hasClaims = true;

vi.mock("@supabase/ssr", () => ({
  createServerClient: vi.fn(
    (
      _url: string,
      _key: string,
      config: {
        cookies: {
          setAll: (
            cookies: { name: string; value: string; options?: object }[],
          ) => void;
        };
      },
    ) => ({
      auth: {
        getClaims: async () => {
          // The real client rotates the auth-token cookie via setAll() as a
          // side effect of refreshing the session — reproduce that here.
          config.cookies.setAll([
            {
              name: ROTATED_COOKIE_NAME,
              value: ROTATED_COOKIE_VALUE,
              options: ROTATED_COOKIE_OPTIONS,
            },
          ]);
          return { data: { claims: hasClaims ? { sub: "user-1" } : null } };
        },
      },
    }),
  ),
}));

// Imported after the mock so proxy.ts (via updateSession) picks it up.
const { proxy } = await import("./proxy");

function expectRotatedCookieSurvives(response: NextResponse): void {
  const cookie = response.cookies.get(ROTATED_COOKIE_NAME);
  expect(cookie?.value).toBe(ROTATED_COOKIE_VALUE);
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.maxAge).toBe(3600);
}

describe("proxy — updateSession + applyLangParam composition", () => {
  beforeEach(() => {
    hasClaims = true;
  });

  it("row 1: no lang param — rotated cookie still lands on the response", async () => {
    const request = new NextRequest("https://example.com/", {
      headers: { "sec-fetch-dest": "document" },
    });

    const result = await proxy(request);

    expectRotatedCookieSurvives(result);
  });

  it("row 2: lang present but not a known locale — rotated cookie still lands on the response", async () => {
    const request = new NextRequest("https://example.com/?lang=xx", {
      headers: { "sec-fetch-dest": "document" },
    });

    const result = await proxy(request);

    expectRotatedCookieSurvives(result);
  });

  it("row 3: non-document request — rotated cookie still lands on the response", async () => {
    const request = new NextRequest("https://example.com/?lang=vi", {
      headers: { "sec-fetch-dest": "empty" },
    });

    const result = await proxy(request);

    expectRotatedCookieSurvives(result);
  });

  it("row 4: updateSession itself returns the auth-gate 307 — rotated cookie carried onto it", async () => {
    hasClaims = false;
    const request = new NextRequest("https://example.com/trips?lang=vi", {
      headers: { "sec-fetch-dest": "document" },
    });

    const result = await proxy(request);

    expect(getRedirectUrl(result)).toContain("/auth/login");
    expectRotatedCookieSurvives(result);
  });

  it("row 5: valid lang on a document GET builds a NEW redirect — rotated cookie must survive the copy", async () => {
    const request = new NextRequest("https://example.com/?lang=vi", {
      headers: { "sec-fetch-dest": "document" },
    });

    const result = await proxy(request);

    expect(getRedirectUrl(result)).not.toBeNull();
    expectRotatedCookieSurvives(result);
  });
});
