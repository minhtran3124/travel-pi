import { describe, expect, it } from "vitest";

import { safeNextPath } from "./next-path";

const ORIGIN = "https://app.example.com";

describe("safeNextPath", () => {
  it.each([
    ["/trips", "/trips"],
    ["/trips/abc?tab=expenses", "/trips/abc?tab=expenses"],
    ["/trips#notes", "/trips#notes"],
    [`${ORIGIN}/trips`, "/trips"],
  ])("keeps the same-origin path %s", (input, expected) => {
    expect(safeNextPath(input, ORIGIN)).toBe(expected);
  });

  it.each([
    ["protocol-relative", "//evil.example"],
    ["backslash", "/\\evil.example"],
    ["encoded backslash", decodeURIComponent("/%5Cevil.example")],
    ["tab-smuggled", "/\t/evil.example"],
    ["absolute foreign URL", "https://evil.example/trips"],
    ["scheme-changing", "javascript:alert(1)"],
  ])("rejects %s payloads", (_label, input) => {
    expect(safeNextPath(input, ORIGIN)).toBe("/");
  });

  it("keeps an @ in the path rather than letting it become a host", () => {
    // Concatenating this onto an origin would move the host into userinfo;
    // resolving it keeps it a path segment.
    expect(safeNextPath("@evil.example", ORIGIN)).toBe("/@evil.example");
  });

  it.each([[null], [undefined], [""], [42], [{}]])(
    "falls back to / for %s",
    (input) => {
      expect(safeNextPath(input, ORIGIN)).toBe("/");
    },
  );

  it("falls back to / when the origin is unusable", () => {
    expect(safeNextPath("/trips", "not-an-origin")).toBe("/");
  });
});
