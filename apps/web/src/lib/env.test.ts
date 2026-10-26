import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

// The module reads both variables at module scope, so vi.stubEnv after import
// has no effect on it. Each missing-variable case must vi.resetModules() and
// dynamically re-import the module. src/test/setup.ts sets both variables for
// every test file, so a case must delete them explicitly before importing.

const ORIGINAL_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ORIGINAL_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

afterEach(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = ORIGINAL_URL;
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = ORIGINAL_KEY;
});

describe("requireSupabaseEnv", () => {
  it("returns both values when set", async () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "publishable-key";
    vi.resetModules();
    const { requireSupabaseEnv } = await import("./env");

    expect(requireSupabaseEnv()).toEqual({
      url: "https://example.supabase.co",
      key: "publishable-key",
    });
  });

  it("throws naming NEXT_PUBLIC_SUPABASE_URL when it is absent", async () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "publishable-key";
    vi.resetModules();
    const { requireSupabaseEnv } = await import("./env");

    expect(() => requireSupabaseEnv()).toThrow("NEXT_PUBLIC_SUPABASE_URL");
  });

  it("throws naming NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY when it is absent", async () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    vi.resetModules();
    const { requireSupabaseEnv } = await import("./env");

    expect(() => requireSupabaseEnv()).toThrow(
      "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    );
  });

  it("states the build-time requirement in the error message", async () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "publishable-key";
    vi.resetModules();
    const { requireSupabaseEnv } = await import("./env");

    expect(() => requireSupabaseEnv()).toThrow(/build/i);
  });
});

describe("env.ts source-text gate", () => {
  // Positive assertion: Next inlines NEXT_PUBLIC_* only for literal
  // `process.env.NAME` access. A negative check for `process.env[` alone
  // still lets `const { NEXT_PUBLIC_SUPABASE_URL } = process.env` through,
  // which ships `undefined` to the browser just the same. Requiring the
  // literal text covers every non-inlined variant at once.
  it("reads both variables via literal process.env.NAME access", () => {
    const source = readFileSync(join(__dirname, "env.ts"), "utf-8");

    expect(source).toContain("process.env.NEXT_PUBLIC_SUPABASE_URL");
    expect(source).toContain(
      "process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    );
  });

  it("never uses dynamic process.env[ access", () => {
    const source = readFileSync(join(__dirname, "env.ts"), "utf-8");

    expect(source).not.toContain("process.env[");
  });
});
