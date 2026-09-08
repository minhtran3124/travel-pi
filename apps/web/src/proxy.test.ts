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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

// Mutable per-test knob: whether getClaims() rejects, simulating an auth
// backend outage. Read by the createServerClient mock below.
let shouldRejectClaims = false;

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
          if (shouldRejectClaims) {
            throw new Error("auth backend unreachable");
          }
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

// Rows 1-3 must prove their own guard was the one that returned early —
// not just that the cookie survived, which row 5 (a real redirect) would
// also satisfy. `getRedirectUrl` returning null is the unambiguous signal
// that no redirect was built (NextResponse.next() carries no Location).
function expectNoRedirectBuilt(response: NextResponse): void {
  expect(getRedirectUrl(response)).toBeNull();
}

describe("proxy — updateSession + applyLangParam composition", () => {
  beforeEach(() => {
    hasClaims = true;
    shouldRejectClaims = false;
  });

  it("row 1: no lang param — rotated cookie still lands on the response", async () => {
    const request = new NextRequest("https://example.com/", {
      headers: { "sec-fetch-dest": "document" },
    });

    const result = await proxy(request);

    expectRotatedCookieSurvives(result);
    expectNoRedirectBuilt(result);
  });

  it("row 2: lang present but not a known locale — rotated cookie still lands on the response", async () => {
    const request = new NextRequest("https://example.com/?lang=xx", {
      headers: { "sec-fetch-dest": "document" },
    });

    const result = await proxy(request);

    expectRotatedCookieSurvives(result);
    expectNoRedirectBuilt(result);
  });

  it("row 3: non-document request — rotated cookie still lands on the response", async () => {
    const request = new NextRequest("https://example.com/?lang=vi", {
      headers: { "sec-fetch-dest": "empty" },
    });

    const result = await proxy(request);

    expectRotatedCookieSurvives(result);
    expectNoRedirectBuilt(result);
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

describe("proxy — auth backend outage (getClaims() rejects)", () => {
  beforeEach(() => {
    hasClaims = true;
    shouldRejectClaims = true;
    // proxy.ts's catch handler logs via console.error(). In this test file
    // (node environment + next/experimental/testing/server's getRedirectUrl
    // imported above), letting a real thrown Error reach console.error()
    // after an async rejection crosses a function boundary trips a Next/Node
    // AsyncLocalStorage invariant unrelated to the code under test — stub it
    // so the real behavior under test (fail-closed routing) runs, and assert
    // the pathname was logged instead of relying on the raw console call.
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fails closed: a protected path redirects to /auth/login", async () => {
    const request = new NextRequest("https://example.com/trips", {
      headers: { "sec-fetch-dest": "document" },
    });

    const result = await proxy(request);

    expect(result.status).toBe(307);
    expect(new URL(result.headers.get("location")!).pathname).toBe(
      "/auth/login",
    );
    expect(console.error).toHaveBeenCalledTimes(1);
    expect(console.error).toHaveBeenCalledWith(
      expect.stringContaining("/trips"),
      expect.anything(),
    );
  });

  it("fails closed: a protected path's redirect carries next back to the originally requested path", async () => {
    const request = new NextRequest("https://example.com/trips?lang=vi", {
      headers: { "sec-fetch-dest": "document" },
    });

    const result = await proxy(request);

    const location = new URL(result.headers.get("location")!);
    expect(location.pathname).toBe("/auth/login");
    expect(location.searchParams.get("next")).toBe("/trips?lang=vi");
  });

  it("fails open: an unprotected path still renders", async () => {
    const request = new NextRequest("https://example.com/", {
      headers: { "sec-fetch-dest": "document" },
    });

    const result = await proxy(request);

    expect(result.status < 300 || result.status >= 400).toBe(true);
  });

  it("fails open: /auth/login itself still renders — the recovery path must not also be gated", async () => {
    const request = new NextRequest("https://example.com/auth/login", {
      headers: { "sec-fetch-dest": "document" },
    });

    const result = await proxy(request);

    expect(getRedirectUrl(result)).toBeNull();
  });
});

describe("proxy.ts — imports isProtected from the shared middleware module", () => {
  it("does not re-list the protected prefixes", async () => {
    const { readFileSync } = await import("node:fs");
    const source = readFileSync(
      new URL("./proxy.ts", import.meta.url),
      "utf-8",
    );

    expect(source).toMatch(
      /import\s*\{[^}]*\bisProtected\b[^}]*\}\s*from\s*['"]@\/lib\/supabase\/middleware['"]/,
    );
  });
});
