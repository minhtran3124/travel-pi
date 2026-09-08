import { describe, expect, it } from "vitest";

import { panelKey, panelSubLabel, type PanelArtifact } from "./panel";

function artifact(kind: string, data: unknown): PanelArtifact {
  return { toolCallId: "t1", kind, data };
}

describe("panelKey", () => {
  it("returns `kind:category` for a places panel with a category", () => {
    expect(panelKey(artifact("places", { category: "cafe" }))).toBe("places:cafe");
  });

  it("returns bare `places` when category is null", () => {
    expect(panelKey(artifact("places", { category: null }))).toBe("places");
  });

  it("returns bare `places` when data has no category field", () => {
    expect(panelKey(artifact("places", {}))).toBe("places");
  });

  it("returns bare kind for non-places kinds", () => {
    expect(panelKey(artifact("weather", {}))).toBe("weather");
  });

  it("keys off category_key, not the (possibly localized) category", () => {
    expect(
      panelKey(artifact("places", { category_key: "cafe", category: "quán cà phê" })),
    ).toBe("places:cafe");
  });

  it("falls back to category when category_key is absent", () => {
    expect(panelKey(artifact("places", { category: "cafe" }))).toBe("places:cafe");
  });
});

describe("panelSubLabel", () => {
  it("mirrors the category for a places panel", () => {
    expect(panelSubLabel(artifact("places", { category: "cafe" }))).toBe("cafe");
  });

  it("returns null when category is null", () => {
    expect(panelSubLabel(artifact("places", { category: null }))).toBeNull();
  });

  it("returns null for non-places kinds", () => {
    expect(panelSubLabel(artifact("weather", {}))).toBeNull();
  });

  it("returns the display category even when category_key differs", () => {
    expect(
      panelSubLabel(artifact("places", { category_key: "cafe", category: "quán cà phê" })),
    ).toBe("quán cà phê");
  });
});
