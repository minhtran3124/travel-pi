import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// `env.ts` reads NEXT_PUBLIC_SUPABASE_* at module scope, so each case needs a
// fresh module graph (vi.resetModules) plus a dynamic import — a static
// top-level import would only ever see the module as loaded once, with
// whichever env vars were present at that first load.

describe("register", () => {
  const ORIGINAL_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const ORIGINAL_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = ORIGINAL_URL;
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = ORIGINAL_KEY;
  });

  it("is exported as a function", async () => {
    const { register } = await import("./instrumentation");
    expect(typeof register).toBe("function");
  });

  it("throws naming the missing variable when both env vars are absent", async () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

    const { register } = await import("./instrumentation");

    expect(() => register()).toThrow(/NEXT_PUBLIC_SUPABASE_URL/);
  });

  it("returns without throwing when both env vars are present", async () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://test.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "test-publishable-key";

    const { register } = await import("./instrumentation");

    expect(() => register()).not.toThrow();
  });
});
