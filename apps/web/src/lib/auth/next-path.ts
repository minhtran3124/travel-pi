/**
 * Validation for the post-authentication return path (`?next=`).
 *
 * The rule is allowlist, not blocklist: resolve the candidate against the site
 * origin and keep it only when the result stays on that origin. Character
 * blocklists do not hold here — `/\evil.example` and `/<tab>/evil.example` both
 * start with a single `/`, yet WHATWG URL parsing turns them into
 * `https://evil.example/`, and string-concatenating `@evil.example` onto an
 * origin moves the host into the userinfo slot.
 *
 * @param value Untrusted candidate, typically a query param or form field.
 * @param origin Absolute site origin to resolve against.
 * @returns A same-origin path (with query and hash), or `/` when the candidate
 *   is missing, unparseable, or points anywhere else.
 */
export function safeNextPath(value: unknown, origin: string): string {
  if (typeof value !== "string" || value === "") return "/";

  let base: URL;
  try {
    base = new URL(origin);
  } catch {
    return "/";
  }

  let resolved: URL;
  try {
    resolved = new URL(value, base);
  } catch {
    return "/";
  }

  if (resolved.origin !== base.origin) return "/";

  return `${resolved.pathname}${resolved.search}${resolved.hash}`;
}
