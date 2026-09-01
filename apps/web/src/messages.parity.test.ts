import { describe, expect, it } from "vitest";

import en from "../messages/en.json";
import vi from "../messages/vi.json";

/**
 * Collect every leaf key path in a messages object as dot-delimited strings.
 * A leaf is any value that is not a plain nested object (strings, and the
 * arrays/primitives next-intl treats as terminal message values).
 */
function collectKeyPaths(
  value: unknown,
  prefix = "",
  out: string[] = [],
): string[] {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      collectKeyPaths(child, prefix ? `${prefix}.${key}` : key, out);
    }
  } else {
    out.push(prefix);
  }
  return out;
}

describe("messages en/vi parity", () => {
  const enKeys = new Set(collectKeyPaths(en));
  const viKeys = new Set(collectKeyPaths(vi));

  it("has no key present in en but missing from vi", () => {
    const missingInVi = [...enKeys].filter((k) => !viKeys.has(k)).sort();
    expect(missingInVi, `Keys in en.json missing from vi.json:\n${missingInVi.join("\n")}`).toEqual([]);
  });

  it("has no key present in vi but missing from en", () => {
    const missingInEn = [...viKeys].filter((k) => !enKeys.has(k)).sort();
    expect(missingInEn, `Keys in vi.json missing from en.json:\n${missingInEn.join("\n")}`).toEqual([]);
  });
});
