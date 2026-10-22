import { afterEach, describe, expect, it, vi } from "vitest";

import { researchEnabled } from "./features";

describe("researchEnabled", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("is on by default, like the API's research_enabled", () => {
    vi.stubEnv("NEXT_PUBLIC_RESEARCH_ENABLED", undefined);
    expect(researchEnabled()).toBe(true);
  });

  it("is off only when explicitly set to false", () => {
    vi.stubEnv("NEXT_PUBLIC_RESEARCH_ENABLED", "false");
    expect(researchEnabled()).toBe(false);
  });

  it("stays on for any other value", () => {
    vi.stubEnv("NEXT_PUBLIC_RESEARCH_ENABLED", "true");
    expect(researchEnabled()).toBe(true);
  });
});
